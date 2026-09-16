from dataclasses import dataclass
import re

from ..utils.markdown import parse_markdown_document


PROTOCOL_RE = re.compile(r"(?im)^Protocol:\s*(\S+)\s*$")
TASK_ID_RE = re.compile(r"(?im)^Task-ID:\s*([A-Za-z0-9_-]+)\s*$")


@dataclass(frozen=True)
class ParsedResponse:
    protocol: str
    task_id: str
    sections: dict[str, str]


def parse_response(text: str) -> ParsedResponse:
    metadata, sections = parse_markdown_document(text)
    protocols = PROTOCOL_RE.findall(metadata)
    if not protocols:
        raise ValueError("response is missing Protocol")
    if len(protocols) != 1:
        raise ValueError("response must contain exactly one Protocol")
    if protocols[0] != "CODEPP/1":
        raise ValueError(f"unsupported protocol: {protocols[0]}")
    task_ids = TASK_ID_RE.findall(metadata)
    if not task_ids:
        raise ValueError("response is missing Task-ID")
    if len(task_ids) != 1:
        raise ValueError("response must contain exactly one Task-ID")
    return ParsedResponse("CODEPP/1", task_ids[0], sections)
