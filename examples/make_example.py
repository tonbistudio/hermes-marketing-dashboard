#!/usr/bin/env python3
"""Write a made-up marketing package ("Northwind Candles") for trying the dashboard.

  python3 examples/make_example.py [folder]     # default: examples/northwind-candles

The numbers are invented. The files have the same shape the Marketer agent's
tools write, so the snapshot builder and the dashboard treat them like real ones.
"""
from __future__ import annotations

import json
import random
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "northwind-candles"
BASE = date(2026, 10, 6)  # the dates below are written against this start
SHIFT = (date.today() - timedelta(days=15)) - BASE  # so the example always ends yesterday
START = BASE
DAYS = 14
CAMPAIGN = "120200000000000001"


def shift(text: str) -> str:
    return re.sub(r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)", lambda m: str(date.fromisoformat(m.group(0)) + SHIFT), text)


def write(rel: str, text: str) -> None:
    rel, text = shift(rel), shift(text)
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def row(spend: float, impressions: int, reach: int, clicks: int, landing: int, carts: int, purchases: int, **keys) -> dict:
    return {**keys, "spend": round(spend, 2), "impressions": impressions, "reach": reach,
            "frequency": round(impressions / reach, 2) if reach else None, "clicks": clicks + 9,
            "inline_link_clicks": clicks, "inline_link_click_ctr": round(clicks / impressions * 100, 4) if impressions else None,
            "cost_per_inline_link_click": round(spend / clicks, 4) if clicks else None,
            "cpm": round(spend / impressions * 1000, 4) if impressions else None, "landing_page_views": landing,
            "actions": {"link_click": clicks, "landing_page_view": landing, "offsite_conversion.fb_pixel_add_to_cart": carts,
                        "offsite_conversion.fb_pixel_purchase": purchases}}


def main() -> None:
    rnd = random.Random(7)
    write("policy.yaml", """business_name: Northwind Candles
mode: live
currency: USD
timezone: America/Chicago
access_level: 1
budget:
  launch_exception: {approved: true, total: 300, start: 2026-10-06, end: 2026-11-04}
  owner_monthly_cap: 250
  contribution_share: 0.30
  max_increase_pct: 20
campaigns:
  - id: A
    job: landing-page views to the autumn collection
    meta_campaign_id: "120200000000000001"
    lifetime_budget: 300
    placements: [facebook:feed, instagram:feed, instagram:story]
thresholds:
  approved: false
  rules: []
""")
    daily, totals = [], dict(spend=0.0, impressions=0, reach=0, clicks=0, landing=0, carts=0, purchases=0)
    for i in range(DAYS):
        d = START + timedelta(days=i)
        spend = round(rnd.uniform(8.5, 11.5), 2)
        imp = int(spend * rnd.uniform(48, 62))
        reach = int(imp * rnd.uniform(0.86, 0.93))
        clicks = int(imp * rnd.uniform(0.012, 0.024))
        landing = int(clicks * rnd.uniform(0.84, 0.95))
        carts = int(landing * rnd.uniform(0.05, 0.12))
        purchases = int(carts * rnd.uniform(0.2, 0.5))
        if i == 9:  # a data gap: Meta returned 0 cost rows while clicks look normal
            r = row(0, 0, 0, clicks, landing, carts, purchases, date_start=str(d), date_stop=str(d))
        else:
            r = row(spend, imp, reach, clicks, landing, carts, purchases, date_start=str(d), date_stop=str(d))
        daily.append(r)
        for k, v in zip(("spend", "impressions", "reach", "clicks", "landing", "carts", "purchases"),
                        (spend, imp, reach, clicks, landing, carts, purchases)):
            totals[k] += v
    totals["reach"] = int(totals["reach"] * 0.62)  # reach is deduplicated across days
    total = row(totals["spend"], totals["impressions"], totals["reach"], totals["clicks"], totals["landing"],
                totals["carts"], totals["purchases"], date_start=str(START), date_stop=str(START + timedelta(days=DAYS - 1)))
    shares = {("facebook", "feed"): 0.31, ("instagram", "feed"): 0.47, ("instagram", "story"): 0.22}
    placement = [row(totals["spend"] * s, int(totals["impressions"] * s), int(totals["reach"] * s), int(totals["clicks"] * s),
                     int(totals["landing"] * s), int(totals["carts"] * s), int(totals["purchases"] * s),
                     publisher_platform=p, platform_position=pos) for (p, pos), s in shares.items()]
    audience = []
    for age, a in (("25-34", 0.38), ("35-44", 0.41), ("45-54", 0.21)):
        for gender, g in (("female", 0.72), ("male", 0.25), ("unknown", 0.03)):
            s = a * g
            audience.append(row(totals["spend"] * s, int(totals["impressions"] * s), int(totals["reach"] * s),
                                int(totals["clicks"] * s), int(totals["landing"] * s), 0, 0, age=age, gender=gender))
    checked = datetime(2026, 10, 20, 13, 2, 11, tzinfo=timezone.utc)
    report = {
        "checked_at_utc": checked.strftime("%Y-%m-%dT%H:%M:%SZ"), "account": {"id": "act_100000000000001", "currency": "USD"},
        "api_version": "v26.0", "verdict": "PASS",
        "campaigns": [{
            "campaign_id": CAMPAIGN, "checked_at_utc": checked.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "readback": {
                "campaign": {"id": CAMPAIGN, "objective": "OUTCOME_TRAFFIC", "status": "ACTIVE", "effective_status": "ACTIVE",
                             "start_time": None, "stop_time": None, "name": "A · Autumn collection", "spend_cap": 30000},
                "adsets": [{"id": "120200000000000002", "status": "ACTIVE", "effective_status": "ACTIVE",
                            "start_time": "2026-10-06T00:00:00-0500", "end_time": "2026-11-04T23:59:00-0600",
                            "name": "A · US 25-54", "lifetime_budget": 30000, "daily_budget": None}],
                "ads": [{"id": "120200000000000003", "status": "ACTIVE", "effective_status": "ACTIVE",
                         "adset_id": "120200000000000002", "name": "A · Feed + Stories v1", "issues": []}],
            },
            "insights": {"total": [total], "daily": daily, "placement": placement, "age_gender": audience},
            "complete": True, "problems": [], "data_gaps": [str(START + timedelta(days=9))], "lifetime_cap": 300.0,
        }],
    }
    write(f"runs/meta-daily/{checked:%Y-%m-%dT%H%M%SZ}.json", json.dumps(report, indent=1))
    write("runs/meta-daily/log.md", "\n".join(
        f"- {START + timedelta(days=i + 1)}T13:02 PASS daily report sent; spend on pace" for i in range(DAYS)) + "\n")
    write("runs/weekly/2026-10-06_2026-10-12.json", json.dumps(
        {"checked_at_utc": "2026-10-14T13:00:00Z", "time_range": {"since": "2026-10-06", "until": "2026-10-12"},
         "campaigns": [], "verdict": "PASS"}, indent=1))
    write("runs/weekly-performance/log.md", "- 2026-10-14T13:00 REPORT_ONLY 1 rule hit (frequency under threshold; thresholds not approved)\n")
    write("runs/editorial/log.md", "- 2026-10-15T14:00 DRAFT packet 2026-10-15-gift-guide ready for review\n")
    write("decisions.json", json.dumps([
        {"id": "2026-10-03-launch-content", "at_utc": "2026-10-03T16:20:00Z", "topic": "content",
         "owner_words": "Approved: the autumn ad as shown, Feed and Stories. Content only.",
         "approves_files": {f"packets/2026-10-02-autumn/file-{i}": "sha256:0" for i in range(9)},
         "not_authorized": ["upload", "funding", "launch"], "expires_utc": None},
        {"id": "2026-10-05-launch-go", "at_utc": "2026-10-05T22:05:00Z", "topic": "launch",
         "owner_words": "Go: launch campaign A, $300 lifetime, ends Nov 4.",
         "approves_files": {}, "not_authorized": ["budget increase", "new audiences"], "expires_utc": "2026-10-07T22:05:00Z"},
    ], indent=1))
    write("packets/2026-10-02-autumn/manifest.json", json.dumps({"packet_id": "2026-10-02-autumn", "status": "approved_launched"}))
    write("packets/2026-10-15-gift-guide/manifest.json", json.dumps({"packet_id": "2026-10-15-gift-guide", "status": "awaiting_owner"}))
    write("packets/2026-10-15-gift-guide/review.html", "<!doctype html><title>Gift guide packet</title><p>Example review page.</p>\n")
    write("economics/2026-09.yaml", """month: 2026-09
currency: USD
net_revenue: 4210.00
product_and_fulfillment: 1630.00
shipping_paid: 410.00
payment_fees: 135.00
fault_and_reprint: 40.00
per_customer_tool_costs: 25.00
attributable_overhead: 120.00
ad_spend: 0
source_notes: "invented example figures"
""")
    write("economics/2026-10.yaml", """month: 2026-10
currency: USD
net_revenue: 3120.00
product_and_fulfillment: null
shipping_paid: 330.00
payment_fees: 101.00
fault_and_reprint: null
per_customer_tool_costs: 22.00
attributable_overhead: 120.00
ad_spend: 141.40
source_notes: "month not closed: product cost and reprints not in yet"
""")
    print(ROOT)


if __name__ == "__main__":
    main()
