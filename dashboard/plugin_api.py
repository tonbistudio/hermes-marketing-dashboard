"""Backend routes for the Marketing dashboard (mounted at /api/plugins/marketing-dashboard/).

Read-only over configured marketing packages. The page never sends a path: it
picks a business by the id returned from /businesses, and only packages named
in this profile's configuration are ever read. Packages are found in order:

  1. MARKETING_DASHBOARD_PACKAGES   (os.pathsep-separated folders)
  2. $HERMES_HOME/local/marketing-dashboard.yaml   packages: [<folder>, ...]
  3. $HERMES_HOME/local/marketer.yaml              package: <folder>

/snapshot serves the package's runs/dashboard/snapshot.json (written by the
agent's scheduled jobs), or builds one in memory when none exists yet.
/refresh rebuilds and saves it now.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter()

_HERE = Path(__file__).resolve().parent.parent


def _load_snapshot_module():
    spec = importlib.util.spec_from_file_location("marketing_snapshot", _HERE / "marketing_snapshot.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


snapshot = _load_snapshot_module()


def _hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home
        return Path(get_hermes_home())
    except Exception:  # noqa: BLE001 - outside Hermes, fall back to the environment
        return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")


def _read_yaml(path: Path) -> Any:
    yaml = snapshot.yaml_module()
    if yaml is None or not path.is_file():
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _configured() -> list[Path]:
    found: list[str] = []
    env = os.environ.get("MARKETING_DASHBOARD_PACKAGES", "")
    found += [p for p in env.split(os.pathsep) if p.strip()]
    local = _hermes_home() / "local"
    cfg = _read_yaml(local / "marketing-dashboard.yaml")
    if isinstance(cfg, dict) and isinstance(cfg.get("packages"), list):
        found += [str(p) for p in cfg["packages"] if p]
    marketer = _read_yaml(local / "marketer.yaml")
    if isinstance(marketer, dict) and marketer.get("package"):
        found.append(str(marketer["package"]))
    out: list[Path] = []
    for raw in found:
        path = Path(raw).expanduser().resolve()
        if path.is_dir() and path not in out:
            out.append(path)
    return out


def _business_id(path: Path) -> str:
    return hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:12]


def _resolve(business: str | None) -> Path:
    packages = _configured()
    if not packages:
        raise HTTPException(status_code=404, detail="no marketing package configured")
    if not business:
        return packages[0]
    for path in packages:
        if _business_id(path) == business:
            return path
    raise HTTPException(status_code=404, detail="unknown business")


def _saved(path: Path) -> dict[str, Any] | None:
    file = path / snapshot.SNAPSHOT_REL
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("schema") == snapshot.SCHEMA else None


def _list() -> list[dict[str, Any]]:
    out = []
    for path in _configured():
        saved = _saved(path)
        name = (saved or {}).get("business", {}).get("name") or path.name
        out.append({"id": _business_id(path), "name": name, "package": str(path),
                    "snapshot_at": (saved or {}).get("generated_at")})
    return out


def _get(business: str | None) -> dict[str, Any]:
    path = _resolve(business)
    saved = _saved(path)
    data = saved or snapshot.build(path, "dashboard (not saved)")
    return {**data, "business_id": _business_id(path), "source": "saved" if saved else "live"}


def _refresh(business: str | None) -> dict[str, Any]:
    path = _resolve(business)
    snapshot.write(path, "dashboard refresh")
    return {**_saved(path), "business_id": _business_id(path), "source": "saved"}


@router.get("/businesses")
async def businesses() -> dict[str, Any]:
    return {"businesses": await asyncio.to_thread(_list)}


@router.get("/snapshot")
async def get_snapshot(business: str | None = None) -> dict[str, Any]:
    return await asyncio.to_thread(_get, business)


@router.post("/refresh")
async def refresh(business: str | None = None) -> dict[str, Any]:
    return await asyncio.to_thread(_refresh, business)
