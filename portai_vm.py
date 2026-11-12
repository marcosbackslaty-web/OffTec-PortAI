"""Roda sistemas operacionais que estão em arquivos no aparelho (ISO, IMG,
QCOW2, VHD, VMDK, VDI) como máquina virtual QEMU, na tela do Termux:X11.

Sem KVM no Android, a emulação é por software (TCG): sistemas ARM64 rodam
bem melhor que x86_64. Tudo pelo comando `portai vm`.
"""

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
from pathlib import Path

import portai_toolkit

EXTS = {".iso": "instalador/live", ".img": "disco", ".qcow2": "disco QEMU", ".raw": "disco",
        ".vhd": "disco Hyper-V", ".vhdx": "disco Hyper-V", ".vmdk": "disco VMware", ".vdi": "disco VirtualBox"}
ARCHES = {
    "x86_64": {"bin": "qemu-system-x86_64", "pkg": "qemu-system-x86-64", "label": "PC (x86_64) — Windows, Ubuntu PC… (lento)"},
    "aarch64": {"bin": "qemu-system-aarch64", "pkg": "qemu-system-aarch64", "label": "ARM64 — Ubuntu ARM, Raspberry Pi OS… (mais rápido)"},
}
MIN_SIZE = 8 * 1024 * 1024
DISPLAY = ":0"


def vms_dir() -> Path:
    path = portai_toolkit.data_home() / "vms"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_path() -> Path:
    return portai_toolkit.data_home() / "vm.log"


def search_roots() -> list[Path]:
    home = Path.home()
    roots = [home / "storage" / "shared", Path("/sdcard"), vms_dir()]
    storage = Path("/storage")
    try:
        roots += [p for p in storage.iterdir() if re.fullmatch(r"[0-9A-F]{4}-[0-9A-F]{4}", p.name)]  # cartão SD
    except OSError:
        pass
    seen, out = set(), []
    for r in roots:
        try:
            key = str(r.resolve())
        except OSError:
            continue
        if r.is_dir() and key not in seen:
            seen.add(key)
            out.append(r)
    return out


def guess_arch(name: str) -> str:
    n = name.lower()
    return "aarch64" if re.search(r"arm64|aarch64|armv8|raspi|raspberry|rpi", n) else "x86_64"


def find_images(roots: list[Path] | None = None, max_depth: int = 4) -> list[dict]:
    found: dict[str, dict] = {}
    for root in roots if roots is not None else search_roots():
        base_depth = len(root.parts)
        for cur, dirs, files in os.walk(root, followlinks=False):
            if len(Path(cur).parts) - base_depth >= max_depth:
                dirs[:] = []
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("Android", "proc")]
            for f in files:
                ext = Path(f).suffix.lower()
                if ext not in EXTS:
                    continue
                p = Path(cur) / f
                try:
                    size = p.stat().st_size
                    real = str(p.resolve())
                except OSError:
                    continue
                if size < MIN_SIZE or real in found:
                    continue
                found[real] = {"path": str(p), "name": f, "size": size, "kind": EXTS[ext],
                               "arch": guess_arch(f), "writable": os.access(p, os.W_OK)}
    return sorted(found.values(), key=lambda x: x["name"].lower())


def install_commands(arch: str) -> list[list[str]]:
    if arch not in ARCHES:
        raise ValueError(f"Arquitetura desconhecida: {arch}. Use: {', '.join(ARCHES)}")
    return [["pkg", "install", "-y", "x11-repo"],
            ["pkg", "install", "-y", ARCHES[arch]["pkg"], "qemu-utils", "termux-x11-nightly"]]


def _prefix() -> Path:
    return Path(os.environ.get("PREFIX", "/data/data/com.termux/files/usr"))


def build_command(image: str, arch: str, ram_mb: int = 4096, cpus: int = 4, disk: str | None = None) -> list[str]:
    """Linha de comando do QEMU para o arquivo escolhido."""
    if arch not in ARCHES:
        raise ValueError(f"Arquitetura desconhecida: {arch}")
    img = Path(image)
    ext = img.suffix.lower()
    if ext not in EXTS:
        raise ValueError(f"Tipo de arquivo não suportado: {ext}")
    cmd = [ARCHES[arch]["bin"], "-m", str(int(ram_mb)), "-smp", str(int(cpus)),
           "-accel", "tcg,thread=multi", "-display", "gtk,show-menubar=off", "-name", img.stem,
           "-netdev", "user,id=net0", "-device", "virtio-net-pci,netdev=net0"]
    if arch == "x86_64":
        cmd += ["-machine", "q35", "-cpu", "max", "-vga", "std", "-usb", "-device", "usb-tablet"]
    else:
        fw = _prefix() / "share" / "qemu" / "edk2-aarch64-code.fd"
        cmd += ["-machine", "virt", "-cpu", "max", "-bios", str(fw), "-device", "virtio-gpu-pci",
                "-device", "qemu-xhci", "-device", "usb-kbd", "-device", "usb-tablet"]
    if ext == ".iso":
        cmd += ["-cdrom", str(img), "-boot", "order=dc"]
        if disk:
            cmd += ["-drive", f"file={disk},if=virtio,format=qcow2"]
    else:
        fmt = {".qcow2": "qcow2", ".vhd": "vpc", ".vhdx": "vhdx", ".vmdk": "vmdk", ".vdi": "vdi"}.get(ext, "raw")
        drive = f"file={img},if=virtio,format={fmt}"
        cmd += ["-drive", drive]
        if not os.access(img, os.W_OK):
            cmd.append("-snapshot")  # arquivo só-leitura (ex.: cartão SD): alterações ficam na memória
    return cmd


def ensure_disk(image: str, size: str = "32G") -> str:
    """Para ISOs: cria (uma vez) um disco virtual onde o sistema será instalado."""
    disk = vms_dir() / (Path(image).stem + ".qcow2")
    if not disk.exists():
        subprocess.run(["qemu-img", "create", "-f", "qcow2", str(disk), size], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    return str(disk)


def _pids(pattern: str) -> list[int]:
    if not shutil.which("pgrep"):
        return []
    r = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True, check=False)
    return [int(p) for p in r.stdout.split() if p.isdigit() and int(p) != os.getpid()]


def start(image: str, arch: str | None = None, ram_mb: int = 4096, cpus: int = 4, disk_size: str = "32G") -> dict:
    arch = arch or guess_arch(Path(image).name)
    if not Path(image).is_file():
        raise RuntimeError(f"Arquivo não encontrado: {image} (no Termux, rode termux-setup-storage para ver o armazenamento)")
    if not shutil.which(ARCHES[arch]["bin"]):
        raise RuntimeError(f"QEMU {arch} não instalado. Rode: portai vm instalar {arch}")
    disk = ensure_disk(image, disk_size) if image.lower().endswith(".iso") else None
    log = open(log_path(), "ab")
    env = os.environ.copy()
    env["DISPLAY"] = DISPLAY
    if not _pids("termux-x11") and shutil.which("termux-x11"):
        subprocess.Popen(["termux-x11", DISPLAY], env=env, stdout=log, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, start_new_session=True)
    cmd = build_command(image, arch, ram_mb, cpus, disk)
    proc = subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                            start_new_session=True)
    return {"pid": proc.pid, "arch": arch, "disk": disk, "command": " ".join(cmd), "log": str(log_path())}


def stop() -> bool:
    killed = False
    for pid in _pids("qemu-system-"):
        try:
            os.kill(pid, signal.SIGTERM)
            killed = True
        except OSError:
            pass
    return killed


def status() -> dict:
    tail = ""
    try:
        tail = "\n".join(log_path().read_text(encoding="utf-8", errors="replace").splitlines()[-6:])
    except OSError:
        pass
    return {
        "arches": {k: {"label": a["label"], "installed": bool(shutil.which(a["bin"]))} for k, a in ARCHES.items()},
        "running": bool(_pids("qemu-system-")),
        "roots": [str(r) for r in search_roots()],
        "log_tail": tail,
    }
