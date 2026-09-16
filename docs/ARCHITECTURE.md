# Architecture

Code++ is a local-first bridge between a reasoning-oriented Planner and an execution-oriented coding agent. It deliberately has no cloud backend and no browser integration.

```text
Explicit seeds -> bounded context -> CODEPP/1 -> clipboard/file/stdout
                                                   |
                                        user-mediated Planner
                                                   |
Task + baseline <- validation <- CODEPP/1 <- clipboard/file/stdin
        |
drift check -> review -> conservative git apply -> local verification -> finish
```

## Components

- `codepp/core` owns project discovery, explicit and one-hop related context, safe repository-memory CRUD, state containment, and persisted tasks.
- `codepp/security` applies ignore rules, rejects binary/oversized/out-of-project files, and redacts likely secrets.
- `codepp/git` collects repository state, fingerprints the exported Git baseline, and validates safe unified diffs with `git apply --check`.
- `codepp/protocol` renders requests and parses minimally valid responses.
- `codepp/relay` defines the provider boundary and implements only the human-mediated clipboard provider.
- `codepp/cli.py` coordinates the workflow and provides developer-facing errors.

Project state lives under `.codepp/` and is locally excluded from Git during initialization. Task metadata is schema-checked JSON so it remains inspectable and easy to recover. State artifacts use atomic replacement, and persisted artifact references are confined to `.codepp`. Planner-proposed verification commands are saved as text and are never executed by Code++.

Repository memory is intentionally simple: the user maintains small UTF-8 Markdown or text documents under `.codepp/memory` through the `memory` commands, and an export includes them only when `--memory` is present. A separate aggregate budget prevents a directory of notes from silently turning into an oversized context capsule.

Related discovery never crawls recursively. It examines only explicit seeds for local imports and conventional test/source counterparts, then sends candidates through the standard context checks. This gives useful context expansion without silently exporting a repository.
