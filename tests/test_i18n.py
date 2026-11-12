import json
import re
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import portai_i18n as i18n
import portai
from portai import LocalizedConsole
from rich.table import Table
from unittest.mock import patch


class InterfaceLocalizationTests(unittest.TestCase):
    def setUp(self):
        self.old_path = i18n.CONFIG_PATH
        self.old_locale = i18n.get_locale()
        self.temp = tempfile.TemporaryDirectory()
        i18n.set_config_path(Path(self.temp.name) / "settings.json")
        i18n.save_locale("pt-BR")

    def tearDown(self):
        i18n.set_config_path(self.old_path)
        i18n._locale = self.old_locale
        self.temp.cleanup()

    def test_all_supported_languages_have_unicode_catalog_entries(self):
        self.assertEqual(i18n.LOCALES, ("pt-BR", "en", "es", "ar", "hi"))
        for locale in i18n.LOCALES:
            with self.subTest(locale=locale):
                label = i18n.translate_text("Idioma da interface", locale)
                self.assertTrue(label)
                self.assertEqual(label == "Idioma da interface", locale == "pt-BR")
                self.assertEqual(i18n.translate_text("AI Game Recreation Engine", locale), "AI Game Recreation Engine")
                if locale != "pt-BR":
                    catalog = i18n._CATALOGS[locale]
                    self.assertTrue(all(value.strip() for value in catalog.values()))
        self.assertIn("العربية", i18n.LOCALE_NAMES["ar"])
        self.assertIn("हिन्दी", i18n.LOCALE_NAMES["hi"])

    def test_persistent_preference_and_portuguese_fallback(self):
        i18n.save_locale("hi")
        self.assertEqual(i18n.load_locale(), "hi")
        self.assertEqual(json.loads(i18n.CONFIG_PATH.read_text(encoding="utf-8"))["interface_language"], "hi")
        i18n.CONFIG_PATH.write_text('{"interface_language":"invalid"}', encoding="utf-8")
        self.assertEqual(i18n.load_locale(), "pt-BR")

    def test_translation_preserves_paths_commands_ids_and_markup_code(self):
        value = "Pasta do projeto: /tmp/Projeto Alpha; execute `codex login status`; ID `quest_42`."
        rendered = i18n.translate_text(value, "en")
        self.assertIn("/tmp/Projeto", rendered)
        self.assertIn("`codex login status`", rendered)
        self.assertIn("`quest_42`", rendered)
        self.assertIn("project folder", rendered.lower())

    def test_rich_interface_output_uses_selected_catalog(self):
        for locale in i18n.LOCALES:
            with self.subTest(locale=locale):
                i18n.save_locale(locale)
                table = Table()
                table.add_column("Idioma")
                table.add_row("Configurações")
                stream = StringIO()
                output = LocalizedConsole(file=stream, force_terminal=False, color_system=None)
                output.print(table)
                expected = i18n.translate_text("Configurações", locale)
                self.assertIn(expected, stream.getvalue())
                self.assertIn(i18n.translate_text("Idioma", locale), stream.getvalue())

    def test_markdown_report_uses_locale_and_keeps_json_identifiers(self):
        i18n.save_locale("en")
        report_data = {
            "version": "0.3.0", "project": "/tmp/Project", "files_found": 2,
            "text_files_read": 1, "verdict": "Review dependencies", "languages": {"C#": 1},
            "build_files": ["build.gradle"], "windows_indicators": {}, "limitations": [],
        }
        with patch.object(portai, "REPORTS", Path(self.temp.name) / "reports"):
            markdown, json_report = portai.save_report(report_data)
        self.assertIn("OffTec PortAI Report", markdown.read_text(encoding="utf-8"))
        self.assertIn("`/tmp/Project`", markdown.read_text(encoding="utf-8"))
        self.assertEqual(json.loads(json_report.read_text(encoding="utf-8"))["project"], "/tmp/Project")

    def test_settings_menu_persists_language_selection(self):
        with patch.object(portai, "ask_prompt", return_value="4"), patch.object(portai.console, "print"):
            portai.interface_language_menu()
        self.assertEqual(i18n.load_locale(), "ar")

    def test_category_menu_renders_localized_text_without_a_table(self):
        for locale in i18n.LOCALES:
            with self.subTest(locale=locale):
                i18n.save_locale(locale)
                stream = StringIO()
                previous = portai.console
                portai.console = LocalizedConsole(file=stream, force_terminal=False, color_system=None, width=28)
                try:
                    with patch.object(portai, "banner"), patch.object(portai, "ask_prompt", return_value="0"):
                        portai.menu()
                finally:
                    portai.console = previous
                rendered = stream.getvalue()
                # Títulos longos quebram dentro do cartão: ignora as bordas ao comparar o texto.
                readable = " ".join(re.sub(r"[│╭╮╰╯─]", " ", rendered).split())
                for category in ("01 — PROJETOS", "02 — APK BUILD CENTER", "03 — TRADUÇÃO", "04 — GAME PORTABILITY", "05 — SISTEMA E CONFIGURAÇÕES"):
                    self.assertIn(" ".join(i18n.translate_text(category, locale).split()), readable)
                self.assertNotIn("┌", rendered)

    def test_translation_quality_uses_the_registered_report_path(self):
        reports = Path(self.temp.name) / "reports"
        output = Path(self.temp.name) / "outside-output"
        output.mkdir()
        report = output / "translation-report-test.json"
        report.write_text(json.dumps({
            "entries": [{"status": "approved"}, {"status": "review"}],
            "scan_errors": [{"path": "strings.json", "error": "fixture"}],
        }), encoding="utf-8")
        with patch.object(portai, "REPORTS", reports), patch.object(portai.console, "print") as rendered:
            portai._record_translation_report(report)
            portai._show_translation_quality()
        output_text = " ".join(str(call) for call in rendered.call_args_list)
        self.assertIn(str(report), output_text)
        self.assertIn("Aprovadas: 1", output_text)
        self.assertTrue((reports / "translation-history.json").is_file())


if __name__ == "__main__":
    unittest.main()
