# Changelog

## 0.3.0 - 2026-09-16

- Added bounded one-hop related-file discovery for Python and JavaScript/TypeScript imports plus conventional test/source counterparts.
- Added safe repository-memory CRUD commands with portable names, atomic writes, secret warnings, and link/junction defenses.
- Added pure `--stdout` export, exact `--output` copies, overwrite protection, and backward-compatible `--print` behavior.
- Added deterministic `latest` selection, explicit terminal `finish` modes, completion notes, and microsecond task ordering.
- Added exported Git/context baselines, stale-patch detection, explicit `--allow-drift` rebaselining, and apply-time drift checks.
- Added fence-aware protocol and patch parsing, duplicate-field rejection, dynamic Markdown fences, and configurable response-size limits.
- Hardened patch targets against project policy, binary/symlink/submodule changes, Windows path hazards, protected policy files, and additional secret filenames.
- Upgraded ignore handling to Git-native nested rules and local excludes; initialization now keeps `.codepp` out of `git add .` without changing shared `.gitignore`.
- Expanded redaction for quoted/multiword assignments, authorization headers, PEM private keys, and high-confidence provider tokens.
- Made local state writes atomic and tightened configuration/task schema, artifact-reference, Git failure, and state-directory validation.

## 0.2.0 - 2026-09-16

- Added opt-in repository memory with selected/all modes, UTF-8 type checks, per-file limits, aggregate budgeting, path containment, and secret redaction.
- Added inline and file-based diagnostics with the normal context safety checks.
- Added optional staged Git diff collection with ignore filtering and redaction.
- Added response import from standard input for headless and pipeline workflows.
- Added backward-compatible task metadata for included memory documents.
- Hardened configuration type validation and explicitly rejected automatic patch application.
- Made `patch.auto_validate = false` defer validation until `codepp validate` is run.
- Expanded Windows, configuration, memory, diagnostics, staged-diff, and CLI integration tests.

## 0.1.0 - 2026-09-15

- Added the Python CLI and local `.codepp` project state.
- Added CODEPP/1 request generation and tolerant response parsing.
- Added explicit context collection, ignore handling, binary/size checks, and secret redaction.
- Added human-mediated clipboard relay and file-based scripting alternatives.
- Added Git metadata, patch extraction, safety validation, and conservative application.
- Added the Code++ relay skill, documentation, unit tests, and end-to-end integration coverage.
