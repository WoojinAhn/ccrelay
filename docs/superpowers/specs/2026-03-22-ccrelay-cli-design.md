# ccrelay CLI Design Spec

## Overview

A CLI tool that selectively syncs Claude Code sessions between machines via Google Drive.
"Relay race baton pass" metaphor — hand off session context to the next machine.

## Motivation

- Claude Code sessions are stored locally (`~/.claude/`) only — no cross-machine access
- Official Remote Control requires the original terminal to stay open
- Third-party tools like claude-sync sync the entire `~/.claude` — no selective sync
- **No tool exists for "shut down machine A, continue a specific session on machine B"**

## Architecture

### Single Script

`ccrelay.py` — all logic in one file. Zero dependencies (Python stdlib only).
`gws` CLI is an external prerequisite, invoked via `subprocess`.

### Session File Structure (Verified)

```
~/.claude/
  projects/{project_path}/
    {uuid}.jsonl                    (main conversation log)
    {uuid}/subagents/
      agent-*.jsonl                 (subagent logs)
      agent-*.meta.json             (subagent metadata)
  sessions/
    {pid}.json                      (session index, e.g. {"pid":42366, "sessionId":"2a671b32-...", "cwd":"..."})
  transcripts/
    ses_*.jsonl                     (NOT needed for resume — independent data with separate ID scheme)
```

`claude --resume` uses the `sessions/` index to locate project JSONL files. Transcripts are excluded from scope.

### Data Flow

```
[push]
~/.claude/projects/{project_path}/
  {uuid}.jsonl + {uuid}/subagents/*
  -> tar.gz bundle
  -> gws drive files create -> Google Drive ccrelay/{project_path}/

[pull]
Google Drive ccrelay/{project_path}/
  -> gws drive files get (alt=media) -> temp directory
  -> extract tar.gz -> ~/.claude/projects/{project_path}/
  -> create ~/.claude/sessions/{pid}.json index entry
  (timestamp comparison -> warn on conflict)

[list]
Google Drive ccrelay/
  -> gws drive files list -> print session list
```

### Why tar.gz

A single session consists of a main JSONL file plus a `{uuid}/subagents/` directory
with `.jsonl` and `.meta.json` files. Bundling into one tar.gz means one API call
per push/pull and preserves directory structure.

## CLI Interface

```bash
# Current directory based
ccrelay push              # interactive session picker -> push
ccrelay pull              # Drive session list -> pick -> pull
ccrelay list              # list sessions on Drive
ccrelay help              # usage info

# Explicit project
ccrelay push --project cclanes
ccrelay pull --project cclanes
ccrelay list --project cclanes
```

### Project Path Resolution

- No `--project`: `os.getcwd()` -> convert to Claude project path format
  (e.g., `/Users/woojin/home/ccrelay` -> `-Users-woojin-home-ccrelay`)
- With `--project`: suffix match against `~/.claude/projects/` entries
  (e.g., `--project cclanes` matches `-Users-woojin-home-cclanes`)

### Session Picker (push)

```
Project: ccrelay (-Users-woojin-home-ccrelay)
Sessions:
  1. 2a671b32-... (2026-03-22 01:43, 692KB)
  2. f8a1c3e9-... (2026-03-21 18:20, 1.2MB)

Select number:
```

Simple numbered selection. Interactive TUI deferred to skill phase.

## Google Drive Structure

```
ccrelay/                                  (root folder, auto-created)
  -Users-woojin-home-ccrelay/             (per-project folder, auto-created)
    2a671b32-..._2026-03-22.tar.gz
    f8a1c3e9-..._2026-03-21.tar.gz
  -Users-woojin-home-cclanes/
    ...
```

### File Naming

`{session_uuid}_{date}.tar.gz`

Re-pushing the same session updates the existing file (matched by UUID prefix).

### gws CLI Calls

```python
# Create folder
subprocess.run(["gws", "drive", "files", "create",
    "--json", '{"name": "...", "mimeType": "application/vnd.google-apps.folder", "parents": ["..."]}'])

# Upload
subprocess.run(["gws", "drive", "files", "create",
    "--json", '{"name": "...", "parents": ["..."]}',
    "--upload", "./session.tar.gz"])

# Download (alt=media required for binary content)
subprocess.run(["gws", "drive", "files", "get",
    "--params", '{"fileId": "...", "alt": "media"}',
    "--output", "./session.tar.gz"])

# Update existing file (re-push)
subprocess.run(["gws", "drive", "files", "update",
    "--params", '{"fileId": "..."}',
    "--upload", "./session.tar.gz"])

# List
subprocess.run(["gws", "drive", "files", "list",
    "--params", '{"q": "\"...\" in parents", "pageSize": 100}'])
```

## Conflict Handling

### Pull

1. Download tar.gz from Drive to temp directory
2. Check if same session exists locally
3. If not exists -> restore directly
4. If exists -> compare local mtime vs Drive modifiedTime
   - Drive is newer -> overwrite
   - Local is newer -> warn + confirmation prompt

```
Warning: local file is newer
  Local:  2026-03-22 14:30
  Remote: 2026-03-22 13:00
Overwrite? [y/N]
```

### Push

If same UUID file exists on Drive, update without prompt (push = I'm uploading the latest).

## Configuration

`~/.config/ccrelay/config.json`:

```json
{
  "drive_folder_id": "1AlKrdvbnc1izzFT3XbG_CelJ_Z-nI0du",
  "claude_dir": "~/.claude"
}
```

- First run: search for `ccrelay` folder on Drive, create if missing
- Cache folder ID in config to avoid repeated API lookups

## Error Handling

- `gws` not installed -> print install instructions (`brew install googleworkspace-cli`)
- `gws` not authenticated -> print `gws auth setup --login` instructions
- Network failure -> print error from gws, suggest retry
- No sessions found -> clear message

## Future (Out of Scope)

- Claude Code skill/command wrapping (after standalone CLI is validated)
- Interactive TUI picker (curses/fzf)
- Multiple storage backends
- Google OAuth app verification for public distribution
