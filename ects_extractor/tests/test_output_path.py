"""Sprawdza położenie wyniku ekstrakcji bez pobierania prawdziwego planu."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "extract_classes_info.sh"


class OutputPathTest(unittest.TestCase):
    def test_output_is_in_project_data_from_another_cwd(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "projekt ze spacją i ' apostrofem"
            project.mkdir()
            script = project / SCRIPT.name
            shutil.copy2(SCRIPT, script)
            cwd = root / "working"
            cwd.mkdir()
            binaries = root / "bin"
            binaries.mkdir()
            commands = {
                "curl": "#!/bin/bash\nprintf 'fake XLS\\n'\n",
                "ssconvert": """#!/bin/bash
cat > "$3.0" <<'CSV'
"SEMESTR 1"
1,2,3,"Test",5,6,7,15,0,0,0,0
CSV
""",
            }
            for name, content in commands.items():
                command = binaries / name
                command.write_text(content)
                command.chmod(0o755)

            result = subprocess.run(
                ["bash", str(script)],
                cwd=cwd,
                env={**os.environ, "PATH": f"{binaries}{os.pathsep}{os.environ['PATH']}"},
                text=True, capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            output = project / "data" / "subjects_formatted.txt"
            self.assertIn("SEMESTR 1", output.read_text())
            self.assertIn("(T)_Test: W", output.read_text())
            self.assertFalse((cwd / "subjects_formatted.txt").exists())
            self.assertFalse((project / "subjects_formatted.txt").exists())
            self.assertFalse((cwd / "struktura.csv").exists())
            self.assertFalse((cwd / "struktura.xls").exists())


if __name__ == "__main__":
    unittest.main()
