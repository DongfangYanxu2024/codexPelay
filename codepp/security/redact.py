import re


_ASSIGNMENT = re.compile(
    r"""(?ix)
    (?P<prefix>
        [\"']?(?:[A-Za-z0-9]+_)*
        (?:api[_-]?key|apikey|secret|password|passwd|token|private_key|
           aws_access_key_id|aws_secret_access_key)
        [\"']?\s*[:=]\s*
    )
    (?:
        \"(?P<double>[^\"\r\n]*)\" |
        '(?P<single>[^'\r\n]*)' |
        (?P<bare>[^\r\n,;#]+)
    )
    """
)
_AUTHORIZATION = re.compile(r"(?im)(\bauthorization\s*:\s*)([^\r\n]+)")
_BEARER = re.compile(r"(?i)(\bbearer\s+)([A-Za-z0-9._~+/=-]{6,})")
_PRIVATE_KEY = re.compile(
    r"(?is)-----BEGIN (?P<kind>(?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY)-----.*?"
    r"-----END (?P=kind)-----"
)
_HIGH_CONFIDENCE_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_-])(?:"
    r"sk-(?:proj-)?[A-Za-z0-9_-]{16,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|"
    r"gh[pousr]_[A-Za-z0-9]{20,}|"
    r"xox[baprs]-[A-Za-z0-9-]{16,}|"
    r"AKIA[0-9A-Z]{16}"
    r")(?![A-Za-z0-9_-])"
)


def redact_secrets(text: str) -> tuple[str, int]:
    count = 0

    def private_key(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return "[REDACTED PRIVATE KEY]"

    def assignment(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        if match.group("double") is not None:
            replacement = '\"[REDACTED]\"'
        elif match.group("single") is not None:
            replacement = "'[REDACTED]'"
        else:
            replacement = "[REDACTED]"
        return f"{match.group('prefix')}{replacement}"

    def value(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return f"{match.group(1)}[REDACTED]"

    def token(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return "[REDACTED]"

    result = _PRIVATE_KEY.sub(private_key, text)
    result = _ASSIGNMENT.sub(assignment, result)
    result = _AUTHORIZATION.sub(value, result)
    result = _BEARER.sub(value, result)
    result = _HIGH_CONFIDENCE_TOKEN.sub(token, result)
    return result, count
