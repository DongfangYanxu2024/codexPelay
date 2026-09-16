from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess

from ..utils.encoding import write_text


@dataclass(frozen=True)
class GitResult:
    returncode: int
    stdout: str
    stderr: str


def git_available() -> bool:
    return shutil.which("git") is not None


def run_git(root: Path, args: list[str], *, input_text: str | None = None) -> GitResult:
    if not git_available():
        return GitResult(127, "", "git executable was not found")
    if input_text is None:
        process = subprocess.run(
            ["git", *args], cwd=root, text=True, capture_output=True,
            encoding="utf-8", errors="replace", check=False,
        )
        return GitResult(process.returncode, process.stdout, process.stderr)
    # Text-mode pipes translate LF to CRLF on Windows. A unified diff must retain
    # its exact line endings, especially when the working tree intentionally uses LF.
    process = subprocess.run(
        ["git", *args], cwd=root, input=input_text.encode("utf-8"),
        capture_output=True, check=False,
    )
    return GitResult(
        process.returncode,
        process.stdout.decode("utf-8", errors="replace"),
        process.stderr.decode("utf-8", errors="replace"),
    )


def git_toplevel(start: Path) -> Path | None:
    result = run_git(start, ["rev-parse", "--show-toplevel"])
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip()).resolve()


def is_git_repository(root: Path) -> bool:
    result = run_git(root, ["rev-parse", "--is-inside-work-tree"])
    return result.returncode == 0 and result.stdout.strip() == "true"


def ensure_codepp_excluded(root: Path) -> bool:
    """Idempotently exclude local Code++ state without changing project .gitignore."""
    if not is_git_repository(root):
        return False
    result = run_git(root, ["rev-parse", "--git-path", "info/exclude"])
    if result.returncode != 0 or not result.stdout.strip():
        raise ValueError(
            f"could not locate Git exclude file: {result.stderr.strip() or 'unknown error'}"
        )
    exclude = Path(result.stdout.strip())
    if not exclude.is_absolute():
        exclude = root / exclude
    try:
        existing = exclude.read_text(encoding="utf-8-sig") if exclude.exists() else ""
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"could not read Git exclude file: {exc}") from exc
    if any(line.strip() in {"/.codepp/", ".codepp/"} for line in existing.splitlines()):
        return False
    separator = "" if not existing or existing.endswith(("\n", "\r")) else "\n"
    write_text(exclude, existing + separator + "# Code++ local state\n/.codepp/\n")
    return True
