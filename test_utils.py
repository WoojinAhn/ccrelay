"""Tests for ccrelay.utils — path resolution and formatting."""

import subprocess
import unittest

from ccrelay.utils import format_size, format_time


class TestFormatSize(unittest.TestCase):
    """Tests for format_size()."""

    def test_bytes(self):
        self.assertEqual(format_size("500"), "500B")

    def test_kilobytes(self):
        self.assertEqual(format_size("1500"), "2KB")

    def test_megabytes(self):
        self.assertEqual(format_size("1500000"), "1.5MB")

    def test_zero(self):
        self.assertEqual(format_size("0"), "0B")

    def test_invalid_returns_unknown(self):
        self.assertEqual(format_size("not_a_number"), "unknown")

    def test_none_returns_unknown(self):
        self.assertEqual(format_size(None), "unknown")


class TestFormatTime(unittest.TestCase):
    """Tests for format_time()."""

    def test_iso_with_z(self):
        """UTC input should be converted to local timezone."""
        from datetime import datetime, timezone
        result = format_time("2026-03-22T15:30:00Z")
        # Verify by computing expected local time
        utc_dt = datetime(2026, 3, 22, 15, 30, tzinfo=timezone.utc)
        expected = utc_dt.astimezone().strftime("%Y-%m-%d %H:%M")
        self.assertEqual(result, expected)

    def test_iso_with_offset(self):
        """Offset input should be converted to local timezone."""
        from datetime import datetime, timezone
        result = format_time("2026-03-22T15:30:00+00:00")
        utc_dt = datetime(2026, 3, 22, 15, 30, tzinfo=timezone.utc)
        expected = utc_dt.astimezone().strftime("%Y-%m-%d %H:%M")
        self.assertEqual(result, expected)

    def test_empty_string_returns_unknown(self):
        self.assertEqual(format_time(""), "unknown")

    def test_none_returns_unknown(self):
        self.assertEqual(format_time(None), "unknown")

    def test_invalid_returns_unknown(self):
        self.assertEqual(format_time("not-a-date"), "unknown")


class TestModuleEntryPoint(unittest.TestCase):
    """Test that python -m ccrelay works."""

    def test_python_m_ccrelay_shows_help(self):
        """python -m ccrelay with no args should print help and exit 2."""
        result = subprocess.run(
            ["python3", "-m", "ccrelay"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("push", result.stdout + result.stderr)
        self.assertIn("pull", result.stdout + result.stderr)
        self.assertIn("list", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
