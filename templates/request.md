# CODEPP REQUEST

Protocol: CODEPP/1
Task-ID: {{ task_id }}

## Task

{{ task }}

## Project

{{ project }}

## Repository State

{{ repository_state }}

## Relevant Files

{{ relevant_files }}

## Repository Memory

{{ repository_memory }}

## Current Diff

```diff
{{ current_diff }}
```

## Staged Diff

```diff
{{ staged_diff }}
```

## Error / Diagnostics

```text
{{ diagnostics }}
```

## Requirements

Analyze root cause, implementation plan, files, unified diff, verification, risks, and assumptions.

## Executor Contract

Validate against the real repository. Prefer minimal changes and a unified diff. Finish with a concise `Codex Instruction`.
