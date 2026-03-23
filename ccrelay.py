#!/usr/bin/env python3
"""ccrelay — backward-compatible entry point. Use `python -m ccrelay` instead."""

# Re-export everything for backward compatibility with existing tests
from ccrelay.utils import (  # noqa: F401
    DEFAULT_CLAUDE_DIR,
    CONFIG_DIR,
    CONFIG_FILE,
    cwd_to_project_path,
    resolve_project_path,
    project_path_to_cwd,
    format_size as _format_size,
    format_time as _format_time,
)
from ccrelay.drive import (  # noqa: F401
    check_gws_available,
    gws_run,
    drive_create_folder,
    drive_upload,
    drive_update,
    drive_download,
    drive_list_files,
    drive_find_folder,
)
from ccrelay.config import (  # noqa: F401
    load_config,
    save_config,
    ensure_drive_root,
)
from ccrelay.session import (  # noqa: F401
    extract_session_label,
    list_local_sessions,
    bundle_session,
    restore_session,
    create_session_index,
)
from ccrelay.cli import (  # noqa: F401
    build_parser,
    cmd_push,
    cmd_pull,
    cmd_list,
    _print_gws_error,
    _print_sessions,
    main,
)

if __name__ == "__main__":
    main()
