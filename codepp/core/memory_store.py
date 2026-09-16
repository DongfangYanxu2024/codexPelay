"""Safe CRUD operations for repository memory documents.

Repository memory is deliberately small and file based.  This module keeps the
filesystem boundary in one place so CLI code does not have to duplicate path,
symlink, and encoding checks.
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import tempfile

from ..utils.encoding import TextDecodingError, read_text


MEMORY_SUFFIXES = frozenset({".md", ".txt"})
WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)


class MemoryStoreError(ValueError):
    """A user-correctable repository memory error."""


def _is_link(path: Path) -> bool:
    """Recognise symbolic links and Windows directory junctions."""
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        return bool(is_junction and is_junction())
    except OSError as exc:
        raise MemoryStoreError(f"could not inspect repository memory path: {path}") from exc


def _memory_root(project_root: Path) -> tuple[Path, Path]:
    project = Path(project_root)
    if not project.exists():
        raise MemoryStoreError(f"project root does not exist: {project}")
    if not project.is_dir():
        raise MemoryStoreError(f"project root is not a directory: {project}")

    try:
        resolved_project = project.resolve(strict=True)
        codepp = resolved_project / ".codepp"
        memory = codepp / "memory"
        if _is_link(codepp):
            raise MemoryStoreError("symbolic links are not allowed for .codepp")
        if _is_link(memory):
            raise MemoryStoreError(
                "symbolic links are not allowed for .codepp/memory"
            )
        resolved_memory = memory.resolve(strict=False)
        resolved_memory.relative_to(resolved_project)
    except MemoryStoreError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise MemoryStoreError(
            "repository memory path escapes the project or cannot be resolved"
        ) from exc

    if codepp.exists() and not codepp.is_dir():
        raise MemoryStoreError(".codepp exists but is not a directory")
    if memory.exists() and not memory.is_dir():
        raise MemoryStoreError(".codepp/memory exists but is not a directory")
    return memory, resolved_memory


def _validate_portable_parts(parts: list[str], raw: str) -> None:
    for part in parts:
        if not part or part == ".":
            raise MemoryStoreError(
                f"memory document path has an empty or '.' part: {raw}"
            )
        if any(ord(character) < 32 or ord(character) == 127 for character in part):
            raise MemoryStoreError(
                f"memory document path contains an ASCII control character: {raw}"
            )
        if ":" in part:
            raise MemoryStoreError(
                f"memory document path cannot contain ':': {raw}"
            )
        if part.endswith((".", " ")):
            raise MemoryStoreError(
                f"memory document path parts cannot end with a dot or space: {raw}"
            )
        basename = part.split(".", 1)[0].rstrip(" .").upper()
        if basename in WINDOWS_RESERVED_NAMES:
            raise MemoryStoreError(
                f"memory document path uses a Windows-reserved name: {part}"
            )


def _normalise_name(name: str | Path) -> tuple[PurePosixPath, str]:
    try:
        raw = os.fspath(name)
    except TypeError as exc:
        raise MemoryStoreError("memory document name must be a path string") from exc
    if not isinstance(raw, str):
        raise MemoryStoreError("memory document name must be a path string")
    if not raw or "\x00" in raw or raw.endswith(("/", "\\")):
        raise MemoryStoreError("memory document name must name a file")

    # Treat both separators consistently so a name accepted on one platform
    # cannot become traversal when the repository is opened on another.
    portable = raw.replace("\\", "/")
    windows_path = PureWindowsPath(portable)
    relative = PurePosixPath(portable)
    if relative.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        raise MemoryStoreError(f"memory document path must be relative: {raw}")
    if not relative.parts or any(part == ".." for part in relative.parts):
        raise MemoryStoreError(f"memory document path cannot contain '..': {raw}")
    _validate_portable_parts(portable.split("/"), raw)
    if relative.suffix.lower() not in MEMORY_SUFFIXES:
        raise MemoryStoreError(
            f"memory document must use a .md or .txt extension: {raw}"
        )
    normalised = relative.as_posix()
    return relative, normalised


def _document_path(project_root: Path, name: str | Path) -> tuple[Path, str]:
    memory, resolved_memory = _memory_root(project_root)
    relative, normalised = _normalise_name(name)
    target = memory.joinpath(*relative.parts)
    try:
        current = memory
        for part in relative.parts:
            current /= part
            if _is_link(current):
                raise MemoryStoreError(
                    f"symbolic links are not allowed in repository memory: "
                    f"{normalised}"
                )
        target.resolve(strict=False).relative_to(resolved_memory)
    except MemoryStoreError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise MemoryStoreError(
            f"memory document escapes .codepp/memory: {normalised}"
        ) from exc
    return target, normalised


def _sort_key(name: str) -> tuple[str, str]:
    return name.casefold(), name


def list_documents(project_root: Path) -> list[str]:
    """Return supported memory document names in deterministic order."""
    memory, _ = _memory_root(project_root)
    if not memory.exists():
        return []

    names: list[str] = []
    try:
        for current, directories, files in os.walk(memory, followlinks=False):
            current_path = Path(current)
            linked_directories = [
                directory
                for directory in directories
                if _is_link(current_path / directory)
            ]
            if linked_directories:
                linked = (current_path / linked_directories[0]).relative_to(memory)
                raise MemoryStoreError(
                    "symbolic links are not allowed in repository memory: "
                    f"{linked.as_posix()}"
                )
            directories[:] = sorted(
                directories,
                key=lambda value: (value.casefold(), value),
            )
            for filename in files:
                candidate = current_path / filename
                if candidate.suffix.lower() not in MEMORY_SUFFIXES:
                    continue
                relative = candidate.relative_to(memory).as_posix()
                checked, normalised = _document_path(project_root, relative)
                if checked.is_file():
                    names.append(normalised)
    except MemoryStoreError:
        raise
    except OSError as exc:
        raise MemoryStoreError(f"could not list repository memory: {exc}") from exc
    return sorted(names, key=_sort_key)


def read_document(project_root: Path, name: str | Path) -> str:
    """Read one UTF-8 memory document."""
    target, normalised = _document_path(project_root, name)
    if not target.exists():
        raise MemoryStoreError(f"memory document does not exist: {normalised}")
    if not target.is_file():
        raise MemoryStoreError(f"memory document is not a regular file: {normalised}")
    try:
        return read_text(target)
    except TextDecodingError as exc:
        raise MemoryStoreError(
            f"memory document is not valid UTF-8 text: {normalised}"
        ) from exc
    except OSError as exc:
        raise MemoryStoreError(
            f"could not read memory document {normalised}: {exc}"
        ) from exc


def _validate_text(text: str) -> None:
    if not isinstance(text, str):
        raise MemoryStoreError("memory document text must be a string")
    if "\x00" in text:
        raise MemoryStoreError("memory document text cannot contain null bytes")
    try:
        text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise MemoryStoreError("memory document text must be valid UTF-8") from exc


def _check_destination(
    target: Path,
    normalised: str,
    *,
    overwrite: bool,
    require_existing: bool,
) -> None:
    occupied = target.exists() or _is_link(target)
    if require_existing and not occupied:
        raise MemoryStoreError(f"memory document does not exist: {normalised}")
    if occupied and not target.is_file():
        raise MemoryStoreError(f"memory document is not a regular file: {normalised}")
    if occupied and not overwrite:
        raise MemoryStoreError(
            f"memory document already exists: {normalised}; "
            "pass overwrite=True to replace it"
        )


def _remove_temporary(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        # The primary write error is more useful.  The temporary name starts
        # with a dot and ends in .tmp so a rare cleanup failure is identifiable.
        pass


def _write_document(
    project_root: Path,
    name: str | Path,
    text: str,
    *,
    overwrite: bool,
    require_existing: bool,
) -> str:
    _validate_text(text)
    target, normalised = _document_path(project_root, name)
    _check_destination(
        target,
        normalised,
        overwrite=overwrite,
        require_existing=require_existing,
    )

    memory, _ = _memory_root(project_root)
    try:
        memory.mkdir(parents=True, exist_ok=True)
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise MemoryStoreError(
            f"could not create repository memory directories: {exc}"
        ) from exc

    # Resolve again after directory creation so an existing intermediate link
    # cannot redirect the write outside the memory root.
    target, normalised = _document_path(project_root, normalised)
    _check_destination(
        target,
        normalised,
        overwrite=overwrite,
        require_existing=require_existing,
    )

    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())

        # Recheck both link safety and overwrite policy immediately before the
        # atomic replacement.  os.replace never exposes a partial document.
        target, normalised = _document_path(project_root, normalised)
        _check_destination(
            target,
            normalised,
            overwrite=overwrite,
            require_existing=require_existing,
        )
        os.replace(temporary, target)
        temporary = None
    except MemoryStoreError:
        raise
    except (OSError, UnicodeError) as exc:
        raise MemoryStoreError(
            f"could not write memory document {normalised}: {exc}"
        ) from exc
    finally:
        _remove_temporary(temporary)
    return normalised


def add_document(
    project_root: Path,
    name: str | Path,
    text: str,
    *,
    overwrite: bool = False,
) -> str:
    """Add a document, refusing replacement unless ``overwrite`` is true."""
    return _write_document(
        project_root,
        name,
        text,
        overwrite=overwrite,
        require_existing=False,
    )


def update_document(project_root: Path, name: str | Path, text: str) -> str:
    """Replace an existing document; fail when the named document is missing."""
    return _write_document(
        project_root,
        name,
        text,
        overwrite=True,
        require_existing=True,
    )


def remove_document(project_root: Path, name: str | Path) -> str:
    """Remove exactly one existing memory document and return its name."""
    target, normalised = _document_path(project_root, name)
    if not target.exists():
        raise MemoryStoreError(f"memory document does not exist: {normalised}")
    if not target.is_file():
        raise MemoryStoreError(f"memory document is not a regular file: {normalised}")
    try:
        target.unlink()
    except OSError as exc:
        raise MemoryStoreError(
            f"could not remove memory document {normalised}: {exc}"
        ) from exc
    return normalised
