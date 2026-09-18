"""Renders the same report_data dict served by /api/report into a .pptx deck.

Reuses the web dashboard's already-computed, already-formatted data verbatim -
no metric is recalculated here (numbers charted here are parsed back out of
the same formatted strings the tables/docx/xlsx already show, via `_num()`,
rather than re-deriving anything). Unlike the docx/xlsx exports (reference
documents that show everything), a slide has to stay readable at a glance:
wide tables are trimmed to their most decision-relevant columns, long tables
are capped to a top-N + TOTAL, and each analytical section pairs its table
with a native chart plus a one-line takeaway so the deck reads as an
analytics presentation, not a document pasted onto slides.
"""
import io
import re

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

# Theme: light lavender canvas, deep indigo headlines, purple/teal/yellow/coral
# accents - a data-analytics deck palette rather than the docx/xlsx's navy
# report look, since this format is meant to be presented, not filed.
BG = RGBColor(0xF3, 0xF1, 0xFC)
CARD = RGBColor(0xFF, 0xFF, 0xFF)
INK = RGBColor(0x2A, 0x25, 0x52)
MUTED = RGBColor(0x8B, 0x86, 0xAE)
INDIGO = RGBColor(0x34, 0x2D, 0x6B)
TABLE_HEADER_FILL = RGBColor(0xE7, 0xE3, 0xFA)

PURPLE = RGBColor(0x7B, 0x6E, 0xF3)
TEAL = RGBColor(0x2F, 0xC2, 0xB2)
YELLOW = RGBColor(0xFB, 0xC0, 0x2B)
LILAC = RGBColor(0xB6, 0xAE, 0xF0)
DEEP_PURPLE = RGBColor(0x5B, 0x4E, 0xC4)
CORAL = RGBColor(0xFF, 0x8A, 0x65)
CHART_COLORS = [PURPLE, TEAL, YELLOW, LILAC, DEEP_PURPLE, CORAL]

GOOD = RGBColor(0x1F, 0xA3, 0x63)
WARNING = RGBColor(0xC9, 0x8A, 0x0A)
CRITICAL = RGBColor(0xE1, 0x4B, 0x5A)
NEUTRAL = RGBColor(0x60, 0x5A, 0x8A)

_DIR_COLOR = {"up": GOOD, "down": CRITICAL, "neutral": NEUTRAL}
_TONE_COLOR = {"good": GOOD, "warning": WARNING, "critical": CRITICAL, "neutral": NEUTRAL}
_PRIORITY_COLOR = {"CRITICAL": CRITICAL, "HIGH": WARNING, "MEDIUM": NEUTRAL, "WIN": GOOD}
PERIOD_TITLES = {"day": "DAILY", "week": "WEEKLY", "month": "MONTHLY"}

SLIDE_W, SLIDE_H = Inches(13.333), Inches(7.5)
MARGIN = Inches(0.45)
CONTENT_W = SLIDE_W - 2 * MARGIN

# Shared two-column layout (chart left, table right) reused across every
# section that pairs a visual with its supporting detail.
COL_GAP = Inches(0.3)
LEFT_W = Inches(5.9)
RIGHT_LEFT = MARGIN + LEFT_W + COL_GAP
RIGHT_W = CONTENT_W - LEFT_W - COL_GAP


def _num(value) -> float:
    """Parses a number back out of the report's formatted strings
    ('6,601' / '78.2%' / 'KES 1,234.56' / '+2.3 pp') so charts can plot the
    exact figures already shown in the tables, without re-deriving them."""
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = re.sub(r"[^0-9.\-]", "", str(value))
    return float(cleaned) if cleaned not in ("", "-", ".") else 0.0


def _new_slide(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank layout
    bg = slide.shapes.add_shape(1, 0, 0, SLIDE_W, SLIDE_H)  # MSO_SHAPE.RECTANGLE == 1
    bg.fill.solid()
    bg.fill.fore_color.rgb = BG
    bg.line.fill.background()
    bg.shadow.inherit = False
    slide.shapes._spTree.remove(bg._element)
    slide.shapes._spTree.insert(2, bg._element)  # push background behind later shapes
    return slide


def _textbox(slide, text, left, top, width, height, size=14, bold=False, italic=False, color=INK, align=PP_ALIGN.LEFT):
    tb = slide.shapes.add_textbox(left, top, width, height)
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    run.font.name = "Calibri"
    return tb


def _section_title(slide, number, title, sub=None):
    _textbox(slide, f"{number}. {title}", MARGIN, Inches(0.3), CONTENT_W, Inches(0.6), size=24, bold=True, color=INDIGO)
    bar = slide.shapes.add_shape(1, MARGIN, Inches(0.82), Inches(0.55), Inches(0.05))
    bar.fill.solid()
    bar.fill.fore_color.rgb = YELLOW
    bar.line.fill.background()
    if sub:
        _textbox(slide, sub, MARGIN, Inches(0.95), CONTENT_W, Inches(0.5), size=12, italic=True, color=MUTED)


def _top_n(rows, n=8):
    if not rows:
        return rows, 0
    if rows[-1].get("shop", rows[-1].get("metric", "")).strip().upper() != "TOTAL" or len(rows) <= n + 1:
        return rows[: n + 1], max(0, len(rows) - (n + 1))
    total = rows[-1]
    top = rows[:n]
    return top + [total], len(rows) - n - 1


def _pick(row, keys):
    return [str(row.get(k, "")) for k in keys]


def _add_table(slide, headers, rows, keys, top, height=None, color_key=None, left=None, width=None):
    left = MARGIN if left is None else left
    width = CONTENT_W if width is None else width
    n_rows = len(rows) + 1
    height = height or Inches(0.32 * n_rows)
    shape = slide.shapes.add_table(n_rows, len(headers), left, top, width, height)
    table = shape.table
    table.first_row = False

    for c, h in enumerate(headers):
        cell = table.cell(0, c)
        cell.text = h
        cell.fill.solid()
        cell.fill.fore_color.rgb = TABLE_HEADER_FILL
        para = cell.text_frame.paragraphs[0]
        para.font.size = Pt(10)
        para.font.bold = True
        para.font.color.rgb = INDIGO

    for r, row in enumerate(rows, start=1):
        is_total = str(row.get("shop", row.get("metric", ""))).strip().upper() == "TOTAL"
        values = _pick(row, keys)
        for c, val in enumerate(values):
            cell = table.cell(r, c)
            cell.text = val
            cell.fill.solid()
            cell.fill.fore_color.rgb = CARD
            para = cell.text_frame.paragraphs[0]
            para.font.size = Pt(9.5)
            para.font.bold = is_total
            para.font.color.rgb = INK
            if color_key and c == color_key[0]:
                tone = row.get(color_key[1])
                color = _DIR_COLOR.get(tone) or _TONE_COLOR.get(tone)
                if color:
                    para.font.color.rgb = color

    return shape


def _truncation_note(slide, omitted, top, left=None, width=None):
    if omitted > 0:
        _textbox(slide, f"+ {omitted} more row(s) - see the full breakdown in the .docx/.xlsx export.",
                 left or MARGIN, top, width or CONTENT_W, Inches(0.35), size=9.5, italic=True, color=MUTED)


def _callout(slide, text, top, kind="context", left=None, width=None):
    color = {"critical": CRITICAL, "warning": WARNING, "good": GOOD}.get(kind, PURPLE)
    left = left or MARGIN
    width = width or CONTENT_W
    box = slide.shapes.add_shape(1, left, top, width, Inches(0.5))
    box.fill.solid()
    box.fill.fore_color.rgb = CARD
    box.line.color.rgb = color
    box.line.width = Pt(1)
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = Inches(0.1)
    tf.margin_top = Inches(0.05)
    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = text
    run.font.size = Pt(10.5)
    run.font.italic = True
    run.font.color.rgb = INK
    return box


def _caption(slide, text, left, top, width, height=Inches(0.5)):
    _textbox(slide, text, left, top, width, height, size=10.5, italic=True, color=MUTED)


def _style_chart(chart, show_legend=True):
    chart.font.size = Pt(9.5)
    chart.font.color.rgb = INK
    if show_legend:
        chart.has_legend = True
        chart.legend.position = XL_LEGEND_POSITION.BOTTOM
        chart.legend.include_in_layout = False
        chart.legend.font.size = Pt(9.5)
    else:
        chart.has_legend = False


def _add_bar_chart(slide, categories, series, left, top, width, height, horizontal=False, number_format="#,##0"):
    """series: list of (name, values) tuples. One series -> each bar/category
    gets its own accent color; 2+ series -> one color per series with a legend."""
    chart_data = CategoryChartData()
    chart_data.categories = categories
    for name, values in series:
        chart_data.add_series(name, values)

    chart_type = XL_CHART_TYPE.BAR_CLUSTERED if horizontal else XL_CHART_TYPE.COLUMN_CLUSTERED
    gframe = slide.shapes.add_chart(chart_type, left, top, width, height, chart_data)
    chart = gframe.chart
    _style_chart(chart, show_legend=len(series) > 1)

    plot = chart.plots[0]
    plot.has_data_labels = True
    plot.data_labels.number_format = number_format
    plot.data_labels.number_format_is_linked = False
    plot.data_labels.font.size = Pt(8.5)
    plot.data_labels.font.color.rgb = INK

    if len(series) == 1:
        for i, point in enumerate(plot.series[0].points):
            point.format.fill.solid()
            point.format.fill.fore_color.rgb = CHART_COLORS[i % len(CHART_COLORS)]
    else:
        for i, s in enumerate(chart.series):
            s.format.fill.solid()
            s.format.fill.fore_color.rgb = CHART_COLORS[i % len(CHART_COLORS)]

    return chart


def _add_donut_chart(slide, categories, values, left, top, width, height):
    chart_data = CategoryChartData()
    chart_data.categories = categories
    chart_data.add_series("Share", values)

    gframe = slide.shapes.add_chart(XL_CHART_TYPE.DOUGHNUT, left, top, width, height, chart_data)
    chart = gframe.chart
    _style_chart(chart, show_legend=True)

    plot = chart.plots[0]
    plot.has_data_labels = True
    dl = plot.data_labels
    dl.show_percentage = True
    dl.show_value = False
    dl.show_category_name = False
    dl.number_format = "0.0%"
    dl.number_format_is_linked = False
    dl.font.size = Pt(9)
    dl.font.bold = True
    dl.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    for i, point in enumerate(plot.series[0].points):
        point.format.fill.solid()
        point.format.fill.fore_color.rgb = CHART_COLORS[i % len(CHART_COLORS)]

    return chart


def _add_line_chart(slide, categories, values, left, top, width, height, name="Value"):
    chart_data = CategoryChartData()
    chart_data.categories = categories
    chart_data.add_series(name, values)

    gframe = slide.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS, left, top, width, height, chart_data)
    chart = gframe.chart
    _style_chart(chart, show_legend=False)

    series = chart.series[0]
    series.format.line.color.rgb = PURPLE
    series.format.line.width = Pt(2.5)
    series.marker.format.fill.solid()
    series.marker.format.fill.fore_color.rgb = YELLOW

    return chart


# --- Slides ---

def _title_slide(prs, meta):
    slide = _new_slide(prs)

    logo = slide.shapes.add_shape(1, MARGIN, Inches(0.5), Inches(0.5), Inches(0.5))
    logo.fill.solid()
    logo.fill.fore_color.rgb = PURPLE
    logo.line.fill.background()
    _textbox(slide, "DENRI AFRICA", Inches(1.1), Inches(0.55), Inches(3.5), Inches(0.4), size=13, bold=True, color=INDIGO)

    title = f"{PERIOD_TITLES.get(meta['period_type'], '')} SALES PERFORMANCE REPORT"
    _textbox(slide, title, MARGIN, Inches(2.7), Inches(9.5), Inches(1.4), size=36, bold=True, color=INDIGO)
    bar = slide.shapes.add_shape(1, MARGIN, Inches(3.55), Inches(1.4), Inches(0.07))
    bar.fill.solid()
    bar.fill.fore_color.rgb = YELLOW
    bar.line.fill.background()

    _textbox(slide, f"{meta['period_label']} | {meta['date_range']} ({meta['days']} day(s))",
             MARGIN, Inches(3.85), Inches(9.5), Inches(0.5), size=15, bold=True, color=INK)
    _textbox(slide, f"Compared to: {meta['compared_to']}", MARGIN, Inches(4.3), Inches(9.5), Inches(0.4),
             size=12, italic=True, color=MUTED)

    # Decorative bar/pie cluster, right side - echoes an analytics cover slide
    # without needing external image assets.
    chart_data = CategoryChartData()
    chart_data.categories = ["A", "B", "C", "D"]
    chart_data.add_series("", (2.0, 3.2, 4.4, 5.6))
    gframe = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(10.1), Inches(4.3), Inches(2.6), Inches(2.3), chart_data)
    chart = gframe.chart
    chart.has_legend = False
    chart.has_title = False
    chart.category_axis.visible = False
    chart.value_axis.visible = False
    for i, point in enumerate(chart.plots[0].series[0].points):
        point.format.fill.solid()
        point.format.fill.fore_color.rgb = CHART_COLORS[i % len(CHART_COLORS)]

    donut_data = CategoryChartData()
    donut_data.categories = ["1", "2", "3"]
    donut_data.add_series("", (3, 2, 1))
    dframe = slide.shapes.add_chart(XL_CHART_TYPE.DOUGHNUT, Inches(10.3), Inches(1.5), Inches(2.2), Inches(2.2), donut_data)
    dchart = dframe.chart
    dchart.has_legend = False
    dchart.has_title = False
    for i, point in enumerate(dchart.plots[0].series[0].points):
        point.format.fill.solid()
        point.format.fill.fore_color.rgb = CHART_COLORS[i % len(CHART_COLORS)]

    _textbox(slide, "Denri Africa — Business Intelligence", MARGIN, Inches(6.6), Inches(9.5), Inches(0.4),
             size=11, color=MUTED)
    _textbox(slide, f"Generated {meta['generated_on']}", MARGIN, Inches(6.95), Inches(9.5), Inches(0.4),
             size=9.5, italic=True, color=MUTED)


def _kpi_slide(prs, kpi_strip, context_note):
    slide = _new_slide(prs)
    _textbox(slide, "Key Performance Indicators", MARGIN, Inches(0.3), CONTENT_W, Inches(0.6), size=24, bold=True, color=INDIGO)
    bar = slide.shapes.add_shape(1, MARGIN, Inches(0.82), Inches(0.55), Inches(0.05))
    bar.fill.solid()
    bar.fill.fore_color.rgb = YELLOW
    bar.line.fill.background()

    n = len(kpi_strip)
    card_w = (CONTENT_W - Inches(0.2) * (n - 1)) / n
    top = Inches(1.3)
    for i, card in enumerate(kpi_strip):
        left = MARGIN + i * (card_w + Inches(0.2))
        box = slide.shapes.add_shape(1, left, top, card_w, Inches(2.0))
        box.fill.solid()
        box.fill.fore_color.rgb = CARD
        box.line.fill.background()
        accent = slide.shapes.add_shape(1, left, top, card_w, Inches(0.08))
        accent.fill.solid()
        accent.fill.fore_color.rgb = CHART_COLORS[i % len(CHART_COLORS)]
        accent.line.fill.background()

        tf = box.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = Inches(0.1)
        tf.margin_top = Inches(0.18)

        p0 = tf.paragraphs[0]
        r0 = p0.add_run()
        r0.text = card["label"]
        r0.font.size = Pt(11)
        r0.font.color.rgb = MUTED

        p1 = tf.add_paragraph()
        r1 = p1.add_run()
        r1.text = card["value"]
        r1.font.size = Pt(19)
        r1.font.bold = True
        r1.font.color.rgb = INDIGO

        p2 = tf.add_paragraph()
        r2 = p2.add_run()
        r2.text = card["sub"]
        r2.font.size = Pt(10)
        r2.font.bold = True
        r2.font.color.rgb = _DIR_COLOR.get(card["tone"], NEUTRAL)

    _callout(slide, context_note, Inches(3.6))


def _exec_summary_slides(prs, data):
    slide = _new_slide(prs)
    _section_title(slide, 1, "Executive Summary")
    _textbox(slide, data["narrative"], MARGIN, Inches(1.3), LEFT_W, Inches(2.0), size=12, color=INK)

    headline = data["metrics"][0]
    is_money = headline["current"].strip().startswith("KES")
    _add_bar_chart(
        slide, ["Current", "Previous"],
        [(headline["metric"], [_num(headline["current"]), _num(headline["previous"])])],
        RIGHT_LEFT, Inches(1.3), RIGHT_W, Inches(2.3),
        number_format=('"KES" #,##0' if is_money else "#,##0"),
    )
    _caption(slide, f"{headline['metric']}: {headline['current']} vs {headline['previous']} last period.",
             RIGHT_LEFT, Inches(3.6), RIGHT_W, Inches(0.4))

    _add_table(slide, ["Metric", "Current", "Previous", "Change"], data["metrics"],
               ["metric", "current", "previous", "change"], Inches(4.2), color_key=(3, "dir"))

    slide2 = _new_slide(prs)
    _section_title(slide2, 1, "Executive Summary", "Flags & Meeting Note")
    top = Inches(1.4)
    for flag in data["flags"]:
        _callout(slide2, flag["text"], top, kind={"risk": "critical", "positive": "good", "watch": "warning"}.get(flag["kind"], "context"))
        top += Inches(0.6)
    _callout(slide2, "\U0001F4CB " + data["meeting_note"], top, kind="context")


def _customer_metrics_slides(prs, data):
    slide = _new_slide(prs)
    _section_title(slide, 2, "Customer Metrics")
    _textbox(slide, data["summary"], MARGIN, Inches(1.2), CONTENT_W, Inches(0.8), size=12, color=INK)
    _add_table(slide, ["Metric", "Current", "Previous", "Change"], data["comparison"],
               ["metric", "current", "previous", "change"], Inches(2.1), color_key=(3, "dir"))

    slide2 = _new_slide(prs)
    _section_title(slide2, 2, "Customer Metrics", "2.1 Purchase Frequency Distribution")
    freq = data["frequency"]
    leading = max(freq, key=lambda r: _num(r["count"]))
    _add_bar_chart(slide2, [r["band"] for r in freq], [("Customers", [_num(r["count"]) for r in freq])],
                   MARGIN, Inches(1.4), LEFT_W, Inches(3.6))
    _caption(slide2, f"\"{leading['band']}\" is the largest band ({leading['pct']} of customers) — {leading['read'].lower()}.",
             MARGIN, Inches(5.2), LEFT_W, Inches(0.6))
    _add_table(slide2, ["Frequency", "Count", "%", "Read"], freq,
               ["band", "count", "pct", "read"], Inches(1.4), left=RIGHT_LEFT, width=RIGHT_W)

    slide3 = _new_slide(prs)
    _section_title(slide3, 2, "Customer Metrics", "2.2 Channel Overview")
    channels = [r for r in data["channels"] if r["channel"] != "TOTAL"]
    _add_donut_chart(slide3, [r["channel"] for r in channels], [_num(r["customers"]) for r in channels],
                      MARGIN, Inches(1.4), LEFT_W, Inches(3.8))
    _add_table(slide3, ["Channel", "Customers", "Share", "Avg Spend", "Note"], data["channels"],
               ["channel", "customers", "share", "avg_spend", "note"], Inches(1.4), left=RIGHT_LEFT, width=RIGHT_W)
    _callout(slide3, "\U0001F4CB " + data["meeting_note"], Inches(5.5))


def _store_performance_slides(prs, data):
    slide = _new_slide(prs)
    _section_title(slide, 3, "Store Performance")
    _textbox(slide, data["summary"], MARGIN, Inches(1.2), CONTENT_W, Inches(0.7), size=12, color=INK)

    shops = [r for r in data["rows"] if r["shop"] != "TOTAL"][:8]
    top_shop = max(shops, key=lambda r: r["current_raw"]) if shops else None
    _add_bar_chart(slide, [r["shop"] for r in shops], [("Revenue (KES)", [r["current_raw"] for r in shops])],
                   MARGIN, Inches(2.0), LEFT_W, Inches(3.6), horizontal=True, number_format='"KES" #,##0')
    if top_shop:
        _caption(slide, f"{top_shop['shop']} led store revenue this period at {top_shop['current']}.",
                 MARGIN, Inches(5.6), LEFT_W, Inches(0.5))

    rows, omitted = _top_n(data["rows"], 8)
    _add_table(slide, ["Shop", "Current", "Change %", "Repeat Rate"], rows,
               ["shop", "current", "change_pct", "repeat_rate"], Inches(2.0), color_key=(2, "dir"), left=RIGHT_LEFT, width=RIGHT_W)
    _truncation_note(slide, omitted, Inches(6.0), left=RIGHT_LEFT, width=RIGHT_W)

    slide2 = _new_slide(prs)
    _section_title(slide2, 3, "Store Performance", "3.1 Channel Mix by Location")
    mix_rows, mix_omitted = _top_n(data["channel_mix"], 8)
    _add_table(slide2, ["Shop", "Walk-in", "Online", "Activation", "Online %"], mix_rows,
               ["shop", "walkin", "online", "activation", "online_pct"], Inches(1.3))
    _truncation_note(slide2, mix_omitted, Inches(6.0))

    slide3 = slide2
    if data.get("monthly_retention"):
        slide3 = _new_slide(prs)
        _section_title(slide3, 3, "Store Performance", "3.2 Monthly Customer Retention by Location")
        ret_rows, ret_omitted = _top_n(data["monthly_retention"], 8)
        _add_table(slide3, ["Shop", "Current", "Previous", "Repeat Rate", "Retention Rate"], ret_rows,
                   ["shop", "current", "previous", "repeat_rate", "retention_rate"], Inches(1.3))
        _truncation_note(slide3, ret_omitted, Inches(6.0))

    _callout(slide3, "\U0001F4CB " + data["meeting_note"], Inches(6.5))


def _gender_performance_slides(prs, data):
    slide = _new_slide(prs)
    _section_title(slide, 4, "Gender Performance Analysis")
    _textbox(slide, data["summary"], MARGIN, Inches(1.2), CONTENT_W, Inches(0.7), size=12, color=INK)
    if data.get("ratio"):
        _textbox(slide, f"Ratio: {data['ratio']['ratio_text']}", MARGIN, Inches(1.85), CONTENT_W, Inches(0.4), size=13, bold=True, color=PURPLE)

    overall = data["overall"]
    _add_donut_chart(slide, [r["gender"] for r in overall], [_num(r["count"]) for r in overall],
                      MARGIN, Inches(2.3), LEFT_W, Inches(3.8))
    _add_table(slide, ["Gender", "Count", "%", "Change"], overall,
               ["gender", "count", "pct", "change"], Inches(2.3), color_key=(3, "dir"), left=RIGHT_LEFT, width=RIGHT_W)

    slide2 = _new_slide(prs)
    _section_title(slide2, 4, "Gender Performance Analysis", "4.2 Gender by Location")
    cols = data["by_location"]["columns"]
    headers = ["Shop"] + cols + ["Total"]
    keys = ["shop"] + [c.lower() for c in cols] + ["total"]
    rows, omitted = _top_n(data["by_location"]["rows"], 10)
    _add_table(slide2, headers, rows, keys, Inches(1.3))
    _truncation_note(slide2, omitted, Inches(6.5))
    _callout(slide2, "\U0001F4CB " + data["meeting_note"], Inches(6.9))


def _traffic_slide(prs, data):
    slide = _new_slide(prs)
    _section_title(slide, 5, "Foot & Online Traffic Analysis")
    _textbox(slide, data["summary"], MARGIN, Inches(1.2), CONTENT_W, Inches(0.7), size=12, color=INK)
    top = Inches(1.95)
    if data.get("data_gap_note"):
        _callout(slide, "⚠ " + data["data_gap_note"], top, kind="warning")
        top += Inches(0.6)

    shops = [r for r in data["rows"] if r["shop"] != "TOTAL"][:8]
    _add_bar_chart(
        slide, [r["shop"] for r in shops],
        [("Walk-in", [r["walkin_total_raw"] for r in shops]), ("Online", [r["online_raw"] for r in shops])],
        MARGIN, top, LEFT_W, Inches(4.6 - float(top.inches - 1.95)),
    )

    rows, omitted = _top_n(data["rows"], 8)
    _add_table(slide, ["Shop", "Walk-in Total", "Conv. Rate", "Total Customers"], rows,
               ["shop", "walkin_total", "conv_rate", "total_customers"], top, left=RIGHT_LEFT, width=RIGHT_W)
    _truncation_note(slide, omitted, top + Inches(0.32 * (len(rows) + 1) + 0.1), left=RIGHT_LEFT, width=RIGHT_W)
    _callout(slide, "\U0001F4CB " + data["meeting_note"], Inches(6.9))


def _revenue_slides(prs, data):
    slide = _new_slide(prs)
    _section_title(slide, 6, "Revenue Analysis", "6.1 Revenue Bridge")
    _textbox(slide, data["summary"], MARGIN, Inches(1.3), CONTENT_W, Inches(0.8), size=12, color=INK)

    bridge = data["bridge"]
    if len(bridge) >= 2:
        _add_line_chart(slide, [row["period"] for row in bridge], [row["revenue_raw"] for row in bridge],
                         MARGIN, Inches(2.2), CONTENT_W, Inches(4.6), name="Revenue (KES)")

    slide2 = _new_slide(prs)
    _section_title(slide2, 6, "Revenue Analysis", "Key Metrics")
    _add_table(slide2, ["Metric", "Current", "Previous", "Change"], data["comparison"],
               ["metric", "current", "previous", "change"], Inches(1.3), color_key=(3, "dir"))
    _callout(slide2, "\U0001F4CB " + data["meeting_note"], Inches(5.0))


def _data_quality_slide(prs, data):
    slide = _new_slide(prs)
    _section_title(slide, 7, "Data Quality (KYC)")
    _textbox(slide, data["summary"], MARGIN, Inches(1.2), CONTENT_W, Inches(0.7), size=12, color=INK)

    rows_by_metric = {r["metric"]: r for r in data["comparison"]}
    quality_labels = ["Valid Phone Numbers", "N/A Phones", "Invalid"]
    quality_rows = [rows_by_metric[m] for m in quality_labels if m in rows_by_metric]
    valid_row = rows_by_metric.get("Valid Phone Numbers")

    if quality_rows:
        _add_donut_chart(slide, [r["metric"] for r in quality_rows], [_num(r["current"]) for r in quality_rows],
                          MARGIN, Inches(1.95), LEFT_W, Inches(3.9))
        if valid_row:
            _caption(slide, f"{valid_row['current_pct']} of records carry a valid phone number this period.",
                     MARGIN, Inches(5.9), LEFT_W, Inches(0.5))

    _add_table(slide, ["Metric", "Current", "Change"], data["comparison"],
               ["metric", "current", "change"], Inches(1.95), color_key=(2, "dir"), left=RIGHT_LEFT, width=RIGHT_W)
    _callout(slide, "\U0001F511 " + data["score_note"], Inches(6.5), left=RIGHT_LEFT, width=RIGHT_W)

    if data.get("store_number_by_shop"):
        slide2 = _new_slide(prs)
        _section_title(slide2, 7, "Data Quality (KYC)", "7.1 Store Numbers Used by Location")
        rows, omitted = _top_n(data["store_number_by_shop"], 10)
        _add_table(slide2, ["Shop", "Unique Numbers", "Occurrences"], rows,
                   ["shop", "unique_numbers", "occurrences"], Inches(1.3))
        _truncation_note(slide2, omitted, Inches(6.5))
        _callout(slide2, "\U0001F4CB " + data["meeting_note"], Inches(6.9))
    else:
        _callout(slide, "\U0001F4CB " + data["meeting_note"], Inches(7.0), left=RIGHT_LEFT, width=RIGHT_W)


def _feedback_slides(prs, data):
    slide = _new_slide(prs)
    _section_title(slide, 8, "Customer Feedback")
    _textbox(slide, data["summary"], MARGIN, Inches(1.2), CONTENT_W, Inches(0.8), size=12, color=INK)
    _add_table(slide, ["Metric", "Current", "Previous", "Status"], data["comparison"],
               ["metric", "current", "previous", "status"], Inches(2.1), color_key=(3, "status_tone"))
    if data.get("target"):
        _callout(slide, "\U0001F3AF " + data["target"]["note"], Inches(4.4), kind=data["target"].get("status_tone", "context"))

    slide2 = _new_slide(prs)
    _section_title(slide2, 8, "Customer Feedback", "8.1 Store Breakdown — Feedback Responses")
    shops = [r for r in data["store_breakdown"] if r["shop"] != "TOTAL"][:8]
    _add_bar_chart(slide2, [r["shop"] for r in shops], [("Responses", [r["current_raw"] for r in shops])],
                   MARGIN, Inches(1.4), LEFT_W, Inches(3.9), horizontal=True)
    rows, omitted = _top_n(data["store_breakdown"], 10)
    _add_table(slide2, ["Shop", "Current", "Previous", "Change"], rows,
               ["shop", "current", "previous", "change"], Inches(1.4), color_key=(3, "dir"), left=RIGHT_LEFT, width=RIGHT_W)
    _truncation_note(slide2, omitted, Inches(6.0), left=RIGHT_LEFT, width=RIGHT_W)

    last_slide = slide2
    if data.get("feedback_links"):
        slide3 = _new_slide(prs)
        _section_title(slide3, 8, "Customer Feedback", "8.2 Feedback Link Targets by Location")
        link_rows, link_omitted = _top_n(data["feedback_links"], 8)
        _add_table(slide3, ["Shop", "Links Sent", "Online", "Achv %", "Status"], link_rows,
                   ["shop", "links_sent", "online", "achv_pct", "status"], Inches(1.3), color_key=(4, "status_tone"))
        _truncation_note(slide3, link_omitted, Inches(6.0))
        last_slide = slide3

    _callout(last_slide, "\U0001F4CB " + data["meeting_note"], Inches(6.5))


def _priorities_slide(prs, data):
    slide = _new_slide(prs)
    _section_title(slide, 9, "Summary & Key Notes")

    dept_labels = [("marketing", "\U0001F4E2 Marketing"), ("sales", "\U0001F4B0 Sales"),
                   ("production", "\U0001F4E6 Production"), ("data", "\U0001F5C4 Data")]
    quad_w = (CONTENT_W - Inches(0.2)) / 2
    quad_h = Inches(2.7)
    positions = [(MARGIN, Inches(1.2)), (MARGIN + quad_w + Inches(0.2), Inches(1.2)),
                 (MARGIN, Inches(1.2) + quad_h + Inches(0.2)), (MARGIN + quad_w + Inches(0.2), Inches(1.2) + quad_h + Inches(0.2))]

    for idx, ((key, label), (left, top)) in enumerate(zip(dept_labels, positions)):
        dept = data[key]
        box = slide.shapes.add_shape(1, left, top, quad_w, quad_h)
        box.fill.solid()
        box.fill.fore_color.rgb = CARD
        box.line.fill.background()
        accent = slide.shapes.add_shape(1, left, top, Inches(0.08), quad_h)
        accent.fill.solid()
        accent.fill.fore_color.rgb = CHART_COLORS[idx % len(CHART_COLORS)]
        accent.line.fill.background()

        tf = box.text_frame
        tf.word_wrap = True
        tf.margin_left = Inches(0.22)
        tf.margin_right = Inches(0.12)
        tf.margin_top = Inches(0.08)

        p0 = tf.paragraphs[0]
        r0 = p0.add_run()
        r0.text = label
        r0.font.size = Pt(13)
        r0.font.bold = True
        r0.font.color.rgb = INDIGO

        p1 = tf.add_paragraph()
        r1 = p1.add_run()
        r1.text = dept["summary"]
        r1.font.size = Pt(9)
        r1.font.italic = True
        r1.font.color.rgb = MUTED

        if dept.get("unavailable"):
            p2 = tf.add_paragraph()
            r2 = p2.add_run()
            r2.text = dept["note"]
            r2.font.size = Pt(9)
            r2.font.italic = True
            r2.font.color.rgb = MUTED
            continue

        for item in dept["items"][:4]:
            p = tf.add_paragraph()
            r = p.add_run()
            r.text = f"[{item['priority']}] {item['text']}"
            r.font.size = Pt(9)
            r.font.color.rgb = _PRIORITY_COLOR.get(item["priority"], INK)


def _closing_slide(prs, meta):
    slide = _new_slide(prs)
    _textbox(slide, "Denri Africa — Business Intelligence", MARGIN, Inches(3.3), CONTENT_W, Inches(0.5),
             size=18, bold=True, color=INDIGO, align=PP_ALIGN.CENTER)
    _textbox(slide, f"Generated {meta['generated_on']}", MARGIN, Inches(3.9), CONTENT_W, Inches(0.4),
             size=11, italic=True, color=MUTED, align=PP_ALIGN.CENTER)


def build_pptx(report: dict) -> io.BytesIO:
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H

    _title_slide(prs, report["meta"])
    _kpi_slide(prs, report["kpi_strip"], report["context_note"])
    _exec_summary_slides(prs, report["exec_summary"])
    _customer_metrics_slides(prs, report["customer_metrics"])
    _store_performance_slides(prs, report["store_performance"])
    _gender_performance_slides(prs, report["gender_performance"])
    _traffic_slide(prs, report["traffic"])
    _revenue_slides(prs, report["revenue_analysis"])
    _data_quality_slide(prs, report["data_quality"])
    _feedback_slides(prs, report["feedback"])
    _priorities_slide(prs, report["priorities"])
    _closing_slide(prs, report["meta"])

    buf = io.BytesIO()
    prs.save(buf)
    buf.seek(0)
    return buf
