# OffTec PortAI

<p align="center">
  <img src="assets/portai-hero.svg" alt="OffTec PortAI: jogos, terminal Termux e portabilidade para Android" width="100%">
</p>

<p align="center"><strong>Do projeto ao bolso.</strong><br>Analise projetos e explore caminhos para levá-los ao Android com as ferramentas do Termux.</p>

> Fork de [Mcsd7/OffTec-PortAI](https://github.com/Mcsd7/OffTec-PortAI) com instalador único, diagnóstico, IA local (llama.cpp) e integração com o app Android **PortAI**.

---

**OffTec PortAI** é um assistente experimental para analisar projetos Windows e apoiar sua adaptação para Android no Termux. Ele identifica tecnologias e dependências que podem exigir ajustes, gera relatórios e, opcionalmente, usa o Codex CLI para trabalhar em uma cópia isolada do projeto.

> **Escopo:** o PortAI não converte automaticamente qualquer programa Windows em um aplicativo Android. As análises são heurísticas; revise os resultados e valide cada build no dispositivo.

## Navegação

- [Recursos](#recursos)
- [Requisitos](#requisitos)
- [Instalação](#instalação)
- [Integração com Codex](#integração-com-codex)
- [Tradução de projetos e APKs](#universal-translation-engine)
- [Portabilidade de jogos](#ai-game-recreation-engine)
- [Idioma da interface](#idioma-da-interface)
- [Limitações](#limitações)
- [Licença](#licença)

## Recursos

- Descoberta de projetos em diretórios configurados e seleção manual de pastas.
- Análise estática de arquivos de código e configuração de build.
- Identificação heurística de referências a APIs Windows, DirectX, Registry e WPF/.NET.
- Relatórios em Markdown e JSON.
- Universal Translation Engine modular para JSON, XML/Android resources, TXT, CSV, PO, RESX, properties, INI e YAML.
- Propostas de tradução revisadas antes da aplicação, com placeholders protegidos, cópias localizadas e relatórios JSON.
- Integração opcional com Codex CLI em uma cópia de trabalho isolada.
- Fluxo de build que verifica se o APK gerado é válido como arquivo ZIP e contém `AndroidManifest.xml`.

## Requisitos

- Python 3.10 ou superior.
- Termux em dispositivo ARM64 (ambiente recomendado).
- `rich`, instalado pelo `install.sh` (ou `requirements.txt`).
- Codex CLI autenticado para os recursos de assistência com Codex.
- Java, Android SDK e Gradle compatíveis com o projeto para compilar APKs.

## Instalação

Um único comando no Termux instala tudo pelo **repositório oficial do Termux** (`packages-cf.termux.dev`) e deixa o comando `portai` pronto:

```bash
pkg install -y git && git clone https://github.com/marcosbackslaty-web/OffTec-PortAI.git && bash OffTec-PortAI/install.sh
```

- `bash install.sh` instala o perfil **completo**: Python, Git, OpenJDK 21, Apktool, apksigner, aapt/aapt2/zipalign, JADX, Gradle, CMake, Ninja, Clang, ADB e Codex CLI.
- `bash install.sh --base` instala só o essencial para abrir o PortAI.
- Pode rodar de novo quando quiser: só instala o que falta.
- Cria o atalho **PortAI** para o widget do Termux:Widget.

### Tudo em um comando

| Comando | O que faz |
|---|---|
| `portai` | abre o menu |
| `portai doctor` | cada ferramenta: instalada ou não, para que serve e como instalar |
| `portai doctor --json` | o mesmo diagnóstico em JSON |
| `portai instalar` | instala o que falta (`--base` só o essencial, `-y` sem perguntar) |
| `portai info` | onde ficam relatórios, workspaces, saídas e configurações |
| `portai analisar PASTA` | analisa um projeto direto, sem menu |
| `portai relatorios` | workspaces e relatórios recentes |
| `portai atualizar` | `git pull` + dependências Python |

### Onde fica cada coisa

Os dados ficam separados do código, em uma pasta só: `~/PortAI` (mude com `PORTAI_HOME`).

```
~/PortAI/
  projetos/     coloque aqui seus projetos — aparecem na busca automática
  relatorios/   relatórios Markdown/JSON e históricos
  workspaces/   cópias isoladas usadas pelo Codex e pelo APK Build Center
  saidas/       traduções geradas (destino padrão) e APKs que você queira guardar
```

### Instalação manual (fora do Termux)

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python portai.py doctor
```
## Integração com Codex

Instale e autentique o Codex CLI antes de usar esse recurso:

```bash
codex login status
```

No PortAI, abra a opção de assistência com Codex e selecione um projeto. O aplicativo cria ou reutiliza uma cópia em `workspaces/`, preservando os arquivos originais. A partir dela, é possível solicitar análise e alterações, acompanhar a execução e iniciar o build quando o projeto oferecer suporte.

A integração depende da versão instalada do Codex CLI. Consulte `codex exec --help` se a CLI não aceitar algum comando ou opção. Evite selecionar projetos que contenham credenciais, tokens ou outros dados privados.

## Universal Translation Engine

No menu, escolha **Traduzir projeto**, informe a pasta, o idioma de origem, os idiomas de destino e uma pasta de saída fora do projeto. Os originais são somente lidos. Traduções existentes na pasta de saída recebem backup em `backups/` antes de serem substituídas. Cada proposta precisa de aprovação explícita; strings sem proposta ou aprovação aparecem no relatório.

Idiomas iniciais: `pt-BR`, `en`, `es`, `ar` e `hi`. Recursos Android são gravados em pastas `values-pt-rBR`, `values-en`, `values-es`, `values-ar` e `values-hi`. O relatório de metadados marca árabe como RTL; layouts devem ser revisados e o aplicativo Android deve declarar suporte RTL quando apropriado. Fontes e renderização de glifos árabes/Devanagari dependem do projeto Android e do dispositivo.

O padrão é `offline-review`, que não finge traduzir: deixa entradas pendentes. Para ligar uma API, serviço ou modelo local, configure um adaptador que implemente `TranslationProvider` e indique-o com `PORTAI_TRANSLATION_PROVIDER=meu_modulo:MinhaClasse`. O adaptador recebe uma lista de strings com contexto/IDs e os idiomas de origem/destino; deve implementar `translate(entries, target, source)` e retornar `{entry_id: texto}`. Segredos devem ser lidos pelo adaptador de variáveis de ambiente ou armazenamento seguro do serviço, nunca gravados no repositório.

Também é possível configurar `PORTAI_TRANSLATION_COMMAND` com um executável local ou bridge do serviço. O processo recebe JSON UTF-8 pela entrada padrão (`source_language`, `target_language` e `entries` com `id`, `path`, `key`, `format`, `text`, `context`) e devolve pela saída padrão um objeto JSON de IDs para traduções. O contexto pode indicar diálogo, menu, missão, configuração ou mensagem conforme os nomes encontrados. Esse é o contrato do adaptador PortAI, não uma API de terceiros. O processo pode buscar credenciais do próprio ambiente; não passe chaves como argumentos de linha de comando.

O motor preserva IDs estruturais, faz validação de placeholders e não altera a árvore de origem. PO simples mantém `msgid` e preenche `msgstr` na cópia localizada; entradas PO plurais são identificadas como não suportadas e ficam sem alteração. XML é serializado novamente na cópia gerada; namespaces e formatação podem mudar, então valide a saída no projeto consumidor. YAML, properties, TXT e outros dialetos são tratados como texto simples; valide a saída no projeto consumidor.

## Tradução de APK Android

No menu, escolha **Traduzir APK Android**, selecione o APK, idioma de origem e um destino (`en`, `es`, `ar` ou `hi`), depois informe a keystore e o alias que você controla. O fluxo requer `apktool`, Java e `apksigner`; `jadx` e `zipalign` são complementares. O Apktool decodifica em um workspace novo sob `workspaces/`; somente XML base de `res/values/` é passado ao Universal Translation Engine. Após revisão das propostas, os novos recursos são inseridos na cópia decodificada, reconstruídos, assinados e verificados. Para árabe, `android:supportsRtl="true"` é habilitado no Manifest da cópia e o Manifest original decodificado é guardado no backup do workspace. O APK original é conferido por SHA-256 antes e depois.

As senhas são solicitadas sem eco e fornecidas ao `apksigner` por variáveis de ambiente do subprocesso. Elas não são gravadas no relatório. Use exclusivamente uma keystore sua: o PortAI não extrai, cria nem reutiliza chaves do APK original. Reconstrução e assinatura podem invalidar atualizações sobre a instalação original, que foi assinada com outra chave.

O relatório `apk-translation-report.json` fica no workspace e registra pacote, versões, ABIs nativas detectadas, ferramentas, avisos, erros, recursos modificados, verificação de assinatura e caminho de saída. APKs split precisam do conjunto compatível completo; este fluxo processa apenas o APK selecionado e avisa quando encontra indícios de splits. Bibliotecas nativas são preservadas pelo Apktool, mas não traduzidas nem recompiladas. JADX serve apenas para inspeção complementar. O fluxo não contorna DRM, licenças ou proteções de terceiros. A validação ZIP e `apksigner verify` não substitui instalação e teste no dispositivo.

## AI Game Recreation Engine

No menu, escolha **AI Game Recreation Engine** e informe a raiz do projeto. A análise somente lê o projeto e tenta identificar Unity, Unreal Engine, Godot, GameMaker ou um projeto personalizado; também registra linguagens, manifests de dependências, controles de teclado/mouse, APIs desktop, resolução, gráficos, assets e arquivos candidatos. A detecção é heurística: confirme as evidências e o plano nos relatórios Markdown/JSON.

O fluxo oferece uma cópia isolada em `workspaces/`, reutiliza o estado e a sessão persistente do Codex, e começa em revisão somente leitura. Para solicitar alterações, selecione os arquivos candidatos autorizados; um backup recuperável é criado antes da chamada, e a ferramenta grava `GAME_PORTABILITY_DIFF.patch` com o diff dos arquivos autorizados. O pedido orienta mapear ações de teclado/mouse para controles touch e propor alternativas para APIs desktop, preservando o comportamento de desktop quando viável. O progresso registra arquivos modificados e alterações fora da lista. Revise o diff antes de usar o resultado. A recuperação restaura os arquivos autorizados daquele backup.

A análise também mostra versão da engine quando encontrada, evidências de configuração Android, arquivos com controles desktop, referências a APIs desktop, ferramentas locais e os maiores assets. Os arquivos candidatos são priorizados por incompatibilidades encontradas. As verificações são um checklist de evidências, não uma medida de compatibilidade ou garantia de conversão.

Não há conversão universal nem build de engine simulada. O plano indica a toolchain provável: Unity com módulo Android, Unreal com toolchain Android, Godot com templates de exportação, ou GameMaker com runtime/export correspondente. Essas compilações normalmente precisam de Linux, Windows ou macOS configurado. A opção de build usa o exportador Godot quando há CLI e preset Android, ou Gradle/CMake Android quando configurados. O relatório inclui tamanho, SHA-256, integridade ZIP/Manifest e verificação de assinatura quando `apksigner` está disponível. Com `adb`, `aapt` e um dispositivo conectado, oferece instalar e abrir o APK, registrando se o processo do jogo apareceu; isso não substitui teste funcional manual. Unity, Unreal e GameMaker ainda exigem seus exportadores/toolchains próprios. Código nativo, plugins, splits e dependências de engine continuam sujeitos a revisão.

## Idioma da interface

Abra **Configurações** no menu principal para escolher Português brasileiro, inglês, espanhol, árabe ou hindi. A escolha fica em `~/.config/offtec-portai/settings.json` (ou no diretório `XDG_CONFIG_HOME` quando definido); se a configuração estiver ausente ou inválida, o PortAI usa português brasileiro. O catálogo é offline e centralizado em `portai_i18n.py`, para que novas mensagens possam ser adicionadas sem alterar o Universal Translation Engine, que continua destinado à localização de conteúdo de projetos. Identificadores técnicos, comandos, nomes de ferramentas e caminhos são preservados. O árabe usa caracteres Unicode e isolates bidirecionais; a apresentação RTL depende do terminal e da fonte instalados.

## Limitações

- A análise é estática e heurística; não substitui compilação, execução ou revisão manual.
- Arquivos `.exe` são exibidos como referência, mas não são convertidos em APK.
- DirectX, DRM, drivers, bibliotecas fechadas e dependências complexas do Windows podem exigir reimplementação.
- Um executável Linux ARM64 não é automaticamente um aplicativo Android.
- Um APK estruturalmente válido ainda precisa ser instalado e testado no dispositivo.
- A assistência com Codex requer autenticação e acesso ao serviço.

## Estrutura do projeto

- `portai.py`: aplicativo de terminal e comandos `portai ...`.
- `portai_toolkit.py`: registro único de ferramentas, diagnóstico, instalação e pastas.
- `install.sh`: instalador único para Termux (repositório oficial).
- `game_portability.py`: análise heurística e relatórios de portabilidade de jogos.
- `samples/demo_windows/`: exemplo didático de projeto Windows.
- `tests/`: testes automatizados.
- `~/PortAI/relatorios`: destino dos relatórios gerados.
- `~/PortAI/workspaces`: cópias de trabalho criadas durante o uso do Codex.

## Licença

Distribuído sob a licença MIT. Consulte [`LICENSE`](LICENSE).
