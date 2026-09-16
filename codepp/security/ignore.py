from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath

from ..git.repo import is_git_repository, run_git


@dataclass(frozen=True)
class IgnoreRule:
    pattern: str
    negate: bool = False


def parse_rules(text: str) -> list[IgnoreRule]:
    rules: list[IgnoreRule] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        negate = line.startswith("!")
        if negate:
            line = line[1:]
        if line:
            rules.append(IgnoreRule(line.replace("\\", "/"), negate))
    return rules


def _matches(relative: str, pattern: str) -> bool:
    relative = relative.strip("/")
    directory_only = pattern.endswith("/")
    pattern = pattern.rstrip("/")
    anchored = pattern.startswith("/")
    pattern = pattern.lstrip("/")
    if not pattern:
        return False
    parts = relative.split("/")
    if directory_only:
        directories = parts[:-1] if "." in parts[-1] else parts
        candidates = ["/".join(directories[:index]) for index in range(1, len(directories) + 1)]
        if anchored:
            return any(fnmatch(candidate, pattern) for candidate in candidates)
        return any(fnmatch(candidate, pattern) or fnmatch(candidate.split("/")[-1], pattern) for candidate in candidates)
    if anchored or "/" in pattern:
        return PurePosixPath(relative).match(pattern) or fnmatch(relative, pattern)
    return any(fnmatch(part, pattern) for part in parts)


def _evaluate_rules(relative: str, rules: list[IgnoreRule]) -> bool:
    ignored = False
    for rule in rules:
        if _matches(relative, rule.pattern):
            ignored = not rule.negate
    return ignored


class IgnoreMatcher:
    def __init__(
        self,
        rules: list[IgnoreRule],
        *,
        git_root: Path | None = None,
        git_rules: list[IgnoreRule] | None = None,
    ):
        self.rules = rules
        self.git_root = git_root
        self.git_rules = git_rules or []

    def ignored(self, relative: str) -> bool:
        git_ignored = False
        if self.git_root is not None:
            result = run_git(
                self.git_root,
                ["check-ignore", "--no-index", "-q", "--", relative.replace("\\", "/")],
            )
            if result.returncode not in {0, 1}:
                raise ValueError(
                    f"git ignore check failed: {result.stderr.strip() or 'unknown error'}"
                )
            git_ignored = result.returncode == 0
        else:
            git_ignored = _evaluate_rules(relative, self.git_rules)

        # Project policy may narrow or negate its own earlier rules, but it
        # must never make a path visible when Git already considers it
        # ignored. Respecting both sources is a union of their protections.
        return git_ignored or _evaluate_rules(relative, self.rules)

    @classmethod
    def from_project(cls, root: Path, *, gitignore: bool = True, codeppignore: bool = True) -> "IgnoreMatcher":
        git_rules: list[IgnoreRule] = []
        codepp_rules: list[IgnoreRule] = []
        git_root = root if gitignore and is_git_repository(root) else None
        for enabled, name, destination in (
            (gitignore and git_root is None, ".gitignore", git_rules),
            (codeppignore, ".codeppignore", codepp_rules),
        ):
            path = root / name
            if enabled and path.is_file():
                try:
                    destination.extend(parse_rules(path.read_text(encoding="utf-8-sig")))
                except (OSError, UnicodeDecodeError):
                    continue
        return cls(codepp_rules, git_root=git_root, git_rules=git_rules)
