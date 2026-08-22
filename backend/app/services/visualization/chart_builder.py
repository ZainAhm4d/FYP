"""
Chart Builder
Generates Plotly chart specifications from chart configurations
"""
from typing import Dict, List, Any, Optional
import json



class ChartBuilder:
    """Build Plotly chart specifications"""
    
    # Default color palette
    DEFAULT_COLORS = [
        '#4F46E5', '#0D9488', '#10B981', '#F59E0B',
        '#EF4444', '#6366F1', '#EC4899', '#14B8A6',
        '#F97316', '#84CC16', '#06B6D4', '#A855F7'
    ]
    
    @staticmethod
    def build_chart(chart_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build Plotly chart specification from configuration
        
        Args:
            chart_config: Chart configuration from ChartFactory
        
        Returns:
            Plotly chart specification (JSON-serializable dict)
        """
        if "error" in chart_config:
            return {"error": chart_config["error"]}
        
        chart_type = chart_config.get("chart_type")
        data = chart_config.get("data", [])
        config = chart_config.get("config", {})

        if chart_type == "line":
            anomalies = chart_config.get("anomalies", [])
            spec = ChartBuilder._build_line_chart(data, config, anomalies)
        elif chart_type == "bar":
            spec = ChartBuilder._build_bar_chart(data, config)
        elif chart_type == "pie":
            spec = ChartBuilder._build_pie_chart(data, config)
        elif chart_type == "histogram":
            spec = ChartBuilder._build_histogram(data, config)
        elif chart_type == "scatter":
            spec = ChartBuilder._build_scatter_chart(data, config)
        elif chart_type == "heatmap":
            spec = ChartBuilder._build_heatmap(data, config)
        elif chart_type == "grouped_bar":
            spec = ChartBuilder._build_grouped_bar(data, config)
        elif chart_type == "period_comparison":
            spec = ChartBuilder._build_period_comparison(data, config)
        else:
            return {"error": f"Unsupported chart type: {chart_type}"}

        return ChartBuilder._polish_spec(spec)

    # ── CH-05: one shared formatting pass for financial trust ──────────────
    # Axis ticks, on-bar labels and hover values must always agree: ticks and
    # labels share the same SI abbreviation; hover shows the exact full number.

    @staticmethod
    def _axis_is_numeric(traces: List[Dict], key: str) -> bool:
        for tr in traces:
            vals = tr.get(key)
            if isinstance(vals, list) and vals:
                sample = [v for v in vals[:20] if v is not None]
                return bool(sample) and all(
                    isinstance(v, (int, float)) and not isinstance(v, bool)
                    for v in sample
                )
        return False

    @staticmethod
    def _polish_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(spec, dict) or "error" in spec or not spec.get("data"):
            return spec
        traces = spec["data"]
        layout = spec.setdefault("layout", {})

        has_xy = any(tr.get("x") is not None and tr.get("y") is not None for tr in traces)
        if not has_xy:
            return spec   # pie / other label-value charts need no axis work

        x_num = ChartBuilder._axis_is_numeric(traces, "x")
        y_num = ChartBuilder._axis_is_numeric(traces, "y")

        for axis_key, numeric in (("xaxis", x_num), ("yaxis", y_num)):
            ax = layout.setdefault(axis_key, {})
            ax.setdefault("automargin", True)
            if numeric:
                # '~s' = SI abbreviation (1.2M) — identical to on-bar labels
                ax.setdefault("tickformat", "~s")
                ax.setdefault("separatethousands", True)

        for tr in traces:
            horizontal = tr.get("orientation") == "h"
            val_key = "x" if horizontal else "y"
            val_num = x_num if horizontal else y_num
            if not val_num:
                continue
            # Hover: the exact, thousands-separated number (trust anchor)
            ht = tr.get("hovertemplate")
            if isinstance(ht, str) and f"%{{{val_key}}}" in ht:
                tr["hovertemplate"] = ht.replace(f"%{{{val_key}}}", f"%{{{val_key}:,.2f}}")
            elif ht is None and tr.get("type") in ("bar", "scatter"):
                cat_key = "y" if horizontal else "x"
                tr["hovertemplate"] = (
                    f"%{{{cat_key}}}: %{{{val_key}:,.2f}}<extra></extra>"
                )
            # On-bar value labels using the same abbreviation as the ticks
            if tr.get("type") == "bar" and "texttemplate" not in tr:
                tr["texttemplate"] = f"%{{{val_key}:.3s}}"
                tr["textposition"] = "outside"
                tr["cliponaxis"] = False

        # Unified hover reads all series at a glance on vertical xy charts
        if not any(tr.get("orientation") == "h" for tr in traces):
            layout.setdefault("hovermode", "x unified")
        return spec
    
    @staticmethod
    def _build_line_chart(
        data: List[Dict],
        config: Dict,
        anomalies: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """Build line chart specification with optional anomaly markers."""
        x_field = config.get('x_field', 'x')
        y_field = config.get('y_field', 'y')

        x_values = [item[x_field] for item in data]
        y_values = [item[y_field] for item in data]

        # Main line trace
        main_trace = {
            "type": "scatter",
            "mode": config.get("mode", "lines+markers"),
            "x": x_values,
            "y": y_values,
            "name": config.get("y_label", "Value"),
            "line":   {"color": config.get("color", "#4F46E5"), "width": 3},
            "marker": {"size": 6, "color": config.get("color", "#4F46E5")},
        }

        traces = [main_trace]
        annotations = []

        # Anomaly overlay traces (one per severity level)
        _SEVERITY_CFG = {
            "high":   {"color": "#EF4444", "size": 14, "symbol": "circle"},
            "medium": {"color": "#F97316", "size": 11, "symbol": "circle"},
            "low":    {"color": "#EAB308", "size": 9,  "symbol": "circle"},
        }
        if anomalies:
            by_severity: Dict[str, List] = {"high": [], "medium": [], "low": []}
            for a in anomalies:
                sev = a.get("severity", "low")
                by_severity.setdefault(sev, []).append(a)

            for sev, cfg in _SEVERITY_CFG.items():
                pts = by_severity.get(sev, [])
                if not pts:
                    continue
                traces.append({
                    "type": "scatter",
                    "mode": "markers",
                    "x":    [p["label"] for p in pts],
                    "y":    [p["value"] for p in pts],
                    "name": f"{sev.title()} Anomaly",
                    "marker": {
                        "color":  cfg["color"],
                        "size":   cfg["size"],
                        "symbol": cfg["symbol"],
                        "line":   {"color": "white", "width": 2},
                    },
                    "hovertemplate": (
                        f"<b>⚠ {sev.title()} Anomaly</b><br>"
                        "%{x}<br>Value: %{y}<extra></extra>"
                    ),
                })

            # Warning annotations for high severity
            for a in by_severity.get("high", []):
                annotations.append({
                    "x":          a["label"],
                    "y":          a["value"],
                    "text":       "⚠",
                    "showarrow":  False,
                    "yshift":     18,
                    "font":       {"color": "#EF4444", "size": 14},
                })

        layout = {
            "title": {
                "text": config.get("title", "Line Chart"),
                "font": {"size": 20, "family": "Arial, sans-serif"},
            },
            "xaxis": {
                "title":     {"text": config.get("x_label", "X Axis"), "font": {"size": 13, "color": "#374151"}, "standoff": 20},
                "tickfont":  {"size": 11, "color": "#374151"},
                "showgrid":  True,
                "gridcolor": "#E5E7EB",
                "automargin": True,
            },
            "yaxis": {
                "title":     {"text": config.get("y_label", "Y Axis"), "font": {"size": 13, "color": "#374151"}, "standoff": 15},
                "tickfont":  {"size": 11, "color": "#374151"},
                "showgrid":  True,
                "gridcolor": "#E5E7EB",
                "automargin": True,
            },
            "plot_bgcolor":  "#FFFFFF",
            "paper_bgcolor": "#FFFFFF",
            "hovermode":     "x unified",
            "margin":        {"l": 80, "r": 40, "t": 50, "b": 110},
            "showlegend":    bool(anomalies),
        }

        if annotations:
            layout["annotations"] = annotations

        return {"data": traces, "layout": layout}
    
    @staticmethod
    def _build_bar_chart(data: List[Dict], config: Dict) -> Dict[str, Any]:
        """Build bar chart specification"""
        orientation = config.get('orientation', 'vertical')
        
        if orientation == 'horizontal':
            x_field = config.get('x_field', 'x')
            y_field = config.get('y_field', 'y')
            x_values = [item[x_field] for item in data]
            y_values = [item[y_field] for item in data]
            
            trace = {
                "type": "bar",
                "orientation": "h",
                "x": x_values,
                "y": y_values,
                "marker": {
                    "color": config.get("color", "#4F46E5"),
                    "line": {"width": 0}
                },
                "hovertemplate": "%{y}: %{x}<extra></extra>"
            }
            
            layout = {
                "title": {
                    "text": config.get("title", "Bar Chart"),
                    "font": {"size": 20, "family": "Arial, sans-serif"}
                },
                "xaxis": {
                    "title": {"text": config.get("x_label", "Value"), "font": {"size": 13, "color": "#374151"}, "standoff": 12},
                    "tickfont": {"size": 11, "color": "#374151"},
                    "showgrid": True,
                    "gridcolor": "#E5E7EB",
                    "automargin": True
                },
                "yaxis": {
                    "title": {"text": config.get("y_label", "Category"), "font": {"size": 13, "color": "#374151"}, "standoff": 12},
                    "tickfont": {"size": 11, "color": "#374151"},
                    "automargin": True
                },
                "plot_bgcolor": "#FFFFFF",
                "paper_bgcolor": "#FFFFFF",
                "margin": {"l": 180, "r": 40, "t": 80, "b": 80}
            }
        else:
            x_field = config.get('x_field', 'x')
            y_field = config.get('y_field', 'y')
            x_values = [item[x_field] for item in data]
            y_values = [item[y_field] for item in data]
            
            trace = {
                "type": "bar",
                "x": x_values,
                "y": y_values,
                "marker": {
                    "color": config.get("color", "#4F46E5"),
                    "line": {"width": 0}
                },
                "hovertemplate": "%{x}: %{y}<extra></extra>"
            }
            
            layout = {
                "title": {
                    "text": config.get("title", "Bar Chart"),
                    "font": {"size": 20, "family": "Arial, sans-serif"}
                },
                "xaxis": {
                    "title": {"text": config.get("x_label", "Category"), "font": {"size": 13, "color": "#374151"}, "standoff": 20},
                    "tickfont": {"size": 11, "color": "#374151"},
                    "tickangle": -35,
                    "automargin": True
                },
                "yaxis": {
                    "title": {"text": config.get("y_label", "Value"), "font": {"size": 13, "color": "#374151"}, "standoff": 15},
                    "tickfont": {"size": 11, "color": "#374151"},
                    "showgrid": True,
                    "gridcolor": "#E5E7EB",
                    "automargin": True
                },
                "plot_bgcolor": "#FFFFFF",
                "paper_bgcolor": "#FFFFFF",
                "margin": {"l": 80, "r": 40, "t": 50, "b": 150}
            }
        
        return {
            "data": [trace],
            "layout": layout
        }
    
    @staticmethod
    def _build_pie_chart(data: List[Dict], config: Dict) -> Dict[str, Any]:
        """Build pie chart specification"""
        labels_field = config.get('labels_field', 'label')
        values_field = config.get('values_field', 'value')
        
        labels = [item[labels_field] for item in data]
        values = [item[values_field] for item in data]
        
        colors = config.get('colors', ChartBuilder.DEFAULT_COLORS)
        
        trace = {
            "type": "pie",
            "labels": labels,
            "values": values,
            "marker": {
                "colors": colors[:len(data)],
                "line": {"color": "#FFFFFF", "width": 2}
            },
            "textposition": "inside",
            "textinfo": "label+percent",
            "hoverinfo": "label+value+percent",
            "hole": 0  # Set to 0.4 for donut chart
        }
        
        layout = {
            "title": {
                "text": config.get("title", "Pie Chart"),
                "font": {"size": 20, "family": "Arial, sans-serif"}
            },
            "paper_bgcolor": "#FFFFFF",
            "showlegend": True,
            "legend": {
                "orientation": "v",
                "x": 1.05,
                "y": 0.5
            },
            "margin": {"l": 20, "r": 200, "t": 80, "b": 20}
        }
        
        return {
            "data": [trace],
            "layout": layout
        }
    
    @staticmethod
    def _build_histogram(data: List[Dict], config: Dict) -> Dict[str, Any]:
        """Build histogram specification"""
        x_field = config.get('x_field', 'x')
        y_field = config.get('y_field', 'y')
        
        x_values = [item[x_field] for item in data]
        y_values = [item[y_field] for item in data]
        
        trace = {
            "type": "bar",
            "x": x_values,
            "y": y_values,
            "marker": {
                "color": config.get("color", "#10B981"),
                "line": {"width": 0}
            },
            "hovertemplate": "%{x}: %{y} items<extra></extra>"
        }
        
        layout = {
            "title": {
                "text": config.get("title", "Histogram"),
                "font": {"size": 20, "family": "Arial, sans-serif"}
            },
            "xaxis": {
                "title": {"text": config.get("x_label", "Bins"), "font": {"size": 13, "color": "#374151"}, "standoff": 20},
                "tickfont": {"size": 11, "color": "#374151"},
                "tickangle": -35,
                "showgrid": False,
                "automargin": True
            },
            "yaxis": {
                "title": {"text": config.get("y_label", "Frequency"), "font": {"size": 13, "color": "#374151"}, "standoff": 15},
                "tickfont": {"size": 11, "color": "#374151"},
                "showgrid": True,
                "gridcolor": "#E5E7EB",
                "automargin": True
            },
            "plot_bgcolor": "#FFFFFF",
            "paper_bgcolor": "#FFFFFF",
            "bargap": 0.05,
            "margin": {"l": 80, "r": 40, "t": 50, "b": 150}
        }
        
        return {
            "data": [trace],
            "layout": layout
        }
    
    @staticmethod
    def _build_scatter_chart(data: List[Dict], config: Dict) -> Dict[str, Any]:
        """Build scatter plot specification"""
        x_field = config.get('x_field', 'x')
        y_field = config.get('y_field', 'y')
        color_field = config.get('color_field')
        
        if color_field:
            # Group by color field
            color_groups = {}
            for item in data:
                color_val = item.get(color_field, 'Unknown')
                if color_val not in color_groups:
                    color_groups[color_val] = {'x': [], 'y': []}
                color_groups[color_val]['x'].append(item[x_field])
                color_groups[color_val]['y'].append(item[y_field])
            
            # Create trace for each group
            traces = []
            for idx, (group_name, group_data) in enumerate(color_groups.items()):
                trace = {
                    "type": "scatter",
                    "mode": "markers",
                    "x": group_data['x'],
                    "y": group_data['y'],
                    "name": str(group_name),
                    "marker": {
                        "size": config.get("marker_size", 8),
                        "color": ChartBuilder.DEFAULT_COLORS[idx % len(ChartBuilder.DEFAULT_COLORS)],
                        "opacity": 0.7
                    },
                    "hovertemplate": f"<b>{group_name}</b><br>X: %{{x}}<br>Y: %{{y}}<extra></extra>"
                }
                traces.append(trace)
        else:
            # Single trace
            x_values = [item[x_field] for item in data]
            y_values = [item[y_field] for item in data]
            
            traces = [{
                "type": "scatter",
                "mode": "markers",
                "x": x_values,
                "y": y_values,
                "marker": {
                    "size": config.get("marker_size", 8),
                    "color": "#3B82F6",
                    "opacity": 0.7
                },
                "hovertemplate": "X: %{x}<br>Y: %{y}<extra></extra>"
            }]
        
        title_text = config.get("title", "Scatter Plot")
        if config.get("subtitle"):
            title_text += f"<br><sub>{config['subtitle']}</sub>"
        
        layout = {
            "title": {
                "text": title_text,
                "font": {"size": 20, "family": "Arial, sans-serif"}
            },
            "xaxis": {
                "title": {"text": config.get("x_label", "X Axis"), "font": {"size": 13, "color": "#374151"}, "standoff": 20},
                "tickfont": {"size": 11, "color": "#374151"},
                "showgrid": True,
                "gridcolor": "#E5E7EB",
                "automargin": True
            },
            "yaxis": {
                "title": {"text": config.get("y_label", "Y Axis"), "font": {"size": 13, "color": "#374151"}, "standoff": 15},
                "tickfont": {"size": 11, "color": "#374151"},
                "showgrid": True,
                "gridcolor": "#E5E7EB",
                "automargin": True
            },
            "plot_bgcolor": "#FFFFFF",
            "paper_bgcolor": "#FFFFFF",
            "hovermode": "closest",
            "margin": {"l": 80, "r": 40, "t": 50, "b": 110}
        }
        
        if color_field:
            layout["showlegend"] = True
            layout["legend"] = {
                "title": {"text": config.get("color_label", "Category")},
                "orientation": "v",
                "x": 1.05,
                "y": 1
            }
            layout["margin"]["r"] = 150
        
        return {
            "data": traces,
            "layout": layout
        }
    
    @staticmethod
    def _build_heatmap(data: List[Dict], config: Dict) -> Dict[str, Any]:
        """Build Plotly heatmap for a correlation matrix."""
        cols = config.get("columns", [])
        if not cols:
            cols = list(dict.fromkeys(d["x"] for d in data))

        col_idx = {c: i for i, c in enumerate(cols)}
        n = len(cols)
        z = [[None] * n for _ in range(n)]
        for d in data:
            i = col_idx.get(d.get("x"))
            j = col_idx.get(d.get("y"))
            if i is not None and j is not None:
                z[j][i] = d.get("value")

        text = [[f"{v:.2f}" if v is not None else "" for v in row] for row in z]

        trace = {
            "type": "heatmap",
            "x":    cols,
            "y":    cols,
            "z":    z,
            "colorscale":     "RdBu",
            "zmid":           0,
            "reversescale":   True,
            "text":           text,
            "texttemplate":   "%{text}",
            "showscale":      True,
            "hovertemplate":  "<b>%{y} vs %{x}</b><br>Correlation: %{z:.3f}<extra></extra>",
        }

        layout = {
            "title": {"text": config.get("title", "Correlation Matrix"), "font": {"size": 20}},
            "xaxis": {
                "tickfont": {"size": 11}, "tickangle": -35,
                "automargin": True, "side": "bottom",
            },
            "yaxis": {"tickfont": {"size": 11}, "automargin": True},
            "paper_bgcolor": "#FFFFFF",
            "plot_bgcolor":  "#FFFFFF",
            "margin": {"l": 140, "r": 60, "t": 80, "b": 140},
        }
        return {"data": [trace], "layout": layout}

    @staticmethod
    def _build_grouped_bar(data: List[Dict], config: Dict) -> Dict[str, Any]:
        """Build a grouped bar chart for aggregation-by-two-dimensions data."""
        secondary_values = config.get("secondary_values") or sorted(
            {d.get("secondary", "") for d in data}
        )
        # Ordered list of primary values (preserving first-seen order)
        seen: dict = {}
        for d in data:
            p = d.get("primary", "")
            if p not in seen:
                seen[p] = True
        primary_values = list(seen)

        colors = ChartBuilder.DEFAULT_COLORS
        traces = []
        for idx, sec in enumerate(secondary_values):
            sec_data = {d["primary"]: d["value"] for d in data if d.get("secondary") == sec}
            traces.append({
                "type":   "bar",
                "name":   str(sec),
                "x":      primary_values,
                "y":      [sec_data.get(p, 0) for p in primary_values],
                "marker": {"color": colors[idx % len(colors)]},
                "hovertemplate": f"<b>{sec}</b><br>%{{x}}: %{{y}}<extra></extra>",
            })

        layout = {
            "title":   {"text": config.get("title", "Grouped Aggregation"), "font": {"size": 20}},
            "barmode": "group",
            "xaxis": {
                "title":     {"text": config.get("x_label", "Category"), "font": {"size": 13, "color": "#374151"}},
                "tickangle": -35, "automargin": True,
            },
            "yaxis": {
                "title":     {"text": config.get("y_label", "Value"), "font": {"size": 13, "color": "#374151"}},
                "showgrid":  True, "gridcolor": "#E5E7EB", "automargin": True,
            },
            "legend": {
                "title": {"text": config.get("secondary_label", "Group")},
                "orientation": "v",
            },
            "paper_bgcolor": "#FFFFFF",
            "plot_bgcolor":  "#FFFFFF",
            "margin": {"l": 80, "r": 160, "t": 60, "b": 130},
            "showlegend": True,
        }
        return {"data": traces, "layout": layout}

    @staticmethod
    def _build_period_comparison(data: List[Dict], config: Dict) -> Dict[str, Any]:
        """Build a bar chart for period-over-period comparison with per-bar colours."""
        periods = [d["period"] for d in data]
        values  = [d["value"]  for d in data]
        colors  = ChartBuilder.DEFAULT_COLORS[:len(data)]

        trace = {
            "type":   "bar",
            "x":      periods,
            "y":      values,
            "marker": {"color": colors, "line": {"width": 0}},
            "hovertemplate": "<b>%{x}</b><br>Value: %{y:,.2f}<extra></extra>",
        }

        layout = {
            "title": {"text": config.get("title", "Period-over-Period"), "font": {"size": 20}},
            "xaxis": {
                "title":     {"text": config.get("x_label", "Period"), "font": {"size": 13, "color": "#374151"}},
                "tickangle": -30, "automargin": True,
            },
            "yaxis": {
                "title":     {"text": config.get("y_label", "Value"), "font": {"size": 13, "color": "#374151"}},
                "showgrid":  True, "gridcolor": "#E5E7EB", "automargin": True,
            },
            "paper_bgcolor": "#FFFFFF",
            "plot_bgcolor":  "#FFFFFF",
            "margin": {"l": 80, "r": 40, "t": 60, "b": 100},
        }
        return {"data": [trace], "layout": layout}

    @staticmethod
    def to_json(chart_spec: Dict[str, Any]) -> str:
        """Convert chart specification to JSON string"""
        return json.dumps(chart_spec, indent=2)
