"""
Dashboard summary generator — produces HTML + PDF summaries for scheduled email reports.

Insight pipeline (in priority order):
  1. Use insights already stored in chart's queryResult.insights (new saves)
  2. Re-generate insights on-the-fly from queryResult.data/summary using the
     same narrative_generator that powers the live query view (works for any
     existing dashboard — no re-save required)
  3. Fall back to "No insights available" only if there is literally no data
"""
import json
from datetime import datetime
from typing import Dict, Any, List

FRONTEND_BASE = "http://localhost:5500"

_TEMPLATE_LABELS: Dict[str, str] = {
    "trend_over_time":       "Trend Over Time",
    "category_comparison":   "Category Comparison",
    "distribution_analysis": "Distribution Analysis",
    "top_k_items":           "Top-K Items",
    "scatter_relationship":  "Scatter / Correlation",
    "correlation_analysis":  "Correlation Heatmap",
    "grouped_aggregation":   "Aggregation by Group",
    "period_over_period":    "Period-over-Period",
}

_TYPE_ICON: Dict[str, str] = {
    "trend_over_time":       "📈",
    "category_comparison":   "📊",
    "distribution_analysis": "🥧",
    "top_k_items":           "🏆",
    "scatter_relationship":  "🔵",
    "correlation_analysis":  "🔲",
    "grouped_aggregation":   "📋",
    "period_over_period":    "🔄",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_stored_insights(ch: dict) -> List[str]:
    """Return insight strings that were already saved in the chart config."""
    candidates: List[str] = []
    for store in [
        (ch.get("queryResult") or {}).get("insights", []),
        ch.get("insights", []),
    ]:
        for ins in store:
            txt = ins.get("text", "") if isinstance(ins, dict) else str(ins)
            if txt.strip() and txt not in candidates:
                candidates.append(txt.strip())
    return candidates[:3]


def _regenerate_insights(ttype: str, query_result: dict) -> List[str]:
    """
    Re-run narrative_generator against stored queryResult data so that
    dashboards saved before insights were embedded still get real insights.
    """
    if not ttype or not query_result.get("data"):
        return []
    try:
        from app.services.insights.narrative_generator import generate_insights
        data = query_result.get("data", [])
        # Build minimal params from data key names
        params: Dict[str, Any] = {}
        if data:
            first = data[0]
            if "category" in first:
                params["metric_column"] = "Value"
            elif "time" in first:
                params["metric_column"] = "Value"
            elif "item" in first:
                params["metric_column"] = "Value"
                params["k"] = len(data)
                params["direction"] = "top"
            elif "x" in first and "y" in first:
                params["x_column"] = "X"
                params["y_column"] = "Y"

        raw = generate_insights(ttype, query_result, params)
        return [ins.get("text", "") for ins in raw if ins.get("text", "").strip()][:3]
    except Exception as exc:
        print(f"[summary_generator] insight regen failed ({ttype}): {exc}")
        return []


def _chart_meta(ch: dict) -> tuple:
    """
    Return (display_title, template_type, template_label, dataset_name).
    Reads from the nested keys that query.js actually stores.
    """
    raw_title = ch.get("title", "Untitled Chart")

    # Template info — stored under ch.template.type / ch.template.name
    tpl   = ch.get("template") or {}
    ttype = tpl.get("type") or ch.get("template_type") or ch.get("templateType") or ""
    tname = tpl.get("name") or _TEMPLATE_LABELS.get(ttype, "")

    # Dataset name — stored under ch.dataset.name
    ds_obj       = ch.get("dataset") or {}
    dataset_name = (
        ds_obj.get("name")
        or ch.get("datasetName")
        or ch.get("dataset_name")
        or ""
    )
    # Fall back: parse from title ("Template Name - dataset.csv")
    if not dataset_name and " - " in raw_title:
        dataset_name = raw_title.split(" - ", 1)[1].strip()

    # Display title: prefer template name, else first part of title
    display_title = tname or (raw_title.split(" - ")[0].strip() if " - " in raw_title else raw_title)

    # Readable type label
    type_label = _TEMPLATE_LABELS.get(ttype, tname or display_title)

    return display_title, ttype, type_label, dataset_name


# ── Public API ────────────────────────────────────────────────────────────────

def generate_dashboard_summary(dashboard) -> Dict[str, Any]:
    """Return a rich summary dict for a Dashboard ORM object."""
    try:
        config = (
            json.loads(dashboard.config_json)
            if isinstance(dashboard.config_json, str)
            else dashboard.config_json
        ) or {}
    except Exception:
        config = {}

    charts = config.get("charts", [])
    chart_summaries = []

    for ch in charts:
        title, ttype, type_label, dataset_name = _chart_meta(ch)
        qr        = ch.get("queryResult") or {}
        data_rows = len(qr.get("data", []))
        summary   = qr.get("summary") or {}

        # 1. Try stored insights; 2. regenerate from data; 3. fall back
        insights = _extract_stored_insights(ch)
        if not insights:
            insights = _regenerate_insights(ttype, qr)

        chart_summaries.append({
            "title":        title,
            "chart_type":   type_label,
            "type_icon":    _TYPE_ICON.get(ttype, "📊"),
            "dataset_name": dataset_name,
            "data_rows":    data_rows,
            "summary":      summary,
            "insights":     insights,
        })

    return {
        "dashboard_id":   dashboard.id,
        "dashboard_name": dashboard.name,
        "description":    dashboard.description or "",
        "chart_count":    len(charts),
        "charts":         chart_summaries,
        "generated_at":   datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    }


# ── HTML email ────────────────────────────────────────────────────────────────

def render_html_email(summary: Dict[str, Any], frequency: str) -> str:
    freq_label    = frequency.capitalize()
    dashboard_id  = summary.get("dashboard_id", "")
    dashboard_url = f"{FRONTEND_BASE}/view-dashboard.html?id={dashboard_id}"

    charts_html = ""
    for i, ch in enumerate(summary["charts"], 1):
        icon = ch.get("type_icon", "📊")

        rows_badge = (
            f'<span style="background:#eff6ff;color:#1d4ed8;font-size:11px;'
            f'padding:1px 7px;border-radius:10px;margin-left:6px;white-space:nowrap;">'
            f'{ch["data_rows"]:,} rows</span>'
        ) if ch["data_rows"] > 0 else ""

        ds_badge = (
            f'<span style="background:#f0fdf4;color:#15803d;font-size:11px;'
            f'padding:1px 7px;border-radius:10px;margin-left:4px;white-space:nowrap;">'
            f'📁 {ch["dataset_name"]}</span>'
        ) if ch["dataset_name"] else ""

        if ch["insights"]:
            bullets = "".join(
                f'<li style="margin:4px 0;color:#374151;font-size:13px;line-height:1.5;">{ins}</li>'
                for ins in ch["insights"]
            )
            insights_block = (
                f'<ul style="margin:6px 0 0 0;padding-left:16px;list-style:disc;">'
                f'{bullets}</ul>'
            )
        else:
            insights_block = (
                '<p style="margin:6px 0 0 0;color:#9ca3af;font-size:12px;font-style:italic;">'
                'No data available for this chart.</p>'
            )

        charts_html += f"""
        <tr style="border-bottom:1px solid #f3f4f6;">
          <td style="padding:14px 18px;vertical-align:top;">
            <div style="display:flex;align-items:center;flex-wrap:wrap;gap:4px;margin-bottom:4px;">
              <span style="font-weight:700;color:#1e3a5f;font-size:14px;">
                {icon} {i}. {ch["title"]}
              </span>
              <span style="color:#6b7280;font-size:12px;">— {ch["chart_type"]}</span>
              {rows_badge}{ds_badge}
            </div>
            <div style="padding:8px 12px;background:#f8fafc;border-left:3px solid #2563eb;
                        border-radius:0 6px 6px 0;margin-top:6px;">
              {insights_block}
            </div>
          </td>
        </tr>"""

    no_charts = '<tr><td style="padding:16px;color:#9ca3af;font-size:13px;">No charts in this dashboard.</td></tr>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:32px 0;">
<tr><td align="center">
<table width="640" cellpadding="0" cellspacing="0"
       style="background:#fff;border-radius:12px;overflow:hidden;
              box-shadow:0 4px 16px rgba(0,0,0,.08);max-width:640px;">

  <!-- Header -->
  <tr>
    <td style="background:linear-gradient(135deg,#1d4ed8 0%,#4f46e5 100%);padding:32px 40px 28px;">
      <div style="font-size:32px;margin-bottom:10px;">📊</div>
      <h1 style="margin:0 0 6px;color:#fff;font-size:24px;font-weight:800;letter-spacing:-0.3px;">
        {freq_label} Dashboard Report
      </h1>
      <p style="margin:0;color:#bfdbfe;font-size:13px;">Generated {summary["generated_at"]}</p>
    </td>
  </tr>

  <!-- Dashboard metadata -->
  <tr>
    <td style="padding:24px 40px 16px;border-bottom:2px solid #e5e7eb;">
      <h2 style="margin:0 0 6px;color:#111827;font-size:20px;font-weight:700;">
        {summary["dashboard_name"]}
      </h2>
      {"<p style='margin:0 0 10px;color:#4b5563;font-size:14px;line-height:1.6;'>" + summary["description"] + "</p>" if summary["description"] else ""}
      <p style="margin:0;color:#6b7280;font-size:13px;">
        This report covers
        <strong style="color:#1d4ed8;">{summary["chart_count"]}</strong>
        chart{"s" if summary["chart_count"] != 1 else ""} in your dashboard.
      </p>
    </td>
  </tr>

  <!-- Charts & insights -->
  <tr>
    <td style="padding:22px 40px 10px;">
      <h3 style="margin:0 0 14px;color:#111827;font-size:16px;font-weight:700;">
        Charts &amp; Key Insights
      </h3>
      <table width="100%" cellpadding="0" cellspacing="0"
             style="border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;">
        {charts_html if charts_html else no_charts}
      </table>
    </td>
  </tr>

  <!-- CTA -->
  <tr>
    <td style="padding:24px 40px 32px;text-align:center;">
      <a href="{dashboard_url}"
         style="display:inline-block;background:linear-gradient(135deg,#1d4ed8,#4f46e5);
                color:#fff;text-decoration:none;padding:14px 36px;border-radius:8px;
                font-size:15px;font-weight:700;letter-spacing:0.2px;">
        Open Dashboard →
      </a>
      <p style="margin:10px 0 0;color:#9ca3af;font-size:11px;">{dashboard_url}</p>
    </td>
  </tr>

  <!-- Footer -->
  <tr>
    <td style="background:#f8fafc;padding:14px 40px;border-top:1px solid #e5e7eb;
               text-align:center;color:#9ca3af;font-size:11px;line-height:1.7;">
      BI Dashboard Generator · {freq_label} Scheduled Report<br>
      You received this because a report schedule is active for this dashboard.
    </td>
  </tr>

</table>
</td></tr>
</table>
</body>
</html>"""


# ── PDF report ────────────────────────────────────────────────────────────────

def render_pdf_report(summary: Dict[str, Any], frequency: str) -> bytes:
    """Generate a PDF report with reportlab — no chart images, full insights."""
    try:
        import io
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
        )

        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf, pagesize=A4,
            leftMargin=2*cm, rightMargin=2*cm,
            topMargin=2*cm, bottomMargin=2*cm,
        )

        def _ps(name, **kw):
            return ParagraphStyle(name, **kw)

        h1 = _ps("h1", fontSize=22, fontName="Helvetica-Bold", spaceAfter=4,
                 textColor=colors.HexColor("#1d4ed8"))
        h2 = _ps("h2", fontSize=16, fontName="Helvetica-Bold", spaceAfter=4,
                 textColor=colors.HexColor("#111827"))
        h3 = _ps("h3", fontSize=12, fontName="Helvetica-Bold", spaceAfter=6,
                 textColor=colors.HexColor("#374151"))
        p  = _ps("p",  fontSize=10, fontName="Helvetica",       spaceAfter=2,
                 textColor=colors.HexColor("#4b5563"), leading=14)
        sm = _ps("sm", fontSize=9,  fontName="Helvetica",        spaceAfter=2,
                 textColor=colors.HexColor("#6b7280"))

        dashboard_url = f"{FRONTEND_BASE}/view-dashboard.html?id={summary.get('dashboard_id', '')}"

        story: list = [
            Paragraph(f"{frequency.capitalize()} Dashboard Report", h1),
            Paragraph(summary["dashboard_name"], h2),
        ]
        if summary["description"]:
            story.append(Paragraph(summary["description"], p))
        story.append(Paragraph(
            f"Generated: {summary['generated_at']}  ·  Charts: {summary['chart_count']}  ·  {dashboard_url}",
            sm,
        ))
        story.append(Spacer(1, 0.3*cm))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#d1d5db")))
        story.append(Spacer(1, 0.4*cm))
        story.append(Paragraph("Charts & Key Insights", h3))

        if not summary["charts"]:
            story.append(Paragraph("No charts in this dashboard.", sm))
        else:
            header_row = [
                Paragraph("<b>#</b>", _ps("th", fontSize=9, fontName="Helvetica-Bold",
                                          textColor=colors.white)),
                Paragraph("<b>Chart</b>", _ps("th2", fontSize=9, fontName="Helvetica-Bold",
                                              textColor=colors.white)),
                Paragraph("<b>Type / Dataset</b>", _ps("th3", fontSize=9, fontName="Helvetica-Bold",
                                                        textColor=colors.white)),
                Paragraph("<b>Key Insights</b>", _ps("th4", fontSize=9, fontName="Helvetica-Bold",
                                                      textColor=colors.white)),
            ]
            rows = [header_row]

            for i, ch in enumerate(summary["charts"], 1):
                # Insight text
                if ch["insights"]:
                    insight_text = "\n".join(f"• {t}" for t in ch["insights"])
                else:
                    insight_text = "No data available."

                ds_text = ch["dataset_name"] if ch["dataset_name"] else "—"
                type_ds = f"{ch['chart_type']}\n{ds_text}"
                if ch["data_rows"] > 0:
                    type_ds += f"\n({ch['data_rows']:,} rows)"

                cell_style = _ps(f"cell{i}", fontSize=8, fontName="Helvetica",
                                 textColor=colors.HexColor("#374151"), leading=11)
                bold_style = _ps(f"bold{i}", fontSize=8, fontName="Helvetica-Bold",
                                 textColor=colors.HexColor("#1e3a5f"), leading=11)
                rows.append([
                    Paragraph(str(i), cell_style),
                    Paragraph(ch["title"], bold_style),
                    Paragraph(type_ds, cell_style),
                    Paragraph(insight_text, cell_style),
                ])

            tbl = Table(rows, colWidths=[0.6*cm, 3.8*cm, 3.8*cm, 8.0*cm])
            tbl.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, 0),  colors.HexColor("#1d4ed8")),
                ("ROWBACKGROUNDS",(0, 1), (-1, -1),
                 [colors.white, colors.HexColor("#f0f4ff")]),
                ("GRID",          (0, 0), (-1, -1),  0.4, colors.HexColor("#e5e7eb")),
                ("VALIGN",        (0, 0), (-1, -1),  "TOP"),
                ("LEFTPADDING",   (0, 0), (-1, -1),  5),
                ("RIGHTPADDING",  (0, 0), (-1, -1),  5),
                ("TOPPADDING",    (0, 0), (-1, -1),  5),
                ("BOTTOMPADDING", (0, 0), (-1, -1),  6),
            ]))
            story.append(tbl)

        doc.build(story)
        return buf.getvalue()
    except Exception as exc:
        print(f"[summary_generator] PDF render failed: {exc}")
        return b""
