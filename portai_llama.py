"""IA local com llama.cpp (repositório oficial ggml-org/llama.cpp).

Compila no próprio aparelho (CPU ARM64 com otimizações nativas), guarda
modelos GGUF em ~/PortAI/modelos e oferece chat e servidor compatível com
a API OpenAI em http://127.0.0.1:8080 — tudo pelo comando `portai llama`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable

import portai_toolkit

LLAMA_REPO = "https://github.com/ggml-org/llama.cpp.git"
DEFAULT_PORT = 8080
# Modelos pequenos e bons para CPU de tablet (baixados do Hugging Face pelo
# próprio llama.cpp com -hf). O usuário pode informar qualquer outro repo GGUF.
SUGGESTED_MODELS = (
    ("ggml-org/gemma-3-1b-it-GGUF", "Gemma 3 1B — leve e rápido (~0,8 GB)"),
    ("Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF:Q4_K_M", "Qwen2.5 Coder 1.5B — código (~1 GB)"),
    ("bartowski/Llama-3.2-3B-Instruct-GGUF:Q4_K_M", "Llama 3.2 3B — conversa geral (~2 GB)"),
    ("ggml-org/gemma-3-4b-it-GGUF", "Gemma 3 4B — bom em português (~2,5 GB)"),
    ("ggml-org/Qwen3-4B-GGUF", "Qwen3 4B — raciocínio, mais lento (~2,5 GB)"),
    ("Qwen/Qwen2.5-Coder-7B-Instruct-GGUF:Q4_K_M", "Qwen2.5 Coder 7B — código avançado, pesado (~4,7 GB)"),
)


def source_dir() -> Path:
    return Path(os.environ.get("PORTAI_LLAMA_DIR", str(Path.home() / "llama.cpp"))).expanduser()


def models_dir() -> Path:
    path = portai_toolkit.data_home() / "modelos"
    path.mkdir(parents=True, exist_ok=True)
    return path


def binary(name: str) -> str | None:
    """Procura no PATH e na pasta de build do llama.cpp."""
    built = source_dir() / "build" / "bin" / name
    if built.is_file() and os.access(built, os.X_OK):
        return str(built)
    return shutil.which(name)


def build_commands(src: Path, jobs: int | None = None) -> list[list[str]]:
    jobs = jobs or max(1, (os.cpu_count() or 4))
    git = "git"
    steps: list[list[str]] = []
    if (src / ".git").is_dir():
        steps.append([git, "-C", str(src), "pull", "--ff-only"])
    else:
        steps.append([git, "clone", "--depth", "1", LLAMA_REPO, str(src)])
    steps.append([
        "cmake", "-S", str(src), "-B", str(src / "build"),
        "-DCMAKE_BUILD_TYPE=Release", "-DGGML_NATIVE=ON", "-DLLAMA_CURL=ON",
        "-DLLAMA_BUILD_TESTS=OFF", "-DLLAMA_BUILD_EXAMPLES=OFF",
    ])
    steps.append(["cmake", "--build", str(src / "build"), "--config", "Release", "-j", str(jobs),
                  "--target", "llama-cli", "llama-server", "llama-bench"])
    return steps


def build(runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
          echo: Callable[[str], None] = print) -> int:
    src = source_dir()
    for step in build_commands(src):
        echo("$ " + " ".join(step))
        code = runner(step, check=False).returncode
        if code != 0:
            return code
    link_dir = Path(os.environ.get("PREFIX", str(Path.home() / ".local"))) / "bin"
    link_dir.mkdir(parents=True, exist_ok=True)
    for name in ("llama-cli", "llama-server", "llama-bench"):
        target = src / "build" / "bin" / name
        link = link_dir / name
        if target.is_file():
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(target)
    return 0


def local_models() -> list[Path]:
    return sorted(models_dir().rglob("*.gguf"), key=lambda p: p.name.lower())


def model_args(model: str) -> list[str]:
    """Arquivo local → -m; repositório do Hugging Face → -hf (baixa e guarda em cache)."""
    path = Path(model).expanduser()
    if path.is_file():
        return ["-m", str(path)]
    candidate = models_dir() / model
    if candidate.is_file():
        return ["-m", str(candidate)]
    return ["-hf", model]


def llama_env() -> dict[str, str]:
    env = os.environ.copy()
    # Modelos baixados com -hf ficam junto dos demais, em ~/PortAI/modelos.
    env.setdefault("LLAMA_CACHE", str(models_dir()))
    return env


def chat_command(model: str, threads: int | None = None) -> list[str]:
    exe = binary("llama-cli") or "llama-cli"
    cmd = [exe, *model_args(model), "-cnv", "-c", "4096"]
    if threads:
        cmd += ["-t", str(threads)]
    return cmd


def server_command(model: str, port: int = DEFAULT_PORT, threads: int | None = None, ctx: int = 8192) -> list[str]:
    exe = binary("llama-server") or "llama-server"
    cmd = [exe, *model_args(model), "--host", "127.0.0.1", "--port", str(port), "-c", str(ctx)]
    if threads:
        cmd += ["-t", str(threads)]
    return cmd


def bench_command(model: str) -> list[str]:
    exe = binary("llama-bench") or "llama-bench"
    path = Path(model).expanduser()
    if not path.is_file():
        path = models_dir() / model
    return [exe, "-m", str(path), "-p", "128", "-n", "64"]


def server_log() -> Path:
    return portai_toolkit.data_home() / "llama-server.log"


def _pid_file() -> Path:
    return portai_toolkit.data_home() / "llama-server.pid"


def _running_pid() -> int | None:
    try:
        pid = int(_pid_file().read_text().strip())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        return None


def start_server(model: str, port: int = DEFAULT_PORT, ctx: int = 8192, threads: int | None = None) -> int:
    """Sobe o llama-server desacoplado do terminal (o app Android conversa com ele)."""
    old = _running_pid()
    if old:
        return old
    log = open(server_log(), "ab")
    proc = subprocess.Popen(server_command(model, port, threads, ctx), env=llama_env(), stdout=log, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, start_new_session=True)
    _pid_file().write_text(str(proc.pid))
    (portai_toolkit.data_home() / "llama-server.model").write_text(model)
    return proc.pid


def _running_model() -> str | None:
    if not _running_pid():
        return None
    try:
        return (portai_toolkit.data_home() / "llama-server.model").read_text().strip()
    except OSError:
        return None


def delete_model(name: str) -> bool:
    """Apaga um .gguf dentro de ~/PortAI/modelos (inclusive o blob do cache do Hugging Face)."""
    base = models_dir().resolve()
    given = Path(name).expanduser()
    link = given if given.is_absolute() else models_dir() / name
    if link.suffix != ".gguf" or base not in link.absolute().parents or not link.exists():
        return False
    blob = link.resolve()
    if link.is_symlink():
        link.unlink()
    if blob.exists() and base in blob.parents:
        blob.unlink()
    return True


def stop_server() -> bool:
    import signal
    pid = _running_pid()
    if not pid:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass
    _pid_file().unlink(missing_ok=True)
    return True


def status(port: int = DEFAULT_PORT) -> dict:
    import urllib.request
    health = None
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as resp:
            health = resp.read().decode("utf-8", "replace")[:200]
    except Exception as exc:  # servidor parado, carregando ou baixando o modelo
        health = None if isinstance(exc, (ConnectionError, OSError)) and "refused" in str(exc).lower() else str(exc)[:200]
    tail = ""
    try:
        tail = "\n".join(server_log().read_text(encoding="utf-8", errors="replace").splitlines()[-6:])
    except OSError:
        pass
    return {
        "installed": bool(binary("llama-server")),
        "source": str(source_dir()),
        "running_pid": _running_pid(),
        "running_model": _running_model(),
        "cpus": os.cpu_count(),
        "port": port,
        "health": health,
        "models": [{"name": p.name, "path": str(p), "size": p.stat().st_size} for p in local_models()],
        "suggested": [{"repo": r, "label": t} for r, t in SUGGESTED_MODELS],
        "log_tail": tail,
    }
