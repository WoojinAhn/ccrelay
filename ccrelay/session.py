"""Session operations: scanning, bundling, restoring, labeling."""

import json
import os
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

from ccrelay.utils import DEFAULT_CLAUDE_DIR, project_path_to_cwd


def extract_session_label(jsonl_path: str, max_len: int = 60) -> str | None:
    """Extract a human-readable label from a session JSONL file.

    Priority:
      1. custom-title message (set via claude --name)
      2. First user message text
    Returns None if neither found. Truncates to max_len.
    """
    custom_title = None
    first_user_msg = None

    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                msg_type = obj.get("type")

                if msg_type == "custom-title":
                    custom_title = obj.get("customTitle")
                    break  # highest priority, stop early

                if msg_type == "user" and first_user_msg is None:
                    content = obj.get("message", {}).get("content", obj.get("content"))
                    if isinstance(content, list):
                        for c in content:
                            if isinstance(c, dict) and c.get("type") == "text":
                                first_user_msg = c["text"]
                                break
                    elif isinstance(content, str):
                        first_user_msg = content
    except (OSError, UnicodeDecodeError):
        return None

    label = custom_title or first_user_msg
    if label is None:
        return None
    label = label.replace("\n", " ").strip()
    if len(label) > max_len:
        label = label[:max_len] + "..."
    return label


def list_local_sessions(project_path: str, claude_dir: Path = DEFAULT_CLAUDE_DIR) -> list[dict]:
    """List local sessions for a project.
    Scans claude_dir/projects/{project_path}/ for *.jsonl files.
    Returns list of dicts with keys: uuid, path, size, mtime, label
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

        label = extract_session_label(str(f))

        sessions.append({
            "uuid": uuid,
            "path": str(f),
            "size": size,
            "mtime": datetime.fromtimestamp(f.stat().st_mtime),
            "label": label,
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
