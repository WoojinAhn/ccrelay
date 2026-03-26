"""Path resolution and formatting utilities."""

import os
from datetime import datetime
from pathlib import Path

DEFAULT_CLAUDE_DIR = Path.home() / ".claude"
CONFIG_DIR = Path.home() / ".config" / "ccrelay"
CONFIG_FILE = CONFIG_DIR / "config.json"


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


def project_path_to_cwd(project_path: str) -> str:
    """Reverse of cwd_to_project_path. Convert '-Users-woojin-home-ccrelay' back to '/Users/woojin/home/ccrelay'.
    Strategy: replace '-' with '/' and ensure it starts with '/'.
    Note: This is a best-effort approximation since the conversion is lossy
    (paths with dashes are ambiguous). For the user's consistent ~/home/{project} layout, it works.
    """
    if not project_path:
        return "/"
    return project_path.replace("-", "/")


def format_size(size_str: str) -> str:
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


def format_time(time_str: str) -> str:
    """Format ISO time string to 'YYYY-MM-DD HH:MM' in local timezone."""
    try:
        dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        local_dt = dt.astimezone()
        return local_dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError, AttributeError):
        return "unknown"
