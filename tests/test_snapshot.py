"""Tests for marketing_snapshot.py and dashboard/plugin_api.py.

  python3 -m unittest discover -s tests

Builds the made-up example package into a temp folder and checks the snapshot,
then exercises the backend's package discovery without a running Hermes.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


snapshot = load("marketing_snapshot", ROOT / "marketing_snapshot.py")


class ExampleBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.pkg = Path(cls.tmp.name) / "northwind-candles"
        subprocess.run([sys.executable, str(ROOT / "examples" / "make_example.py"), str(cls.pkg)], check=True,
                       capture_output=True)
        cls.snap = snapshot.build(cls.pkg, "test")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()


class SnapshotTest(ExampleBase):
    def test_schema_and_business(self):
        s = self.snap
        self.assertEqual(s["schema"], snapshot.SCHEMA)
        self.assertEqual(s["business"]["name"], "Northwind Candles")
        self.assertEqual(s["business"]["currency"], "USD")
        self.assertEqual(s["warnings"], [])
        json.dumps(s)  # serializable as-is

    def test_campaign_totals_and_pacing(self):
        c = self.snap["campaigns"][0]
        self.assertEqual(c["effective_status"], "ACTIVE")
        self.assertEqual(c["cap"], 300.0)
        self.assertAlmostEqual(c["remaining"], 300.0 - c["spend"], places=2)
        self.assertTrue(c["start"].endswith("Z") and c["end"].endswith("Z"))
        self.assertGreater(c["pacing"]["days_left"], 0)
        self.assertAlmostEqual(c["totals"]["ctr"], c["totals"]["link_clicks"] / c["totals"]["impressions"])

    def test_gap_days_are_missing_not_zero(self):
        c = self.snap["campaigns"][0]
        gaps = [d for d in c["daily"] if d["gap"]]
        self.assertEqual(len(gaps), 1)
        self.assertIsNone(gaps[0]["spend"])
        self.assertIsNone(gaps[0]["cpc"])
        self.assertIsNotNone(gaps[0]["link_clicks"])
        self.assertEqual(self.snap["status"]["level"], "attention")

    def test_economics_unknown_when_a_cost_is_missing(self):
        months = {m["month"]: m for m in self.snap["economics"]}
        closed = [m for m in months.values() if not m["missing"]]
        open_ = [m for m in months.values() if m["missing"]]
        self.assertEqual(len(closed), 1)
        self.assertAlmostEqual(closed[0]["contribution"], 1850.0)
        self.assertIsNone(open_[0]["contribution"])
        self.assertIn("product_and_fulfillment", open_[0]["missing"])

    def test_packets_decisions_activity(self):
        s = self.snap
        self.assertEqual(sum(p["needs_owner"] for p in s["packets"]), 1)
        self.assertEqual(len(s["decisions"]), 2)
        self.assertGreater(s["decisions"][0]["at"], s["decisions"][1]["at"])  # newest first
        self.assertTrue(s["activity"])

    def test_write_is_atomic_and_readable(self):
        path = snapshot.write(self.pkg, "test")
        self.assertEqual(path, self.pkg.resolve() / snapshot.SNAPSHOT_REL)
        self.assertFalse(path.with_suffix(".json.tmp").exists())
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["generated_by"], "test")


class EmptyPackageTest(unittest.TestCase):
    def test_empty_folder_is_unknown_not_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = snapshot.build(Path(tmp), "test")
        self.assertEqual(s["status"]["level"], "unknown")
        self.assertEqual(s["campaigns"], [])
        self.assertIsNone(s["report"])
        self.assertIn("policy.yaml missing or unreadable", s["warnings"])

    def test_bad_files_become_warnings(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp)
            (pkg / "runs" / "meta-daily").mkdir(parents=True)
            (pkg / "runs" / "meta-daily" / "2026-01-01T000000Z.json").write_text("{not json", encoding="utf-8")
            (pkg / "decisions.json").write_text("[]", encoding="utf-8")
            s = snapshot.build(pkg, "test")
        self.assertTrue(any("unreadable" in w for w in s["warnings"]))
        self.assertEqual(s["campaigns"], [])


class PluginApiTest(ExampleBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        try:
            import fastapi  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("fastapi not installed")
        cls.api = load("plugin_api", ROOT / "dashboard" / "plugin_api.py")

    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.env = {k: os.environ.get(k) for k in ("HERMES_HOME", "MARKETING_DASHBOARD_PACKAGES")}
        os.environ["HERMES_HOME"] = self.home.name
        os.environ.pop("MARKETING_DASHBOARD_PACKAGES", None)
        self.api._hermes_home = lambda: Path(self.home.name)

    def tearDown(self):
        for k, v in self.env.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        self.home.cleanup()

    def run_async(self, coro):
        return asyncio.run(coro)

    def test_no_package_configured(self):
        self.assertEqual(self.run_async(self.api.businesses())["businesses"], [])
        with self.assertRaises(self.api.HTTPException) as e:
            self.run_async(self.api.get_snapshot())
        self.assertEqual(e.exception.status_code, 404)

    def test_marketer_settings_and_refresh(self):
        local = Path(self.home.name) / "local"
        local.mkdir()
        (local / "marketer.yaml").write_text(f"package: {json.dumps(str(self.pkg))}\n", encoding="utf-8")
        listed = self.run_async(self.api.businesses())["businesses"]
        self.assertEqual(len(listed), 1)
        bid = listed[0]["id"]
        snap = self.run_async(self.api.get_snapshot(bid))
        self.assertEqual(snap["business"]["name"], "Northwind Candles")
        snap = self.run_async(self.api.refresh(bid))
        self.assertEqual(snap["source"], "saved")
        self.assertEqual(snap["generated_by"], "dashboard refresh")

    def test_unknown_business_is_refused(self):
        os.environ["MARKETING_DASHBOARD_PACKAGES"] = str(self.pkg)
        with self.assertRaises(self.api.HTTPException) as e:
            self.run_async(self.api.get_snapshot("../../etc"))
        self.assertEqual(e.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
