#!/usr/bin/env python3
"""Copy the plugin files from the Marketer agent's copy, which is the source of truth.

  python3 tools/sync_from_marketer.py <path to agents/marketer/plugins/marketing-dashboard>
"""
import shutil
import sys
from pathlib import Path

FILES = ["plugin.yaml", "__init__.py", "marketing_snapshot.py", "SNAPSHOT.md",
         "dashboard/manifest.json", "dashboard/plugin_api.py", "desktop/plugin.js"]

src = Path(sys.argv[1]) if len(sys.argv) > 1 else None
if not src or not (src / "plugin.yaml").is_file():
    sys.exit(__doc__)
dest = Path(__file__).resolve().parent.parent
for rel in FILES:
    (dest / rel).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src / rel, dest / rel)
    print("synced", rel)
