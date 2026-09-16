from pathlib import Path

import pytest

from codepp.git.patch import extract_patch, patch_files, validate_patch


VALID_PATCH = """diff --git a/app.py b/app.py
index d43e89d..7f8a624 100644
--- a/app.py
+++ b/app.py
@@ -1 +1 @@
-print("old")
+print("new")
"""


def response_for(patch: str) -> str:
    return f"""# CODEPP RESPONSE

Protocol: CODEPP/1
Task-ID: task-1

## Patch

```diff
{patch}```

## Verification

```bash
pytest
```
"""


def test_extracts_patch_only_from_patch_section():
    assert extract_patch(response_for(VALID_PATCH)) == VALID_PATCH
    assert patch_files(VALID_PATCH) == ("app.py",)


def test_validates_patch(git_repo: Path):
    result = validate_patch(git_repo, VALID_PATCH)
    assert result.valid
    assert result.files == ("app.py",)


def test_validates_lf_patch_against_lf_worktree(git_repo: Path):
    (git_repo / "app.py").write_bytes(b'print("old")\n')
    result = validate_patch(git_repo, VALID_PATCH)
    assert result.valid


def test_rejects_invalid_patch(git_repo: Path):
    result = validate_patch(git_repo, VALID_PATCH.replace('print("old")', 'print("missing")'))
    assert not result.valid
    assert result.error


def test_rejects_protected_and_sensitive_targets(git_repo: Path):
    for target in (".codepp/config.toml", ".git/config", ".env", "keys/private.pem", "../outside.py"):
        patch = f"diff --git a/{target} b/{target}\n--- a/{target}\n+++ b/{target}\n@@ -0,0 +1 @@\n+x\n"
        result = validate_patch(git_repo, patch)
        assert not result.valid
        assert "unsafe patch target" in result.error


def test_rejects_rename_from_sensitive_source(git_repo: Path):
    patch = """diff --git a/.env b/public.txt
similarity index 100%
rename from .env
rename to public.txt
"""
    result = validate_patch(git_repo, patch)
    assert not result.valid
    assert ".env" in result.error


def test_extracts_patch_containing_markdown_fence():
    patch = """diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -0,0 +1,3 @@
+```python
+print('ok')
+```
"""
    response = f"""Protocol: CODEPP/1
Task-ID: task-1

## Patch

````diff
{patch}````
"""
    assert extract_patch(response) == patch


def test_rejects_policy_ignored_and_protected_patch_targets(git_repo: Path):
    (git_repo / ".codeppignore").write_text("private/\n", encoding="utf-8")
    for target in ("private/config.yml", ".codeppignore", ".npmrc", "C:/secret.txt", "file.txt:stream"):
        patch = f"diff --git a/{target} b/{target}\n--- a/{target}\n+++ b/{target}\n@@ -0,0 +1 @@\n+x\n"
        result = validate_patch(git_repo, patch)
        assert not result.valid, target
        assert "unsafe patch target" in result.error


@pytest.mark.parametrize(
    "marker,error",
    [
        ("GIT binary patch\nliteral 1\nA", "binary"),
        ("new file mode 120000", "symlink"),
        ("new file mode 160000", "submodule"),
        ("index 1111111..2222222 120000", "symlink"),
        ("index 1111111..2222222 160000", "submodule"),
    ],
)
def test_rejects_non_text_patch_kinds(git_repo: Path, marker: str, error: str):
    patch = f"diff --git a/link b/link\n{marker}\n--- /dev/null\n+++ b/link\n@@ -0,0 +1 @@\n+x\n"
    result = validate_patch(git_repo, patch)
    assert not result.valid
    assert error in result.error


def test_scans_all_path_bearing_headers(git_repo: Path):
    patch = """diff --git a/safe.txt b/safe.txt
--- a/safe.txt
+++ b/.envrc
@@ -0,0 +1 @@
+x
"""
    result = validate_patch(git_repo, patch)
    assert not result.valid
    assert ".envrc" in result.error
