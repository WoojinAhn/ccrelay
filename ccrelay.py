#!/usr/bin/env python3
"""ccrelay — selectively relay Claude Code sessions between machines via Google Drive."""

import argparse
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path


# === Config ===

DEFAULT_CLAUDE_DIR = Path.home() / ".claude"
CONFIG_DIR = Path.home() / ".config" / "ccrelay"
CONFIG_FILE = CONFIG_DIR / "config.json"


# === Project Path Resolution ===


def cwd_to_project_path(cwd: str) -> str:
    """Convert absolute path to Claude project path format.
    Replace '/' with '-', strip trailing '-'.
    e.g., '/Users/woojin/home/ccrelay' -> '-Users-woojin-home-ccrelay'
         '/' -> ''
    """
    return cwd.replace("/", "-").rstrip("-")


def resolve_project_path(project_arg: str | None, claude_dir: Path = DEFAULT_CLAUDE_DIR) -> str:
    """Resolve project path from --project arg or cwd.
    - No arg: use cwd_to_project_path(os.getcwd())
    - With arg: suffix match against directories in claude_dir/projects/
      e.g., 'cclanes' matches '-Users-woojin-home-cclanes'
    Raises ValueError if no match or ambiguous (multiple) match.
    """
    if project_arg is None:
        return cwd_to_project_path(os.getcwd())

    projects_dir = claude_dir / "projects"
    if not projects_dir.is_dir():
        raise ValueError(f"Projects directory not found: {projects_dir}")

    matches = [
        d.name for d in projects_dir.iterdir()
        if d.is_dir() and d.name.endswith(project_arg)
    ]

    if len(matches) == 0:
        raise ValueError(f"No project matching '{project_arg}'")
    if len(matches) > 1:
        raise ValueError(
            f"Ambiguous project '{project_arg}': matches {matches}"
        )
    return matches[0]


# === Drive Operations ===


def check_gws_available() -> bool:
    """Check if gws CLI is installed and authenticated.
    Runs 'gws auth status' via subprocess, checks for credentials.
    Returns True if auth_method != 'none', False otherwise.
    """
    try:
        result = subprocess.run(
            ["gws", "auth", "status"],
            capture_output=True,
            text=True,
        )
        data = json.loads(result.stdout)
        return data.get("auth_method") != "none"
    except FileNotFoundError:
        return False


def gws_run(args: list[str]) -> dict:
    """Run a gws command and return parsed JSON response.
    Full command: ['gws'] + args
    Captures stdout, parses as JSON.
    Raises RuntimeError with stderr on non-zero exit code.
    Raises RuntimeError on invalid JSON.
    """
    result = subprocess.run(
        ["gws"] + args,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid JSON from gws: {e}")


def drive_create_folder(name: str, parent_id: str) -> str:
    """Create a folder on Drive under parent_id. Returns new folder ID."""
    metadata = json.dumps({
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    })
    result = gws_run(["drive", "files", "create", "--json", metadata])
    return result["id"]


def drive_upload(file_path: str, name: str, parent_id: str) -> str:
    """Upload a file to Drive. Returns file ID."""
    metadata = json.dumps({
        "name": name,
        "parents": [parent_id],
    })
    result = gws_run([
        "drive", "files", "create",
        "--json", metadata,
        "--upload", file_path,
    ])
    return result["id"]


def drive_update(file_id: str, file_path: str) -> str:
    """Update an existing file on Drive. Returns file ID."""
    params = json.dumps({"fileId": file_id})
    result = gws_run([
        "drive", "files", "update",
        "--params", params,
        "--upload", file_path,
    ])
    return result["id"]


def drive_download(file_id: str, output_path: str) -> None:
    """Download a file from Drive to local path."""
    params = json.dumps({"fileId": file_id, "alt": "media"})
    gws_run([
        "drive", "files", "get",
        "--params", params,
        "--output", output_path,
    ])


def drive_list_files(parent_id: str) -> list[dict]:
    """List files in a Drive folder. Returns list of file metadata dicts."""
    params = json.dumps({
        "q": f'"{parent_id}" in parents',
        "pageSize": 100,
    })
    result = gws_run(["drive", "files", "list", "--params", params])
    return result.get("files", [])


def drive_find_folder(name: str, parent_id: str | None = None) -> str | None:
    """Find a folder by name. Returns folder ID or None."""
    query = f"name='{name}' and mimeType='application/vnd.google-apps.folder'"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    params = json.dumps({"q": query})
    result = gws_run(["drive", "files", "list", "--params", params])
    files = result.get("files", [])
    if files:
        return files[0]["id"]
    return None


# === Session Operations ===


# === Commands: push, pull, list ===


# === CLI Entry Point ===


def build_parser() -> argparse.ArgumentParser:
    """Build argparse parser.
    Subcommands: push, pull, list
    Each subcommand accepts --project option.
    """
    parser = argparse.ArgumentParser(
        prog="ccrelay",
        description="Selectively relay Claude Code sessions between machines.",
    )
    subparsers = parser.add_subparsers(dest="command")

    for name in ("push", "pull", "list"):
        sub = subparsers.add_parser(name)
        sub.add_argument("--project", default=None, help="Project name or suffix to match")

    return parser


def cmd_push(args):
    print("push: not implemented yet")


def cmd_pull(args):
    print("pull: not implemented yet")


def cmd_list(args):
    print("list: not implemented yet")


def main():
    parser = build_parser()
    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(2)
    dispatch = {
        "push": cmd_push,
        "pull": cmd_pull,
        "list": cmd_list,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
