from pathlib import Path
import os

import pytest

from codepp.core import memory_store
from codepp.core.memory_store import (
    MemoryStoreError,
    add_document,
    list_documents,
    read_document,
    remove_document,
    update_document,
)


def test_add_read_list_and_remove_documents(tmp_path: Path):
    assert list_documents(tmp_path) == []

    assert add_document(tmp_path, "architecture.md", "Layers: CLI -> core\n") == (
        "architecture.md"
    )
    assert add_document(tmp_path, "notes/commands.txt", "pytest\n") == (
        "notes/commands.txt"
    )
    assert read_document(tmp_path, "architecture.md") == "Layers: CLI -> core\n"
    assert read_document(tmp_path, Path("notes") / "commands.txt") == "pytest\n"

    assert remove_document(tmp_path, "architecture.md") == "architecture.md"
    assert list_documents(tmp_path) == ["notes/commands.txt"]
    assert (tmp_path / ".codepp" / "memory" / "notes").is_dir()


def test_add_refuses_overwrite_unless_requested(tmp_path: Path):
    add_document(tmp_path, "decisions.md", "first\n")

    with pytest.raises(MemoryStoreError, match="already exists.*overwrite=True"):
        add_document(tmp_path, "decisions.md", "second\n")
    assert read_document(tmp_path, "decisions.md") == "first\n"

    assert add_document(
        tmp_path, "decisions.md", "second\n", overwrite=True
    ) == "decisions.md"
    assert read_document(tmp_path, "decisions.md") == "second\n"


def test_update_requires_an_existing_document(tmp_path: Path):
    with pytest.raises(MemoryStoreError, match="does not exist"):
        update_document(tmp_path, "nested/missing.md", "new\n")
    assert not (tmp_path / ".codepp").exists()

    add_document(tmp_path, "existing.md", "old\n")
    assert update_document(tmp_path, "existing.md", "new\n") == "existing.md"
    assert read_document(tmp_path, "existing.md") == "new\n"


@pytest.mark.parametrize("name", ["data.json", "README", "notes.md.exe"])
def test_rejects_unsupported_document_types(tmp_path: Path, name: str):
    with pytest.raises(MemoryStoreError, match=r"\.md or \.txt"):
        add_document(tmp_path, name, "content\n")


def test_rejects_traversal_and_absolute_paths(tmp_path: Path):
    outside = tmp_path.parent / "outside-memory.md"
    attempts = ["../outside-memory.md", "nested/../../outside-memory.md", outside]
    for name in attempts:
        with pytest.raises(MemoryStoreError, match="relative|cannot contain"):
            add_document(tmp_path, name, "do not write\n")
    assert not outside.exists()


def test_rejects_backslash_traversal_on_every_platform(tmp_path: Path):
    with pytest.raises(MemoryStoreError, match="cannot contain"):
        add_document(tmp_path, r"..\outside.md", "do not write\n")


@pytest.mark.parametrize(
    "name",
    [
        "bad:name.md",
        "control\x01.md",
        "delete\x7f.txt",
        "folder./notes.md",
        "folder /notes.md",
        "notes.md.",
        "notes.md ",
        "CON.md",
        "con.notes.txt",
        "nested/PRN.txt",
        "AUX/readme.md",
        "nul.md",
        "COM1.md",
        "com9.extra.txt",
        "LPT1.md",
        "lpt9.notes.txt",
    ],
)
def test_rejects_nonportable_path_parts(tmp_path: Path, name: str):
    with pytest.raises(MemoryStoreError, match="control|dot or space|reserved|':'"):
        add_document(tmp_path, name, "do not write\n")
    assert not (tmp_path / ".codepp").exists()


def test_allows_names_outside_windows_reserved_number_range(tmp_path: Path):
    add_document(tmp_path, "COM10.md", "portable\n")
    add_document(tmp_path, "LPT10.txt", "portable\n")
    assert list_documents(tmp_path) == ["COM10.md", "LPT10.txt"]


def test_rejects_symlink_escape_without_touching_target(tmp_path: Path):
    memory = tmp_path / ".codepp" / "memory"
    memory.mkdir(parents=True)
    outside = tmp_path.parent / "outside-target.md"
    outside.write_text("keep\n", encoding="utf-8")
    link = memory / "escape.md"
    try:
        link.symlink_to(outside)
    except (NotImplementedError, OSError):
        pytest.skip("symbolic links are unavailable on this platform")

    for operation in (
        lambda: read_document(tmp_path, "escape.md"),
        lambda: add_document(tmp_path, "escape.md", "replace\n", overwrite=True),
        lambda: remove_document(tmp_path, "escape.md"),
        lambda: list_documents(tmp_path),
    ):
        with pytest.raises(MemoryStoreError, match="symbolic links"):
            operation()
    assert outside.read_text(encoding="utf-8") == "keep\n"
    assert link.is_symlink()


def test_rejects_symlinked_parent_escape(tmp_path: Path):
    memory = tmp_path / ".codepp" / "memory"
    memory.mkdir(parents=True)
    outside = tmp_path.parent / "outside-memory-directory"
    outside.mkdir()
    link = memory / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip("directory symbolic links are unavailable on this platform")

    with pytest.raises(MemoryStoreError, match="symbolic links"):
        add_document(tmp_path, "linked/secret.md", "do not write\n")
    assert not (outside / "secret.md").exists()


def test_rejects_in_root_file_symlinks_for_all_operations(tmp_path: Path):
    memory = tmp_path / ".codepp" / "memory"
    memory.mkdir(parents=True)
    target = memory / "real.md"
    target.write_text("keep\n", encoding="utf-8")
    link = memory / "alias.md"
    try:
        link.symlink_to(target)
    except (NotImplementedError, OSError):
        pytest.skip("symbolic links are unavailable on this platform")

    for operation in (
        lambda: read_document(tmp_path, "alias.md"),
        lambda: add_document(tmp_path, "alias.md", "replace\n", overwrite=True),
        lambda: update_document(tmp_path, "alias.md", "replace\n"),
        lambda: remove_document(tmp_path, "alias.md"),
        lambda: list_documents(tmp_path),
    ):
        with pytest.raises(MemoryStoreError, match="symbolic links"):
            operation()
    assert target.read_text(encoding="utf-8") == "keep\n"
    assert link.is_symlink()


def test_missing_read_and_remove_are_friendly(tmp_path: Path):
    for operation in (read_document, remove_document):
        with pytest.raises(MemoryStoreError, match="does not exist: missing.md"):
            operation(tmp_path, "missing.md")


def test_listing_is_deterministic_and_nested(tmp_path: Path):
    for name in (
        "nested/Z.md",
        "B.txt",
        "nested/a.txt",
        "a.md",
        "nested/deeper/guide.MD",
    ):
        add_document(tmp_path, name, f"{name}\n")
    (tmp_path / ".codepp" / "memory" / "ignored.json").write_text(
        "{}\n", encoding="utf-8"
    )

    expected = [
        "a.md",
        "B.txt",
        "nested/a.txt",
        "nested/deeper/guide.MD",
        "nested/Z.md",
    ]
    assert list_documents(tmp_path) == expected
    assert list_documents(tmp_path) == expected


def test_read_rejects_non_utf8_and_add_rejects_non_text(tmp_path: Path):
    memory = tmp_path / ".codepp" / "memory"
    memory.mkdir(parents=True)
    (memory / "invalid.txt").write_bytes(b"\xff\xfe")

    with pytest.raises(MemoryStoreError, match="not valid UTF-8"):
        read_document(tmp_path, "invalid.txt")
    with pytest.raises(MemoryStoreError, match="must be a string"):
        add_document(tmp_path, "object.txt", b"bytes")  # type: ignore[arg-type]
    with pytest.raises(MemoryStoreError, match="null bytes"):
        add_document(tmp_path, "null.txt", "before\x00after")


def test_atomic_write_flushes_and_replaces_from_same_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    real_fsync = os.fsync
    real_replace = os.replace
    calls: dict[str, object] = {"fsync": 0}

    def tracking_fsync(descriptor: int) -> None:
        calls["fsync"] = int(calls["fsync"]) + 1
        real_fsync(descriptor)

    def tracking_replace(source: str | Path, destination: str | Path) -> None:
        source_path = Path(source)
        destination_path = Path(destination)
        assert source_path.parent == destination_path.parent
        assert source_path.read_text(encoding="utf-8") == "atomic\n"
        calls["replace"] = (source_path, destination_path)
        real_replace(source, destination)

    monkeypatch.setattr(memory_store.os, "fsync", tracking_fsync)
    monkeypatch.setattr(memory_store.os, "replace", tracking_replace)

    add_document(tmp_path, "atomic.md", "atomic\n")
    target = tmp_path / ".codepp" / "memory" / "atomic.md"
    source, destination = calls["replace"]  # type: ignore[misc]
    assert calls["fsync"] == 1
    assert Path(source).parent == target.parent
    assert Path(source).name.startswith(".atomic.md.")
    assert Path(source).suffix == ".tmp"
    assert destination == target
    assert [path.name for path in target.parent.iterdir()] == ["atomic.md"]


def test_atomic_replace_failure_preserves_original_and_cleans_temporary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    add_document(tmp_path, "stable.md", "original\n")
    target = tmp_path / ".codepp" / "memory" / "stable.md"

    def fail_replace(source: str | Path, destination: str | Path) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(memory_store.os, "replace", fail_replace)
    with pytest.raises(MemoryStoreError, match="simulated replace failure"):
        update_document(tmp_path, "stable.md", "replacement\n")

    assert target.read_text(encoding="utf-8") == "original\n"
    assert [path.name for path in target.parent.iterdir()] == ["stable.md"]
