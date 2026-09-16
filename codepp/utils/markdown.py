from __future__ import annotations

import re


_HEADING = re.compile(r"^##\s+(.+?)\s*$")
_FENCE = re.compile(r"^\s*(?P<marker>`{3,}|~{3,})(?P<info>[^`~]*)$")


def parse_markdown_document(text: str) -> tuple[str, dict[str, str]]:
    """Return unfenced preamble metadata and fence-aware level-two sections."""
    metadata: list[str] = []
    sections: dict[str, str] = {}
    current_name: str | None = None
    current_lines: list[str] = []
    fence: str | None = None

    def finish_section() -> None:
        nonlocal current_name, current_lines
        if current_name is None:
            return
        if current_name in sections:
            raise ValueError(f"response contains duplicate section: {current_name}")
        sections[current_name] = "\n".join(current_lines).strip()
        current_name = None
        current_lines = []

    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        stripped = line.strip()
        if fence is not None:
            if current_name is not None:
                current_lines.append(line)
            if stripped == fence:
                fence = None
            continue

        opening = _FENCE.match(line)
        if opening:
            fence = opening.group("marker")
            if current_name is not None:
                current_lines.append(line)
            continue

        heading = _HEADING.match(line)
        if heading:
            finish_section()
            current_name = heading.group(1).strip()
            continue

        if current_name is None:
            metadata.append(line)
        else:
            current_lines.append(line)

    finish_section()
    return "\n".join(metadata), sections


def extract_fenced_block(section: str, languages: set[str]) -> str | None:
    """Extract a complete fenced block with an allowed info-string language."""
    lines = section.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    index = 0
    allowed = {language.lower() for language in languages}
    while index < len(lines):
        opening = _FENCE.match(lines[index])
        if not opening:
            index += 1
            continue
        marker = opening.group("marker")
        info = opening.group("info").strip().split(maxsplit=1)
        language = info[0].lower() if info else ""
        end = index + 1
        while end < len(lines) and lines[end].strip() != marker:
            end += 1
        if end >= len(lines):
            return None
        if language in allowed:
            content = "\n".join(lines[index + 1:end]).strip("\n")
            return content + "\n" if content else None
        index = end + 1
    return None
