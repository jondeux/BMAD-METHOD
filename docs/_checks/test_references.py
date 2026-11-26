import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CHECK = Path(__file__).with_name("check_references.py")


class FreshnessTest(unittest.TestCase):
    def run_check(self, markdown):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            (root / "tools").mkdir()
            (root / "tools/helper.py").write_text(
                "def build():\n    return 1\n\ndef publish():\n    return 2\n", encoding="utf-8"
            )
            (root / "README.md").write_text(markdown, encoding="utf-8")
            return subprocess.run(
                [sys.executable, "-B", str(CHECK), "--root", str(root)],
                text=True,
                capture_output=True,
                timeout=10,
            )

    def test_passes_existing_path_line_and_symbol(self):
        result = self.run_check(
            "[file](tools/helper.py)\n[\x60publish()\x60](tools/helper.py#L4-L5)\n"
            "\x60tools/helper.py::build\x60 and tools/helper.py:1:2\n"
            "[external](https://example.com/docs/missing.md)\n"
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_rejects_missing_path_and_drifted_location(self):
        result = self.run_check(
            "[missing](tools/removed.py)\n\x60tools/helper.py:100\x60\n"
            "[\x60publish\x60](tools/helper.py#L1)\n\x60tools/helper.py::missing\x60\n"
            "The former runner was tools/no-longer-here.py.\n"
        )
        self.assertEqual(result.returncode, 1)
        for number, finding in (
            (1, "file or directory does not exist"),
            (2, "past the end of the file"),
            (3, "line does not point to Python symbol publish"),
            (4, "Python symbol missing does not exist"),
            (5, "file or directory does not exist"),
        ):
            with self.subTest(line=number):
                self.assertRegex(result.stdout, rf"README.md:{number}: [^\n]+{finding}")

    def test_limited_example_exemption_and_fences(self):
        result = self.run_check(
            "\x60tools/example.py\x60 and \x60tools/stale.py\x60 <!-- freshness-example: tools/example.py -->\n"
            "~~~sh\npython tools/fenced-example.py\n~~~\n"
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("tools/stale.py", result.stdout)
        self.assertNotIn("tools/example.py", result.stdout)
        self.assertNotIn("tools/fenced-example.py", result.stdout)
