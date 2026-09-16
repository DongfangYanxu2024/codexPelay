import pytest

from codepp.core.context import ContextFile
from codepp.git.diff import RepositoryState
from codepp.protocol.parser import parse_response
from codepp.protocol.request import build_request


def test_builds_valid_request():
    request = build_request(
        "20260914-191055-a7f3", "Fix it", {"Name": "demo"},
        [ContextFile("app.py", "print('ok')")], RepositoryState(True, "main", " M app.py", ""),
    )
    assert "# CODEPP REQUEST" in request
    assert "Protocol: CODEPP/1" in request
    assert "Task-ID: 20260914-191055-a7f3" in request
    assert "### app.py" in request


def test_parses_response_sections():
    response = """# CODEPP RESPONSE

Protocol: CODEPP/1
Task-ID: abc-123

## Diagnosis

Cause.

## Plan

Do it.
"""
    parsed = parse_response(response)
    assert parsed.task_id == "abc-123"
    assert parsed.sections["Diagnosis"] == "Cause."
    assert parsed.sections["Plan"] == "Do it."


@pytest.mark.parametrize(
    "text,error",
    [
        ("Task-ID: abc", "missing Protocol"),
        ("Protocol: CODEPP/2\nTask-ID: abc", "unsupported protocol"),
        ("Protocol: CODEPP/1", "missing Task-ID"),
    ],
)
def test_rejects_invalid_response(text: str, error: str):
    with pytest.raises(ValueError, match=error):
        parse_response(text)


def test_section_parser_ignores_headings_inside_fences():
    response = """# CODEPP RESPONSE
Protocol: CODEPP/1
Task-ID: task-1

## Diagnosis

```markdown
## Patch
Protocol: CODEPP/9
Task-ID: fake
```

Still diagnosis.

## Plan

Real plan.
"""
    parsed = parse_response(response)
    assert parsed.task_id == "task-1"
    assert "## Patch" in parsed.sections["Diagnosis"]
    assert parsed.sections["Plan"] == "Real plan."
    assert "Patch" not in parsed.sections


@pytest.mark.parametrize(
    "field",
    [
        "Protocol: CODEPP/1\nProtocol: CODEPP/1\nTask-ID: task-1",
        "Protocol: CODEPP/1\nTask-ID: task-1\nTask-ID: task-2",
    ],
)
def test_rejects_duplicate_protocol_identity(field: str):
    with pytest.raises(ValueError, match="exactly one"):
        parse_response(field)


def test_rejects_duplicate_sections():
    text = "Protocol: CODEPP/1\nTask-ID: task-1\n\n## Plan\nOne\n## Plan\nTwo\n"
    with pytest.raises(ValueError, match="duplicate section"):
        parse_response(text)


def test_request_uses_safe_dynamic_fences():
    request = build_request(
        "task-1",
        "Analyze",
        {"Name": "demo"},
        [],
        RepositoryState(True, "main", "M README.md", "+```python\n+print('x')", ""),
        diagnostics="trace contains ``` marker",
    )
    assert "````diff\n+```python" in request
    assert "````text\ntrace contains ``` marker\n````" in request
