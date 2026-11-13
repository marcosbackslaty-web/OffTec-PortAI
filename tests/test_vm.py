import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import portai_desktop as pd
import portai_vm as vm


class VmTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"PORTAI_HOME": self.tmp.name, "PREFIX": self.tmp.name})
        self.env.start()
        self.base = Path(self.tmp.name) / "imgs"
        (self.base / "sub").mkdir(parents=True)

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def _file(self, name, size=vm.MIN_SIZE + 1):
        p = self.base / "sub" / name
        with open(p, "wb") as f:
            f.truncate(size)
        return p

    def test_find_images_filters_and_guesses_arch(self):
        self._file("ubuntu-24.04-desktop-arm64.iso")
        self._file("win11.iso")
        self._file("disco.qcow2")
        self._file("pequeno.iso", size=1024)
        self._file("foto.jpg")
        found = {f["name"]: f for f in vm.find_images([self.base])}
        self.assertEqual(set(found), {"ubuntu-24.04-desktop-arm64.iso", "win11.iso", "disco.qcow2"})
        self.assertEqual(found["ubuntu-24.04-desktop-arm64.iso"]["arch"], "aarch64")
        self.assertEqual(found["win11.iso"]["arch"], "x86_64")

    def test_iso_command_has_cdrom_and_disk(self):
        cmd = vm.build_command("/x/win11.iso", "x86_64", 4096, 4, "/d/win11.qcow2")
        self.assertEqual(cmd[0], "qemu-system-x86_64")
        self.assertIn("-cdrom", cmd)
        self.assertIn("file=/d/win11.qcow2,if=virtio,format=qcow2", cmd)

    def test_aarch64_uses_uefi_and_virt(self):
        cmd = vm.build_command("/x/disco.qcow2", "aarch64")
        self.assertIn("virt", cmd)
        self.assertTrue(any(c.endswith("edk2-aarch64-code.fd") for c in cmd))

    def test_readonly_image_uses_snapshot(self):
        p = self._file("ro.img")
        p.chmod(0o444)
        cmd = vm.build_command(str(p), "x86_64")
        if not os.access(p, os.W_OK):
            self.assertIn("-snapshot", cmd)

    def test_install_and_errors(self):
        self.assertIn("qemu-system-aarch64", vm.install_commands("aarch64")[1])
        with self.assertRaises(ValueError):
            vm.install_commands("mips")
        with self.assertRaises(ValueError):
            vm.build_command("/x/a.zip", "x86_64")
        with self.assertRaises(RuntimeError):
            vm.start(str(self.base / "nao-existe.iso"))

    def test_debian_fixa_downloads_once(self):
        steps = vm.debian_prepare_commands("20G")
        self.assertEqual([s[0] for s in steps], ["curl", "qemu-img", "mv"])
        self.assertIn(vm.DEBIAN_URL, steps[0])
        self.assertEqual(steps[-1][-1], str(vm.debian_path()))
        vm.debian_path().write_bytes(b"x")
        self.assertEqual(vm.debian_prepare_commands(), [])
        self.assertTrue(vm.status()["debian"]["exists"])

    def test_debian_cli_parses(self):
        import portai
        a = portai.build_parser().parse_args(["vm", "debian", "--ram", "6144"])
        self.assertEqual((a.vm_cmd, a.ram, a.disco), ("debian", 6144, "20G"))


class DesktopAiTests(unittest.TestCase):
    def test_setup_ai_writes_script_and_launchers_into_distro(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"PREFIX": tmp, "PORTAI_HOME": tmp, "HOME": tmp}):
            pd.rootfs("ubuntu").mkdir(parents=True)
            keys = pd.keys_file()
            keys.parent.mkdir(parents=True)
            keys.write_text("IA_PADRAO=claude\n")
            written = pd.setup_ai("ubuntu")
            ia = pd.rootfs("ubuntu") / "usr" / "local" / "bin" / "ia"
            self.assertTrue(ia.is_file() and os.access(ia, os.X_OK))
            self.assertIn("api.anthropic.com", ia.read_text())
            self.assertTrue((pd.rootfs("ubuntu") / "root" / "Desktop" / "assistente-ia.desktop").is_file())
            self.assertTrue(any(w.endswith("ia.env") for w in written))

    def test_ai_extras_in_install(self):
        flat = " ".join(" ".join(s) for s in pd.install_commands("debian", "xfce"))
        self.assertIn("firefox-esr", flat)
        self.assertIn("jq", flat)


if __name__ == "__main__":
    unittest.main()
