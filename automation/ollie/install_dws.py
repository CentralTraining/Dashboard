"""Install the pinned official CLI with checksum verification."""
import hashlib
import io
import os
from pathlib import Path
import tarfile
import requests

VERSION = "v1.0.63"
SHA256 = "78cab668bf671c17128ac55347627fb28f80c15b9c30c5f86e32e2b5ee6e34bc"
URL = f"https://github.com/DingTalk-Real-AI/dingtalk-workspace-cli/releases/download/{VERSION}/dws-linux-amd64.tar.gz"


def install(destination):
    response = requests.get(URL, timeout=60)
    response.raise_for_status()
    if hashlib.sha256(response.content).hexdigest() != SHA256:
        raise RuntimeError("cli_checksum_mismatch")
    with tarfile.open(fileobj=io.BytesIO(response.content)) as archive:
        members = [item for item in archive.getmembers() if item.isfile() and Path(item.name).name == "dws"]
        if len(members) != 1:
            raise RuntimeError("cli_binary_missing")
        Path(destination).write_bytes(archive.extractfile(members[0]).read())
    os.chmod(destination, 0o700)


if __name__ == "__main__":
    install("dws")
