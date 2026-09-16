from pathlib import Path

from codepp.config import DEFAULT_CONFIG, initialize_config
from codepp.core.context import collect_files, sanitize_diagnostics, sanitize_diff


def config_with_limit(limit: int = 200000) -> dict:
    config = {key: value.copy() for key, value in DEFAULT_CONFIG.items()}
    config["context"]["max_file_bytes"] = limit
    return config


def test_reads_and_redacts_file(tmp_path: Path):
    initialize_config(tmp_path)
    (tmp_path / "app.py").write_text("API_KEY=secret-value\nprint('ok')\n", encoding="utf-8")
    item = collect_files(tmp_path, ["app.py"], config_with_limit())[0]
    assert not item.omitted
    assert "secret-value" not in item.content
    assert item.redactions == 1


def test_missing_large_binary_and_ignored(tmp_path: Path):
    initialize_config(tmp_path)
    (tmp_path / "large.txt").write_text("x" * 20, encoding="utf-8")
    (tmp_path / "image.bin").write_bytes(b"abc\x00def")
    (tmp_path / "private").mkdir()
    (tmp_path / "private" / "notes.txt").write_text("nope", encoding="utf-8")
    items = collect_files(tmp_path, ["missing.py", "large.txt", "image.bin", "private/notes.txt"], config_with_limit(10))
    assert all(item.omitted for item in items)
    assert "does not exist" in items[0].content
    assert "exceeds" in items[1].content
    assert "binary" in items[2].content
    assert "ignored" in items[3].content


def test_rejects_path_outside_project(tmp_path: Path):
    initialize_config(tmp_path)
    item = collect_files(tmp_path, ["../outside.txt"], config_with_limit())[0]
    assert item.omitted
    assert "outside the project" in item.content


def test_deduplicates_files(tmp_path: Path):
    initialize_config(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    assert len(collect_files(tmp_path, ["a.py", "./a.py"], config_with_limit())) == 1


def test_sanitizes_outbound_git_diff(tmp_path: Path):
    initialize_config(tmp_path)
    diff = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -0,0 +1 @@
+API_KEY=visible-secret
diff --git a/.env b/.env
--- a/.env
+++ b/.env
@@ -0,0 +1 @@
+UNLABELED_VALUE
"""
    cleaned, redactions, omitted = sanitize_diff(tmp_path, diff, config_with_limit())
    assert "visible-secret" not in cleaned
    assert ".env" not in cleaned
    assert "UNLABELED_VALUE" not in cleaned
    assert redactions == 1
    assert omitted == 1


def test_sanitizes_and_bounds_diagnostics():
    config = config_with_limit(30)
    cleaned, redactions = sanitize_diagnostics("password=private-value", config)
    assert "private-value" not in cleaned
    assert redactions == 1
    omitted, _ = sanitize_diagnostics("x" * 31, config)
    assert "DIAGNOSTICS OMITTED" in omitted
