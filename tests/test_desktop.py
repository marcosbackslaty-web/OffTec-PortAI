import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import portai_desktop as pd


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"PORTAI_HOME": self.tmp.name, "PREFIX": self.tmp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_termux_native_install_uses_x11_repo(self):
        steps = pd.install_commands("termux", "xfce")
        self.assertEqual(steps[0], ["pkg", "install", "-y", "x11-repo"])
        self.assertIn("termux-x11-nightly", steps[1])
        self.assertIn("xfce4", steps[1])
        self.assertNotIn("proot-distro", " ".join(" ".join(s) for s in steps))

    def test_ubuntu_install_uses_proot_distro_and_apt(self):
        steps = pd.install_commands("ubuntu", "lxqt")
        flat = [" ".join(s) for s in steps]
        self.assertIn("proot-distro install ubuntu", flat)
        self.assertTrue(any("apt-get install" in f and "lxqt-core" in f for f in flat))

    def test_distro_already_installed_skips_rootfs_install(self):
        pd.rootfs("debian").mkdir(parents=True)
        flat = [" ".join(s) for s in pd.install_commands("debian", "xfce")]
        self.assertNotIn("proot-distro install debian", flat)

    def test_families(self):
        self.assertIn("dnf install", " ".join(pd.install_commands("fedora", "xfce")[-1]))
        self.assertIn("pacman -Syu", " ".join(pd.install_commands("archlinux", "openbox")[-1]))

    def test_startup_command(self):
        self.assertIn("proot-distro login ubuntu --shared-tmp", pd.startup_command("ubuntu", "xfce", True))
        self.assertIn("startxfce4", pd.startup_command("ubuntu", "xfce", True))
        self.assertIn("PULSE_SERVER", pd.startup_command("ubuntu", "xfce", True))
        self.assertNotIn("PULSE_SERVER", pd.startup_command("termux", "openbox", False))
        self.assertIn("openbox-session", pd.startup_command("termux", "openbox", False))

    def test_invalid_choices(self):
        with self.assertRaises(ValueError):
            pd.install_commands("windows", "xfce")
        with self.assertRaises(ValueError):
            pd.startup_command("ubuntu", "gnome", True)

    def test_config_roundtrip_and_status(self):
        self.assertEqual(pd.load_config()["system"], "ubuntu")
        pd.save_config({"system": "debian", "desktop": "lxqt", "som": False})
        self.assertEqual(pd.load_config()["desktop"], "lxqt")
        st = pd.status()
        self.assertEqual(set(st["systems"]), {"termux", "ubuntu", "debian", "fedora", "archlinux"})
        self.assertFalse(st["systems"]["ubuntu"]["installed"]["xfce"])

    def test_start_refuses_when_not_installed(self):
        with self.assertRaises(RuntimeError):
            pd.start("ubuntu", "xfce")


if __name__ == "__main__":
    unittest.main()
