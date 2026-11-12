"""Central de ferramentas do PortAI: um único lugar para saber o que existe,
o que falta, para que serve cada ferramenta e onde ficam os arquivos.

Substitui a necessidade de rodar vários scripts soltos e procurar
informação em vários lugares: `portai doctor`, `portai instalar`,
`portai info` e `portai atualizar` usam este registro.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

ROOT = Path(__file__).resolve().parent
# Repositório oficial do Termux (CDN mantida pelo projeto Termux).
TERMUX_OFFICIAL_MIRROR = "https://packages-cf.termux.dev/apt/termux-main"


def is_termux() -> bool:
    prefix = os.environ.get("PREFIX", "")
    return "com.termux" in prefix or Path("/data/data/com.termux/files/usr").is_dir()


def data_home() -> Path:
    """Pasta única de dados do usuário (relatórios, workspaces, saídas).

    `PORTAI_HOME` permite mudar o local; por padrão fica em ~/PortAI para
    não misturar dados com o código do repositório (que é atualizado por git).
    """
    custom = os.environ.get("PORTAI_HOME")
    return Path(custom).expanduser() if custom else Path.home() / "PortAI"


@dataclass(frozen=True)
class Tool:
    key: str
    label: str
    commands: tuple[str, ...]
    package: str | None  # pacote no repositório oficial do Termux
    area: str
    purpose: str
    profile: str = "completo"  # "base" = obrigatório, "completo" = recursos extras
    version_args: tuple[str, ...] = ("--version",)
    hint: str = ""

    def path(self, which: Callable[[str], str | None] = shutil.which) -> str | None:
        for command in self.commands:
            found = which(command)
            if found:
                return found
        return None


TOOLS: tuple[Tool, ...] = (
    Tool("python", "Python", ("python3", "python"), "python", "Base", "Executa o PortAI.", "base"),
    Tool("git", "Git", ("git",), "git", "Base", "Atualiza o PortAI e registra diffs dos workspaces.", "base"),
    Tool("java", "Java (OpenJDK 21)", ("java",), "openjdk-21", "APK", "Necessário para Apktool, apksigner e Gradle.", version_args=("-version",)),
    Tool("apktool", "Apktool", ("apktool",), "apktool", "APK", "Decodifica e reconstrói APKs (tradução de APK, rebuild)."),
    Tool("apksigner", "apksigner", ("apksigner",), "apksigner", "APK", "Assina e verifica APKs com a sua keystore.", version_args=("--version",)),
    Tool("zipalign", "zipalign", ("zipalign",), "aapt", "APK", "Alinha APKs antes da assinatura.", version_args=()),
    Tool("aapt", "aapt", ("aapt",), "aapt", "APK", "Lê pacote/versão do APK para instalar e abrir.", version_args=("version",)),
    Tool("aapt2", "aapt2", ("aapt2",), "aapt2", "APK", "Compila recursos em builds Gradle no Termux.", version_args=("version",)),
    Tool("jadx", "JADX", ("jadx",), "jadx", "APK", "Inspeção complementar de código Java/Kotlin do APK."),
    Tool("gradle", "Gradle", ("gradle",), "gradle", "Build", "Compila projetos Android sem gradlew."),
    Tool("cmake", "CMake", ("cmake",), "cmake", "Build", "Builds nativos (C/C++) e projetos NDK."),
    Tool("ninja", "Ninja", ("ninja",), "ninja", "Build", "Gerador de build usado com CMake."),
    Tool("clang", "Clang", ("clang",), "clang", "Build", "Compilador C/C++ local."),
    Tool("adb", "ADB", ("adb",), "android-tools", "Dispositivo", "Instala e abre APKs gerados (depuração sem fio)."),
    Tool("codex", "Codex CLI", ("codex",), "codex", "IA", "Assistência de IA no workspace isolado.",
         hint="Depois de instalar: codex login"),
    Tool("llama", "llama.cpp", ("llama-cli", "llama-server"), None, "IA local",
         "Modelos de IA rodando offline no aparelho (chat e API).", hint="portai llama instalar"),
    Tool("godot", "Godot", ("godot", "godot4"), None, "Jogos", "Exporta projetos Godot para Android.",
         hint="Instale o Godot e os templates de exportação Android."),
    Tool("which", "which", ("which",), "which", "Base", "Usado por scripts como o do JADX para achar o Java.", "completo", version_args=()),
    Tool("termux-api", "Termux:API", ("termux-battery-status",), "termux-api", "Dispositivo",
         "Bateria, Wi-Fi, lanterna, voz, notificações, câmera e sensores (precisa do app Termux:API).", version_args=()),
    Tool("termux-open", "termux-tools", ("termux-open",), "termux-tools", "Dispositivo", "Abre APKs/relatórios em outros apps.", version_args=()),
)

PROFILES = ("base", "completo")


@dataclass
class ToolStatus:
    tool: Tool
    path: str | None
    version: str = ""
    broken: bool = False  # instalado, mas não executa (ex.: CANNOT LINK EXECUTABLE)

    @property
    def ok(self) -> bool:
        return self.path is not None and not self.broken


@dataclass
class Report:
    statuses: list[ToolStatus]
    android_sdk: str | None
    environment: dict[str, str] = field(default_factory=dict)

    def missing(self, profile: str = "completo") -> list[ToolStatus]:
        wanted = {"base"} if profile == "base" else set(PROFILES)
        return [s for s in self.statuses if not s.ok and s.tool.profile in wanted]

    def broken(self) -> list[ToolStatus]:
        return [s for s in self.statuses if s.broken]

    def installable(self, profile: str = "completo") -> list[str]:
        packages: list[str] = []
        for status in self.missing(profile):
            if status.broken:
                continue
            pkg = status.tool.package
            if pkg and pkg not in packages:
                packages.append(pkg)
        return packages

    def to_dict(self) -> dict:
        return {
            "environment": self.environment,
            "android_sdk": self.android_sdk,
            "tools": [
                {"key": s.tool.key, "label": s.tool.label, "purpose": s.tool.purpose, "hint": s.tool.hint,
                 "ok": s.ok, "broken": s.broken, "path": s.path, "version": s.version,
                 "package": s.tool.package, "area": s.tool.area, "profile": s.tool.profile}
                for s in self.statuses
            ],
        }


BROKEN_MARKERS = ("CANNOT LINK EXECUTABLE", "error while loading shared libraries", "JAVA_HOME is not set")


def _probe(path: str, args: tuple[str, ...]) -> tuple[str, bool]:
    """Executa a ferramenta para ler a versão e detectar instalação quebrada."""
    if not args:
        return "", False
    try:
        proc = subprocess.run([path, *args], capture_output=True, text=True, timeout=20)
    except subprocess.TimeoutExpired:
        return "", False
    except OSError as exc:
        return str(exc)[:60], True
    output = (proc.stdout or "") + (proc.stderr or "")
    if any(marker in output for marker in BROKEN_MARKERS):
        return output.strip().splitlines()[0][:60], True
    lines = [ln.strip() for ln in output.splitlines() if ln.strip() and not set(ln.strip()) <= set("-=_*")]
    return (lines[0][:60] if lines else ""), False


def android_sdk() -> str | None:
    for var in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        value = os.environ.get(var)
        if value and Path(value).is_dir():
            return value
    for candidate in (Path.home() / "android-sdk", Path(os.environ.get("PREFIX", "/nonexistent")) / "share" / "android-sdk"):
        if candidate.is_dir():
            return str(candidate)
    return None


def collect(with_versions: bool = True, which: Callable[[str], str | None] = shutil.which) -> Report:
    statuses = []
    for tool in TOOLS:
        path = tool.path(which)
        version, broken = _probe(path, tool.version_args) if (path and with_versions) else ("", False)
        statuses.append(ToolStatus(tool, path, version, broken))
    env = {
        "Sistema": f"{platform.system()} {platform.machine()}",
        "Termux": "sim" if is_termux() else "não",
        "Python": sys.version.split()[0],
        "Código do PortAI": str(ROOT),
        "Dados do usuário": str(data_home()),
    }
    return Report(statuses, android_sdk(), env)


def install_command(packages: Iterable[str]) -> list[str]:
    packages = list(packages)
    if not packages:
        return []
    if is_termux():
        return ["pkg", "install", "-y", *packages]
    if shutil.which("apt-get"):
        return ["sudo", "apt-get", "install", "-y", *packages]
    return []


def install(packages: Iterable[str], runner: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> int:
    command = install_command(packages)
    if not command:
        return 0
    return runner(command, check=False).returncode


def ensure_data_dirs() -> dict[str, Path]:
    home = data_home()
    dirs = {
        "Relatórios": home / "relatorios",
        "Workspaces": home / "workspaces",
        "Saídas (APKs/traduções)": home / "saidas",
        "Projetos (coloque aqui)": home / "projetos",
    }
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return dirs


def update_repo(runner: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> tuple[int, str]:
    """git pull --ff-only no repositório do PortAI e reinstala requirements."""
    if not (ROOT / ".git").is_dir() or not shutil.which("git"):
        return 1, "O PortAI não está em um clone git; reinstale com install.sh."
    pull = runner(["git", "-C", str(ROOT), "pull", "--ff-only"], capture_output=True, text=True, check=False)
    out = (pull.stdout or "") + (pull.stderr or "")
    if pull.returncode != 0:
        return pull.returncode, out
    pip = runner([sys.executable, "-m", "pip", "install", "-q", "-r", str(ROOT / "requirements.txt")],
                 capture_output=True, text=True, check=False)
    return pip.returncode, out + (pip.stdout or "") + (pip.stderr or "")


def report_json(report: Report) -> str:
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2)


def broken_packages(report: Report) -> list[str]:
    packages: list[str] = []
    for status in report.broken():
        if status.tool.package and status.tool.package not in packages:
            packages.append(status.tool.package)
    return packages


def repair_commands(packages: Iterable[str]) -> list[list[str]]:
    """Binário quebrado no Termux quase sempre é biblioteca desatualizada:
    atualizar tudo e reinstalar o pacote resolve."""
    packages = list(packages)
    if not packages or not is_termux():
        return []
    return [["pkg", "upgrade", "-y"], ["pkg", "reinstall", "-y", *packages]]


def repair(packages: Iterable[str], runner: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> int:
    for command in repair_commands(packages):
        code = runner(command, check=False).returncode
        if code != 0:
            return code
    return 0
