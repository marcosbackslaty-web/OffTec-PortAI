"""Desktop Linux na tela do aparelho com Termux:X11.

Escolha simples: um SISTEMA (Termux nativo, Ubuntu, Debian, Fedora, Arch) e um
AMBIENTE (XFCE, LXQt, Openbox). O app Termux:X11 (github.com/termux/termux-x11)
é a tela; as distros rodam com o proot-distro oficial do Termux. Tudo pelo
comando `portai desktop` — o app PortAI só aperta os botões.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import signal
import subprocess
from pathlib import Path
from typing import Callable

import portai_toolkit

X11_APP = "com.termux.x11"
X11_APK_URL = "https://github.com/termux/termux-x11/releases/download/nightly/termux-x11-universal-debug.apk"
DISPLAY = ":0"

DESKTOPS: dict[str, dict] = {
    "xfce": {"label": "XFCE", "desc": "Completo e estável (recomendado)",
             "procs": ["xfce4-session", "xfwm4", "xfce4-panel"]},
    "lxqt": {"label": "LXQt", "desc": "Leve, visual moderno", "procs": ["lxqt-session", "lxqt-panel"]},
    "openbox": {"label": "Openbox", "desc": "Mínimo e mais rápido", "procs": ["openbox"]},
}

# Cada sistema: como instalar cada ambiente e como iniciar a sessão.
SYSTEMS: dict[str, dict] = {
    "termux": {
        "label": "Termux (nativo)", "desc": "Mais rápido e leve; programas do repositório do Termux.", "size": "~0,8 GB",
        "packages": {"xfce": "xfce4 xfce4-goodies", "lxqt": "lxqt", "openbox": "openbox pypanel xorg-xsetroot aterm"},
        "session": {"xfce": "xfce4-session", "lxqt": "startlxqt", "openbox": "openbox-session"},
    },
    "ubuntu": {
        "label": "Ubuntu", "desc": "O mais popular; apt e milhares de programas.", "size": "~2 GB", "family": "apt",
    },
    "debian": {
        "label": "Debian", "desc": "Estável e leve; base do Ubuntu.", "size": "~1,6 GB", "family": "apt",
    },
    "fedora": {
        "label": "Fedora", "desc": "Programas recentes; usa dnf.", "size": "~2,5 GB", "family": "dnf",
    },
    "archlinux": {
        "label": "Arch Linux", "desc": "Sempre atualizado; usa pacman.", "size": "~2 GB", "family": "pacman",
    },
}

DISTRO_PACKAGES = {
    "apt": {"xfce": "xfce4 xfce4-goodies dbus-x11 xfce4-terminal", "lxqt": "lxqt-core openbox dbus-x11 qterminal",
            "openbox": "openbox tint2 xterm dbus-x11"},
    "dnf": {"xfce": "xfce4-session xfwm4 xfce4-panel xfdesktop thunar xfce4-terminal dbus-x11",
            "lxqt": "lxqt-session lxqt-panel openbox qterminal dbus-x11", "openbox": "openbox tint2 xterm dbus-x11"},
    "pacman": {"xfce": "xfce4 xfce4-goodies", "lxqt": "lxqt openbox", "openbox": "openbox tint2 xterm"},
}
DISTRO_INSTALL = {
    "apt": "export DEBIAN_FRONTEND=noninteractive; apt-get update && apt-get install -y --no-install-recommends {pkgs}",
    "dnf": "dnf install -y {pkgs}",
    "pacman": "pacman -Syu --noconfirm --needed {pkgs}",
}
DISTRO_SESSION = {"xfce": "startxfce4", "lxqt": "startlxqt", "openbox": "openbox-session"}

HOST_PACKAGES = ["termux-x11-nightly", "pulseaudio"]

# Navegador + ferramentas para o "Assistente IA" dentro do desktop.
AI_EXTRAS = {"termux": "firefox jq curl", "ubuntu": "falkon jq curl", "debian": "firefox-esr jq curl",
             "fedora": "firefox jq curl", "archlinux": "firefox jq curl"}

# Script `ia` colocado dentro do desktop. Escolha da IA: offline (llama.cpp no
# tablet), claude, deepseek ou gemini. Chaves só existem se o usuário levar do
# app PortAI (arquivo ~/.config/portai/ia.env, permissão 600).
IA_SCRIPT = r"""#!/bin/sh
# ia — assistente do PortAI dentro do desktop Linux.
#   ia                      conversa (pergunta qual IA usar)
#   ia "pergunta"           responde com a IA padrão
#   ia -i claude "pergunta" escolhe: offline | claude | deepseek | gemini
CONF="$HOME/.config/portai/ia.env"
[ -f "$CONF" ] && . "$CONF"
IA="${IA_PADRAO:-offline}"
SYS="Você é o assistente do PortAI dentro de um desktop Linux rodando num tablet Android (Termux:X11). Responda em português do Brasil, direto, com comandos prontos quando útil."
if [ "$1" = "-i" ]; then IA="$2"; shift 2; fi

perguntar() {
  q="$1"
  case "$IA" in
    claude)
      [ -z "$CLAUDE_KEY" ] && { echo "Sem chave do Claude aqui. No app PortAI: Desktop → IA no desktop → Levar minhas chaves."; return 1; }
      body=$(jq -n --arg s "$SYS" --arg q "$q" --arg m "${CLAUDE_MODEL:-claude-opus-5-5}" '{model:$m,max_tokens:16000,system:$s,messages:[{role:"user",content:$q}]}')
      curl -s --max-time 600 https://api.anthropic.com/v1/messages -H "x-api-key: $CLAUDE_KEY" \
        -H "anthropic-version: 2026-10-21" -H "content-type: application/json" -d "$body" \
        | jq -r '([.content[]? | select(.type=="text") | .text] | join("")) as $t | if $t != "" then $t else (.error.message // "sem resposta") end' ;;
    deepseek|gemini)
      if [ "$IA" = deepseek ]; then url=https://api.deepseek.com/chat/completions; key="$DEEPSEEK_KEY"; m="${DEEPSEEK_MODEL:-deepseek-flash}"
      else url=https://generativelanguage.googleapis.com/v1beta/openai/chat/completions; key="$GEMINI_KEY"; m="${GEMINI_MODEL:-gemini-3.8-flash}"; fi
      [ -z "$key" ] && { echo "Sem chave do $IA aqui. No app PortAI: Desktop → IA no desktop → Levar minhas chaves."; return 1; }
      body=$(jq -n --arg s "$SYS" --arg q "$q" --arg m "$m" '{model:$m,messages:[{role:"system",content:$s},{role:"user",content:$q}]}')
      curl -s --max-time 600 "$url" -H "Authorization: Bearer $key" -H "content-type: application/json" -d "$body" \
        | jq -r '.choices[0].message.content // .error.message // "sem resposta"' ;;
    *)
      body=$(jq -n --arg s "$SYS" --arg q "$q" '{messages:[{role:"system",content:$s},{role:"user",content:$q}]}')
      curl -s --max-time 600 http://127.0.0.1:8080/v1/chat/completions -H "content-type: application/json" -d "$body" \
        | jq -r '.choices[0].message.content // .error.message // empty' \
        || echo "A IA offline não respondeu. No app PortAI: IA → Offline → ▶ Iniciar servidor." ;;
  esac
}

if [ $# -gt 0 ]; then perguntar "$*"; exit; fi
echo "Assistente PortAI — escolha a IA:"
echo "  1) Offline (llama.cpp no tablet)   2) Claude   3) DeepSeek   4) Gemini   [Enter = $IA]"
printf "> "; read -r op
case "$op" in 1) IA=offline;; 2) IA=claude;; 3) IA=deepseek;; 4) IA=gemini;; esac
echo "Usando: $IA. Escreva sua pergunta (sair = Ctrl+D)."
while printf "\nvocê> " && read -r q; do [ -n "$q" ] && { echo; perguntar "$q"; }; done
"""

LAUNCHERS = {
    "assistente-ia.desktop": (
        "[Desktop Entry]\nType=Application\nName=Assistente IA (PortAI)\n"
        "Comment=Escolha a IA (offline, Claude, DeepSeek, Gemini) e converse\n"
        "Exec=ia\nIcon=dialog-information\nTerminal=true\nCategories=Utility;\n"),
    "ia-offline-web.desktop": (
        "[Desktop Entry]\nType=Application\nName=IA offline no navegador (PortAI)\n"
        "Comment=Chat da IA local do tablet (llama.cpp)\n"
        "Exec=xdg-open http://127.0.0.1:8080\nIcon=applications-internet\nTerminal=false\nCategories=Utility;\n"),
}


def keys_file() -> Path:
    return Path.home() / ".config" / "portai" / "ia.env"


def _home() -> Path:
    return portai_toolkit.data_home()


def config_path() -> Path:
    return _home() / "desktop.json"


def log_path() -> Path:
    return _home() / "desktop.log"


def load_config() -> dict:
    try:
        return json.loads(config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"system": "ubuntu", "desktop": "xfce", "som": True}


def save_config(cfg: dict) -> None:
    config_path().parent.mkdir(parents=True, exist_ok=True)
    config_path().write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def _check(system: str, desktop: str) -> None:
    if system not in SYSTEMS:
        raise ValueError(f"Sistema desconhecido: {system}. Use: {', '.join(SYSTEMS)}")
    if desktop not in DESKTOPS:
        raise ValueError(f"Ambiente desconhecido: {desktop}. Use: {', '.join(DESKTOPS)}")


def rootfs(system: str) -> Path:
    prefix = Path(os.environ.get("PREFIX", "/data/data/com.termux/files/usr"))
    return prefix / "var" / "lib" / "proot-distro" / "installed-rootfs" / system


def install_commands(system: str, desktop: str) -> list[list[str]]:
    """Comandos, em ordem, para deixar SISTEMA + AMBIENTE prontos."""
    _check(system, desktop)
    steps = [["pkg", "install", "-y", "x11-repo"]]
    if system == "termux":
        steps.append(["pkg", "install", "-y", *HOST_PACKAGES, "dbus", *SYSTEMS["termux"]["packages"][desktop].split(),
                      *AI_EXTRAS["termux"].split()])
        return steps
    fam = SYSTEMS[system]["family"]
    steps.append(["pkg", "install", "-y", *HOST_PACKAGES, "proot-distro"])
    if not rootfs(system).is_dir():
        steps.append(["proot-distro", "install", system])
    inner = DISTRO_INSTALL[fam].format(pkgs=DISTRO_PACKAGES[fam][desktop] + " " + AI_EXTRAS[system])
    steps.append(["proot-distro", "login", system, "--", "bash", "-c", inner])
    return steps


def install(system: str, desktop: str, runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
            echo: Callable[[str], None] = print) -> int:
    for step in install_commands(system, desktop):
        echo("$ " + " ".join(shlex.quote(s) for s in step))
        code = runner(step, check=False).returncode
        if code != 0:
            return code
    save_config({**load_config(), "system": system, "desktop": desktop})
    return 0


def startup_command(system: str, desktop: str, som: bool) -> str:
    """Comando que o termux-x11 executa dentro da tela (-xstartup)."""
    _check(system, desktop)
    pulse = "PULSE_SERVER=tcp:127.0.0.1 " if som else ""
    if system == "termux":
        return f"env {pulse}dbus-launch --exit-with-session {SYSTEMS['termux']['session'][desktop]}"
    return (f"proot-distro login {system} --shared-tmp -- env DISPLAY={DISPLAY} {pulse}"
            f"dbus-launch --exit-with-session {DISTRO_SESSION[desktop]}")


def is_installed(system: str, desktop: str) -> bool:
    if not shutil.which("termux-x11"):
        return False
    if system == "termux":
        return bool(shutil.which(SYSTEMS["termux"]["session"][desktop]))
    root = rootfs(system)
    return root.is_dir() and any((root / d / DISTRO_SESSION[desktop]).exists() for d in ("usr/bin", "bin", "usr/local/bin"))


def setup_ai(system: str) -> list[str]:
    """Coloca o comando `ia` e os atalhos do Assistente IA dentro do sistema escolhido."""
    if system == "termux":
        prefix = Path(os.environ.get("PREFIX", "/data/data/com.termux/files/usr"))
        bin_dir, home = prefix / "bin", Path.home()
    else:
        root = rootfs(system)
        if not root.is_dir():
            return []
        bin_dir, home = root / "usr" / "local" / "bin", root / "root"
    written = []
    bin_dir.mkdir(parents=True, exist_ok=True)
    ia = bin_dir / "ia"
    ia.write_text(IA_SCRIPT, encoding="utf-8")
    ia.chmod(0o755)
    written.append(str(ia))
    # Chaves que o usuário escolheu levar do app (só se existirem), com permissão 600.
    src = keys_file()
    if src.is_file() and system != "termux":
        dst = home / ".config" / "portai" / "ia.env"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
        dst.chmod(0o600)
        written.append(str(dst))
    for folder in (home / "Desktop", home / ".local" / "share" / "applications"):
        folder.mkdir(parents=True, exist_ok=True)
        for name, text in LAUNCHERS.items():
            f = folder / name
            f.write_text(text, encoding="utf-8")
            f.chmod(0o755)
            written.append(str(f))
    return written


def ensure_ai_server() -> str:
    """Sobe a IA offline (llama-server) se houver modelo baixado e ela estiver parada."""
    try:
        import portai_llama
    except ImportError:
        return "indisponível"
    if not portai_llama.binary("llama-server"):
        return "llama.cpp não instalado"
    st = portai_llama.status()
    if st.get("running_pid"):
        return "já rodando"
    models = portai_llama.local_models()
    if not models:
        return "sem modelo baixado (baixe em IA → Offline)"
    portai_llama.start_server(str(models[0]))
    return "iniciada com " + models[0].name


def _pids(pattern: str) -> list[int]:
    if not shutil.which("pgrep"):
        return []
    r = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True, check=False)
    return [int(p) for p in r.stdout.split() if p.isdigit() and int(p) != os.getpid()]


def running() -> dict:
    info = {"x11": bool(_pids("termux-x11")), "som": bool(_pids("pulseaudio")), "desktop": None}
    for key, d in DESKTOPS.items():
        if any(_pids(p) for p in d["procs"]):
            info["desktop"] = key
            break
    return info


def start(system: str | None = None, desktop: str | None = None, som: bool | None = None) -> dict:
    cfg = load_config()
    system = system or cfg.get("system", "ubuntu")
    desktop = desktop or cfg.get("desktop", "xfce")
    som = cfg.get("som", True) if som is None else som
    _check(system, desktop)
    if not is_installed(system, desktop):
        raise RuntimeError(f"{SYSTEMS[system]['label']} com {DESKTOPS[desktop]['label']} ainda não está instalado. "
                           f"Rode: portai desktop instalar {system} {desktop}")
    stop()
    save_config({"system": system, "desktop": desktop, "som": som})
    log = open(log_path(), "ab")
    env = os.environ.copy()
    env["DISPLAY"] = DISPLAY
    if som and shutil.which("pulseaudio"):
        subprocess.run(["pulseaudio", "--start", "--exit-idle-time=-1",
                        "--load=module-native-protocol-tcp auth-ip-acl=127.0.0.1 auth-anonymous=1"],
                       stdout=log, stderr=subprocess.STDOUT, check=False)
    try:
        setup_ai(system)
    except OSError:
        pass
    ai = ensure_ai_server()
    proc = subprocess.Popen(["termux-x11", DISPLAY, "-xstartup", startup_command(system, desktop, som)], env=env,
                            stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    return {"pid": proc.pid, "system": system, "desktop": desktop, "som": som, "ia": ai, "log": str(log_path())}


def stop() -> bool:
    killed = False
    patterns = ["termux-x11", "proot-distro login"] + [p for d in DESKTOPS.values() for p in d["procs"]]
    for pattern in patterns:
        for pid in _pids(pattern):
            try:
                os.kill(pid, signal.SIGTERM)
                killed = True
            except OSError:
                pass
    return killed


def status() -> dict:
    cfg = load_config()
    tail = ""
    try:
        tail = "\n".join(log_path().read_text(encoding="utf-8", errors="replace").splitlines()[-8:])
    except OSError:
        pass
    return {
        "x11_app": X11_APP,
        "x11_apk_url": X11_APK_URL,
        "x11_pkg": bool(shutil.which("termux-x11")),
        "systems": {k: {"label": s["label"], "desc": s["desc"], "size": s["size"],
                        "installed": {d: is_installed(k, d) for d in DESKTOPS}} for k, s in SYSTEMS.items()},
        "desktops": {k: {"label": d["label"], "desc": d["desc"]} for k, d in DESKTOPS.items()},
        "running": running(),
        "config": cfg,
        "log_tail": tail,
    }
