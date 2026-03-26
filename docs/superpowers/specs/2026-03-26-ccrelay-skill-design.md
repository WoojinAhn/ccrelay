# ccrelay Slash Command Design Spec

## Overview

Wrap ccrelay CLI as a Claude Code slash command (`/relay`) so users can push/pull/list sessions through natural conversation instead of manual CLI invocation.

## Approach

Single slash command file at `~/.claude/commands/relay.md`. Claude orchestrates the flow using Bash + AskUserQuestion.

## CLI Extensions (ccrelay.py)

Add two flags to existing subcommands:

### `--json`

Output machine-readable JSON instead of human-formatted text. When used with `push` or `pull`, outputs the session list and exits without executing.

```bash
python3 /Users/woojin/home/ccrelay/ccrelay.py push --json
# [{"uuid": "9f2fc8f2-...", "label": "이슈 16 진행", "size": 3849300, "mtime": "2026-03-20T16:09:08"}]

python3 /Users/woojin/home/ccrelay/ccrelay.py list --json
# [{"project": "-Users-woojin-home-cclanes", "sessions": [{"name": "...", "size": "...", "modifiedTime": "..."}]}]

python3 /Users/woojin/home/ccrelay/ccrelay.py pull --json
# [{"id": "file_xyz", "name": "9f2fc8f2-..._2026-03-23.tar.gz", "size": "820898", "modifiedTime": "...", "uuid": "9f2fc8f2-..."}]
```

Notes:
- `mtime` in push --json: convert `datetime` to ISO 8601 string in cli.py
- `uuid` in pull --json: extracted from filename (`{uuid}_{date}.tar.gz`)
- pull has no session label (label is inside the tar.gz, not accessible from Drive metadata). AskUserQuestion shows UUID + size + date only.

### `--session <uuid>`

Skip interactive picker, execute directly with the specified session.

```bash
python3 /Users/woojin/home/ccrelay/ccrelay.py push --session 9f2fc8f2-...
python3 /Users/woojin/home/ccrelay/ccrelay.py pull --session 9f2fc8f2-...
```

For pull: `--session` takes a UUID prefix. Internally, the CLI queries Drive file list and matches by UUID prefix in the filename, then downloads and restores.

### Flag Combinations

- No flags: existing interactive behavior unchanged
- `--json` only: list and exit
- `--session` only: execute without picker, human-readable output
- `--json` + `--session`: execute without picker, JSON result output

## Slash Command Definition

### File

`~/.claude/commands/relay.md`

Uses absolute path for ccrelay: `python3 /Users/woojin/home/ccrelay/ccrelay.py`
(Same pattern as lanes.md: `python3 /Users/woojin/home/cclanes/cclanes.py`)

### Frontmatter

```yaml
---
description: Relay Claude Code sessions to/from Google Drive
argument-hint: push|pull|list [--project PROJECT]
allowed-tools: Bash, AskUserQuestion
---
```

### Command Flows

#### `/relay push [--project PROJECT]`

1. Parse subcommand and --project from user input
2. Run `python3 /Users/woojin/home/ccrelay/ccrelay.py push --json [--project PROJECT]` to get local session list
3. If empty: inform user, stop
4. Present sessions via AskUserQuestion (take first 4 from JSON array — already sorted by most recent)
   - Label: session label or UUID (truncated)
   - Description: size + date
5. Run `python3 /Users/woojin/home/ccrelay/ccrelay.py push --session <selected_uuid> [--project PROJECT]`
6. Report result

#### `/relay pull [--project PROJECT]`

1. Parse subcommand and --project from user input
2. Run `python3 /Users/woojin/home/ccrelay/ccrelay.py pull --json [--project PROJECT]` to get Drive session list
3. If empty: inform user, stop
4. Present sessions via AskUserQuestion (first 4)
   - Label: UUID (extracted from filename)
   - Description: size + date
5. Run `python3 /Users/woojin/home/ccrelay/ccrelay.py pull --session <selected_uuid> [--project PROJECT]`
6. Post-pull resume:
   - Check `CMUX_WORKSPACE_ID` env var
   - If set: derive project cwd, run `cmux new-workspace --cwd <project_dir> --command "claude --resume <uuid>"`
   - If cmux fails or not set: `echo "claude --resume <uuid>" | pbcopy` (macOS), print resume instructions
   - Always print the resume command as text fallback

#### `/relay list [--project PROJECT]`

1. Run `python3 /Users/woojin/home/ccrelay/ccrelay.py list [--project PROJECT]`
2. Present output as-is

### Instruction Notes for relay.md

- `$ARGUMENTS` contains everything after `/relay` — parse the first word as subcommand (push/pull/list), pass remaining flags through
- `--project` must be forwarded to both `--json` and `--session` calls
- AskUserQuestion max 4 options — slice JSON array in the instruction

## Files to Create/Modify

| File | Action |
|------|--------|
| `~/.claude/commands/relay.md` | Create — slash command definition |
| `ccrelay/cli.py` | Add `--json`, `--session` flags to argparse and cmd handlers |
| `test_cli.py` | Tests for new flag parsing |
| `test_push.py` | Tests for `--json` output and `--session` push |
| `test_pull.py` | Tests for `--json` output and `--session` pull |

## Testing

### Unit tests (automated)
- `--json` flag produces valid JSON for push/pull/list
- `--session` flag bypasses picker and executes
- `--json --session` produces JSON result

### Manual verification checklist
- [ ] `/relay push` — presents AskUserQuestion, uploads selected session
- [ ] `/relay pull` — presents AskUserQuestion, downloads, cmux resume or pbcopy
- [ ] `/relay list` — shows Drive sessions
- [ ] `/relay push --project cclanes` — project flag forwarded correctly

## Out of Scope

- TUI picker (#10) — deferred until skill usage patterns are clear
- Auto-invocation by Claude — explicit `/relay` only
- Linux clipboard support (xclip/xsel) — macOS only for now
