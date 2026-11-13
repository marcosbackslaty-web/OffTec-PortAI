import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import portai_desktop as pd


class UserAndCompatTests(unittest.TestCase):
    def test_user_login_and_compat_env(self):
        cmd = pd.startup_command("debian", "xfce", True, user=pd.USER)
        self.assertIn("proot-distro login debian --user portai --shared-tmp", cmd)
        self.assertIn("MOZ_FAKE_NO_SANDBOX=1", cmd)
        self.assertNotIn("--user", pd.startup_command("debian", "xfce", True))

    def test_install_creates_user_with_sudo(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"PREFIX": tmp}):
            steps = pd.install_commands("ubuntu", "xfce")
        self.assertIn("sudo", steps[-2][-1])
        self.assertIn("useradd -m -s /bin/bash portai", steps[-1][-1])
        self.assertIn("/etc/sudoers.d/portai", steps[-1][-1])

    def test_has_user_reads_rootfs(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"PREFIX": tmp}):
            root = pd.rootfs("debian")
            (root / "etc").mkdir(parents=True)
            (root / "etc" / "passwd").write_text("root:x:0:0::/root:/bin/bash\n")
            self.assertFalse(pd.has_user("debian"))
            (root / "home" / "portai").mkdir(parents=True)
            (root / "etc" / "passwd").write_text("root:x:0:0::/root:/bin/bash\nportai:x:1000:1000::/home/portai:/bin/bash\n")
            self.assertTrue(pd.has_user("debian"))


class DockAndAndroidTests(unittest.TestCase):
    def test_dock_only_on_supported_systems(self):
        self.assertIn("plank", " ".join(pd.install_commands("debian", "dock")[-2]))
        with self.assertRaises(ValueError):
            pd.install_commands("archlinux", "dock")
        with self.assertRaises(ValueError):
            pd.startup_command("termux", "dock", False)
        self.assertIn("portai-dock", pd.startup_command("fedora", "dock", False))

    def test_setup_session_writes_scripts(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"PREFIX": tmp}):
            pd.rootfs("debian").mkdir(parents=True)
            out = pd.setup_session("debian")
            bin_dir = pd.rootfs("debian") / "usr" / "local" / "bin"
            self.assertEqual(len(out), 3)
            self.assertTrue((bin_dir / "portai-aparencia").is_file())
            self.assertIn("plank", (bin_dir / "portai-dock").read_text())
            self.assertIn("android.intent.action.VIEW", (bin_dir / "android").read_text())
            self.assertTrue(os.access(bin_dir / "android", os.X_OK))
            self.assertEqual(pd.setup_session("termux"), [])

    def test_setup_ai_reaches_user_home(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"PREFIX": tmp, "HOME": tmp}):
            (pd.rootfs("ubuntu") / "home" / "portai").mkdir(parents=True)
            pd.setup_ai("ubuntu")
            self.assertTrue((pd.rootfs("ubuntu") / "home" / "portai" / "Desktop" / "assistente-ia.desktop").is_file())
            self.assertTrue((pd.rootfs("ubuntu") / "root" / "Desktop" / "assistente-ia.desktop").is_file())

    def test_limitador_script_uses_wireless_adb(self):
        self.assertIn("adb pair", pd.LIMITADOR_SCRIPT)
        self.assertIn("max_phantom_processes 2147483647", pd.LIMITADOR_SCRIPT)
        self.assertNotIn("__CMD__", pd.LIMITADOR_SCRIPT)

    def test_cli_flags(self):
        import portai
        a = portai.build_parser().parse_args(["desktop", "iniciar", "--root"])
        self.assertTrue(a.as_root)
        self.assertIsNone(portai.build_parser().parse_args(["desktop", "iniciar"]).as_root)
        self.assertEqual(portai.build_parser().parse_args(["desktop", "limitador"]).desk_cmd, "limitador")


class TelaTests(unittest.TestCase):
    def test_check_and_prefs(self):
        t = pd.check_tela({"modo": "custom", "tamanho": "2560X1600", "escala": 999, "toque": "direto"})
        self.assertEqual((t["tamanho"], t["escala"]), ("2560x1600", 300))
        args = pd.x11_pref_args(t)
        self.assertIn("displayResolutionCustom:2560x1600", args)
        self.assertIn("touchMode:3", args)
        self.assertIn("fullscreen:true", args)
        for bad in ({"modo": "x"}, {"tamanho": "abc"}, {"tema": "azul"}, {"icones": "x"}):
            with self.assertRaises(ValueError):
                pd.check_tela(bad)

    def test_theme_env_and_session(self):
        dark = pd.theme_env(pd.check_tela({"texto": 150}))
        self.assertIn("GTK_THEME=Adwaita:dark", dark)
        self.assertIn("GDK_DPI_SCALE=1.50", dark)
        self.assertNotIn("GDK_DPI_SCALE", pd.theme_env(pd.check_tela({"tema": "claro"})))
        cmd = pd.startup_command("debian", "xfce", False, extra_env="GTK_THEME=Adwaita ")
        self.assertIn("sh -c 'portai-aparencia; exec startxfce4'", cmd)
        sc = pd.aparencia_script(pd.check_tela({"tema": "claro", "icones": "papirus-escuro"}))
        self.assertIn('T="Adwaita"', sc)
        self.assertIn('I="Papirus-Dark"', sc)

    def test_set_tela_saves(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"PORTAI_HOME": tmp, "PREFIX": tmp}):
            t, applied = pd.set_tela({"tema": "claro", "escala": None})
            self.assertFalse(applied)
            self.assertEqual(pd.tela_config()["tema"], "claro")
            self.assertEqual(pd.load_config()["tela"]["escala"], 100)


class PacotesTests(unittest.TestCase):
    def test_parsers(self):
        self.assertEqual(pd.parse_search("apt", "vlc - player\nvlc - dup")[0], {"name": "vlc", "desc": "player"})
        self.assertEqual(pd.parse_search("dnf", "gimp.aarch64 : GNU Image")[0]["name"], "gimp")
        self.assertEqual(pd.parse_search("pacman", "extra/gimp 2.10-1\n    GNU Image")[0]["desc"], "GNU Image")

    def test_commands_are_safe(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"PREFIX": tmp}):
            pd.rootfs("debian").mkdir(parents=True)
            cmd = pd.package_command("debian", "install", ["vlc", "gimp"])
            self.assertEqual(cmd[:3], ["proot-distro", "login", "debian"])
            self.assertIn("apt-get install -y vlc gimp", cmd[-1])
            with self.assertRaises(ValueError):
                pd.package_command("debian", "install", ["vlc; rm -rf /"])
            with self.assertRaises(RuntimeError):
                pd.package_command("fedora", "remove", ["vlc"])
            with self.assertRaises(ValueError):
                pd.search_packages("debian", "a;b")
        self.assertEqual(pd.package_command("termux", "remove", ["vlc"]), ["bash", "-c", "pkg remove -y vlc"])

    def test_popular_and_muon(self):
        labels = [p["label"] for p in pd.popular("ubuntu")]
        self.assertNotIn("Firefox", labels)
        self.assertTrue(any("Muon" in l for l in labels))
        self.assertFalse(any("Muon" in p["label"] for p in pd.popular("fedora")))
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"PREFIX": tmp}):
            root = pd.rootfs("debian")
            (root / "usr" / "bin").mkdir(parents=True)
            self.assertEqual(pd.store_launchers("debian"), [])
            (root / "usr" / "bin" / "muon").write_text("")
            out = pd.store_launchers("debian")
            self.assertTrue(any(o.endswith("Desktop/portai-muon.desktop") for o in out))
            self.assertIn("sudo -E muon", (root / "root" / "Desktop" / "portai-muon.desktop").read_text())


if __name__ == "__main__":
    unittest.main()
