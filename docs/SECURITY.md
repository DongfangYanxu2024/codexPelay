# Security

Code++ assumes Planner output is untrusted and keeps web relay human-mediated.

## Context protection

- Explicit file paths are resolved and must remain inside the project, including through symlinks.
- Git repositories use Git's own ignore engine, including nested `.gitignore` files and `.git/info/exclude`; `.codeppignore` adds project-specific policy and cannot re-include a Git-ignored path.
- Known binary extensions, null-byte files, non-UTF-8 files, and files over the configured limit are omitted.
- Common assignments, authorization headers, bearer credentials, private-key blocks, and high-confidence provider tokens are replaced by redaction markers.
- Logs contain command/status metadata, not clipboard bodies or file content.
- Repository memory is opt-in, restricted to `.codepp/memory`, limited to `.md`/`.txt`, size-bounded, and secret-redacted.
- Inline and file diagnostics are size-bounded and secret-redacted; diagnostics files must remain inside the project.
- Working-tree and staged diffs both pass ignore filtering and secret redaction before export.
- Related-file discovery is one-hop, explicitly seeded, count/byte bounded, and passed back through the same context checks.
- `.codepp` state paths are containment-checked. Repository-memory links and Windows junctions are rejected; persisted task artifact references cannot escape local state.
- Git initialization locally excludes `.codepp`, reducing the risk of committing requests, responses, patches, or memory with `git add .`.

Secret detection is defense in depth, not a guarantee. Review the generated request before sharing it, and add project-specific sensitive paths to `.codeppignore`.

## Patch protection

Patches require a Git repository and must pass `git apply --check`. Every path-bearing header is inspected. Absolute/drive/ADS paths, traversal, Windows reserved names, `.git/`, `.codepp/`, `.codeppignore`, policy-ignored files, common secret filenames, private-key formats, binary patches, symlinks, and submodules are rejected. Applying requires interactive confirmation unless `--yes` is explicitly supplied.

CODEPP/1 parsing is fence-aware: headings inside code blocks do not become protocol sections, duplicate identity fields/sections are rejected, and dynamic request content uses a fence longer than any fence found in that content. Response size is bounded before parsing.

Each exported Git task records its commit, tracked worktree/index fingerprint, and hashes for included context files. Import marks otherwise-valid patches stale when that baseline changes; validation and application stop until a human reviews the new state and explicitly runs `validate TASK_ID --allow-drift`.

Task, request, response, patch, output-copy, and memory writes use same-directory temporary files followed by atomic replacement. Task metadata is schema-checked before artifact references are trusted.

`patch.auto_apply = true` is rejected. `patch.auto_validate = false` may defer validation, but it never makes a patch ready to apply until `codepp validate` succeeds.

Verification blocks are suggestions only. Code++ never executes them automatically.

## Web boundary

Code++ does not automate ChatGPT Web, extract cookies or sessions, scrape DOM content, send messages, retrieve responses, or use undocumented web endpoints. The user transfers request and response text through the clipboard or explicit file/stdin/stdout paths.
