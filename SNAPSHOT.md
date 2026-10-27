# Snapshot format

`marketing_snapshot.py` reads a marketing package and writes
`runs/dashboard/snapshot.json`. The dashboard only ever reads this file (or
builds the same structure in memory), so anything that writes it, in any
language, works with the page.

Rules that hold everywhere:

- **Missing is `null`, never `0`.** A day whose cost rows came back empty, a
  month with an unknown cost, or a campaign with no report yet stays `null`.
- **Times are UTC ISO 8601** with a `Z` (`2026-10-20T13:02:11Z`). Daily rows
  use the ad account's own calendar date (`date`).
- **Money is in `business.currency`**, as plain numbers.
- Free text is trimmed to 300 characters.

```jsonc
{
  "schema": "marketing-dashboard/snapshot@1",
  "generated_at": "2026-10-27T20:35:11Z",
  "generated_by": "daily-ad-report",      // the job or tool that wrote it
  "status": { "level": "ok | attention | problem | unknown", "headline": "..." },
  "business": {
    "name": "Northwind Candles", "package": "~/marketing/northwind",
    "currency": "USD", "timezone": "America/Chicago",
    "mode": "dry_run | live", "access_level": 0
  },
  "budget": {
    "owner_monthly_cap": 250, "contribution_share": 0.3,
    "launch_exception": { "approved": true, "total": 300, "start": "2026-10-06", "end": "2026-11-04" }
  },
  "report": {                              // the newest campaign report, or null
    "file": "runs/meta-daily/2026-10-20T130211Z.json",
    "checked_at": "2026-10-20T13:02:11Z", "verdict": "PASS", "count": 12
  },
  "campaigns": [{
    "id": "1202...", "name": "A · Autumn collection", "objective": "OUTCOME_TRAFFIC",
    "status": "ACTIVE", "effective_status": "ACTIVE",
    "start": "...Z", "end": "...Z",
    "cap": 300, "spend": 133.53, "remaining": 166.47,
    "pacing": { "days_total": 30.04, "days_elapsed": 14.33, "days_left": 15.71,
                "even_spend_to_date": 143.15, "per_day_to_finish": 10.6 },
    "totals": { "spend": 133.53, "impressions": 7365, "reach": 4081, "frequency": 1.8,
                "link_clicks": 124, "landing_views": 105, "ctr": 0.0168, "cpc": 1.08, "cpm": 18.13,
                "actions": { "offsite_conversion.fb_pixel_add_to_cart": 1 } },
    "daily": [{ "date": "2026-10-12", "spend": 9.47, "impressions": 474, "reach": 429,
                "link_clicks": 6, "landing_views": 5, "ctr": 0.0127, "cpc": 1.58, "gap": false }],
    "placements": [{ "label": "instagram feed", "spend": 62.76, "impressions": 3461,
                     "link_clicks": 58, "landing_views": 49, "ctr": 0.0168, "cpc": 1.08 }],
    "audience": [{ "age": "25-34", "gender": "female", "spend": 36.5, "impressions": 2014,
                   "link_clicks": 33, "landing_views": 28 }],
    "ads": [{ "id": "1202...", "name": "...", "effective_status": "ACTIVE", "issues": [] }],
    "problems": [], "data_gaps": ["2026-10-21"], "complete": true
  }],
  "weekly":    [{ "since": "2026-10-06", "until": "2026-10-12", "verdict": "PASS", "file": "..." }],
  "packets":   [{ "id": "2026-10-15-gift-guide", "status": "awaiting_owner", "needs_owner": true,
                  "updated": "...Z", "review_page": "packets/2026-10-15-gift-guide/review.html" }],
  "decisions": [{ "id": "...", "at": "...Z", "topic": "content", "owner_words": "...",
                  "approves_files": 9, "not_authorized": ["upload", "funding"], "expires": null }],
  "economics": [{ "month": "2026-09", "currency": "USD", "net_revenue": 4210, "costs": 2360,
                  "contribution": 1850, "ad_spend": 0, "net_after_ads": 1850, "missing": [] }],
  "activity":  [{ "job": "daily-ad-report", "at": "...Z", "verdict": "PASS", "text": "..." }],
  "warnings":  ["runs/meta-daily/x.json: unreadable (JSONDecodeError)"]
}
```

`ctr` is link clicks ÷ impressions (a fraction, not a percent). `reach` is
deduplicated by the platform: daily or segment reach never adds up to the total.

## What the builder reads

| Package path | Used for |
| --- | --- |
| `policy.yaml` | `business_name`, `currency`, `timezone`, `mode`, `access_level`, `budget` |
| `runs/meta-daily/*.json` | the newest file in `meta-report collect` format: `campaigns[]` with `readback`, `insights.{total,daily,placement,age_gender}`, `problems`, `data_gaps`, `lifetime_cap` |
| `runs/weekly/*.json` | closed performance windows: `time_range`, `verdict` |
| `runs/*/log.md` | activity: `- <time> <text>` or `<time> \| task=… \| status=… \| <text>` lines |
| `runs/<task>/*.json` | activity: run records with `task`, `checked_at_utc`, `verdict` or `status`, `next` or `summary` |
| `packets/*/manifest.json` | `status`; a status mentioning awaiting, blocked, owner or review counts as waiting |
| `decisions.json` | a list of `{id, at_utc, topic, owner_words, approves_files, not_authorized, expires_utc}` |
| `economics/YYYY-MM.yaml` | `net_revenue`, the six cost lines, `ad_spend` |

Files the builder can't read become `warnings`, never a crash.
