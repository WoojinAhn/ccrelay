"""CLI entry point and command handlers."""

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime

from ccrelay.config import load_config, ensure_drive_root
from ccrelay.drive import (
    check_gws_available,
    drive_create_folder,
    drive_download,
    drive_find_folder,
    drive_list_files,
    drive_update,
    drive_upload,
)
from ccrelay.session import (
    bundle_session,
    create_session_index,
    list_local_sessions,
    restore_session,
)
from ccrelay.utils import (
    DEFAULT_CLAUDE_DIR,
    format_size,
    format_time,
    resolve_project_path,
)


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
        sub.add_argument("--json", action="store_true", default=False,
                         help="Output machine-readable JSON")
        if name in ("push", "pull"):
            sub.add_argument("--session", default=None,
                             help="Session UUID to use (skip interactive picker)")

    return parser


def _print_gws_error():
    """Print standardized gws CLI error message."""
    print("Error: gws CLI is not available or not authenticated.", file=sys.stderr)
    print("Install: brew install googleworkspace-cli", file=sys.stderr)
    print("Authenticate: gws auth setup --login", file=sys.stderr)


def _print_sessions(project_name: str, sessions: list[dict]) -> None:
    """Print sessions for a single project."""
    print(f"\nProject: {project_name}")
    if not sessions:
        print("  (no sessions)")
        return
    for i, s in enumerate(sessions, 1):
        name = s.get("name", "unknown")
        size = format_size(s.get("size", "0"))
        time = format_time(s.get("modifiedTime", ""))
        print(f"  {i}. {name}  ({size}, {time})")


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

    # --json only: output and exit
    if args.json and not args.session:
        output = [
            {
                "uuid": s["uuid"],
                "label": s.get("label"),
                "size": s["size"],
                "mtime": s["mtime"].isoformat(),
            }
            for s in sessions
        ]
        print(json.dumps(output, ensure_ascii=False))
        return

    if not sessions:
        print(f"No local sessions found for project: {project_path}")
        return

    # --session: skip picker
    if args.session:
        selected = next((s for s in sessions if s["uuid"] == args.session), None)
        if not selected:
            print(f"Error: Session '{args.session}' not found.", file=sys.stderr)
            sys.exit(1)
        uuid = selected["uuid"]
    else:
        print(f"Sessions for {project_path}:\n")
        for i, s in enumerate(sessions, 1):
            size_kb = s["size"] / 1024
            mtime_str = s["mtime"].strftime("%Y-%m-%d %H:%M:%S")
            label = s.get("label")
            print(f"  [{i}] {s['uuid']}")
            if label:
                print(f"      \"{label}\"")
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
    if not check_gws_available():
        _print_gws_error()
        sys.exit(1)

    try:
        project_path = resolve_project_path(args.project)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        config = load_config()
        root_folder_id = ensure_drive_root(config)
    except RuntimeError as e:
        print(f"Error: Drive operation failed: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        folder_id = drive_find_folder(project_path, parent_id=root_folder_id)
    except RuntimeError as e:
        print(f"Error: Drive operation failed: {e}", file=sys.stderr)
        sys.exit(1)
    if not folder_id:
        print(f"No project folder '{project_path}' found on Drive.")
        return

    try:
        files = drive_list_files(folder_id)
    except RuntimeError as e:
        print(f"Error: Drive operation failed: {e}", file=sys.stderr)
        sys.exit(1)
    if not files:
        print("No sessions found on Drive for this project.")
        return

    # --json only: output Drive session list and exit
    if args.json and not args.session:
        output = [
            {
                "id": f["id"],
                "name": f["name"],
                "uuid": f["name"].split("_")[0],
                "size": f.get("size", "0"),
                "modifiedTime": f.get("modifiedTime", ""),
            }
            for f in files
        ]
        print(json.dumps(output, ensure_ascii=False))
        return

    # --session: skip picker, match by UUID prefix
    if args.session:
        selected = next((f for f in files if f["name"].startswith(args.session)), None)
        if not selected:
            print(f"Error: Session '{args.session}' not found on Drive.", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"\nSessions for {project_path}:\n")
        for i, f_info in enumerate(files, 1):
            size = f_info.get("size", "?")
            modified = f_info.get("modifiedTime", "?")
            print(f"  [{i}] {f_info['name']}  ({size} bytes, modified: {modified})")
        print()

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

    tmp_dir = tempfile.mkdtemp()
    try:
        tar_path = os.path.join(tmp_dir, file_name)
        drive_download(file_id, tar_path)

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

        extracted_uuid = restore_session(tar_path, project_path)
        create_session_index(extracted_uuid, project_path)

        print(f"\nSession {extracted_uuid} pulled.")
        print(f"Use 'claude --resume {extracted_uuid}' to continue.")

    except RuntimeError as e:
        print(f"Error: Drive operation failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


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
        if args.json:
            result = []
            if args.project:
                project_folder_id = drive_find_folder(args.project, root_id)
                if project_folder_id:
                    sessions = drive_list_files(project_folder_id)
                    result.append({"project": args.project, "sessions": sessions})
            else:
                folders = drive_list_files(root_id)
                for f in folders:
                    if f.get("mimeType") == "application/vnd.google-apps.folder":
                        sessions = drive_list_files(f["id"])
                        result.append({"project": f["name"], "sessions": sessions})
            print(json.dumps(result, ensure_ascii=False))
            return

        if args.project:
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
