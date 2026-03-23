"""Google Drive operations via gws CLI."""

import json
import os
import subprocess


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
    abs_path = os.path.abspath(output_path)
    file_dir = os.path.dirname(abs_path)
    file_name = os.path.basename(abs_path)
    params = json.dumps({"fileId": file_id, "alt": "media"})
    gws_run([
        "drive", "files", "get",
        "--params", params,
        "--output", file_name,
    ], cwd=file_dir)


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
