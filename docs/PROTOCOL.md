# CODEPP/1 Protocol

CODEPP/1 uses Markdown so a human can inspect and transfer every handoff.

## Request

A request begins with `# CODEPP REQUEST` and includes:

```text
Protocol: CODEPP/1
Task-ID: <id>
```

It then carries the task, concise project and Git metadata, explicitly selected files, the current diff, optional diagnostics, requirements, and the executor contract. Version 0.3 exports may also contain bounded related files, `## Repository Memory`, and `## Staged Diff`; these remain backward-compatible CODEPP/1 content. Omitted, ignored, binary, oversized, and unreadable files are represented by an omission marker rather than silently disappearing.

All dynamic code blocks choose a Markdown fence longer than fences found in their content, so a diff or diagnostic containing triple backticks cannot truncate the request.

## Response

A response must contain only two machine-required fields:

```text
Protocol: CODEPP/1
Task-ID: <existing task id>
```

The parser optionally recognizes `Diagnosis`, `Assumptions`, `Plan`, `Files`, `Patch`, `Verification`, `Risks`, and `Codex Instruction` level-two headings. A unified diff is extracted only from a complete fenced block inside `## Patch`. Headings inside fences are content, not sections.

Unknown or missing optional sections are tolerated. Duplicate sections, duplicate identity fields, oversized responses, a wrong protocol, missing task ID, unknown task, invalid task state, unsafe patch target, stale repository baseline, or patch that fails `git apply --check` is rejected or recorded as invalid.
