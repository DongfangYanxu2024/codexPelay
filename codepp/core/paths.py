from pathlib import Path, PurePosixPath, PureWindowsPath


class ProjectNotFoundError(RuntimeError):
    pass


def find_project(start: Path | None = None, *, require_initialized: bool = True) -> Path:
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / ".codepp" / "config.toml").is_file():
            return candidate
    if require_initialized:
        raise ProjectNotFoundError(
            "no Code++ project was found.\n\nRun:\n\n    codepp init"
        )
    return current


def ensure_inside_project(root: Path, requested: str | Path) -> tuple[Path, str]:
    root = root.resolve()
    raw = Path(requested)
    candidate = raw if raw.is_absolute() else root / raw
    resolved = candidate.resolve(strict=False)
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"path is outside the project: {requested}") from exc
    return resolved, relative.as_posix()


def codepp_dir(root: Path) -> Path:
    return safe_codepp_path(root)


def safe_codepp_path(root: Path, *parts: str) -> Path:
    """Return a local state path only when all resolved components stay in-project."""
    try:
        project = root.resolve(strict=True)
        state = project / ".codepp"
        resolved_state = state.resolve(strict=False)
        resolved_state.relative_to(project)
        target = state.joinpath(*parts)
        resolved_target = target.resolve(strict=False)
        resolved_target.relative_to(resolved_state)
    except (OSError, RuntimeError, ValueError) as exc:
        suffix = "/".join(parts)
        label = f".codepp/{suffix}" if suffix else ".codepp"
        raise ValueError(f"unsafe Code++ state path: {label} escapes the project") from exc
    return target


def safe_codepp_reference(root: Path, reference: str) -> Path:
    """Resolve a persisted `.codepp/...` reference without trusting task JSON."""
    if not isinstance(reference, str) or not reference:
        raise ValueError("invalid Code++ artifact reference")
    portable = reference.replace("\\", "/")
    pure = PurePosixPath(portable)
    windows = PureWindowsPath(reference)
    if (
        pure.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or not pure.parts
        or pure.parts[0] != ".codepp"
        or ".." in pure.parts
    ):
        raise ValueError(f"unsafe Code++ artifact reference: {reference}")
    return safe_codepp_path(root, *pure.parts[1:])
