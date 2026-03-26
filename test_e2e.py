"""End-to-end tests for ccrelay CLI.

Tests the full command flows with mocked Drive operations (no real gws calls).
"""

import json
import os
import shutil
import sys
import tarfile
import tempfile
import unittest
from argparse import Namespace
from datetime import datetime
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import ccrelay
from ccrelay import (
    build_parser,
    cmd_list,
    cmd_pull,
    cmd_push,
    main,
)


class E2EPushTest(unittest.TestCase):
    """E2E test for the push flow: scan local sessions, bundle, upload."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.claude_dir = Path(self.tmpdir) / ".claude"
        self.project_path = "-Users-woojin-home-ccrelay"
        self.project_dir = self.claude_dir / "projects" / self.project_path
        self.project_dir.mkdir(parents=True)

        # Create a real local session file
        self.uuid = "abc12345-1234-1234-1234-123456789abc"
        session_file = self.project_dir / f"{self.uuid}.jsonl"
        session_file.write_text('{"type":"summary","summary":"test session"}\n')

        # Create subagents directory
        subagents_dir = self.project_dir / self.uuid / "subagents"
        subagents_dir.mkdir(parents=True)
        (subagents_dir / "agent-001.jsonl").write_text('{"type":"agent"}\n')

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    @patch("ccrelay.cli.drive_upload", return_value="uploaded_file_id")
    @patch("ccrelay.cli.drive_list_files", return_value=[])
    @patch("ccrelay.cli.drive_create_folder", return_value="proj_folder_id")
    @patch("ccrelay.cli.drive_find_folder", return_value=None)
    @patch("ccrelay.cli.ensure_drive_root", return_value="root_id")
    @patch("ccrelay.cli.load_config", return_value={})
    @patch("ccrelay.cli.check_gws_available", return_value=True)
    @patch("builtins.input", return_value="1")
    def test_push_full_flow(
        self, mock_input, mock_gws, mock_config, mock_root,
        mock_find, mock_create, mock_list_files, mock_upload,
    ):
        """Full push: scan sessions, select, bundle, upload, clean temp."""
        args = Namespace(command="push", project=None, json=False, session=None)
        with patch("ccrelay.utils.os.getcwd", return_value="/Users/woojin/home/ccrelay"), \
             patch("ccrelay.cli.DEFAULT_CLAUDE_DIR", self.claude_dir), \
             patch("ccrelay.cli.list_local_sessions") as mock_scan, \
             patch("ccrelay.cli.bundle_session") as mock_bundle, \
             patch("builtins.print"):

            mock_scan.return_value = [
                {
                    "uuid": self.uuid,
                    "path": str(self.project_dir / f"{self.uuid}.jsonl"),
                    "size": 1024,
                    "mtime": datetime(2026, 3, 22, 10, 0, 0),
                },
            ]
            tar_path = os.path.join(self.tmpdir, f"{self.uuid}_2026-03-22.tar.gz")
            # Create a real temp file so os.remove doesn't fail
            with open(tar_path, "w") as f:
                f.write("fake tar")
            mock_bundle.return_value = tar_path

            cmd_push(args)

        # Verify upload was called with correct args
        mock_upload.assert_called_once()
        upload_args = mock_upload.call_args[0]
        self.assertEqual(upload_args[0], tar_path)
        self.assertIn(self.uuid, upload_args[1])
        # tar file should have been cleaned up
        self.assertFalse(os.path.exists(tar_path))
        # Verify project folder was created
        mock_create.assert_called_once_with(self.project_path, "root_id")

    @patch("ccrelay.cli.drive_update", return_value="updated_file_id")
    @patch("ccrelay.cli.drive_list_files")
    @patch("ccrelay.cli.drive_find_folder", return_value="existing_proj_folder")
    @patch("ccrelay.cli.ensure_drive_root", return_value="root_id")
    @patch("ccrelay.cli.load_config", return_value={})
    @patch("ccrelay.cli.check_gws_available", return_value=True)
    @patch("builtins.input", return_value="1")
    def test_push_updates_existing(
        self, mock_input, mock_gws, mock_config, mock_root,
        mock_find, mock_list_files, mock_update,
    ):
        """Re-push: existing file on Drive gets updated."""
        mock_list_files.return_value = [
            {"id": "old_file_id", "name": f"{self.uuid}_2026-03-20.tar.gz"},
        ]

        args = Namespace(command="push", project=None, json=False, session=None)
        tar_path = os.path.join(self.tmpdir, f"{self.uuid}_2026-03-22.tar.gz")
        with open(tar_path, "w") as f:
            f.write("fake tar")

        with patch("ccrelay.utils.os.getcwd", return_value="/Users/woojin/home/ccrelay"), \
             patch("ccrelay.cli.DEFAULT_CLAUDE_DIR", self.claude_dir), \
             patch("ccrelay.cli.list_local_sessions") as mock_scan, \
             patch("ccrelay.cli.bundle_session", return_value=tar_path), \
             patch("builtins.print"):
            mock_scan.return_value = [
                {
                    "uuid": self.uuid,
                    "path": str(self.project_dir / f"{self.uuid}.jsonl"),
                    "size": 1024,
                    "mtime": datetime(2026, 3, 22, 10, 0, 0),
                },
            ]
            cmd_push(args)

        mock_update.assert_called_once()
        self.assertEqual(mock_update.call_args[0][0], "old_file_id")


class E2EPullTest(unittest.TestCase):
    """E2E test for the pull flow: list Drive sessions, select, download, extract, index."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.claude_dir = Path(self.tmpdir) / ".claude"
        self.claude_dir.mkdir()
        self.project_path = "-Users-woojin-home-ccrelay"
        self.uuid = "abc12345-1234-1234-1234-123456789abc"

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _create_real_tar_bytes(self) -> bytes:
        """Create a real tar.gz bundle in memory for download mock."""
        import io
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            content = b'{"type":"summary","summary":"pulled session"}\n'
            info = tarfile.TarInfo(name=f"{self.uuid}.jsonl")
            info.size = len(content)
            tf.addfile(info, io.BytesIO(content))
        return buf.getvalue()

    @patch("ccrelay.cli.create_session_index")
    @patch("ccrelay.cli.restore_session")
    @patch("ccrelay.cli.drive_download")
    @patch("ccrelay.cli.drive_list_files")
    @patch("ccrelay.cli.drive_find_folder", return_value="proj_folder_id")
    @patch("ccrelay.cli.ensure_drive_root", return_value="root_id")
    @patch("ccrelay.cli.load_config", return_value={})
    @patch("ccrelay.cli.check_gws_available", return_value=True)
    @patch("builtins.input", return_value="1")
    def test_pull_full_flow(
        self, mock_input, mock_gws, mock_config, mock_root,
        mock_find, mock_list_files, mock_download, mock_restore, mock_index,
    ):
        """Full pull: list, select, download, restore, create session index."""
        tar_name = f"{self.uuid}_2026-03-22.tar.gz"
        mock_list_files.return_value = [
            {
                "id": "file_001",
                "name": tar_name,
                "size": "4096",
                "modifiedTime": "2026-03-22T10:00:00Z",
            },
        ]
        mock_restore.return_value = self.uuid

        # When drive_download is called, write a real tar.gz to the output path
        tar_data = self._create_real_tar_bytes()

        def fake_download(file_id, output_path):
            with open(output_path, "wb") as f:
                f.write(tar_data)

        mock_download.side_effect = fake_download

        args = Namespace(command="pull", project=None, json=False, session=None)
        with patch("ccrelay.utils.os.getcwd", return_value="/Users/woojin/home/ccrelay"), \
             patch("ccrelay.cli.DEFAULT_CLAUDE_DIR", self.claude_dir), \
             patch("builtins.print") as mock_print:
            cmd_pull(args)

        # Verify download was called
        mock_download.assert_called_once()
        # Verify restore was called with the downloaded tar and correct project path
        mock_restore.assert_called_once()
        restore_args = mock_restore.call_args[0]
        self.assertIn(tar_name, restore_args[0])
        self.assertEqual(restore_args[1], self.project_path)
        # Verify session index was created
        mock_index.assert_called_once_with(self.uuid, self.project_path)
        # Verify success message printed
        printed = " ".join(str(c) for c in mock_print.call_args_list)
        self.assertIn(self.uuid, printed)
        self.assertIn("claude --resume", printed)

    @patch("ccrelay.cli.create_session_index")
    @patch("ccrelay.cli.drive_download")
    @patch("ccrelay.cli.drive_list_files")
    @patch("ccrelay.cli.drive_find_folder", return_value="proj_folder_id")
    @patch("ccrelay.cli.ensure_drive_root", return_value="root_id")
    @patch("ccrelay.cli.load_config", return_value={})
    @patch("ccrelay.cli.check_gws_available", return_value=True)
    @patch("builtins.input", return_value="1")
    def test_pull_temp_cleaned_up(
        self, mock_input, mock_gws, mock_config, mock_root,
        mock_find, mock_list_files, mock_download, mock_index,
    ):
        """Temp directory should be cleaned up after pull completes."""
        tar_name = f"{self.uuid}_2026-03-22.tar.gz"
        mock_list_files.return_value = [
            {
                "id": "file_001",
                "name": tar_name,
                "size": "4096",
                "modifiedTime": "2026-03-22T10:00:00Z",
            },
        ]

        tar_data = self._create_real_tar_bytes()
        downloaded_paths = []

        def fake_download(file_id, output_path):
            downloaded_paths.append(os.path.dirname(output_path))
            with open(output_path, "wb") as f:
                f.write(tar_data)

        mock_download.side_effect = fake_download

        args = Namespace(command="pull", project=None, json=False, session=None)
        with patch("ccrelay.utils.os.getcwd", return_value="/Users/woojin/home/ccrelay"), \
             patch("ccrelay.cli.DEFAULT_CLAUDE_DIR", self.claude_dir), \
             patch("builtins.print"):
            cmd_pull(args)

        # The temp directory where tar was downloaded should be cleaned up
        self.assertEqual(len(downloaded_paths), 1)
        self.assertFalse(os.path.exists(downloaded_paths[0]))


class E2EListTest(unittest.TestCase):
    """E2E test for the list flow."""

    @patch("ccrelay.cli.drive_list_files")
    @patch("ccrelay.cli.ensure_drive_root", return_value="root_id")
    @patch("ccrelay.cli.load_config", return_value={})
    @patch("ccrelay.cli.check_gws_available", return_value=True)
    def test_list_all_projects_output(self, mock_gws, mock_config, mock_root, mock_list):
        """List all projects and verify formatted output."""
        project_folders = [
            {"id": "p1", "name": "-Users-woojin-home-ccrelay", "mimeType": "application/vnd.google-apps.folder"},
            {"id": "p2", "name": "-Users-woojin-home-cclanes", "mimeType": "application/vnd.google-apps.folder"},
        ]
        sessions_p1 = [
            {"id": "s1", "name": "abc123_2026-03-22.tar.gz", "size": "1258291", "createdTime": "2026-03-22T14:30:00Z"},
        ]
        sessions_p2 = [
            {"id": "s2", "name": "def456_2026-03-21.tar.gz", "size": "512000", "createdTime": "2026-03-21T18:20:00Z"},
        ]
        mock_list.side_effect = [project_folders, sessions_p1, sessions_p2]

        args = Namespace(command="list", project=None, json=False)
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            cmd_list(args)

        output = mock_stdout.getvalue()
        self.assertIn("-Users-woojin-home-ccrelay", output)
        self.assertIn("-Users-woojin-home-cclanes", output)
        self.assertIn("abc123_2026-03-22.tar.gz", output)
        self.assertIn("def456_2026-03-21.tar.gz", output)
        self.assertIn("1.3MB", output)
        self.assertIn("512KB", output)

    @patch("ccrelay.cli.drive_list_files")
    @patch("ccrelay.cli.drive_find_folder", return_value="proj_id")
    @patch("ccrelay.cli.ensure_drive_root", return_value="root_id")
    @patch("ccrelay.cli.load_config", return_value={})
    @patch("ccrelay.cli.check_gws_available", return_value=True)
    def test_list_specific_project(self, mock_gws, mock_config, mock_root, mock_find, mock_list):
        """List sessions for specific project."""
        mock_list.return_value = [
            {"id": "s1", "name": "abc123_2026-03-22.tar.gz", "size": "4096", "createdTime": "2026-03-22T14:30:00Z"},
        ]

        args = Namespace(command="list", project="-Users-woojin-home-ccrelay", json=False)
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            cmd_list(args)

        output = mock_stdout.getvalue()
        self.assertIn("-Users-woojin-home-ccrelay", output)
        self.assertIn("abc123_2026-03-22.tar.gz", output)

    @patch("ccrelay.cli.drive_list_files", return_value=[])
    @patch("ccrelay.cli.ensure_drive_root", return_value="root_id")
    @patch("ccrelay.cli.load_config", return_value={})
    @patch("ccrelay.cli.check_gws_available", return_value=True)
    def test_list_no_projects(self, mock_gws, mock_config, mock_root, mock_list):
        """No projects on Drive prints 'No sessions found'."""
        args = Namespace(command="list", project=None, json=False)
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            cmd_list(args)
        self.assertIn("No sessions found on Drive.", mock_stdout.getvalue())


class E2EHelpTest(unittest.TestCase):
    """E2E test for help text output."""

    def test_no_args_shows_help_and_exits(self):
        """Running with no args prints help and exits with code 2."""
        with patch("sys.argv", ["ccrelay"]):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with self.assertRaises(SystemExit) as ctx:
                    main()
        self.assertEqual(ctx.exception.code, 2)
        output = mock_stdout.getvalue()
        self.assertIn("ccrelay", output)
        self.assertIn("push", output)
        self.assertIn("pull", output)
        self.assertIn("list", output)
        self.assertIn("Google Drive", output)

    def test_help_flag_shows_description(self):
        """--help flag shows program description."""
        with patch("sys.argv", ["ccrelay", "--help"]):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with self.assertRaises(SystemExit) as ctx:
                    main()
        self.assertEqual(ctx.exception.code, 0)
        output = mock_stdout.getvalue()
        self.assertIn("Selectively relay Claude Code sessions", output)
        self.assertIn("Google Drive", output)

    def test_subcommand_help_shows_project_option(self):
        """push --help shows --project option."""
        with patch("sys.argv", ["ccrelay", "push", "--help"]):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with self.assertRaises(SystemExit):
                    main()
        output = mock_stdout.getvalue()
        self.assertIn("--project", output)

    def test_help_shows_subcommand_descriptions(self):
        """Main help shows description for each subcommand."""
        with patch("sys.argv", ["ccrelay", "--help"]):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with self.assertRaises(SystemExit):
                    main()
        output = mock_stdout.getvalue()
        self.assertIn("Push a local session to Google Drive", output)
        self.assertIn("Pull a session from Google Drive to local", output)
        self.assertIn("List sessions on Google Drive", output)


class E2EErrorGwsNotAvailable(unittest.TestCase):
    """E2E tests for gws-not-available error across all commands."""

    @patch("ccrelay.cli.check_gws_available", return_value=False)
    def test_push_gws_not_available(self, mock_gws):
        """push: gws not available prints consistent error and exits."""
        args = Namespace(command="push", project=None, json=False, session=None)
        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            with self.assertRaises(SystemExit) as ctx:
                cmd_push(args)
        self.assertEqual(ctx.exception.code, 1)
        err = mock_stderr.getvalue()
        self.assertIn("gws CLI is not available or not authenticated", err)
        self.assertIn("brew install googleworkspace-cli", err)
        self.assertIn("gws auth setup --login", err)

    @patch("ccrelay.cli.check_gws_available", return_value=False)
    def test_pull_gws_not_available(self, mock_gws):
        """pull: gws not available prints consistent error and exits."""
        args = Namespace(command="pull", project=None, json=False, session=None)
        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            with self.assertRaises(SystemExit) as ctx:
                cmd_pull(args)
        self.assertEqual(ctx.exception.code, 1)
        err = mock_stderr.getvalue()
        self.assertIn("gws CLI is not available or not authenticated", err)
        self.assertIn("brew install googleworkspace-cli", err)
        self.assertIn("gws auth setup --login", err)

    @patch("ccrelay.cli.check_gws_available", return_value=False)
    def test_list_gws_not_available(self, mock_gws):
        """list: gws not available prints consistent error and exits."""
        args = Namespace(command="list", project=None, json=False)
        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            with self.assertRaises(SystemExit) as ctx:
                cmd_list(args)
        self.assertEqual(ctx.exception.code, 1)
        err = mock_stderr.getvalue()
        self.assertIn("gws CLI is not available or not authenticated", err)
        self.assertIn("brew install googleworkspace-cli", err)
        self.assertIn("gws auth setup --login", err)


class E2EErrorInvalidSelection(unittest.TestCase):
    """E2E tests for invalid user input during session selection."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.claude_dir = Path(self.tmpdir) / ".claude"
        self.project_path = "-Users-woojin-home-ccrelay"
        self.project_dir = self.claude_dir / "projects" / self.project_path
        self.project_dir.mkdir(parents=True)
        (self.project_dir / "abc123.jsonl").write_text('{"type":"test"}\n')

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _mock_sessions(self):
        return [
            {
                "uuid": "abc123",
                "path": str(self.project_dir / "abc123.jsonl"),
                "size": 1024,
                "mtime": datetime(2026, 3, 22, 10, 0, 0),
            },
        ]

    @patch("ccrelay.cli.check_gws_available", return_value=True)
    @patch("builtins.input", return_value="abc")
    def test_push_non_numeric_input(self, mock_input, mock_gws):
        """push: non-numeric input prints error with the invalid value."""
        args = Namespace(command="push", project=None, json=False, session=None)
        with patch("ccrelay.utils.os.getcwd", return_value="/Users/woojin/home/ccrelay"), \
             patch("ccrelay.cli.DEFAULT_CLAUDE_DIR", self.claude_dir), \
             patch("ccrelay.cli.list_local_sessions", return_value=self._mock_sessions()), \
             patch("sys.stderr", new_callable=StringIO) as mock_stderr, \
             patch("sys.stdout", new_callable=StringIO):
            cmd_push(args)
        self.assertIn("'abc' is not a valid number", mock_stderr.getvalue())

    @patch("ccrelay.cli.check_gws_available", return_value=True)
    @patch("builtins.input", return_value="99")
    def test_push_out_of_range(self, mock_input, mock_gws):
        """push: out-of-range number prints descriptive error."""
        args = Namespace(command="push", project=None, json=False, session=None)
        with patch("ccrelay.utils.os.getcwd", return_value="/Users/woojin/home/ccrelay"), \
             patch("ccrelay.cli.DEFAULT_CLAUDE_DIR", self.claude_dir), \
             patch("ccrelay.cli.list_local_sessions", return_value=self._mock_sessions()), \
             patch("sys.stderr", new_callable=StringIO) as mock_stderr, \
             patch("sys.stdout", new_callable=StringIO):
            cmd_push(args)
        self.assertIn("between 1 and 1", mock_stderr.getvalue())

    @patch("ccrelay.cli.check_gws_available", return_value=True)
    @patch("builtins.input", return_value="0")
    def test_push_zero_input(self, mock_input, mock_gws):
        """push: zero is out of range (1-indexed)."""
        args = Namespace(command="push", project=None, json=False, session=None)
        with patch("ccrelay.utils.os.getcwd", return_value="/Users/woojin/home/ccrelay"), \
             patch("ccrelay.cli.DEFAULT_CLAUDE_DIR", self.claude_dir), \
             patch("ccrelay.cli.list_local_sessions", return_value=self._mock_sessions()), \
             patch("sys.stderr", new_callable=StringIO) as mock_stderr, \
             patch("sys.stdout", new_callable=StringIO):
            cmd_push(args)
        self.assertIn("between 1 and 1", mock_stderr.getvalue())

    @patch("ccrelay.cli.drive_list_files")
    @patch("ccrelay.cli.drive_find_folder", return_value="proj_id")
    @patch("ccrelay.cli.ensure_drive_root", return_value="root_id")
    @patch("ccrelay.cli.load_config", return_value={})
    @patch("ccrelay.cli.check_gws_available", return_value=True)
    @patch("builtins.input", return_value="xyz")
    def test_pull_non_numeric_input(self, mock_input, mock_gws, mock_config,
                                     mock_root, mock_find, mock_list):
        """pull: non-numeric input prints error with the invalid value."""
        mock_list.return_value = [
            {"id": "f1", "name": "ses_2026-03-22.tar.gz", "size": "1024", "modifiedTime": "2026-03-22T10:00:00Z"},
        ]
        args = Namespace(command="pull", project=None, json=False, session=None)
        with patch("ccrelay.utils.os.getcwd", return_value="/Users/woojin/home/ccrelay"), \
             patch("sys.stderr", new_callable=StringIO) as mock_stderr, \
             patch("sys.stdout", new_callable=StringIO):
            cmd_pull(args)
        self.assertIn("'xyz' is not a valid number", mock_stderr.getvalue())

    @patch("ccrelay.cli.drive_list_files")
    @patch("ccrelay.cli.drive_find_folder", return_value="proj_id")
    @patch("ccrelay.cli.ensure_drive_root", return_value="root_id")
    @patch("ccrelay.cli.load_config", return_value={})
    @patch("ccrelay.cli.check_gws_available", return_value=True)
    @patch("builtins.input", return_value="99")
    def test_pull_out_of_range(self, mock_input, mock_gws, mock_config,
                                mock_root, mock_find, mock_list):
        """pull: out-of-range number prints descriptive error."""
        mock_list.return_value = [
            {"id": "f1", "name": "ses_2026-03-22.tar.gz", "size": "1024", "modifiedTime": "2026-03-22T10:00:00Z"},
        ]
        args = Namespace(command="pull", project=None, json=False, session=None)
        with patch("ccrelay.utils.os.getcwd", return_value="/Users/woojin/home/ccrelay"), \
             patch("sys.stderr", new_callable=StringIO) as mock_stderr, \
             patch("sys.stdout", new_callable=StringIO):
            cmd_pull(args)
        self.assertIn("between 1 and 1", mock_stderr.getvalue())

    @patch("ccrelay.cli.drive_list_files")
    @patch("ccrelay.cli.drive_find_folder", return_value="proj_id")
    @patch("ccrelay.cli.ensure_drive_root", return_value="root_id")
    @patch("ccrelay.cli.load_config", return_value={})
    @patch("ccrelay.cli.check_gws_available", return_value=True)
    @patch("builtins.input", return_value="-1")
    def test_pull_negative_input(self, mock_input, mock_gws, mock_config,
                                  mock_root, mock_find, mock_list):
        """pull: negative number is out of range."""
        mock_list.return_value = [
            {"id": "f1", "name": "ses_2026-03-22.tar.gz", "size": "1024", "modifiedTime": "2026-03-22T10:00:00Z"},
        ]
        args = Namespace(command="pull", project=None, json=False, session=None)
        with patch("ccrelay.utils.os.getcwd", return_value="/Users/woojin/home/ccrelay"), \
             patch("sys.stderr", new_callable=StringIO) as mock_stderr, \
             patch("sys.stdout", new_callable=StringIO):
            cmd_pull(args)
        self.assertIn("between 1 and 1", mock_stderr.getvalue())


class E2EErrorDriveFailure(unittest.TestCase):
    """E2E tests for Drive operation failures (RuntimeError from gws)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.claude_dir = Path(self.tmpdir) / ".claude"
        self.project_path = "-Users-woojin-home-ccrelay"
        self.project_dir = self.claude_dir / "projects" / self.project_path
        self.project_dir.mkdir(parents=True)
        (self.project_dir / "abc123.jsonl").write_text('{"type":"test"}\n')

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    @patch("ccrelay.cli.ensure_drive_root", side_effect=RuntimeError("network timeout"))
    @patch("ccrelay.cli.load_config", return_value={})
    @patch("ccrelay.cli.check_gws_available", return_value=True)
    @patch("builtins.input", return_value="1")
    def test_push_drive_error(self, mock_input, mock_gws, mock_config, mock_root):
        """push: Drive RuntimeError is caught and printed."""
        tar_path = os.path.join(self.tmpdir, "abc123_2026-03-22.tar.gz")
        with open(tar_path, "w") as f:
            f.write("fake tar")

        args = Namespace(command="push", project=None, json=False, session=None)
        with patch("ccrelay.utils.os.getcwd", return_value="/Users/woojin/home/ccrelay"), \
             patch("ccrelay.cli.DEFAULT_CLAUDE_DIR", self.claude_dir), \
             patch("ccrelay.cli.list_local_sessions") as mock_scan, \
             patch("ccrelay.cli.bundle_session", return_value=tar_path), \
             patch("sys.stderr", new_callable=StringIO) as mock_stderr, \
             patch("sys.stdout", new_callable=StringIO):
            mock_scan.return_value = [
                {
                    "uuid": "abc123",
                    "path": str(self.project_dir / "abc123.jsonl"),
                    "size": 1024,
                    "mtime": datetime(2026, 3, 22, 10, 0, 0),
                },
            ]
            with self.assertRaises(SystemExit):
                cmd_push(args)
        self.assertIn("Drive operation failed", mock_stderr.getvalue())
        self.assertIn("network timeout", mock_stderr.getvalue())

    @patch("ccrelay.cli.ensure_drive_root", side_effect=RuntimeError("auth expired"))
    @patch("ccrelay.cli.load_config", return_value={})
    @patch("ccrelay.cli.check_gws_available", return_value=True)
    def test_pull_drive_error(self, mock_gws, mock_config, mock_root):
        """pull: Drive RuntimeError is caught and printed."""
        args = Namespace(command="pull", project=None, json=False, session=None)
        with patch("ccrelay.utils.os.getcwd", return_value="/Users/woojin/home/ccrelay"), \
             patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            with self.assertRaises(SystemExit):
                cmd_pull(args)
        self.assertIn("Drive operation failed", mock_stderr.getvalue())
        self.assertIn("auth expired", mock_stderr.getvalue())

    @patch("ccrelay.cli.ensure_drive_root", side_effect=RuntimeError("quota exceeded"))
    @patch("ccrelay.cli.load_config", return_value={})
    @patch("ccrelay.cli.check_gws_available", return_value=True)
    def test_list_drive_error(self, mock_gws, mock_config, mock_root):
        """list: Drive RuntimeError is caught and printed."""
        args = Namespace(command="list", project=None, json=False)
        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            with self.assertRaises(SystemExit):
                cmd_list(args)
        self.assertIn("Drive operation failed", mock_stderr.getvalue())
        self.assertIn("quota exceeded", mock_stderr.getvalue())


class E2EMainDispatch(unittest.TestCase):
    """E2E tests verifying main() dispatches correctly via sys.argv."""

    @patch("ccrelay.cli.check_gws_available", return_value=True)
    @patch("ccrelay.cli.resolve_project_path", return_value="-Users-woojin-home-ccrelay")
    @patch("ccrelay.cli.list_local_sessions", return_value=[])
    def test_main_push(self, mock_list, mock_resolve, mock_gws):
        """main() with 'push' arg dispatches to cmd_push."""
        with patch("sys.argv", ["ccrelay", "push"]):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                main()
        self.assertIn("No local sessions found", mock_stdout.getvalue())

    @patch("ccrelay.cli.check_gws_available", return_value=True)
    @patch("ccrelay.cli.ensure_drive_root", return_value="root_id")
    @patch("ccrelay.cli.load_config", return_value={})
    @patch("ccrelay.cli.drive_list_files", return_value=[])
    @patch("ccrelay.cli.resolve_project_path", return_value="-Users-woojin-home-ccrelay")
    def test_main_list_no_sessions(self, mock_resolve, mock_list, mock_config, mock_root, mock_gws):
        """main() with 'list' dispatches to cmd_list."""
        with patch("sys.argv", ["ccrelay", "list"]):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                main()
        self.assertIn("No sessions found on Drive.", mock_stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
