"""Tests for ccrelay Drive operations."""

import json
import subprocess
import unittest
from unittest.mock import MagicMock, patch

from ccrelay import (
    check_gws_available,
    drive_create_folder,
    drive_download,
    drive_find_folder,
    drive_list_files,
    drive_update,
    drive_upload,
    gws_run,
)


class TestCheckGwsAvailable(unittest.TestCase):
    """Tests for check_gws_available()."""

    @patch("ccrelay.subprocess.run")
    def test_authenticated(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"auth_method": "oauth2", "account": "user@gmail.com"}',
        )
        self.assertTrue(check_gws_available())
        mock_run.assert_called_once_with(
            ["gws", "auth", "status"],
            capture_output=True,
            text=True,
        )

    @patch("ccrelay.subprocess.run")
    def test_not_authenticated(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"auth_method": "none"}',
        )
        self.assertFalse(check_gws_available())

    @patch("ccrelay.subprocess.run")
    def test_gws_not_installed(self, mock_run):
        mock_run.side_effect = FileNotFoundError("gws not found")
        self.assertFalse(check_gws_available())


class TestGwsRun(unittest.TestCase):
    """Tests for gws_run()."""

    @patch("ccrelay.subprocess.run")
    def test_success_valid_json(self, mock_run):
        expected = {"id": "file123", "name": "test.txt"}
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(expected),
        )
        result = gws_run(["drive", "files", "list"])
        self.assertEqual(result, expected)
        mock_run.assert_called_once_with(
            ["gws", "drive", "files", "list"],
            capture_output=True,
            text=True,
            cwd=None,
        )

    @patch("ccrelay.subprocess.run")
    def test_nonzero_exit_raises(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="something went wrong",
        )
        with self.assertRaises(RuntimeError) as ctx:
            gws_run(["drive", "files", "list"])
        self.assertIn("something went wrong", str(ctx.exception))

    @patch("ccrelay.subprocess.run")
    def test_invalid_json_raises(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="not valid json {{{",
        )
        with self.assertRaises(RuntimeError):
            gws_run(["drive", "files", "list"])


class TestDriveCreateFolder(unittest.TestCase):
    """Tests for drive_create_folder()."""

    @patch("ccrelay.gws_run")
    def test_creates_folder_returns_id(self, mock_gws_run):
        mock_gws_run.return_value = {"id": "folder_abc"}
        result = drive_create_folder("MyFolder", "parent_123")

        self.assertEqual(result, "folder_abc")
        mock_gws_run.assert_called_once()
        args = mock_gws_run.call_args[0][0]
        self.assertEqual(args[0:3], ["drive", "files", "create"])
        # Verify --json flag contains correct metadata
        json_idx = args.index("--json")
        metadata = json.loads(args[json_idx + 1])
        self.assertEqual(metadata["name"], "MyFolder")
        self.assertEqual(metadata["mimeType"], "application/vnd.google-apps.folder")
        self.assertIn("parent_123", metadata["parents"])


class TestDriveUpload(unittest.TestCase):
    """Tests for drive_upload()."""

    @patch("ccrelay.gws_run")
    def test_uploads_file_returns_id(self, mock_gws_run):
        mock_gws_run.return_value = {"id": "file_xyz"}
        result = drive_upload("/tmp/test.tar.gz", "test.tar.gz", "parent_123")

        self.assertEqual(result, "file_xyz")
        mock_gws_run.assert_called_once()
        args = mock_gws_run.call_args[0][0]
        self.assertEqual(args[0:3], ["drive", "files", "create"])
        # Verify --json metadata
        json_idx = args.index("--json")
        metadata = json.loads(args[json_idx + 1])
        self.assertEqual(metadata["name"], "test.tar.gz")
        self.assertIn("parent_123", metadata["parents"])
        # Verify --upload flag uses basename
        upload_idx = args.index("--upload")
        self.assertEqual(args[upload_idx + 1], "test.tar.gz")
        # Verify cwd is set to file's directory
        self.assertEqual(mock_gws_run.call_args[1].get("cwd"), "/tmp")


class TestDriveUpdate(unittest.TestCase):
    """Tests for drive_update()."""

    @patch("ccrelay.gws_run")
    def test_updates_file_returns_id(self, mock_gws_run):
        mock_gws_run.return_value = {"id": "file_xyz"}
        result = drive_update("file_xyz", "/tmp/updated.tar.gz")

        self.assertEqual(result, "file_xyz")
        mock_gws_run.assert_called_once()
        args = mock_gws_run.call_args[0][0]
        self.assertEqual(args[0:3], ["drive", "files", "update"])
        # Verify --params contains fileId
        params_idx = args.index("--params")
        params = json.loads(args[params_idx + 1])
        self.assertEqual(params["fileId"], "file_xyz")
        # Verify --upload flag uses basename
        upload_idx = args.index("--upload")
        self.assertEqual(args[upload_idx + 1], "updated.tar.gz")
        # Verify cwd is set to file's directory
        self.assertEqual(mock_gws_run.call_args[1].get("cwd"), "/tmp")


class TestDriveDownload(unittest.TestCase):
    """Tests for drive_download()."""

    @patch("ccrelay.gws_run")
    def test_downloads_file(self, mock_gws_run):
        mock_gws_run.return_value = {}
        drive_download("file_xyz", "/tmp/output.tar.gz")

        mock_gws_run.assert_called_once()
        args = mock_gws_run.call_args[0][0]
        self.assertEqual(args[0:3], ["drive", "files", "get"])
        # Verify --params contains fileId and alt=media
        params_idx = args.index("--params")
        params = json.loads(args[params_idx + 1])
        self.assertEqual(params["fileId"], "file_xyz")
        self.assertEqual(params["alt"], "media")
        # Verify --output flag uses basename
        output_idx = args.index("--output")
        self.assertEqual(args[output_idx + 1], "output.tar.gz")
        # Verify cwd is set to file's directory
        self.assertEqual(mock_gws_run.call_args[1].get("cwd"), "/tmp")


class TestDriveListFiles(unittest.TestCase):
    """Tests for drive_list_files()."""

    @patch("ccrelay.gws_run")
    def test_returns_files_array(self, mock_gws_run):
        mock_gws_run.return_value = {
            "files": [
                {"id": "f1", "name": "file1.txt"},
                {"id": "f2", "name": "file2.txt"},
            ]
        }
        result = drive_list_files("parent_123")

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["id"], "f1")
        mock_gws_run.assert_called_once()
        args = mock_gws_run.call_args[0][0]
        self.assertEqual(args[0:3], ["drive", "files", "list"])
        params_idx = args.index("--params")
        params = json.loads(args[params_idx + 1])
        self.assertIn('"parent_123" in parents', params["q"])
        self.assertEqual(params["pageSize"], 100)

    @patch("ccrelay.gws_run")
    def test_empty_list(self, mock_gws_run):
        mock_gws_run.return_value = {"files": []}
        result = drive_list_files("parent_123")
        self.assertEqual(result, [])


class TestDriveFindFolder(unittest.TestCase):
    """Tests for drive_find_folder()."""

    @patch("ccrelay.gws_run")
    def test_found_returns_id(self, mock_gws_run):
        mock_gws_run.return_value = {
            "files": [{"id": "folder_abc", "name": "ccrelay"}]
        }
        result = drive_find_folder("ccrelay")

        self.assertEqual(result, "folder_abc")
        args = mock_gws_run.call_args[0][0]
        params_idx = args.index("--params")
        params = json.loads(args[params_idx + 1])
        self.assertIn("name='ccrelay'", params["q"])
        self.assertIn("mimeType='application/vnd.google-apps.folder'", params["q"])

    @patch("ccrelay.gws_run")
    def test_not_found_returns_none(self, mock_gws_run):
        mock_gws_run.return_value = {"files": []}
        result = drive_find_folder("nonexistent")
        self.assertIsNone(result)

    @patch("ccrelay.gws_run")
    def test_with_parent_id(self, mock_gws_run):
        mock_gws_run.return_value = {
            "files": [{"id": "folder_abc", "name": "sessions"}]
        }
        result = drive_find_folder("sessions", parent_id="root_123")

        self.assertEqual(result, "folder_abc")
        args = mock_gws_run.call_args[0][0]
        params_idx = args.index("--params")
        params = json.loads(args[params_idx + 1])
        self.assertIn("'root_123' in parents", params["q"])


if __name__ == "__main__":
    unittest.main()
