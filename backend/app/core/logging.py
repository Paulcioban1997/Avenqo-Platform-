import logging
from urllib.parse import urlsplit, urlunsplit

from backend.app.core.request_context import get_request_id


class _RequestIDFilter(logging.Filter):
    """Injecte `request_id` (contextvar) dans chaque enregistrement de log."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        return True


class _CallbackQueryFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        def safe(value):
            if not isinstance(value, str) or "/callback?" not in value:
                return value
            parsed = urlsplit(value)
            if parsed.path.endswith("/callback"):
                return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
            return value
        if isinstance(record.args, tuple):
            record.args = tuple(safe(value) for value in record.args)
        elif isinstance(record.args, dict):
            record.args = {key: safe(value) for key, value in record.args.items()}
        record.msg = safe(record.msg)
        return True


def configure_logging(log_level: str = "INFO") -> None:
    """Configure le format et le niveau des journaux de l'application."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | request_id=%(request_id)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    root = logging.getLogger()
    for handler in root.handlers:
        if not any(isinstance(existing, _RequestIDFilter) for existing in handler.filters):
            handler.addFilter(_RequestIDFilter())
        if not any(isinstance(existing, _CallbackQueryFilter) for existing in handler.filters):
            handler.addFilter(_CallbackQueryFilter())
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(existing, _CallbackQueryFilter) for existing in access.filters):
        access.addFilter(_CallbackQueryFilter())
