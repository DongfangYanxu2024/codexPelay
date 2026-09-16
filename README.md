# Code++ / CodexRelay

Current version: **0.3.0**

Code++ is a local-first reasoning orchestration layer for AI coding agents. It separates thinking from execution: a Planner can analyze, design, review, and propose a diff, while an executor inspects the real repository, validates assumptions, edits, runs tests, and verifies the result.

The clipboard relay is intentionally human-in-the-loop. Code++ never automates ChatGPT Web.

## Why it exists

Complex coding work often repeats expensive repository understanding and design reasoning. Code++ packages a minimal, inspectable Context Capsule containing a task, explicitly selected files, concise project metadata, Git status, and the current diff. It then tracks the returned response and validates any proposed patch locally.

## Architecture

```text
Repository -> minimal context -> CODEPP/1 -> clipboard -> user -> Planner
Repository <- validated patch <- CODEPP/1 <- clipboard <- user <- Planner
```

All state remains in `.codepp/`. See [Architecture](docs/ARCHITECTURE.md), [Protocol](docs/PROTOCOL.md), and [Security](docs/SECURITY.md).

## Install

Python 3.11 or newer and Git are recommended.

```bash
python -m pip install -e .
```

For development:

```bash
python -m pip install -e ".[test]"
pytest
```

## Quick start

From the project you want to work on:

```bash
codepp init
codepp export "Fix duplicate login request" --files src/Login.tsx --related
```

Paste the clipboard content into your Planner chat. When it replies, copy the complete CODEPP/1 response and run:

```bash
codepp import
codepp status
```

Then ask the local coding executor to inspect the latest Code++ task, validate it against the repository, implement or apply only supported changes, and run appropriate tests. You can inspect and apply a valid patch directly:

```bash
codepp show TASK_ID --patch
codepp validate TASK_ID
codepp apply TASK_ID
codepp finish TASK_ID --note "pytest passed"
```

## CLI

Code++ provides `init`, `doctor`, `export`, `import`, `status`, `show`, `list`, `validate`, `apply`, `finish`, `memory`, and `clean`. See the [CLI reference](docs/CLI.md) for options and behavior.

## Context and protocol

Only files passed with `--files` are included. They must resolve inside the project and pass ignore, type, size, encoding, and redaction checks. Requests and responses use inspectable CODEPP/1 Markdown. Optional response sections may be omitted; `Protocol` and `Task-ID` are required.

Version 0.3 can discover a small, deterministic set of one-hop imports and test counterparts. Discovery is seeded by explicit files, reuses the normal ignore/redaction pipeline, and is bounded by file-count and byte budgets:

```bash
codepp export "Plan the refactor" --files src/api.py --related --related-limit 8
```

Repository memory, staged changes, and diagnostics remain opt-in:

```bash
codepp export "Plan the refactor" --files src/api.py --memory architecture.md decisions.md --staged --diagnostics-file logs/failure.log
```

With `--memory` and no names, Code++ includes all `.md` and `.txt` files under `.codepp/memory/`, subject to per-file and total memory budgets. Inline diagnostics use `--diagnostics`. Both memory and diagnostics are secret-redacted before export.

Maintain those notes without editing state files by hand:

```bash
codepp memory add architecture.md --file docs/ARCHITECTURE.md
codepp memory update decisions.md --stdin
codepp memory list
codepp memory show architecture.md
codepp memory remove obsolete.md
```

For scripts and terminals, `--stdout` emits only the request and skips the clipboard. `--output PATH` writes an additional exact, atomic copy inside the project and refuses accidental overwrite unless `--force-output` is supplied.

`status` and `show` default to the latest task; state-changing commands require an explicit task ID or the literal `latest`. Code++ records the exported Git/context baseline and blocks stale validation or application until reviewed drift is explicitly accepted with `validate TASK_ID --allow-drift`.

## Codex Skill

[`skill/codepp-relay/SKILL.md`](skill/codepp-relay/SKILL.md) teaches Codex when to relay reasoning-heavy work and how to preserve the human/web and Planner/executor trust boundaries. Install or link that directory through your normal Codex skill workflow if you want automatic discovery.

## Security

Planner responses, patches, and shell suggestions are untrusted. Code++ redacts common secret assignments, honors `.gitignore` and `.codeppignore`, blocks paths outside the repository, rejects protected/sensitive patch targets, and runs `git apply --check` before applying. Review generated requests and patches yourself; heuristic redaction cannot guarantee secret detection.

## Limitations

- Related-file discovery is deliberately one-hop and heuristic; there is no full import graph, symbol search, embedding, or vector database.
- Clipboard availability depends on the local OS/session. File/stdin import and stdout/file export remain available.
- Secret detection and ignore matching cover common cases but are not a substitute for review.
- Only unified diffs are machine-validated/applied. Verification commands are never run automatically.
- Repository memory supports UTF-8 Markdown and text files only and is never included unless `--memory` is used.
- There is no GUI, VS Code extension, cloud backend, telemetry, account system, or web automation.

## Trust boundary

The Planner never gets authority over the repository. Patches are parsed fence-safely, screened against protected and ignored paths, checked with Git, and rechecked against repository drift before application. Future relay providers must use documented, authorized APIs; browser automation remains out of scope.

## License

MIT. See [LICENSE](LICENSE).
