"""Section 9 - department-level notes on what needs attention this period.

Deliberately does not recompute thresholds from scratch: it reads the signals
every other section already derived (evaluate_metrics' ratio/dir, store and
traffic rows' raw deltas, data quality's comparison rows, feedback's status
tones) and routes them to whichever department actually owns that lever. One
threshold definition per metric, reused everywhere it appears.
"""

_PRIORITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "WIN": 3}


def _item(priority: str, text: str) -> dict:
    return {"priority": priority, "text": text}


def _severity(ratio: float, critical_at: float = 2.0) -> str:
    return "CRITICAL" if ratio >= critical_at else "HIGH"


def _summarize(items: list, dept: str) -> str:
    if not items:
        return f"No material {dept.lower()} issues flagged for this period."

    counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "WIN": 0}
    for i in items:
        counts[i["priority"]] += 1

    parts = []
    if counts["CRITICAL"]:
        parts.append(f"{counts['CRITICAL']} critical")
    if counts["HIGH"]:
        parts.append(f"{counts['HIGH']} high-priority")
    if counts["MEDIUM"]:
        parts.append(f"{counts['MEDIUM']} to watch")
    if counts["WIN"]:
        parts.append(f"{counts['WIN']} win(s) to reinforce")

    return f"{len(items)} item(s) flagged for {dept} this period: " + ", ".join(parts) + "."


def _sort_items(items: list) -> list:
    return sorted(items, key=lambda i: _PRIORITY_ORDER[i["priority"]])


def build_marketing_notes(evaluated: list, gender_section: dict, feedback_section: dict, period: dict) -> dict:
    items = []
    by_metric = {e["metric"]: e for e in evaluated}

    rev = by_metric["Revenue"]
    if rev["ratio"] >= 1:
        if rev["dir"] == "down":
            items.append(_item(_severity(rev["ratio"]), f"Revenue declined {rev['magnitude']} vs {period['compared_to']} - review demand and acquisition drivers."))
        elif rev["dir"] == "up":
            items.append(_item("WIN", f"Revenue grew {rev['magnitude']} vs {period['compared_to']} - capture what drove it for the next campaign."))

    new_m = by_metric["New"]
    if new_m["ratio"] >= 1 and new_m["dir"] == "down":
        items.append(_item(_severity(new_m["ratio"]), f"New customer acquisition is down {new_m['magnitude']} vs {period['compared_to']} - review marketing/acquisition channels."))

    for g in gender_section["overall"]:
        if abs(g["change_raw"]) >= 5:
            direction_word = "rose" if g["change_raw"] > 0 else "fell"
            items.append(_item("MEDIUM", f"{g['gender']} share {direction_word} {abs(g['change_raw']):.1f} pp vs {period['compared_to']} - confirm this matches campaign targeting intent."))

    overall_exp = next((r for r in feedback_section["comparison"] if r["metric"] == "Overall Experience"), None)
    if overall_exp and overall_exp["status_tone"] != "good":
        priority = "HIGH" if overall_exp["status_tone"] == "critical" else "MEDIUM"
        items.append(_item(priority, f"Overall Experience score is {overall_exp['status']} ({overall_exp['current']}/5) - brand-perception risk worth a marketing review."))

    target = feedback_section.get("target")
    if target and target["status_tone"] in ("warning", "critical"):
        priority = "CRITICAL" if target["status_tone"] == "critical" else "HIGH"
        items.append(_item(priority, target["note"]))

    links = [r for r in feedback_section.get("feedback_links", []) if r["shop"] != "TOTAL" and r["sent_raw"] >= 10]
    if links:
        worst_link = min(links, key=lambda r: r["achv_pct_raw"])
        if worst_link["achv_pct_raw"] < 50:
            items.append(_item("HIGH", f"{worst_link['shop']}'s online feedback link conversion is {worst_link['achv_pct']} ({worst_link['online']} of {worst_link['links_sent']} sent) - lowest of any shop with meaningful volume."))

    items = _sort_items(items)
    return {"summary": _summarize(items, "Marketing"), "items": items}


def build_sales_notes(evaluated: list, store_section: dict, traffic_section: dict, period: dict) -> dict:
    items = []
    by_metric = {e["metric"]: e for e in evaluated}

    shops = [r for r in store_section["rows"] if r["shop"] != "TOTAL" and r["change_pct_raw"] is not None]
    if shops:
        worst = min(shops, key=lambda r: r["change_pct_raw"])
        best = max(shops, key=lambda r: r["change_pct_raw"])
        if worst["change_pct_raw"] <= -10:
            priority = "CRITICAL" if worst["change_pct_raw"] <= -20 else "HIGH"
            items.append(_item(priority, f"{worst['shop']} revenue is down {abs(worst['change_pct_raw']):.1f}% vs {period['compared_to']} - review with the store team."))
        if best["change_pct_raw"] >= 10 and best["shop"] != worst["shop"]:
            items.append(_item("WIN", f"{best['shop']} revenue is up {best['change_pct_raw']:.1f}% vs {period['compared_to']} - identify and replicate what's working."))

    rr = by_metric["Repeat Rate"]
    if rr["ratio"] >= 1 and rr["dir"] == "down":
        items.append(_item(_severity(rr["ratio"]), f"Repeat rate is down {rr['magnitude']} vs {period['compared_to']} - review loyalty/retention tactics."))

    avg_spend = by_metric["Avg Spend/Customer"]
    if avg_spend["ratio"] >= 1 and avg_spend["dir"] == "down":
        items.append(_item("MEDIUM", f"Avg spend/customer is down {avg_spend['magnitude']} vs {period['compared_to']} - review upsell/cross-sell at checkout."))

    traffic_shops = [r for r in traffic_section["rows"] if r["shop"] != "TOTAL" and r["walkin_total_raw"] > 0]
    if traffic_shops:
        worst_conv = min(traffic_shops, key=lambda r: r["conv_rate_raw"])
        if worst_conv["conv_rate_raw"] < 50:
            priority = "HIGH" if worst_conv["conv_rate_raw"] < 35 else "MEDIUM"
            items.append(_item(priority, f"{worst_conv['shop']} conversion rate is {worst_conv['conv_rate']} - coach staff on walk-in-to-sale conversion."))

    items = _sort_items(items)
    return {"summary": _summarize(items, "Sales"), "items": items}


def build_data_notes(data_quality_section: dict, traffic_section: dict, customer_metrics_section: dict, period: dict) -> dict:
    items = []
    comparison = {r["metric"]: r for r in data_quality_section["comparison"]}

    invalid = comparison.get("Invalid")
    if invalid and invalid["current_pct"] != "-":
        pct = float(invalid["current_pct"].rstrip("%"))
        if pct >= 2:
            items.append(_item("HIGH" if pct >= 5 else "MEDIUM", f"Invalid phone entries are at {invalid['current_pct']} this period - retrain staff on phone capture at checkout."))

    na = comparison.get("N/A Phones")
    if na and na["current_pct"] != "-":
        pct = float(na["current_pct"].rstrip("%"))
        if pct >= 2:
            items.append(_item("HIGH" if pct >= 5 else "MEDIUM", f"{na['current_pct']} of records have no phone captured - review data entry compliance."))

    if data_quality_section["store_number_by_shop"]:
        shops_list = ", ".join(r["shop"] for r in data_quality_section["store_number_by_shop"])
        items.append(_item("MEDIUM", f"Shop's own number was used instead of a customer's at: {shops_list} - remind staff to capture the real customer number."))

    if traffic_section.get("data_gap_note"):
        items.append(_item("MEDIUM", traffic_section["data_gap_note"]))

    if traffic_section.get("data_anomaly_note"):
        items.append(_item("MEDIUM", traffic_section["data_anomaly_note"]))

    untagged = next((c for c in customer_metrics_section["channels"] if c["channel"] == "Untagged / Other"), None)
    if untagged and untagged["note"]:
        items.append(_item("MEDIUM", f"{untagged['share']} of transactions this period have no Customer Type tag - this affects channel-mix accuracy across every section of this report."))

    items = _sort_items(items)
    return {"summary": _summarize(items, "Data"), "items": items}


def build_production_notes() -> dict:
    return {
        "summary": "No product/inventory data source is wired in yet.",
        "items": [],
        "unavailable": True,
        "note": (
            "None of the connected sheets (Shops, Footfall, Revamped feedback) track stock, inventory, "
            "or manufacturing - once a data source for that exists, this section will populate automatically."
        ),
    }


def build_section(
    evaluated: list, store_section: dict, gender_section: dict, traffic_section: dict,
    data_quality_section: dict, feedback_section: dict, customer_metrics_section: dict, period: dict,
) -> dict:
    return {
        "marketing": build_marketing_notes(evaluated, gender_section, feedback_section, period),
        "sales": build_sales_notes(evaluated, store_section, traffic_section, period),
        "production": build_production_notes(),
        "data": build_data_notes(data_quality_section, traffic_section, customer_metrics_section, period),
    }
