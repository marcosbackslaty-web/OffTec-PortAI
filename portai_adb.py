"""Aparelhos via adb: parear outro Android por Wi-Fi e mandar APKs, arquivos,
prints e comandos — tudo a partir do tablet, sem PC.

Usa o `adb` oficial do Termux (pacote android-tools). Tudo pelo comando
`portai adb`; o app PortAI só aperta os botões.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import portai_toolkit

SERIAL = re.compile(r"^[A-Za-z0-9._:\-\[\]]+$")
HOST = re.compile(r"^(\d{1,3}(\.\d{1,3}){3}|localhost|[A-Za-z0-9.\-]+\.local)$")
PACKAGE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$")


class AdbError(RuntimeError):
    pass


def adb_path() -> str:
    path = shutil.which("adb")
    if not path:
        raise AdbError("adb não instalado. Rode: pkg install -y android-tools")
    return path


def ensure_adb() -> str:
    if not shutil.which("adb"):
        subprocess.run(["pkg", "install", "-y", "android-tools"], check=False, stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # não sujar a saída JSON
    return adb_path()


def _run(args: list[str], timeout: int = 60, serial: str | None = None) -> subprocess.CompletedProcess:
    cmd = [adb_path()] + (["-s", check_serial(serial)] if serial else []) + args
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise AdbError(f"O aparelho não respondeu a tempo ({' '.join(args[:2])}).") from exc


def check_serial(serial: str | None) -> str:
    if not serial or not SERIAL.match(serial):
        raise AdbError(f"Aparelho inválido: {serial!r}")
    return serial


def check_host_port(host: str, port: str | int) -> str:
    if not HOST.match(str(host)) or not str(port).isdigit() or not 1 <= int(port) <= 65535:
        raise AdbError("Use IP e porta da tela 'Depuração sem fio' (ex.: 192.168.0.20 e 37123).")
    return f"{host}:{int(port)}"


def parse_devices(out: str) -> list[dict]:
    """`adb devices -l` → [{serial, state, model, product, device, wifi}]."""
    devs = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 2 or line.startswith("*"):
            continue
        d = {"serial": parts[0], "state": parts[1], "model": "", "product": "", "device": ""}
        for p in parts[2:]:
            k, _, v = p.partition(":")
            if k in ("model", "product", "device"):
                d[k] = v.replace("_", " ") if k == "model" else v
        d["wifi"] = ":" in d["serial"] or "._adb-tls-connect." in d["serial"]
        devs.append(d)
    return devs


def devices() -> list[dict]:
    return parse_devices(_run(["devices", "-l"], timeout=20).stdout)


def pair(host: str, port: str | int, code: str) -> str:
    if not re.fullmatch(r"\d{6}", str(code)):
        raise AdbError("O código de pareamento tem 6 dígitos.")
    r = _run(["pair", check_host_port(host, port), str(code)], timeout=40)
    text = (r.stdout + r.stderr).strip()
    if "Successfully paired" not in text:
        raise AdbError(text or "Pareamento falhou.")
    return text


def connect(host: str, port: str | int) -> str:
    target = check_host_port(host, port)
    r = _run(["connect", target], timeout=30)
    text = (r.stdout + r.stderr).strip()
    if "connected to" not in text:
        raise AdbError(text or "Não conectou.")
    return target


def disconnect(serial: str) -> str:
    return (_run(["disconnect", check_serial(serial)], timeout=20).stdout or "").strip()


def info(serial: str) -> dict:
    script = ("getprop ro.product.manufacturer; getprop ro.product.model; getprop ro.build.version.release; "
              "getprop ro.build.version.sdk; getprop ro.product.cpu.abi; getprop ro.hardware.egl; "
              "dumpsys battery | grep -m1 level; df -h /data | tail -1")
    lines = (_run(["shell", script], timeout=40, serial=serial).stdout or "").splitlines() + [""] * 8
    disk = lines[7].split()
    return {"fabricante": lines[0].strip(), "modelo": lines[1].strip(), "android": lines[2].strip(),
            "sdk": lines[3].strip(), "abi": lines[4].strip(), "gpu": lines[5].strip(),
            "bateria": lines[6].split(":")[-1].strip() + "%" if ":" in lines[6] else "",
            "armazenamento": f"{disk[3]} livres de {disk[1]}" if len(disk) >= 4 else ""}


def apks(roots: list[Path] | None = None, max_depth: int = 3) -> list[dict]:
    """APKs prontos para instalar (saídas do PortAI e Download)."""
    home = Path.home()
    roots = roots if roots is not None else [portai_toolkit.data_home(), home / "storage" / "downloads", Path("/sdcard/Download")]
    found: dict[str, dict] = {}
    for root in roots:
        if not root.is_dir():
            continue
        base = len(root.parts)
        for cur, dirs, files in os.walk(root):
            if len(Path(cur).parts) - base >= max_depth:
                dirs[:] = []
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for f in files:
                if f.lower().endswith((".apk", ".apks")):
                    p = Path(cur) / f
                    try:
                        st, real = p.stat(), str(p.resolve())
                    except OSError:
                        continue
                    found.setdefault(real, {"path": str(p), "name": f, "size": st.st_size, "mtime": int(st.st_mtime)})
    return sorted(found.values(), key=lambda x: -x["mtime"])[:60]


def install(serial: str, apk: str) -> str:
    p = Path(apk)
    if not p.is_file() or p.suffix.lower() != ".apk":
        raise AdbError(f"APK não encontrado: {apk}")
    r = _run(["install", "-r", str(p)], timeout=600, serial=serial)
    text = (r.stdout + r.stderr).strip()
    if "Success" not in text:
        raise AdbError(text[-800:] or "Instalação falhou.")
    return text


def push(serial: str, path: str, dest: str = "/sdcard/Download/") -> str:
    p = Path(path)
    if not p.exists():
        raise AdbError(f"Arquivo não encontrado: {path}")
    if not dest.startswith("/sdcard/"):
        raise AdbError("Destino precisa ficar em /sdcard/.")
    r = _run(["push", str(p), dest], timeout=1800, serial=serial)
    if r.returncode != 0:
        raise AdbError((r.stderr or r.stdout).strip()[-800:])
    return dest + p.name


def screenshot(serial: str, out_dir: Path | None = None) -> str:
    out_dir = out_dir or Path("/sdcard/Download/PortAI-prints")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"print-{re.sub(r'[^A-Za-z0-9]', '_', serial)}-{time.strftime('%Y%m%d-%H%M%S')}.png"
    with open(out, "wb") as fh:
        r = subprocess.run([adb_path(), "-s", check_serial(serial), "exec-out", "screencap", "-p"], stdout=fh,
                           stderr=subprocess.PIPE, timeout=60, check=False)
    if r.returncode != 0 or out.stat().st_size < 100:
        out.unlink(missing_ok=True)
        raise AdbError((r.stderr or b"").decode(errors="replace").strip() or "Print falhou (tela bloqueada?).")
    return str(out)


def packages(serial: str, todos: bool = False) -> list[str]:
    r = _run(["shell", "pm list packages" + ("" if todos else " -3")], timeout=60, serial=serial)
    return sorted(line.split(":", 1)[1].strip() for line in r.stdout.splitlines() if line.startswith("package:"))


def uninstall(serial: str, package: str) -> str:
    if not PACKAGE.match(package):
        raise AdbError(f"Pacote inválido: {package}")
    r = _run(["uninstall", package], timeout=120, serial=serial)
    text = (r.stdout + r.stderr).strip()
    if "Success" not in text:
        raise AdbError(text or "Falhou.")
    return text
