from __future__ import annotations

import ast
import os
from pathlib import Path
import re
import stat
from typing import Iterable

from ..security.ignore import IgnoreMatcher


_PYTHON_SUFFIXES = (".py", ".pyi")
_TYPESCRIPT_SUFFIXES = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")
_JAVASCRIPT_SUFFIXES = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts")
_JS_LIKE_SUFFIXES = frozenset(_TYPESCRIPT_SUFFIXES)

_JS_STATIC_IMPORT = re.compile(
    r"(?m)(?<![\w$.])(?:import|export)\s+(?:type\s+)?"
    r"(?:[^;\r\n]*?\s+from\s+)?(?P<quote>['\"])"
    r"(?P<path>\.{1,2}/[^'\"\r\n?#]+)(?P=quote)"
)
_JS_CALL_IMPORT = re.compile(
    r"(?m)(?<![\w$.])(?:require|import)\s*\(\s*(?P<quote>['\"])"
    r"(?P<path>\.{1,2}/[^'\"\r\n?#]+)(?P=quote)\s*\)"
)


def discover_related_files(
    root: Path,
    seed_files: list[str],
    config: dict,
    *,
    max_files: int = 12,
) -> list[str]:
    """Return a bounded, one-hop list of project-local files related to seeds.

    Discovery intentionally uses only import declarations in the explicit seed
    files and a finite set of conventional test/source filename counterparts.
    Newly discovered files are never parsed, so this cannot turn into a
    repository crawl.
    """
    if max_files <= 0:
        return []

    project_root = root.resolve()
    security = config["security"]
    matcher = IgnoreMatcher.from_project(
        project_root,
        gitignore=bool(security["respect_gitignore"]),
        codeppignore=bool(security["respect_codeppignore"]),
    )
    maximum = int(config["context"]["max_file_bytes"])

    seed_logical: set[str] = set()
    seed_resolved: set[Path] = set()
    seeds: list[tuple[Path, Path, str]] = []
    processed_seeds: set[Path] = set()

    # First collect every safe seed identity. This prevents one seed from being
    # returned merely because it was imported by an earlier seed.
    for requested in seed_files:
        lexical = _lexical_path(project_root, requested)
        if lexical is None:
            continue
        logical = lexical.relative_to(project_root).as_posix()
        seed_logical.add(logical)
        try:
            resolved = lexical.resolve(strict=True)
            resolved.relative_to(project_root)
        except (OSError, RuntimeError, ValueError):
            continue
        seed_resolved.add(resolved)
        if resolved in processed_seeds:
            continue
        processed_seeds.add(resolved)
        if matcher.ignored(logical) or matcher.ignored(resolved.relative_to(project_root).as_posix()):
            continue
        if not _is_regular_file(resolved) or _file_size(resolved) > maximum:
            continue
        seeds.append((lexical, resolved, logical))

    result: list[str] = []
    seen_resolved: set[Path] = set()

    def offer(candidate: Path) -> None:
        if len(result) >= max_files:
            return
        lexical = _lexical_path(project_root, candidate)
        if lexical is None:
            return
        logical = lexical.relative_to(project_root).as_posix()
        try:
            resolved = lexical.resolve(strict=True)
            canonical = resolved.relative_to(project_root).as_posix()
        except (OSError, RuntimeError, ValueError):
            return
        if (
            logical in seed_logical
            or resolved in seed_resolved
            or resolved in seen_resolved
            or matcher.ignored(logical)
            or matcher.ignored(canonical)
            or not _is_regular_file(resolved)
            or _file_size(resolved) > maximum
        ):
            return
        seen_resolved.add(resolved)
        result.append(logical)

    for lexical, resolved, logical in seeds:
        if len(result) >= max_files:
            break
        suffix = Path(logical).suffix.lower()
        content = _read_bounded_utf8(resolved, maximum)
        if content is not None:
            if suffix in _PYTHON_SUFFIXES:
                for candidate in _python_imports(project_root, lexical, content):
                    offer(candidate)
                    if len(result) >= max_files:
                        break
            elif suffix in _JS_LIKE_SUFFIXES:
                for candidate in _javascript_imports(lexical, suffix, content):
                    offer(candidate)
                    if len(result) >= max_files:
                        break

        if len(result) < max_files:
            for candidate in _counterparts(project_root, lexical, suffix):
                offer(candidate)
                if len(result) >= max_files:
                    break

    return result


def _lexical_path(root: Path, requested: str | Path) -> Path | None:
    raw = Path(requested)
    candidate = raw if raw.is_absolute() else root / raw
    # abspath collapses ``..`` without resolving symlinks. Both this lexical
    # path and the real path are checked by callers so ignore rules cannot be
    # bypassed via an in-project symlink.
    lexical = Path(os.path.abspath(candidate))
    try:
        lexical.relative_to(root)
    except ValueError:
        return None
    return lexical


def _is_regular_file(path: Path) -> bool:
    try:
        return stat.S_ISREG(path.stat().st_mode)
    except OSError:
        return False


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return -1


def _read_bounded_utf8(path: Path, maximum: int) -> str | None:
    """Read at most the size observed from the opened file descriptor."""
    try:
        with path.open("rb") as handle:
            size = os.fstat(handle.fileno()).st_size
            if size < 0 or size > maximum:
                return None
            data = handle.read(size)
    except OSError:
        return None
    if len(data) > maximum or b"\x00" in data:
        return None
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None


def _module_variants(stem: Path, suffixes: tuple[str, ...], indexes: tuple[str, ...]) -> Iterable[Path]:
    yield stem
    if stem.suffix:
        return
    for suffix in suffixes:
        yield stem.with_suffix(suffix)
    for index in indexes:
        yield stem / index


def _find_module(stems: Iterable[Path], suffixes: tuple[str, ...], indexes: tuple[str, ...]) -> Path | None:
    for stem in stems:
        for candidate in _module_variants(stem, suffixes, indexes):
            if _is_regular_file(candidate):
                return candidate
    return None


def _python_roots(root: Path, seed: Path, parts: list[str]) -> list[Path]:
    bases: list[Path] = [root]

    # Detect the import root above a normal Python package. This covers src/
    # layouts without searching the repository.
    package_root = seed.parent
    while package_root != root and (package_root / "__init__.py").is_file():
        package_root = package_root.parent
    if package_root != root:
        bases.append(package_root)

    for name in ("src", "lib"):
        conventional = root / name
        if conventional.is_dir():
            bases.append(conventional)

    # A single-name import can intentionally refer to an adjacent module in
    # simple script-style projects.
    if len(parts) == 1:
        bases.append(seed.parent)

    unique: list[Path] = []
    for base in bases:
        if base not in unique:
            unique.append(base)
    return unique


def _python_module(root: Path, seed: Path, parts: list[str], *, base: Path | None = None) -> Path | None:
    if not parts:
        return None
    roots = [base] if base is not None else _python_roots(root, seed, parts)
    stems = (item.joinpath(*parts) for item in roots)
    return _find_module(stems, _PYTHON_SUFFIXES, ("__init__.py",))


def _python_imports(root: Path, seed: Path, content: str) -> Iterable[Path]:
    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError):
        return

    nodes = sorted(
        (node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))),
        key=lambda node: (node.lineno, node.col_offset),
    )
    for node in nodes:
        if isinstance(node, ast.Import):
            for alias in node.names:
                candidate = _python_module(root, seed, alias.name.split("."))
                if candidate is not None:
                    yield candidate
            continue

        module_parts = node.module.split(".") if node.module else []
        relative_base: Path | None = None
        if node.level:
            relative_base = seed.parent
            for _ in range(node.level - 1):
                relative_base = relative_base.parent

        if module_parts:
            candidate = _python_module(root, seed, module_parts, base=relative_base)
            if candidate is not None:
                yield candidate

        # Imported names can themselves be modules, most notably in
        # ``from . import helper`` and ``from package import helper``.
        for alias in node.names:
            if alias.name == "*":
                continue
            alias_parts = [*module_parts, *alias.name.split(".")]
            candidate = _python_module(root, seed, alias_parts, base=relative_base)
            if candidate is not None:
                yield candidate


def _javascript_imports(seed: Path, suffix: str, content: str) -> Iterable[Path]:
    suffixes = _TYPESCRIPT_SUFFIXES if suffix in {".ts", ".tsx", ".mts", ".cts"} else _JAVASCRIPT_SUFFIXES
    code_positions = _javascript_code_positions(content)
    matches: list[tuple[int, str]] = []
    for pattern in (_JS_STATIC_IMPORT, _JS_CALL_IMPORT):
        for match in pattern.finditer(content):
            if code_positions[match.start()]:
                matches.append((match.start(), match.group("path")))

    seen: set[str] = set()
    for _, specifier in sorted(matches):
        if specifier in seen:
            continue
        seen.add(specifier)
        candidate = _find_module((seed.parent / specifier,), suffixes, tuple(f"index{item}" for item in suffixes))
        if candidate is not None:
            yield candidate


def _javascript_code_positions(content: str) -> bytearray:
    """Mark positions that are JavaScript code rather than comments/strings."""
    positions = bytearray(b"\x01") * len(content)
    index = 0
    state = "code"
    quote = ""
    while index < len(content):
        char = content[index]
        next_char = content[index + 1] if index + 1 < len(content) else ""
        if state == "code":
            if char == "/" and next_char == "/":
                positions[index:index + 2] = b"\x00\x00"
                state = "line-comment"
                index += 2
                continue
            if char == "/" and next_char == "*":
                positions[index:index + 2] = b"\x00\x00"
                state = "block-comment"
                index += 2
                continue
            if char in {"'", '"', "`"}:
                positions[index] = 0
                quote = char
                state = "string"
        elif state == "line-comment":
            positions[index] = 0
            if char in "\r\n":
                positions[index] = 1
                state = "code"
        elif state == "block-comment":
            positions[index] = 0
            if char == "*" and next_char == "/":
                positions[index + 1] = 0
                state = "code"
                index += 2
                continue
        else:
            positions[index] = 0
            if char == "\\":
                if index + 1 < len(content):
                    positions[index + 1] = 0
                index += 2
                continue
            if char == quote:
                state = "code"
        index += 1
    return positions


def _counterparts(root: Path, seed: Path, suffix: str) -> Iterable[Path]:
    if suffix in _PYTHON_SUFFIXES:
        yield from _python_counterparts(root, seed, suffix)
    elif suffix in _JS_LIKE_SUFFIXES:
        yield from _javascript_counterparts(root, seed, suffix)


def _python_counterparts(root: Path, seed: Path, suffix: str) -> Iterable[Path]:
    stem = seed.stem
    relative_parent = seed.parent.relative_to(root)
    if stem.startswith("test_"):
        source_name = f"{stem[5:]}{suffix}"
        yield seed.with_name(source_name)
        yield from _mirrored_sources(root, relative_parent, source_name)
        return
    if stem.endswith("_test"):
        source_name = f"{stem[:-5]}{suffix}"
        yield seed.with_name(source_name)
        yield from _mirrored_sources(root, relative_parent, source_name)
        return

    test_names = (f"test_{stem}{suffix}", f"{stem}_test{suffix}")
    for name in test_names:
        yield seed.with_name(name)
    for test_parent in _mirrored_test_parents(root, relative_parent):
        for name in test_names:
            yield test_parent / name


def _javascript_counterparts(root: Path, seed: Path, suffix: str) -> Iterable[Path]:
    stem = seed.stem
    relative_parent = seed.parent.relative_to(root)
    for marker in (".test", ".spec"):
        if stem.endswith(marker):
            source_stem = stem[: -len(marker)]
            for source_suffix in _source_suffixes_for(suffix):
                yield seed.with_name(f"{source_stem}{source_suffix}")
            if seed.parent.name == "__tests__":
                for source_suffix in _source_suffixes_for(suffix):
                    yield seed.parent.parent / f"{source_stem}{source_suffix}"
            for candidate in _mirrored_sources(root, relative_parent, f"{source_stem}{suffix}"):
                yield candidate
            return

    for marker in (".test", ".spec"):
        yield seed.with_name(f"{stem}{marker}{suffix}")
    for test_parent in _mirrored_test_parents(root, relative_parent):
        for marker in (".test", ".spec"):
            yield test_parent / f"{stem}{marker}{suffix}"


def _source_suffixes_for(suffix: str) -> tuple[str, ...]:
    ordered = _TYPESCRIPT_SUFFIXES if suffix in {".ts", ".tsx", ".mts", ".cts"} else _JAVASCRIPT_SUFFIXES
    return (suffix, *(item for item in ordered if item != suffix))


def _mirrored_test_parents(root: Path, relative_parent: Path) -> Iterable[Path]:
    parts = relative_parent.parts
    if parts and parts[0] in {"src", "lib", "app"}:
        yield root / "tests" / Path(*parts[1:])
    elif not parts or parts[0] not in {"tests", "test", "__tests__"}:
        yield root / "tests" / relative_parent


def _mirrored_sources(root: Path, relative_parent: Path, filename: str) -> Iterable[Path]:
    parts = relative_parent.parts
    if parts and parts[0] in {"tests", "test", "__tests__"}:
        remainder = Path(*parts[1:]) if len(parts) > 1 else Path()
        yield root / remainder / filename
        yield root / "src" / remainder / filename
