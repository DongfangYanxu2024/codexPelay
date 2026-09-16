from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import shlex

from ..security.ignore import IgnoreMatcher
from ..security.redact import redact_secrets
from ..security.scanner import contains_null_byte, is_binary_path
from ..utils.encoding import TextDecodingError, read_text
from .paths import ensure_inside_project


@dataclass(frozen=True)
class ContextFile:
    path: str
    content: str
    omitted: bool = False
    redactions: int = 0


def collect_files(root: Path, requested_files: list[str], config: dict) -> list[ContextFile]:
    security = config["security"]
    matcher = IgnoreMatcher.from_project(
        root,
        gitignore=bool(security["respect_gitignore"]),
        codeppignore=bool(security["respect_codeppignore"]),
    )
    maximum = int(config["context"]["max_file_bytes"])
    result: list[ContextFile] = []
    seen: set[str] = set()
    for requested in requested_files:
        try:
            path, relative = ensure_inside_project(root, requested)
        except ValueError as exc:
            result.append(ContextFile(str(requested), f"[FILE OMITTED: {exc}]", True))
            continue
        if relative in seen:
            continue
        seen.add(relative)
        if matcher.ignored(relative):
            result.append(ContextFile(relative, "[FILE OMITTED: ignored by project rules]", True))
        elif not path.exists():
            result.append(ContextFile(relative, "[FILE OMITTED: file does not exist]", True))
        elif not path.is_file():
            result.append(ContextFile(relative, "[FILE OMITTED: not a regular file]", True))
        elif path.stat().st_size > maximum:
            result.append(ContextFile(relative, f"[FILE OMITTED: exceeds {maximum} bytes]", True))
        elif is_binary_path(path) or contains_null_byte(path):
            result.append(ContextFile(relative, "[FILE OMITTED: binary file]", True))
        else:
            try:
                content = read_text(path)
            except (OSError, TextDecodingError) as exc:
                result.append(ContextFile(relative, f"[FILE OMITTED: {exc}]", True))
                continue
            redactions = 0
            if security["redact_secrets"]:
                content, redactions = redact_secrets(content)
            result.append(ContextFile(relative, content, redactions=redactions))
    return result


def sanitize_diff(root: Path, diff: str, config: dict) -> tuple[str, int, int]:
    """Apply context ignore and redaction rules to an outbound Git diff."""
    if not diff:
        return "", 0, 0
    security = config["security"]
    matcher = IgnoreMatcher.from_project(
        root,
        gitignore=bool(security["respect_gitignore"]),
        codeppignore=bool(security["respect_codeppignore"]),
    )
    blocks = re.split(r"(?=^diff --git )", diff, flags=re.MULTILINE)
    kept: list[str] = []
    omitted = 0
    for block in blocks:
        if not block:
            continue
        first_line = block.splitlines()[0]
        paths: list[str] = []
        if first_line.startswith("diff --git "):
            try:
                parts = shlex.split(first_line[len("diff --git "):], posix=True)
            except ValueError:
                parts = []
            for value in parts[:2]:
                paths.append(value[2:] if value.startswith(("a/", "b/")) else value)
        if paths and any(matcher.ignored(path) for path in paths):
            omitted += 1
            continue
        kept.append(block)
    cleaned = "".join(kept).rstrip()
    redactions = 0
    if security["redact_secrets"]:
        cleaned, redactions = redact_secrets(cleaned)
    return cleaned, redactions, omitted


def sanitize_diagnostics(text: str, config: dict) -> tuple[str, int]:
    maximum = int(config["context"]["max_file_bytes"])
    if "\x00" in text:
        return f"[DIAGNOSTICS OMITTED: binary content]", 0
    if len(text.encode("utf-8")) > maximum:
        return f"[DIAGNOSTICS OMITTED: exceeds {maximum} bytes]", 0
    if config["security"]["redact_secrets"]:
        return redact_secrets(text)
    return text, 0


def fingerprint_files(root: Path, files: list[str]) -> dict[str, str]:
    """Hash project-contained files for later planner-context drift checks."""
    fingerprints: dict[str, str] = {}
    for requested in files:
        path, relative = ensure_inside_project(root, requested)
        if not path.is_file():
            fingerprints[relative] = "[MISSING]"
            continue
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(131072), b""):
                digest.update(chunk)
        fingerprints[relative] = digest.hexdigest()
    return fingerprints
