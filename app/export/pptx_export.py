"""Renders the same report_data dict served by /api/report into a .pptx deck.

Reuses the web dashboard's already-computed, already-formatted data verbatim -
no metric is recalculated here. Unlike the docx/xlsx exports (which are
reference documents and show everything), a slide has to stay readable at a
glance: wide tables are trimmed to their most decision-relevant columns and
long tables are capped to a top-N + TOTAL, with a note pointing to the full
detail in the Word/Excel export.
"""
import io

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Pt

# Palette mirrors the web dashboard's validated light-mode tokens and the
# docx/xlsx exports, so all three outputs read as the same product.
HEADER_FILL = RGBColor(0x1F, 0x38, 0x64)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
TABLE_HEADER_FILL = RGBColor(0xDC, 0xE3, 0xEE)
PAGE_BG = RGBColor(0xF9, 0xF9, 0xF7)
INK = RGBColor(0x0B, 0x0B, 0x0B)
MUTED = RGBColor(0x89, 0x87, 0x81)
GOOD = RGBColor(0x0C, 0xA3, 0x0C)
WARNING = RGBColor(0xB8, 0x86, 0x00)
CRITICAL = RGBColor(0xD0, 0x3B, 0x3B)
NEUTRAL = RGBColor(0x52, 0x51, 0x4E)
BLUE = RGBColor(0x2A, 0x78, 0xD6)

_DIR_COLOR = {"up": GOOD, "down": CRITICAL, "neutral": NEUTRAL}
_TONE_COLOR = {"good": GOOD, "warning": WARNING, "critical": CRITICAL, "neutral": NEUTRAL}
_PRIORITY_COLOR = {"CRITICAL": CRITICAL, "HIGH": WARNING, "MEDIUM": NEUTRAL, "WIN": GOOD}
PERIOD_TITLES = {"day": "DAILY", "week": "WEEKLY", "month": "MONTHLY"}

SLIDE_W, SLIDE_H = Inches(13.333), Inches(7.5)
MARGIN = Inches(0.45)
CONTENT_W = SLIDE_W - 2 * MARGIN


def _new_slide(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank layout
    bg = slide.shapes.add_shape(1, 0, 0, SLIDE_W, SLIDE_H)  # MSO_SHAPE.RECTANGLE == 1
    bg.fill.solid()
    bg.fill.fore_color.rgb = PAGE_BG
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
    _textbox(slide, f"{number}. {title}", MARGIN, Inches(0.3), CONTENT_W, Inches(0.6), size=24, bold=True, color=HEADER_FILL)
    if sub:
        _textbox(slide, sub, MARGIN, Inches(0.9), CONTENT_W, Inches(0.5), size=12, italic=True, color=MUTED)


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
        para.font.color.rgb = INK

    for r, row in enumerate(rows, start=1):
        is_total = str(row.get("shop", row.get("metric", ""))).strip().upper() == "TOTAL"
        values = _pick(row, keys)
        for c, val in enumerate(values):
            cell = table.cell(r, c)
            cell.text = val
            cell.fill.solid()
            cell.fill.fore_color.rgb = WHITE
            para = cell.text_frame.paragraphs[0]
            para.font.size = Pt(9.5)
            para.font.bold = is_total
            if color_key and c == color_key[0]:
                tone = row.get(color_key[1])
                color = _DIR_COLOR.get(tone) or _TONE_COLOR.get(tone)
                if color:
                    para.font.color.rgb = color

    return shape


def _truncation_note(slide, omitted, top):
    if omitted > 0:
        _textbox(slide, f"+ {omitted} more row(s) - see the full breakdown in the .docx/.xlsx export.",
                 MARGIN, top, CONTENT_W, Inches(0.35), size=10, italic=True, color=MUTED)


def _callout(slide, text, top, kind="context"):
    color = {"critical": CRITICAL, "warning": WARNING, "good": GOOD}.get(kind, BLUE)
    box = slide.shapes.add_shape(1, MARGIN, top, CONTENT_W, Inches(0.5))
    box.fill.solid()
    box.fill.fore_color.rgb = RGBColor(0xF2, 0xF2, 0xF2)
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


# --- Slides ---

def _title_slide(prs, meta):
    slide = _new_slide(prs)
    band = slide.shapes.add_shape(1, 0, Inches(2.6), SLIDE_W, Inches(2.3))
    band.fill.solid()
    band.fill.fore_color.rgb = HEADER_FILL
    band.line.fill.background()

    title = f"{PERIOD_TITLES.get(meta['period_type'], '')} SALES PERFORMANCE REPORT"
    _textbox(slide, title, MARGIN, Inches(2.85), CONTENT_W, Inches(0.8), size=32, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    _textbox(slide, f"{meta['period_label']} | {meta['date_range']} ({meta['days']} day(s))",
             MARGIN, Inches(3.65), CONTENT_W, Inches(0.5), size=16, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    _textbox(slide, f"Compared to: {meta['compared_to']}", MARGIN, Inches(4.15), CONTENT_W, Inches(0.4),
             size=12, italic=True, color=RGBColor(0xE0, 0xE0, 0xE0), align=PP_ALIGN.CENTER)
    _textbox(slide, "Denri Africa — Business Intelligence", MARGIN, Inches(5.3), CONTENT_W, Inches(0.4),
             size=13, color=MUTED, align=PP_ALIGN.CENTER)
    _textbox(slide, f"Generated {meta['generated_on']}", MARGIN, Inches(5.7), CONTENT_W, Inches(0.4),
             size=10, italic=True, color=MUTED, align=PP_ALIGN.CENTER)


def _kpi_slide(prs, kpi_strip, context_note):
    slide = _new_slide(prs)
    _textbox(slide, "Key Performance Indicators", MARGIN, Inches(0.3), CONTENT_W, Inches(0.6), size=22, bold=True, color=HEADER_FILL)

    n = len(kpi_strip)
    card_w = (CONTENT_W - Inches(0.2) * (n - 1)) / n
    top = Inches(1.2)
    for i, card in enumerate(kpi_strip):
        left = MARGIN + i * (card_w + Inches(0.2))
        box = slide.shapes.add_shape(1, left, top, card_w, Inches(1.9))
        box.fill.solid()
        box.fill.fore_color.rgb = TABLE_HEADER_FILL
        box.line.fill.background()
        tf = box.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = Inches(0.08)

        p0 = tf.paragraphs[0]
        r0 = p0.add_run()
        r0.text = card["label"]
        r0.font.size = Pt(11)
        r0.font.color.rgb = MUTED

        p1 = tf.add_paragraph()
        r1 = p1.add_run()
        r1.text = card["value"]
        r1.font.size = Pt(18)
        r1.font.bold = True
        r1.font.color.rgb = INK

        p2 = tf.add_paragraph()
        r2 = p2.add_run()
        r2.text = card["sub"]
        r2.font.size = Pt(10)
        r2.font.bold = True
        r2.font.color.rgb = _DIR_COLOR.get(card["tone"], NEUTRAL)

    _callout(slide, context_note, Inches(3.5))


def _exec_summary_slides(prs, data):
    slide = _new_slide(prs)
    _section_title(slide, 1, "Executive Summary")
    _textbox(slide, data["narrative"], MARGIN, Inches(1.2), CONTENT_W, Inches(1.0), size=12, color=NEUTRAL)
    _add_table(slide, ["Metric", "Current", "Previous", "Change"], data["metrics"],
               ["metric", "current", "previous", "change"], Inches(2.3), color_key=(3, "dir"))

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
    _textbox(slide, data["summary"], MARGIN, Inches(1.2), CONTENT_W, Inches(0.8), size=12, color=NEUTRAL)
    _add_table(slide, ["Metric", "Current", "Previous", "Change"], data["comparison"],
               ["metric", "current", "previous", "change"], Inches(2.1), color_key=(3, "dir"))
    _add_table(slide, ["Purchase Frequency", "Count", "%", "Read"], data["frequency"],
               ["band", "count", "pct", "read"], Inches(4.6))

    slide2 = _new_slide(prs)
    _section_title(slide2, 2, "Customer Metrics", "2.2 Channel Overview")
    _add_table(slide2, ["Channel", "Customers", "Share", "Avg Spend", "Note"], data["channels"],
               ["channel", "customers", "share", "avg_spend", "note"], Inches(1.3))
    _callout(slide2, "\U0001F4CB " + data["meeting_note"], Inches(4.2))


def _store_performance_slides(prs, data):
    slide = _new_slide(prs)
    _section_title(slide, 3, "Store Performance")
    _textbox(slide, data["summary"], MARGIN, Inches(1.2), CONTENT_W, Inches(0.8), size=12, color=NEUTRAL)
    rows, omitted = _top_n(data["rows"], 8)
    _add_table(slide, ["Shop", "Current", "Change %", "New", "Repeat", "Repeat Rate"], rows,
               ["shop", "current", "change_pct", "new", "repeat", "repeat_rate"], Inches(2.1), color_key=(2, "dir"))
    _truncation_note(slide, omitted, Inches(6.9))

    slide2 = _new_slide(prs)
    _section_title(slide2, 3, "Store Performance", "3.1 Channel Mix by Location")
    mix_rows, mix_omitted = _top_n(data["channel_mix"], 8)
    _add_table(slide2, ["Shop", "Walk-in", "Online", "Activation", "Online %"], mix_rows,
               ["shop", "walkin", "online", "activation", "online_pct"], Inches(1.3))
    _truncation_note(slide2, mix_omitted, Inches(6.0))

    if data.get("monthly_retention"):
        slide3 = _new_slide(prs)
        _section_title(slide3, 3, "Store Performance", "3.2 Monthly Customer Retention by Location")
        ret_rows, ret_omitted = _top_n(data["monthly_retention"], 8)
        _add_table(slide3, ["Shop", "Current", "Previous", "Repeat Rate", "Retention Rate"], ret_rows,
                   ["shop", "current", "previous", "repeat_rate", "retention_rate"], Inches(1.3))
        _truncation_note(slide3, ret_omitted, Inches(6.0))

    slide_last = slide3 if data.get("monthly_retention") else slide
    _callout(slide_last, "\U0001F4CB " + data["meeting_note"], Inches(6.5))


def _gender_performance_slides(prs, data):
    slide = _new_slide(prs)
    _section_title(slide, 4, "Gender Performance Analysis")
    _textbox(slide, data["summary"], MARGIN, Inches(1.2), CONTENT_W, Inches(0.8), size=12, color=NEUTRAL)
    if data.get("ratio"):
        _textbox(slide, f"Ratio: {data['ratio']['ratio_text']}", MARGIN, Inches(2.0), CONTENT_W, Inches(0.4), size=13, bold=True, color=BLUE)
    _add_table(slide, ["Gender", "Count", "%", "Change"], data["overall"],
               ["gender", "count", "pct", "change"], Inches(2.6), color_key=(3, "dir"))

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
    _textbox(slide, data["summary"], MARGIN, Inches(1.2), CONTENT_W, Inches(0.8), size=12, color=NEUTRAL)
    top = Inches(2.1)
    if data.get("data_gap_note"):
        _callout(slide, "⚠ " + data["data_gap_note"], top, kind="warning")
        top += Inches(0.6)
    rows, omitted = _top_n(data["rows"], 8)
    _add_table(slide, ["Shop", "Walk-in Total", "Conv. Rate", "Online", "Total Customers"], rows,
               ["shop", "walkin_total", "conv_rate", "online", "total_customers"], top)
    _truncation_note(slide, omitted, top + Inches(0.32 * (len(rows) + 1) + 0.1))
    _callout(slide, "\U0001F4CB " + data["meeting_note"], Inches(6.9))


def _revenue_slides(prs, data):
    slide = _new_slide(prs)
    _section_title(slide, 6, "Revenue Analysis")
    _textbox(slide, data["summary"], MARGIN, Inches(1.1), CONTENT_W, Inches(0.8), size=12, color=NEUTRAL)

    bridge = data["bridge"]
    if len(bridge) >= 2:
        chart_data = CategoryChartData()
        chart_data.categories = [row["period"] for row in bridge]
        chart_data.add_series("Revenue (KES)", [row["revenue_raw"] for row in bridge])
        graphic_frame = slide.shapes.add_chart(
            XL_CHART_TYPE.LINE_MARKERS, MARGIN, Inches(2.0), CONTENT_W, Inches(4.8), chart_data
        )
        chart = graphic_frame.chart
        chart.has_legend = False
        chart.has_title = True
        chart.chart_title.text_frame.text = "6.1 Revenue Bridge"

    slide2 = _new_slide(prs)
    _section_title(slide2, 6, "Revenue Analysis", "Key Metrics")
    _add_table(slide2, ["Metric", "Current", "Previous", "Change"], data["comparison"],
               ["metric", "current", "previous", "change"], Inches(1.3), color_key=(3, "dir"))
    _callout(slide2, "\U0001F4CB " + data["meeting_note"], Inches(5.0))


def _data_quality_slide(prs, data):
    slide = _new_slide(prs)
    _section_title(slide, 7, "Data Quality (KYC)")
    _textbox(slide, data["summary"], MARGIN, Inches(1.2), CONTENT_W, Inches(0.8), size=12, color=NEUTRAL)
    _add_table(slide, ["Metric", "Current", "Previous", "Change"], data["comparison"],
               ["metric", "current", "previous", "change"], Inches(2.1), color_key=(3, "dir"))
    _callout(slide, "\U0001F511 " + data["score_note"], Inches(4.8))
    _callout(slide, "\U0001F4CB " + data["meeting_note"], Inches(5.5))

    if data.get("store_number_by_shop"):
        slide2 = _new_slide(prs)
        _section_title(slide2, 7, "Data Quality (KYC)", "7.1 Store Numbers Used by Location")
        rows, omitted = _top_n(data["store_number_by_shop"], 10)
        _add_table(slide2, ["Shop", "Unique Numbers", "Occurrences"], rows,
                   ["shop", "unique_numbers", "occurrences"], Inches(1.3))
        _truncation_note(slide2, omitted, Inches(6.5))


def _feedback_slides(prs, data):
    slide = _new_slide(prs)
    _section_title(slide, 8, "Customer Feedback")
    _textbox(slide, data["summary"], MARGIN, Inches(1.2), CONTENT_W, Inches(0.8), size=12, color=NEUTRAL)
    _add_table(slide, ["Metric", "Current", "Previous", "Status"], data["comparison"],
               ["metric", "current", "previous", "status"], Inches(2.1), color_key=(3, "status_tone"))
    if data.get("target"):
        _callout(slide, "\U0001F3AF " + data["target"]["note"], Inches(4.4), kind=data["target"].get("status_tone", "context"))

    slide2 = _new_slide(prs)
    _section_title(slide2, 8, "Customer Feedback", "8.1 Store Breakdown")
    rows, omitted = _top_n(data["store_breakdown"], 10)
    _add_table(slide2, ["Shop", "Current", "Previous", "Change"], rows,
               ["shop", "current", "previous", "change"], Inches(1.3), color_key=(3, "dir"))
    _truncation_note(slide2, omitted, Inches(6.5))

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

    for (key, label), (left, top) in zip(dept_labels, positions):
        dept = data[key]
        box = slide.shapes.add_shape(1, left, top, quad_w, quad_h)
        box.fill.solid()
        box.fill.fore_color.rgb = TABLE_HEADER_FILL
        box.line.fill.background()
        tf = box.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = Inches(0.12)
        tf.margin_top = Inches(0.08)

        p0 = tf.paragraphs[0]
        r0 = p0.add_run()
        r0.text = label
        r0.font.size = Pt(13)
        r0.font.bold = True
        r0.font.color.rgb = HEADER_FILL

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
             size=18, bold=True, color=HEADER_FILL, align=PP_ALIGN.CENTER)
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
