"""
Data Preprocessing Pipeline
Orchestrates type detection and data cleaning
"""
import os
import json
from pathlib import Path
from typing import Dict, Tuple, Optional
import pandas as pd

from app.services.data_processing.type_detector import TypeDetector
from app.services.data_processing.cleaner import DataCleaner


class DataPreprocessor:
    """
    Main preprocessing pipeline that coordinates type detection and cleaning
    """
    
    def __init__(self, processed_dir: str = "data/processed"):
        """
        Initialize preprocessor
        
        Args:
            processed_dir: Directory to save processed files
        """
        self.processed_dir = Path(processed_dir)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
    
    def process_dataset(
        self,
        file_path: str,
        dataset_id: int,
        user_id: int,
        clean_data: bool = True,
        cleaning_strategy: str = 'auto'
    ) -> Dict[str, any]:
        """
        Complete preprocessing pipeline for a dataset
        
        Args:
            file_path: Path to original dataset file
            dataset_id: Database ID of dataset
            user_id: User ID who owns the dataset
            clean_data: Whether to clean the data
            cleaning_strategy: Cleaning strategy to use
        
        Returns:
            Dictionary with processing results and metadata
        """
        try:
            # Load dataset (encoding-aware — records which encoding worked)
            encoding_used = None
            try:
                from app.services.data_processing.io_utils import read_tabular_ex
                df_original, encoding_used = read_tabular_ex(file_path)
            except Exception:
                df_original = self._load_dataset(file_path)

            if df_original is None or df_original.empty:
                return {
                    'success': False,
                    'error': 'Failed to load dataset or dataset is empty'
                }
            
            # Step 0: Structural sanitation — whitespace/nbsp hygiene, sentinel
            # missing tokens ("N/A", "-", Excel error codes) -> NaN, repeated
            # header rows, empty rows, junk "Unnamed:" columns. Must run BEFORE
            # type detection so financial columns aren't polluted by sentinels.
            df_sanitized, sanitize_actions = DataCleaner.sanitize_dataframe(df_original)

            # Step 1: Detect types (financial-aware) + per-column format info
            type_map, format_info = TypeDetector.detect_all_types_ex(df_sanitized)
            type_stats = TypeDetector.get_type_statistics(df_sanitized, type_map)

            # Step 2: Analyze data quality (before cleaning)
            missing_analysis = DataCleaner.analyze_missing_values(df_sanitized)
            duplicate_analysis = DataCleaner.analyze_duplicates(df_sanitized)
            outlier_analysis = DataCleaner.detect_outliers(df_sanitized, type_map)

            # Step 3: Clean data (if requested)
            df_cleaned = df_sanitized.copy()
            cleaning_report = None
            actions_taken = {'sanitation': sanitize_actions} if sanitize_actions else {}
            if format_info:
                actions_taken['detected_formats'] = {
                    col: {k: v for k, v in info.items() if v}
                    for col, info in format_info.items()
                }

            if clean_data:
                # Canonical order (CP-02/CP-03):
                #   normalize labels → deduplicate → convert types → missing audit
                # Conversion runs BEFORE the missing pass so parse failures are
                # counted and reported, never leaked as silent nulls.

                # Normalize categorical columns (fix case and typos)
                df_cleaned, normalization_report = DataCleaner.normalize_categorical_columns(
                    df_cleaned, type_map, fix_case=True, fix_typos=True, typo_threshold=0.8
                )
                actions_taken['categorical_normalization'] = normalization_report

                # Remove exact duplicates (after normalization so variant-only
                # duplicates collapse and are removed)
                df_cleaned, duplicates_removed = DataCleaner.remove_duplicates(df_cleaned)
                actions_taken['duplicates'] = f'Removed {duplicates_removed} duplicate rows'

                # Snapshot nulls before conversion for the reconciliation table
                nulls_before = {c: int(df_cleaned[c].isna().sum()) for c in df_cleaned.columns}

                # Convert types (parse-failure nulls appear here)
                df_cleaned = TypeDetector.convert_types(df_cleaned, type_map)
                nulls_after = {c: int(df_cleaned[c].isna().sum()) for c in df_cleaned.columns}

                # Handle missing values LAST — sees original blanks AND parse
                # failures; numeric/date stay blank (never fabricated), labels
                # filled with "Unknown"
                df_cleaned, missing_actions = DataCleaner.handle_missing_values(
                    df_cleaned, type_map, strategy=cleaning_strategy
                )
                actions_taken['missing_values'] = missing_actions

                # Null reconciliation — every remaining null is traceable (CP-02)
                reconciliation = {}
                for col in df_cleaned.columns:
                    before = nulls_before.get(col, 0)
                    after = nulls_after.get(col, before)
                    parse_failures = max(0, after - before)
                    final_nulls = int(df_cleaned[col].isna().sum())
                    if before or parse_failures or final_nulls:
                        reconciliation[col] = {
                            "nulls_before_convert": before,
                            "parse_failures": parse_failures,
                            "filled": 0,
                            "final_nulls": final_nulls,
                        }
                actions_taken['null_reconciliation'] = reconciliation

                # Generate cleaning report
                cleaning_report = DataCleaner.generate_cleaning_report(
                    df_original, df_cleaned, type_map, actions_taken
                )
                if encoding_used:
                    cleaning_report['source_encoding'] = encoding_used
                
                # Save cleaned dataset
                processed_path = self._save_processed_dataset(
                    df_cleaned, dataset_id, user_id
                )
                cleaning_report['processed_file_path'] = str(processed_path)
            
            # Step 4: Generate comprehensive metadata
            metadata = {
                'success': True,
                'dataset_id': dataset_id,
                'original_file': file_path,
                'original_shape': {
                    'rows': len(df_original),
                    'columns': len(df_original.columns)
                },
                'cleaned_shape': {
                    'rows': len(df_cleaned),
                    'columns': len(df_cleaned.columns)
                } if clean_data else None,
                'type_detection': {
                    'type_map': type_map,
                    'type_statistics': type_stats
                },
                'data_quality': {
                    'missing_values': missing_analysis,
                    'duplicates': duplicate_analysis,
                    'outliers': outlier_analysis
                },
                'cleaning_report': cleaning_report,
                'column_names': df_cleaned.columns.tolist(),
                'sample_data': json.loads(df_cleaned.head(5).to_json(orient='records'))
            }
            
            # Save metadata
            self._save_metadata(metadata, dataset_id, user_id)
            
            return metadata
        
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'dataset_id': dataset_id
            }
    
    def _load_dataset(self, file_path: str) -> Optional[pd.DataFrame]:
        """
        Load dataset from file
        
        Args:
            file_path: Path to dataset file
        
        Returns:
            DataFrame or None if loading fails
        """
        try:
            file_extension = Path(file_path).suffix.lower()
            if file_extension not in ('.csv', '.xlsx', '.xls'):
                return None
            from app.services.data_processing.io_utils import read_tabular
            return read_tabular(file_path)
        except Exception as e:
            print(f"Error loading dataset: {str(e)}")
            return None
    
    def _save_processed_dataset(
        self,
        df: pd.DataFrame,
        dataset_id: int,
        user_id: int
    ) -> Path:
        """
        Save processed dataset to file
        
        Args:
            df: Processed DataFrame
            dataset_id: Dataset ID
            user_id: User ID
        
        Returns:
            Path to saved file
        """
        # Create user directory
        user_dir = self.processed_dir / f"user_{user_id}"
        user_dir.mkdir(parents=True, exist_ok=True)

        # Parquet preserves dtypes exactly (dates stay dates, floats stay
        # floats — no re-parsing on every load) and reads ~10x faster than CSV.
        processed_file = user_dir / f"dataset_{dataset_id}_cleaned.parquet"
        try:
            df.to_parquet(processed_file, index=False)
        except Exception:
            # Fallback if a column defeats Arrow (e.g. mixed object types)
            processed_file = user_dir / f"dataset_{dataset_id}_cleaned.csv"
            df.to_csv(processed_file, index=False)

        # Drop any stale sibling from a previous format so loads are unambiguous
        for stale in (user_dir / f"dataset_{dataset_id}_cleaned.csv",
                      user_dir / f"dataset_{dataset_id}_cleaned.parquet"):
            if stale != processed_file and stale.exists():
                try:
                    stale.unlink()
                except OSError:
                    pass

        # Warm the cache with the freshly cleaned frame
        from app.core.dataframe_cache import df_cache
        df_cache.put(processed_file, df)

        return processed_file
    
    def _save_metadata(
        self,
        metadata: Dict,
        dataset_id: int,
        user_id: int
    ) -> Path:
        """
        Save processing metadata to JSON file
        
        Args:
            metadata: Metadata dictionary
            dataset_id: Dataset ID
            user_id: User ID
        
        Returns:
            Path to metadata file
        """
        user_dir = self.processed_dir / f"user_{user_id}"
        user_dir.mkdir(parents=True, exist_ok=True)
        
        metadata_file = user_dir / f"dataset_{dataset_id}_metadata.json"
        
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2, default=str)
        
        return metadata_file
    
    def get_processed_dataset(
        self,
        dataset_id: int,
        user_id: int
    ) -> Optional[pd.DataFrame]:
        """
        Load processed dataset from file
        
        Args:
            dataset_id: Dataset ID
            user_id: User ID
        
        Returns:
            DataFrame or None if not found
        """
        user_dir = self.processed_dir / f"user_{user_id}"
        parquet_file = user_dir / f"dataset_{dataset_id}_cleaned.parquet"
        csv_file = user_dir / f"dataset_{dataset_id}_cleaned.csv"   # legacy format
        processed_file = parquet_file if parquet_file.exists() else csv_file

        if not processed_file.exists():
            return None

        # Serve from the in-memory cache when the file hasn't changed —
        # avoids re-reading + re-parsing from disk on every query
        from app.core.dataframe_cache import df_cache
        cached = df_cache.get(processed_file)
        if cached is not None:
            return cached

        try:
            if processed_file.suffix == '.parquet':
                df = pd.read_parquet(processed_file)
            else:
                df = pd.read_csv(processed_file)
            df_cache.put(processed_file, df)
            return df
        except Exception as e:
            print(f"Error loading processed dataset: {str(e)}")
            return None
    
    def get_metadata(
        self,
        dataset_id: int,
        user_id: int
    ) -> Optional[Dict]:
        """
        Load processing metadata from file
        
        Args:
            dataset_id: Dataset ID
            user_id: User ID
        
        Returns:
            Metadata dictionary or None if not found
        """
        metadata_file = self.processed_dir / f"user_{user_id}" / f"dataset_{dataset_id}_metadata.json"
        
        if not metadata_file.exists():
            return None
        
        try:
            with open(metadata_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading metadata: {str(e)}")
            return None
    
    def analyze_only(self, file_path: str) -> Dict[str, any]:
        """
        Analyze dataset without cleaning (for preview purposes)
        
        Args:
            file_path: Path to dataset file
        
        Returns:
            Analysis results
        """
        try:
            df = self._load_dataset(file_path)
            
            if df is None or df.empty:
                return {
                    'success': False,
                    'error': 'Failed to load dataset or dataset is empty'
                }
            
            # Detect types
            type_map = TypeDetector.detect_all_types(df)
            type_stats = TypeDetector.get_type_statistics(df, type_map)
            
            # Analyze quality
            missing_analysis = DataCleaner.analyze_missing_values(df)
            duplicate_analysis = DataCleaner.analyze_duplicates(df)
            outlier_analysis = DataCleaner.detect_outliers(df, type_map)
            
            return {
                'success': True,
                'shape': {
                    'rows': len(df),
                    'columns': len(df.columns)
                },
                'type_detection': {
                    'type_map': type_map,
                    'type_statistics': type_stats
                },
                'data_quality': {
                    'missing_values': missing_analysis,
                    'duplicates': duplicate_analysis,
                    'outliers': outlier_analysis
                },
                'column_names': df.columns.tolist(),
                'sample_data': df.head(5).to_dict('records')
            }
        
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
