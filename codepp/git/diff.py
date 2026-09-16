from dataclasses import dataclass
import hashlib
from pathlib import Path

from .repo import is_git_repository, run_git


@dataclass(frozen=True)
class RepositoryState:
    is_git: bool
    branch: str = ""
    status: str = ""
    diff: str = ""
    staged_diff: str = ""
    head: str = ""


class GitCollectionError(ValueError):
    pass


def _require(result, label: str) -> str:
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown Git error"
        raise GitCollectionError(f"could not collect {label}: {detail}")
    return result.stdout.rstrip()


def collect_repository_state(
    root: Path,
    *,
    include_diff: bool = True,
    include_staged_diff: bool = False,
    include_status: bool = True,
) -> RepositoryState:
    if not is_git_repository(root):
        return RepositoryState(False)
    branch_result = run_git(root, ["branch", "--show-current"])
    status_result = run_git(root, ["status", "--short"]) if include_status else None
    # Keep Git's normal binary-file marker rather than embedding binary patches in
    # a context capsule.
    diff_result = run_git(root, ["diff", "--no-ext-diff", "--no-textconv"]) if include_diff else None
    staged_result = run_git(root, ["diff", "--cached", "--no-ext-diff", "--no-textconv"]) if include_staged_diff else None
    head_result = run_git(root, ["rev-parse", "--verify", "HEAD"])
    return RepositoryState(
        True,
        _require(branch_result, "Git branch").strip() or "(detached HEAD)",
        _require(status_result, "Git status") if status_result else "",
        _require(diff_result, "working-tree diff") if diff_result else "",
        _require(staged_result, "staged diff") if staged_result else "",
        head_result.stdout.strip() if head_result.returncode == 0 else "(unborn)",
    )


def repository_fingerprint(root: Path) -> str | None:
    """Hash the complete Git worktree/index state without persisting its content."""
    if not is_git_repository(root):
        return None
    commands = (
        (
            "Git status",
            [
                "status",
                "--porcelain=v1",
                "-z",
                # User-mediated response files and other new local artifacts
                # are commonly created after export. Existing tracked/index
                # changes are the semantic baseline that must remain stable;
                # explicit context files are fingerprinted separately.
                "--untracked-files=no",
                "--",
                ".",
                ":(exclude).codepp",
            ],
        ),
        (
            "working-tree fingerprint",
            [
                "diff",
                "--no-ext-diff",
                "--no-textconv",
                "--binary",
                "--",
                ".",
                ":(exclude).codepp",
            ],
        ),
        (
            "staged fingerprint",
            [
                "diff",
                "--cached",
                "--no-ext-diff",
                "--no-textconv",
                "--binary",
                "--",
                ".",
                ":(exclude).codepp",
            ],
        ),
    )
    digest = hashlib.sha256()
    for label, arguments in commands:
        content = _require(run_git(root, arguments), label)
        digest.update(label.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content.encode("utf-8", errors="surrogatepass"))
        digest.update(b"\0")
    return digest.hexdigest()
