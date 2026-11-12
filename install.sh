#!/usr/bin/env bash
# OffTec PortAI — instalador único para Termux.
#
#   curl -fsSL https://raw.githubusercontent.com/marcosbackslaty-web/OffTec-PortAI/main/install.sh | bash
#   bash install.sh            # perfil completo (APK, build, IA)
#   bash install.sh --base     # só o necessário para abrir o PortAI
#
# Tudo vem do repositório OFICIAL do Termux (packages-cf.termux.dev) e do
# repositório oficial do PortAI no GitHub. Pode ser executado de novo a
# qualquer momento: ele só instala o que falta e atualiza o resto.
set -euo pipefail

REPO_URL="${PORTAI_REPO:-https://github.com/marcosbackslaty-web/OffTec-PortAI.git}"
BRANCH="${PORTAI_BRANCH:-main}"
DEST="${PORTAI_DIR:-$HOME/OffTec-PortAI}"
PROFILE="completo"
MIRROR_OFFICIAL=1

for arg in "$@"; do
  case "$arg" in
    --base) PROFILE="base" ;;
    --completo) PROFILE="completo" ;;
    --manter-espelho) MIRROR_OFFICIAL=0 ;;
    -h|--help)
      sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "Opção desconhecida: $arg" >&2; exit 2 ;;
  esac
done

BASE_PKGS=(python git)
FULL_PKGS=(openjdk-21 apktool apksigner aapt aapt2 jadx gradle cmake ninja clang android-tools codex termux-tools which)

say()  { printf '\033[1;31m==>\033[0m \033[1m%s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[aviso]\033[0m %s\n' "$*"; }

if [ -z "${PREFIX:-}" ] || [[ "$PREFIX" != *com.termux* ]]; then
  warn "Este instalador foi feito para o Termux. Fora dele, instale manualmente: python3, git e pip install -r requirements.txt"
  exit 1
fi

# 1) Repositório oficial do Termux ------------------------------------------
OFFICIAL="https://packages-cf.termux.dev/apt/termux-main"
if [ "$MIRROR_OFFICIAL" = 1 ]; then
  say "Usando o repositório oficial do Termux ($OFFICIAL)"
  # O pkg só troca de espelho quando o atual falha; por isso gravamos o
  # sources.list diretamente e fixamos a escolha em "default" (oficial).
  if [ -f "$PREFIX/etc/termux/mirrors/default" ]; then
    ln -sf "$PREFIX/etc/termux/mirrors/default" "$PREFIX/etc/termux/chosen_mirrors"
  fi
  echo "deb $OFFICIAL stable main" > "$PREFIX/etc/apt/sources.list"
fi

say "Atualizando o Termux (pacotes desatualizados quebram binários novos: CANNOT LINK EXECUTABLE)"
# Sem `yes |`: com pipefail o SIGPIPE do yes (141) abortaria o script.
DEBIAN_FRONTEND=noninteractive pkg upgrade -y -o Dpkg::Options::=--force-confnew -o Dpkg::Options::=--force-confdef

PKGS=("${BASE_PKGS[@]}")
[ "$PROFILE" = "completo" ] && PKGS+=("${FULL_PKGS[@]}")

MISSING=()
for p in "${PKGS[@]}"; do
  dpkg -s "$p" >/dev/null 2>&1 || MISSING+=("$p")
done
if [ "${#MISSING[@]}" -gt 0 ]; then
  say "Instalando ${#MISSING[@]} pacote(s): ${MISSING[*]}"
  pkg install -y -o Dpkg::Options::=--force-confnew "${MISSING[@]}"
else
  say "Pacotes do perfil '$PROFILE' já instalados"
fi

# 2) Código do PortAI -------------------------------------------------------
HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
if [ -n "$HERE" ] && [ -f "$HERE/portai.py" ]; then
  DEST="$HERE"
  say "Usando o PortAI desta pasta: $DEST"
elif [ -d "$DEST/.git" ]; then
  say "Atualizando $DEST"
  git -C "$DEST" pull --ff-only || warn "Não foi possível atualizar (alterações locais?). Mantendo a versão atual."
else
  say "Baixando o PortAI de $REPO_URL"
  git clone --depth 1 -b "$BRANCH" "$REPO_URL" "$DEST"
fi

say "Instalando dependências Python"
python -m pip install --disable-pip-version-check -q -r "$DEST/requirements.txt"

# 3) Comando 'portai', atalho e pastas -------------------------------------
cat > "$PREFIX/bin/portai" <<EOF
#!$PREFIX/bin/bash
exec python "$DEST/portai.py" "\$@"
EOF
chmod 700 "$PREFIX/bin/portai"

mkdir -p "$HOME/.shortcuts"
cat > "$HOME/.shortcuts/PortAI" <<EOF
#!$PREFIX/bin/bash
exec portai
EOF
chmod 700 "$HOME/.shortcuts/PortAI"

mkdir -p "$HOME/PortAI/relatorios" "$HOME/PortAI/workspaces" "$HOME/PortAI/saidas" "$HOME/PortAI/projetos"

# Permite que o app PortAI (Android) rode comandos aqui pela API oficial
# RUN_COMMAND do Termux. Só apps que você autorizar na tela de permissões usam.
mkdir -p "$HOME/.termux"
touch "$HOME/.termux/termux.properties"
if ! grep -q '^allow-external-apps *= *true' "$HOME/.termux/termux.properties"; then
  sed -i '/^#* *allow-external-apps/d' "$HOME/.termux/termux.properties"
  echo "allow-external-apps = true" >> "$HOME/.termux/termux.properties"
  command -v termux-reload-settings >/dev/null && termux-reload-settings || true
fi

if [ ! -d "$HOME/storage" ]; then
  warn "Para acessar Download/Documentos do tablet, rode uma vez: termux-setup-storage"
fi

say "Pronto! Diagnóstico:"
python "$DEST/portai.py" doctor || true
cat <<'EOF'

Comandos:
  portai              abre o menu
  portai doctor       mostra o que está instalado e o que falta
  portai instalar     instala o que falta (repositório oficial do Termux)
  portai info         onde ficam relatórios, workspaces e configurações
  portai analisar DIR analisa um projeto direto, sem menu
  portai atualizar    baixa a versão nova do PortAI
Atalho na tela inicial: widget "Termux:Widget" → PortAI
EOF
