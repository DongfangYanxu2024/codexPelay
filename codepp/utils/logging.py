from datetime import datetime
from pathlib import Path

from ..core.paths import safe_codepp_path


def log_event(root: Path, command: str, *, task_id: str = "-", status: str = "OK", message: str = "") -> None:
    try:
        log_path = safe_codepp_path(root, "logs", "codepp.log")
    except ValueError:
        return
    if not log_path.parent.is_dir():
        return
    safe_message = " ".join(message.replace("\r", " ").replace("\n", " ").split())[:500]
    line = f"{datetime.now().astimezone().isoformat(timespec='seconds')} command={command} task={task_id} status={status}"
    if safe_message:
        line += f" message={safe_message}"
    try:
        with log_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line + "\n")
    except OSError:
        pass
