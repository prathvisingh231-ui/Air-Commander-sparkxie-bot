"""Static JavaScript syntax regression tests for the dashboard template."""
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "dashboard.html"


class DashboardJavaScriptSyntaxTests(unittest.TestCase):
    def test_inline_dashboard_script_parses(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is not available in this test environment")
        source = TEMPLATE.read_text(encoding="utf-8")
        scripts = re.findall(r"<script>(.*?)</script>", source, flags=re.DOTALL)
        self.assertTrue(scripts, "Dashboard template should contain its client script")
        # The dashboard's Jinja CSRF token is inserted inside quoted JS strings,
        # so the template source itself remains valid JavaScript.
        with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as handle:
            handle.write("\n".join(scripts))
            script_path = handle.name
        try:
            result = subprocess.run(
                [node, "--check", script_path],
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
            self.assertEqual(
                result.returncode,
                0,
                msg=(result.stderr or result.stdout or "Node.js rejected dashboard JavaScript"),
            )
        finally:
            Path(script_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
