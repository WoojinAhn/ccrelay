# ccrelay

Selectively relay Claude Code sessions between machines via Google Drive.

"Relay race baton pass" — hand off session context to the next machine.

## Why

Claude Code sessions live in `~/.claude/` and can't move between machines. ccrelay lets you **push** a specific session from machine A and **pull** it on machine B, then `claude --resume` to continue.

## Prerequisites

- Python 3.10+
- [Google Workspace CLI](https://github.com/googleworkspace/cli) (`gws`)
- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) (`gcloud`) — for initial setup only

## Setup

```bash
# 1. Install gws
brew install googleworkspace-cli

# 2. Install gcloud (for initial OAuth setup)
brew install --cask google-cloud-sdk
export PATH="/opt/homebrew/share/google-cloud-sdk/bin:$PATH"

# 3. Setup & authenticate (opens browser)
gws auth setup --login

# 4. Add yourself as a test user in Google Cloud Console
#    https://console.cloud.google.com/apis/credentials/consent
#    → Test users → Add users → your email

# 5. Login with Drive scope
gws auth login -s drive
```

## Usage

```bash
# Push a session to Google Drive (from project directory)
python3 ccrelay.py push

# Pull a session from Google Drive
python3 ccrelay.py pull

# List sessions on Google Drive
python3 ccrelay.py list

# Specify a different project
python3 ccrelay.py push --project cclanes
python3 ccrelay.py list --project cclanes
```

After pulling, resume the session:

```bash
claude --resume <session-uuid>
```

## How It Works

1. **push**: Bundles session files (`{uuid}.jsonl` + `subagents/`) into a `tar.gz`, uploads to Google Drive under `ccrelay/{project-path}/`
2. **pull**: Downloads `tar.gz` from Drive, extracts to `~/.claude/projects/`, creates session index for `claude --resume`
3. **list**: Shows sessions stored on Drive

Sessions are matched by UUID — re-pushing updates the existing file.

## Config

Stored at `~/.config/ccrelay/config.json`:

```json
{
  "drive_folder_id": "..."
}
```

Auto-created on first run.

## Testing

```bash
python3 -m unittest discover -v
```

102 tests (unit + e2e).
