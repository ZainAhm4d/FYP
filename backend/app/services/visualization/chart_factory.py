"""
Chart Factory
Determines the appropriate chart type and configuration based on query type and data
"""
from typing import Dict, List, Any, Optional
from enum import Enum


class ChartType(str, Enum):
    """Available chart types"""
    LINE = "line"
    BAR = "bar"
    PIE = "pie"
    HISTOGRAM = "histogram"
    SCATTER = "scatter"


class ChartFactory:
    """Factory for creating chart configurations"""
    
    @staticmethod
    def create_chart_config(
        template_type: str,
        query_result: Dict[str, Any],
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create chart configuration based on template type and query results
        
        Args:
            template_type: Type of query template
            query_result: Results from query execution
            parameters: Original query parameters
        
        Returns:
            Chart configuration dictionary
        """
        if not query_result.get('success', False):
            return {
                "error": query_result.get('error', 'Query execution failed')
            }
        
        data = query_result.get('data', [])
        summary = query_result.get('summary', {})
        
        if template_type == 'trend_over_time':
            anomalies = query_result.get('anomalies', [])
            return ChartFactory._create_line_chart_config(data, parameters, summary, anomalies)
        
        elif template_type == 'category_comparison':
            return ChartFactory._create_bar_chart_config(data, parameters, summary)
        
        elif template_type == 'distribution_analysis':
            chart_type = query_result.get('chart_type', 'histogram')
            if chart_type == 'histogram':
                return ChartFactory._create_histogram_config(data, parameters, summary)
            else:
                return ChartFactory._create_pie_chart_config(data, parameters, summary)
        
        elif template_type == 'top_k_items':
            return ChartFactory._create_horizontal_bar_config(data, parameters, summary)
        
        elif template_type == 'scatter_relationship':
            return ChartFactory._create_scatter_config(data, parameters, summary)

        elif template_type == 'correlation_analysis':
            return ChartFactory._create_heatmap_config(data, parameters, summary, query_result)

        elif template_type == 'grouped_aggregation':
            return ChartFactory._create_grouped_bar_config(data, parameters, summary, query_result)

        elif template_type == 'period_over_period':
            return ChartFactory._create_period_comparison_config(data, parameters, summary)

        else:
            return {"error": f"Unknown template type: {template_type}"}
    
    @staticmethod
    def _create_line_chart_config(
        data: List[Dict],
        parameters: Dict,
        summary: Dict,
        anomalies: List[Dict] = None,
    ) -> Dict[str, Any]:
        """Create line chart configuration"""
        metric_col = parameters.get('metric_column', 'Metric')
        aggregation = parameters.get('aggregation', 'sum')

        return {
            "chart_type": "line",
            "data": data,
            "anomalies": anomalies or [],
            "config": {
                "x_field": "time",
                "y_field": "value",
                "x_label": "Time Period",
                "y_label": f"{metric_col} ({aggregation})",
                "title": f"{metric_col} Trend Over Time",
                "color": "#3B82F6",
                "mode": "lines+markers"
            },
            "summary": summary
        }
    
    @staticmethod
    def _create_bar_chart_config(
        data: List[Dict],
        parameters: Dict,
        summary: Dict
    ) -> Dict[str, Any]:
        """Create bar chart configuration"""
        metric_col = parameters.get('metric_column', 'Metric')
        category_col = parameters.get('category_column', 'Category')
        aggregation = parameters.get('aggregation', 'sum')
        
        return {
            "chart_type": "bar",
            "data": data,
            "config": {
                "x_field": "category",
                "y_field": "value",
                "x_label": category_col,
                "y_label": f"{metric_col} ({aggregation})",
                "title": f"{metric_col} by {category_col}",
                "color": "#4F46E5",
                "orientation": "vertical"
            },
            "summary": summary
        }
    
    @staticmethod
    def _create_histogram_config(
        data: List[Dict],
        parameters: Dict,
        summary: Dict
    ) -> Dict[str, Any]:
        """Create histogram configuration"""
        column = parameters.get('column', 'Column')
        
        return {
            "chart_type": "histogram",
            "data": data,
            "config": {
                "x_field": "bin",
                "y_field": "count",
                "x_label": column,
                "y_label": "Frequency",
                "title": f"Distribution of {column}",
                "color": "#10B981"
            },
            "summary": summary
        }
    
    @staticmethod
    def _create_pie_chart_config(
        data: List[Dict],
        parameters: Dict,
        summary: Dict
    ) -> Dict[str, Any]:
        """Create pie chart configuration"""
        column = parameters.get('column', 'Column')
        
        return {
            "chart_type": "pie",
            "data": data,
            "config": {
                "labels_field": "category",
                "values_field": "count",
                "title": f"Distribution of {column}",
                "colors": [
                    "#4F46E5", "#0D9488", "#10B981", "#F59E0B",
                    "#EF4444", "#6366F1", "#EC4899", "#14B8A6"
                ]
            },
            "summary": summary
        }
    
    @staticmethod
    def _create_horizontal_bar_config(
        data: List[Dict],
        parameters: Dict,
        summary: Dict
    ) -> Dict[str, Any]:
        """Create horizontal bar chart configuration for top-K"""
        metric_col  = parameters.get('metric_column', 'Metric')
        dim_col     = parameters.get('dimension_column', 'Item')
        sec_dims    = parameters.get('secondary_dimensions') or []
        k           = parameters.get('k', 10)
        direction   = parameters.get('direction', 'top')
        aggregation = parameters.get('aggregation', 'sum')

        # Compound y-axis label when grouping by multiple columns
        all_dims  = [dim_col] + sec_dims
        y_label   = " & ".join(all_dims)
        direction_word = "Top" if direction == "top" else "Bottom"
        title = f"{direction_word} {k} {y_label} by {metric_col}"

        return {
            "chart_type": "bar",
            "data": data,
            "config": {
                "x_field": "value",
                "y_field": "item",
                "x_label": f"{metric_col} ({aggregation})",
                "y_label": y_label,
                "title": title,
                "color": "#F59E0B",
                "orientation": "horizontal"
            },
            "summary": summary
        }
    
    @staticmethod
    def _create_heatmap_config(
        data: List[Dict],
        parameters: Dict,
        summary: Dict,
        query_result: Dict,
    ) -> Dict[str, Any]:
        method = parameters.get("method", "pearson")
        columns = query_result.get("columns", [])
        return {
            "chart_type": "heatmap",
            "data": data,
            "config": {
                "title":   f"Correlation Matrix ({method.title()})",
                "columns": columns,
                "method":  method,
            },
            "summary": summary,
        }

    @staticmethod
    def _create_grouped_bar_config(
        data: List[Dict],
        parameters: Dict,
        summary: Dict,
        query_result: Dict,
    ) -> Dict[str, Any]:
        metric_col    = parameters.get("metric_column", "Metric")
        primary_dim   = parameters.get("primary_dimension", "Primary")
        secondary_dim = parameters.get("secondary_dimension", "Secondary")
        aggregation   = parameters.get("aggregation", "sum")
        secondary_values = query_result.get("secondary_values", [])
        return {
            "chart_type": "grouped_bar",
            "data": data,
            "config": {
                "title":            f"{metric_col} by {primary_dim} & {secondary_dim}",
                "x_label":          primary_dim,
                "y_label":          f"{metric_col} ({aggregation})",
                "secondary_values": secondary_values,
                "secondary_label":  secondary_dim,
            },
            "summary": summary,
        }

    @staticmethod
    def _create_period_comparison_config(
        data: List[Dict],
        parameters: Dict,
        summary: Dict,
    ) -> Dict[str, Any]:
        metric_col   = parameters.get("metric_column", "Metric")
        aggregation  = parameters.get("aggregation", "sum")
        granularity  = parameters.get("time_granularity", "month")
        return {
            "chart_type": "period_comparison",
            "data": data,
            "config": {
                "title":       f"{metric_col} — Period-over-Period ({granularity.title()})",
                "x_label":     "Period",
                "y_label":     f"{metric_col} ({aggregation})",
                "metric_col":  metric_col,
            },
            "summary": summary,
        }

    @staticmethod
    def _create_scatter_config(
        data: List[Dict],
        parameters: Dict,
        summary: Dict
    ) -> Dict[str, Any]:
        """Create scatter plot configuration"""
        x_col = parameters.get('x_column', 'X')
        y_col = parameters.get('y_column', 'Y')
        color_col = parameters.get('color_column')
        
        correlation = summary.get('correlation', 0)
        correlation_text = f"Correlation: {correlation:.3f}"
        
        config = {
            "chart_type": "scatter",
            "data": data,
            "config": {
                "x_field": "x",
                "y_field": "y",
                "x_label": x_col,
                "y_label": y_col,
                "title": f"{y_col} vs {x_col}",
                "subtitle": correlation_text,
                "mode": "markers",
                "marker_size": 8
            },
            "summary": summary
        }
        
        if color_col:
            config["config"]["color_field"] = "color"
            config["config"]["color_label"] = color_col
        
        return config
