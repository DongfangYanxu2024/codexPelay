# Command-line reference

Run commands inside an initialized project or one of its subdirectories.

## `codepp init [PATH]`

Initializes the Git repository containing `PATH`, or `PATH` itself when it is not a repository. Existing configuration and ignore files are preserved.

For Git repositories, initialization also adds `/.codepp/` to the repository-local `.git/info/exclude`. It does not edit the shared `.gitignore`.

## `codepp doctor`

Checks Python, Git, clipboard availability, configuration validity, and `.codepp` writability. A missing clipboard backend is reported as a warning because file/manual relay remains possible.

## `codepp export`

```text
codepp export TASK
  [--files FILE ...]
  [--related] [--related-limit N]
  [--memory [NAME ...]]
  [--diagnostics TEXT | --diagnostics-file FILE]
  [--staged]
  [--no-diff]
  [--copy | --no-copy]
  [--stdout]
  [--output PATH [--force-output]]
```

Builds and saves a request. Clipboard copy is the default. `--no-copy` supports headless workflows. `--stdout` (and the compatibility alias `--print`) emits only the request on stdout, sends notices to stderr, and never touches the clipboard. `--output -` has the same streaming behavior. `--output PATH` writes an additional exact copy inside the project; it is atomic and refuses overwrite unless `--force-output` is present.

`--related` discovers a bounded, deterministic, one-hop set of local Python imports, JavaScript/TypeScript relative imports, and conventional test/source counterparts. It requires one or more explicit `--files` seeds. `--related-limit N` enables discovery and overrides `context.max_related_files`; the aggregate is also limited by `context.max_related_bytes`. Every discovered file still passes containment, ignore, type, size, encoding, and redaction checks.

`--memory` includes UTF-8 `.md` and `.txt` documents from `.codepp/memory`. With no names it includes every supported memory document; with names it includes only those documents. Inclusion is bounded by `context.max_file_bytes` per file and `context.max_memory_bytes` in total.

`--diagnostics` includes redacted inline diagnostics. `--diagnostics-file` reads a project-contained file through the normal ignore, binary, size, encoding, and redaction checks. `--staged` adds the staged Git diff as a separate request section. The working-tree diff remains controlled by `--no-diff` and configuration.

## `codepp import [--file RESPONSE.md | --stdin]`

Imports from the clipboard by default. `--file` and `--stdin` support scripting and headless sessions. Input is capped by `protocol.max_response_bytes`. The raw response and any patch are saved before validation. When `patch.auto_validate` is false, use `codepp validate TASK_ID` explicitly.

## Inspection

- `codepp status [TASK_ID]` shows the latest or selected workflow state.
- `codepp list [--limit N]` lists recent tasks.
- `codepp show [TASK_ID] [--request|--response|--patch]` defaults to the latest task.
- `codepp validate TASK_ID [--allow-drift]` revalidates protocol linkage and any patch. If the exported commit, tracked worktree/index, or explicit context changed, validation stops. `--allow-drift` explicitly records the reviewed current baseline before retrying validation.

Read-only commands may default to the latest task. `validate`, `apply`, and `finish` require a concrete task ID or the literal `latest` so scripts do not mutate an accidental task.

## `codepp apply TASK_ID [--yes]`

Rechecks repository drift and the patch, displays all target files and current workspace status, asks for confirmation, and applies it through Git. It never runs the response's verification commands.

## `codepp finish TASK_ID`

```text
codepp finish TASK_ID [--note TEXT]
codepp finish TASK_ID --manual --note TEXT [--yes]
codepp finish TASK_ID --failed --note REASON
```

Records a terminal result without claiming that verification was automated. Applied tasks can be finished normally. A validated or ready task requires the explicit `--manual` mode and a verification note. Failure always requires a reason. Completed and failed tasks remain terminal.

## Repository memory

```text
codepp memory list
codepp memory show NAME
codepp memory add NAME (--text TEXT | --file PATH | --stdin) [--force]
codepp memory update NAME (--text TEXT | --file PATH | --stdin)
codepp memory remove NAME [--yes]
```

Names must be portable relative `.md` or `.txt` paths under `.codepp/memory`. Writes are atomic, links/junctions are rejected, per-document limits are enforced, and suspected secrets produce a warning while the local source remains unchanged. Export-time redaction still applies.

## `codepp clean [--yes]`

Removes cache and log files only. Tasks, inbox, outbox, memory, configuration, and ignore rules are preserved.
