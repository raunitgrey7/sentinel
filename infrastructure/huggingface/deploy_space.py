"""Deploy the Sentinel demo backend to a Hugging Face Docker Space.

Requires `huggingface-cli login` and an account allowed to host Docker Spaces
(HF currently requires PRO for Docker Spaces on cpu-basic).

    python infrastructure/huggingface/deploy_space.py [space-name]
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).parents[2]


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else "sentinel-api"
    api = HfApi()
    me = api.whoami()["name"]
    repo_id = f"{me}/{name}"
    with tempfile.TemporaryDirectory() as td:
        stage = Path(td) / "space"
        stage.mkdir()
        for item in ("backend", "simulator", "pyproject.toml", "uv.lock", "LICENSE"):
            src = ROOT / item
            if src.is_dir():
                shutil.copytree(src, stage / item, ignore=shutil.ignore_patterns("__pycache__"))
            else:
                shutil.copy2(src, stage / item)
        (stage / "infrastructure" / "docker").mkdir(parents=True)
        shutil.copy2(ROOT / "infrastructure" / "docker" / "entrypoint.sh", stage / "infrastructure" / "docker" / "entrypoint.sh")
        shutil.copy2(ROOT / "infrastructure" / "huggingface" / "Dockerfile", stage / "Dockerfile")
        shutil.copy2(ROOT / "infrastructure" / "huggingface" / "README.md", stage / "README.md")
        api.create_repo(repo_id, repo_type="space", space_sdk="docker", exist_ok=True)
        api.upload_folder(folder_path=str(stage), repo_id=repo_id, repo_type="space", commit_message="Deploy Sentinel demo backend")
    host = f"https://{me}-{name.replace('_', '-')}.hf.space"
    print(f"space  https://huggingface.co/spaces/{repo_id}")
    print(f"api    {host}")
    print("Set frontend NEXT_PUBLIC_API_URL to the api URL and add the frontend origin to")
    print("the Space variable SENTINEL_CORS_ORIGINS (Settings → Variables), then restart.")


if __name__ == "__main__":
    main()
