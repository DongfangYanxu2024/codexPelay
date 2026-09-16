from pathlib import Path

from ..core.context import ContextFile
from ..git.diff import RepositoryState
from ..utils.text import fence_language, safe_fence


def _append_block(lines: list[str], content: str, language: str) -> None:
    fence = safe_fence(content)
    lines.extend([f"{fence}{language}", content.rstrip(), fence])


def build_request(
    task_id: str,
    description: str,
    metadata: dict[str, str],
    files: list[ContextFile],
    repository: RepositoryState,
    memory: list[ContextFile] | None = None,
    diagnostics: str | None = None,
) -> str:
    lines = [
        "# CODEPP REQUEST", "", "Protocol: CODEPP/1", f"Task-ID: {task_id}", "",
        "## Task", "", description.strip(), "", "## Project", "",
    ]
    lines.extend(f"{key}: {value}" for key, value in metadata.items())
    lines.extend(["", "## Repository State", ""])
    if repository.is_git:
        lines.extend([f"Branch: {repository.branch}"])
        if repository.head:
            lines.append(f"Commit: {repository.head}")
        lines.extend(["", "Git Status:", ""])
        _append_block(lines, repository.status or "(clean)", "text")
    else:
        lines.append("Not a Git repository.")
    lines.extend(["", "## Relevant Files", ""])
    if not files:
        lines.append("(No explicit files were provided.)")
    for item in files:
        fence = safe_fence(item.content)
        language = "text" if item.omitted else fence_language(Path(item.path).suffix)
        lines.extend([f"### {item.path}", "", f"{fence}{language}", item.content.rstrip(), fence, ""])
    if memory:
        lines.extend(["## Repository Memory", ""])
        for item in memory:
            fence = safe_fence(item.content)
            language = "text" if item.omitted else fence_language(Path(item.path).suffix)
            lines.extend([f"### {item.path}", "", f"{fence}{language}", item.content.rstrip(), fence, ""])
    lines.extend(["## Current Diff", ""])
    _append_block(lines, repository.diff if repository.diff else "(none)", "diff")
    lines.append("")
    if repository.staged_diff:
        lines.extend(["## Staged Diff", ""])
        _append_block(lines, repository.staged_diff, "diff")
        lines.append("")
    if diagnostics:
        lines.extend(["## Error / Diagnostics", ""])
        _append_block(lines, diagnostics, "text")
        lines.append("")
    lines.extend([
        "## Requirements", "", "Analyze:", "", "1. Root cause", "2. Implementation plan",
        "3. Files to modify", "4. Unified diff if possible", "5. Verification commands",
        "6. Risks", "7. Assumptions", "", "## Executor Contract", "",
        "The downstream executor has access to the real repository.", "",
        "Do not assume unprovided project facts.", "", "Prefer minimal modifications.", "",
        "Prefer unified diff.", "", "Finish with a concise `Codex Instruction`.", "",
    ])
    return "\n".join(lines)
