# Changelog

## 0.4.0
- Desktop Linux na tela com Termux:X11: `portai desktop instalar|iniciar|parar|status` — sistemas Termux nativo, Ubuntu, Debian, Fedora e Arch (proot-distro) com XFCE, LXQt ou Openbox, som via PulseAudio.
- `install.sh`: instalador único para Termux usando o repositório oficial (packages-cf.termux.dev), perfis `--base`/completo, comando `portai` e atalho Termux:Widget.
- `portai_toolkit.py`: registro único de ferramentas (para que serve, pacote oficial, perfil) usado pelo diagnóstico, instalação e painel.
- Comandos diretos: `portai doctor [--json]`, `instalar`, `info`, `analisar PASTA`, `relatorios`, `atualizar`.
- Dados do usuário em `~/PortAI` (relatorios, workspaces, saidas, projetos), separados do código; `PORTAI_HOME` muda o local.
- Menu 05 reorganizado como "Sistema e configurações": diagnóstico, instalar o que falta, onde fica cada coisa, atualizar, exportar diagnóstico.
- Painel inicial mostra ferramentas prontas e se o fluxo de APK está completo.
- IA local com llama.cpp oficial (ggml-org) compilado no aparelho: `portai llama instalar|modelos|iniciar|parar|status|chat|bench|apagar`, servidor em 127.0.0.1 com contexto/threads configuráveis; menu 06 — IA LOCAL.
- Diagnóstico detecta ferramentas instaladas mas quebradas (ex.: CANNOT LINK EXECUTABLE) e `portai instalar` repara (pkg upgrade + reinstall).
- Saídas JSON para integração: `portai doctor --json`, `analisar --json`, `relatorios --json`, `projetos`.
- install.sh: libera `allow-external-apps` para o app PortAI (Android), inclui which (necessário ao JADX); recursos do aparelho (bateria, Wi-Fi, lanterna, voz, câmera…) ficam no próprio app, sem Termux:API, corrige saída 141 do `yes |` com pipefail.

## 0.3.0
- Universal Translation Engine modular com extração e saída localizada para JSON, XML/Android, TXT, CSV, PO, RESX, properties, INI e YAML.
- Camada de provedores offline, adaptador por comando e plugin Python sem endpoints ou credenciais embutidos.
- Revisão explícita, validação de placeholders, backups de saídas existentes, metadados RTL e relatório de traduções.
- Tradutor de APK em workspace independente: Apktool, JADX complementar, revisão pelo UTE, rebuild, assinatura com keystore do usuário e validação.
- Diagnóstico de pacote/versão/ABIs, erros, arquivos modificados e limitações de split APKs e código nativo.
- Novo fluxo de tradução no menu principal; preservados os fluxos existentes de sessão, workspace, Codex e relatórios.
- AI Game Recreation Engine: análise heurística de engines, linguagens, dependências, controles, APIs desktop, gráficos e candidatos a adaptação Android; plano e relatórios.
- Integração opcional com sessão Codex persistente na cópia isolada, autorização de arquivos, backup/recuperação e progresso; build Gradle real validada quando aplicável.
- Localização offline centralizada da interface em pt-BR, en, es, ar e hi, com configuração persistente, suporte Unicode e direção bidirecional best-effort no terminal.

## 0.2.1
- Busca automática por projetos de código em pastas comuns do Termux/armazenamento compartilhado.
- Seleção por número em vez de digitação de caminho absoluto.
- Lista `.exe` encontrados com aviso de que binários fechados não são convertidos diretamente em APK.
- Opção de análise e integração Codex usam o mesmo seletor.

## 0.2.0
- Interface Rich, análise estática e integração inicial com Codex CLI.
