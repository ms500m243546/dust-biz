"""Phase A snapshot/restore tool.

Not a VCS replacement. Provides revertibility before git is initialized
in Phase B. Snapshots are stored under .rollback/<name>/.

Usage:
    python ops/rollback.py snapshot <name> [--modified F...] [--created F...]
    python ops/rollback.py to <name>
    python ops/rollback.py list
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_DIR = ROOT / ".rollback"


def snapshot(name: str, modified: list[str], created: list[str]) -> int:
    target = SNAPSHOT_DIR / name
    if target.exists():
        print(f"error: snapshot '{name}' already exists at {target}", file=sys.stderr)
        return 1
    (target / "modified").mkdir(parents=True, exist_ok=True)

    captured_modified: list[str] = []
    for rel in modified:
        src = ROOT / rel
        if not src.exists():
            print(f"warning: --modified file does not exist, skipping: {rel}", file=sys.stderr)
            continue
        dst = target / "modified" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        captured_modified.append(rel)

    manifest = {
        "name": name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "modified": captured_modified,
        "created": list(created),
    }
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(
        f"snapshot '{name}' saved: "
        f"{len(captured_modified)} modified captured, "
        f"{len(created)} created-files tracked for deletion on revert"
    )
    return 0


def restore(name: str) -> int:
    target = SNAPSHOT_DIR / name
    manifest_path = target / "manifest.json"
    if not manifest_path.exists():
        print(f"error: snapshot '{name}' not found at {target}", file=sys.stderr)
        return 1
    manifest = json.loads(manifest_path.read_text())

    for rel in manifest["modified"]:
        src = target / "modified" / rel
        dst = ROOT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"restored: {rel}")

    for rel in manifest["created"]:
        path = ROOT / rel
        if path.exists():
            path.unlink()
            print(f"removed (was created in this snapshot): {rel}")
        else:
            print(f"already absent: {rel}")

    print(f"snapshot '{name}' restored")
    return 0


def list_snapshots() -> int:
    if not SNAPSHOT_DIR.exists():
        print("no snapshots")
        return 0
    found = False
    for d in sorted(SNAPSHOT_DIR.iterdir()):
        manifest_path = d / "manifest.json"
        if not manifest_path.exists():
            continue
        m = json.loads(manifest_path.read_text())
        print(
            f"  {m['name']}  {m['created_at']}  "
            f"modified={len(m['modified'])} created={len(m['created'])}"
        )
        found = True
    if not found:
        print("no snapshots")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase A snapshot/restore tool")
    sub = parser.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("snapshot")
    s.add_argument("name")
    s.add_argument("--modified", nargs="*", default=[])
    s.add_argument("--created", nargs="*", default=[])

    t = sub.add_parser("to")
    t.add_argument("name")

    sub.add_parser("list")

    args = parser.parse_args()
    if args.cmd == "snapshot":
        return snapshot(args.name, args.modified, args.created)
    if args.cmd == "to":
        return restore(args.name)
    if args.cmd == "list":
        return list_snapshots()
    return 1


if __name__ == "__main__":
    sys.exit(main())
