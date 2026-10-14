"""Run the downloaded local model on a fixed loopback socket without prompt logs."""
import asyncio
import json
import os
import secrets
import subprocess
from pathlib import Path

import requests


def ready():
    session = requests.Session()
    session.trust_env = False
    try:
        return session.get("http://127.0.0.1:18081/health", timeout=2,
                           allow_redirects=False).status_code == 200
    except requests.RequestException:
        return False
    finally:
        session.close()


def launch(root):
    root = Path(root)
    folder = root / "runtime/local-ai"
    manifest = json.loads((folder / "manifest.json").read_text())
    # Manifest fields never choose an executable or arbitrary model location.
    binary = folder / "bin/llama-b11609/llama-server"
    filename = manifest["model_file"]
    if filename not in ("Qwen3-4B-Q4_K_M.gguf", "Qwen3-1.7B-Q4_K_M.gguf"):
        raise ValueError("Unrecognized local model")
    model = folder / filename
    if not binary.exists() or not model.exists():
        raise FileNotFoundError("Local model is not installed")
    key = folder / "api-key.txt"
    if not key.exists():
        key.write_text(secrets.token_urlsafe(32) + "\n")
    key.chmod(0o600)
    args = [str(binary), "--model", str(model), "--host", "127.0.0.1",
            "--port", "18081", "--ctx-size", "8192", "--parallel", "1",
            "--threads", "3", "--threads-batch", "3", "--gpu-layers", "0",
            "--alias", "ollie-local", "--jinja", "--log-disable",
            "--api-key-file", str(key)]
    with (folder / "server.log").open("ab") as log:
        os.chmod(folder / "server.log", 0o600)
        process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=log,
                                   stderr=log, start_new_session=True)
    (folder / "server.pid").write_text(str(process.pid))
    return process


async def supervise(root):
    process = None
    while True:
        config_path = Path(root) / "runtime/ai-settings.json"
        try:
            config = json.loads(config_path.read_text()) if config_path.exists() else {}
            local_enabled = config.get("enabled") and config.get("provider") == "local"
            if local_enabled and not await asyncio.to_thread(ready):
                if process is None or process.poll() is not None:
                    process = launch(root)
        except (OSError, ValueError, KeyError):
            # Keep the existing task service running if the model is unavailable.
            pass
        await asyncio.sleep(20)
