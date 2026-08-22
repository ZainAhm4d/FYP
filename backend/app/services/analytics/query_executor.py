"""
Query Executor
Executes query templates on datasets using Pandas operations
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import warnings

from app.services.analytics.anomaly_detection import detect_zscore, detect_trend_aware

warnings.filterwarnings('ignore')


class QueryExecutor:
    """Execute analytical queries on datasets"""
    
    def __init__(self, dataframe: pd.DataFrame):
        """
        Initialize with a dataset
        
        Args:
            dataframe: Pandas DataFrame to query
        """
        self.df = dataframe.copy()
    
    def execute_trend_over_time(
        self,
        metric_column: str,
        time_column: str,
        aggregation: str = 'sum',
        time_granularity: str = 'month'
    ) -> Dict[str, Any]:
        """
        Execute trend over time query
        
        Args:
            metric_column: Column to aggregate
            time_column: Date column for time axis
            aggregation: Aggregation method (sum, mean, count, min, max)
            time_granularity: Time grouping (day, week, month, quarter, year)
        
        Returns:
            Dictionary with query results and metadata
        """
        try:
            # Convert time column to datetime
            df = self.df.copy()
            df[time_column] = pd.to_datetime(df[time_column], errors='coerce')
            
            # Remove rows with invalid dates
            df = df.dropna(subset=[time_column])
            
            if len(df) == 0:
                return {
                    "success": False,
                    "error": "No valid date values found in time column"
                }
            
            # Create time period column based on granularity
            if time_granularity == 'day':
                df['time_period'] = df[time_column].dt.date
                df['time_label'] = df[time_column].dt.strftime('%Y-%m-%d')
            elif time_granularity == 'week':
                df['time_period'] = df[time_column].dt.to_period('W')
                df['time_label'] = df[time_column].dt.strftime('%Y-W%U')
            elif time_granularity == 'month':
                df['time_period'] = df[time_column].dt.to_period('M')
                df['time_label'] = df[time_column].dt.strftime('%Y-%m')
            elif time_granularity == 'quarter':
                df['time_period'] = df[time_column].dt.to_period('Q')
                df['time_label'] = df[time_column].dt.strftime('%Y-Q') + df[time_column].dt.quarter.astype(str)
            elif time_granularity == 'year':
                df['time_period'] = df[time_column].dt.to_period('Y')
                df['time_label'] = df[time_column].dt.strftime('%Y')
            else:
                df['time_period'] = df[time_column].dt.to_period('M')
                df['time_label'] = df[time_column].dt.strftime('%Y-%m')
            
            # Group by time period and aggregate
            grouped = df.groupby('time_label')[metric_column]
            
            if aggregation == 'sum':
                result = grouped.sum()
            elif aggregation == 'mean':
                result = grouped.mean()
            elif aggregation == 'count':
                result = grouped.count()
            elif aggregation == 'min':
                result = grouped.min()
            elif aggregation == 'max':
                result = grouped.max()
            else:
                result = grouped.sum()
            
            # Convert to list of dicts
            data = [
                {"time": str(time), "value": float(value)}
                for time, value in result.items()
            ]

            # Sort by time
            data = sorted(data, key=lambda x: x['time'])

            # Auto-detect anomalies on the aggregated values
            values_series = pd.Series([d["value"] for d in data])
            labels_series = pd.Series([d["time"]  for d in data])
            anomaly_list  = detect_trend_aware(values_series, threshold=3.0,
                                               label_series=labels_series)

            # Tag each data point with anomaly info
            anomaly_times = {a["label"]: a for a in anomaly_list}
            for point in data:
                a = anomaly_times.get(point["time"])
                point["is_anomaly"] = a is not None
                point["severity"]   = a["severity"] if a else None
                point["zscore"]     = a["zscore"]   if a else None

            return {
                "success":   True,
                "data":      data,
                "row_count": len(data),
                "anomalies": anomaly_list,
                "summary": {
                    "total":   float(result.sum()),
                    "average": float(result.mean()),
                    "min":     float(result.min()),
                    "max":     float(result.max()),
                    "periods": len(data),
                    "anomaly_count": len(anomaly_list),
                }
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Error executing trend query: {str(e)}"
            }
    
    def execute_category_comparison(
        self,
        metric_column: str,
        category_column: str,
        aggregation: str = 'sum',
        sort_order: str = 'desc',
        secondary_dimensions: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Execute category comparison query.
        secondary_dimensions: extra columns to include in grouping.
        """
        try:
            df = self.df.copy()

            extra = [c for c in (secondary_dimensions or []) if c in df.columns]
            group_cols = [category_column] + extra

            grouped = df.groupby(group_cols)[metric_column]

            if aggregation == 'sum':
                result = grouped.sum()
            elif aggregation == 'mean':
                result = grouped.mean()
            elif aggregation == 'count':
                result = grouped.count()
            elif aggregation == 'min':
                result = grouped.min()
            elif aggregation == 'max':
                result = grouped.max()
            else:
                result = grouped.sum()

            if sort_order == 'desc':
                result = result.sort_values(ascending=False)
            elif sort_order == 'asc':
                result = result.sort_values(ascending=True)

            def _label(idx):
                if isinstance(idx, tuple):
                    return " — ".join(str(v) for v in idx)
                return str(idx)

            data = [
                {"category": _label(idx), "value": float(val)}
                for idx, val in result.items()
            ]

            return {
                "success": True,
                "data": data,
                "row_count": len(data),
                "summary": {
                    "total": float(result.sum()),
                    "average": float(result.mean()),
                    "min": float(result.min()),
                    "max": float(result.max()),
                    "categories": len(data)
                }
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Error executing category comparison: {str(e)}"
            }
    
    def execute_distribution_analysis(
        self,
        column: str,
        chart_preference: str = 'auto',
        bins: int = 10
    ) -> Dict[str, Any]:
        """
        Execute distribution analysis query
        
        Args:
            column: Column to analyze
            chart_preference: Preferred chart type (auto, histogram, pie)
            bins: Number of bins for histogram
        
        Returns:
            Dictionary with query results
        """
        try:
            df = self.df.copy()
            
            # Check column type
            is_numeric = pd.api.types.is_numeric_dtype(df[column])
            
            # Determine chart type
            if chart_preference == 'auto':
                # Auto-select based on data
                unique_count = df[column].nunique()
                if is_numeric and unique_count > 20:
                    chart_type = 'histogram'
                else:
                    chart_type = 'pie'
            else:
                chart_type = chart_preference
            
            if chart_type == 'histogram' and is_numeric:
                # Histogram for numeric data
                data, bin_edges = np.histogram(df[column].dropna(), bins=bins)
                
                bin_labels = [
                    f"{bin_edges[i]:.2f} - {bin_edges[i+1]:.2f}"
                    for i in range(len(bin_edges) - 1)
                ]
                
                result = [
                    {"bin": label, "count": int(count)}
                    for label, count in zip(bin_labels, data)
                ]
                
                return {
                    "success": True,
                    "data": result,
                    "chart_type": "histogram",
                    "row_count": len(result),
                    "summary": {
                        "total_values": int(df[column].count()),
                        "mean": float(df[column].mean()),
                        "median": float(df[column].median()),
                        "std": float(df[column].std()),
                        "min": float(df[column].min()),
                        "max": float(df[column].max())
                    }
                }
            else:
                # Pie chart for categorical or low-cardinality data
                value_counts = df[column].value_counts()
                
                result = [
                    {"category": str(cat), "count": int(count)}
                    for cat, count in value_counts.items()
                ]
                
                return {
                    "success": True,
                    "data": result,
                    "chart_type": "pie",
                    "row_count": len(result),
                    "summary": {
                        "total_values": int(df[column].count()),
                        "unique_values": len(result),
                        "most_common": str(value_counts.index[0]),
                        "most_common_count": int(value_counts.iloc[0])
                    }
                }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Error executing distribution analysis: {str(e)}"
            }
    
    def execute_top_k_items(
        self,
        metric_column: str,
        dimension_column: str,
        k: int = 10,
        direction: str = 'top',
        aggregation: str = 'sum',
        secondary_dimensions: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Execute top-K items query.
        secondary_dimensions: extra columns to include in grouping
        (e.g. ['Product_Name'] → group by [dimension_column, Product_Name])
        """
        try:
            df = self.df.copy()

            # Build full group-by column list
            extra = [c for c in (secondary_dimensions or []) if c in df.columns]
            group_cols = [dimension_column] + extra

            grouped = df.groupby(group_cols)[metric_column]

            if aggregation == 'sum':
                result = grouped.sum()
            elif aggregation == 'mean':
                result = grouped.mean()
            elif aggregation == 'count':
                result = grouped.count()
            elif aggregation == 'min':
                result = grouped.min()
            elif aggregation == 'max':
                result = grouped.max()
            else:
                result = grouped.sum()

            # Sort and get top/bottom K
            if direction == 'top':
                result = result.nlargest(k)
            else:
                result = result.nsmallest(k)

            # Build item labels — compound when multiple group cols
            def _label(idx):
                if isinstance(idx, tuple):
                    return " — ".join(str(v) for v in idx)
                return str(idx)

            data = [
                {"item": _label(idx), "value": float(val)}
                for idx, val in result.items()
            ]

            return {
                "success": True,
                "data": data,
                "row_count": len(data),
                "summary": {
                    "total": float(result.sum()),
                    "average": float(result.mean()),
                    "highest": float(result.max()),
                    "lowest": float(result.min()),
                    "items_count": len(data)
                }
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Error executing top-K query: {str(e)}"
            }
    
    def execute_scatter_relationship(
        self,
        x_column: str,
        y_column: str,
        color_column: Optional[str] = None,
        size_column: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute scatter relationship query
        
        Args:
            x_column: Column for X-axis
            y_column: Column for Y-axis
            color_column: Optional column for coloring points
            size_column: Optional column for sizing points
        
        Returns:
            Dictionary with query results
        """
        try:
            df = self.df.copy()
            
            # Remove rows with missing values in key columns
            required_cols = [x_column, y_column]
            df = df.dropna(subset=required_cols)
            
            # Limit to reasonable number of points (for performance)
            if len(df) > 1000:
                df = df.sample(n=1000, random_state=42)
            
            # Build data points
            data = []
            for _, row in df.iterrows():
                point = {
                    "x": float(row[x_column]),
                    "y": float(row[y_column])
                }
                
                if color_column and color_column in df.columns:
                    point["color"] = str(row[color_column])
                
                if size_column and size_column in df.columns:
                    point["size"] = float(row[size_column])
                
                data.append(point)
            
            # Calculate correlation
            correlation = df[x_column].corr(df[y_column])
            
            return {
                "success": True,
                "data": data,
                "row_count": len(data),
                "summary": {
                    "correlation": float(correlation),
                    "x_mean": float(df[x_column].mean()),
                    "y_mean": float(df[y_column].mean()),
                    "x_std": float(df[x_column].std()),
                    "y_std": float(df[y_column].std()),
                    "points_count": len(data)
                }
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Error executing scatter query: {str(e)}"
            }
    
    def execute_correlation_analysis(
        self,
        method: str = "pearson",
        columns: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Compute a pairwise correlation matrix for numeric columns.
        Returns flat list of {x, y, value} dicts suitable for a heatmap.
        """
        try:
            df = self.df.copy()
            numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            if columns:
                numeric_cols = [c for c in columns if c in numeric_cols]
            if len(numeric_cols) < 2:
                return {"success": False, "error": "Need at least 2 numeric columns for correlation analysis"}

            corr = df[numeric_cols].corr(method=method)

            data = [
                {"x": col_x, "y": col_y, "value": round(float(corr.loc[col_x, col_y]), 3)}
                for col_x in numeric_cols
                for col_y in numeric_cols
            ]
            return {
                "success": True,
                "data": data,
                "row_count": len(data),
                "columns": numeric_cols,
                "summary": {"columns_count": len(numeric_cols), "method": method},
            }
        except Exception as e:
            return {"success": False, "error": f"Correlation analysis error: {e}"}

    def execute_grouped_aggregation(
        self,
        metric_column: str,
        primary_dimension: str,
        secondary_dimension: str,
        aggregation: str = "sum",
        top_n: int = 8,
    ) -> Dict[str, Any]:
        """
        Aggregate metric_column grouped by two dimensions simultaneously.
        Returns data suitable for a Plotly grouped-bar chart.
        """
        try:
            df = self.df.copy()
            grouped = df.groupby([primary_dimension, secondary_dimension])[metric_column]

            if aggregation == "sum":    result = grouped.sum()
            elif aggregation == "mean": result = grouped.mean()
            elif aggregation == "count":result = grouped.count()
            elif aggregation == "min":  result = grouped.min()
            elif aggregation == "max":  result = grouped.max()
            else:                       result = grouped.sum()

            result = result.reset_index()
            result.columns = ["primary", "secondary", "value"]

            if top_n and top_n > 0:
                totals = result.groupby("primary")["value"].sum().nlargest(top_n)
                result = result[result["primary"].isin(totals.index)]

            secondary_values = sorted(str(v) for v in result["secondary"].unique())
            data = [
                {"primary": str(r["primary"]), "secondary": str(r["secondary"]), "value": float(r["value"])}
                for _, r in result.iterrows()
            ]
            return {
                "success": True,
                "data": data,
                "secondary_values": secondary_values,
                "row_count": len(data),
                "summary": {
                    "total": float(result["value"].sum()),
                    "primary_count": int(result["primary"].nunique()),
                    "secondary_count": len(secondary_values),
                },
            }
        except Exception as e:
            return {"success": False, "error": f"Grouped aggregation error: {e}"}

    def execute_period_over_period(
        self,
        metric_column: str,
        time_column: str,
        aggregation: str = "sum",
        time_granularity: str = "month",
        num_periods: int = 3,
    ) -> Dict[str, Any]:
        """
        Aggregate metric_column by time period and return the last num_periods periods,
        plus period-over-period percentage changes.
        """
        try:
            df = self.df.copy()
            df[time_column] = pd.to_datetime(df[time_column], errors="coerce")
            df = df.dropna(subset=[time_column])
            if df.empty:
                return {"success": False, "error": "No valid dates in time column"}

            fmt_map = {
                "day":     "%Y-%m-%d",
                "week":    "%Y-W%U",
                "month":   "%Y-%m",
                "quarter": None,
                "year":    "%Y",
            }
            fmt = fmt_map.get(time_granularity, "%Y-%m")
            if time_granularity == "quarter":
                df["period"] = df[time_column].dt.to_period("Q").astype(str)
            else:
                df["period"] = df[time_column].dt.strftime(fmt)

            grouped = df.groupby("period")[metric_column]
            if aggregation == "sum":    agg = grouped.sum()
            elif aggregation == "mean": agg = grouped.mean()
            elif aggregation == "count":agg = grouped.count()
            elif aggregation == "min":  agg = grouped.min()
            elif aggregation == "max":  agg = grouped.max()
            else:                       agg = grouped.sum()

            agg = agg.sort_index()
            num_periods = max(2, min(int(num_periods), len(agg)))
            agg = agg.iloc[-num_periods:]

            data = [{"period": str(p), "value": float(v)} for p, v in agg.items()]

            changes = []
            for i in range(1, len(data)):
                prev, curr = data[i - 1]["value"], data[i]["value"]
                pct = round((curr - prev) / abs(prev) * 100, 2) if prev != 0 else 0.0
                changes.append({
                    "from": data[i - 1]["period"],
                    "to":   data[i]["period"],
                    "from_value": prev,
                    "to_value":   curr,
                    "pct_change": pct,
                })

            return {
                "success": True,
                "data":    data,
                "changes": changes,
                "row_count": len(data),
                "summary": {
                    "periods_compared": len(data),
                    "metric": metric_column,
                    "latest_change_pct": changes[-1]["pct_change"] if changes else 0.0,
                    "total": float(agg.sum()),
                },
            }
        except Exception as e:
            return {"success": False, "error": f"Period-over-period error: {e}"}

    def execute_query(
        self,
        template_type: str,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a query based on template type and parameters.

        An optional 'filters' key in parameters applies WHERE-style row
        filtering before the template runs:
            filters = [{"column": "Region", "value": "North"}, ...]
        This lets the NLP engine pass phrases like 'in north region' as
        pre-aggregation filters without changing any template method signature.
        """
        # Presentation-only keys are consumed downstream (chart building), not
        # by the template methods — strip them so **params stays clean.
        _NON_EXECUTOR_KEYS = {"filters", "requested_chart_type"}
        params = {k: v for k, v in parameters.items() if k not in _NON_EXECUTOR_KEYS}
        filters: List[Dict[str, str]] = parameters.get("filters") or []

        original_df = self.df
        try:
            if filters:
                df = self.df.copy()
                applied: List[str] = []
                for f in filters:
                    col, val = f.get("column"), f.get("value")
                    if col and col in df.columns:
                        mask = df[col].astype(str).str.lower() == val.lower()
                        df = df[mask]
                        applied.append(f"{col}={val}")
                if df.empty:
                    desc = ", ".join(applied) if applied else str(filters)
                    return {
                        "success": False,
                        "error": f"No data found after applying filter: {desc}",
                    }
                self.df = df

            if template_type == 'trend_over_time':
                return self.execute_trend_over_time(**params)
            elif template_type == 'category_comparison':
                return self.execute_category_comparison(**params)
            elif template_type == 'distribution_analysis':
                return self.execute_distribution_analysis(**params)
            elif template_type == 'top_k_items':
                return self.execute_top_k_items(**params)
            elif template_type == 'scatter_relationship':
                return self.execute_scatter_relationship(**params)
            elif template_type == 'correlation_analysis':
                return self.execute_correlation_analysis(**params)
            elif template_type == 'grouped_aggregation':
                return self.execute_grouped_aggregation(**params)
            elif template_type == 'period_over_period':
                return self.execute_period_over_period(**params)
            else:
                return {
                    "success": False,
                    "error": f"Unknown template type: {template_type}",
                }
        except TypeError as e:
            # Raised when required parameters are missing from the call binding
            # (e.g. metric_column omitted). Fail gracefully instead of bubbling
            # up as an opaque HTTP 500.
            return {
                "success": False,
                "error": f"Missing or invalid parameter for '{template_type}': {e}",
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Query execution failed: {e}",
            }
        finally:
            self.df = original_df
