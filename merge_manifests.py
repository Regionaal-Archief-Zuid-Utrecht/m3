#!/usr/bin/env python3
"""
Merge all *.manifest.json files in a single directory into a single manifest.json.

Input files are JSON objects mapping relative paths to metadata objects, e.g.
{
  "nl-wbdrazu/.../file.meta.json": { "MD5Hash": "...", "MD5HashDate": "...", "URI": "..." },
  "nl-wbdrazu/.../file.jpg": { "MD5Hash": "...", "MD5HashDate": "..." }
}

Usage:
  python merge_manifests.py <source_dir> [-o output_path]

Defaults:
  - Output path defaults to <source_dir>/manifest.json

Notes:
  - Keys are expected to be unique across input files. If a duplicate key is found
    with a different value, the script will raise an error. If the value is identical,
    it will be kept once.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Any


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    ap = argparse.ArgumentParser(description="Merge *.manifest.json files from one directory into a single manifest.json")
    ap.add_argument("source_dir", type=Path, help="Directory containing *.manifest.json files (non-recursive)")
    ap.add_argument("-o", "--output", type=Path, default=None, help="Output manifest.json path (default: <source_dir>/manifest.json)")
    args = ap.parse_args()

    src_dir: Path = args.source_dir
    if not src_dir.exists() or not src_dir.is_dir():
        raise SystemExit(f"Source directory does not exist or is not a directory: {src_dir}")

    out_path: Path = args.output if args.output else (src_dir / "manifest.json")

    manifest: Dict[str, Any] = {}
    files = sorted(src_dir.glob("*.manifest.json"))
    if not files:
        print("No *.manifest.json files found.")

    for fp in files:
        try:
            data = load_json(fp)
        except Exception as e:
            raise SystemExit(f"Failed to read {fp}: {e}")
        if not isinstance(data, dict):
            raise SystemExit(f"Manifest file is not a JSON object (dict): {fp}")
        for k, v in data.items():
            if k in manifest:
                if manifest[k] != v:
                    raise SystemExit(f"Duplicate key with conflicting values found: {k} (in {fp})")
                # if identical, skip
                continue
            manifest[k] = v

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, sort_keys=True)
    print(f"Merged {len(files)} files into {out_path} with {len(manifest)} entries.")


if __name__ == "__main__":
    main()
