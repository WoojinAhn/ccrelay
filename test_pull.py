"""Tests for ccrelay pull command: restore_session, create_session_index, project_path_to_cwd, cmd_pull."""

import io
import json
import os
import shutil
import tarfile
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, patch

from ccrelay import (
    create_session_index,
    cmd_pull,
    project_path_to_cwd,
    restore_session,
)


class TestProjectPathToCwd(unittest.TestCase):
    """Tests for project_path_to_cwd."""

    def test_normal_path(self):
        result = project_path_to_cwd("-Users-woojin-home-ccrelay")
        self.assertEqual(result, "/Users/woojin/home/ccrelay")

    def test_empty_string(self):
        result = project_path_to_cwd("")
        self.assertEqual(result, "/")


class TestRestoreSession(unittest.TestCase):
    """Tests for restore_session."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.claude_dir = Path(self.tmpdir) / ".claude"
        self.claude_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _create_mock_tar(self, uuid: str) -> str:
        """Create a mock tar.gz with session files."""
        tar_path = os.path.join(self.tmpdir, f"{uuid}_20260322.tar.gz")
        src_dir = os.path.join(self.tmpdir, "src")
        os.makedirs(src_dir, exist_ok=True)
        # Main session file
        jsonl_path = os.path.join(src_dir, f"{uuid}.jsonl")
        with open(jsonl_path, "w") as f:
            f.write('{"type":"summary","summary":"test session"}\n')
        # Agent file
        agent_path = os.path.join(src_dir, f"agent-{uuid}.jsonl")
        with open(agent_path, "w") as f:
            f.write('{"type":"agent","data":"test"}\n')

        with tarfile.open(tar_path, "w:gz") as tar:
            tar.add(jsonl_path, arcname=f"{uuid}.jsonl")
            tar.add(agent_path, arcname=f"agent-{uuid}.jsonl")

        return tar_path

    def test_extracts_to_correct_location(self):
        uuid = "abc12345-1234-1234-1234-123456789abc"
        tar_path = self._create_mock_tar(uuid)
        project_path = "-Users-woojin-home-ccrelay"

        result = restore_session(tar_path, project_path, claude_dir=self.claude_dir)

        self.assertEqual(result, uuid)
        dest_dir = self.claude_dir / "projects" / project_path
        self.assertTrue((dest_dir / f"{uuid}.jsonl").exists())
        self.assertTrue((dest_dir / f"agent-{uuid}.jsonl").exists())

    def test_returns_uuid(self):
        uuid = "def67890-5678-5678-5678-567890abcdef"
        tar_path = self._create_mock_tar(uuid)
        project_path = "-Users-woojin-home-cclanes"

        result = restore_session(tar_path, project_path, claude_dir=self.claude_dir)

        self.assertEqual(result, uuid)

    def test_creates_project_dir_if_missing(self):
        uuid = "aaa11111-2222-3333-4444-555566667777"
        tar_path = self._create_mock_tar(uuid)
        project_path = "-Users-woojin-home-newproject"

        restore_session(tar_path, project_path, claude_dir=self.claude_dir)

        dest_dir = self.claude_dir / "projects" / project_path
        self.assertTrue(dest_dir.exists())
        self.assertTrue((dest_dir / f"{uuid}.jsonl").exists())


class TestCreateSessionIndex(unittest.TestCase):
    """Tests for create_session_index."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.claude_dir = Path(self.tmpdir) / ".claude"
        self.claude_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_creates_json_file_in_sessions_dir(self):
        session_id = "abc12345-1234-1234-1234-123456789abc"
        project_path = "-Users-woojin-home-ccrelay"

        create_session_index(session_id, project_path, claude_dir=self.claude_dir)

        sessions_dir = self.claude_dir / "sessions"
        self.assertTrue(sessions_dir.exists())
        json_files = list(sessions_dir.glob("*.json"))
        self.assertEqual(len(json_files), 1)

    def test_json_structure(self):
        session_id = "abc12345-1234-1234-1234-123456789abc"
        project_path = "-Users-woojin-home-ccrelay"

        create_session_index(session_id, project_path, claude_dir=self.claude_dir)

        sessions_dir = self.claude_dir / "sessions"
        json_files = list(sessions_dir.glob("*.json"))
        with open(json_files[0]) as f:
            data = json.load(f)

        self.assertIn("pid", data)
        self.assertIn("sessionId", data)
        self.assertIn("cwd", data)
        self.assertIn("startedAt", data)

        self.assertEqual(data["sessionId"], session_id)
        self.assertEqual(data["cwd"], "/Users/woojin/home/ccrelay")
        self.assertIsInstance(data["pid"], int)
        self.assertIsInstance(data["startedAt"], int)

    def test_sessions_dir_created_if_missing(self):
        session_id = "abc12345-1234-1234-1234-123456789abc"
        project_path = "-Users-woojin-home-ccrelay"

        self.assertFalse((self.claude_dir / "sessions").exists())

        create_session_index(session_id, project_path, claude_dir=self.claude_dir)

        self.assertTrue((self.claude_dir / "sessions").exists())


class TestCmdPull(unittest.TestCase):
    """Tests for cmd_pull."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.claude_dir = Path(self.tmpdir) / ".claude"
        self.claude_dir.mkdir()
        self.projects_dir = self.claude_dir / "projects"
        self.projects_dir.mkdir()
        (self.projects_dir / "-Users-woojin-home-ccrelay").mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _make_args(self, project=None):
        return Namespace(command="pull", project=project, json=False, session=None)

    @patch("ccrelay.cli.check_gws_available", return_value=False)
    def test_gws_not_available(self, mock_gws):
        """Should print error and exit when gws is not available."""
        args = self._make_args()
        with self.assertRaises(SystemExit):
            cmd_pull(args)

    @patch("ccrelay.cli.create_session_index")
    @patch("ccrelay.cli.restore_session", return_value="abc12345")
    @patch("ccrelay.cli.drive_download")
    @patch("ccrelay.cli.drive_list_files", return_value=[])
    @patch("ccrelay.cli.drive_find_folder", return_value="proj_folder_id")
    @patch("ccrelay.cli.ensure_drive_root", return_value="root_123")
    @patch("ccrelay.cli.load_config", return_value={"drive_folder_id": "root_123"})
    @patch("ccrelay.cli.resolve_project_path", return_value="-Users-woojin-home-ccrelay")
    @patch("ccrelay.cli.check_gws_available", return_value=True)
    def test_no_sessions_on_drive(self, mock_gws, mock_resolve, mock_load,
                                   mock_ensure, mock_find, mock_list,
                                   mock_download, mock_restore, mock_index):
        """Should print message and return when no sessions found."""
        args = self._make_args(project="ccrelay")
        with patch("builtins.print") as mock_print:
            cmd_pull(args)
        mock_download.assert_not_called()
        # Verify appropriate message printed
        mock_print.assert_any_call("No sessions found on Drive for this project.")

    @patch("ccrelay.cli.DEFAULT_CLAUDE_DIR")
    @patch("ccrelay.cli.create_session_index")
    @patch("ccrelay.cli.restore_session", return_value="abc12345-1234-1234-1234-123456789abc")
    @patch("ccrelay.cli.drive_download")
    @patch("ccrelay.cli.drive_list_files")
    @patch("ccrelay.cli.drive_find_folder", return_value="proj_folder_id")
    @patch("ccrelay.cli.ensure_drive_root", return_value="root_123")
    @patch("ccrelay.cli.load_config", return_value={"drive_folder_id": "root_123"})
    @patch("ccrelay.cli.resolve_project_path", return_value="-Users-woojin-home-ccrelay")
    @patch("ccrelay.cli.check_gws_available", return_value=True)
    def test_full_flow(self, mock_gws, mock_resolve, mock_load, mock_ensure,
                       mock_find, mock_list, mock_download, mock_restore,
                       mock_index, mock_claude_dir):
        """Test full pull flow: list, select, download, restore, index."""
        mock_claude_dir.__truediv__ = lambda self, x: Path(self.tmpdir) / ".claude" / x
        mock_list.return_value = [
            {
                "id": "file_001",
                "name": "abc12345-1234-1234-1234-123456789abc_20260322.tar.gz",
                "size": "4096",
                "modifiedTime": "2026-03-22T10:00:00Z",
            },
        ]
        # Make DEFAULT_CLAUDE_DIR point to our temp dir so conflict check doesn't find local file
        mock_claude_dir.__truediv__ = MagicMock(return_value=Path(self.tmpdir) / "nonexistent")
        # Ensure the nested / calls work — we need Path-like behavior
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        mock_claude_dir.__truediv__ = MagicMock(return_value=MagicMock(__truediv__=MagicMock(return_value=MagicMock(__truediv__=MagicMock(return_value=mock_path)))))

        args = self._make_args(project="ccrelay")
        with patch("builtins.input", return_value="1"):
            with patch("builtins.print"):
                cmd_pull(args)

        mock_download.assert_called_once()
        mock_restore.assert_called_once()
        mock_index.assert_called_once()

    @patch("ccrelay.cli.create_session_index")
    @patch("ccrelay.cli.restore_session", return_value="abc12345-1234-1234-1234-123456789abc")
    @patch("ccrelay.cli.drive_download")
    @patch("ccrelay.cli.drive_list_files")
    @patch("ccrelay.cli.drive_find_folder", return_value="proj_folder_id")
    @patch("ccrelay.cli.ensure_drive_root", return_value="root_123")
    @patch("ccrelay.cli.load_config", return_value={"drive_folder_id": "root_123"})
    @patch("ccrelay.cli.resolve_project_path", return_value="-Users-woojin-home-ccrelay")
    @patch("ccrelay.cli.check_gws_available", return_value=True)
    def test_conflict_local_newer_skip(self, mock_gws, mock_resolve, mock_load,
                                        mock_ensure, mock_find, mock_list,
                                        mock_download, mock_restore, mock_index):
        """Local file newer than Drive — user says N, should skip."""
        uuid = "abc12345-1234-1234-1234-123456789abc"
        mock_list.return_value = [
            {
                "id": "file_001",
                "name": f"{uuid}_20260322.tar.gz",
                "size": "4096",
                "modifiedTime": "2026-03-20T10:00:00Z",
            },
        ]
        # Create local file with newer mtime
        project_path = "-Users-woojin-home-ccrelay"
        local_session_dir = self.claude_dir / "projects" / project_path
        local_session_dir.mkdir(parents=True, exist_ok=True)
        local_file = local_session_dir / f"{uuid}.jsonl"
        local_file.write_text('{"test": true}\n')
        # Set local mtime to March 21 00:00 UTC (newer than Drive's March 20 10:00 UTC)
        march_21_ts = 1774051200.0  # 2026-03-21T00:00:00Z
        os.utime(local_file, (march_21_ts, march_21_ts))

        args = self._make_args(project="ccrelay")
        with patch("ccrelay.cli.DEFAULT_CLAUDE_DIR", self.claude_dir):
            with patch("builtins.input", side_effect=["1", "N"]):
                with patch("builtins.print"):
                    cmd_pull(args)

        mock_restore.assert_not_called()

    @patch("ccrelay.cli.create_session_index")
    @patch("ccrelay.cli.restore_session", return_value="abc12345-1234-1234-1234-123456789abc")
    @patch("ccrelay.cli.drive_download")
    @patch("ccrelay.cli.drive_list_files")
    @patch("ccrelay.cli.drive_find_folder", return_value="proj_folder_id")
    @patch("ccrelay.cli.ensure_drive_root", return_value="root_123")
    @patch("ccrelay.cli.load_config", return_value={"drive_folder_id": "root_123"})
    @patch("ccrelay.cli.resolve_project_path", return_value="-Users-woojin-home-ccrelay")
    @patch("ccrelay.cli.check_gws_available", return_value=True)
    def test_conflict_drive_newer_overwrites(self, mock_gws, mock_resolve, mock_load,
                                              mock_ensure, mock_find, mock_list,
                                              mock_download, mock_restore, mock_index):
        """Drive file newer than local — should overwrite without prompt."""
        uuid = "abc12345-1234-1234-1234-123456789abc"
        mock_list.return_value = [
            {
                "id": "file_001",
                "name": f"{uuid}_20260322.tar.gz",
                "size": "4096",
                "modifiedTime": "2026-03-22T10:00:00Z",
            },
        ]
        # Create local file with older mtime
        project_path = "-Users-woojin-home-ccrelay"
        local_session_dir = self.claude_dir / "projects" / project_path
        local_session_dir.mkdir(parents=True, exist_ok=True)
        local_file = local_session_dir / f"{uuid}.jsonl"
        local_file.write_text('{"test": true}\n')
        # Set local mtime to March 20 00:00 UTC (older than Drive's March 22 10:00 UTC)
        march_20_ts = 1773964800.0  # 2026-03-20T00:00:00Z
        os.utime(local_file, (march_20_ts, march_20_ts))

        args = self._make_args(project="ccrelay")
        with patch("ccrelay.cli.DEFAULT_CLAUDE_DIR", self.claude_dir):
            # Only one input call — session selection, no overwrite prompt
            with patch("builtins.input", return_value="1") as mock_input:
                with patch("builtins.print"):
                    cmd_pull(args)

        mock_restore.assert_called_once()
        mock_index.assert_called_once()
        # input should only be called once (for selection, not for overwrite confirmation)
        mock_input.assert_called_once()


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


if __name__ == "__main__":
    unittest.main()
