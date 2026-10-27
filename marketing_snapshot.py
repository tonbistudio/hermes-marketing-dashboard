#!/usr/bin/env python3
"""marketing-snapshot: one JSON summary of a marketing package, for the dashboard.

Reads a marketing package folder (policy.yaml, runs/, decisions.json, packets/,
economics/) and writes runs/dashboard/snapshot.json. It only reads the package
and writes that one derived file; it never contacts an ad platform.

  python3 marketing_snapshot.py <package> [--write] [--by JOB]

Missing data stays missing: an absent report or figure is null, never 0.
The schema is documented in SNAPSHOT.md beside this file.

Python 3.9+, stdlib only (PyYAML, or Hermes's hermes_yaml, for YAML files).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "marketing-dashboard/snapshot@1"
SNAPSHOT_REL = Path("runs") / "dashboard" / "snapshot.json"
STALE_REPORT_HOURS = 36
ECONOMICS_COSTS = ("product_and_fulfillment", "shipping_paid", "payment_fees", "fault_and_reprint",
                   "per_customer_tool_costs", "attributable_overhead")
# Packet statuses are free text the agent writes ("awaiting_owner", "AWAITING_OWNER_CONTENT_REVIEW", ...).
OWNER_STATUS = re.compile(r"await|block|owner|review|unreadable", re.I)
# Run folders that hold data, not run records.
DATA_RUNS = {"meta-daily", "weekly", "dashboard"}
MAX_TEXT = 300


def yaml_module() -> Any:
    """PyYAML, else Hermes's own hermes_yaml (Hermes's cron Python ships ruamel, not PyYAML)."""
    try:
        import yaml
        return yaml
    except ImportError:
        pass
    try:
        import hermes_yaml
        return hermes_yaml
    except ImportError:
        pass
    for root in (os.environ.get("HERMES_AGENT_DIR"), str(Path.home() / ".hermes" / "hermes-agent")):
        if root and (Path(root) / "hermes_yaml.py").is_file():
            sys.path.append(root)
            try:
                import hermes_yaml
                return hermes_yaml
            except ImportError:
                sys.path.remove(root)
    try:
        from ruamel.yaml import YAML

        class _Ruamel:
            @staticmethod
            def safe_load(text: str) -> Any:
                return YAML(typ="safe", pure=True).load(text)
        return _Ruamel
    except ImportError:
        return None


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_time(value: Any) -> datetime | None:
    """ISO 8601 with Z or an offset (Meta sends +0000), or a bare date."""
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    if len(text) >= 5 and text[-5] in "+-" and text[-3] != ":":
        text = text[:-2] + ":" + text[-2:]
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def num(value: Any) -> float | None:
    try:
        return None if value is None or value == "" else float(value)
    except (TypeError, ValueError):
        return None


def clip(value: Any, limit: int = MAX_TEXT) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


class Reader:
    """Reads package files, collecting a warning instead of failing on bad ones."""

    def __init__(self, pkg: Path):
        self.pkg = pkg
        self.warnings: list[str] = []
        self._yaml = None

    def rel(self, path: Path) -> str:
        try:
            return path.relative_to(self.pkg).as_posix()
        except ValueError:
            return path.name

    def json(self, path: Path) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            self.warnings.append(f"{self.rel(path)}: unreadable ({type(e).__name__})")
            return None

    def yaml(self, path: Path) -> Any:
        if self._yaml is None:
            self._yaml = yaml_module() or False
        if not self._yaml:
            self.warnings.append(f"{self.rel(path)}: no YAML loader (install PyYAML)")
            return None
        try:
            return self._yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001 - any parse error is a warning, not a crash
            self.warnings.append(f"{self.rel(path)}: unreadable ({type(e).__name__})")
            return None


# --- campaigns, from the newest meta-report collect file ---------------------------------------

def link_clicks(row: dict[str, Any]) -> float | None:
    return num(row.get("inline_link_clicks")) if row.get("inline_link_clicks") is not None else num(row.get("clicks"))


def metrics(row: dict[str, Any]) -> dict[str, Any]:
    spend, impressions, clicks = num(row.get("spend")), num(row.get("impressions")), link_clicks(row)
    out = {
        "spend": spend, "impressions": impressions, "reach": num(row.get("reach")),
        "frequency": num(row.get("frequency")), "link_clicks": clicks,
        "landing_views": num(row.get("landing_page_views")),
        "ctr": clicks / impressions if clicks is not None and impressions else None,
        "cpc": spend / clicks if spend is not None and clicks else None,
        "cpm": spend / impressions * 1000 if spend is not None and impressions else None,
    }
    actions = row.get("actions")
    if isinstance(actions, dict):
        out["actions"] = {str(k): num(v) for k, v in actions.items() if num(v) is not None}
    return out


def pacing(start: datetime | None, end: datetime | None, cap: float | None, spend: float | None,
           at: datetime) -> dict[str, Any] | None:
    if not (start and end and end > start):
        return None
    total = (end - start).total_seconds() / 86400
    elapsed = min(max((at - start).total_seconds() / 86400, 0), total)
    left = max((end - at).total_seconds() / 86400, 0)
    out: dict[str, Any] = {"days_total": round(total, 2), "days_elapsed": round(elapsed, 2), "days_left": round(left, 2)}
    if cap is not None:
        out["even_spend_to_date"] = round(cap * elapsed / total, 2)
        if spend is not None:
            remaining = max(cap - spend, 0)
            out["per_day_to_finish"] = round(remaining / left, 2) if left > 0 else None
    return out


def campaign_entry(rep: dict[str, Any], checked_at: datetime) -> dict[str, Any]:
    rb = rep.get("readback") or {}
    camp = rb.get("campaign") or {}
    adsets = rb.get("adsets") or []
    insights = rep.get("insights") or {}
    total = metrics((insights.get("total") or [{}])[0]) if insights.get("total") else None
    starts = [t for t in (parse_time(s.get("start_time")) for s in adsets) if t] or [parse_time(camp.get("start_time"))]
    ends = [t for t in (parse_time(s.get("end_time")) for s in adsets) if t] or [parse_time(camp.get("stop_time"))]
    start = min((t for t in starts if t), default=None)
    end = max((t for t in ends if t), default=None)
    cap = num(rep.get("lifetime_cap"))
    spend = total["spend"] if total else None
    gaps = set(rep.get("data_gaps") or [])
    daily = []
    for d in insights.get("daily") or []:
        m = metrics(d)
        gap = d.get("date_start") in gaps
        if gap:  # Meta returned 0 cost rows while clicks look normal: those zeros are missing data
            m.update(spend=None, impressions=None, reach=None, ctr=None, cpc=None)
        daily.append({"date": d.get("date_start"), **{k: m[k] for k in
                      ("spend", "impressions", "reach", "link_clicks", "landing_views", "ctr", "cpc")},
                      "gap": gap})
    placements = []
    for p in insights.get("placement") or []:
        m = metrics(p)
        label = " ".join(str(x) for x in (p.get("publisher_platform"), p.get("platform_position")) if x)
        placements.append({"label": label or "unknown", **{k: m[k] for k in
                           ("spend", "impressions", "link_clicks", "landing_views", "ctr", "cpc")}})
    audience = []
    for a in insights.get("age_gender") or []:
        m = metrics(a)
        audience.append({"age": a.get("age") or "unknown", "gender": a.get("gender") or "unknown",
                         **{k: m[k] for k in ("spend", "impressions", "link_clicks", "landing_views")}})
    ads = [{"id": ad.get("id"), "name": clip(ad.get("name"), 120), "effective_status": ad.get("effective_status"),
            "issues": [clip(i.get("summary"), 160) for i in ad.get("issues") or []]} for ad in rb.get("ads") or []]
    return {
        "id": rep.get("campaign_id") or camp.get("id"),
        "name": clip(camp.get("name"), 120) or None,
        "objective": camp.get("objective"),
        "status": camp.get("status"),
        "effective_status": camp.get("effective_status"),
        "start": iso(start) if start else None,
        "end": iso(end) if end else None,
        "cap": cap,
        "spend": spend,
        "remaining": round(cap - spend, 2) if cap is not None and spend is not None else None,
        "pacing": pacing(start, end, cap, spend, checked_at),
        "totals": total,
        "daily": daily,
        "placements": sorted(placements, key=lambda p: -(p["spend"] or 0)),
        "audience": audience,
        "ads": ads,
        "problems": [clip(p) for p in rep.get("problems") or []],
        "data_gaps": sorted(gaps),
        "complete": rep.get("complete", True),
    }


def latest_report(r: Reader) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    folder = r.pkg / "runs" / "meta-daily"
    files = sorted(folder.glob("*.json")) if folder.is_dir() else []
    for path in reversed(files):
        data = r.json(path)
        if isinstance(data, dict) and isinstance(data.get("campaigns"), list):
            checked = parse_time(data.get("checked_at_utc"))
            report = {"file": r.rel(path), "checked_at": iso(checked) if checked else None,
                      "verdict": data.get("verdict"), "count": len(files)}
            at = checked or now_utc()
            return report, [campaign_entry(c, at) for c in data["campaigns"] if isinstance(c, dict)]
        if data is not None:
            r.warnings.append(f"{r.rel(path)}: not a meta-report collect file; skipped")
    return None, []


# --- weekly windows, decisions, packets, economics, activity ------------------------------------

def weekly(r: Reader) -> list[dict[str, Any]]:
    folder = r.pkg / "runs" / "weekly"
    out = []
    for path in sorted(folder.glob("*.json"))[-8:] if folder.is_dir() else []:
        data = r.json(path)
        if isinstance(data, dict):
            tr = data.get("time_range") or {}
            out.append({"since": tr.get("since"), "until": tr.get("until"), "verdict": data.get("verdict"),
                        "file": r.rel(path)})
    return out


def decisions(r: Reader) -> list[dict[str, Any]]:
    path = r.pkg / "decisions.json"
    data = r.json(path) if path.is_file() else []
    if not isinstance(data, list):
        return []
    out = []
    for d in data[-20:]:
        if isinstance(d, dict):
            out.append({"id": d.get("id"), "at": d.get("at_utc"), "topic": d.get("topic"),
                        "owner_words": clip(d.get("owner_words")),
                        "approves_files": len(d.get("approves_files") or {}),
                        "not_authorized": [clip(x, 80) for x in d.get("not_authorized") or []][:10],
                        "expires": d.get("expires_utc")})
    return list(reversed(out))


def packets(r: Reader) -> list[dict[str, Any]]:
    folder = r.pkg / "packets"
    out = []
    for m in sorted(folder.glob("*/manifest.json")) if folder.is_dir() else []:
        data = r.json(m)
        status = data.get("status") if isinstance(data, dict) else "unreadable manifest"
        out.append({"id": m.parent.name, "status": status or "unknown",
                    "needs_owner": bool(OWNER_STATUS.search(str(status or ""))),
                    "updated": iso(datetime.fromtimestamp(m.stat().st_mtime, timezone.utc)),
                    "review_page": r.rel(m.parent / "review.html") if (m.parent / "review.html").is_file() else None})
    return sorted(out, key=lambda p: p["updated"], reverse=True)


def economics(r: Reader) -> list[dict[str, Any]]:
    folder = r.pkg / "economics"
    out = []
    for path in sorted(folder.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9].yaml"))[-12:] if folder.is_dir() else []:
        data = r.yaml(path)
        if not isinstance(data, dict):
            continue
        missing = [k for k in ("net_revenue", *ECONOMICS_COSTS) if num(data.get(k)) is None]
        revenue, ads = num(data.get("net_revenue")), num(data.get("ad_spend"))
        costs = None if any(k in missing for k in ECONOMICS_COSTS) else sum(num(data.get(k)) for k in ECONOMICS_COSTS)
        contribution = revenue - costs if revenue is not None and costs is not None else None
        out.append({"month": path.stem, "currency": data.get("currency"), "net_revenue": revenue, "costs": costs,
                    "contribution": contribution, "ad_spend": ads,
                    "net_after_ads": contribution - ads if contribution is not None and ads is not None else None,
                    "missing": missing + ([] if ads is not None else ["ad_spend"])})
    return out


def log_entry(job: str, line: str) -> dict[str, Any] | None:
    """One run-log line: '- <time> <text>' or '<time> | task=x | status=y | text'."""
    text = line[2:].strip() if line.startswith("- ") else line.strip()
    stamp, _, rest = text.partition(" ")
    at = parse_time(stamp.rstrip("|"))
    if at is None:
        return None if not line.startswith("- ") else {"job": job, "at": None, "verdict": None, "text": clip(text)}
    fields = [f.strip() for f in rest.strip().lstrip("|").split("|")]
    verdict = next((f.split("=", 1)[1] for f in fields if f.startswith(("status=", "verdict="))), None)
    words = [f for f in fields if f and not re.match(r"^(task|status|verdict|sources|window)=", f)]
    return {"job": job, "at": iso(at), "verdict": verdict, "text": clip(" | ".join(words))}


def activity(r: Reader, limit: int = 40) -> list[dict[str, Any]]:
    runs = r.pkg / "runs"
    out = []
    for log in runs.glob("*/log.md") if runs.is_dir() else []:
        try:
            lines = log.read_text(encoding="utf-8").splitlines()
        except OSError:
            r.warnings.append(f"{r.rel(log)}: unreadable")
            continue
        out += [e for e in (log_entry(log.parent.name, ln) for ln in lines[-limit:] if ln.strip()) if e]
    # JSON run records (runs/<task>/<stamp>.json) carry their own verdict and next step.
    for folder in sorted(p for p in runs.iterdir() if p.is_dir() and p.name not in DATA_RUNS) if runs.is_dir() else []:
        for path in sorted(folder.glob("*.json"))[-5:]:
            data = r.json(path)
            if not isinstance(data, dict):
                continue
            at = parse_time(data.get("checked_at_utc") or data.get("at_utc"))
            verdict = data.get("verdict") or data.get("status")
            out.append({"job": str(data.get("task") or folder.name), "at": iso(at) if at else None,
                        "verdict": clip(verdict, 80) if verdict else None,
                        "text": clip(data.get("summary") or data.get("next") or "")})
    return sorted(out, key=lambda a: a["at"] or "", reverse=True)[:limit]


# --- assembly -----------------------------------------------------------------------------------

def overall(campaigns: list[dict[str, Any]], report: dict[str, Any] | None, waiting: int,
            at: datetime) -> dict[str, str]:
    problems = [p for c in campaigns for p in c["problems"]]
    live = [c for c in campaigns if c.get("effective_status") == "ACTIVE"]
    if problems or (report and report.get("verdict") in ("PROBLEMS", "BLOCKED")):
        return {"level": "problem", "headline": problems[0] if problems else f"Last report: {report['verdict']}"}
    if report is None:
        if waiting:
            return {"level": "attention", "headline": f"{waiting} packet{'s' if waiting != 1 else ''} waiting for the owner"}
        return {"level": "unknown", "headline": "No campaign report yet"}
    checked = parse_time(report.get("checked_at"))
    if live and checked and (at - checked).total_seconds() > STALE_REPORT_HOURS * 3600:
        return {"level": "attention", "headline": f"Live campaign, but the last report is over {STALE_REPORT_HOURS} h old"}
    if any(c["data_gaps"] for c in campaigns):
        return {"level": "attention", "headline": "Some days have data gaps: cost rows came back as 0"}
    if waiting:
        return {"level": "attention", "headline": f"{waiting} packet{'s' if waiting != 1 else ''} waiting for the owner"}
    state = "live" if live else "not delivering"
    return {"level": "ok", "headline": f"{len(campaigns)} campaign{'s' if len(campaigns) != 1 else ''} {state}, no problems"}


def build(pkg: Path, generated_by: str = "cli") -> dict[str, Any]:
    pkg = pkg.expanduser().resolve()
    r = Reader(pkg)
    at = now_utc()
    policy = r.yaml(pkg / "policy.yaml") if (pkg / "policy.yaml").is_file() else None
    if policy is None:
        r.warnings.append("policy.yaml missing or unreadable")
    policy = policy if isinstance(policy, dict) else {}
    budget = policy.get("budget") if isinstance(policy.get("budget"), dict) else {}
    report, campaigns = latest_report(r)
    pk = packets(r)
    snap = {
        "schema": SCHEMA,
        "generated_at": iso(at),
        "generated_by": clip(generated_by, 60),
        "business": {
            "name": clip(policy.get("business_name"), 80) or pkg.name.replace("-", " ").replace("_", " ").title(),
            "package": str(pkg),
            "currency": policy.get("currency"),
            "timezone": policy.get("timezone") or None,
            "mode": policy.get("mode"),
            "access_level": policy.get("access_level"),
        },
        "budget": {
            "owner_monthly_cap": num(budget.get("owner_monthly_cap")),
            "contribution_share": num(budget.get("contribution_share")),
            "launch_exception": ({"approved": bool(le.get("approved")), "total": num(le.get("total")),
                                  "start": str(le["start"]) if le.get("start") else None,
                                  "end": str(le["end"]) if le.get("end") else None}
                                 if isinstance(le := budget.get("launch_exception"), dict) else None),
        },
        "report": report,
        "campaigns": campaigns,
        "weekly": weekly(r),
        "packets": pk,
        "decisions": decisions(r),
        "economics": economics(r),
        "activity": activity(r),
    }
    snap["status"] = overall(campaigns, report, sum(p["needs_owner"] for p in pk), at)
    snap["warnings"] = r.warnings
    return snap


def write(pkg: Path, generated_by: str = "cli") -> Path:
    """Build and atomically replace <package>/runs/dashboard/snapshot.json."""
    snap = build(pkg, generated_by)
    path = Path(snap["business"]["package"]) / SNAPSHOT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(snap, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    os.replace(tmp, path)
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="marketing-snapshot", description=__doc__.split("\n\n")[0])
    ap.add_argument("package", type=Path, help="marketing package folder")
    ap.add_argument("--write", action="store_true", help="write runs/dashboard/snapshot.json instead of printing")
    ap.add_argument("--by", default="cli", help="what produced this snapshot (a cron job name)")
    a = ap.parse_args(argv)
    if not a.package.expanduser().is_dir():
        print(f"marketing-snapshot: no such package folder: {a.package}", file=sys.stderr)
        return 2
    if a.write:
        print(write(a.package, a.by))
    else:
        print(json.dumps(build(a.package, a.by), indent=1, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
