from datetime import datetime

from flask import Blueprint, jsonify, render_template, request, send_file

from app.data.feedback import load_feedback_by_shop, load_feedback_daily, load_feedback_links
from app.data.footfall import get_footfall_gaps, load_footfall_df
from app.data.shops import load_shops_df
from app.export.docx_export import build_docx
from app.export.pptx_export import build_pptx
from app.export.xlsx_export import build_xlsx
from app.metrics.executive_summary import build_report
from app.sheets_client import clear_cache

bp = Blueprint("main", __name__)


class BadRequest(Exception):
    def __init__(self, message):
        self.message = message


def _parse_period_args():
    period_type = request.args.get("period", "week")
    if period_type not in ("day", "week", "month"):
        raise BadRequest("period must be one of day, week, month")

    date_str = request.args.get("date")
    ref_date = None
    if date_str:
        try:
            ref_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            raise BadRequest("date must be YYYY-MM-DD")

    return period_type, ref_date


def _load_report():
    """Shared by /api/report and both export routes, so the exported file is
    always built from exactly the same data and logic as what's on screen."""
    period_type, ref_date = _parse_period_args()

    df = load_shops_df()
    footfall_df = load_footfall_df()
    footfall_gaps = get_footfall_gaps()
    feedback_daily_df = load_feedback_daily()
    feedback_by_shop_df = load_feedback_by_shop()
    feedback_links_df = load_feedback_links()

    return build_report(
        df, period_type, ref_date, footfall_df, footfall_gaps,
        feedback_daily_df, feedback_by_shop_df, feedback_links_df,
    )


def _export_filename(report: dict, ext: str) -> str:
    meta = report["meta"]
    return f"Denri_{meta['period_type'].capitalize()}_{meta['start']}_to_{meta['end']}.{ext}"


@bp.route("/")
def dashboard():
    return render_template("dashboard.html")


@bp.route("/api/report")
def api_report():
    try:
        report = _load_report()
    except BadRequest as e:
        return jsonify({"error": e.message}), 400
    return jsonify(report)


@bp.route("/api/export/docx")
def export_docx():
    try:
        report = _load_report()
    except BadRequest as e:
        return jsonify({"error": e.message}), 400

    buf = build_docx(report)
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=_export_filename(report, "docx"),
    )


@bp.route("/api/export/xlsx")
def export_xlsx():
    try:
        report = _load_report()
    except BadRequest as e:
        return jsonify({"error": e.message}), 400

    buf = build_xlsx(report)
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=_export_filename(report, "xlsx"),
    )


@bp.route("/api/export/pptx")
def export_pptx():
    try:
        report = _load_report()
    except BadRequest as e:
        return jsonify({"error": e.message}), 400

    buf = build_pptx(report)
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        as_attachment=True,
        download_name=_export_filename(report, "pptx"),
    )


@bp.route("/api/refresh", methods=["GET", "POST"])
def api_refresh():
    clear_cache()
    load_shops_df(force_refresh=True)
    load_footfall_df(force_refresh=True)
    load_feedback_daily(force_refresh=True)
    return jsonify({"status": "refreshed"})
