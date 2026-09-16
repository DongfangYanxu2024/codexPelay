from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import platform
import sys
import tempfile

from . import __version__
from .config import initialize_config, load_config
from .core.context import (
    ContextFile,
    collect_files,
    fingerprint_files,
    sanitize_diagnostics,
    sanitize_diff,
)
from .core.memory import collect_memory
from .core.memory_store import (
    add_document,
    list_documents,
    read_document,
    remove_document,
    update_document,
)
from .core.related import discover_related_files
from .core.paths import (
    ProjectNotFoundError,
    ensure_inside_project,
    find_project,
    safe_codepp_path,
    safe_codepp_reference,
)
from .core.project import detect_metadata, initialization_root
from .core.task import Task, list_tasks, load_task
from .git.diff import RepositoryState, collect_repository_state, repository_fingerprint
from .git.patch import apply_patch as apply_git_patch
from .git.patch import extract_patch, validate_patch
from .git.repo import ensure_codepp_excluded, git_available, is_git_repository, run_git
from .protocol.parser import parse_response
from .protocol.request import build_request
from .relay.clipboard import ClipboardError, ClipboardProvider
from .security.redact import redact_secrets
from .utils.encoding import read_text, write_text
from .utils.logging import log_event


class CommandError(RuntimeError):
    pass


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _root() -> Path:
    try:
        return find_project()
    except ProjectNotFoundError as exc:
        raise CommandError(str(exc)) from exc


def _latest_task(root: Path) -> Task:
    tasks = list_tasks(root)
    if not tasks:
        raise CommandError("no Code++ tasks exist yet.\n\nRun:\n\n    codepp export \"your task\"")
    return tasks[0]


def _select_task(root: Path, task_id: str | None) -> Task:
    return _latest_task(root) if not task_id or task_id.lower() == "latest" else load_task(root, task_id)


def _read_patch(root: Path, task: Task) -> str:
    if not task.patch_file:
        raise CommandError(f"task {task.task_id} does not contain a patch")
    path = safe_codepp_reference(root, task.patch_file)
    if not path.is_file():
        raise CommandError(f"patch file is missing for task {task.task_id}")
    return read_text(path)


def _task_drift(root: Path, task: Task) -> list[str]:
    drift: list[str] = []
    if task.repository_head:
        current = collect_repository_state(root, include_diff=False, include_status=False).head
        if current != task.repository_head:
            drift.append(f"Git HEAD changed ({task.repository_head} -> {current})")
    if task.context_hashes:
        current_hashes = fingerprint_files(root, list(task.context_hashes))
        changed = sorted(
            name for name, digest in task.context_hashes.items() if current_hashes.get(name) != digest
        )
        if changed:
            drift.append("context files changed: " + ", ".join(changed))
    if task.repository_fingerprint:
        current_fingerprint = repository_fingerprint(root)
        if current_fingerprint != task.repository_fingerprint:
            drift.append("Git working tree or index changed")
    return drift


def _accept_or_reject_drift(root: Path, task: Task, *, allow: bool) -> None:
    drift = _task_drift(root, task)
    if not drift:
        return
    if not allow:
        raise CommandError(
            "repository context changed since export: " + "; ".join(drift) + ". "
            "Review the current repository, then run `codepp validate "
            f"{task.task_id} --allow-drift` to rebaseline explicitly."
        )
    current = collect_repository_state(root, include_diff=False, include_status=False)
    task.repository_head = current.head
    task.repository_fingerprint = repository_fingerprint(root)
    task.context_hashes = fingerprint_files(root, list(task.context_hashes))
    task.drift_accepted_at = datetime.now().astimezone().isoformat(timespec="microseconds")
    task.save(root)
    print("Warning: repository drift was explicitly accepted and the task baseline was updated.")


def command_init(args: argparse.Namespace) -> int:
    requested = Path(args.path).expanduser() if args.path else Path.cwd()
    if not requested.exists() or not requested.is_dir():
        raise CommandError(f"project directory does not exist: {requested}")
    root = initialization_root(requested)
    created = initialize_config(root)
    exclude_added = ensure_codepp_excluded(root)
    print("Code++ initialized.\n")
    print(f"Project:\n{root}\n")
    if created:
        print("Created:")
        for path in created:
            suffix = "/" if path.is_dir() else ""
            print(f"  {_relative(root, path)}{suffix}")
    else:
        print("Existing configuration was preserved.")
    if exclude_added:
        print("\nGit local exclude updated: /.codepp/")
    log_event(root, "init")
    return 0


def command_doctor(args: argparse.Namespace) -> int:
    root = _root()
    checks: list[tuple[bool, str, str]] = []
    version_ok = sys.version_info >= (3, 11)
    checks.append((version_ok, f"Python {platform.python_version()}", "Python 3.11 or newer is required"))
    checks.append((is_git_repository(root), "Git repository", "not a Git repository (patch commands unavailable)"))
    checks.append((git_available(), "Git executable", "Git executable was not found"))
    try:
        import pyperclip
        clip_ok = bool(pyperclip.is_available())
        clip_detail = "Clipboard" if clip_ok else "Clipboard backend is unavailable"
    except ImportError:
        clip_ok, clip_detail = False, "pyperclip is not installed"
    checks.append((clip_ok, "Clipboard", clip_detail))
    try:
        load_config(root)
        config_ok, config_error = True, ""
    except ValueError as exc:
        config_ok, config_error = False, str(exc)
    checks.append((config_ok, "Config", config_error))
    try:
        base = safe_codepp_path(root)
        cache = safe_codepp_path(root, "cache")
        writable = base.is_dir()
    except ValueError:
        writable = False
        cache = None
    if writable and cache is not None:
        probe: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=cache, prefix=".doctor-", delete=False
            ) as handle:
                probe = Path(handle.name)
                handle.write("ok")
            relative = probe.relative_to(safe_codepp_path(root))
            probe = safe_codepp_path(root, *relative.parts)
            probe.unlink()
        except (OSError, ValueError):
            writable = False
        finally:
            if probe is not None and probe.exists():
                try:
                    probe.unlink()
                except OSError:
                    pass
    checks.append((writable, ".codepp directory", "directory is missing or not writable"))
    if is_git_repository(root):
        tracked = bool(run_git(root, ["ls-files", "--", ".codepp"]).stdout.strip())
        checks.append((not tracked, ".codepp is not tracked", ".codepp contains Git-tracked files"))

    print("Code++ Doctor\n")
    for ok, label, error in checks:
        print(f"[{'OK' if ok else 'WARN'}] {label if ok else error}")
    required_ok = all(
        ok
        for ok, label, _ in checks
        if label not in {"Git repository", "Clipboard", ".codepp is not tracked"}
    )
    print("\nCode++ is ready." if required_ok else "\nCode++ needs attention.")
    log_event(root, "doctor", status="OK" if required_ok else "WARN")
    return 0 if required_ok else 1


def command_export(args: argparse.Namespace) -> int:
    root = _root()
    config = load_config(root)
    if not args.task.strip():
        raise CommandError("task description cannot be empty")
    stdout_request = bool(args.stdout_request or args.output == "-")
    if stdout_request and args.copy:
        raise CommandError("--stdout/--output - cannot be combined with --copy")
    if args.force_output and (not args.output or args.output == "-"):
        raise CommandError("--force-output requires --output PATH")
    output_path: Path | None = None
    if args.output and args.output != "-":
        output_path, output_relative = ensure_inside_project(root, args.output)
        lowered = {part.lower() for part in Path(output_relative).parts}
        if ".git" in lowered or ".codepp" in lowered:
            raise CommandError("--output cannot target .git or .codepp")
        if output_path.exists() and not args.force_output:
            raise CommandError(
                f"output file already exists: {output_path}; use --force-output to replace it"
            )
        if output_path.exists() and not output_path.is_file():
            raise CommandError(f"output path is not a regular file: {output_path}")
    requested_files = args.files or []
    related_requested = args.related or args.related_limit is not None
    if related_requested and not requested_files:
        raise CommandError("--related requires at least one explicit --files seed")
    related_limit = (
        args.related_limit
        if args.related_limit is not None
        else int(config["context"]["max_related_files"])
    )
    if related_limit <= 0:
        raise CommandError("related file limit must be greater than zero")
    discovered_related = (
        discover_related_files(root, requested_files, config, max_files=related_limit)
        if related_requested
        else []
    )
    context_files = collect_files(root, [*requested_files, *discovered_related], config)
    related_set = set(discovered_related)
    related_budget = int(config["context"]["max_related_bytes"])
    bounded_context: list[ContextFile] = []
    accepted_related: list[str] = []
    for item in context_files:
        if item.path in related_set and not item.omitted:
            size = len(item.content.encode("utf-8"))
            if size > related_budget:
                item = ContextFile(
                    item.path,
                    "[FILE OMITTED: related context budget exceeded]",
                    True,
                )
            else:
                related_budget -= size
                accepted_related.append(item.path)
        bounded_context.append(item)
    context_files = bounded_context
    task = Task.create(args.task.strip(), [item.path for item in context_files])
    task.related_files = accepted_related
    memory = collect_memory(root, args.memory, config) if args.memory is not None else []
    task.memory_files = [item.path for item in memory]
    task.save(root)
    repository = collect_repository_state(
        root,
        include_diff=bool(config["context"]["include_git_diff"]) and not args.no_diff,
        include_staged_diff=bool(config["context"]["include_staged_diff"]) or args.staged,
        include_status=bool(config["context"]["include_git_status"]),
    )
    sanitized_diff, diff_redactions, omitted_diffs = sanitize_diff(root, repository.diff, config)
    sanitized_staged, staged_redactions, omitted_staged = sanitize_diff(root, repository.staged_diff, config)
    safe_branch, branch_redactions = redact_secrets(repository.branch)
    safe_status, status_redactions = redact_secrets(repository.status)
    repository = RepositoryState(
        repository.is_git,
        safe_branch,
        safe_status,
        sanitized_diff,
        sanitized_staged,
        repository.head,
    )
    task.repository_head = repository.head if repository.is_git else None
    task.repository_fingerprint = repository_fingerprint(root)
    task.context_hashes = fingerprint_files(
        root, [item.path for item in context_files if not item.omitted]
    )
    metadata = detect_metadata(root) if config["context"]["include_project_metadata"] else {"Name": root.name}
    configured_name = config["project"].get("name", "auto")
    if configured_name != "auto":
        metadata["Name"] = str(configured_name)
    metadata_redactions = 0
    for key, value in metadata.items():
        metadata[key], count = redact_secrets(str(value))
        metadata_redactions += count
    safe_task, task_redactions = redact_secrets(args.task)
    diagnostics = args.diagnostics
    diagnostics_redactions = 0
    if args.diagnostics_file:
        diagnostic_file = collect_files(root, [args.diagnostics_file], config)[0]
        diagnostics = f"Source: {diagnostic_file.path}\n\n{diagnostic_file.content}"
        diagnostics_redactions = diagnostic_file.redactions
    elif diagnostics is not None:
        diagnostics, diagnostics_redactions = sanitize_diagnostics(diagnostics, config)
    request = build_request(task.task_id, safe_task, metadata, context_files, repository, memory, diagnostics)
    request_path = safe_codepp_path(root, "outbox", f"{task.task_id}.md")
    write_text(request_path, request)
    if output_path is not None:
        write_text(output_path, request)
    task.request_file = _relative(root, request_path)
    task.transition("PACKED")
    task.save(root)

    copied = False
    if not args.no_copy and not stdout_request:
        try:
            ClipboardProvider().send(request)
            copied = True
        except ClipboardError as exc:
            task.save(root)
            log_event(root, "export", task_id=task.task_id, status="WARN", message=str(exc))
            raise CommandError(
                f"request was saved, but {exc}.\n\nRequest:\n{request_path}\n\n"
                "Use --stdout or copy that file manually."
            ) from exc
    task.transition("WAITING_FOR_RESPONSE")
    task.save(root)
    notice_stream = sys.stderr if stdout_request else sys.stdout
    if stdout_request:
        print(request, end="")
    else:
        print(f"Code++ request created.\n\nTask: {task.task_id}\nRequest: {request_path}")
        if output_path is not None:
            print(f"Output copy: {output_path}")
        if related_requested:
            print(f"Related files: {len(accepted_related)} included, {len(discovered_related) - len(accepted_related)} omitted")
        print("Clipboard: copied" if copied else "Clipboard: skipped (--no-copy)")
        print("\nPaste the request into your Planner chat, then run `codepp import` after copying its response.")
    redactions = (
        sum(item.redactions for item in context_files)
        + sum(item.redactions for item in memory)
        + diff_redactions
        + staged_redactions
        + diagnostics_redactions
        + branch_redactions
        + status_redactions
        + metadata_redactions
        + task_redactions
    )
    if redactions:
        print(f"\nSecurity: redacted {redactions} potential secret value(s).", file=notice_stream)
    omitted_diff_count = omitted_diffs + omitted_staged
    if omitted_diff_count:
        print(f"Security: omitted {omitted_diff_count} ignored file diff(s).", file=notice_stream)
    log_event(
        root,
        "export",
        task_id=task.task_id,
        message=(
            f"files={len(context_files)} memory={len(memory)} redactions={redactions} "
            f"omitted_diffs={omitted_diff_count}"
        ),
    )
    return 0


def command_import(args: argparse.Namespace) -> int:
    root = _root()
    config = load_config(root)
    if args.stdin:
        response_text = sys.stdin.read()
        if not response_text.strip():
            raise CommandError("standard input does not contain a response")
        source = "standard input"
    elif args.file:
        path = Path(args.file).expanduser().resolve()
        if not path.is_file():
            raise CommandError(f"response file does not exist: {path}")
        response_text = read_text(path)
        source = str(path)
    else:
        try:
            response_text = ClipboardProvider().receive()
        except ClipboardError as exc:
            raise CommandError(str(exc)) from exc
        source = "clipboard"
    response_size = len(response_text.encode("utf-8"))
    response_limit = int(config["protocol"]["max_response_bytes"])
    if response_size > response_limit:
        raise CommandError(
            f"response is {response_size} bytes; protocol.max_response_bytes is {response_limit}"
        )
    parsed = parse_response(response_text)
    task = load_task(root, parsed.task_id)
    if task.status not in {"PACKED", "WAITING_FOR_RESPONSE", "RESPONSE_RECEIVED"}:
        raise CommandError(f"task {task.task_id} cannot import a response while status is {task.status}")
    response_path = safe_codepp_path(root, "inbox", f"{task.task_id}.md")
    write_text(response_path, response_text)
    task.response_file = _relative(root, response_path)
    task.response_sections = {
        name: content for name, content in parsed.sections.items() if name != "Patch"
    }
    if task.status != "RESPONSE_RECEIVED":
        task.transition("RESPONSE_RECEIVED")

    patch = extract_patch(response_text)
    if patch:
        patch_path = safe_codepp_path(root, "tasks", f"{task.task_id}.patch")
        write_text(patch_path, patch)
        task.patch_file = _relative(root, patch_path)
        if config["patch"]["auto_validate"]:
            validation = validate_patch(root, patch)
            task.patch_validation = "VALID" if validation.valid else "INVALID"
            task.patch_error = validation.error or None
            if validation.valid:
                drift = _task_drift(root, task)
                if drift:
                    task.patch_validation = "STALE"
                    task.patch_error = "repository context changed since export: " + "; ".join(drift)
                else:
                    task.transition("VALIDATED")
                    task.transition("READY_TO_APPLY")
        else:
            task.patch_validation = "NOT_RUN"
            task.patch_error = None
    else:
        task.patch_file = None
        task.patch_validation = "NONE"
        task.patch_error = None
        task.transition("VALIDATED")
    task.save(root)
    print(f"Code++ response imported.\n\nTask: {task.task_id}\nSource: {source}\nStatus: {task.status}")
    if patch:
        print(f"Patch: detected ({task.patch_validation})")
        if task.patch_error:
            print(f"Patch error: {task.patch_error}")
    else:
        print("Patch: not present")
    log_event(root, "import", task_id=task.task_id, status=task.patch_validation or "OK")
    return 0


def _next_step(task: Task) -> str:
    return {
        "WAITING_FOR_RESPONSE": "Copy the Planner response, then run `codepp import`.",
        "RESPONSE_RECEIVED": f"Run `codepp validate {task.task_id}` after resolving patch issues.",
        "VALIDATED": "Review the response and implement its plan locally.",
        "READY_TO_APPLY": f"Review the patch, then run `codepp apply {task.task_id}`.",
        "APPLIED": "Run appropriate tests and inspect the resulting diff.",
        "VERIFYING": "Complete verification before marking the work done.",
        "DONE": "No further Code++ action is required.",
        "FAILED": "Inspect task details and fix the reported failure.",
    }.get(task.status, "Continue the Code++ workflow.")


def command_status(args: argparse.Namespace) -> int:
    root = _root()
    task = _select_task(root, args.task_id)
    print(f"Task:\n{task.task_id}\n\nTitle:\n{task.title}\n\nStatus:\n{task.status}\n")
    print(f"Files:\n{len(task.files)}\n\nPatch:\n{'Detected' if task.patch_file else 'None'}\n")
    print(f"Related files:\n{len(task.related_files)}\n")
    print(f"Memory files:\n{len(task.memory_files)}\n")
    print(f"Patch validation:\n{task.patch_validation or 'Not run'}\n\nNext:\n{_next_step(task)}")
    return 0


def command_list(args: argparse.Namespace) -> int:
    root = _root()
    if args.limit <= 0:
        raise CommandError("list limit must be greater than zero")
    tasks = list_tasks(root)[:args.limit]
    if not tasks:
        print("No Code++ tasks.")
        return 0
    print(f"{'TASK ID':<24} {'STATUS':<22} TITLE")
    for task in tasks:
        title = task.title.replace("\n", " ")
        print(f"{task.task_id:<24} {task.status:<22} {title[:70]}")
    return 0


def command_show(args: argparse.Namespace) -> int:
    root = _root()
    task = _select_task(root, args.task_id)
    if args.request:
        if not task.request_file:
            raise CommandError("task has no saved request")
        print(read_text(safe_codepp_reference(root, task.request_file)), end="")
        return 0
    if args.response:
        if not task.response_file:
            raise CommandError("task has no saved response")
        print(read_text(safe_codepp_reference(root, task.response_file)), end="")
        return 0
    if args.patch:
        print(_read_patch(root, task), end="")
        return 0
    print(f"Task: {task.task_id}\nStatus: {task.status}\nTitle: {task.title}\nCreated: {task.created_at}\nUpdated: {task.updated_at}")
    print("Files:")
    for file in task.files:
        print(f"  - {file}")
    if task.memory_files:
        print("Memory:")
        for file in task.memory_files:
            print(f"  - {file}")
    if task.related_files:
        print("Related files:")
        for file in task.related_files:
            print(f"  - {file}")
    print(f"Request: {task.request_file or 'none'}\nResponse: {task.response_file or 'none'}\nPatch: {task.patch_file or 'none'}")
    if task.patch_validation:
        print(f"Patch validation: {task.patch_validation}")
    if task.patch_error:
        print(f"Patch error: {task.patch_error}")
    if task.completed_at:
        print(f"Completed: {task.completed_at}")
    if task.completion_note:
        print(f"Completion note: {task.completion_note}")
    if task.completion_mode:
        print(f"Completion mode: {task.completion_mode}")
    for name in ("Diagnosis", "Plan", "Verification", "Risks", "Codex Instruction"):
        if task.response_sections.get(name):
            print(f"\n## {name}\n\n{task.response_sections[name]}")
    return 0


def command_validate(args: argparse.Namespace) -> int:
    root = _root()
    task = _select_task(root, args.task_id)
    _accept_or_reject_drift(root, task, allow=args.allow_drift)
    print("Protocol: ", end="")
    if not task.response_file:
        print("MISSING")
        raise CommandError("task has no imported response")
    parsed = parse_response(read_text(safe_codepp_reference(root, task.response_file)))
    print("OK")
    print(f"Task: {'OK' if parsed.task_id == task.task_id else 'MISMATCH'}")
    if parsed.task_id != task.task_id:
        raise CommandError("response Task-ID does not match task")
    patch = extract_patch(read_text(safe_codepp_reference(root, task.response_file)))
    if not patch:
        task.patch_validation = "NONE"
        task.patch_error = None
        task.save(root)
        print("Patch: NONE\n\nResponse is valid; no patch is available to apply.")
        return 0
    validation = validate_patch(root, patch)
    task.patch_validation = "VALID" if validation.valid else "INVALID"
    task.patch_error = validation.error or None
    if validation.valid and task.status == "RESPONSE_RECEIVED":
        task.transition("VALIDATED")
        task.transition("READY_TO_APPLY")
    task.save(root)
    print(f"Patch: {'OK' if validation.valid else 'INVALID'}")
    if not validation.valid:
        raise CommandError(validation.error)
    print("\nReady to apply.")
    log_event(root, "validate", task_id=task.task_id)
    return 0


def command_apply(args: argparse.Namespace) -> int:
    root = _root()
    task = _select_task(root, args.task_id)
    if task.status != "READY_TO_APPLY":
        raise CommandError(f"task {task.task_id} is not ready to apply (status: {task.status})")
    _accept_or_reject_drift(root, task, allow=False)
    patch = _read_patch(root, task)
    validation = validate_patch(root, patch)
    if not validation.valid:
        task.patch_validation = "INVALID"
        task.patch_error = validation.error
        task.save(root)
        raise CommandError(f"patch validation failed: {validation.error}")
    print("Patch will modify:")
    for file in validation.files:
        print(f"  - {file}")
    status = run_git(root, ["status", "--short"]).stdout.rstrip()
    if status:
        print("\nWorkspace currently has changes:")
        print(status)
    if not args.yes:
        try:
            answer = input("\nApply this patch? [y/N] ").strip().lower()
        except EOFError:
            answer = ""
        if answer not in {"y", "yes"}:
            print("Patch not applied.")
            return 1
    applied = apply_git_patch(root, patch)
    if not applied.valid:
        raise CommandError(f"patch application failed: {applied.error}")
    task.transition("APPLIED")
    task.save(root)
    print(f"\nPatch applied for task {task.task_id}.\nVerification commands were not run automatically; review them with `codepp show {task.task_id}`.")
    log_event(root, "apply", task_id=task.task_id)
    return 0


def command_finish(args: argparse.Namespace) -> int:
    root = _root()
    task = _select_task(root, args.task_id)
    if task.status in {"DONE", "FAILED"}:
        raise CommandError(f"task {task.task_id} is already {task.status}")
    if args.failed:
        if not args.note or not args.note.strip():
            raise CommandError("finishing a task as failed requires --note with a reason")
        task.transition("FAILED")
        task.completion_mode = "failed"
    else:
        if task.status not in {"VALIDATED", "READY_TO_APPLY", "APPLIED", "VERIFYING"}:
            raise CommandError(
                f"task {task.task_id} cannot finish successfully while status is {task.status}"
            )
        if task.status in {"VALIDATED", "READY_TO_APPLY"}:
            if not args.manual:
                raise CommandError(
                    "this task was not applied by Code++; use --manual --note <verification> "
                    "to record a manually completed result"
                )
            if not args.note or not args.note.strip():
                raise CommandError("manual completion requires --note describing verification")
            if not args.yes:
                try:
                    answer = input(
                        "Record this task as manually completed without Code++ applying its patch? [y/N] "
                    ).strip().lower()
                except EOFError:
                    answer = ""
                if answer not in {"y", "yes"}:
                    print("Task was not finished.")
                    return 1
            task.completion_mode = "manual"
        else:
            if args.manual:
                raise CommandError("--manual is only needed when Code++ did not apply the task patch")
            task.completion_mode = "applied"
        if task.status == "APPLIED":
            task.transition("VERIFYING")
        task.transition("DONE")
    task.completion_note = args.note.strip() if args.note and args.note.strip() else None
    task.save(root)
    outcome = "FAILED" if args.failed else "DONE"
    print(f"Task {task.task_id} marked {outcome}.")
    print("This records the executor's result; Code++ did not run verification commands automatically.")
    log_event(root, "finish", task_id=task.task_id, status=outcome)
    return 0


def _memory_input(args: argparse.Namespace) -> str:
    if args.text is not None:
        text = args.text
    elif args.file:
        source = Path(args.file).expanduser().resolve()
        if not source.is_file():
            raise CommandError(f"memory source file does not exist: {source}")
        text = read_text(source)
    else:
        text = sys.stdin.read()
    if not text.strip():
        raise CommandError("memory document content cannot be empty")
    return text


def _report_memory_safety(root: Path, name: str, text: str) -> None:
    config = load_config(root)
    size = len(text.encode("utf-8"))
    maximum = int(config["context"]["max_file_bytes"])
    if size > maximum:
        raise CommandError(
            f"memory document is {size} bytes; context.max_file_bytes is {maximum}"
        )
    _, secret_count = redact_secrets(text)
    if secret_count:
        print(
            f"Warning: {name} contains {secret_count} potential secret value(s); "
            "they will be redacted during export.",
            file=sys.stderr,
        )


def _warn_memory_budget(root: Path) -> None:
    config = load_config(root)
    total = 0
    for name in list_documents(root):
        total += len(read_document(root, name).encode("utf-8"))
    maximum = int(config["context"]["max_memory_bytes"])
    if total > maximum:
        print(
            f"Warning: repository memory totals {total} bytes; `export --memory` "
            f"includes at most {maximum} bytes. Select the most relevant documents explicitly.",
            file=sys.stderr,
        )


def command_memory_list(args: argparse.Namespace) -> int:
    root = _root()
    documents = list_documents(root)
    if not documents:
        print("No repository memory documents.")
        return 0
    print("Repository memory:")
    for name in documents:
        size = len(read_document(root, name).encode("utf-8"))
        print(f"  {name} ({size} bytes)")
    return 0


def command_memory_show(args: argparse.Namespace) -> int:
    root = _root()
    print(read_document(root, args.name), end="")
    return 0


def command_memory_add(args: argparse.Namespace) -> int:
    root = _root()
    text = _memory_input(args)
    _report_memory_safety(root, args.name, text)
    name = add_document(root, args.name, text, overwrite=args.force)
    _warn_memory_budget(root)
    print(f"Memory document saved: {name}")
    log_event(root, "memory-add", message=f"name={name} bytes={len(text.encode('utf-8'))}")
    return 0


def command_memory_update(args: argparse.Namespace) -> int:
    root = _root()
    text = _memory_input(args)
    _report_memory_safety(root, args.name, text)
    name = update_document(root, args.name, text)
    _warn_memory_budget(root)
    print(f"Memory document updated: {name}")
    log_event(root, "memory-update", message=f"name={name} bytes={len(text.encode('utf-8'))}")
    return 0


def command_memory_remove(args: argparse.Namespace) -> int:
    root = _root()
    if not args.yes:
        try:
            answer = input(f"Remove memory document '{args.name}'? [y/N] ").strip().lower()
        except EOFError:
            answer = ""
        if answer not in {"y", "yes"}:
            print("Memory document was not removed.")
            return 1
    name = remove_document(root, args.name)
    print(f"Memory document removed: {name}. This cannot be recovered by Code++.")
    log_event(root, "memory-remove", message=f"name={name}")
    return 0


def command_clean(args: argparse.Namespace) -> int:
    root = _root()
    targets = [safe_codepp_path(root, "cache"), safe_codepp_path(root, "logs")]
    state = safe_codepp_path(root)
    files: list[Path] = []
    for directory in targets:
        for path in directory.rglob("*"):
            relative = path.relative_to(state)
            checked = safe_codepp_path(root, *relative.parts)
            if checked.is_file():
                files.append(checked)
    if not files:
        print("Code++ cache and logs are already clean.")
        return 0
    print(f"This will remove {len(files)} cache/log file(s). Tasks, inbox, and outbox are preserved.")
    if not args.yes:
        try:
            answer = input("Continue? [y/N] ").strip().lower()
        except EOFError:
            answer = ""
        if answer not in {"y", "yes"}:
            print("Nothing removed.")
            return 1
    for path in files:
        path.unlink()
    print(f"Removed {len(files)} cache/log file(s).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codepp", description="Separate reasoning from local coding execution.")
    parser.add_argument("--version", action="version", version=f"codepp {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="initialize Code++ in a project")
    init.add_argument("path", nargs="?", help="project directory (defaults to current directory)")
    init.set_defaults(handler=command_init)

    doctor = subparsers.add_parser("doctor", help="check local requirements")
    doctor.set_defaults(handler=command_doctor)

    export = subparsers.add_parser("export", help="create a minimal CODEPP/1 request")
    export.add_argument("task", help="task description")
    export.add_argument("--files", nargs="+", metavar="FILE", help="explicit relevant files")
    export.add_argument("--related", action="store_true", help="discover one-hop local imports and test counterparts")
    export.add_argument("--related-limit", type=int, metavar="N", help="override the related-file count limit")
    export.add_argument("--no-diff", action="store_true", help="exclude the working tree diff")
    export.add_argument("--staged", action="store_true", help="include the staged Git diff")
    export.add_argument(
        "--memory",
        nargs="*",
        metavar="NAME",
        help="include all repository memory, or only the named .md/.txt files",
    )
    diagnostics = export.add_mutually_exclusive_group()
    diagnostics.add_argument("--diagnostics", help="include inline diagnostics after secret redaction")
    diagnostics.add_argument("--diagnostics-file", metavar="FILE", help="include a project diagnostics file")
    clipboard = export.add_mutually_exclusive_group()
    clipboard.add_argument("--copy", action="store_true", help="copy request (the default; retained for clarity)")
    clipboard.add_argument("--no-copy", action="store_true", help="do not use the clipboard")
    export_output = export.add_mutually_exclusive_group()
    export_output.add_argument(
        "--stdout", "--print", dest="stdout_request", action="store_true",
        help="write only the request to stdout and skip clipboard copy",
    )
    export_output.add_argument("--output", metavar="PATH", help="also save a request copy inside the project; use - for stdout")
    export.add_argument("--force-output", action="store_true", help="replace an existing --output file")
    export.set_defaults(handler=command_export)

    import_cmd = subparsers.add_parser("import", help="import a CODEPP/1 response")
    import_source = import_cmd.add_mutually_exclusive_group()
    import_source.add_argument("--file", help="read response from a file instead of the clipboard")
    import_source.add_argument("--stdin", action="store_true", help="read response from standard input")
    import_cmd.set_defaults(handler=command_import)

    status = subparsers.add_parser("status", help="show task status")
    status.add_argument("task_id", nargs="?")
    status.set_defaults(handler=command_status)

    list_cmd = subparsers.add_parser("list", help="list recent tasks")
    list_cmd.add_argument("--limit", type=int, default=20)
    list_cmd.set_defaults(handler=command_list)

    show = subparsers.add_parser("show", help="show task details")
    show.add_argument("task_id", nargs="?", default="latest")
    selection = show.add_mutually_exclusive_group()
    selection.add_argument("--request", action="store_true")
    selection.add_argument("--response", action="store_true")
    selection.add_argument("--patch", action="store_true")
    show.set_defaults(handler=command_show)

    validate = subparsers.add_parser("validate", help="validate a task response and patch")
    validate.add_argument("task_id", help="task ID, or the literal 'latest'")
    validate.add_argument("--allow-drift", action="store_true", help="accept reviewed repository drift and update the task baseline")
    validate.set_defaults(handler=command_validate)

    apply = subparsers.add_parser("apply", help="conservatively apply a validated patch")
    apply.add_argument("task_id", help="task ID, or the literal 'latest'")
    apply.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    apply.set_defaults(handler=command_apply)

    finish = subparsers.add_parser("finish", help="record a task as done or failed")
    finish.add_argument("task_id", help="task ID, or the literal 'latest'")
    finish_mode = finish.add_mutually_exclusive_group()
    finish_mode.add_argument("--failed", action="store_true", help="record failure instead of success")
    finish_mode.add_argument("--manual", action="store_true", help="record work completed without applying through Code++")
    finish.add_argument("--note", help="store a concise local completion note")
    finish.add_argument("--yes", action="store_true", help="confirm a manual completion non-interactively")
    finish.set_defaults(handler=command_finish)

    memory = subparsers.add_parser("memory", help="manage repository memory documents")
    memory_commands = memory.add_subparsers(dest="memory_command", required=True)

    memory_list = memory_commands.add_parser("list", help="list memory documents")
    memory_list.set_defaults(handler=command_memory_list)

    memory_show = memory_commands.add_parser("show", help="print one memory document")
    memory_show.add_argument("name")
    memory_show.set_defaults(handler=command_memory_show)

    def add_memory_source(command: argparse.ArgumentParser) -> None:
        source = command.add_mutually_exclusive_group(required=True)
        source.add_argument("--text", help="document text")
        source.add_argument("--file", metavar="PATH", help="read document text from a UTF-8 file")
        source.add_argument("--stdin", action="store_true", help="read document text from standard input")

    memory_add = memory_commands.add_parser("add", help="add a memory document")
    memory_add.add_argument("name")
    add_memory_source(memory_add)
    memory_add.add_argument("--force", action="store_true", help="replace an existing document")
    memory_add.set_defaults(handler=command_memory_add)

    memory_update = memory_commands.add_parser("update", help="replace an existing memory document")
    memory_update.add_argument("name")
    add_memory_source(memory_update)
    memory_update.set_defaults(handler=command_memory_update)

    memory_remove = memory_commands.add_parser("remove", help="remove one memory document")
    memory_remove.add_argument("name")
    memory_remove.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    memory_remove.set_defaults(handler=command_memory_remove)

    clean = subparsers.add_parser("clean", help="remove Code++ cache and log files")
    clean.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    clean.set_defaults(handler=command_clean)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args) or 0)
    except (CommandError, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
