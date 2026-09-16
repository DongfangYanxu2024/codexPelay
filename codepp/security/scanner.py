from pathlib import Path


BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".zip", ".7z",
    ".tar", ".gz", ".exe", ".dll", ".so", ".dylib", ".pdf", ".docx",
    ".xlsx", ".pptx", ".pyc", ".class",
}


def is_binary_path(path: Path) -> bool:
    return path.suffix.lower() in BINARY_EXTENSIONS


def contains_null_byte(path: Path, sample_size: int = 8192) -> bool:
    with path.open("rb") as handle:
        return b"\x00" in handle.read(sample_size)
