"""
ExportManager — convert dashboard charts to PDF, PNG (ZIP), or CSV (ZIP).

Soft dependencies (falls back gracefully when absent):
  kaleido   — pip install kaleido    (Plotly → PNG rasterisation)
  reportlab — pip install reportlab  (PDF assembly)

Both are listed in requirements.txt for Phase 3.
"""
import io
import zipfile
from datetime import datetime
from typing import List, Optional

import pandas as pd


def _kaleido_available() -> bool:
    try:
        import kaleido  # noqa: F401
        return True
    except ImportError:
        return False


def _reportlab_available() -> bool:
    try:
        import reportlab  # noqa: F401
        return True
    except ImportError:
        return False


class ExportManager:
    """Converts dashboard chart configs to PDF, PNG ZIP, or CSV ZIP byte streams."""

    # ─── PNG ─────────────────────────────────────────────────────────────────

    def chart_to_png_bytes(
        self,
        plotly_spec: dict,
        width: int = 1200,
        height: int = 600,
    ) -> Optional[bytes]:
        """Render a Plotly JSON spec to PNG via Kaleido. Returns None on failure."""
        if not _kaleido_available():
            return None
        try:
            import plotly.graph_objects as go
            import plotly.io as pio

            fig = go.Figure(
                data=plotly_spec.get("data", []),
                layout=plotly_spec.get("layout", {}),
            )
            return pio.to_image(fig, format="png", width=width, height=height, scale=2)
        except Exception:
            return None

    def dashboard_to_png_zip(self, charts: List[dict]) -> bytes:
        """Return a ZIP file containing one PNG per chart."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            rendered = 0
            for i, chart in enumerate(charts):
                title_slug = (
                    chart.get("title", f"chart_{i + 1}")
                    .replace(" ", "_")
                    .replace("/", "-")[:40]
                )
                spec = chart.get("plotlySpec") or chart.get("plotly_spec") or {}
                if not spec:
                    continue
                png = self.chart_to_png_bytes(spec, width=1200, height=600)
                if png:
                    zf.writestr(f"{i + 1:02d}_{title_slug}.png", png)
                    rendered += 1
            if rendered == 0:
                msg = (
                    "No charts could be rendered.\n"
                    "Ensure kaleido is installed: pip install kaleido\n"
                )
                zf.writestr("README.txt", msg)
        return buf.getvalue()

    # ─── PDF (from pre-rendered client-side images — no Kaleido needed) ──────

    def dashboard_to_pdf_from_images(
        self,
        dashboard_name: str,
        description: str,
        charts: List[dict],
    ) -> bytes:
        """
        Assemble a PDF from base64 PNG images captured by the browser.

        Each item in `charts` must have:
          - title: str
          - image_b64: str   — a data-URL "data:image/png;base64,..." or raw base64
          - insights: list   — optional list of insight dicts with a "text" key
        """
        if not _reportlab_available():
            raise RuntimeError("reportlab is not installed. Run: pip install reportlab")

        import base64

        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            Image,
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
        )

        buf = io.BytesIO()
        page_w, page_h = landscape(A4)
        doc = SimpleDocTemplate(
            buf,
            pagesize=landscape(A4),
            leftMargin=1.5 * cm,
            rightMargin=1.5 * cm,
            topMargin=1.5 * cm,
            bottomMargin=1.5 * cm,
        )

        def _ps(name, **kw):
            return ParagraphStyle(name, **kw)

        title_st = _ps("DTitle2", fontSize=22, fontName="Helvetica-Bold",
                        spaceAfter=8, textColor=colors.HexColor("#1e3a5f"))
        meta_st = _ps("Meta2", fontSize=10, fontName="Helvetica",
                       spaceAfter=4, textColor=colors.HexColor("#555555"))
        chart_title_st = _ps("CTitle2", fontSize=14, fontName="Helvetica-Bold",
                               spaceAfter=6, textColor=colors.HexColor("#1e3a5f"))
        insight_head_st = _ps("IHead2", fontSize=9, fontName="Helvetica-Bold", spaceAfter=3)
        insight_st = _ps("IBody2", fontSize=8, fontName="Helvetica",
                          leftIndent=10, spaceAfter=2, textColor=colors.HexColor("#444444"))
        no_chart_st = _ps("NoChart2", fontSize=9, fontName="Helvetica-Oblique",
                           textColor=colors.HexColor("#888888"))

        story = []
        story.append(Paragraph(dashboard_name, title_st))
        if description:
            story.append(Paragraph(description, meta_st))
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        story.append(Paragraph(f"Exported {ts}  ·  {len(charts)} chart(s)", meta_st))
        story.append(Spacer(1, 0.8 * cm))

        usable_w = page_w - 3 * cm
        chart_img_h = page_h - 7 * cm

        for i, chart in enumerate(charts):
            if i > 0:
                story.append(PageBreak())

            story.append(Paragraph(chart.get("title", f"Chart {i + 1}"), chart_title_st))

            img_b64 = chart.get("image_b64", "")
            if img_b64:
                # Strip data-URL prefix if present
                if "," in img_b64:
                    img_b64 = img_b64.split(",", 1)[1]
                try:
                    raw = base64.b64decode(img_b64)
                    story.append(
                        Image(io.BytesIO(raw), width=usable_w, height=chart_img_h * 0.82)
                    )
                except Exception:
                    story.append(Paragraph("[Could not decode image]", no_chart_st))
            else:
                story.append(Paragraph("[No image data received]", no_chart_st))

            insights = chart.get("insights", [])
            if insights:
                story.append(Spacer(1, 0.2 * cm))
                story.append(Paragraph("Key Insights:", insight_head_st))
                for ins in insights[:3]:
                    text = ins.get("text", "") if isinstance(ins, dict) else str(ins)
                    if text:
                        story.append(Paragraph(f"• {text}", insight_st))

        doc.build(story)
        return buf.getvalue()

    # ─── PDF (server-side Kaleido fallback — kept for completeness) ───────────

    def dashboard_to_pdf(
        self,
        dashboard_name: str,
        description: str,
        charts: List[dict],
    ) -> bytes:
        """Assemble all dashboard charts into a multi-page landscape-A4 PDF."""
        if not _reportlab_available():
            raise RuntimeError(
                "reportlab is not installed. Run: pip install reportlab"
            )

        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            Image,
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
        )

        buf = io.BytesIO()
        page_w, page_h = landscape(A4)
        doc = SimpleDocTemplate(
            buf,
            pagesize=landscape(A4),
            leftMargin=1.5 * cm,
            rightMargin=1.5 * cm,
            topMargin=1.5 * cm,
            bottomMargin=1.5 * cm,
        )

        # Styles
        def _ps(name, **kw):
            return ParagraphStyle(name, **kw)

        title_st = _ps(
            "DTitle",
            fontSize=22,
            fontName="Helvetica-Bold",
            spaceAfter=8,
            textColor=colors.HexColor("#1e3a5f"),
        )
        meta_st = _ps(
            "Meta",
            fontSize=10,
            fontName="Helvetica",
            spaceAfter=4,
            textColor=colors.HexColor("#555555"),
        )
        chart_title_st = _ps(
            "CTitle",
            fontSize=14,
            fontName="Helvetica-Bold",
            spaceAfter=6,
            textColor=colors.HexColor("#1e3a5f"),
        )
        insight_head_st = _ps(
            "IHead",
            fontSize=9,
            fontName="Helvetica-Bold",
            spaceAfter=3,
        )
        insight_st = _ps(
            "IBody",
            fontSize=8,
            fontName="Helvetica",
            leftIndent=10,
            spaceAfter=2,
            textColor=colors.HexColor("#444444"),
        )
        no_chart_st = _ps(
            "NoChart",
            fontSize=9,
            fontName="Helvetica-Oblique",
            textColor=colors.HexColor("#888888"),
        )

        story = []

        # Cover section
        story.append(Paragraph(dashboard_name, title_st))
        if description:
            story.append(Paragraph(description, meta_st))
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        story.append(
            Paragraph(f"Exported {ts}  ·  {len(charts)} chart(s)", meta_st)
        )
        story.append(Spacer(1, 0.8 * cm))

        usable_w = page_w - 3 * cm
        # Chart image height: total page minus margins (3 cm) minus title/insights area (~4 cm)
        chart_img_h = page_h - 7 * cm

        for i, chart in enumerate(charts):
            if i > 0:
                story.append(PageBreak())

            chart_title = chart.get("title", f"Chart {i + 1}")
            story.append(Paragraph(chart_title, chart_title_st))

            spec = chart.get("plotlySpec") or chart.get("plotly_spec") or {}
            if spec:
                # Render at 3× physical size for crisp output
                png_w = int(usable_w * 3.78)   # pt → px at 96 dpi ≈ 3.78
                png_h = int(chart_img_h * 3.0)
                png = self.chart_to_png_bytes(spec, width=png_w, height=png_h)
                if png:
                    story.append(
                        Image(io.BytesIO(png), width=usable_w, height=chart_img_h * 0.80)
                    )
                else:
                    story.append(
                        Paragraph(
                            "[Chart image unavailable — kaleido not installed or render failed]",
                            no_chart_st,
                        )
                    )
            else:
                story.append(Paragraph("[No chart specification stored]", no_chart_st))

            # Key insights (max 3)
            insights = (chart.get("queryResult") or {}).get("insights", [])
            if insights:
                story.append(Spacer(1, 0.2 * cm))
                story.append(Paragraph("Key Insights:", insight_head_st))
                for ins in insights[:3]:
                    text = ins.get("text", "") if isinstance(ins, dict) else str(ins)
                    if text:
                        story.append(Paragraph(f"• {text}", insight_st))

        doc.build(story)
        return buf.getvalue()

    # ─── CSV ─────────────────────────────────────────────────────────────────

    def dashboard_to_csv_zip(self, charts: List[dict]) -> bytes:
        """Return a ZIP containing one CSV per chart, from queryResult.data."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            exported = 0
            for i, chart in enumerate(charts):
                title_slug = (
                    chart.get("title", f"chart_{i + 1}")
                    .replace(" ", "_")
                    .replace("/", "-")[:40]
                )
                data = (chart.get("queryResult") or {}).get("data", [])
                if not data or not isinstance(data, list):
                    continue
                if not isinstance(data[0], dict):
                    continue
                df = pd.DataFrame(data)
                zf.writestr(
                    f"{i + 1:02d}_{title_slug}.csv",
                    df.to_csv(index=False, encoding="utf-8"),
                )
                exported += 1
            if exported == 0:
                zf.writestr(
                    "README.txt",
                    "No tabular chart data available for CSV export.\n"
                    "Only charts with a queryResult.data array can be exported as CSV.\n",
                )
        return buf.getvalue()
