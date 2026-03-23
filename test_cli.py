"""Tests for ccrelay CLI entry point and project path resolution."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ccrelay import (
    build_parser,
    cmd_list,
    cmd_push,
    cmd_pull,
    cwd_to_project_path,
    main,
    resolve_project_path,
)


class TestCwdToProjectPath(unittest.TestCase):
    """Tests for cwd_to_project_path."""

    def test_normal_path(self):
        result = cwd_to_project_path("/Users/woojin/home/ccrelay")
        self.assertEqual(result, "-Users-woojin-home-ccrelay")

    def test_root_path(self):
        result = cwd_to_project_path("/")
        self.assertEqual(result, "")


class TestResolveProjectPath(unittest.TestCase):
    """Tests for resolve_project_path."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.claude_dir = Path(self.tmpdir)
        self.projects_dir = self.claude_dir / "projects"
        self.projects_dir.mkdir(parents=True)
        # Create mock project directories
        (self.projects_dir / "-Users-woojin-home-ccrelay").mkdir()
        (self.projects_dir / "-Users-woojin-home-cclanes").mkdir()
        (self.projects_dir / "-Users-woojin-work-api-server").mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_no_arg_uses_cwd(self):
        """No --project arg: use cwd_to_project_path(os.getcwd())."""
        with patch("ccrelay.utils.os.getcwd", return_value="/Users/woojin/home/ccrelay"):
            result = resolve_project_path(None, claude_dir=self.claude_dir)
        self.assertEqual(result, "-Users-woojin-home-ccrelay")

    def test_suffix_match(self):
        """--project cclanes should match -Users-woojin-home-cclanes."""
        result = resolve_project_path("cclanes", claude_dir=self.claude_dir)
        self.assertEqual(result, "-Users-woojin-home-cclanes")

    def test_suffix_match_partial(self):
        """--project api-server should match -Users-woojin-work-api-server."""
        result = resolve_project_path("api-server", claude_dir=self.claude_dir)
        self.assertEqual(result, "-Users-woojin-work-api-server")

    def test_no_match_raises(self):
        """No matching directory raises ValueError."""
        with self.assertRaises(ValueError):
            resolve_project_path("nonexistent", claude_dir=self.claude_dir)

    def test_ambiguous_match_raises(self):
        """Multiple matches raise ValueError."""
        # Both ccrelay and cclanes end with 'cc'-prefixed names,
        # but we need something that actually matches multiple dirs.
        # Add another dir that creates ambiguity.
        (self.projects_dir / "-Users-woojin-other-cclanes").mkdir()
        with self.assertRaises(ValueError):
            resolve_project_path("cclanes", claude_dir=self.claude_dir)


class TestBuildParser(unittest.TestCase):
    """Tests for build_parser."""

    def setUp(self):
        self.parser = build_parser()

    def test_parse_push(self):
        args = self.parser.parse_args(["push"])
        self.assertEqual(args.command, "push")

    def test_parse_pull(self):
        args = self.parser.parse_args(["pull"])
        self.assertEqual(args.command, "pull")

    def test_parse_list(self):
        args = self.parser.parse_args(["list"])
        self.assertEqual(args.command, "list")

    def test_project_option_push(self):
        args = self.parser.parse_args(["push", "--project", "cclanes"])
        self.assertEqual(args.command, "push")
        self.assertEqual(args.project, "cclanes")

    def test_project_option_pull(self):
        args = self.parser.parse_args(["pull", "--project", "myproject"])
        self.assertEqual(args.command, "pull")
        self.assertEqual(args.project, "myproject")

    def test_project_option_list(self):
        args = self.parser.parse_args(["list", "--project", "myproject"])
        self.assertEqual(args.command, "list")
        self.assertEqual(args.project, "myproject")

    def test_default_project_is_none(self):
        args = self.parser.parse_args(["push"])
        self.assertIsNone(args.project)


class TestMain(unittest.TestCase):
    """Tests for main entry point."""

    def test_no_args_prints_help_and_exits(self):
        """No subcommand should print help and exit."""
        with patch("sys.argv", ["ccrelay"]):
            with self.assertRaises(SystemExit):
                main()

    def test_dispatch_push(self):
        """'push' subcommand dispatches to cmd_push."""
        with patch("sys.argv", ["ccrelay", "push"]):
            with patch("ccrelay.cli.cmd_push") as mock_push:
                main()
                mock_push.assert_called_once()

    def test_dispatch_pull(self):
        """'pull' subcommand dispatches to cmd_pull."""
        with patch("sys.argv", ["ccrelay", "pull"]):
            with patch("ccrelay.cli.cmd_pull") as mock_pull:
                main()
                mock_pull.assert_called_once()

    def test_dispatch_list(self):
        """'list' subcommand dispatches to cmd_list."""
        with patch("sys.argv", ["ccrelay", "list"]):
            with patch("ccrelay.cli.cmd_list") as mock_list:
                main()
                mock_list.assert_called_once()


if __name__ == "__main__":
    unittest.main()
