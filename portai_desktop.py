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
    "dock": {"label": "Dock", "desc": "Leve e bonito: Openbox + barra de apps (plank)", "procs": ["plank"],
             "only": ["ubuntu", "debian", "fedora"]},
}
# Programa que prova que o ambiente está instalado dentro do sistema.
DESKTOP_BIN = {"xfce": "startxfce4", "lxqt": "startlxqt", "openbox": "openbox-session", "dock": "plank"}

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
            "openbox": "openbox tint2 xterm dbus-x11",
            "dock": "openbox plank xcompmgr pcmanfm xfce4-terminal dbus-x11"},
    "dnf": {"xfce": "xfce4-session xfwm4 xfce4-panel xfdesktop thunar xfce4-terminal dbus-x11",
            "lxqt": "lxqt-session lxqt-panel openbox qterminal dbus-x11", "openbox": "openbox tint2 xterm dbus-x11",
            "dock": "openbox plank xcompmgr pcmanfm xfce4-terminal dbus-x11"},
    "pacman": {"xfce": "xfce4 xfce4-goodies", "lxqt": "lxqt openbox", "openbox": "openbox tint2 xterm"},
}
DISTRO_INSTALL = {
    "apt": "export DEBIAN_FRONTEND=noninteractive; apt-get update && apt-get install -y --no-install-recommends {pkgs}",
    "dnf": "dnf install -y {pkgs}",
    "pacman": "pacman -Syu --noconfirm --needed {pkgs}",
}
DISTRO_SESSION = {"xfce": "startxfce4", "lxqt": "startlxqt", "openbox": "openbox-session", "dock": "portai-dock"}

# Usuário comum (com sudo): navegadores Chromium/Electron e VS Code reclamam de root.
USER = "portai"
USER_SETUP = (
    f"id {USER} >/dev/null 2>&1 || useradd -m -s /bin/bash {USER}; "
    f"mkdir -p /etc/sudoers.d && echo '{USER} ALL=(ALL:ALL) NOPASSWD: ALL' > /etc/sudoers.d/{USER} "
    f"&& chmod 440 /etc/sudoers.d/{USER}; "
    # helper do dbus com setuid: loja de apps e configurações de sistema funcionam.
    "for h in /usr/lib/dbus-1.0/dbus-daemon-launch-helper /usr/libexec/dbus-daemon-launch-helper; do "
    "[ -f $h ] && chmod u+s $h; done; true")
# Ajustes para programas rodarem dentro do proot (sem sandbox do kernel).
COMPAT_ENV = "MOZ_FAKE_NO_SANDBOX=1 CHROMIUM_FLAGS=--no-sandbox ELECTRON_DISABLE_SANDBOX=1 "

# Sessão "Dock": compositor + barra plank + Openbox.
DOCK_SCRIPT = """#!/bin/sh
# portai-dock — sessão leve do PortAI: Openbox + barra de apps (plank).
xcompmgr -n &
(sleep 1; pcmanfm --desktop) &
(sleep 2; plank) &
exec openbox-session
"""

# android — de dentro do Linux, pede coisas ao Android (como o "unproot").
ANDROID_SCRIPT = r"""#!/bin/sh
# android — comandos do lado Android a partir do desktop Linux (PortAI).
#   android abrir URL     abre o link no Android (navegador/app)
#   android cmd COMANDO   roda um comando do Android (ex.: android cmd getprop ro.product.model)
unset LD_PRELOAD LD_LIBRARY_PATH
P=/system/bin:/system/xbin
case "$1" in
  abrir) [ -n "$2" ] || { echo "uso: android abrir URL"; exit 1; }
         exec env -i PATH=$P ANDROID_DATA=/data ANDROID_ROOT=/system /system/bin/am start -a android.intent.action.VIEW -d "$2" >/dev/null ;;
  cmd)   shift; exec env -i PATH=$P ANDROID_DATA=/data ANDROID_ROOT=/system "$@" ;;
  *)     echo "uso: android abrir URL | android cmd COMANDO"; exit 1 ;;
esac
"""

# Tela e aparência. Resolução, escala, toque etc. vão para o Termux:X11 pelo
# termux-x11-preference (chave:valor); tema e tamanho do texto viram variáveis
# de ambiente da sessão Linux (valem ao abrir o desktop).
TOQUE = {"trackpad": "1", "tela": "2", "direto": "3"}
ICONES = {"padrao": "Adwaita", "papirus": "Papirus", "papirus-escuro": "Papirus-Dark", "papirus-claro": "Papirus-Light"}
THEME_PACKAGES = "gnome-themes-extra papirus-icon-theme"
ORIENTACOES = ["auto", "landscape", "portrait", "reverse landscape", "reverse portrait"]
MODOS = ["native", "scaled", "custom"]
TELA_PADRAO = {"modo": "native", "tamanho": "1920x1080", "escala": 100, "tela_cheia": True, "toque": "trackpad",
               "orientacao": "auto", "teclas": True, "tema": "escuro", "texto": 100, "icones": "papirus"}


def tela_config() -> dict:
    return {**TELA_PADRAO, **(load_config().get("tela") or {})}


def check_tela(t: dict) -> dict:
    t = {**TELA_PADRAO, **t}
    if t["modo"] not in MODOS:
        raise ValueError(f"Resolução: use {', '.join(MODOS)}")
    w, _, h = str(t["tamanho"]).lower().partition("x")
    if not (w.isdigit() and h.isdigit() and 320 <= int(w) <= 7680 and 200 <= int(h) <= 4320):
        raise ValueError("Tamanho inválido (ex.: 1920x1080)")
    t["tamanho"] = f"{int(w)}x{int(h)}"
    t["escala"] = max(30, min(300, int(t["escala"])))
    t["texto"] = max(50, min(300, int(t["texto"])))
    if t["toque"] not in TOQUE:
        raise ValueError(f"Toque: use {', '.join(TOQUE)}")
    if t["orientacao"] not in ORIENTACOES:
        raise ValueError(f"Orientação: use {', '.join(ORIENTACOES)}")
    if t["tema"] not in ("escuro", "claro"):
        raise ValueError("Tema: escuro ou claro")
    if t["icones"] not in ICONES:
        raise ValueError(f"Ícones: use {', '.join(ICONES)}")
    t["tela_cheia"], t["teclas"] = bool(t["tela_cheia"]), bool(t["teclas"])
    return t


def x11_pref_args(t: dict) -> list[str]:
    """Argumentos do termux-x11-preference para a configuração de tela."""
    b = lambda v: "true" if v else "false"
    args = [f"displayResolutionMode:{t['modo']}", f"displayScale:{t['escala']}", f"fullscreen:{b(t['tela_cheia'])}",
            f"touchMode:{TOQUE[t['toque']]}", f"forceOrientation:{t['orientacao']}",
            f"showAdditionalKbd:{b(t['teclas'])}"]
    if t["modo"] == "custom":
        args.append(f"displayResolutionCustom:{t['tamanho']}")
    return args


def theme_env(t: dict) -> str:
    """Tema escuro/claro (GTK: XFCE, Firefox, apps) e tamanho do texto, como variáveis da sessão."""
    env = "GTK_THEME=Adwaita:dark " if t["tema"] == "escuro" else "GTK_THEME=Adwaita "
    if t["texto"] != 100:
        f = f"{t['texto'] / 100:.2f}"
        env += f"GDK_DPI_SCALE={f} QT_SCALE_FACTOR={f} "
    return env


APARENCIA_SCRIPT = r"""#!/bin/sh
# portai-aparencia — tema e ícones escolhidos no app PortAI (Desktop → Tela e aparência).
T="__TEMA__"; I="__ICONES__"; D="__DARK__"
for v in 3.0 4.0; do
  mkdir -p "$HOME/.config/gtk-$v"
  printf '[Settings]\ngtk-theme-name=%s\ngtk-icon-theme-name=%s\ngtk-application-prefer-dark-theme=%s\n' "$T" "$I" "$D" > "$HOME/.config/gtk-$v/settings.ini"
done
printf 'gtk-theme-name="%s"\ngtk-icon-theme-name="%s"\n' "$T" "$I" > "$HOME/.gtkrc-2.0"
if [ -d "$HOME/.config/lxqt" ] || command -v lxqt-session >/dev/null 2>&1; then
  mkdir -p "$HOME/.config/lxqt"; f="$HOME/.config/lxqt/lxqt.conf"; touch "$f"
  grep -q '^icon_theme=' "$f" && sed -i "s/^icon_theme=.*/icon_theme=$I/" "$f" || printf '[General]\nicon_theme=%s\n' "$I" >> "$f"
fi
if command -v xfconf-query >/dev/null 2>&1; then
  (sleep 4
   xfconf-query -c xsettings -p /Net/ThemeName -s "$T"
   xfconf-query -c xsettings -p /Net/IconThemeName -s "$I") >/dev/null 2>&1 &
fi
true
"""


def aparencia_script(t: dict) -> str:
    dark = t["tema"] == "escuro"
    return (APARENCIA_SCRIPT.replace("__TEMA__", "Adwaita-dark" if dark else "Adwaita")
            .replace("__ICONES__", ICONES[t["icones"]]).replace("__DARK__", "1" if dark else "0"))


def apply_x11(t: dict) -> bool:
    """Aplica já no Termux:X11 (só funciona com o app aberto ou em segundo plano)."""
    if not shutil.which("termux-x11-preference") or not _pids("termux-x11"):
        return False
    r = subprocess.run(["termux-x11-preference", *x11_pref_args(t)], capture_output=True, text=True, timeout=15, check=False)
    return r.returncode == 0


def set_tela(changes: dict) -> tuple[dict, bool]:
    t = check_tela({**tela_config(), **{k: v for k, v in changes.items() if v is not None}})
    cfg = load_config()
    cfg["tela"] = t
    save_config(cfg)
    try:
        applied = apply_x11(t)
    except (OSError, subprocess.SubprocessError):
        applied = False
    system = cfg.get("system", "ubuntu")
    if system in SYSTEMS and system != "termux":
        try:
            setup_session(system, t)
        except OSError:
            pass
    return t, applied


# Gerenciador de programas: buscar/instalar/remover pacotes do sistema escolhido,
# pelo gerenciador oficial de cada um (apt, dnf, pacman; Termux usa apt/pkg).
PKG_CMDS = {
    "apt": {"search": "apt-cache search --names-only -- {q}",
            "installed": "dpkg-query -W -f='${Package}\\n'",
            "install": "export DEBIAN_FRONTEND=noninteractive; apt-get update -q && apt-get install -y {p}",
            "remove": "apt-get remove -y {p}"},
    "dnf": {"search": "dnf search -q -- {q}", "installed": "rpm -qa --qf '%{NAME}\\n'",
            "install": "dnf install -y {p}", "remove": "dnf remove -y {p}"},
    "pacman": {"search": "pacman -Ss -- {q}", "installed": "pacman -Qq",
               "install": "pacman -Sy --noconfirm --needed {p}", "remove": "pacman -R --noconfirm {p}"},
}
# Sugestões prontas (nome do pacote em cada família).
POPULARES = [
    {"label": "Firefox", "apt": "firefox-esr", "ubuntu": "-", "dnf": "firefox", "pacman": "firefox", "termux": "firefox"},
    {"label": "Chromium", "apt": "chromium", "ubuntu": "-", "dnf": "chromium", "pacman": "chromium", "termux": "chromium"},
    {"label": "LibreOffice", "apt": "libreoffice", "dnf": "libreoffice", "pacman": "libreoffice-fresh", "termux": "libreoffice"},
    {"label": "GIMP", "apt": "gimp", "dnf": "gimp", "pacman": "gimp", "termux": "gimp"},
    {"label": "Inkscape", "apt": "inkscape", "dnf": "inkscape", "pacman": "inkscape", "termux": "inkscape"},
    {"label": "VLC", "apt": "vlc", "dnf": "vlc", "pacman": "vlc", "termux": "vlc"},
    {"label": "Thunderbird", "apt": "thunderbird", "dnf": "thunderbird", "pacman": "thunderbird"},
    {"label": "Geany (editor de código)", "apt": "geany", "dnf": "geany", "pacman": "geany", "termux": "geany"},
    {"label": "Python + pip", "apt": "python3-pip", "dnf": "python3-pip", "pacman": "python-pip", "termux": "python"},
    {"label": "Node.js", "apt": "nodejs npm", "dnf": "nodejs npm", "pacman": "nodejs npm", "termux": "nodejs"},
    {"label": "Git", "apt": "git", "dnf": "git", "pacman": "git", "termux": "git"},
    {"label": "Falkon (navegador)", "apt": "falkon", "dnf": "falkon", "pacman": "falkon"},
    {"label": "Muon (loja gráfica do KDE)", "apt": "muon"},
    {"label": "Synaptic (loja gráfica)", "apt": "synaptic"},
]
_PKG_NAME = __import__("re").compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]*$")


def pkg_family(system: str) -> str:
    if system not in SYSTEMS:
        raise ValueError(f"Sistema desconhecido: {system}")
    return "apt" if system == "termux" else SYSTEMS[system]["family"]


def pkg_shell(system: str, script: str) -> list[str]:
    """Comando para rodar `script` como root dentro do sistema (ou direto no Termux)."""
    if system == "termux":
        return ["bash", "-c", script]
    if not rootfs(system).is_dir():
        raise RuntimeError(f"{SYSTEMS[system]['label']} ainda não está instalado. Rode: portai desktop instalar {system}")
    return ["proot-distro", "login", system, "--", "sh", "-c", script]


def check_pkgs(names: list[str]) -> list[str]:
    bad = [n for n in names if not _PKG_NAME.match(n)]
    if bad or not names:
        raise ValueError("Nome de pacote inválido: " + ", ".join(bad or ["(vazio)"]))
    return names


def parse_search(fam: str, out: str) -> list[dict]:
    res: list[dict] = []
    lines = out.splitlines()
    if fam == "apt":
        for ln in lines:
            name, sep, desc = ln.partition(" - ")
            if sep and _PKG_NAME.match(name.strip()):
                res.append({"name": name.strip(), "desc": desc.strip()})
    elif fam == "dnf":
        for ln in lines:
            left, sep, desc = ln.partition(" : ")
            name = left.strip().rsplit(".", 1)[0]
            if sep and _PKG_NAME.match(name):
                res.append({"name": name, "desc": desc.strip()})
    else:  # pacman: "repo/nome versão" + linha recuada com a descrição
        for i, ln in enumerate(lines):
            if ln and not ln.startswith(" ") and "/" in ln:
                name = ln.split("/", 1)[1].split()[0]
                desc = lines[i + 1].strip() if i + 1 < len(lines) and lines[i + 1].startswith(" ") else ""
                res.append({"name": name, "desc": desc})
    seen, uniq = set(), []
    for r in res:
        if r["name"] not in seen:
            seen.add(r["name"])
            uniq.append(r)
    return uniq


def search_packages(system: str, query: str, limit: int = 60) -> list[dict]:
    fam = pkg_family(system)
    q = query.strip()
    if not q or not all(c.isalnum() or c in "+-._ " for c in q):
        raise ValueError("Busque com letras, números ou + - . _")
    c = PKG_CMDS[fam]
    script = c["search"].format(q=shlex.quote(q)) + " 2>/dev/null; echo '@@INSTALADOS@@'; " + c["installed"] + " 2>/dev/null"
    r = subprocess.run(pkg_shell(system, script), capture_output=True, text=True, timeout=300, check=False)
    found, _, inst = r.stdout.partition("@@INSTALADOS@@")
    installed = set(inst.split())
    items = parse_search(fam, found)
    words = q.lower().split()
    items.sort(key=lambda x: (x["name"].lower() != q.lower(), not x["name"].lower().startswith(words[0]), len(x["name"])))
    for it in items:
        it["installed"] = it["name"] in installed
    return items[:limit]


def package_command(system: str, action: str, names: list[str]) -> list[str]:
    fam = pkg_family(system)
    if action not in ("install", "remove"):
        raise ValueError(action)
    script = PKG_CMDS[fam][action].format(p=" ".join(shlex.quote(n) for n in check_pkgs(names)))
    if system == "termux":
        script = script.replace("apt-get", "pkg").replace("export DEBIAN_FRONTEND=noninteractive; pkg update -q && ", "")
    return pkg_shell(system, script)


def popular(system: str) -> list[dict]:
    fam = pkg_family(system)
    out = []
    for p in POPULARES:
        name = p.get("termux") if system == "termux" else p.get(system, p.get(fam))
        if name and name != "-":
            out.append({"label": p["label"], "pkgs": name})
    return out


# Lojas gráficas: dentro do proot o polkit não funciona, então abrem com sudo.
STORE_LAUNCHERS = {
    "muon": ("[Desktop Entry]\nType=Application\nName=Loja de programas (Muon)\nExec=sudo -E muon\n"
             "Icon=muondiscover\nTerminal=false\nCategories=System;PackageManager;\n"),
    "synaptic": ("[Desktop Entry]\nType=Application\nName=Gerenciador de pacotes (Synaptic)\nExec=sudo -E synaptic\n"
                 "Icon=synaptic\nTerminal=false\nCategories=System;PackageManager;\n"),
}


def store_launchers(system: str) -> list[str]:
    """Atalhos das lojas gráficas instaladas (Muon/Synaptic), abrindo como administrador."""
    if system == "termux":
        return []
    root = rootfs(system)
    homes = [root / "root"] + ([root / "home" / USER] if (root / "home" / USER).is_dir() else [])
    out = []
    for prog, text in STORE_LAUNCHERS.items():
        if not any((root / d / prog).exists() for d in ("usr/bin", "bin")):
            continue
        for h in homes:
            for folder in (h / "Desktop", h / ".local" / "share" / "applications"):
                folder.mkdir(parents=True, exist_ok=True)
                f = folder / f"portai-{prog}.desktop"
                f.write_text(text, encoding="utf-8")
                f.chmod(0o755)
                out.append(str(f))
    return out


def shell_command(system: str, as_root: bool = False) -> list[str]:
    """Entra no terminal do Linux escolhido, sem abrir o desktop."""
    if system not in SYSTEMS:
        raise ValueError(f"Sistema desconhecido: {system}")
    if system == "termux":
        return ["bash", "-l"]
    if not rootfs(system).is_dir():
        raise RuntimeError(f"{SYSTEMS[system]['label']} ainda não está instalado. Rode: portai desktop instalar {system}")
    who = [] if as_root or not has_user(system) else ["--user", USER]
    return ["proot-distro", "login", system, *who, "--shared-tmp"]


# VNC opcional: espelha a tela do Termux:X11 (:0) para ver/controlar pelo PC
# ou outro aparelho no mesmo Wi-Fi. Sempre com senha; a tela principal continua
# sendo o Termux:X11.
VNC_PORT = 5900


def vnc_pass_file() -> Path:
    return Path.home() / ".config" / "portai" / "vnc.pass"


def local_ip() -> str:
    """IP do tablet no Wi-Fi (não envia nada: só consulta a rota)."""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sk:
            sk.connect(("10.255.255.255", 1))
            return sk.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def vnc_command(pass_file: str, port: int = VNC_PORT) -> list[str]:
    return ["x11vnc", "-display", DISPLAY, "-forever", "-shared", "-rfbport", str(port), "-rfbauth", pass_file,
            "-noxdamage", "-bg", "-o", str(_home() / "vnc.log")]


def vnc_start(log=None) -> dict:
    if not _pids("termux-x11"):
        raise RuntimeError("Abra o desktop primeiro (▶ Abrir desktop) — o VNC mostra a mesma tela.")
    if not shutil.which("x11vnc"):
        subprocess.run(["pkg", "install", "-y", "x11vnc"], stdout=log or subprocess.DEVNULL, stderr=subprocess.STDOUT,
                       stdin=subprocess.DEVNULL, check=False)
    if not shutil.which("x11vnc"):
        raise RuntimeError("Não consegui instalar o x11vnc (pkg install x11vnc).")
    pf = vnc_pass_file()
    pf.parent.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    senha = cfg.get("vnc_senha")
    if not senha or not pf.is_file():
        import secrets
        senha = "".join(secrets.choice("abcdefghjkmnpqrstuvwxyz23456789") for _ in range(8))
        subprocess.run(["x11vnc", "-storepasswd", senha, str(pf)], stdout=subprocess.DEVNULL,
                       stderr=subprocess.STDOUT, check=True)
        pf.chmod(0o600)
        cfg["vnc_senha"] = senha
        save_config(cfg)
    if not _pids("x11vnc"):
        env = os.environ.copy()
        env["DISPLAY"] = DISPLAY
        subprocess.run(vnc_command(str(pf)), env=env, stdout=log or subprocess.DEVNULL, stderr=subprocess.STDOUT,
                       stdin=subprocess.DEVNULL, check=False, timeout=60)
    return vnc_status()


def vnc_stop() -> bool:
    killed = False
    for pid in _pids("x11vnc"):
        try:
            os.kill(pid, signal.SIGTERM)
            killed = True
        except OSError:
            pass
    return killed


def vnc_status() -> dict:
    return {"rodando": bool(_pids("x11vnc")), "endereco": f"{local_ip()}:{VNC_PORT}",
            "senha": load_config().get("vnc_senha", "")}


# Limitador de processos do Android 12+ ("phantom process killer"): mata o
# desktop quando o Termux passa de 32 processos. Desligar exige o adb do próprio
# aparelho (Depuração sem fio) — ou a opção do desenvolvedor no Android 14+.
PHANTOM_ADB = ("/system/bin/device_config set_sync_disabled_for_tests persistent; "
               "/system/bin/device_config put activity_manager max_phantom_processes 2147483647; "
               "settings put global settings_enable_monitor_phantom_procs false; "
               "echo max_phantom_processes=$(device_config get activity_manager max_phantom_processes)")
LIMITADOR_SCRIPT = r"""set -e
echo "== Desligar o limitador de processos do Android =="
echo "Jeito fácil (Android 14+): Opções do desenvolvedor -> 'Desativar restrições de processos filhos'."
echo
echo "Jeito pelo adb sem fio (funciona sempre):"
echo " 1. Opções do desenvolvedor -> Depuração sem fio -> ligar -> 'Parear dispositivo com código'"
echo " 2. Use tela dividida/janela flutuante para ver o código e este terminal ao mesmo tempo."
command -v adb >/dev/null || pkg install -y android-tools
printf "Porta de PAREAMENTO (ex.: 37123): "; read -r PP
printf "Código de 6 dígitos: "; read -r CODE
adb pair "localhost:$PP" "$CODE"
printf "Porta de CONEXÃO (tela Depuração sem fio, número depois dos ':'): "; read -r CP
adb connect "localhost:$CP"
adb -s "localhost:$CP" shell '__CMD__'
adb disconnect "localhost:$CP" >/dev/null 2>&1 || true
echo "Pronto! Pode desligar a Depuração sem fio. (Repita depois de atualizações do sistema.)"
""".replace("__CMD__", PHANTOM_ADB)

HOST_PACKAGES = ["termux-x11-nightly", "pulseaudio", "virglrenderer-android"]

# Aceleração de vídeo (GPU): o virgl_test_server_android do Termux repassa o
# OpenGL do Linux para a GPU do tablet (via GLES do Android). Dentro do Linux o
# Mesa usa o driver "virpipe", que conversa com ele pelo /tmp compartilhado.
VIRGL_SERVER = "virgl_test_server_android"
GPU_ENV = "GALLIUM_DRIVER=virpipe MESA_GL_VERSION_OVERRIDE=4.0 "

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
        return {"system": "ubuntu", "desktop": "xfce", "som": True, "gpu": False, "root": False}


def save_config(cfg: dict) -> None:
    config_path().parent.mkdir(parents=True, exist_ok=True)
    config_path().write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def _check(system: str, desktop: str) -> None:
    if system not in SYSTEMS:
        raise ValueError(f"Sistema desconhecido: {system}. Use: {', '.join(SYSTEMS)}")
    if desktop not in DESKTOPS:
        raise ValueError(f"Ambiente desconhecido: {desktop}. Use: {', '.join(DESKTOPS)}")
    only = DESKTOPS[desktop].get("only")
    if only and system not in only:
        names = ", ".join(SYSTEMS[o]["label"] for o in only)
        raise ValueError(f"O ambiente {DESKTOPS[desktop]['label']} só está disponível em: {names}")


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
    inner = DISTRO_INSTALL[fam].format(pkgs=DISTRO_PACKAGES[fam][desktop] + " sudo " + THEME_PACKAGES + " " + AI_EXTRAS[system])
    steps.append(["proot-distro", "login", system, "--", "bash", "-c", inner])
    steps.append(["proot-distro", "login", system, "--", "bash", "-c", USER_SETUP])
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


def startup_command(system: str, desktop: str, som: bool, gpu: bool = False, user: str | None = None,
                    extra_env: str = "") -> str:
    """Comando que o termux-x11 executa dentro da tela (-xstartup). user=None entra como root."""
    _check(system, desktop)
    pulse = ("PULSE_SERVER=tcp:127.0.0.1 " if som else "") + (GPU_ENV if gpu else "") + COMPAT_ENV + extra_env
    if system == "termux":
        return f"env {pulse}dbus-launch --exit-with-session {SYSTEMS['termux']['session'][desktop]}"
    who = f"--user {user} " if user else ""
    return (f"proot-distro login {system} {who}--shared-tmp -- env DISPLAY={DISPLAY} {pulse}"
            f"dbus-launch --exit-with-session sh -c 'portai-aparencia; exec {DISTRO_SESSION[desktop]}'")


def has_user(system: str) -> bool:
    root = rootfs(system)
    try:
        passwd = (root / "etc" / "passwd").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return (root / "home" / USER).is_dir() and any(line.startswith(USER + ":") for line in passwd.splitlines())


def ensure_user(system: str, log=None) -> bool:
    """Cria o usuário comum em sistemas instalados antes desta versão."""
    if system == "termux":
        return False
    if not has_user(system):
        subprocess.run(["proot-distro", "login", system, "--", "bash", "-c", USER_SETUP],
                       stdout=log or subprocess.DEVNULL, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, check=False)
    return has_user(system)


def setup_session(system: str, tela: dict | None = None) -> list[str]:
    """Coloca os comandos portai-dock, android e portai-aparencia dentro do sistema."""
    if system == "termux":
        return []
    root = rootfs(system)
    if not root.is_dir():
        return []
    bin_dir = root / "usr" / "local" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    out = []
    scripts = (("portai-dock", DOCK_SCRIPT), ("android", ANDROID_SCRIPT),
               ("portai-aparencia", aparencia_script(check_tela(tela or tela_config()))))
    for name, text in scripts:
        f = bin_dir / name
        f.write_text(text, encoding="utf-8")
        f.chmod(0o755)
        out.append(str(f))
    out += tablet_links(system)
    return out


def tablet_links(system: str) -> list[str]:
    """Pasta "Tablet" (o armazenamento do aparelho, /sdcard) na pasta pessoal e na área de trabalho."""
    root = rootfs(system)
    homes = [root / "root"] + ([root / "home" / USER] if (root / "home" / USER).is_dir() else [])
    out = []
    for h in homes:
        for folder in (h, h / "Desktop"):
            link = folder / "Tablet"
            try:
                folder.mkdir(parents=True, exist_ok=True)
                if link.is_symlink() and os.readlink(link) == "/sdcard":
                    continue  # já existe
                if link.is_symlink():
                    link.unlink()
                elif link.exists():
                    continue  # pasta "Tablet" do usuário: não mexe
                link.symlink_to("/sdcard")
                out.append(str(link))
            except OSError:
                pass
    return out


def is_installed(system: str, desktop: str) -> bool:
    if not shutil.which("termux-x11"):
        return False
    if system == "termux":
        return bool(shutil.which(SYSTEMS["termux"]["session"][desktop]))
    if DESKTOPS[desktop].get("only") and system not in DESKTOPS[desktop]["only"]:
        return False
    root = rootfs(system)
    return root.is_dir() and any((root / d / DESKTOP_BIN[desktop]).exists() for d in ("usr/bin", "bin", "usr/local/bin"))


def setup_ai(system: str) -> list[str]:
    """Coloca o comando `ia` e os atalhos do Assistente IA dentro do sistema escolhido."""
    homes_extra: list[Path] = []
    if system == "termux":
        prefix = Path(os.environ.get("PREFIX", "/data/data/com.termux/files/usr"))
        bin_dir, home = prefix / "bin", Path.home()
    else:
        root = rootfs(system)
        if not root.is_dir():
            return []
        bin_dir, home = root / "usr" / "local" / "bin", root / "root"
        if (root / "home" / USER).is_dir():
            homes_extra.append(root / "home" / USER)
    written = []
    bin_dir.mkdir(parents=True, exist_ok=True)
    ia = bin_dir / "ia"
    ia.write_text(IA_SCRIPT, encoding="utf-8")
    ia.chmod(0o755)
    written.append(str(ia))
    # Chaves que o usuário escolheu levar do app (só se existirem), com permissão 600.
    src = keys_file()
    for h in [home, *homes_extra]:
        if src.is_file() and system != "termux":
            dst = h / ".config" / "portai" / "ia.env"
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src.read_bytes())
            dst.chmod(0o600)
            written.append(str(dst))
        written += _launchers(h)
    return written


def _launchers(home: Path) -> list[str]:
    written = []
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
    info = {"x11": bool(_pids("termux-x11")), "som": bool(_pids("pulseaudio")), "gpu": bool(_pids("virgl_test_server")),
            "desktop": None}
    for key, d in sorted(DESKTOPS.items(), key=lambda kv: kv[0] != "dock"):  # dock antes do openbox
        if any(_pids(p) for p in d["procs"]):
            info["desktop"] = key
            break
    return info


def start_gpu(log) -> bool:
    """Liga o servidor virgl (instala o pacote oficial na 1ª vez). False se não deu."""
    if _pids("virgl_test_server"):
        return True
    if not shutil.which(VIRGL_SERVER):
        subprocess.run(["pkg", "install", "-y", "virglrenderer-android"], stdout=log, stderr=subprocess.STDOUT,
                       stdin=subprocess.DEVNULL, check=False)
    if not shutil.which(VIRGL_SERVER):
        return False
    subprocess.Popen([VIRGL_SERVER], stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                     start_new_session=True)
    return True


def start(system: str | None = None, desktop: str | None = None, som: bool | None = None,
          gpu: bool | None = None, as_root: bool | None = None) -> dict:
    cfg = load_config()
    system = system or cfg.get("system", "ubuntu")
    desktop = desktop or cfg.get("desktop", "xfce")
    som = cfg.get("som", True) if som is None else som
    gpu = cfg.get("gpu", False) if gpu is None else gpu
    as_root = cfg.get("root", False) if as_root is None else as_root
    tela = tela_config()
    _check(system, desktop)
    if not is_installed(system, desktop):
        raise RuntimeError(f"{SYSTEMS[system]['label']} com {DESKTOPS[desktop]['label']} ainda não está instalado. "
                           f"Rode: portai desktop instalar {system} {desktop}")
    stop()
    save_config({**cfg, "system": system, "desktop": desktop, "som": som, "gpu": gpu, "root": as_root, "tela": tela})
    log = open(log_path(), "ab")
    if gpu:
        gpu = start_gpu(log)
    env = os.environ.copy()
    env["DISPLAY"] = DISPLAY
    if som and shutil.which("pulseaudio"):
        subprocess.run(["pulseaudio", "--start", "--exit-idle-time=-1",
                        "--load=module-native-protocol-tcp auth-ip-acl=127.0.0.1 auth-anonymous=1"],
                       stdout=log, stderr=subprocess.STDOUT, check=False)
    user = None
    try:
        if not as_root and ensure_user(system, log):
            user = USER
        setup_session(system, tela)
        setup_ai(system)
        store_launchers(system)
    except OSError:
        pass
    ai = ensure_ai_server()
    proc = subprocess.Popen(["termux-x11", DISPLAY, "-xstartup", startup_command(system, desktop, som, gpu, user, theme_env(tela))],
                            env=env, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    if shutil.which("termux-x11-preference"):  # aplica a tela quando o app Termux:X11 abrir
        prefs = " ".join(shlex.quote(a) for a in x11_pref_args(tela))
        subprocess.Popen(["sh", "-c", f"sleep 6; termux-x11-preference {prefs} || (sleep 8; termux-x11-preference {prefs})"],
                         stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    return {"pid": proc.pid, "system": system, "desktop": desktop, "som": som, "gpu": gpu, "user": user or "root", "ia": ai, "log": str(log_path())}


def stop() -> bool:
    killed = False
    patterns = ["termux-x11", "proot-distro login", "virgl_test_server", "x11vnc"] + [p for d in DESKTOPS.values() for p in d["procs"]]
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
        "desktops": {k: {"label": d["label"], "desc": d["desc"], "only": d.get("only")} for k, d in DESKTOPS.items()},
        "running": running(),
        "config": cfg,
        "tela": tela_config(),
        "log_tail": tail,
    }
