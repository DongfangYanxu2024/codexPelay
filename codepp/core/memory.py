from pathlib import Path

from ..security.redact import redact_secrets
from .context import ContextFile
from .memory_store import MemoryStoreError, list_documents, read_document


def collect_memory(root: Path, requested: list[str] | None, config: dict) -> list[ContextFile]:
    """Collect opt-in, size-bounded repository memory documents."""
    names = requested if requested else list_documents(root)
    maximum_file = int(config["context"]["max_file_bytes"])
    remaining = int(config["context"]["max_memory_bytes"])
    redact = bool(config["security"]["redact_secrets"])
    result: list[ContextFile] = []
    seen: set[str] = set()
    for name in names:
        label = f"memory/{name}"
        try:
            content = read_document(root, name)
        except MemoryStoreError as exc:
            result.append(ContextFile(label, f"[MEMORY OMITTED: {exc}]", True))
            continue
        normalized = str(name).replace("\\", "/")
        label = f"memory/{normalized}"
        if normalized in seen:
            continue
        seen.add(normalized)
        size = len(content.encode("utf-8"))
        if size > maximum_file:
            result.append(ContextFile(label, f"[MEMORY OMITTED: exceeds {maximum_file} bytes]", True))
        elif size > remaining:
            result.append(ContextFile(label, "[MEMORY OMITTED: total memory budget exceeded]", True))
        else:
            redactions = 0
            if redact:
                content, redactions = redact_secrets(content)
            remaining -= size
            result.append(ContextFile(label, content, redactions=redactions))
    return result
