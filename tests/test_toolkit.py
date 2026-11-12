import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import portai
import portai_toolkit


class ToolkitTests(unittest.TestCase):
    def test_collect_reports_missing_and_installable_packages(self):
        present = {"python3", "git", "java"}
        report = portai_toolkit.collect(with_versions=False, which=lambda name: f"/bin/{name}" if name in present else None)
        self.assertEqual(report.missing("base"), [])
        packages = report.installable()
        self.assertIn("apktool", packages)
        self.assertNotIn("git", packages)
        self.assertNotIn("openjdk-21", packages)
        self.assertEqual(len(packages), len(set(packages)), "pacotes não podem repetir")

    def test_base_profile_flags_missing_git(self):
        report = portai_toolkit.collect(with_versions=False, which=lambda name: "/bin/python3" if name == "python3" else None)
        self.assertEqual([s.tool.key for s in report.missing("base")], ["git"])
        self.assertEqual(report.installable("base"), ["git"])

    def test_install_command_uses_pkg_in_termux(self):
        with patch.object(portai_toolkit, "is_termux", return_value=True):
            self.assertEqual(portai_toolkit.install_command(["git"]), ["pkg", "install", "-y", "git"])
            self.assertEqual(portai_toolkit.install_command([]), [])

    def test_install_runs_runner(self):
        calls = []
        def runner(cmd, check=False):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0)
        with patch.object(portai_toolkit, "is_termux", return_value=True):
            self.assertEqual(portai_toolkit.install(["jadx"], runner=runner), 0)
        self.assertEqual(calls, [["pkg", "install", "-y", "jadx"]])

    def test_data_home_respects_env_and_creates_dirs(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"PORTAI_HOME": temp}):
            self.assertEqual(portai_toolkit.data_home(), Path(temp))
            dirs = portai_toolkit.ensure_data_dirs()
            self.assertTrue(all(path.is_dir() for path in dirs.values()))

    def test_report_json_roundtrip(self):
        import json
        report = portai_toolkit.collect(with_versions=False, which=lambda name: None)
        data = json.loads(portai_toolkit.report_json(report))
        self.assertTrue(all(item["ok"] is False for item in data["tools"]))

    def test_cli_parser_subcommands(self):
        parser = portai.build_parser()
        self.assertEqual(parser.parse_args(["doctor", "--json"]).json, True)
        self.assertEqual(parser.parse_args(["analisar", "x"]).pasta, "x")
        self.assertTrue(parser.parse_args(["instalar", "--base", "-y"]).base)
        self.assertIsNone(parser.parse_args([]).command)

    def test_cli_analyze_writes_reports(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "proj"; project.mkdir()
            (project / "main.cpp").write_text("#include <windows.h>\n", encoding="utf-8")
            reports = Path(temp) / "reports"
            with patch.object(portai, "REPORTS", reports), patch.object(portai.console, "print"):
                self.assertEqual(portai.run_cli(["analisar", str(project)]), 0)
            self.assertEqual(len(list(reports.glob("portai-*.json"))), 1)
            with patch.object(portai.console, "print"):
                self.assertEqual(portai.run_cli(["analisar", str(Path(temp) / "nao-existe")]), 1)


if __name__ == "__main__":
    unittest.main()
