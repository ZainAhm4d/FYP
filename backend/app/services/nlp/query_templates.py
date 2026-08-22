"""
Query Template System
Defines predefined analytical query templates for business intelligence
"""
from typing import Dict, List, Optional, Any
from enum import Enum
from pydantic import BaseModel


class QueryTemplateType(str, Enum):
    """Available query template types"""
    TREND_OVER_TIME = "trend_over_time"
    CATEGORY_COMPARISON = "category_comparison"
    DISTRIBUTION_ANALYSIS = "distribution_analysis"
    TOP_K_ITEMS = "top_k_items"
    SCATTER_RELATIONSHIP = "scatter_relationship"
    CORRELATION_ANALYSIS = "correlation_analysis"
    GROUPED_AGGREGATION = "grouped_aggregation"
    PERIOD_OVER_PERIOD = "period_over_period"


class QueryParameter(BaseModel):
    """Query parameter definition"""
    name: str
    type: str  # 'metric', 'dimension', 'date', 'number'
    required: bool
    description: str
    default: Optional[Any] = None


class QueryTemplate(BaseModel):
    """Query template definition"""
    template_type: QueryTemplateType
    name: str
    description: str
    chart_type: str  # 'line', 'bar', 'pie', 'histogram', 'scatter'
    parameters: List[QueryParameter]
    aggregation: Optional[str] = None  # 'sum', 'mean', 'count', 'min', 'max'
    
    
class QueryTemplateRegistry:
    """Registry of all available query templates"""
    
    _templates: Dict[QueryTemplateType, QueryTemplate] = {}
    
    @classmethod
    def register_template(cls, template: QueryTemplate):
        """Register a query template"""
        cls._templates[template.template_type] = template
    
    @classmethod
    def get_template(cls, template_type: QueryTemplateType) -> Optional[QueryTemplate]:
        """Get template by type"""
        return cls._templates.get(template_type)
    
    @classmethod
    def get_all_templates(cls) -> List[QueryTemplate]:
        """Get all registered templates"""
        return list(cls._templates.values())
    
    @classmethod
    def get_template_info(cls) -> List[Dict[str, Any]]:
        """Get simplified template information for frontend"""
        return [
            {
                "template_type": t.template_type,
                "name": t.name,
                "description": t.description,
                "chart_type": t.chart_type,
                "parameters": [
                    {
                        "name": p.name,
                        "type": p.type,
                        "required": p.required,
                        "description": p.description,
                        "default": p.default
                    }
                    for p in t.parameters
                ]
            }
            for t in cls._templates.values()
        ]


# Template 1: Trend Over Time
trend_over_time = QueryTemplate(
    template_type=QueryTemplateType.TREND_OVER_TIME,
    name="Trend Over Time",
    description="Analyze how a metric changes over time. Perfect for tracking sales, revenue, or any time-series data.",
    chart_type="line",
    parameters=[
        QueryParameter(
            name="metric_column",
            type="metric",
            required=True,
            description="The numeric column to track (e.g., sales, revenue, quantity)"
        ),
        QueryParameter(
            name="time_column",
            type="date",
            required=True,
            description="The date/time column for X-axis"
        ),
        QueryParameter(
            name="aggregation",
            type="aggregation",
            required=False,
            description="How to aggregate the metric (sum, mean, count, min, max)",
            default="sum"
        ),
        QueryParameter(
            name="time_granularity",
            type="granularity",
            required=False,
            description="Time grouping (day, week, month, quarter, year)",
            default="month"
        )
    ],
    aggregation="sum"
)

# Template 2: Category Comparison
category_comparison = QueryTemplate(
    template_type=QueryTemplateType.CATEGORY_COMPARISON,
    name="Category Comparison",
    description="Compare a metric across different categories. Great for product categories, departments, or regions.",
    chart_type="bar",
    parameters=[
        QueryParameter(
            name="metric_column",
            type="metric",
            required=True,
            description="The numeric column to compare (e.g., sales, revenue)"
        ),
        QueryParameter(
            name="category_column",
            type="dimension",
            required=True,
            description="The categorical column to group by (e.g., product, region)"
        ),
        QueryParameter(
            name="aggregation",
            type="aggregation",
            required=False,
            description="How to aggregate the metric (sum, mean, count, min, max)",
            default="sum"
        ),
        QueryParameter(
            name="sort_order",
            type="sort",
            required=False,
            description="Sort results (asc, desc, none)",
            default="desc"
        )
    ],
    aggregation="sum"
)

# Template 3: Distribution Analysis
distribution_analysis = QueryTemplate(
    template_type=QueryTemplateType.DISTRIBUTION_ANALYSIS,
    name="Distribution Analysis",
    description="Show the distribution or breakdown of values. Use histogram for numeric data, pie for categories.",
    chart_type="histogram",  # Can be pie or histogram depending on data type
    parameters=[
        QueryParameter(
            name="column",
            type="column",
            required=True,
            description="The column to analyze distribution"
        ),
        QueryParameter(
            name="chart_preference",
            type="chart_type",
            required=False,
            description="Preferred chart type (auto, histogram, pie)",
            default="auto"
        ),
        QueryParameter(
            name="bins",
            type="number",
            required=False,
            description="Number of bins for histogram (numeric data only)",
            default=10
        )
    ],
    aggregation="count"
)

# Template 4: Top-K Items
top_k_items = QueryTemplate(
    template_type=QueryTemplateType.TOP_K_ITEMS,
    name="Top-K Items",
    description="Find the top or bottom N items by a metric. Perfect for best sellers, top performers, etc.",
    chart_type="bar",
    parameters=[
        QueryParameter(
            name="metric_column",
            type="metric",
            required=True,
            description="The numeric column to rank by (e.g., sales, revenue)"
        ),
        QueryParameter(
            name="dimension_column",
            type="dimension",
            required=True,
            description="The column to identify items (e.g., product, employee)"
        ),
        QueryParameter(
            name="k",
            type="number",
            required=False,
            description="Number of top items to show",
            default=10
        ),
        QueryParameter(
            name="direction",
            type="direction",
            required=False,
            description="Show top or bottom items (top, bottom)",
            default="top"
        ),
        QueryParameter(
            name="aggregation",
            type="aggregation",
            required=False,
            description="How to aggregate the metric (sum, mean, count, min, max)",
            default="sum"
        )
    ],
    aggregation="sum"
)

# Template 5: Scatter Relationship
scatter_relationship = QueryTemplate(
    template_type=QueryTemplateType.SCATTER_RELATIONSHIP,
    name="Scatter Relationship",
    description="Explore the relationship between two numeric variables. Useful for correlation analysis.",
    chart_type="scatter",
    parameters=[
        QueryParameter(
            name="x_column",
            type="metric",
            required=True,
            description="The numeric column for X-axis"
        ),
        QueryParameter(
            name="y_column",
            type="metric",
            required=True,
            description="The numeric column for Y-axis"
        ),
        QueryParameter(
            name="color_column",
            type="dimension",
            required=False,
            description="Optional: Column to color points by category"
        ),
        QueryParameter(
            name="size_column",
            type="metric",
            required=False,
            description="Optional: Column to size points by value"
        )
    ],
    aggregation=None
)


# Template 6: Correlation Analysis
correlation_analysis = QueryTemplate(
    template_type=QueryTemplateType.CORRELATION_ANALYSIS,
    name="Correlation Analysis",
    description="Show a heatmap of correlations between numeric columns. Identify which metrics move together.",
    chart_type="heatmap",
    parameters=[
        QueryParameter(
            name="method",
            type="string",
            required=False,
            description="Correlation method (pearson, spearman)",
            default="pearson",
        ),
    ],
    aggregation=None,
)

# Template 7: Aggregation by Group
grouped_aggregation = QueryTemplate(
    template_type=QueryTemplateType.GROUPED_AGGREGATION,
    name="Aggregation by Group",
    description="Aggregate a metric across two dimensions simultaneously — e.g., sales by region AND product category.",
    chart_type="bar",
    parameters=[
        QueryParameter(
            name="metric_column",
            type="metric",
            required=True,
            description="Numeric column to aggregate (e.g., sales, revenue)",
        ),
        QueryParameter(
            name="primary_dimension",
            type="dimension",
            required=True,
            description="Primary grouping column (X-axis groups)",
        ),
        QueryParameter(
            name="secondary_dimension",
            type="dimension",
            required=True,
            description="Secondary grouping column (creates sub-bars within each group)",
        ),
        QueryParameter(
            name="aggregation",
            type="aggregation",
            required=False,
            description="Aggregation method (sum, mean, count)",
            default="sum",
        ),
        QueryParameter(
            name="top_n",
            type="number",
            required=False,
            description="Limit to top N primary dimension values by total (0 = all)",
            default=8,
        ),
    ],
    aggregation="sum",
)

# Template 8: Period-over-Period Comparison
period_over_period = QueryTemplate(
    template_type=QueryTemplateType.PERIOD_OVER_PERIOD,
    name="Period-over-Period Comparison",
    description="Compare a metric between the current period and previous periods — e.g., this month vs last month.",
    chart_type="bar",
    parameters=[
        QueryParameter(
            name="metric_column",
            type="metric",
            required=True,
            description="Numeric column to compare (e.g., revenue, orders)",
        ),
        QueryParameter(
            name="time_column",
            type="date",
            required=True,
            description="Date/time column",
        ),
        QueryParameter(
            name="aggregation",
            type="aggregation",
            required=False,
            description="Aggregation method (sum, mean, count)",
            default="sum",
        ),
        QueryParameter(
            name="time_granularity",
            type="granularity",
            required=False,
            description="Time period size (month, quarter, year)",
            default="month",
        ),
        QueryParameter(
            name="num_periods",
            type="number",
            required=False,
            description="Number of consecutive periods to compare (2–6)",
            default=3,
        ),
    ],
    aggregation="sum",
)


# Register all templates
QueryTemplateRegistry.register_template(trend_over_time)
QueryTemplateRegistry.register_template(category_comparison)
QueryTemplateRegistry.register_template(distribution_analysis)
QueryTemplateRegistry.register_template(top_k_items)
QueryTemplateRegistry.register_template(scatter_relationship)
QueryTemplateRegistry.register_template(correlation_analysis)
QueryTemplateRegistry.register_template(grouped_aggregation)
QueryTemplateRegistry.register_template(period_over_period)


def get_template_by_type(template_type: str) -> Optional[QueryTemplate]:
    """Get template by type string"""
    try:
        template_enum = QueryTemplateType(template_type)
        return QueryTemplateRegistry.get_template(template_enum)
    except ValueError:
        return None


def list_all_templates() -> List[Dict[str, Any]]:
    """List all templates with their information"""
    return QueryTemplateRegistry.get_template_info()
