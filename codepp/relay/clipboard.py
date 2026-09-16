from .base import RelayProvider


class ClipboardError(RuntimeError):
    pass


class ClipboardProvider(RelayProvider):
    def _module(self):
        try:
            import pyperclip
        except ImportError as exc:
            raise ClipboardError("clipboard support requires pyperclip; reinstall Code++") from exc
        return pyperclip

    def send(self, request: str) -> None:
        try:
            self._module().copy(request)
        except Exception as exc:
            raise ClipboardError(f"clipboard copy failed: {exc}") from exc

    def receive(self) -> str:
        try:
            value = self._module().paste()
        except Exception as exc:
            raise ClipboardError(f"clipboard paste failed: {exc}") from exc
        if not isinstance(value, str) or not value.strip():
            raise ClipboardError("clipboard does not contain a response")
        return value

    def check(self) -> tuple[bool, str]:
        module = self._module()
        try:
            available = bool(module.is_available())
            return available, "clipboard backend available" if available else "clipboard backend unavailable"
        except Exception as exc:
            return False, str(exc)
