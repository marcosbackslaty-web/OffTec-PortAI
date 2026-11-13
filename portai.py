#!/usr/bin/env python3
"""OffTec PortAI — assistente de análise e adaptação de projetos para Android."""

from __future__ import annotations

import json
import difflib
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import portai_toolkit
from portai_i18n import (
    LOCALES, LOCALE_NAMES, ask_confirm, ask_prompt, get_locale, save_locale,
    translate_text,
)

try:
    from rich import box
    from rich.align import Align
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt
    from rich.table import Table
    from rich.text import Text
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print("Dependência ausente. Instale com: python -m pip install -r requirements.txt")
    raise SystemExit(1)

install_rich_traceback(show_locals=False)


class LocalizedConsole(Console):
    """Translate known UI phrases at Rich's string rendering boundary."""
    def render_str(self, text: str, *args: Any, **kwargs: Any):
        return super().render_str(translate_text(text), *args, **kwargs)


console = LocalizedConsole()
ROOT = Path(__file__).resolve().parent
# Dados do usuário ficam fora do código (que é atualizado via git), numa pasta
# única e fácil de achar: ~/PortAI (ou $PORTAI_HOME).
DATA_HOME = portai_toolkit.data_home()
REPORTS = DATA_HOME / "relatorios"
WORKSPACES = DATA_HOME / "workspaces"
VERSION = "0.4.2"
MAX_FILES = 3000
MAX_TEXT_BYTES = 1_000_000
MAX_SCAN_DIRS = 25000
MAX_CANDIDATES = 80
PROJECT_MARKERS = {
    "CMakeLists.txt", "Makefile", "meson.build", "Cargo.toml", "go.mod",
    "package.json", "pyproject.toml", "requirements.txt", "setup.py",
    "build.gradle", "build.gradle.kts", "pom.xml", "AndroidManifest.xml",
    "*.sln", "*.csproj", "*.vcxproj", "*.vbproj", "*.pro",
}
IGNORED_DIRS = {
    ".git", ".gradle", ".idea", ".venv", "venv", "node_modules",
    "__pycache__", "build", "dist", "target", "bin", "obj",
    ".next", ".pytest_cache", "workspaces", ".cache", ".npm", ".rustup",
    ".cargo", ".sdkman", "android-sdk", "llama.cpp",
}
SOURCE_EXTS = {
    ".c", ".h", ".cc", ".cpp", ".hpp", ".cxx", ".cs", ".py",
    ".java", ".kt", ".kts", ".js", ".ts", ".rs", ".go", ".html",
    ".xml", ".gradle", ".bat", ".ps1", ".sh", ".json", ".toml",
    ".yaml", ".yml", ".cmake", ".txt", ".md", ".properties",
}
BUILD_NAMES = {
    "CMakeLists.txt", "Makefile", "meson.build", "Cargo.toml",
    "go.mod", "package.json", "pyproject.toml", "requirements.txt",
    "CMakePresets.json",
    "setup.py", "build.gradle", "build.gradle.kts", "pom.xml",
    "AndroidManifest.xml", "README", "README.md", "README.txt",
}
LANGUAGES = {
    ".c": "C", ".h": "C/C++ header", ".cc": "C++", ".cpp": "C++",
    ".hpp": "C++ header", ".cxx": "C++", ".cs": "C#",
    ".py": "Python", ".java": "Java", ".kt": "Kotlin",
    ".kts": "Kotlin DSL", ".js": "JavaScript", ".ts": "TypeScript",
    ".rs": "Rust", ".go": "Go", ".html": "HTML", ".xml": "XML",
    ".gradle": "Gradle", ".bat": "Windows Batch", ".ps1": "PowerShell",
    ".sh": "Shell", ".json": "JSON", ".toml": "TOML",
}
PATTERNS = {
    "Windows API / headers": r"\b(windows\.h|WinMain|CreateWindowEx|MessageBoxW)\b",
    "Registry do Windows": r"\b(RegOpenKeyEx|RegSetValueEx|HKEY_CURRENT_USER)\b",
    "Processos Windows": r"\b(CreateProcessW|ShellExecuteW|COMSPEC)\b",
    "DirectX / Direct3D": r"\b(DirectX|Direct3D|D3D11CreateDevice|IDirect3D)\b",
    ".NET UI Windows": r"\b(System\.Windows\.Forms|PresentationFramework|WPF)\b",
    "Caminhos Windows": r"\b[A-Za-z]:\\\\(?:Windows|Program Files|Users)\\",
    "Chamadas possivelmente específicas do Windows": r"\b(GetLastError|LoadLibraryW|GetModuleHandleW|HRESULT)\b",
}

def banner() -> None:
    brand = Text.assemble(
        ("OFFTEC", "bold white"),
        (" / ", "dim"),
        ("PORTAI", "bold bright_red"),
    )
    brand.append(f"   v{VERSION}", style="dim")
    detail = Text(translate_text("GAME PORTABILITY  •  ANDROID TOOLING  •  TERMUX"), style="dim")
    console.print(Panel(
        Align.left(Text.assemble(brand, "\n", detail)),
        border_style="bright_red",
        box=box.ROUNDED,
        padding=(0, 2),
    ))

def section(title: str) -> None:
    console.print()
    console.print(Text(translate_text(title), style="bold bright_red"))

def yesno(value: bool) -> str:
    return "[bright_green]OK[/]" if value else "[yellow]NÃO ENCONTRADO[/]"

def show_doctor(report: "portai_toolkit.Report | None" = None) -> "portai_toolkit.Report":
    """Diagnóstico único: cada ferramenta, para que serve, onde está e como instalar."""
    report = report or portai_toolkit.collect()
    section("DIAGNÓSTICO DO AMBIENTE")
    env = Table.grid(padding=(0, 2))
    env.add_column(style="white"); env.add_column(style="bright_red")
    for key, value in report.environment.items():
        env.add_row(key, value)
    env.add_row("Android SDK", report.android_sdk or "não encontrado (só necessário para Gradle/NDK)")
    console.print(env)
    table = Table(box=box.ROUNDED, border_style="grey50", header_style="bold bright_red", expand=True)
    table.add_column("Área", style="dim", no_wrap=True)
    table.add_column("Ferramenta", style="white", no_wrap=True)
    table.add_column("Estado", max_width=34)
    table.add_column("Para que serve / como instalar", ratio=1, min_width=24)
    for status in report.statuses:
        tool = status.tool
        if status.broken:
            state = "[red]QUEBRADO[/]"
            detail = f"{tool.purpose}\n[dim]{status.version} — rode: portai instalar (atualiza e reinstala)[/]"
        elif status.ok:
            state = f"[bright_green]OK[/] [dim]{status.version[:28]}[/]" if status.version else "[bright_green]OK[/]"
            detail = tool.purpose
        else:
            state = "[red]FALTA[/]" if tool.profile == "base" else "[yellow]opcional[/]"
            how = f"pkg install {tool.package}" if tool.package else tool.hint
            detail = f"{tool.purpose}\n[dim]{how}[/]"
        table.add_row(tool.area, tool.label, state, detail)
    console.print(table)
    ready = sum(1 for s in report.statuses if s.ok)
    console.print(f"[bold]{ready}/{len(report.statuses)}[/] ferramentas prontas.")
    if report.broken():
        console.print(f"[red]Instaladas mas quebradas:[/] {', '.join(s.tool.label for s in report.broken())} — [bold]portai instalar[/] repara.")
    if report.installable():
        console.print(f"[dim]Para instalar o que falta: [bold]portai instalar[/] ({' '.join(report.installable())})[/]")
    if any(s.ok and s.tool.key == "codex" for s in report.statuses):
        console.print("[dim]Codex: confira o login com [bold]codex login status[/].[/]")
    console.print("[dim]A disponibilidade de ferramentas não garante que um projeto possa ser portado.[/]")
    return report


def check_environment() -> None:
    show_doctor()


def install_missing(profile: str = "completo", assume_yes: bool = False) -> int:
    report = portai_toolkit.collect()  # executa cada ferramenta: detecta as quebradas
    broken = portai_toolkit.broken_packages(report)
    if broken:
        commands = portai_toolkit.repair_commands(broken)
        console.print(f"[yellow]Ferramentas instaladas mas quebradas: {' '.join(broken)}[/]")
        for command in commands:
            console.print(f"Comando: [bold]{' '.join(command)}[/]")
        if commands and (assume_yes or ask_confirm("Reparar agora (atualizar Termux e reinstalar)?", default=True)):
            code = portai_toolkit.repair(broken)
            console.print("[bright_green]Reparo concluído.[/]" if code == 0 else f"[red]Reparo terminou com código {code}.[/]")
    packages = report.installable(profile)
    if not packages:
        if not broken:
            console.print("[bright_green]Nada para instalar: todas as ferramentas com pacote oficial já estão presentes.[/]")
        return 0
    command = portai_toolkit.install_command(packages)
    if not command:
        console.print(f"[yellow]Instalação automática só no Termux/apt. Instale manualmente: {' '.join(packages)}[/]")
        return 1
    console.print(f"Comando: [bold]{' '.join(command)}[/]")
    if not assume_yes and not ask_confirm("Instalar agora pelo repositório oficial do Termux?", default=True):
        return 1
    code = portai_toolkit.install(packages)
    console.print("[bright_green]Instalação concluída.[/]" if code == 0 else f"[red]O instalador terminou com código {code}.[/]")
    return code


def show_locations() -> None:
    """Mostra em um só lugar onde fica cada coisa do PortAI."""
    section("ONDE FICA CADA COISA")
    dirs = portai_toolkit.ensure_data_dirs()
    table = Table(box=box.ROUNDED, border_style="grey50", header_style="bold bright_red")
    table.add_column("O quê", style="white")
    table.add_column("Caminho", style="bright_red")
    table.add_column("Itens", justify="right")
    rows = [("Código do PortAI", ROOT), *dirs.items(),
            ("Configurações (idioma)", portai_i18n_config_path())]
    for label, path in rows:
        count = len(list(path.iterdir())) if path.is_dir() else ("existe" if path.exists() else "—")
        table.add_row(label, str(path), str(count))
    console.print(table)
    console.print("[dim]Dica: coloque projetos em [bold]~/PortAI/projetos[/] e eles aparecem automaticamente na busca. "
                  "Mude a pasta de dados com a variável PORTAI_HOME.[/]")


def portai_i18n_config_path() -> Path:
    import portai_i18n
    return portai_i18n.CONFIG_PATH


def update_portai() -> int:
    console.print("Atualizando o PortAI (git pull + dependências)...")
    code, output = portai_toolkit.update_repo()
    if output.strip():
        console.print(Panel(output.strip()[-4000:], border_style="grey50"))
    console.print("[bright_green]PortAI atualizado. Reabra para usar a nova versão.[/]" if code == 0 else f"[red]Falha na atualização (código {code}).[/]")
    return code


def export_doctor_json() -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / f"diagnostico-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(portai_toolkit.report_json(portai_toolkit.collect()) + "\n", encoding="utf-8")
    console.print(f"Diagnóstico salvo em [bold]{path}[/]")

def iter_project_files(root: Path):
    count = 0
    for current, dirs, names in os.walk(root, followlinks=False):
        cur = Path(current)
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not (cur / d).is_symlink()]
        for name in names:
            p = cur / name
            if p.is_symlink() or not p.is_file():
                continue
            if p.name in BUILD_NAMES or p.suffix.lower() in SOURCE_EXTS:
                yield p
                count += 1
                if count >= MAX_FILES:
                    return

def scan_roots() -> list[Path]:
    """Retorna apenas locais configurados, sem varrer a Home inteira."""
    home = Path.home()
    possible = [
        home / "simple-calculator",
        home / "storage" / "shared",
        home / "storage" / "downloads",
        home / "projetos",
        home / "Projects",
        home / "Downloads",
        home / "Documentos",
        home / "PORT",
        DATA_HOME / "projetos",
    ]
    # Não varre todos os diretórios de primeiro nível da Home: isso incluía
    # ambientes, caches e ferramentas como se fossem projetos do usuário.
    roots: list[Path] = []
    seen: set[str] = set()
    for root in possible:
        try:
            if root.is_dir():
                resolved = str(root.resolve())
                if resolved not in seen:
                    roots.append(root.resolve())
                    seen.add(resolved)
        except OSError:
            continue
    # Evita raízes duplicadas quando uma pasta está dentro de outra já selecionada.
    compact: list[Path] = []
    for root in roots:
        if not any(root == old or old in root.parents for old in compact):
            compact.append(root)
    return compact


def _desktop_evidence(root: Path, names: list[str]) -> dict[str, str] | None:
    """Classifica pela configuração localizada na raiz, nunca por código solto."""
    marker_names = [n for n in names if n in BUILD_NAMES or n.endswith((".sln", ".csproj", ".vcxproj", ".vbproj", ".pro"))]
    if not marker_names:
        return None
    texts: dict[str, str] = {}
    for name in marker_names:
        path = root / name
        try:
            if not path.is_symlink() and path.stat().st_size <= 250_000:
                texts[name] = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
    body = "\n".join(texts.values())
    low = body.lower()
    if "androidmanifest.xml" in names or re.search(r"com\.android\.(application|library)|android\s*\{", low):
        return None
    if re.search(r"<manifest[^>]+package=|apktool|smali_classes|classes\.dex", low):
        return None

    # Configuração de compilação declara o executável e seu alvo. Strings em .cpp/.h não contam.
    cmake_app = bool(re.search(r"\badd_executable\s*\(", low))
    dotnet_app = any(n.endswith((".csproj", ".vbproj")) for n in marker_names) and bool(re.search(r"<outputtype>winexe</outputtype>|<usewindowsforms>true|<usewpf>true", low))
    electron_app = "package.json" in texts and bool(re.search(r'"(electron|electron-builder|electron-forge)"\s*:', low)) and bool(re.search(r'"main"\s*:', low))
    python_ui = any(n in texts for n in ("pyproject.toml", "setup.py", "setup.cfg")) and bool(re.search(r"(pyqt|pyside|tkinter|wxpython)", low))
    desktop_dep = bool(re.search(r"find_package\s*\(\s*(qt[56]?|sfml|sdl2?|gtk)", low))
    configured_ui = bool(re.search(r"\b(tkinter|pyqt[56]|pyside[236]|wxpython|pygame)\b", low))
    if not (cmake_app or dotnet_app or electron_app or python_ui or (desktop_dep and cmake_app) or configured_ui):
        # Configuração válida, mas sem alvo desktop provado: manter visível para análise.
        technology = "CMake" if "CMakeLists.txt" in texts else ", ".join(Path(n).suffix or n for n in marker_names)
        kind = "Biblioteca/SDK" if re.search(r"\badd_library\s*\(", low) else "Projeto para análise"
        return {"platform": "Precisa de análise", "kind": kind, "technology": technology, "reason": "configuração de projeto encontrada, alvo desktop não confirmado", "source_count": str(sum(Path(n).suffix.lower() in SOURCE_EXTS for n in names))}

    technologies = []
    if re.search(r"find_package\s*\(\s*sfml", low): technologies.append("SFML")
    if re.search(r"find_package\s*\(\s*sdl", low): technologies.append("SDL")
    if re.search(r"find_package\s*\(\s*qt", low): technologies.append("Qt Widgets")
    if re.search(r"find_package\s*\(\s*boost", low): technologies.append("Boost")
    if dotnet_app: technologies.append(".NET desktop")
    if electron_app: technologies.append("Electron")
    if python_ui: technologies.append("Python desktop")
    is_windows = bool(re.search(r"\bwin32\b|\bwin64\b|\bwinexe\b|\busewpf\b|\busewindowsforms\b|\bwin32\s+executable\b|cl\.exe", low))
    if is_windows:
        platform = "Windows desktop"
        reason = "alvo Windows declarado na configuração" + (f"; dependências: {', '.join(technologies)}" if technologies else "")
    elif technologies:
        platform = "desktop multiplataforma"
        reason = "alvo executável e dependência de interface desktop declarados"
    else:
        platform = "Precisa de análise"
        reason = "configuração declara aplicação, mas não identifica com segurança as plataformas"
    project_name = ""
    project_match = re.search(r"\bproject\s*\(\s*([^\s)]+)", low)
    if project_match:
        project_name = project_match.group(1)
    if re.search(r"\b(game|engine|sdk|source[- ]port)\b", project_name):
        kind = "Jogo/motor/SDK/código-fonte de jogo"
    else:
        kind = "Aplicativo desktop independente"
    return {"platform": platform, "kind": kind, "technology": ", ".join(technologies or ["alvo desktop configurado"]), "reason": reason, "source_count": str(sum(Path(n).suffix.lower() in SOURCE_EXTS for n in names))}


def discover_projects(search_roots: list[Path] | None = None) -> tuple[list[dict[str, Any]], list[Path]]:
    """Busca projetos de desktop somente nas raízes configuradas."""
    candidates: dict[str, dict[str, Any]] = {}
    executables: dict[str, Path] = {}
    visited = 0
    configured = search_roots if search_roots is not None else scan_roots()
    # Uma pasta selecionada manualmente pode ser a própria raiz de projeto; quando for
    # diretório de busca, continua a exploração limitada em profundidade.
    for root in configured:
        root = root.expanduser().resolve()
        for current, dirs, names in os.walk(root, followlinks=False):
            current_path = Path(current)
            if any(current_path == own or own in current_path.parents for own in (ROOT, WORKSPACES)):
                dirs[:] = []
                continue
            try:
                depth = len(current_path.relative_to(root).parts)
            except ValueError:
                depth = 99
            dirs[:] = [d for d in dirs if d.lower() not in IGNORED_DIRS and not (current_path / d).is_symlink()]
            if depth >= 6:
                dirs[:] = []
            visited += 1
            if visited > MAX_SCAN_DIRS:
                break
            for name in names:
                file_path = current_path / name
                if file_path.is_symlink():
                    continue
                if name.lower().endswith(".exe"):
                    executables[str(file_path)] = file_path
            classification = _desktop_evidence(current_path, names)
            if classification:
                resolved = current_path.resolve()
                candidates[str(resolved)] = {"path": resolved, **classification}
            if len(candidates) >= MAX_CANDIDATES:
                break
        if visited > MAX_SCAN_DIRS or len(candidates) >= MAX_CANDIDATES:
            break
    projects = sorted(candidates.values(), key=lambda item: str(item["path"]).lower())
    return projects, sorted(executables.values(), key=lambda item: str(item).lower())[:100]


def select_project() -> Path | None:
    """Mostra projetos encontrados e devolve a escolha do usuário."""
    section("PROJETOS DESKTOP E PROJETOS PARA ANÁLISE")
    console.print("[dim]Procurando aplicativos desktop nas raízes configuradas...[/]")
    projects, executables = discover_projects()
    if not projects:
        console.print("[yellow]Nenhum projeto desktop com evidências suficientes foi encontrado.[/]")
        chosen = ask_prompt("Informe outra pasta de busca (Enter para voltar)", default="")
        if chosen:
            search = Path(chosen).expanduser()
            if search.is_dir():
                projects, executables = discover_projects([search.resolve()])
            else:
                console.print("[yellow]Pasta inválida.[/]")
        if not projects:
            ask_prompt("Pressione Enter para voltar ao menu", default="")
            return None
    else:
        table = Table(box=box.ROUNDED, border_style="bright_red", header_style="bold bright_red")
        table.add_column("Nº", justify="right", style="bright_red")
        table.add_column("Projeto", style="white")
        table.add_column("Caminho completo", style="dim")
        table.add_column("Plataforma", style="bright_red")
        table.add_column("Tipo", style="white")
        table.add_column("Tecnologia", style="white")
        table.add_column("Evidência", style="green")
        for i, item in enumerate(projects, 1):
            if item["platform"] == "Precisa de análise":
                continue
            path = Path(item["path"])
            table.add_row(str(i), path.name, str(path), item["platform"], item.get("kind", "Projeto para análise"), item["technology"], item["reason"])
        console.print(table)
        uncertain = [(i, item) for i, item in enumerate(projects, 1) if item["platform"] == "Precisa de análise"]
        if uncertain:
            details = "\n".join(f"#{i} {item['path']}\n  Razão: {item['reason']}" for i, item in uncertain)
            console.print(Panel(details, title="Precisa de análise", border_style="yellow"))
        for i, item in enumerate(projects, 1):
            console.print(f"[dim]Raiz completa #{i}: {item['path']}[/]")
    if executables:
        console.print(Panel(
            "\n".join(f"[yellow]•[/] {p}" for p in executables[:12])
            + (f"\n[dim]... e mais {len(executables)-12}[/]" if len(executables) > 12 else ""),
            title=f"Executáveis .EXE encontrados ({len(executables)})",
            border_style="yellow"
        ))
        console.print("[dim]Um .EXE sozinho não vira APK: normalmente precisamos do código-fonte e das dependências.[/]")
    console.print("[dim]Opções numeradas correspondem às linhas da lista.[/]")
    options = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    options.add_column("Opção", style="bright_red", justify="right")
    options.add_column("Projeto", style="white")
    for i, item in enumerate(projects, 1):
        path = Path(item["path"])
        try:
            display_path = "~/" + str(path.relative_to(Path.home()))
        except ValueError:
            display_path = str(path)
        options.add_row(str(i), f"{path.name}  [dim]{display_path}[/]")
    options.add_row("0", "Voltar ao menu")
    console.print(options)
    valid = [str(i) for i in range(len(projects) + 1)] + ["a"]
    console.print("[dim]Digite 'a' para buscar em outro diretório; isso não amplia a busca automática.[/]")
    choice = ask_prompt("Projeto", choices=valid, default="1" if projects else "0")
    if choice == "a":
        chosen = ask_prompt("Diretório adicional")
        search = Path(chosen).expanduser()
        if search.is_dir():
            extra, extra_executables = discover_projects([search.resolve()])
            existing = {str(item["path"]) for item in projects}
            projects.extend(item for item in extra if str(item["path"]) not in existing)
            executables = sorted({str(p): p for p in executables + extra_executables}.values(), key=lambda p: str(p).lower())[:100]
            if not projects:
                console.print("[yellow]Nenhuma configuração de projeto foi encontrada nesse diretório.[/]")
                return None
            return select_project_from_items(projects)
        console.print("[yellow]Pasta inválida.[/]")
        return None
    if choice == "0":
        return None
    return projects[int(choice) - 1]["path"]


def select_project_from_items(projects: list[dict[str, Any]]) -> Path | None:
    """Mostra lista resultante da busca manual e devolve a escolha correspondente."""
    table = Table(box=box.ROUNDED, header_style="bold bright_red")
    table.add_column("Nº", justify="right")
    table.add_column("Raiz identificada")
    table.add_column("Plataforma")
    table.add_column("Tipo")
    table.add_column("Razão")
    for index, item in enumerate(projects, 1):
        table.add_row(str(index), str(item["path"]), item["platform"], item.get("kind", "Projeto para análise"), item["reason"])
    console.print(table)
    choice = ask_prompt("Projeto", choices=[str(i) for i in range(len(projects) + 1)], default="1")
    return None if choice == "0" else projects[int(choice) - 1]["path"]


def analyze_project(path: Path) -> dict[str, Any]:
    root = path.expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Diretório não encontrado: {root}")
    files = list(iter_project_files(root))
    counts: dict[str, int] = {}
    build_files: list[str] = []
    hits: dict[str, list[str]] = {k: [] for k in PATTERNS}
    scanned_text = 0
    skipped_large = 0
    for p in files:
        rel = str(p.relative_to(root))
        if p.suffix:
            lang = LANGUAGES.get(p.suffix.lower(), p.suffix.lower())
            counts[lang] = counts.get(lang, 0) + 1
        if p.name in BUILD_NAMES:
            build_files.append(rel)
        if p.suffix.lower() not in SOURCE_EXTS:
            continue
        try:
            size = p.stat().st_size
            if size > MAX_TEXT_BYTES:
                skipped_large += 1
                continue
            content = p.read_text(encoding="utf-8", errors="replace")
            scanned_text += 1
        except OSError:
            continue
        for label, pattern in PATTERNS.items():
            if len(hits[label]) < 25 and re.search(pattern, content, re.IGNORECASE):
                hits[label].append(rel)
    findings = {k: v for k, v in hits.items() if v}
    extensions = {p.suffix.lower() for p in files}
    if not files:
        verdict = "Nenhum arquivo de código/build reconhecido"
    elif any(k in findings for k in ("Windows API / headers", "DirectX / Direct3D", ".NET UI Windows", "Registry do Windows")):
        verdict = "Possíveis dependências específicas do Windows: requer adaptação"
    elif extensions & {".c", ".cpp", ".cc", ".cxx", ".h", ".hpp"}:
        verdict = "Código nativo encontrado: verificar bibliotecas, compilador e sistema de build"
    elif ".py" in extensions:
        verdict = "Python encontrado: verificar dependências e APIs do sistema"
    else:
        verdict = "Compatibilidade indeterminada: revisar dependências e arquitetura"
    return {
        "tool": "OffTec PortAI", "version": VERSION,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "project": str(root), "verdict": verdict, "files_found": len(files),
        "text_files_read": scanned_text, "large_files_skipped": skipped_large,
        "languages": dict(sorted(counts.items())),
        "build_files": sorted(build_files), "windows_indicators": findings,
        "sample_files": [str(p.relative_to(root)) for p in files[:20]],
        "limitations": [
            "Análise estática heurística; não comprova compatibilidade.",
            "Não inspeciona profundamente binários EXE/DLL.",
            "Não gera APK automaticamente nesta versão.",
            "Dependências, licenças, APIs gráficas e arquitetura exigem validação.",
        ],
    }

def save_report(report: dict[str, Any]) -> tuple[Path, Path]:
    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = REPORTS / f"portai-{stamp}"
    json_path = base.with_suffix(".json")
    md_path = base.with_suffix(".md")
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# Relatório OffTec PortAI", "",
        f"- Versão: {report['version']}",
        f"- Projeto: `{report['project']}`",
        f"- Arquivos reconhecidos: {report['files_found']}",
        f"- Arquivos de texto lidos: {report['text_files_read']}",
        f"- Avaliação: **{report['verdict']}**", "", "## Linguagens",
    ]
    lines += [f"- {k}: {v}" for k, v in report["languages"].items()] or ["- Nenhuma reconhecida"]
    lines += ["", "## Arquivos de build"]
    lines += [f"- `{x}`" for x in report["build_files"]] or ["- Nenhum reconhecido"]
    lines += ["", "## Indicadores Windows"]
    for key, values in report["windows_indicators"].items():
        lines.append(f"- **{key}:** " + ", ".join(f"`{x}`" for x in values))
    if not report["windows_indicators"]:
        lines.append("- Nenhum indicador conhecido detectado")
    lines += ["", "## Limitações"] + [f"- {x}" for x in report["limitations"]]
    md_path.write_text(translate_text("\n".join(lines) + "\n"), encoding="utf-8")
    return md_path, json_path

def show_report(report: dict[str, Any], md: Path, js: Path) -> None:
    console.print(Panel(
        f"[bold white]{report['verdict']}[/]\n\n"
        f"[bright_red]Arquivos:[/] {report['files_found']}  "
        f"[bright_red]Textos lidos:[/] {report['text_files_read']}  "
        f"[bright_red]Indicadores Windows:[/] {len(report['windows_indicators'])}",
        title="RESULTADO DA ANÁLISE", border_style="bright_red", box=box.ROUNDED
    ))
    table = Table(title="Linguagens e arquivos", box=box.SIMPLE, header_style="bold bright_red")
    table.add_column("Linguagem")
    table.add_column("Quantidade", justify="right")
    for lang, count in report["languages"].items():
        table.add_row(lang, str(count))
    console.print(table)
    if report["windows_indicators"]:
        t = Table(title="Possíveis obstáculos à portabilidade", box=box.SIMPLE)
        t.add_column("Indicador", style="bright_red")
        t.add_column("Arquivos")
        for label, paths in report["windows_indicators"].items():
            t.add_row(label, ", ".join(paths[:5]))
        console.print(t)
    console.print(f"[dim]Markdown: {md}[/]\n[dim]JSON: {js}[/]")

def make_workspace(source: Path) -> Path:
    source = source.expanduser().resolve()
    if not source.is_dir():
        raise ValueError("O caminho informado não é um diretório.")
    if source == ROOT or ROOT in source.parents:
        raise ValueError("Escolha um projeto externo à pasta do próprio OffTec PortAI.")
    WORKSPACES.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = WORKSPACES / f"{source.name}-{stamp}"
    ignored = shutil.ignore_patterns(
        ".git", ".gradle", ".idea", ".venv", "venv", "node_modules",
        "__pycache__", "build", "dist", "target", "bin", "obj",
        ".next", "*.apk", "*.aab", "*.dex", "*.so", "*.class",
    )
    shutil.copytree(source, dest, ignore=ignored, symlinks=False)
    return dest


def workspace_state_path(workspace: Path) -> Path:
    return workspace / ".portai-state.json"


def load_workspace_state(workspace: Path) -> dict[str, Any]:
    path = workspace_state_path(workspace)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_workspace_state(workspace: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    workspace_state_path(workspace).write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def find_workspace(source: Path) -> Path | None:
    """Find the existing isolated copy associated with this exact source path."""
    if not WORKSPACES.is_dir():
        return None
    source_key = str(source.resolve())
    for candidate in sorted(WORKSPACES.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if candidate.is_dir() and not candidate.is_symlink():
            state = load_workspace_state(candidate)
            if state.get("source_path") == source_key:
                return candidate.resolve()
    return None


def codex_exec_command(codex: str, workspace: Path, prompt: str, sandbox: str = "workspace-write") -> list[str]:
    """Build argv for codex exec; keep the workspace path as one argument."""
    if sandbox not in {"read-only", "workspace-write"}:
        raise ValueError(f"Sandbox Codex inválido: {sandbox}")
    return [codex, "exec", "--cd", str(workspace), "--sandbox", sandbox, prompt]


def codex_resume_command(codex: str, workspace: Path, session_id: str | None = None, sandbox: str | None = None) -> list[str]:
    command = [codex, "exec", "resume"]
    if session_id:
        command.append(session_id)
    command += ["--cd", str(workspace)]
    if sandbox:
        if sandbox not in {"read-only", "workspace-write"}:
            raise ValueError(f"Sandbox Codex inválido: {sandbox}")
        command += ["--sandbox", sandbox]
    return command


def run_codex(codex: str, workspace: Path, prompt: str, timeout: int = 1800, resume_id: str | None = None, sandbox: str = "workspace-write"):
    """Run Codex with inherited credentials/network environment and split output."""
    workspace = workspace.resolve(strict=True)
    if not workspace.is_dir() or WORKSPACES.resolve() not in workspace.parents:
        raise ValueError(f"Diretório de trabalho inválido ou fora de workspaces/: {workspace}")
    command = codex_resume_command(codex, workspace, resume_id, sandbox) if resume_id is not None else codex_exec_command(codex, workspace, prompt, sandbox)
    return subprocess.run(
        command, cwd=str(workspace), text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=timeout, check=False,
    )


ANDROID_REBUILD_PROMPT = """Reconstruct this project for Android in the current isolated workspace. First inspect its architecture, UI framework, dependencies, build configuration and platform-specific APIs. Reuse portable business logic where possible; adapt or rewrite the UI and replace incompatible libraries when needed. Create the Android project/configuration required by the most suitable strategy available here (native Android/Gradle, NDK/CMake, or an appropriate existing framework). Check available Java, Gradle, Android SDK, NDK and CMake tools before choosing. Install dependencies only when necessary and report permission, network and compatibility failures. Run relevant tests, attempt to build an installable APK, inspect and fix viable build errors, and keep trying while a practical correction remains. Never claim success without an APK file produced by a successful build. Record approach, blockers, commands, test/build results and changed files in ANDROID_PORT_PROGRESS.md. Do not access secrets or modify files outside this workspace."""


def run_build(workspace: Path) -> tuple[int, str, str, Path | None]:
    """Run a locally available Android build and return only a verified APK."""
    env = os.environ.copy()
    sdk = env.get("ANDROID_HOME") or env.get("ANDROID_SDK_ROOT")
    if not sdk and (Path.home() / "android-sdk").is_dir():
        sdk = str(Path.home() / "android-sdk")
        env["ANDROID_HOME"] = sdk
    gradlew = workspace / "gradlew"
    gradle = shutil.which("gradle")
    if gradlew.is_file():
        try:
            gradlew.chmod(gradlew.stat().st_mode | 0o111)
        except OSError:
            pass
        command = [str(gradlew), "assembleDebug"]
    elif gradle:
        command = [gradle, "assembleDebug"]
    elif (workspace / "CMakeLists.txt").is_file() and shutil.which("cmake"):
        if not sdk:
            return 127, "", "Android SDK não encontrado (ANDROID_HOME/ANDROID_SDK_ROOT).", None
        ndk = env.get("ANDROID_NDK_HOME") or env.get("ANDROID_NDK_ROOT")
        if not ndk:
            ndks = Path(sdk) / "ndk"
            versions = sorted(ndks.iterdir()) if ndks.is_dir() else []
            ndk = str(versions[-1]) if versions else ""
        if not ndk:
            return 127, "", "Android NDK não encontrado para o projeto CMake.", None
        command = [shutil.which("cmake"), "-S", str(workspace), "-B", str(workspace / "build-android"), "-DANDROID_ABI=arm64-v8a", "-DANDROID_PLATFORM=android-24", f"-DANDROID_NDK={ndk}"]
    else:
        return 127, "", "Não encontrei gradlew, Gradle ou uma configuração Android CMake compilável.", None
    tools = {name: shutil.which(name) for name in ("java", "gradle", "cmake", "ninja", "aapt", "apksigner")}
    console.print(Panel("\n".join(f"{name}: {path or 'não encontrado'}" for name, path in tools.items()) + f"\nAndroid SDK: {sdk or 'não encontrado'}", title="FERRAMENTAS DE BUILD", border_style="red"))
    # Termux's AAPT2 needs its matching libc++_shared.so. Put that directory
    # first for this Gradle process only; global LD_LIBRARY_PATH may point at
    # unrelated bundled tools (for example Node-based CLI packages).
    termux_prefix = env.get("PREFIX")
    aapt2 = shutil.which("aapt2")
    if command and Path(command[0]).name in {"gradle", "gradlew"} and termux_prefix and aapt2:
        prefix_path = Path(termux_prefix).expanduser().resolve()
        runtime_lib = prefix_path / "lib"
        try:
            local_aapt2 = Path(aapt2).resolve().is_relative_to(prefix_path)
        except OSError:
            local_aapt2 = False
        if local_aapt2 and (runtime_lib / "libc++_shared.so").is_file():
            inherited = env.get("LD_LIBRARY_PATH", "").split(os.pathsep)
            env["LD_LIBRARY_PATH"] = os.pathsep.join(
                [str(runtime_lib), *(part for part in inherited if part and Path(part).resolve() != runtime_lib)]
            )
    try:
        proc = subprocess.run(command, cwd=workspace, env=env, text=True, capture_output=True, timeout=3600, check=False)
        apk = find_apk(workspace) if proc.returncode == 0 else None
        if proc.returncode == 0 and apk is None:
            return proc.returncode, proc.stdout, proc.stderr + "\nBuild terminou sem APK não vazio encontrado.", None
        if apk and not validate_apk(apk):
            return proc.returncode, proc.stdout, proc.stderr + f"\nAPK inválido ou ZIP corrompido: {apk}", None
        return proc.returncode, proc.stdout, proc.stderr, apk
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, "", str(exc), None


def find_apk(workspace: Path) -> Path | None:
    candidates = [p for p in workspace.rglob("*.apk") if p.is_file() and p.stat().st_size > 0 and "build" in p.parts]
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def validate_apk(apk: Path) -> bool:
    try:
        if not apk.is_file() or apk.stat().st_size <= 0:
            return False
        with zipfile.ZipFile(apk) as package:
            if package.testzip() is not None:
                return False
            names = set(package.namelist())
            return "AndroidManifest.xml" in names
    except (OSError, zipfile.BadZipFile):
        return False


def show_workspace_progress(workspace: Path, state: dict[str, Any]) -> None:
    changed = subprocess.run(["git", "status", "--short"], cwd=workspace, capture_output=True, text=True) if shutil.which("git") else None
    console.print(Panel(f"Estado: {state.get('status', 'aguardando instruções')}\nOrigem: {state.get('source_path', '?')}\nWorkspace: {workspace}\nSessão Codex: {state.get('session_id') or 'indisponível'}\nÚltimo erro: {state.get('last_error') or 'nenhum'}", title="PROGRESSO", border_style="bright_red"))
    if changed:
        console.print(Panel(changed.stdout.strip() or "Git não disponível nesta cópia.", title="ARQUIVOS MODIFICADOS", border_style="red"))
    progress = workspace / "ANDROID_PORT_PROGRESS.md"
    if progress.is_file():
        console.print(Panel(progress.read_text(encoding="utf-8", errors="replace")[-10000:], title="RELATÓRIO DE PROGRESSO", border_style="red"))


def codex_task(codex: str, workspace: Path, state: dict[str, Any], prompt: str, resume: bool = False, sandbox: str = "workspace-write") -> None:
    state["status"] = "reconstruindo" if "Reconstruct" in prompt else "analisando" if "analy" in prompt.lower() else "trabalhando com Codex"
    save_workspace_state(workspace, state)
    try:
        proc = run_codex(codex, workspace, prompt, resume_id=state.get("session_id") if resume else None, sandbox=sandbox)
        # Codex JSONL output may include a thread.started event even if the CLI
        # version does not expose a separate session flag.
        for line in proc.stdout.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict):
                thread = event.get("thread_id") or event.get("session_id")
                if not thread and isinstance(event.get("thread"), dict):
                    thread = event["thread"].get("id")
                if thread:
                    state["session_id"] = str(thread)
        if prompt:
            state["history"].append({"at": datetime.now().isoformat(timespec="seconds"), "prompt": prompt[:600], "return_code": proc.returncode})
        console.print(Panel(proc.stdout[-16000:] or "(sem stdout)", title="SAÍDA DO CODEX", border_style="bright_red"))
        if proc.stderr:
            console.print(Panel(proc.stderr[-8000:], title="ERROS/AVISOS DO CODEX", border_style="yellow"))
        state["last_return_code"] = proc.returncode
        state["last_output"] = proc.stdout[-4000:]
        if proc.returncode:
            state["last_error"] = proc.stderr[-2000:] or f"Codex terminou com código {proc.returncode}"
            state["status"] = "erro"
        else:
            state["last_error"] = None
            state["status"] = "aguardando instruções"
    except subprocess.TimeoutExpired as exc:
        state["status"] = "interrompido"; state["last_error"] = f"Tempo limite: {exc}"
        console.print(f"[red]Codex excedeu o limite. Estado preservado: {exc}[/]")
    except KeyboardInterrupt:
        state["status"] = "interrompido"; state["last_error"] = "Execução interrompida por Ctrl+C"
        console.print("[yellow]Execução interrompida; workspace e estado foram preservados.[/]")
    except OSError as exc:
        state["status"] = "erro"; state["last_error"] = str(exc)
        console.print(f"[red]Falha ao executar Codex: {exc}[/]")
    finally:
        save_workspace_state(workspace, state)


def reconstruction_menu(source: Path | None = None, workspace: Path | None = None) -> None:
    codex = shutil.which("codex")
    if workspace is None:
        if source is None:
            source = select_project()
            if source is None:
                return
        source = source.resolve(strict=True)
        if source == ROOT or ROOT in source.parents:
            console.print("[red]Escolha um projeto fora da pasta do PortAI.[/]"); return
        workspace = find_workspace(source)
        if workspace is None:
            if not ask_confirm("Criar uma cópia de trabalho isolada em workspaces/?", default=False):
                return
            workspace = make_workspace(source)
            save_workspace_state(workspace, {"source_path": str(source), "workspace": str(workspace), "status": "aguardando análise", "session_id": None, "analysis_done": False, "history": []})
    state = load_workspace_state(workspace)
    if not state:
        console.print("[red]Estado da workspace não encontrado; não será associada automaticamente a outro projeto.[/]"); return
    state.setdefault("history", [])
    if codex and not state.get("analysis_done"):
        console.print(f"[red]Analisando a cópia existente: {workspace}[/]")
        codex_task(codex, workspace, state, "Analyze this project for Android portability. Inspect architecture, UI, dependencies, build configuration and platform blockers. Reuse original logic where practical. Write PORTABILITY_REPORT.md with evidence, feasible Android strategy, required adaptations, available tools, risks and concrete next steps. Do not modify outside this workspace.")
        state["analysis_done"] = state.get("last_return_code") == 0
        state["status"] = "aguardando instruções" if state["analysis_done"] else state.get("status", "erro")
        save_workspace_state(workspace, state)
    while True:
        section("RECONSTRUÇÃO ANDROID — SESSÃO PERSISTENTE")
        console.print(f"Projeto: [red]{state.get('source_path')}[/]\nEstado: [yellow]{state.get('status')}[/]  •  Sessão: {state.get('session_id') or 'não disponível'}")
        for n, label in [("1", "Analisar projeto"), ("2", "Reconstruir para Android"), ("3", "Continuar conversa com Codex"), ("4", "Compilar APK"), ("5", "Verificar dependências e corrigir erros"), ("6", "Mostrar arquivos modificados e progresso"), ("7", "Abrir ou instalar APK"), ("8", "Retomar sessão anterior"), ("9", "Voltar ao menu principal")]:
            console.print(f"{n}. {label}")
        choice = ask_prompt("Reconstrução", choices=[str(i) for i in range(1, 10)], default="9")
        if choice == "9": return
        if choice in {"1", "2", "5", "8"}:
            if not codex:
                console.print("[red]Codex CLI não está no PATH.[/]"); continue
            if choice == "1":
                codex_task(codex, workspace, state, "Analyze this project for Android portability. Inspect architecture, dependencies and platform blockers, and update PORTABILITY_REPORT.md with a concrete Android plan.")
                state["analysis_done"] = state.get("last_return_code") == 0
            elif choice == "2": codex_task(codex, workspace, state, ANDROID_REBUILD_PROMPT)
            elif choice == "5": codex_task(codex, workspace, state, "Inspect installed Java/Gradle/Android SDK/NDK/CMake and this project's build. Diagnose the latest compilation error; make viable corrections, run tests and attempt an APK build. Record evidence and remaining blockers in ANDROID_PORT_PROGRESS.md.")
            else:
                if not state.get("session_id"):
                    console.print("[yellow]Não há ID salvo para retomar; use continuar conversa para iniciar uma nova sessão no workspace preservado.[/]"); continue
                codex_task(codex, workspace, state, "", resume=True)
        elif choice == "3":
            if not codex: console.print("[red]Codex CLI não está no PATH.[/]"); continue
            console.print("[red]Iniciando Codex interativo no workspace; saia do Codex para retornar aqui.[/]")
            state["status"] = "conversa interativa"; save_workspace_state(workspace, state)
            try:
                interactive = subprocess.run([codex, "--cd", str(workspace)], cwd=workspace, check=False)
                state["last_return_code"] = interactive.returncode
                state["status"] = "aguardando instruções" if interactive.returncode == 0 else "erro"
                state["last_error"] = None if interactive.returncode == 0 else f"Codex interativo terminou com código {interactive.returncode}"
            except (OSError, KeyboardInterrupt) as exc:
                console.print(f"[yellow]Conversa encerrada: {exc}[/]")
                state["status"] = "interrompido"; state["last_error"] = str(exc)
            save_workspace_state(workspace, state)
        elif choice == "4":
            state["status"] = "compilando"; save_workspace_state(workspace, state)
            code, out, err, apk = run_build(workspace)
            if out: console.print(Panel(out[-12000:], title="BUILD STDOUT", border_style="red"))
            if err: console.print(Panel(err[-12000:], title="BUILD STDERR", border_style="yellow"))
            state["status"] = "APK gerado" if code == 0 and apk else "erro"
            state["last_error"] = None if apk else (err[-2000:] or "Build falhou ou nenhum APK verificável foi encontrado.")
            state["apk_path"] = str(apk) if apk else None; save_workspace_state(workspace, state)
            console.print(f"[green]APK validado: {apk} ({apk.stat().st_size} bytes)[/]" if apk else f"[red]Sem APK validado (código {code}).[/]")
        elif choice == "6": show_workspace_progress(workspace, state)
        elif choice == "7":
            apk = find_apk(workspace)
            if not apk: console.print("[yellow]Nenhum APK não vazio encontrado.[/]"); continue
            console.print(f"APK: {apk} ({apk.stat().st_size} bytes)")
            opener = shutil.which("termux-open") or shutil.which("am")
            if opener and ask_confirm("Tentar abrir/instalar este APK?", default=False):
                args = [opener, "--view", str(apk)] if Path(opener).name == "termux-open" else [opener, "start", "-a", "android.intent.action.VIEW", "-d", f"file://{apk}", "-t", "application/vnd.android.package-archive"]
                subprocess.run(args, check=False)
        save_workspace_state(workspace, state)

def codex_port_assist() -> None:
    reconstruction_menu()

def run_analysis() -> None:
    source = select_project()
    if source is None:
        return
    try:
        report = analyze_project(source)
        md, js = save_report(report)
        show_report(report, md, js)
    except (OSError, ValueError) as exc:
        console.print(f"[red]Falha na análise: {exc}[/]")

def _review_translation_proposals(result, engine, targets: list[str]) -> bool:
    from portai_translation import LANGUAGES

    proposals = [(entry, locale) for entry in result.entries for locale in targets if locale in entry.translations]
    decisions = {}
    if not proposals:
        return False
    console.print(f"[red]{len(proposals)} propostas para revisão. Nenhuma será aplicada sem aprovação.[/]")
    for entry, locale in proposals:
        console.print(Panel(
            f"[bold]Idioma:[/] {locale} ({LANGUAGES[locale]['name']})\n"
            f"[bold]Arquivo/chave:[/] {entry.path} :: {entry.key}\n"
            f"[bold]Original:[/] {entry.source}\n[bold]Proposta:[/] {entry.translations[locale]}",
            border_style="red" if locale != "ar" else "bright_red",
            title="Revisão de tradução" + (" • RTL" if locale == "ar" else ""),
        ))
        decisions[(entry.entry_id, locale)] = ask_confirm("Aprovar esta tradução?", default=False)
    engine.approve(result, decisions, targets)
    return True


def translation_menu() -> None:
    from portai_translation import LANGUAGES, TranslationEngine
    from portai_translation.providers import configured_provider

    chosen = ask_prompt("Pasta do projeto para traduzir")
    project = Path(chosen).expanduser()
    if not project.is_dir():
        console.print("[red]Pasta inválida.[/]")
        return
    source_language = ask_prompt("Idioma original", choices=["pt-BR", "en", "es", "ar", "hi"], default="en")
    raw_targets = ask_prompt("Idiomas de destino separados por vírgula", default="pt-BR,es,ar,hi")
    targets = list(dict.fromkeys(item.strip() for item in raw_targets.split(",") if item.strip()))
    invalid = [item for item in targets if item not in LANGUAGES]
    if not targets or invalid:
        console.print(f"[red]Seleção de idiomas inválida: {', '.join(invalid) or 'vazia'}[/]")
        return
    try:
        provider = configured_provider()
        engine = TranslationEngine(provider)
        result = engine.scan(project, source_language)
        console.print(f"Arquivos localizáveis: {len(result.discovered_files)} • strings: {len(result.entries)} • provedor: {provider.name}")
        if result.scan_errors:
            console.print(f"[yellow]Arquivos com erro de leitura/formato: {len(result.scan_errors)} (listados no relatório)[/]")
        if not result.entries:
            console.print("[yellow]Nenhuma string traduzível foi encontrada nos formatos suportados.[/]")
            return
        engine.translate(result, targets)
        if not _review_translation_proposals(result, engine, targets):
            console.print("[yellow]O provedor não produziu traduções. As strings ficam registradas como não traduzidas; configure um provedor e tente novamente.[/]")
        output_default = DATA_HOME / "saidas" / f"{project.name}-locales"
        output_raw = ask_prompt("Pasta de saída (originais permanecem intactos)", default=str(output_default))
        report = engine.apply(result, project, Path(output_raw), targets)
        _record_translation_report(report)
        metadata = {
            locale: {
                "direction": LANGUAGES[locale]["direction"],
                "android_resource_folder": f"values-{LANGUAGES[locale]['android']}" if LANGUAGES[locale]["android"] else "values",
                "unicode": True,
                "notes": (["Configurar android:supportsRtl=\"true\" e revisar layouts para RTL."] if locale == "ar" else (["Validar fallback de fontes com glifos Devanagari no dispositivo."] if locale == "hi" else [])),
            }
            for locale in targets
        }
        metadata_path = Path(output_raw).expanduser().resolve() / "localization-metadata.json"
        if metadata_path.is_symlink():
            raise ValueError("O arquivo de metadados de saída não pode ser um link simbólico.")
        if metadata_path.exists():
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            backup = metadata_path.parent / "backups" / stamp / metadata_path.name
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(metadata_path, backup)
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        missing = sum(1 for entry in result.entries for locale in targets if entry.target_status.get(locale, entry.status) != "approved")
        console.print(f"[green]Relatório: {report}[/]\nSaída: {output_raw}\nStrings sem aprovação: {missing}")
    except (OSError, ValueError, RuntimeError, ImportError, TypeError, subprocess.TimeoutExpired) as exc:
        console.print(f"[red]Falha no Universal Translation Engine: {exc}[/]")


def apk_translation_menu() -> None:
    from getpass import getpass
    from portai_apk_translator import APK_TARGETS, ApkTranslator
    from portai_translation import TranslationEngine
    from portai_translation.providers import configured_provider

    apk = Path(ask_prompt("Caminho do APK original").strip()).expanduser()
    if not apk.is_file():
        console.print("[red]Arquivo APK não encontrado.[/]")
        return
    target = ask_prompt("Idioma de destino", choices=list(APK_TARGETS), default="es")
    missing = [name for name in ("apktool", "apksigner", "java") if not shutil.which(name)]
    if missing:
        console.print(f"[red]Dependências obrigatórias ausentes: {', '.join(missing)}. Instale-as no Termux e tente novamente.[/]")
        return
    keystore = Path(ask_prompt("Caminho da sua keystore de assinatura").strip()).expanduser()
    if not keystore.is_file():
        console.print("[red]Keystore não encontrada. O PortAI não extrai nem cria chaves de terceiros.[/]")
        return
    alias = ask_prompt("Alias da chave")
    keystore_password = getpass("Senha da keystore: ")
    key_password = getpass("Senha da chave: ")
    source_language = ask_prompt("Idioma original das strings", choices=["en", "es", "ar", "hi"], default="en")
    try:
        provider = configured_provider()
        engine = TranslationEngine(provider)
        translator = ApkTranslator(engine)
        report = translator.run(
            apk=apk,
            workspace_root=WORKSPACES,
            targets=[target],
            reviewer=_review_translation_proposals,
            keystore=keystore,
            key_alias=alias,
            keystore_password=keystore_password,
            key_password=key_password,
            source_language=source_language,
        )
        console.print(f"Workspace: {report['workspace']}\nPacote: {report.get('package') or 'indisponível'}\n"
                      f"Versão: {report.get('version_name') or 'indisponível'} ({report.get('version_code') or '?'})\n"
                      f"Arquiteturas: {', '.join(report.get('architectures', [])) or 'nenhuma detectada'}")
        for warning in report.get("warnings", []):
            console.print(f"[yellow]Aviso: {warning}[/]")
        if report["status"] == "success" and report["validated"]:
            console.print(f"[green]APK assinado e validado: {report['output_apk']}[/]")
        else:
            console.print(f"[red]Processamento não concluído: {'; '.join(report['errors'])}[/]")
        console.print(f"Relatório: {report['report_path']}")
    except (OSError, ValueError, RuntimeError, ImportError, TypeError) as exc:
        console.print(f"[red]Falha ao iniciar o tradutor de APK: {exc}[/]")
    finally:
        # Do not retain signing secrets beyond this operation.
        keystore_password = ""
        key_password = ""


def _game_progress(workspace: Path, state: dict[str, Any], analysis: dict[str, Any], report_paths: tuple[Path, Path]) -> Path:
    progress = {
        "project": state.get("source_path"),
        "workspace": str(workspace),
        "session_id": state.get("session_id"),
        "status": state.get("status"),
        "recent_history": state.get("history", [])[-10:],
        "last_return_code": state.get("last_return_code"),
        "last_error": state.get("last_error"),
        "authorized_files": state.get("authorized_game_files", []),
        "last_modified_files": state.get("game_last_modified_files", []),
        "out_of_scope_changes": state.get("game_out_of_scope_changes", []),
        "backup_manifests": state.get("game_backup_manifests", []),
        "compatibility_report_markdown": str(report_paths[0]),
        "compatibility_report_json": str(report_paths[1]),
        "external_build_host": analysis.get("external_build_host"),
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    path = workspace / "GAME_PORTABILITY_PROGRESS.json"
    path.write_text(json.dumps(progress, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _latest_game_backup(workspace: Path) -> Path | None:
    backup_root = WORKSPACES / ".portai-game-backups" / workspace.name
    if not backup_root.is_dir():
        return None
    manifests = sorted(backup_root.glob("*/manifest.json"), reverse=True)
    return manifests[0] if manifests else None


def _is_android_gradle_app(workspace: Path) -> bool:
    manifests = list(workspace.rglob("AndroidManifest.xml"))
    gradle_files = [p for p in workspace.rglob("build.gradle*") if p.is_file() and not p.is_symlink()]
    if not manifests or not gradle_files:
        return False
    for path in gradle_files:
        try:
            if re.search(r"com\.android\.application|com\.android\.tools\.build:gradle", path.read_text(encoding="utf-8", errors="replace")):
                return True
        except OSError:
            continue
    return False


def _game_authorized_diff(workspace: Path, manifest_path: Path, authorized: list[str]) -> tuple[str, list[str]]:
    """Build a review patch from the pre-edit backup and current authorized files."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = {item["path"]: item for item in manifest.get("entries", [])}
    chunks: list[str] = []
    changed: list[str] = []
    for relative in authorized:
        entry = entries.get(relative)
        if not entry:
            continue
        target = (workspace / relative).resolve(strict=False)
        base = workspace.resolve(strict=True)
        current = base
        has_link = False
        for part in Path(relative).parts:
            current /= part
            has_link = has_link or current.is_symlink()
        if base not in target.parents or has_link:
            continue
        before_path = (manifest_path.parent / entry["backup"]).resolve(strict=True) if entry.get("backup") else None
        if before_path and manifest_path.parent.resolve(strict=True) not in before_path.parents:
            continue
        try:
            before = before_path.read_bytes() if before_path else b""
            after = target.read_bytes() if target.is_file() else b""
        except OSError:
            continue
        if before == after:
            continue
        changed.append(relative)
        if max(len(before), len(after)) > 1_000_000 or b"\0" in before or b"\0" in after:
            chunks.append(f"Binary or large file changed: {relative}\n")
            continue
        old_text = before.decode("utf-8", errors="replace").splitlines(keepends=True)
        new_text = after.decode("utf-8", errors="replace").splitlines(keepends=True)
        chunks.extend(difflib.unified_diff(old_text, new_text, fromfile=f"before/{relative}", tofile=f"after/{relative}"))
    return "".join(chunks), changed


def _godot_android_preset(workspace: Path) -> str | None:
    preset_file = workspace / "export_presets.cfg"
    if not preset_file.is_file() or preset_file.is_symlink():
        return None
    try:
        content = preset_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for section_text in re.split(r"(?=\[preset\.\d+\])", content):
        if re.search(r'^platform\s*=\s*"Android"\s*$', section_text, re.M):
            match = re.search(r'^name\s*=\s*"([^"]+)"\s*$', section_text, re.M)
            if match:
                return match.group(1)
    return None


def _run_game_export(workspace: Path, engine: str) -> tuple[int, str, str, Path | None, str]:
    """Use an actual engine exporter when supported, otherwise the Android project build."""
    if engine == "Godot":
        executable = shutil.which("godot") or shutil.which("godot4")
        preset = _godot_android_preset(workspace)
        if not executable or not preset:
            return 127, "", "Godot CLI ou preset Android export_presets.cfg não encontrado.", None, "Godot Android export"
        output = workspace / "build" / "portai-game.apk"
        output.parent.mkdir(parents=True, exist_ok=True)
        command = [executable, "--headless", "--path", str(workspace), "--export-debug", preset, str(output)]
        try:
            proc = subprocess.run(command, cwd=workspace, text=True, capture_output=True, timeout=3600, check=False)
            apk = output if proc.returncode == 0 and output.is_file() and validate_apk(output) else None
            return proc.returncode if apk else (proc.returncode or 1), proc.stdout, proc.stderr, apk, "Godot Android export"
        except (OSError, subprocess.TimeoutExpired) as exc:
            return 1, "", str(exc), None, "Godot Android export"
    return (*run_build(workspace), "Gradle/CMake Android build")


def _test_game_apk(apk: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    with apk.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    info: dict[str, Any] = {
        "apk": str(apk), "size_bytes": apk.stat().st_size,
        "sha256": digest.hexdigest(),
        "zip_manifest_valid": validate_apk(apk), "signature": "não verificada",
    }
    signer = shutil.which("apksigner")
    if signer:
        try:
            result = subprocess.run([signer, "verify", "--verbose", str(apk)], capture_output=True, text=True, timeout=60, check=False)
            info["signature"] = "válida" if result.returncode == 0 else "inválida ou ausente"
            info["signature_output"] = (result.stdout + result.stderr)[-3000:]
        except (OSError, subprocess.TimeoutExpired) as exc:
            info["signature"] = f"verificação falhou: {exc}"
    package_id = None
    aapt = shutil.which("aapt")
    if aapt:
        try:
            result = subprocess.run([aapt, "dump", "badging", str(apk)], capture_output=True, text=True, timeout=60, check=False)
            match = re.search(r"^package: name='([^']+)'", result.stdout, re.M)
            package_id = match.group(1) if match else None
        except (OSError, subprocess.TimeoutExpired):
            pass
    if not package_id and shutil.which("apkanalyzer"):
        try:
            result = subprocess.run([shutil.which("apkanalyzer"), "manifest", "application-id", str(apk)], capture_output=True, text=True, timeout=60, check=False)
            package_id = result.stdout.strip() if result.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            pass
    info["package_id"] = package_id
    info["device_test"] = "não executado"
    adb = shutil.which("adb")
    devices: list[str] = []
    if adb:
        try:
            result = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=15, check=False)
            devices = [line.split()[0] for line in result.stdout.splitlines()[1:] if len(line.split()) >= 2 and line.split()[1] == "device"]
        except (OSError, subprocess.TimeoutExpired):
            pass
    info["connected_devices"] = devices
    info["adb_available"] = bool(adb)
    return info


def game_recreation_menu(initial_choice: str | None = None) -> None:
    from game_portability import (
        analyze_game_project, backup_authorized_files, restore_authorized_backup,
        save_game_report, workspace_inventory,
    )

    selected = Path(ask_prompt("Pasta raiz do projeto de jogo").strip()).expanduser()
    if not selected.is_dir():
        console.print("[red]Pasta inválida.[/]")
        return
    source = selected.resolve()
    if source == ROOT or ROOT in source.parents:
        console.print("[red]Escolha um projeto fora da pasta da PortAI.[/]")
        return
    try:
        analysis = analyze_game_project(source)
        report_paths = save_game_report(analysis, REPORTS)
    except (OSError, ValueError) as exc:
        console.print(f"[red]Falha na análise de jogo: {exc}[/]")
        return
    console.print(Panel(
        f"Engine: [red]{analysis['engine']}[/] • versão: [red]{analysis.get('engine_version', 'não detectada')}[/]\nArquivos: {analysis['files_found']} • scripts/código: {analysis['source_files']}\n"
        f"Dependências identificadas: {len(analysis['dependencies'])}\nIncompatibilidades: {len(analysis['incompatibilities'])}\n"
        f"Build Android já configurado: {'sim, verificar antes de compilar' if analysis['build_ready'] else 'não detectado'}\n"
        f"Host indicado: {analysis['external_build_host']}\n"
        f"Marcador de configuração Android: {'detectado' if analysis['android_config_detected'] else 'não detectado'}",
        title="ANÁLISE DE PORTABILIDADE DE JOGO", border_style="bright_red",
    ))
    for item in analysis.get("portability_checks", []):
        evidence = ", ".join(item.get("evidence", [])) or "nenhum arquivo correspondente"
        console.print(f"[bold]{item['status']}[/] • {item['check']}: [dim]{evidence}[/]")
    if analysis.get("largest_assets"):
        console.print("Assets maiores: " + " • ".join(
            f"{item['path']} ({item['size_bytes'] / (1024 * 1024):.1f} MiB)"
            for item in analysis["largest_assets"][:5]
        ))
    console.print(f"Relatórios: {report_paths[0]} • {report_paths[1]}")

    workspace = find_workspace(source)
    if workspace is None:
        if not ask_confirm("Criar uma cópia isolada em workspaces/ para a sessão Codex?", default=False):
            return
        try:
            workspace = make_workspace(source)
            save_workspace_state(workspace, {
                "source_path": str(source), "workspace": str(workspace),
                "status": "plano de portabilidade criado", "session_id": None,
                "analysis_done": False, "history": [],
            })
        except (OSError, ValueError) as exc:
            console.print(f"[red]Falha ao criar workspace: {exc}[/]")
            return
    state = load_workspace_state(workspace)
    if not state:
        console.print("[red]Estado persistente da workspace inválido; nenhuma sessão será iniciada.[/]")
        return
    state.setdefault("history", [])
    (workspace / "PORTAI_GAME_PORTABILITY_PLAN.json").write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _game_progress(workspace, state, analysis, report_paths)
    codex = shutil.which("codex")

    while True:
        section("AI GAME RECREATION ENGINE — WORKSPACE PERSISTENTE")
        console.print(Panel(
            f"[bold white]{source.name}[/]\n[dim]Projeto[/]  {source}\n"
            f"[dim]Workspace[/]  {workspace}\n"
            f"[dim]Sessão Codex[/]  {state.get('session_id') or 'ainda não iniciada'}",
            title="WORKSPACE DE PORTABILIDADE",
            border_style="bright_red",
            box=box.ROUNDED,
        ))
        game_actions = tuple((number, label, None) for number, label in [
            ("1", "Atualizar análise e plano"),
            ("2", "Pedir revisão de plano ao Codex (somente leitura)"),
            ("3", "Autorizar arquivos e solicitar adaptação ao Codex"),
            ("4", "Continuar sessão Codex persistente"),
            ("5", "Mostrar progresso e arquivos alterados"),
            ("6", "Recuperar backup dos arquivos autorizados"),
            ("7", "Exportar/compilar e validar APK Android"),
        ])
        _render_menu_cards(game_actions, {
            "Atualizar análise e plano": "Atualize engines, dependências, riscos e relatórios.",
            "Pedir revisão de plano ao Codex (somente leitura)": "Obtenha um plano priorizado sem alterar arquivos.",
            "Autorizar arquivos e solicitar adaptação ao Codex": "Escolha os arquivos exatos antes de solicitar mudanças.",
            "Continuar sessão Codex persistente": "Retome o trabalho salvo neste workspace isolado.",
            "Mostrar progresso e arquivos alterados": "Revise o estado atual e o diff do projeto.",
            "Recuperar backup dos arquivos autorizados": "Restaure os arquivos cobertos pelo backup de segurança.",
            "Exportar/compilar e validar APK Android": "Use a toolchain disponível e valide o APK gerado.",
        })
        console.print("[bold bright_red]0.[/] Voltar ao menu principal")
        choice = ask_prompt("Game Recreation", choices=["1", "2", "3", "4", "5", "6", "7", "0"], default=initial_choice or "0")
        initial_choice = None
        if choice == "0":
            return
        if choice == "1":
            try:
                analysis = analyze_game_project(source)
                report_paths = save_game_report(analysis, REPORTS)
                (workspace / "PORTAI_GAME_PORTABILITY_PLAN.json").write_text(json.dumps(analysis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                _game_progress(workspace, state, analysis, report_paths)
                console.print(f"[green]Análise atualizada: {report_paths[0]}[/]")
                for item in analysis.get("portability_checks", []):
                    console.print(f"[bold]{item['status']}[/] • {item['check']}: {', '.join(item.get('evidence', [])) or 'sem evidência'}")
            except (OSError, ValueError) as exc:
                console.print(f"[red]{exc}[/]")
        elif choice == "2":
            if not codex:
                console.print("[red]Codex CLI não encontrado no PATH.[/]")
                continue
            prompt = (
                "Review PORTAI_GAME_PORTABILITY_PLAN.json and provide a concrete, prioritized Android portability plan. "
                "Do not edit, create, delete, or build any file. Distinguish evidence from assumptions, identify dependencies, "
                "touch controls, graphics/performance risks, and whether Linux/Windows/macOS external tooling is required. "
                "Do not claim the game can be converted automatically."
            )
            codex_task(codex, workspace, state, prompt, sandbox="read-only")
            _game_progress(workspace, state, analysis, report_paths)
        elif choice == "3":
            if not codex:
                console.print("[red]Codex CLI não encontrado no PATH.[/]")
                continue
            candidates = analysis["candidate_files"]
            if not candidates:
                console.print("[yellow]A análise não encontrou arquivos candidatos para autorização.[/]")
                continue
            candidates = candidates[:80]
            for index, item in enumerate(candidates, 1):
                console.print(f"[bright_red]{index}[/] {item['path']} [dim]({', '.join(item['reasons'])})[/]")
            raw = ask_prompt("Índices exatos autorizados, separados por vírgula (0 cancela)", default="0")
            try:
                indices = list(dict.fromkeys(int(part.strip()) for part in raw.split(",") if part.strip()))
            except ValueError:
                console.print("[red]Use apenas índices numéricos.[/]")
                continue
            if not indices or indices == [0]:
                continue
            if any(index < 1 or index > len(candidates) for index in indices):
                console.print("[red]Um dos índices não corresponde à lista.[/]")
                continue
            authorized = [candidates[index - 1]["path"] for index in indices]
            state["authorized_game_files"] = authorized
            backup_manifest = backup_authorized_files(workspace, authorized, WORKSPACES / ".portai-game-backups")
            state.setdefault("game_backup_manifests", []).append(str(backup_manifest))
            before = workspace_inventory(workspace)
            plan_context = {
                "engine": analysis["engine"], "incompatibilities": analysis["incompatibilities"],
                "plan": analysis["plan"], "external_build_host": analysis["external_build_host"],
            }
            prompt = (
                "Adapt this game project toward Android using only these user-authorized existing files: "
                + json.dumps(authorized, ensure_ascii=False)
                + ". Do not edit or create any other path, do not access secrets, and do not modify the original project. "
                "Keep the patch small and reviewable; preserve desktop behavior, game logic, save formats and IDs. For every keyboard/mouse action in scope, map the action to an appropriate touch control (virtual buttons, joystick, tap/drag gesture, or touch UI), explain placement/feedback and avoid hiding important game content. "
                "For each Windows/desktop-only API in scope, propose and implement a concrete portable Android-capable alternative only when safe in these files; otherwise leave it unchanged and document the required adapter/file. Preserve existing behavior with platform guards when feasible. "
                "Do not invent engine APIs or claim a build passed. If required changes need other files or a Linux/Windows/macOS host, stop and report them "
                "without touching those paths. Context: " + json.dumps(plan_context, ensure_ascii=False)
                + ". Record each input action -> touch mapping, desktop API -> replacement (or blocker), changed paths, risks and blockers in your response."
            )
            codex_task(codex, workspace, state, prompt, sandbox="workspace-write")
            after = workspace_inventory(workspace)
            changed = sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))
            diff_text, diff_changed = _game_authorized_diff(workspace, backup_manifest, authorized)
            state["game_last_modified_files"] = changed
            state["game_out_of_scope_changes"] = sorted(set(changed) - set(authorized))
            state["game_authorized_diff_files"] = diff_changed
            diff_path = workspace / "GAME_PORTABILITY_DIFF.patch"
            diff_path.write_text(diff_text or "Nenhuma alteração textual autorizada foi detectada.\n", encoding="utf-8")
            state["game_diff_path"] = str(diff_path)
            if state["game_out_of_scope_changes"]:
                state["status"] = "revisão necessária: Codex alterou paths não autorizados"
                state["last_error"] = "Alterações fora da lista autorizada: " + ", ".join(state["game_out_of_scope_changes"])
                console.print(f"[yellow]Foram detectadas alterações fora da lista autorizada: {state['last_error']}[/]")
            save_workspace_state(workspace, state)
            _game_progress(workspace, state, analysis, report_paths)
            console.print(f"Arquivos modificados detectados: {', '.join(changed) or 'nenhum'}")
            console.print(f"Diff revisável: {diff_path} • arquivos autorizados alterados: {', '.join(diff_changed) or 'nenhum'}")
            if diff_text:
                console.print(Panel(diff_text[:12000], title="DIFF DAS ALTERAÇÕES AUTORIZADAS", border_style="red"))
        elif choice == "4":
            if not codex:
                console.print("[red]Codex CLI não encontrado no PATH.[/]")
            elif not state.get("session_id"):
                console.print("[yellow]Nenhum ID de sessão persistente foi salvo ainda.[/]")
            else:
                codex_task(codex, workspace, state, "", resume=True, sandbox="workspace-write")
                _game_progress(workspace, state, analysis, report_paths)
        elif choice == "5":
            show_workspace_progress(workspace, state)
            progress = workspace / "GAME_PORTABILITY_PROGRESS.json"
            if progress.is_file():
                console.print(Panel(progress.read_text(encoding="utf-8", errors="replace"), title="PROGRESSO PORTAI", border_style="red"))
        elif choice == "6":
            manifest = _latest_game_backup(workspace)
            if manifest is None:
                console.print("[yellow]Nenhum backup de arquivos autorizados foi encontrado.[/]")
                continue
            if ask_confirm(f"Recuperar arquivos conforme {manifest}?", default=False):
                try:
                    restored = restore_authorized_backup(workspace, manifest)
                    state["game_last_modified_files"] = restored
                    state["game_out_of_scope_changes"] = []
                    state["status"] = "backup autorizado recuperado"
                    state["last_error"] = None
                    save_workspace_state(workspace, state)
                    _game_progress(workspace, state, analysis, report_paths)
                    console.print(f"[green]Recuperados: {', '.join(restored)}[/]")
                except (OSError, ValueError, KeyError) as exc:
                    console.print(f"[red]Falha ao recuperar backup: {exc}[/]")
        elif choice == "7":
            godot_export = analysis["engine"] == "Godot" and bool(shutil.which("godot") or shutil.which("godot4")) and bool(_godot_android_preset(workspace))
            supported_build = godot_export or _is_android_gradle_app(workspace) or ((workspace / "CMakeLists.txt").is_file() and bool(shutil.which("cmake")))
            if not supported_build:
                console.print(f"[yellow]Build não iniciada: falta um preset Godot Android utilizável ou configuração Android Gradle/CMake. Unity/Unreal/GameMaker precisam de exportador e toolchain próprios. {analysis['external_build_host']}[/]")
                continue
            if not ask_confirm("Exportar/compilar o jogo para Android no workspace?", default=False):
                continue
            prior_apks = {path.resolve(): path.stat().st_mtime_ns for path in workspace.rglob("*.apk") if path.is_file()}
            state["status"] = "compilando projeto Android"
            save_workspace_state(workspace, state)
            code, stdout, stderr, apk, build_method = _run_game_export(workspace, analysis["engine"])
            if apk and prior_apks.get(apk.resolve()) == apk.stat().st_mtime_ns:
                code, apk = 1, None
                stderr += "\nO APK localizado já existia antes desta execução; build não considerada como nova saída."
            build_result = {
                "return_code": code, "apk": str(apk) if apk else None,
                "validated": bool(apk and validate_apk(apk)),
                "method": build_method,
                "stdout_tail": stdout[-6000:], "stderr_tail": stderr[-6000:],
                "completed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            }
            if build_result["validated"] and apk:
                build_result.update(_test_game_apk(apk))
                devices = build_result.get("connected_devices", [])
                package_id = build_result.get("package_id")
                if devices and package_id and ask_confirm(f"Instalar e abrir {package_id} em {devices[0]} para teste?", default=False):
                    adb = shutil.which("adb")
                    try:
                        installed = subprocess.run([adb, "-s", devices[0], "install", "-r", str(apk)], capture_output=True, text=True, timeout=300, check=False)
                        build_result["device_install"] = {"return_code": installed.returncode, "stdout": installed.stdout[-3000:], "stderr": installed.stderr[-3000:]}
                        if installed.returncode == 0:
                            launched = subprocess.run([adb, "-s", devices[0], "shell", "monkey", "-p", package_id, "1"], capture_output=True, text=True, timeout=60, check=False)
                            build_result["device_launch"] = {"return_code": launched.returncode, "stdout": launched.stdout[-3000:], "stderr": launched.stderr[-3000:]}
                            time.sleep(2)
                            process = subprocess.run([adb, "-s", devices[0], "shell", "pidof", package_id], capture_output=True, text=True, timeout=30, check=False)
                            build_result["device_process"] = {"return_code": process.returncode, "pid": process.stdout.strip(), "stderr": process.stderr[-1000:]}
                            build_result["device_test"] = "instalado e processo do jogo detectado" if launched.returncode == 0 and process.stdout.strip() else "instalação concluída; processo não confirmado após abertura"
                        else:
                            build_result["device_test"] = "falha na instalação"
                    except (OSError, subprocess.TimeoutExpired) as exc:
                        build_result["device_test"] = f"falha no teste do dispositivo: {exc}"
                elif devices and not package_id:
                    build_result["device_test"] = "dispositivo conectado, mas package id não pôde ser identificado (instale manualmente)"
            (workspace / "GAME_ANDROID_BUILD_RESULT.json").write_text(json.dumps(build_result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            state["status"] = "APK compilado e validado" if build_result["validated"] else "build Android falhou"
            state["last_error"] = None if build_result["validated"] else (stderr[-2000:] or "Build sem APK validado.")
            save_workspace_state(workspace, state)
            _game_progress(workspace, state, analysis, report_paths)
            console.print(f"[green]APK validado: {apk} ({build_result.get('size_bytes', apk.stat().st_size)} bytes; SHA-256 {build_result.get('sha256', 'n/d')})[/]" if build_result["validated"] else f"[red]Nenhum APK validado (código {code}).[/]")
            console.print(f"Método: {build_method} • Assinatura: {build_result.get('signature', 'não verificada')} • Teste em dispositivo: {build_result.get('device_test', 'não executado')}")


def interface_language_menu() -> None:
    console.print("\n" + translate_text("Idioma da interface"))
    for index, locale in enumerate(LOCALES, 1):
        console.print(f"{index}. {LOCALE_NAMES[locale]} [{locale}]")
    choice = ask_prompt("Selecione o idioma da interface", choices=[str(i) for i in range(1, len(LOCALES) + 1)], default=str(LOCALES.index(get_locale()) + 1))
    try:
        locale = LOCALES[int(choice) - 1]
        save_locale(locale)
        console.print(f"{translate_text('Idioma salvo')}: {LOCALE_NAMES[locale]}")
    except (ValueError, OSError) as exc:
        console.print(f"[red]{translate_text('Opção inválida.')}: {exc}[/]")


def _show_project_reports() -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    if WORKSPACES.is_dir():
        workspaces = sorted(WORKSPACES.iterdir(), key=lambda path: path.stat().st_mtime, reverse=True)
        for workspace in workspaces[:30]:
            state = load_workspace_state(workspace)
            if state:
                history = state.get("history", [])
                latest = history[-1].get("prompt", "") if history else "sem atividade registrada"
                console.print(
                    f"Projeto: {state.get('source_path', workspace.name)}\n"
                    f"Estado: {state.get('status', 'indisponível')} • Sessão Codex: {state.get('session_id') or 'não iniciada'}\n"
                    f"Última atividade: {latest[:160]}"
                )
    reports = sorted(REPORTS.iterdir(), key=lambda path: path.stat().st_mtime, reverse=True)
    console.print("\nRelatórios recentes:")
    if not reports:
        console.print("Nenhum relatório disponível.")
    for path in reports[:30]:
        console.print(f"{path.name} — {path}")


def _show_translation_quality() -> None:
    history_path = REPORTS / "translation-history.json"
    reports = []
    try:
        records = json.loads(history_path.read_text(encoding="utf-8"))
        reports = [Path(item["report"]) for item in reversed(records) if item.get("report") and Path(item["report"]).is_file()]
    except (OSError, ValueError, TypeError, KeyError):
        pass
    if not reports:
        reports = sorted(REPORTS.rglob("translation-report-*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not reports:
        console.print("Nenhum relatório de tradução encontrado. Traduza um projeto para gerar a análise de qualidade.")
        return
    report = json.loads(reports[0].read_text(encoding="utf-8"))
    entries = report.get("entries", [])
    approved = sum(1 for entry in entries if entry.get("status") == "approved")
    console.print(f"Relatório mais recente: {reports[0]}\nStrings: {len(entries)}\nAprovadas: {approved}\nErros de leitura: {len(report.get('scan_errors', []))}")


def _record_translation_report(report: Path) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / "translation-history.json"
    if path.is_symlink():
        raise OSError("O histórico de tradução não pode ser um link simbólico.")
    records = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    records.append({"created_at": datetime.now().astimezone().isoformat(timespec="seconds"), "report": str(report.resolve())})
    if path.exists():
        backup = REPORTS / "backups" / datetime.now().strftime("%Y%m%d-%H%M%S-%f") / path.name
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def _show_help() -> None:
    console.print(f"OffTec PortAI {VERSION}\nFerramenta local para análise e adaptação de projetos Android.\nRelatórios: {REPORTS}\nWorkspaces persistentes: {WORKSPACES}\n\nComandos rápidos (sem menu):\n  portai doctor        diagnóstico completo\n  portai instalar      instala o que falta\n  portai info          onde fica cada coisa\n  portai analisar DIR  analisa um projeto\n  portai relatorios    histórico\n  portai atualizar     nova versão do PortAI")


def _render_menu_cards(
    actions: tuple[tuple[str, str, Any], ...],
    descriptions: dict[str, str],
    *,
    accent: str = "bright_red",
) -> None:
    """Renderiza opções como cartões e adapta as colunas à largura do terminal."""
    columns = 2 if console.width >= 78 else 1
    grid = Table.grid(expand=True, padding=(0, 1))
    for _ in range(columns):
        grid.add_column(ratio=1, min_width=28)

    cards = []
    for number, label, _action in actions:
        content = Text()
        content.append(f"{number}  ", style=f"bold {accent}")
        content.append(translate_text(label), style="bold white")
        content.append("\n")
        content.append(translate_text(descriptions.get(label, "Abrir esta área da PortAI.")), style="dim")
        cards.append(Panel(content, border_style=accent, box=box.ROUNDED, padding=(0, 1)))

    for index in range(0, len(cards), columns):
        row = cards[index:index + columns]
        if columns == 1:
            grid.add_row(row[0])
        else:
            grid.add_row(*(row + [""] * (columns - len(row))))
    console.print(grid)


def _category_menu(title: str, actions: tuple[tuple[str, str, Any], ...]) -> None:
    while True:
        console.print(f"\n[bold bright_red]{translate_text(title)}[/]")
        _render_menu_cards(actions, {
            "Encontrar e analisar projetos": "Localize projetos e gere uma análise técnica.",
            "Portar com Codex": "Trabalhe em uma cópia isolada com assistência do Codex CLI.",
            "Histórico e relatórios": "Consulte workspaces e relatórios recentes.",
            "Traduzir projeto": "Revise propostas de localização antes de aplicá-las.",
            "Traduzir APK Android": "Localize recursos e gere um APK assinado com sua keystore.",
            "Verificar qualidade das traduções": "Consulte aprovações e alertas do relatório mais recente.",
            "Analisar jogos": "Detecte engine, dependências e obstáculos para Android.",
            "Planejar adaptação": "Gere um plano de portabilidade baseado nas evidências do projeto.",
            "Reconstruir com Codex": "Continue em workspace isolado com revisão e recuperação.",
            "Idioma da interface": "Escolha o idioma dos menus e mensagens.",
            "Diagnóstico": "Todas as ferramentas, para que servem e como instalar.",
            "Verificar dependências": "Veja quais ferramentas estão instaladas no ambiente.",
            "Instalar o que falta": "Instala pelo repositório oficial do Termux só o que estiver faltando.",
            "Onde fica cada coisa": "Relatórios, workspaces, saídas e configurações em um só lugar.",
            "Atualizar o PortAI": "Baixa a versão mais nova do repositório oficial (git pull).",
            "Salvar diagnóstico em JSON": "Gera um arquivo com o estado do ambiente para suporte.",
            "Ajuda e informações": "Consulte versão, relatórios e diretórios de trabalho.",
        })
        console.print(f"[bold bright_red]0.[/] {translate_text('Voltar')}")
        choices = [number for number, _label, _action in actions] + ["0"]
        choice = ask_prompt(title, choices=choices, default="0")
        if choice == "0":
            return
        next(action for number, _label, action in actions if number == choice)()


def projects_menu() -> None:
    _category_menu("01 — PROJETOS", (
        ("1", "Encontrar e analisar projetos", run_analysis),
        ("2", "Portar com Codex", codex_port_assist),
        ("3", "Histórico e relatórios", _show_project_reports),
    ))


def apk_build_center_menu() -> None:
    from apk_build_center import ApkBuildCenter
    ApkBuildCenter(ROOT, WORKSPACES, REPORTS, run_build, validate_apk, ask_prompt, ask_confirm, console).menu()


def translation_category_menu() -> None:
    _category_menu("03 — TRADUÇÃO", (
        ("1", "Traduzir projeto", translation_menu),
        ("2", "Traduzir APK Android", apk_translation_menu),
        ("3", "Verificar qualidade das traduções", _show_translation_quality),
    ))


def game_portability_menu() -> None:
    _category_menu("04 — GAME PORTABILITY", (
        ("1", "Analisar jogos", lambda: game_recreation_menu("1")),
        ("2", "Planejar adaptação", lambda: game_recreation_menu("2")),
        ("3", "Reconstruir com Codex", lambda: game_recreation_menu("3")),
    ))


def settings_menu() -> None:
    _category_menu("05 — SISTEMA E CONFIGURAÇÕES", (
        ("1", "Diagnóstico", check_environment),
        ("2", "Instalar o que falta", install_missing),
        ("3", "Onde fica cada coisa", show_locations),
        ("4", "Atualizar o PortAI", update_portai),
        ("5", "Salvar diagnóstico em JSON", export_doctor_json),
        ("6", "Idioma da interface", interface_language_menu),
        ("7", "Ajuda e informações", _show_help),
    ))


def _show_dashboard_status() -> None:
    report = portai_toolkit.collect(with_versions=False)
    by_key = {s.tool.key: s.ok for s in report.statuses}
    apk_ready = all(by_key.get(k) for k in ("java", "apktool", "apksigner"))
    ready = sum(by_key.values())
    total = len(by_key)
    codex_ready = by_key.get("codex", False)
    items = [
        f"[bold]RUNTIME[/]  [green]Python {sys.version_info.major}.{sys.version_info.minor}[/]",
        f"[bold]FERRAMENTAS[/]  [{'green' if ready == total else 'yellow'}]{ready}/{total}[/]",
        f"[bold]APK[/]  [{'green' if apk_ready else 'yellow'}]{'Pronto' if apk_ready else 'portai instalar'}[/]",
        f"[bold]CODEX CLI[/]  [{'green' if codex_ready else 'yellow'}]{'Pronto' if codex_ready else 'Opcional'}[/]",
    ]
    columns = 3 if console.width >= 105 else 2 if console.width >= 76 else 1
    status = Table.grid(expand=True, padding=(0, 2))
    for _ in range(columns):
        status.add_column(ratio=1)
    for index in range(0, len(items), columns):
        row = items[index:index + columns]
        status.add_row(*(row + [""] * (columns - len(row))))
    console.print(Panel(status, title="AMBIENTE LOCAL", border_style="grey50", box=box.ROUNDED, padding=(0, 1)))


def menu() -> None:
    while True:
        banner()
        console.print(Panel(
            "[bold white]Seu espaço de trabalho para levar projetos e jogos ao Android.[/]\n"
            "[dim]Analise primeiro. Planeje a adaptação. Revise cada mudança antes de compilar.[/]",
            title="PORTABILIDADE ANDROID",
            border_style="bright_red",
            box=box.ROUNDED,
            padding=(0, 2),
        ))
        _show_dashboard_status()
        categories = (
            ("1", "01 — PROJETOS", projects_menu),
            ("2", "02 — APK BUILD CENTER", apk_build_center_menu),
            ("3", "03 — TRADUÇÃO", translation_category_menu),
            ("4", "04 — GAME PORTABILITY", game_portability_menu),
            ("5", "05 — SISTEMA E CONFIGURAÇÕES", settings_menu),
            ("6", "06 — IA LOCAL", local_ai_menu),
        )
        console.print("\n[bold white]ÁREAS DE TRABALHO[/]")
        _render_menu_cards(categories, {
            "01 — PROJETOS": "Encontre projetos, analise tecnologias e abra relatórios.",
            "02 — APK BUILD CENTER": "Compile, inspecione, assine e valide pacotes Android.",
            "03 — TRADUÇÃO": "Localize conteúdo de projetos e recursos de APKs.",
            "04 — GAME PORTABILITY": "Analise engines e planeje a jornada do jogo até o Android.",
            "05 — SISTEMA E CONFIGURAÇÕES": "Diagnóstico, instalar o que falta, pastas, atualização e idioma.",
            "06 — IA LOCAL": "llama.cpp no próprio aparelho: chat e servidor offline.",
        })
        console.print("[bold bright_red]0.[/] Sair")
        choice = ask_prompt("PortAI", choices=[number for number, _name, _action in categories] + ["0"], default="1")
        if choice == "0":
            console.print(Panel("[bold bright_red]OffTec PortAI encerrado. Até a próxima![/]", border_style="red"))
            break
        next(action for number, _name, action in categories if number == choice)()

def _analyze_cli(path: str) -> int:
    try:
        report = analyze_project(Path(path))
        md, js = save_report(report)
        show_report(report, md, js)
        return 0
    except (OSError, ValueError) as exc:
        console.print(f"[red]Falha na análise: {exc}[/]")
        return 1


def build_parser():
    import argparse
    parser = argparse.ArgumentParser(
        prog="portai",
        description="OffTec PortAI — tudo em um comando. Sem argumentos, abre o menu.",
    )
    parser.add_argument("--version", action="version", version=f"OffTec PortAI {VERSION}")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("menu", help="abre o menu interativo (padrão)")
    doctor = sub.add_parser("doctor", aliases=["diagnostico"], help="mostra o que está instalado e o que falta")
    doctor.add_argument("--json", action="store_true", help="saída em JSON")
    inst = sub.add_parser("instalar", aliases=["install"], help="instala o que falta pelo repositório oficial do Termux")
    inst.add_argument("--base", action="store_true", help="só o essencial")
    inst.add_argument("-y", "--sim", action="store_true", help="não perguntar")
    sub.add_parser("info", aliases=["pastas"], help="onde ficam relatórios, workspaces e configurações")
    sub.add_parser("atualizar", aliases=["update"], help="atualiza o PortAI (git pull + dependências)")
    ana = sub.add_parser("analisar", aliases=["analyze"], help="analisa um projeto sem passar pelo menu")
    ana.add_argument("pasta")
    ana.add_argument("--json", action="store_true", help="imprime o relatório em JSON")
    rel = sub.add_parser("relatorios", aliases=["reports"], help="lista workspaces e relatórios recentes")
    rel.add_argument("--json", action="store_true", help="lista em JSON")
    sub.add_parser("projetos", help="lista projetos encontrados nas pastas monitoradas (JSON)")
    llama = sub.add_parser("llama", aliases=["ia"], help="IA local com llama.cpp (compilar, modelos, chat, servidor)")
    lsub = llama.add_subparsers(dest="llama_cmd")
    lsub.add_parser("instalar", help="baixa/atualiza ggml-org/llama.cpp e compila no aparelho")
    lsub.add_parser("modelos", help="lista modelos GGUF e sugestões")
    ini = lsub.add_parser("iniciar", help="sobe o servidor em segundo plano (log em ~/PortAI/llama-server.log)")
    ini.add_argument("modelo", nargs="?")
    ini.add_argument("--porta", type=int, default=8080)
    ini.add_argument("--ctx", type=int, default=8192, help="tamanho do contexto em tokens")
    ini.add_argument("--threads", type=int, default=None, help="núcleos de CPU (padrão: automático)")
    rm = lsub.add_parser("apagar", help="apaga um modelo .gguf de ~/PortAI/modelos")
    rm.add_argument("modelo")
    lsub.add_parser("parar", help="encerra o servidor em segundo plano")
    lsub.add_parser("status", help="estado da IA local em JSON")
    for name, text in (("chat", "conversa no terminal"), ("servidor", "API compatível com OpenAI em 127.0.0.1"), ("bench", "mede a velocidade")):
        p = lsub.add_parser(name, help=text)
        p.add_argument("modelo", nargs="?", help="arquivo .gguf ou repositório do Hugging Face (usuario/repo[:quant])")
        if name == "servidor":
            p.add_argument("--porta", type=int, default=8080)
    desk = sub.add_parser("desktop", help="desktop Linux na tela com Termux:X11 (Ubuntu, Debian, Fedora, Arch ou Termux)")
    dsub = desk.add_subparsers(dest="desk_cmd")
    di = dsub.add_parser("instalar", help="instala o sistema e o ambiente escolhidos")
    di.add_argument("sistema", nargs="?", default=None, help="termux, ubuntu, debian, fedora ou archlinux")
    di.add_argument("ambiente", nargs="?", default=None, help="xfce, lxqt ou openbox")
    ds = dsub.add_parser("iniciar", help="abre o desktop (depois abra o app Termux:X11)")
    ds.add_argument("sistema", nargs="?", default=None)
    ds.add_argument("ambiente", nargs="?", default=None)
    ds.add_argument("--sem-som", action="store_true")
    g = ds.add_mutually_exclusive_group()
    g.add_argument("--gpu", dest="gpu", action="store_true", default=None, help="aceleração de vídeo pela GPU do tablet (virgl)")
    g.add_argument("--sem-gpu", dest="gpu", action="store_false", help="desenho só pelo processador (mais compatível)")
    dsub.add_parser("parar", help="fecha o desktop")
    dsub.add_parser("status", help="estado em JSON")
    vmp = sub.add_parser("vm", help="roda sistemas (ISO/IMG/QCOW2…) que estão no aparelho, com QEMU na tela do Termux:X11")
    vsub = vmp.add_subparsers(dest="vm_cmd")
    vsub.add_parser("procurar", help="lista arquivos de sistema encontrados no aparelho (JSON)")
    vi = vsub.add_parser("instalar", help="instala o QEMU")
    vi.add_argument("arch", nargs="?", default="aarch64", help="aarch64 (ARM, mais rápido) ou x86_64 (PC)")
    vs = vsub.add_parser("iniciar", help="liga a máquina virtual com o arquivo escolhido")
    vs.add_argument("arquivo")
    vs.add_argument("--arch", default=None)
    vs.add_argument("--ram", type=int, default=4096, help="memória em MB")
    vs.add_argument("--cpus", type=int, default=4)
    vs.add_argument("--disco", default="32G", help="tamanho do disco virtual criado para ISOs")
    vd = vsub.add_parser("debian", help="Debian fixa: instala tudo, baixa um disco Debian já instalado (1ª vez) e liga a VM")
    vd.add_argument("--ram", type=int, default=4096, help="memória em MB")
    vd.add_argument("--cpus", type=int, default=4)
    vd.add_argument("--disco", default="20G", help="tamanho do disco na 1ª vez")
    vd.add_argument("--apagar", action="store_true", help="apaga o disco da Debian fixa (perde tudo)")
    vsub.add_parser("parar", help="desliga a máquina virtual")
    vsub.add_parser("status", help="estado em JSON")
    return parser


def vm_cli(args) -> int:
    import portai_vm as vm
    cmd = getattr(args, "vm_cmd", None)
    if cmd in (None, "status"):
        print(json.dumps(vm.status(), ensure_ascii=False))
        return 0
    if cmd == "procurar":
        print(json.dumps(vm.find_images(), ensure_ascii=False))
        return 0
    if cmd == "parar":
        console.print("Máquina virtual desligada." if vm.stop() else "Nenhuma máquina virtual ligada.")
        return 0
    try:
        if cmd == "instalar":
            for step in vm.install_commands(args.arch):
                console.print(f"[dim]$ {' '.join(step)}[/]")
                code = subprocess.run(step, check=False).returncode
                if code:
                    return code
            console.print("[bright_green]QEMU instalado.[/]")
            return 0
        if cmd == "debian":
            return vm_debian(vm, args)
        info = vm.start(args.arquivo, args.arch, args.ram, args.cpus, args.disco)
        console.print(f"Máquina virtual ligando ({info['arch']}). Abra o app Termux:X11.")
        return 0
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        console.print(f"[red]{exc}[/]")
        return 1


def vm_debian(vm, args) -> int:
    """Debian fixa num comando só: QEMU + download (1ª vez) + liga."""
    disk = vm.debian_path()
    if args.apagar:
        vm.stop()
        for f in (disk, Path(str(disk) + ".part")):
            f.unlink(missing_ok=True)
        console.print("Disco da Debian fixa apagado.")
        return 0
    steps = []
    if not shutil.which(vm.ARCHES["aarch64"]["bin"]) or not shutil.which("qemu-img") or not shutil.which("termux-x11"):
        console.print("[bold]1/3[/] Instalando o QEMU e o Termux:X11…")
        steps += vm.install_commands("aarch64")
    prep = vm.debian_prepare_commands(args.disco)
    if prep:
        console.print("[bold]2/3[/] Baixando a Debian 13 oficial (≈ 400 MB, só na 1ª vez; se cair, rode de novo que continua)…")
    for step in steps + prep:
        console.print(f"[dim]$ {' '.join(step)}[/]")
        code = subprocess.run(step, check=False).returncode
        if code:
            console.print("[red]Falhou. Rode de novo: portai vm debian[/]")
            return code
    vm.start(str(disk), "aarch64", args.ram, args.cpus)
    console.print("[bold]3/3[/] [bright_green]Debian fixa ligando.[/] Abra o app Termux:X11 — login: [bold]root[/] (sem senha).")
    console.print("Tudo o que instalar fica salvo. Desligue com 'poweroff' dentro dela ou: portai vm parar")
    return 0


def desktop_cli(args) -> int:
    import portai_desktop as pd
    cmd = getattr(args, "desk_cmd", None)
    if cmd in (None, "status"):
        print(json.dumps(pd.status(), ensure_ascii=False))
        return 0
    if cmd == "parar":
        console.print("Desktop fechado." if pd.stop() else "Nenhum desktop aberto.")
        return 0
    cfg = pd.load_config()
    system = args.sistema or cfg.get("system", "ubuntu")
    desktop = args.ambiente or cfg.get("desktop", "xfce")
    try:
        if cmd == "instalar":
            console.print(f"Instalando [bold]{pd.SYSTEMS[system]['label'] if system in pd.SYSTEMS else system}[/] com "
                          f"[bold]{pd.DESKTOPS[desktop]['label'] if desktop in pd.DESKTOPS else desktop}[/]…")
            code = pd.install(system, desktop, echo=lambda line: console.print(f"[dim]{line}[/]"))
            console.print("[bright_green]Pronto! Toque em ▶ Abrir desktop no app PortAI.[/]" if code == 0 else f"[red]Falhou (código {code}).[/]")
            return code
        info = pd.start(system, desktop, som=not args.sem_som, gpu=args.gpu)
        console.print(f"Desktop iniciando: {info['system']} + {info['desktop']} (pid {info['pid']}). Abra o app Termux:X11.")
        if args.gpu and not info["gpu"]:
            console.print("[yellow]Aceleração de vídeo indisponível (virglrenderer-android não instalou); abrindo sem GPU.[/]")
        return 0
    except (ValueError, RuntimeError) as exc:
        console.print(f"[red]{exc}[/]")
        return 1


def _pick_model(given: str | None) -> str | None:
    import portai_llama
    if given:
        return given
    models = portai_llama.local_models()
    if models:
        return str(models[0])
    return portai_llama.SUGGESTED_MODELS[0][0]


def show_models() -> None:
    import portai_llama
    section("MODELOS DE IA LOCAL")
    models = portai_llama.local_models()
    if models:
        for path in models:
            console.print(f"• {path.name}  [dim]{path.stat().st_size / 1e9:.2f} GB — {path}[/]")
    else:
        console.print("[yellow]Nenhum modelo baixado ainda.[/]")
    console.print("\nSugestões (baixam sozinhas no primeiro uso, ficam em ~/PortAI/modelos):")
    for repo, text in portai_llama.SUGGESTED_MODELS:
        console.print(f"  [bold]{repo}[/]  [dim]{text}[/]")
    console.print("[dim]Exemplo: portai llama chat ggml-org/gemma-3-1b-it-GGUF[/]")


def llama_cli(cmd: str | None, model: str | None = None, port: int = 8080, ctx: int = 8192, threads: int | None = None) -> int:
    import portai_llama
    if cmd in (None, "modelos"):
        show_models()
        return 0
    if cmd == "status":
        print(json.dumps(portai_llama.status(), ensure_ascii=False))
        return 0
    if cmd == "apagar":
        ok = portai_llama.delete_model(model or "")
        console.print("Modelo apagado." if ok else "Modelo não encontrado em ~/PortAI/modelos.")
        return 0 if ok else 1
    if cmd == "parar":
        stopped = portai_llama.stop_server()
        console.print("Servidor encerrado." if stopped else "Nenhum servidor em execução.")
        return 0
    if cmd == "iniciar":
        if not portai_llama.binary("llama-server"):
            console.print("[yellow]llama.cpp ainda não foi compilado. Rode: portai llama instalar[/]")
            return 1
        pid = portai_llama.start_server(_pick_model(model), port, ctx, threads)
        console.print(f"Servidor iniciado (pid {pid}) em http://127.0.0.1:{port} — log: {portai_llama.server_log()}")
        return 0
    if cmd == "instalar":
        missing = [t for t in ("git", "cmake", "clang") if not shutil.which(t)]
        if missing:
            console.print(f"[red]Faltam: {' '.join(missing)} — rode portai instalar.[/]")
            return 1
        return portai_llama.build(echo=lambda line: console.print(f"[dim]{line}[/]"))
    if not portai_llama.binary("llama-cli"):
        console.print("[yellow]llama.cpp ainda não foi compilado. Rode: portai llama instalar[/]")
        return 1
    model = _pick_model(model)
    if cmd == "chat":
        command = portai_llama.chat_command(model)
    elif cmd == "servidor":
        command = portai_llama.server_command(model, port)
        console.print(f"Servidor em [bold]http://127.0.0.1:{port}[/] (interface web e API /v1/chat/completions). Ctrl+C para parar.")
    else:
        command = portai_llama.bench_command(model)
    console.print(f"[dim]$ {' '.join(command)}[/]")
    return subprocess.run(command, env=portai_llama.llama_env(), check=False).returncode


def local_ai_menu() -> None:
    def ask_model() -> str | None:
        return ask_prompt("Modelo (.gguf ou usuario/repo do Hugging Face)", default=_pick_model(None) or "") or None
    _category_menu("06 — IA LOCAL", (
        ("1", "Instalar/atualizar llama.cpp", lambda: llama_cli("instalar")),
        ("2", "Modelos", lambda: llama_cli("modelos")),
        ("3", "Conversar no terminal", lambda: llama_cli("chat", ask_model())),
        ("4", "Servidor de IA (API OpenAI)", lambda: llama_cli("servidor", ask_model())),
        ("5", "Medir velocidade", lambda: llama_cli("bench", ask_model())),
    ))


def run_cli(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command
    if command in (None, "menu"):
        menu()
        return 0
    if command in ("doctor", "diagnostico"):
        if args.json:
            print(portai_toolkit.report_json(portai_toolkit.collect()))
            return 0
        report = show_doctor()
        return 1 if report.missing("base") else 0
    if command in ("instalar", "install"):
        return install_missing("base" if args.base else "completo", assume_yes=args.sim)
    if command in ("info", "pastas"):
        show_locations()
        return 0
    if command in ("atualizar", "update"):
        return update_portai()
    if command in ("analisar", "analyze"):
        if args.json:
            try:
                report = analyze_project(Path(args.pasta))
                md, js = save_report(report)
                report["report_files"] = {"markdown": str(md), "json": str(js)}
                print(json.dumps(report, ensure_ascii=False, default=str))
                return 0
            except (OSError, ValueError) as exc:
                print(json.dumps({"error": str(exc)}, ensure_ascii=False))
                return 1
        return _analyze_cli(args.pasta)
    if command in ("relatorios", "reports"):
        if args.json:
            REPORTS.mkdir(parents=True, exist_ok=True)
            items = sorted((p for p in REPORTS.glob("*.json") if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)[:50]
            print(json.dumps([{"name": p.name, "path": str(p), "size": p.stat().st_size,
                               "mtime": int(p.stat().st_mtime)} for p in items], ensure_ascii=False))
            return 0
        _show_project_reports()
        return 0
    if command == "projetos":
        projects, executables = discover_projects()
        print(json.dumps({"roots": [str(r) for r in scan_roots()],
                          "projects": [{k: str(v) for k, v in p.items()} for p in projects],
                          "executables": [str(e) for e in executables]}, ensure_ascii=False))
        return 0
    if command == "desktop":
        return desktop_cli(args)
    if command == "vm":
        return vm_cli(args)
    if command in ("llama", "ia"):
        return llama_cli(getattr(args, "llama_cmd", None), getattr(args, "modelo", None), getattr(args, "porta", 8080),
                         getattr(args, "ctx", 8192), getattr(args, "threads", None))
    return 2


def main() -> None:
    try:
        code = run_cli(sys.argv[1:])
        if code:
            raise SystemExit(code)
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]Operação interrompida pelo usuário.[/]")
    except Exception as exc:
        console.print(f"[red]Erro inesperado: {exc}[/]")
        raise

if __name__ == "__main__":
    main()
