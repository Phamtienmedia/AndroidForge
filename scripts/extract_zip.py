#!/usr/bin/env python3
"""AndroidForge — Extract Source ZIP.

Extracts the source ZIP to a clean workspace and writes the extracted root
directory to $GITHUB_OUTPUT.

The script strips macOS metadata directories (`__MACOSX`), unwraps a
top-level single directory if present (so e.g. `MyProject-1.2.3/` becomes
the workspace root when it's the only top-level entry), and sanitizes the
final project-root directory name so it contains no spaces.

Why sanitize spaces:
    The Android NDK (r21 and earlier, still pinned by some legacy projects)
    runs `ndk-build` with $APP_BUILD_SCRIPT unquoted. A path like
    `/work/.androidforge/workspace/ImGui dump 64/app/src/main/jni/Android.mk`
    splits into multiple make targets at the space, producing:
        Android NDK: Your APP_BUILD_SCRIPT points to an unknown file: ...
    Newer NDK (r25+) handles spaces correctly, but the rename is cheap
    defence-in-depth and also keeps log paths machine-parseable.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent


def safe_dirname(name: str) -> str:
    """Collapse anything non-alnum/._- to underscore.

    Example: 'ImGui dump 64' → 'ImGui_dump_64'.
    Empty result is replaced with 'project'.
    Long names are capped at 80 chars to keep the final path within
    PATH_MAX when combined with deep extraction roots.
    """
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._-")
    if len(cleaned) > 80:
        cleaned = cleaned[:80].rstrip("._-")
    return cleaned or "project"


def _sanitize_top_level(top: Path) -> Path:
    """Rename a top-level directory if its name contains unsafe characters.

    Returns the (possibly new) path. If the name is already safe, the
    original path is returned unchanged.
    """
    safe = safe_dirname(top.name)
    if safe == top.name:
        return top
    new = top.parent / safe
    # Collision guard: if a same-named entry already exists, append a suffix.
    if new.exists():
        i = 2
        while True:
            candidate = top.parent / f"{safe}_{i}"
            if not candidate.exists():
                new = candidate
                break
            i += 1
    top.rename(new)
    return new


def extract(zip_path: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        # Filter out __MACOSX entries
        members = [m for m in zf.infolist() if not m.filename.startswith("__MACOSX") and "/.DS_Store" not in m.filename]
        zf.extractall(dest_dir, members=members)

    # Remove any leftover __MACOSX dirs on disk
    for macosx in dest_dir.rglob("__MACOSX"):
        if macosx.is_dir():
            shutil.rmtree(macosx, ignore_errors=True)

    # Python's zipfile.extractall() does NOT preserve the Unix execute bit
    # on shell scripts (e.g. `gradlew`). Without this, running `./gradlew`
    # later fails with PermissionError. We restore the +x bit on every
    # shell script and binary we can recognise by extension/name.
    for p in dest_dir.rglob("*"):
        if not p.is_file():
            continue
        name = p.name
        if name == "gradlew" or name == "gradlew.bat" or name.endswith(".sh") or name == "flutter" or name == "dart":
            try:
                cur = p.stat().st_mode
                p.chmod(cur | 0o111)  # set +x for user/group/other
            except Exception:
                pass

    # If the archive contains exactly one top-level directory, unwrap it
    # AND sanitize its name (spaces → underscores) so downstream tools —
    # especially legacy Android NDK r21 — never see a path with spaces.
    top = [p for p in dest_dir.iterdir() if not p.name.startswith(".")]
    if len(top) == 1 and top[0].is_dir():
        return _sanitize_top_level(top[0])

    # Multiple top-level entries: project_root is dest_dir itself.
    # dest_dir is derived from a repo-controlled path (.androidforge/workspace),
    # so it's already safe — nothing to sanitize here.
    return dest_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="AndroidForge ZIP extraction")
    parser.add_argument("--zip", required=True, help="Path to the source ZIP")
    parser.add_argument("--dest-dir", default=None, help="Where to extract (default: <repo>/.androidforge/workspace)")
    args = parser.parse_args()

    zip_path = Path(args.zip).resolve()
    if not zip_path.exists():
        print(f"ERROR: ZIP not found: {zip_path}", file=sys.stderr)
        return 1

    dest_dir = Path(args.dest_dir) if args.dest_dir else (REPO_ROOT / ".androidforge" / "workspace")
    # Clean workspace
    if dest_dir.exists():
        shutil.rmtree(dest_dir, ignore_errors=True)
    dest_dir.mkdir(parents=True, exist_ok=True)

    project_root = extract(zip_path, dest_dir)

    print(json.dumps({
        "zip_path": str(zip_path),
        "extract_root": str(project_root),
        "dest_dir": str(dest_dir),
        "path_had_spaces": " " in str(project_root),
    }, indent=2))

    gh_output = os.environ.get("GITHUB_OUTPUT")
    if gh_output:
        with open(gh_output, "a", encoding="utf-8") as f:
            f.write(f"project_root={project_root}\n")
            f.write(f"extract_root={project_root}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
