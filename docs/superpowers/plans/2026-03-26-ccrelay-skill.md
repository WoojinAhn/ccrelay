# ccrelay Slash Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wrap ccrelay CLI as `/relay` slash command with `--json` and `--session` flags for machine-readable orchestration.

**Architecture:** Add `--json`/`--session` flags to cli.py argparse + cmd handlers. Create `~/.claude/commands/relay.md` that uses Bash + AskUserQuestion to orchestrate push/pull/list flows.

**Tech Stack:** Python stdlib, Claude Code slash command (markdown)

---

### Task 1: Add `--json` and `--session` flags to argparse

**Files:**
- Modify: `ccrelay/cli.py:34-60` (build_parser)
- Test: `test_cli.py`

- [ ] **Step 1: Write failing tests for new flags**

Add to `test_cli.py`:

```python
class TestNewFlags(unittest.TestCase):
    def test_push_json_flag(self):
        parser = build_parser()
        args = parser.parse_args(["push", "--json"])
        self.assertTrue(args.json)

    def test_push_session_flag(self):
        parser = build_parser()
        args = parser.parse_args(["push", "--session", "abc-123"])
        self.assertEqual(args.session, "abc-123")

    def test_pull_json_flag(self):
        parser = build_parser()
        args = parser.parse_args(["pull", "--json"])
        self.assertTrue(args.json)

    def test_pull_session_flag(self):
        parser = build_parser()
        args = parser.parse_args(["pull", "--session", "abc-123"])
        self.assertEqual(args.session, "abc-123")

    def test_list_json_flag(self):
        parser = build_parser()
        args = parser.parse_args(["list", "--json"])
        self.assertTrue(args.json)

    def test_default_json_false(self):
        parser = build_parser()
        args = parser.parse_args(["push"])
        self.assertFalse(args.json)

    def test_default_session_none(self):
        parser = build_parser()
        args = parser.parse_args(["push"])
        self.assertIsNone(args.session)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest test_cli.TestNewFlags -v`
Expected: FAIL — `args` has no attribute `json`

- [ ] **Step 3: Implement — add flags to build_parser**

In `ccrelay/cli.py`, modify the loop in `build_parser()`:

```python
for name, help_text in help_texts.items():
    sub = subparsers.add_parser(name, help=help_text)
    sub.add_argument("--project", default=None, help=project_help)
    sub.add_argument("--json", action="store_true", default=False,
                     help="Output machine-readable JSON")
    if name in ("push", "pull"):
        sub.add_argument("--session", default=None,
                         help="Session UUID to use (skip interactive picker)")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest test_cli.TestNewFlags -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ccrelay/cli.py test_cli.py
git commit -m "feat(#9): add --json and --session flags to argparse"
```

---

### Task 2: Update existing tests for new args (MUST come before Task 3)

**Files:**
- Modify: `test_push.py`, `test_pull.py`, `test_list_config.py`, `test_e2e.py`

Existing tests create `Namespace(command="push", project=None)` without `json` and `session` fields. Since `cmd_push/pull/list` will use `args.json` directly (not `getattr`), these tests will break when we implement the flags. Fix them first.

**IMPORTANT:** `test_pull.py` uses `MagicMock()` for args in `TestCmdPull._make_args`. MagicMock auto-creates attributes as truthy MagicMock objects, so `args.json` would be truthy and route into the `--json` branch. Convert these to `Namespace` objects.

- [ ] **Step 1: Update all `_make_args` and `Namespace(...)` calls**

- `test_push.py` `TestCmdPush._make_args`: `return Namespace(command="push", project=project, json=False, session=None)`
- `test_pull.py` `TestCmdPull._make_args`: change from `MagicMock()` to `return Namespace(command="pull", project=project, json=False, session=None)`
- `test_list_config.py` `TestCmdList._make_args`: `return Namespace(command="list", project=project, json=False)`
- `test_e2e.py`: update all `Namespace(...)` calls to include `json=False, session=None` (or `json=False` for list)

- [ ] **Step 2: Run full suite**

Run: `python3 -m unittest discover`
Expected: all 120 tests pass

- [ ] **Step 3: Commit**

```bash
git add test_push.py test_pull.py test_list_config.py test_e2e.py
git commit -m "test(#9): update existing tests for new flag args"
```

---

### Task 3: Implement `push --json` and `push --session`

**Files:**
- Modify: `ccrelay/cli.py:83-130` (cmd_push)
- Test: `test_push.py`

- [ ] **Step 1: Write failing tests**

Add to `test_push.py` (include `import io` at top):

```python
class TestCmdPushJson(unittest.TestCase):
    def _make_args(self, project=None, json_flag=False, session=None):
        return Namespace(command="push", project=project, json=json_flag, session=session)

    @patch("ccrelay.cli.check_gws_available", return_value=True)
    @patch("ccrelay.cli.resolve_project_path", return_value="-Users-woojin-home-ccrelay")
    @patch("ccrelay.cli.list_local_sessions")
    def test_json_outputs_session_list(self, mock_list, mock_resolve, mock_check):
        mock_list.return_value = [
            {"uuid": "abc-123", "path": "/tmp/abc.jsonl", "size": 1024,
             "mtime": datetime(2026, 3, 22, 14, 30), "label": "test session"},
        ]
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            cmd_push(self._make_args(json_flag=True))
            output = json.loads(mock_out.getvalue())
        self.assertEqual(len(output), 1)
        self.assertEqual(output[0]["uuid"], "abc-123")
        self.assertEqual(output[0]["label"], "test session")
        self.assertIn("mtime", output[0])

    @patch("ccrelay.cli.check_gws_available", return_value=True)
    @patch("ccrelay.cli.resolve_project_path", return_value="-Users-woojin-home-ccrelay")
    @patch("ccrelay.cli.list_local_sessions", return_value=[])
    def test_json_empty_list(self, mock_list, mock_resolve, mock_check):
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            cmd_push(self._make_args(json_flag=True))
            output = json.loads(mock_out.getvalue())
        self.assertEqual(output, [])

    @patch("ccrelay.cli.check_gws_available", return_value=True)
    @patch("ccrelay.cli.resolve_project_path", return_value="-Users-woojin-home-ccrelay")
    @patch("ccrelay.cli.list_local_sessions")
    @patch("ccrelay.cli.bundle_session", return_value="/tmp/abc-123_2026-03-22.tar.gz")
    @patch("ccrelay.cli.ensure_drive_root", return_value="root_123")
    @patch("ccrelay.cli.drive_find_folder", return_value="proj_folder")
    @patch("ccrelay.cli.drive_list_files", return_value=[])
    @patch("ccrelay.cli.drive_upload", return_value="file_id")
    @patch("os.remove")
    def test_session_flag_skips_picker(self, mock_rm, mock_upload, mock_list_files,
                                        mock_find, mock_root, mock_bundle,
                                        mock_list, mock_resolve, mock_check):
        mock_list.return_value = [
            {"uuid": "abc-123", "path": "/tmp/abc.jsonl", "size": 1024,
             "mtime": datetime(2026, 3, 22), "label": "test"},
        ]
        with patch("builtins.print"):
            cmd_push(self._make_args(session="abc-123"))
        mock_bundle.assert_called_once()

    @patch("ccrelay.cli.check_gws_available", return_value=True)
    @patch("ccrelay.cli.resolve_project_path", return_value="-Users-woojin-home-ccrelay")
    @patch("ccrelay.cli.list_local_sessions")
    def test_session_not_found_exits(self, mock_list, mock_resolve, mock_check):
        mock_list.return_value = [
            {"uuid": "abc-123", "path": "/tmp/abc.jsonl", "size": 1024,
             "mtime": datetime(2026, 3, 22), "label": "test"},
        ]
        with self.assertRaises(SystemExit):
            cmd_push(self._make_args(session="nonexistent"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest test_push.TestCmdPushJson -v`
Expected: FAIL

- [ ] **Step 3: Implement `--json` and `--session` in cmd_push**

In `ccrelay/cli.py` `cmd_push()`, add after session list is retrieved and empty check:

```python
    # --json only: output session list as JSON and exit
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

    # --session: skip picker, find by UUID
    if args.session:
        selected = next((s for s in sessions if s["uuid"] == args.session), None)
        if not selected:
            print(f"Error: Session '{args.session}' not found.", file=sys.stderr)
            sys.exit(1)
        uuid = selected["uuid"]
    else:
        # existing interactive picker code (print list, input, validate)
        ...
```

Note: `--json` empty list case — if `sessions` is empty, the existing empty check returns before reaching `--json` branch. Move `--json` check BEFORE the empty check so it outputs `[]`:

```python
    sessions = list_local_sessions(project_path)

    if args.json and not args.session:
        output = [...]  # as above
        print(json.dumps(output, ensure_ascii=False))
        return

    if not sessions:
        print(f"No local sessions found for project: {project_path}")
        return
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest test_push.TestCmdPushJson -v`
Expected: PASS

- [ ] **Step 5: Run full suite**

Run: `python3 -m unittest discover`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add ccrelay/cli.py test_push.py
git commit -m "feat(#9): push --json and --session implementation"
```

---

### Task 4: Implement `pull --json` and `pull --session`

**Files:**
- Modify: `ccrelay/cli.py:133-250` (cmd_pull)
- Test: `test_pull.py`

- [ ] **Step 1: Write failing tests**

Add to `test_pull.py` (include `import io` at top):

```python
class TestCmdPullJson(unittest.TestCase):
    def _make_args(self, project=None, json_flag=False, session=None):
        return Namespace(command="pull", project=project, json=json_flag, session=session)

    @patch("ccrelay.cli.check_gws_available", return_value=True)
    @patch("ccrelay.cli.resolve_project_path", return_value="-Users-woojin-home-ccrelay")
    @patch("ccrelay.cli.ensure_drive_root", return_value="root_123")
    @patch("ccrelay.cli.load_config", return_value={})
    @patch("ccrelay.cli.drive_find_folder", return_value="proj_folder")
    @patch("ccrelay.cli.drive_list_files")
    def test_json_outputs_drive_list(self, mock_list, mock_find, mock_config,
                                      mock_root, mock_resolve, mock_check):
        mock_list.return_value = [
            {"id": "f1", "name": "abc-123_2026-03-22.tar.gz",
             "size": "820898", "modifiedTime": "2026-03-22T15:55:47.021Z"},
        ]
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            cmd_pull(self._make_args(json_flag=True))
            output = json.loads(mock_out.getvalue())
        self.assertEqual(len(output), 1)
        self.assertEqual(output[0]["uuid"], "abc-123")
        self.assertEqual(output[0]["id"], "f1")

    @patch("ccrelay.cli.check_gws_available", return_value=True)
    @patch("ccrelay.cli.resolve_project_path", return_value="-Users-woojin-home-ccrelay")
    @patch("ccrelay.cli.ensure_drive_root", return_value="root_123")
    @patch("ccrelay.cli.load_config", return_value={})
    @patch("ccrelay.cli.drive_find_folder", return_value="proj_folder")
    @patch("ccrelay.cli.drive_list_files")
    @patch("ccrelay.cli.drive_download")
    @patch("ccrelay.cli.restore_session", return_value="abc-123")
    @patch("ccrelay.cli.create_session_index")
    def test_session_flag_skips_picker(self, mock_index, mock_restore,
                                        mock_download, mock_list, mock_find,
                                        mock_config, mock_root, mock_resolve, mock_check):
        mock_list.return_value = [
            {"id": "f1", "name": "abc-123_2026-03-22.tar.gz",
             "size": "820898", "modifiedTime": "2026-03-22T15:55:47.021Z"},
        ]
        with patch("builtins.print"), \
             patch("ccrelay.cli.DEFAULT_CLAUDE_DIR", Path(tempfile.mkdtemp())):
            cmd_pull(self._make_args(session="abc-123"))
        mock_download.assert_called_once()

    @patch("ccrelay.cli.check_gws_available", return_value=True)
    @patch("ccrelay.cli.resolve_project_path", return_value="-Users-woojin-home-ccrelay")
    @patch("ccrelay.cli.ensure_drive_root", return_value="root_123")
    @patch("ccrelay.cli.load_config", return_value={})
    @patch("ccrelay.cli.drive_find_folder", return_value="proj_folder")
    @patch("ccrelay.cli.drive_list_files")
    def test_session_not_found_exits(self, mock_list, mock_find, mock_config,
                                      mock_root, mock_resolve, mock_check):
        mock_list.return_value = [
            {"id": "f1", "name": "xyz-999_2026-03-22.tar.gz",
             "size": "100", "modifiedTime": "2026-03-22T00:00:00Z"},
        ]
        with self.assertRaises(SystemExit):
            cmd_pull(self._make_args(session="abc-123"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest test_pull.TestCmdPullJson -v`
Expected: FAIL

- [ ] **Step 3: Implement `--json` and `--session` in cmd_pull**

In `cmd_pull()`, add after Drive file list is retrieved and empty check:

```python
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

    # --session: skip picker, match by UUID prefix in filename
    if args.session:
        selected = next((f for f in files if f["name"].startswith(args.session)), None)
        if not selected:
            print(f"Error: Session '{args.session}' not found on Drive.", file=sys.stderr)
            sys.exit(1)
    else:
        # existing interactive picker code
        ...
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest test_pull.TestCmdPullJson -v`
Expected: PASS

- [ ] **Step 5: Run full suite**

Run: `python3 -m unittest discover`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add ccrelay/cli.py test_pull.py
git commit -m "feat(#9): pull --json and --session implementation"
```

---

### Task 5: Implement `list --json`

**Files:**
- Modify: `ccrelay/cli.py:253-299` (cmd_list)
- Test: `test_list_config.py`

- [ ] **Step 1: Write failing test**

Add to `test_list_config.py` (include `import io` at top):

```python
class TestCmdListJson(unittest.TestCase):
    def _make_args(self, project=None, json_flag=False):
        return Namespace(command="list", project=project, json=json_flag)

    @patch("ccrelay.cli.check_gws_available", return_value=True)
    @patch("ccrelay.cli.load_config", return_value={})
    @patch("ccrelay.cli.ensure_drive_root", return_value="root_id")
    @patch("ccrelay.cli.drive_list_files")
    def test_json_all_projects(self, mock_list, mock_root, mock_config, mock_check):
        mock_list.side_effect = [
            [{"id": "f1", "name": "proj1", "mimeType": "application/vnd.google-apps.folder"}],
            [{"id": "s1", "name": "abc_2026.tar.gz", "size": "100", "modifiedTime": "2026-03-22T00:00:00Z"}],
        ]
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            cmd_list(self._make_args(json_flag=True))
            output = json.loads(mock_out.getvalue())
        self.assertEqual(len(output), 1)
        self.assertEqual(output[0]["project"], "proj1")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest test_list_config.TestCmdListJson -v`
Expected: FAIL

- [ ] **Step 3: Implement `--json` in cmd_list**

In `cmd_list()`, add `--json` branch right after `ensure_drive_root`:

```python
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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python3 -m unittest test_list_config.TestCmdListJson -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ccrelay/cli.py test_list_config.py
git commit -m "feat(#9): list --json implementation"
```

---

### Task 6: Create relay.md slash command

**Files:**
- Create: `~/.claude/commands/relay.md`
- Create: `commands/relay.md` (repo tracking copy)

- [ ] **Step 1: Write relay.md**

Create `~/.claude/commands/relay.md` with the slash command definition. Key points:
- Use `$ARGUMENTS` (auto-provided by Claude Code)
- Use `<remaining_flags>` as placeholder notation in instructions (NOT a shell variable)
- Instruct Claude to parse the first word as subcommand and forward remaining flags
- For post-pull resume, derive project_dir by replacing `-` with `/` in the project path (same as `project_path_to_cwd`)

- [ ] **Step 2: Verify file is placed correctly**

Run: `ls -la ~/.claude/commands/relay.md`

- [ ] **Step 3: Copy to repo for tracking and commit**

```bash
mkdir -p /Users/woojin/home/ccrelay/commands
cp ~/.claude/commands/relay.md /Users/woojin/home/ccrelay/commands/relay.md
git add commands/relay.md
git commit -m "feat(#9): add /relay slash command"
```

---

### Task 7: Manual verification

- [ ] **Step 1: Test `/relay list`**

In Claude Code, type `/relay list` and verify Drive sessions are shown.

- [ ] **Step 2: Test `/relay push`**

Type `/relay push`, verify AskUserQuestion appears with session options, select one, verify upload succeeds.

- [ ] **Step 3: Test `/relay pull`**

Type `/relay pull`, verify session selection, download, and resume flow (cmux or pbcopy).

- [ ] **Step 4: Test `/relay push --project cclanes`**

Verify `--project` flag is forwarded correctly.

- [ ] **Step 5: Final push and close issue**

```bash
git push
gh issue close 9 -c "Implemented"
```
