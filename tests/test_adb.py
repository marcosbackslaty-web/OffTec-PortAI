import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import portai_adb as pa

FAKE_ADB = r"""#!/bin/sh
# adb falso para testes: responde conforme o subcomando
[ "$1" = "-s" ] && shift 2
case "$1" in
  devices) printf 'List of devices attached\nemulator-5554 offline transport_id:9\nZY22ABC  device usb:1-1 product:rtwo model:moto_X40 device:rtwo transport_id:1\n192.168.0.20:41234 device product:gts11 model:SM_X736B device:gts11 transport_id:2\nEMU1 unauthorized usb:1-2 transport_id:3\n' ;;
  pair) [ "$3" = "123456" ] && echo "Successfully paired to $2 [guid=adb-x]" || echo "Failed: Wrong password or connection was dropped." ;;
  connect) echo "connected to $2" ;;
  install|install-multiple) echo "Performing Streamed Install ($#)"; echo "Success" ;;
  push) echo "1 file pushed" ;;
  uninstall) echo "Success" ;;
  shell) case "$2" in
           pm*) printf 'package:com.b.app\npackage:com.a.app\n' ;;
           *) printf 'motorola\nmoto X40\n16\n36\narm64-v8a\nadreno\n  level: 87\n/dev/block/dm-1 469G 100G 369G 22%% /data\n' ;;
         esac ;;
  exec-out) printf '\211PNG\r\n\032\n'; head -c 200 /dev/zero ;;
esac
"""


class AdbTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        bin_dir = Path(self.tmp.name) / "bin"
        bin_dir.mkdir()
        (bin_dir / "adb").write_text(FAKE_ADB)
        (bin_dir / "adb").chmod(0o755)
        self.env = patch.dict(os.environ, {"PATH": f"{bin_dir}:{os.environ['PATH']}", "PORTAI_HOME": self.tmp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_devices(self):
        d = pa.devices()
        self.assertEqual([x["serial"] for x in d], ["ZY22ABC", "192.168.0.20:41234", "EMU1"])
        self.assertEqual(d[0]["model"], "moto X40")
        self.assertFalse(d[0]["wifi"])
        self.assertTrue(d[1]["wifi"])
        self.assertEqual(d[2]["state"], "unauthorized")

    def test_pair_connect_validation(self):
        self.assertIn("Successfully", pa.pair("192.168.0.20", 37123, "123456"))
        with self.assertRaises(pa.AdbError):
            pa.pair("192.168.0.20", 37123, "000000")
        with self.assertRaises(pa.AdbError):
            pa.pair("192.168.0.20", 37123, "12a456")
        with self.assertRaises(pa.AdbError):
            pa.connect("192.168.0.20; rm -rf /", 5555)
        self.assertEqual(pa.connect("192.168.0.20", "41234"), "192.168.0.20:41234")

    def test_info_apps_install(self):
        i = pa.info("ZY22ABC")
        self.assertEqual((i["modelo"], i["android"], i["bateria"], i["gpu"]), ("moto X40", "16", "87%", "adreno"))
        self.assertEqual(i["armazenamento"], "369G livres de 469G")
        self.assertEqual(pa.packages("ZY22ABC"), ["com.a.app", "com.b.app"])
        apk = Path(self.tmp.name) / "app.apk"
        apk.write_bytes(b"PK")
        self.assertIn("Success", pa.install("ZY22ABC", str(apk)))
        import zipfile
        bundle = Path(self.tmp.name) / "app.apks"
        with zipfile.ZipFile(bundle, "w") as z:
            z.writestr("base.apk", b"PK")
            z.writestr("split_config.arm64_v8a.apk", b"PK")
            z.writestr("toc.pb", b"x")
        self.assertIn("(4)", pa.install("ZY22ABC", str(bundle)))  # install-multiple -r + 2 partes
        with self.assertRaises(pa.AdbError):
            pa.install("ZY22ABC", "/nao/existe.apk")
        with self.assertRaises(pa.AdbError):
            pa.install("bad serial!", str(apk))
        with self.assertRaises(pa.AdbError):
            pa.uninstall("ZY22ABC", "nao-e-pacote")
        with self.assertRaises(pa.AdbError):
            pa.push("ZY22ABC", str(apk), "/data/local/tmp/")

    def test_screenshot_and_apks(self):
        out = pa.screenshot("192.168.0.20:41234", Path(self.tmp.name) / "prints")
        self.assertTrue(Path(out).read_bytes().startswith(b"\x89PNG"))
        self.assertIn("192_168_0_20_41234", out)
        d = Path(self.tmp.name) / "saidas"
        d.mkdir()
        (d / "meu.apk").write_bytes(b"PK")
        (d / "nota.txt").write_text("x")
        self.assertEqual([a["name"] for a in pa.apks([Path(self.tmp.name)])], ["meu.apk"])

    def test_cli_json(self):
        import portai
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = portai.run_cli(["adb", "dispositivos"])
        data = json.loads(buf.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["dispositivos"]), 3)
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = portai.run_cli(["adb", "parear", "192.168.0.20", "37123", "000000"])
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(buf.getvalue())["ok"])


if __name__ == "__main__":
    unittest.main()
