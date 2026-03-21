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


def load_config() -> dict:
    """Load config from CONFIG_FILE.
    Returns dict with at least 'drive_folder_id'.
    If file doesn't exist, returns empty dict.
    """
    if not CONFIG_FILE.exists():
        return {}
    with open(CONFIG_FILE) as f:
        return json.load(f)


def save_config(config: dict) -> None:
    """Save config to CONFIG_FILE.
    Creates CONFIG_DIR if needed.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def ensure_drive_root(config: dict) -> str:
    """Ensure ccrelay root folder exists on Drive, return its ID.
    1. Search Drive for folder named 'ccrelay'
    2. If found, use it (and update config if needed)
    3. If not found, create it at Drive root
    4. Save folder ID to config
    Returns folder ID.
    """
    folder_id = drive_find_folder("ccrelay")
    if folder_id:
        if config.get("drive_folder_id") != folder_id:
            config["drive_folder_id"] = folder_id
            save_config(config)
        return folder_id

    # Not found on Drive — create it
    folder_id = drive_create_folder("ccrelay", "root")
    config["drive_folder_id"] = folder_id
    save_config(config)
    return folder_id


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


def gws_run(args: list[str], cwd: str | None = None) -> dict:
    """Run a gws command and return parsed JSON response.
    Full command: ['gws'] + args
    Captures stdout, parses as JSON.
    Raises RuntimeError with stderr on non-zero exit code.
    Raises RuntimeError on invalid JSON.
    cwd: working directory for the subprocess (needed for --upload).
    """
    result = subprocess.run(
        ["gws"] + args,
        capture_output=True,
        text=True,
        cwd=cwd,
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
    abs_path = os.path.abspath(file_path)
    file_dir = os.path.dirname(abs_path)
    file_name = os.path.basename(abs_path)
    metadata = json.dumps({
        "name": name,
        "parents": [parent_id],
    })
    result = gws_run([
        "drive", "files", "create",
        "--json", metadata,
        "--upload", file_name,
    ], cwd=file_dir)
    return result["id"]


def drive_update(file_id: str, file_path: str) -> str:
    """Update an existing file on Drive. Returns file ID."""
    abs_path = os.path.abspath(file_path)
    file_dir = os.path.dirname(abs_path)
    file_name = os.path.basename(abs_path)
    params = json.dumps({"fileId": file_id})
    result = gws_run([
        "drive", "files", "update",
        "--params", params,
        "--upload", file_name,
    ], cwd=file_dir)
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
        "fields": "files(id,name,size,modifiedTime,mimeType)",
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


def list_local_sessions(project_path: str, claude_dir: Path = DEFAULT_CLAUDE_DIR) -> list[dict]:
    """List local sessions for a project.
    Scans claude_dir/projects/{project_path}/ for *.jsonl files.
    Returns list of dicts with keys: uuid, path, size, mtime
    - uuid: filename without .jsonl extension
    - path: full path to the .jsonl file
    - size: total size of .jsonl + subagents dir (if exists)
    - mtime: modification time of .jsonl as datetime
    Sorted by mtime descending (newest first).
    """
    project_dir = claude_dir / "projects" / project_path
    if not project_dir.is_dir():
        return []

    sessions = []
    for f in project_dir.glob("*.jsonl"):
        uuid = f.stem
        size = f.stat().st_size

        # Add size of {uuid}/ directory tree if it exists
        uuid_dir = project_dir / uuid
        if uuid_dir.is_dir():
            for child in uuid_dir.rglob("*"):
                if child.is_file():
                    size += child.stat().st_size

        sessions.append({
            "uuid": uuid,
            "path": str(f),
            "size": size,
            "mtime": datetime.fromtimestamp(f.stat().st_mtime),
        })

    sessions.sort(key=lambda s: s["mtime"], reverse=True)
    return sessions


def bundle_session(project_path: str, uuid: str, claude_dir: Path = DEFAULT_CLAUDE_DIR) -> str:
    """Bundle a session into a tar.gz in a temp directory.
    Includes: {uuid}.jsonl and {uuid}/ directory (if exists, contains subagents/).
    Returns path to the created tar.gz file.
    tar.gz filename: {uuid}_{YYYY-MM-DD}.tar.gz
    Files are archived relative to the project directory.
    """
    project_dir = claude_dir / "projects" / project_path
    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"{uuid}_{today}.tar.gz"

    tmp_dir = tempfile.mkdtemp()
    tar_path = os.path.join(tmp_dir, filename)

    with tarfile.open(tar_path, "w:gz") as tf:
        jsonl_path = project_dir / f"{uuid}.jsonl"
        tf.add(str(jsonl_path), arcname=f"{uuid}.jsonl")

        uuid_dir = project_dir / uuid
        if uuid_dir.is_dir():
            for child in uuid_dir.rglob("*"):
                arcname = str(child.relative_to(project_dir))
                tf.add(str(child), arcname=arcname)

    return tar_path


# === Commands: push, pull, list ===


def project_path_to_cwd(project_path: str) -> str:
    """Reverse of cwd_to_project_path. Convert '-Users-woojin-home-ccrelay' back to '/Users/woojin/home/ccrelay'.
    Strategy: replace '-' with '/' and ensure it starts with '/'.
    Note: This is a best-effort approximation since the conversion is lossy
    (paths with dashes are ambiguous). For the user's consistent ~/home/{project} layout, it works.
    """
    if not project_path:
        return "/"
    return project_path.replace("-", "/")


def restore_session(tar_path: str, project_path: str, claude_dir: Path = DEFAULT_CLAUDE_DIR) -> str:
    """Extract a session tar.gz to the correct local directory.
    Extracts to claude_dir/projects/{project_path}/
    Returns the session UUID extracted.
    """
    dest_dir = claude_dir / "projects" / project_path
    dest_dir.mkdir(parents=True, exist_ok=True)

    with tarfile.open(tar_path, "r:gz") as tar:
        tar.extractall(path=dest_dir)
        names = tar.getnames()

    # Extract UUID from the first .jsonl file that is not an agent file
    for name in names:
        basename = os.path.basename(name)
        if basename.endswith(".jsonl") and not basename.startswith("agent-"):
            return basename.removesuffix(".jsonl")

    # Fallback: derive from tar filename ({uuid}_{date}.tar.gz)
    tar_basename = os.path.basename(tar_path)
    return tar_basename.split("_")[0]


def create_session_index(session_id: str, project_path: str, claude_dir: Path = DEFAULT_CLAUDE_DIR) -> None:
    """Create a session index file in claude_dir/sessions/ for claude --resume compatibility.
    File: claude_dir/sessions/{pid}.json
    Content: {"pid": <pid>, "sessionId": "<uuid>", "cwd": "<derived_from_project_path>", "startedAt": <timestamp_ms>}
    """
    sessions_dir = claude_dir / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    pid = os.getpid()
    cwd = project_path_to_cwd(project_path)
    started_at = int(datetime.now().timestamp() * 1000)

    index_data = {
        "pid": pid,
        "sessionId": session_id,
        "cwd": cwd,
        "startedAt": started_at,
    }

    index_file = sessions_dir / f"{pid}.json"
    with open(index_file, "w") as f:
        json.dump(index_data, f)


# === CLI Entry Point ===


def build_parser() -> argparse.ArgumentParser:
    """Build argparse parser.
    Subcommands: push, pull, list
    Each subcommand accepts --project option.
    """
    parser = argparse.ArgumentParser(
        prog="ccrelay",
        description="Selectively relay Claude Code sessions between machines via Google Drive.",
    )
    subparsers = parser.add_subparsers(dest="command", title="commands")

    help_texts = {
        "push": "Push a local session to Google Drive",
        "pull": "Pull a session from Google Drive to local",
        "list": "List sessions on Google Drive",
    }
    project_help = (
        "Project name or path suffix to match "
        "(e.g., 'ccrelay' matches '-Users-woojin-home-ccrelay'). "
        "Defaults to current working directory."
    )

    for name, help_text in help_texts.items():
        sub = subparsers.add_parser(name, help=help_text)
        sub.add_argument("--project", default=None, help=project_help)

    return parser


def _print_gws_error():
    """Print standardized gws CLI error message."""
    print("Error: gws CLI is not available or not authenticated.", file=sys.stderr)
    print("Install: brew install googleworkspace-cli", file=sys.stderr)
    print("Authenticate: gws auth setup --login", file=sys.stderr)


def cmd_push(args):
    """Push a session to Google Drive."""
    if not check_gws_available():
        _print_gws_error()
        sys.exit(1)

    try:
        project_path = resolve_project_path(args.project)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    sessions = list_local_sessions(project_path)
    if not sessions:
        print(f"No local sessions found for project: {project_path}")
        return

    print(f"Sessions for {project_path}:\n")
    for i, s in enumerate(sessions, 1):
        size_kb = s["size"] / 1024
        mtime_str = s["mtime"].strftime("%Y-%m-%d %H:%M:%S")
        print(f"  [{i}] {s['uuid']}")
        print(f"      {size_kb:.1f} KB  |  {mtime_str}")

    print()
    choice = input("Select session number to push: ")
    try:
        idx = int(choice) - 1
        if idx < 0 or idx >= len(sessions):
            print(f"Error: Please enter a number between 1 and {len(sessions)}.", file=sys.stderr)
            return
    except ValueError:
        print(f"Error: '{choice}' is not a valid number.", file=sys.stderr)
        return

    selected = sessions[idx]
    uuid = selected["uuid"]

    tar_path = bundle_session(project_path, uuid)
    tar_name = os.path.basename(tar_path)

    try:
        config = load_config()
        root_folder_id = ensure_drive_root(config)

        proj_folder_id = drive_find_folder(project_path, parent_id=root_folder_id)
        if proj_folder_id is None:
            proj_folder_id = drive_create_folder(project_path, root_folder_id)

        existing_files = drive_list_files(proj_folder_id)
        existing = None
        for f in existing_files:
            if f["name"].startswith(uuid):
                existing = f
                break

        if existing:
            drive_update(existing["id"], tar_path)
            print(f"\nUpdated existing session on Drive: {tar_name}")
        else:
            drive_upload(tar_path, tar_name, proj_folder_id)
            print(f"\nUploaded session to Drive: {tar_name}")

    except RuntimeError as e:
        print(f"Error: Drive operation failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        os.remove(tar_path)


def cmd_pull(args):
    """Pull a session from Google Drive."""
    import shutil as _shutil

    # 1. Check gws available
    if not check_gws_available():
        _print_gws_error()
        sys.exit(1)

    # 2. Resolve project path
    try:
        project_path = resolve_project_path(args.project)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # 3. Load config for root folder ID
    try:
        config = load_config()
        root_folder_id = ensure_drive_root(config)
    except RuntimeError as e:
        print(f"Error: Drive operation failed: {e}", file=sys.stderr)
        sys.exit(1)

    # 4. Find project folder on Drive
    try:
        folder_id = drive_find_folder(project_path, parent_id=root_folder_id)
    except RuntimeError as e:
        print(f"Error: Drive operation failed: {e}", file=sys.stderr)
        sys.exit(1)
    if not folder_id:
        print(f"No project folder '{project_path}' found on Drive.")
        return

    # 5. List sessions
    try:
        files = drive_list_files(folder_id)
    except RuntimeError as e:
        print(f"Error: Drive operation failed: {e}", file=sys.stderr)
        sys.exit(1)
    if not files:
        print("No sessions found on Drive for this project.")
        return

    # 6. Print session list
    print(f"\nSessions for {project_path}:\n")
    for i, f_info in enumerate(files, 1):
        size = f_info.get("size", "?")
        modified = f_info.get("modifiedTime", "?")
        print(f"  [{i}] {f_info['name']}  ({size} bytes, modified: {modified})")
    print()

    # 7. User selects a number
    selection = input("Select session number (or 'q' to cancel): ").strip()
    if selection.lower() == "q":
        print("Cancelled.")
        return

    try:
        idx = int(selection) - 1
        if idx < 0 or idx >= len(files):
            print(f"Error: Please enter a number between 1 and {len(files)}.", file=sys.stderr)
            return
    except ValueError:
        print(f"Error: '{selection}' is not a valid number.", file=sys.stderr)
        return

    selected = files[idx]
    file_id = selected["id"]
    file_name = selected["name"]
    drive_modified_time = selected.get("modifiedTime", "")

    # 8. Download to temp dir
    tmp_dir = tempfile.mkdtemp()
    try:
        tar_path = os.path.join(tmp_dir, file_name)
        drive_download(file_id, tar_path)

        # 9. Check for local conflict
        uuid = file_name.split("_")[0]
        local_session_file = DEFAULT_CLAUDE_DIR / "projects" / project_path / f"{uuid}.jsonl"

        if local_session_file.exists():
            local_mtime = local_session_file.stat().st_mtime
            from datetime import timezone
            drive_dt = datetime.fromisoformat(drive_modified_time.replace("Z", "+00:00"))
            drive_ts = drive_dt.timestamp()

            if drive_ts > local_mtime:
                print("Drive version is newer. Overwriting local session.")
            else:
                confirm = input(
                    "Local session is newer than Drive version. Overwrite? [y/N] "
                ).strip()
                if confirm.lower() != "y":
                    print("Skipped.")
                    return

        # 10. Restore session
        extracted_uuid = restore_session(tar_path, project_path)

        # 11. Create session index
        create_session_index(extracted_uuid, project_path)

        # 13. Print success
        print(f"\nSession {extracted_uuid} pulled.")
        print(f"Use 'claude --resume {extracted_uuid}' to continue.")

    except RuntimeError as e:
        print(f"Error: Drive operation failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        # 12. Clean up temp files
        _shutil.rmtree(tmp_dir, ignore_errors=True)


def _format_size(size_str: str) -> str:
    """Format byte size string to human-readable format."""
    try:
        size = int(size_str)
    except (ValueError, TypeError):
        return "unknown"
    if size >= 1_000_000:
        return f"{size / 1_000_000:.1f}MB"
    if size >= 1_000:
        return f"{size / 1_000:.0f}KB"
    return f"{size}B"


def _format_time(time_str: str) -> str:
    """Format ISO time string to 'YYYY-MM-DD HH:MM'."""
    try:
        dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return "unknown"


def _print_sessions(project_name: str, sessions: list[dict]) -> None:
    """Print sessions for a single project."""
    print(f"\nProject: {project_name}")
    if not sessions:
        print("  (no sessions)")
        return
    for i, s in enumerate(sessions, 1):
        name = s.get("name", "unknown")
        size = _format_size(s.get("size", "0"))
        time = _format_time(s.get("modifiedTime", ""))
        print(f"  {i}. {name}  ({size}, {time})")


def cmd_list(args):
    """List sessions on Google Drive."""
    if not check_gws_available():
        _print_gws_error()
        sys.exit(1)

    try:
        config = load_config()
        root_id = ensure_drive_root(config)
    except RuntimeError as e:
        print(f"Error: Drive operation failed: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        if args.project:
            # List sessions for a specific project
            project_folder_id = drive_find_folder(args.project, root_id)
            if not project_folder_id:
                print("No sessions found on Drive.")
                return
            sessions = drive_list_files(project_folder_id)
            if not sessions:
                print("No sessions found on Drive.")
                return
            _print_sessions(args.project, sessions)
        else:
            # List all project folders and their sessions
            folders = drive_list_files(root_id)
            project_folders = [
                f for f in folders
                if f.get("mimeType") == "application/vnd.google-apps.folder"
            ]
            if not project_folders:
                print("No sessions found on Drive.")
                return
            found_any = False
            for folder in project_folders:
                sessions = drive_list_files(folder["id"])
                _print_sessions(folder["name"], sessions)
                if sessions:
                    found_any = True
            if not found_any:
                print("\nNo sessions found on Drive.")
    except RuntimeError as e:
        print(f"Error: Drive operation failed: {e}", file=sys.stderr)
        sys.exit(1)


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
