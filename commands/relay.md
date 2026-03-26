---
description: Relay Claude Code sessions to/from Google Drive
argument-hint: push|pull|list [--project PROJECT]
allowed-tools: Bash, AskUserQuestion
---

Relay Claude Code sessions between machines via Google Drive.

Parse `$ARGUMENTS`: the first word is the subcommand (`push`, `pull`, or `list`). Any remaining flags (e.g., `--project PROJECT`) must be forwarded to ALL ccrelay calls.

## push

1. Get local session list:
```bash
python3 /Users/woojin/home/ccrelay/ccrelay.py push --json <remaining_flags> 2>&1
```

2. If the JSON array is empty, tell the user "No local sessions found." and stop.

3. Take the first 4 entries from the array (already sorted most recent first). Use the AskUserQuestion tool:
   - Label: the `label` field if present, otherwise first 12 chars of `uuid`
   - Description: human-readable size + mtime (convert to user's local timezone if needed)

4. Push the selected session:
```bash
python3 /Users/woojin/home/ccrelay/ccrelay.py push --session <selected_uuid> <remaining_flags> 2>&1
```

5. Report the result to the user.

## pull

1. Get Drive session list:
```bash
python3 /Users/woojin/home/ccrelay/ccrelay.py pull --json <remaining_flags> 2>&1
```

2. If the JSON array is empty, tell the user "No sessions found on Drive." and stop.

3. Take the first 4 entries. Use AskUserQuestion:
   - Label: `label` field if present, otherwise first 12 chars of `uuid`
   - Description: human-readable size + modifiedTime (convert UTC to user's local timezone)

4. Pull the selected session:
```bash
python3 /Users/woojin/home/ccrelay/ccrelay.py pull --session <selected_uuid> <remaining_flags> 2>&1
```

5. After pull completes, help the user resume the session:
   - Check if `CMUX_WORKSPACE_ID` environment variable is set (run `echo $CMUX_WORKSPACE_ID`)
   - If set: derive the project directory by replacing `-` with `/` in the project path (e.g., `-Users-woojin-home-ccrelay` → `/Users/woojin/home/ccrelay`). Then run:
     ```bash
     cmux new-workspace --cwd <project_dir> --command "claude --resume <uuid>"
     ```
   - If not set, or if cmux command fails: copy resume command to clipboard:
     ```bash
     echo "claude --resume <uuid>" | pbcopy
     ```
     Tell the user: "Resume command copied to clipboard."
   - Always print: `claude --resume <uuid>` as text so the user can see it.

## list

Run and present output as-is:
```bash
python3 /Users/woojin/home/ccrelay/ccrelay.py list <remaining_flags> 2>&1
```

## Notes

- `<remaining_flags>` is a placeholder — substitute the actual flags parsed from `$ARGUMENTS` (e.g., `--project cclanes`). Do NOT use it as a literal shell variable.
- `<selected_uuid>` — the full UUID from the user's AskUserQuestion selection.
- `<uuid>` in the resume step — the UUID printed in ccrelay's pull output.
