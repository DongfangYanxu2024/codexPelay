from pathlib import Path
import subprocess

import pytest


def run_git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=True)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    run_git(tmp_path, "init")
    run_git(tmp_path, "config", "user.email", "tests@example.com")
    run_git(tmp_path, "config", "user.name", "Code++ Tests")
    (tmp_path / "app.py").write_text('print("old")\n', encoding="utf-8")
    run_git(tmp_path, "add", "app.py")
    run_git(tmp_path, "commit", "-m", "initial")
    return tmp_path
