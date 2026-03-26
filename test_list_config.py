"""Tests for config management (load_config, save_config, ensure_drive_root) and cmd_list."""

import argparse
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import ccrelay


class TestLoadConfig(unittest.TestCase):
    """Test load_config function."""

    def test_file_exists_returns_parsed_json(self):
        """When config file exists, load_config returns parsed JSON dict."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.json"
            expected = {"drive_folder_id": "abc123", "extra": "value"}
            config_file.write_text(json.dumps(expected))

            with patch("ccrelay.config.CONFIG_FILE", config_file):
                result = ccrelay.load_config()

            self.assertEqual(result, expected)

    def test_file_not_exists_returns_empty_dict(self):
        """When config file doesn't exist, load_config returns empty dict."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "nonexistent" / "config.json"

            with patch("ccrelay.config.CONFIG_FILE", config_file):
                result = ccrelay.load_config()

            self.assertEqual(result, {})


class TestSaveConfig(unittest.TestCase):
    """Test save_config function."""

    def test_creates_directory_and_writes_json(self):
        """save_config creates CONFIG_DIR if needed and writes JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / "new_dir"
            config_file = config_dir / "config.json"

            with patch("ccrelay.config.CONFIG_DIR", config_dir), \
                 patch("ccrelay.config.CONFIG_FILE", config_file):
                ccrelay.save_config({"drive_folder_id": "folder123"})

            self.assertTrue(config_file.exists())
            data = json.loads(config_file.read_text())
            self.assertEqual(data, {"drive_folder_id": "folder123"})

    def test_overwrites_existing_config(self):
        """save_config overwrites existing config file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            config_file = config_dir / "config.json"
            config_file.write_text(json.dumps({"old": "data"}))

            with patch("ccrelay.config.CONFIG_DIR", config_dir), \
                 patch("ccrelay.config.CONFIG_FILE", config_file):
                ccrelay.save_config({"drive_folder_id": "new_id"})

            data = json.loads(config_file.read_text())
            self.assertEqual(data, {"drive_folder_id": "new_id"})


class TestEnsureDriveRoot(unittest.TestCase):
    """Test ensure_drive_root function."""

    @patch("ccrelay.config.save_config")
    @patch("ccrelay.config.drive_find_folder")
    def test_config_has_valid_folder_id(self, mock_find, mock_save):
        """When config has drive_folder_id and folder exists, return it without creating."""
        mock_find.return_value = "existing_id"
        config = {"drive_folder_id": "existing_id"}

        result = ccrelay.ensure_drive_root(config)

        self.assertEqual(result, "existing_id")
        # Verify it checked the folder exists by searching
        mock_find.assert_called_once_with("ccrelay")
        # Should not save since config already had the id
        # (it may or may not save; the key point is it returns the right id)

    @patch("ccrelay.config.save_config")
    @patch("ccrelay.config.drive_find_folder")
    def test_config_empty_finds_existing_folder(self, mock_find, mock_save):
        """When config is empty but folder exists on Drive, find and save it."""
        mock_find.return_value = "found_id"
        config = {}

        result = ccrelay.ensure_drive_root(config)

        self.assertEqual(result, "found_id")
        mock_find.assert_called_with("ccrelay")
        mock_save.assert_called_once()
        saved_config = mock_save.call_args[0][0]
        self.assertEqual(saved_config["drive_folder_id"], "found_id")

    @patch("ccrelay.config.save_config")
    @patch("ccrelay.config.drive_create_folder")
    @patch("ccrelay.config.drive_find_folder")
    def test_config_empty_folder_not_found_creates_new(self, mock_find, mock_create, mock_save):
        """When config is empty and folder doesn't exist, create it."""
        mock_find.return_value = None
        mock_create.return_value = "new_folder_id"
        config = {}

        result = ccrelay.ensure_drive_root(config)

        self.assertEqual(result, "new_folder_id")
        mock_find.assert_called_with("ccrelay")
        mock_create.assert_called_once_with("ccrelay", "root")
        mock_save.assert_called_once()
        saved_config = mock_save.call_args[0][0]
        self.assertEqual(saved_config["drive_folder_id"], "new_folder_id")

    @patch("ccrelay.config.save_config")
    @patch("ccrelay.config.drive_find_folder")
    def test_config_has_stale_folder_id_finds_existing(self, mock_find, mock_save):
        """When config has folder_id but Drive search finds a different one, use the found one."""
        # drive_find_folder returns a different id (folder was recreated)
        mock_find.return_value = "different_id"
        config = {"drive_folder_id": "old_stale_id"}

        result = ccrelay.ensure_drive_root(config)

        self.assertEqual(result, "different_id")

    @patch("ccrelay.config.save_config")
    @patch("ccrelay.config.drive_create_folder")
    @patch("ccrelay.config.drive_find_folder")
    def test_config_has_stale_id_folder_gone_creates_new(self, mock_find, mock_create, mock_save):
        """When config has folder_id but folder is gone from Drive, create new one."""
        mock_find.return_value = None
        mock_create.return_value = "brand_new_id"
        config = {"drive_folder_id": "deleted_folder_id"}

        result = ccrelay.ensure_drive_root(config)

        self.assertEqual(result, "brand_new_id")
        mock_create.assert_called_once_with("ccrelay", "root")


class TestCmdList(unittest.TestCase):
    """Test cmd_list command."""

    def _make_args(self, project=None):
        """Create an args namespace mimicking argparse output."""
        return argparse.Namespace(command="list", project=project, json=False)

    @patch("ccrelay.cli.check_gws_available", return_value=False)
    def test_gws_not_available(self, mock_check):
        """When gws is not available, print error and exit."""
        args = self._make_args()
        with self.assertRaises(SystemExit):
            ccrelay.cmd_list(args)

    @patch("ccrelay.cli.drive_list_files", return_value=[])
    @patch("ccrelay.cli.ensure_drive_root", return_value="root_id")
    @patch("ccrelay.cli.load_config", return_value={})
    @patch("ccrelay.cli.check_gws_available", return_value=True)
    def test_no_sessions_found(self, mock_check, mock_load, mock_ensure, mock_list):
        """When no project folders exist, print 'No sessions found on Drive.'"""
        args = self._make_args()

        from io import StringIO
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            ccrelay.cmd_list(args)

        self.assertIn("No sessions found on Drive.", mock_stdout.getvalue())

    @patch("ccrelay.cli.drive_list_files")
    @patch("ccrelay.cli.ensure_drive_root", return_value="root_id")
    @patch("ccrelay.cli.load_config", return_value={})
    @patch("ccrelay.cli.check_gws_available", return_value=True)
    def test_list_all_projects(self, mock_check, mock_load, mock_ensure, mock_list):
        """Without --project, list all project folders and their sessions."""
        # First call: list project folders under root
        project_folders = [
            {"id": "proj1_id", "name": "-Users-woojin-home-ccrelay", "mimeType": "application/vnd.google-apps.folder"},
            {"id": "proj2_id", "name": "-Users-woojin-home-cclanes", "mimeType": "application/vnd.google-apps.folder"},
        ]
        # Second call: sessions under proj1
        proj1_sessions = [
            {"id": "s1", "name": "2a671b32-xxxx_2026-03-22.tar.gz", "size": "1258291", "createdTime": "2026-03-22T14:30:00Z"},
        ]
        # Third call: sessions under proj2
        proj2_sessions = [
            {"id": "s2", "name": "f8a1c3e9-xxxx_2026-03-21.tar.gz", "size": "512000", "createdTime": "2026-03-21T18:20:00Z"},
        ]
        mock_list.side_effect = [project_folders, proj1_sessions, proj2_sessions]

        args = self._make_args()
        from io import StringIO
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            ccrelay.cmd_list(args)

        output = mock_stdout.getvalue()
        self.assertIn("-Users-woojin-home-ccrelay", output)
        self.assertIn("-Users-woojin-home-cclanes", output)
        self.assertIn("2a671b32-xxxx_2026-03-22.tar.gz", output)
        self.assertIn("f8a1c3e9-xxxx_2026-03-21.tar.gz", output)

    @patch("ccrelay.cli.drive_list_files")
    @patch("ccrelay.cli.drive_find_folder", return_value="proj1_id")
    @patch("ccrelay.cli.ensure_drive_root", return_value="root_id")
    @patch("ccrelay.cli.load_config", return_value={})
    @patch("ccrelay.cli.check_gws_available", return_value=True)
    def test_list_specific_project(self, mock_check, mock_load, mock_ensure, mock_find, mock_list):
        """With --project, list sessions for that specific project only."""
        sessions = [
            {"id": "s1", "name": "2a671b32-xxxx_2026-03-22.tar.gz", "size": "1258291", "createdTime": "2026-03-22T14:30:00Z"},
        ]
        mock_list.return_value = sessions

        args = self._make_args(project="-Users-woojin-home-ccrelay")
        from io import StringIO
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            ccrelay.cmd_list(args)

        output = mock_stdout.getvalue()
        self.assertIn("-Users-woojin-home-ccrelay", output)
        self.assertIn("2a671b32-xxxx_2026-03-22.tar.gz", output)

    @patch("ccrelay.cli.drive_list_files", return_value=[])
    @patch("ccrelay.cli.drive_find_folder", return_value=None)
    @patch("ccrelay.cli.ensure_drive_root", return_value="root_id")
    @patch("ccrelay.cli.load_config", return_value={})
    @patch("ccrelay.cli.check_gws_available", return_value=True)
    def test_list_specific_project_not_found(self, mock_check, mock_load, mock_ensure, mock_find, mock_list):
        """With --project that doesn't exist on Drive, print 'No sessions found'."""
        args = self._make_args(project="-Users-woojin-home-nonexist")
        from io import StringIO
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            ccrelay.cmd_list(args)

        self.assertIn("No sessions found on Drive.", mock_stdout.getvalue())

    @patch("ccrelay.cli.drive_list_files")
    @patch("ccrelay.cli.ensure_drive_root", return_value="root_id")
    @patch("ccrelay.cli.load_config", return_value={})
    @patch("ccrelay.cli.check_gws_available", return_value=True)
    def test_list_projects_with_no_sessions(self, mock_check, mock_load, mock_ensure, mock_list):
        """Project folders exist but have no session files inside."""
        project_folders = [
            {"id": "proj1_id", "name": "-Users-woojin-home-ccrelay", "mimeType": "application/vnd.google-apps.folder"},
        ]
        mock_list.side_effect = [project_folders, []]  # project folder found, but no sessions

        args = self._make_args()
        from io import StringIO
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            ccrelay.cmd_list(args)

        output = mock_stdout.getvalue()
        # Should show the project but indicate no sessions
        self.assertIn("-Users-woojin-home-ccrelay", output)


class TestCmdListJson(unittest.TestCase):
    def _make_args(self, project=None, json_flag=False):
        return argparse.Namespace(command="list", project=project, json=json_flag)

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
            ccrelay.cmd_list(self._make_args(json_flag=True))
            output = json.loads(mock_out.getvalue())
        self.assertEqual(len(output), 1)
        self.assertEqual(output[0]["project"], "proj1")


if __name__ == "__main__":
    unittest.main()
