"""Testy lokalnych ścieżek; wyłącznie sztuczne cookies w katalogach tymczasowych."""

import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "cookie_header_to_txt.py"
HEADER = "Cookie: SID=test; SSID=test; HSID=test; SAPISID=test; APISID=test; __Secure-1PSID=test\n"


class CookiePathsTest(unittest.TestCase):
    def test_default_output_is_project_cookies_from_another_cwd(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "downloader"
            script = project / "scripts" / SCRIPT.name
            script.parent.mkdir(parents=True)
            shutil.copy2(SCRIPT, script)
            cwd = root / "other"
            cwd.mkdir()

            result = subprocess.run(
                [sys.executable, str(script)],
                cwd=cwd, input=HEADER, text=True, capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            output = project / "cookies" / "cookies.txt"
            self.assertIn("\tSID\ttest\n", output.read_text())
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            self.assertFalse((cwd / "cookies.txt").exists())
            self.assertFalse((script.parent / "cookies.txt").exists())

    def test_explicit_output_and_input_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "header.txt").write_text(HEADER)
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "-i", "header.txt", "-o", "custom/cookies.txt"],
                cwd=root, text=True, capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((root / "custom" / "cookies.txt").is_file())

    def test_empty_input_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "cookies.txt"
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "-o", str(output)],
                input="", text=True, capture_output=True,
            )

            self.assertEqual(result.returncode, 1)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
