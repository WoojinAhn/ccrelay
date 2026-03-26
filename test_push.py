"""Tests for ccrelay push command — session scanning, bundling, and cmd_push."""

import json
import os
import shutil
import tarfile
import tempfile
import time
import unittest
from argparse import Namespace
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from ccrelay import (
    bundle_session,
    cmd_push,
    extract_session_label,
    list_local_sessions,
)


class TestListLocalSessions(unittest.TestCase):
    """Tests for list_local_sessions()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.claude_dir = Path(self.tmpdir)
        self.project_path = "-Users-woojin-home-ccrelay"
        self.project_dir = self.claude_dir / "projects" / self.project_path
        self.project_dir.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_returns_sessions_with_correct_fields(self):
        """Each session dict has uuid, path, size, mtime."""
        session_file = self.project_dir / "abc-123.jsonl"
        session_file.write_text('{"type":"test"}\n')

        sessions = list_local_sessions(self.project_path, claude_dir=self.claude_dir)

        self.assertEqual(len(sessions), 1)
        s = sessions[0]
        self.assertEqual(s["uuid"], "abc-123")
        self.assertEqual(s["path"], str(session_file))
        self.assertIsInstance(s["size"], int)
        self.assertGreater(s["size"], 0)
        self.assertIsInstance(s["mtime"], datetime)

    def test_size_includes_subagents_dir(self):
        """Size should include the .jsonl file AND the subagents directory."""
        session_file = self.project_dir / "abc-123.jsonl"
        session_file.write_text('{"type":"test"}\n')
        jsonl_size = session_file.stat().st_size

        # Create subagents dir with a file
        subagents_dir = self.project_dir / "abc-123" / "subagents"
        subagents_dir.mkdir(parents=True)
        agent_file = subagents_dir / "agent-001.jsonl"
        agent_file.write_text('{"type":"agent"}\n')
        agent_size = agent_file.stat().st_size

        sessions = list_local_sessions(self.project_path, claude_dir=self.claude_dir)

        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["size"], jsonl_size + agent_size)

    def test_sorted_by_mtime_descending(self):
        """Sessions are sorted newest first."""
        # Create sessions with different mtimes
        s1 = self.project_dir / "older-uuid.jsonl"
        s1.write_text("older\n")
        # Set older mtime
        old_time = time.time() - 3600
        os.utime(s1, (old_time, old_time))

        s2 = self.project_dir / "newer-uuid.jsonl"
        s2.write_text("newer\n")
        # This file has the current time (newer)

        sessions = list_local_sessions(self.project_path, claude_dir=self.claude_dir)

        self.assertEqual(len(sessions), 2)
        self.assertEqual(sessions[0]["uuid"], "newer-uuid")
        self.assertEqual(sessions[1]["uuid"], "older-uuid")

    def test_empty_directory_returns_empty_list(self):
        """No .jsonl files means empty list."""
        sessions = list_local_sessions(self.project_path, claude_dir=self.claude_dir)
        self.assertEqual(sessions, [])

    def test_nonexistent_project_dir_returns_empty_list(self):
        """If the project directory doesn't exist, return empty list."""
        sessions = list_local_sessions(
            "-Users-nobody-fake-project", claude_dir=self.claude_dir
        )
        self.assertEqual(sessions, [])

    def test_ignores_non_jsonl_files(self):
        """Only .jsonl files are considered sessions."""
        (self.project_dir / "abc-123.jsonl").write_text("session\n")
        (self.project_dir / "readme.txt").write_text("not a session\n")
        (self.project_dir / "some-dir").mkdir()

        sessions = list_local_sessions(self.project_path, claude_dir=self.claude_dir)

        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["uuid"], "abc-123")


class TestExtractSessionLabel(unittest.TestCase):
    """Tests for extract_session_label()."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _write_jsonl(self, filename, lines):
        path = os.path.join(self.tmp, filename)
        with open(path, "w") as f:
            for line in lines:
                f.write(json.dumps(line) + "\n")
        return path

    def test_custom_title_takes_priority(self):
        """custom-title message should be returned as label."""
        path = self._write_jsonl("session.jsonl", [
            {"type": "user", "message": {"content": [{"type": "text", "text": "first msg"}]}},
            {"type": "custom-title", "customTitle": "My Session Name"},
        ])
        self.assertEqual(extract_session_label(path), "My Session Name")

    def test_first_user_message_fallback(self):
        """When no custom-title, use first user message."""
        path = self._write_jsonl("session.jsonl", [
            {"type": "progress", "data": {}},
            {"type": "user", "message": {"content": [{"type": "text", "text": "이슈 12번 개발"}]}},
            {"type": "user", "message": {"content": [{"type": "text", "text": "두번째 메시지"}]}},
        ])
        self.assertEqual(extract_session_label(path), "이슈 12번 개발")

    def test_long_message_truncated(self):
        """Long first message should be truncated."""
        long_msg = "A" * 200
        path = self._write_jsonl("session.jsonl", [
            {"type": "user", "message": {"content": [{"type": "text", "text": long_msg}]}},
        ])
        label = extract_session_label(path)
        self.assertLessEqual(len(label), 63)  # 60 + "..."

    def test_no_useful_content_returns_none(self):
        """If no custom-title and no user message, return None."""
        path = self._write_jsonl("session.jsonl", [
            {"type": "progress", "data": {}},
            {"type": "progress", "data": {}},
        ])
        self.assertIsNone(extract_session_label(path))

    def test_empty_file_returns_none(self):
        """Empty file returns None."""
        path = os.path.join(self.tmp, "empty.jsonl")
        with open(path, "w") as f:
            pass
        self.assertIsNone(extract_session_label(path))

    def test_user_message_string_content(self):
        """Handle user message with plain string content."""
        path = self._write_jsonl("session.jsonl", [
            {"type": "user", "content": "plain string message"},
        ])
        self.assertEqual(extract_session_label(path), "plain string message")


class TestBundleSession(unittest.TestCase):
    """Tests for bundle_session()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.claude_dir = Path(self.tmpdir)
        self.project_path = "-Users-woojin-home-ccrelay"
        self.project_dir = self.claude_dir / "projects" / self.project_path
        self.project_dir.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_creates_tar_gz_with_jsonl(self):
        """bundle_session creates a tar.gz containing the .jsonl file."""
        session_file = self.project_dir / "abc-123.jsonl"
        session_file.write_text('{"type":"test"}\n')

        tar_path = bundle_session(self.project_path, "abc-123", claude_dir=self.claude_dir)

        self.assertTrue(os.path.exists(tar_path))
        self.assertTrue(tar_path.endswith(".tar.gz"))
        with tarfile.open(tar_path, "r:gz") as tf:
            names = tf.getnames()
            self.assertIn("abc-123.jsonl", names)

    def test_includes_subagents_directory(self):
        """Bundle includes the {uuid}/ directory with subagents."""
        session_file = self.project_dir / "abc-123.jsonl"
        session_file.write_text('{"type":"test"}\n')
        subagents_dir = self.project_dir / "abc-123" / "subagents"
        subagents_dir.mkdir(parents=True)
        (subagents_dir / "agent-001.jsonl").write_text('{"type":"agent"}\n')

        tar_path = bundle_session(self.project_path, "abc-123", claude_dir=self.claude_dir)

        with tarfile.open(tar_path, "r:gz") as tf:
            names = tf.getnames()
            self.assertIn("abc-123.jsonl", names)
            # Check subagents are included
            agent_paths = [n for n in names if "agent-001.jsonl" in n]
            self.assertTrue(len(agent_paths) > 0)

    def test_filename_format(self):
        """tar.gz filename is {uuid}_{YYYY-MM-DD}.tar.gz."""
        session_file = self.project_dir / "abc-123.jsonl"
        session_file.write_text('{"type":"test"}\n')

        tar_path = bundle_session(self.project_path, "abc-123", claude_dir=self.claude_dir)

        today = datetime.now().strftime("%Y-%m-%d")
        expected_name = f"abc-123_{today}.tar.gz"
        self.assertTrue(
            tar_path.endswith(expected_name),
            f"Expected filename ending with {expected_name}, got {tar_path}",
        )

    def test_extracting_preserves_contents(self):
        """Extracted contents match the originals."""
        session_file = self.project_dir / "abc-123.jsonl"
        content = '{"type":"test","data":"hello world"}\n'
        session_file.write_text(content)

        tar_path = bundle_session(self.project_path, "abc-123", claude_dir=self.claude_dir)

        # Extract and verify
        extract_dir = tempfile.mkdtemp()
        try:
            with tarfile.open(tar_path, "r:gz") as tf:
                tf.extractall(extract_dir)
            extracted = Path(extract_dir) / "abc-123.jsonl"
            self.assertEqual(extracted.read_text(), content)
        finally:
            shutil.rmtree(extract_dir)

    def test_no_subagents_dir_still_works(self):
        """Bundle works even when there's no {uuid}/ subagents directory."""
        session_file = self.project_dir / "abc-123.jsonl"
        session_file.write_text('{"type":"test"}\n')

        tar_path = bundle_session(self.project_path, "abc-123", claude_dir=self.claude_dir)

        self.assertTrue(os.path.exists(tar_path))
        with tarfile.open(tar_path, "r:gz") as tf:
            names = tf.getnames()
            self.assertIn("abc-123.jsonl", names)


class TestCmdPush(unittest.TestCase):
    """Tests for cmd_push() command."""

    def _make_args(self, project=None):
        return Namespace(command="push", project=project, json=False, session=None)

    @patch("ccrelay.cli.check_gws_available", return_value=False)
    def test_gws_not_available_exits(self, mock_check):
        """cmd_push exits with SystemExit if gws is not available."""
        with patch("builtins.print"):
            with self.assertRaises(SystemExit):
                cmd_push(self._make_args())

    @patch("ccrelay.cli.check_gws_available", return_value=True)
    @patch("ccrelay.cli.resolve_project_path", return_value="-Users-woojin-home-ccrelay")
    @patch("ccrelay.cli.list_local_sessions", return_value=[])
    def test_no_sessions_prints_message(self, mock_list, mock_resolve, mock_check):
        """cmd_push prints message and returns if no sessions found."""
        with patch("builtins.print") as mock_print:
            cmd_push(self._make_args())
            output = " ".join(str(c) for c in mock_print.call_args_list)
            self.assertTrue(
                "no" in output.lower() or "session" in output.lower(),
                f"Expected message about no sessions, got: {output}",
            )

    @patch("ccrelay.cli.check_gws_available", return_value=True)
    @patch("ccrelay.cli.resolve_project_path", return_value="-Users-woojin-home-ccrelay")
    @patch("ccrelay.cli.list_local_sessions")
    @patch("ccrelay.cli.bundle_session", return_value="/tmp/abc-123_2026-03-22.tar.gz")
    @patch("ccrelay.cli.ensure_drive_root", return_value="root_123")
    @patch("ccrelay.cli.drive_find_folder", return_value=None)
    @patch("ccrelay.cli.drive_create_folder", return_value="proj_folder_456")
    @patch("ccrelay.cli.drive_list_files", return_value=[])
    @patch("ccrelay.cli.drive_upload", return_value="uploaded_file_789")
    @patch("builtins.input", return_value="1")
    @patch("os.remove")
    def test_full_push_flow_new_upload(
        self,
        mock_remove,
        mock_input,
        mock_upload,
        mock_list_files,
        mock_create_folder,
        mock_find_folder,
        mock_ensure_root,
        mock_bundle,
        mock_list_sessions,
        mock_resolve,
        mock_check,
    ):
        """Full push flow: select session, bundle, create folder, upload."""
        mock_list_sessions.return_value = [
            {
                "uuid": "abc-123",
                "path": "/fake/.claude/projects/proj/abc-123.jsonl",
                "size": 1024,
                "mtime": datetime(2026, 3, 22, 10, 0, 0),
            },
        ]

        with patch("builtins.print"):
            cmd_push(self._make_args())

        mock_bundle.assert_called_once_with("-Users-woojin-home-ccrelay", "abc-123")
        mock_find_folder.assert_called_once_with(
            "-Users-woojin-home-ccrelay", parent_id="root_123"
        )
        mock_create_folder.assert_called_once_with(
            "-Users-woojin-home-ccrelay", "root_123"
        )
        mock_upload.assert_called_once_with(
            "/tmp/abc-123_2026-03-22.tar.gz",
            "abc-123_2026-03-22.tar.gz",
            "proj_folder_456",
        )
        mock_remove.assert_called_once_with("/tmp/abc-123_2026-03-22.tar.gz")

    @patch("ccrelay.cli.check_gws_available", return_value=True)
    @patch("ccrelay.cli.resolve_project_path", return_value="-Users-woojin-home-ccrelay")
    @patch("ccrelay.cli.list_local_sessions")
    @patch("ccrelay.cli.bundle_session", return_value="/tmp/abc-123_2026-03-22.tar.gz")
    @patch("ccrelay.cli.ensure_drive_root", return_value="root_123")
    @patch("ccrelay.cli.drive_find_folder", return_value="existing_proj_folder")
    @patch("ccrelay.cli.drive_list_files")
    @patch("ccrelay.cli.drive_update", return_value="updated_file_789")
    @patch("builtins.input", return_value="1")
    @patch("os.remove")
    def test_re_push_updates_existing_file(
        self,
        mock_remove,
        mock_input,
        mock_update,
        mock_list_files,
        mock_find_folder,
        mock_ensure_root,
        mock_bundle,
        mock_list_sessions,
        mock_resolve,
        mock_check,
    ):
        """Re-push: existing file on Drive gets updated instead of created."""
        mock_list_sessions.return_value = [
            {
                "uuid": "abc-123",
                "path": "/fake/.claude/projects/proj/abc-123.jsonl",
                "size": 1024,
                "mtime": datetime(2026, 3, 22, 10, 0, 0),
            },
        ]
        mock_list_files.return_value = [
            {"id": "old_file_id", "name": "abc-123_2026-03-20.tar.gz"},
        ]

        with patch("builtins.print"):
            cmd_push(self._make_args())

        mock_update.assert_called_once_with("old_file_id", "/tmp/abc-123_2026-03-22.tar.gz")
        mock_remove.assert_called_once_with("/tmp/abc-123_2026-03-22.tar.gz")

    @patch("ccrelay.cli.check_gws_available", return_value=True)
    @patch("ccrelay.cli.resolve_project_path", return_value="-Users-woojin-home-ccrelay")
    @patch("ccrelay.cli.list_local_sessions")
    @patch("ccrelay.cli.bundle_session", return_value="/tmp/abc-123_2026-03-22.tar.gz")
    @patch("ccrelay.cli.ensure_drive_root", return_value="root_123")
    @patch("ccrelay.cli.drive_find_folder", return_value="existing_proj_folder")
    @patch("ccrelay.cli.drive_list_files")
    @patch("ccrelay.cli.drive_upload", return_value="uploaded_file_789")
    @patch("builtins.input", return_value="1")
    @patch("os.remove")
    def test_no_matching_uuid_on_drive_uploads_new(
        self,
        mock_remove,
        mock_input,
        mock_upload,
        mock_list_files,
        mock_find_folder,
        mock_ensure_root,
        mock_bundle,
        mock_list_sessions,
        mock_resolve,
        mock_check,
    ):
        """If Drive folder exists but no file with matching UUID, upload new."""
        mock_list_sessions.return_value = [
            {
                "uuid": "abc-123",
                "path": "/fake/.claude/projects/proj/abc-123.jsonl",
                "size": 1024,
                "mtime": datetime(2026, 3, 22, 10, 0, 0),
            },
        ]
        mock_list_files.return_value = [
            {"id": "other_file_id", "name": "xyz-999_2026-03-20.tar.gz"},
        ]

        with patch("builtins.print"):
            cmd_push(self._make_args())

        mock_upload.assert_called_once_with(
            "/tmp/abc-123_2026-03-22.tar.gz",
            "abc-123_2026-03-22.tar.gz",
            "existing_proj_folder",
        )


if __name__ == "__main__":
    unittest.main()
