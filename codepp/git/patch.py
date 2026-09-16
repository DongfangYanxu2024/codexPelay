from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shlex

from .repo import is_git_repository, run_git
from ..security.ignore import IgnoreMatcher
from ..utils.markdown import extract_fenced_block, parse_markdown_document


@dataclass(frozen=True)
class PatchValidation:
    valid: bool
    error: str = ""
    files: tuple[str, ...] = ()


def extract_patch(response_text: str) -> str | None:
    _, sections = parse_markdown_document(response_text)
    section = sections.get("Patch")
    return extract_fenced_block(section, {"", "diff", "patch"}) if section else None


def patch_files(patch: str) -> tuple[str, ...]:
    files: list[str] = []

    def add(raw: str, *, git_prefix: bool = False) -> None:
        raw = raw.split("\t", 1)[0].strip()
        if not raw or raw == "/dev/null":
            return
        if raw.startswith(('"', "'")):
            try:
                parsed = shlex.split(raw, posix=True)
                raw = parsed[0] if parsed else raw
            except ValueError:
                return
        if git_prefix and raw.startswith(("a/", "b/")):
            raw = raw[2:]
        if raw not in files:
            files.append(raw)

    for line in patch.splitlines():
        if line.startswith("diff --git "):
            try:
                parts = shlex.split(line[len("diff --git "):], posix=True)
            except ValueError:
                parts = []
            for target in parts[:2]:
                add(target, git_prefix=True)
        elif line.startswith(("--- ", "+++ ")):
            add(line[4:], git_prefix=True)
        elif line.startswith(("rename from ", "rename to ")):
            add(line.split(" ", 2)[2])
        elif line.startswith(("copy from ", "copy to ")):
            add(line.split(" ", 2)[2])
    return tuple(files)


def _unsafe_file(path: str) -> str | None:
    normalized = path.replace("\\", "/")
    pure = PurePosixPath(normalized)
    windows = PureWindowsPath(path)
    if pure.is_absolute() or windows.is_absolute() or windows.drive or ".." in pure.parts:
        return "path traversal or absolute path"
    if not pure.parts or any(
        not part
        or part in {".", ".."}
        or any(ord(character) < 32 or ord(character) == 127 for character in part)
        or ":" in part
        or part.endswith((".", " "))
        for part in pure.parts
    ):
        return "non-portable or unsafe path"
    lowered = [part.lower() for part in pure.parts]
    if ".git" in lowered or ".codepp" in lowered:
        return "protected tool directory"
    name = pure.name.lower()
    stem = name.split(".", 1)[0].upper()
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    if stem in reserved:
        return "Windows reserved filename"
    if name == ".codeppignore":
        return "protected Code++ policy file"
    if (
        name == ".env"
        or name.startswith(".env.")
        or name in {".envrc", ".npmrc", ".pypirc", ".netrc"}
        or name.startswith("credentials")
        or name.startswith("secret")
        or name in {"id_rsa", "id_ed25519"}
    ):
        return "sensitive file"
    if pure.suffix.lower() in {".pem", ".key", ".p12", ".pfx"}:
        return "sensitive file"
    return None


def validate_patch(root: Path, patch: str) -> PatchValidation:
    if not is_git_repository(root):
        return PatchValidation(False, "project is not a Git repository")
    files = patch_files(patch)
    if not files:
        return PatchValidation(False, "patch does not name any files")
    if re.search(r"(?m)^(?:GIT binary patch|Binary files .+ differ)$", patch):
        return PatchValidation(False, "binary patches are not supported", files)
    if re.search(
        r"(?m)^(?:(?:new|old|deleted) file mode (?:120000|160000)|"
        r"index [0-9a-f]+\.\.[0-9a-f]+ (?:120000|160000))$",
        patch,
    ):
        return PatchValidation(False, "symlink and submodule patches are not supported", files)
    matcher = IgnoreMatcher.from_project(root, gitignore=False, codeppignore=True)
    for file in files:
        reason = _unsafe_file(file)
        if not reason and matcher.ignored(file):
            reason = "ignored by .codeppignore"
        if reason:
            return PatchValidation(False, f"unsafe patch target '{file}': {reason}", files)
    result = run_git(root, ["apply", "--check", "--whitespace=nowarn", "-"], input_text=patch)
    if result.returncode != 0:
        return PatchValidation(False, result.stderr.strip() or result.stdout.strip() or "git apply --check failed", files)
    return PatchValidation(True, files=files)


def apply_patch(root: Path, patch: str) -> PatchValidation:
    validation = validate_patch(root, patch)
    if not validation.valid:
        return validation
    result = run_git(root, ["apply", "--whitespace=nowarn", "-"], input_text=patch)
    if result.returncode != 0:
        return PatchValidation(False, result.stderr.strip() or "git apply failed", validation.files)
    return validation
