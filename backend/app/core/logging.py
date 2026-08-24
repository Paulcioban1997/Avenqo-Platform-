import logging

from backend.app.core.request_context import get_request_id


class _RequestIDFilter(logging.Filter):
    """Injecte `request_id` (contextvar) dans chaque enregistrement de log."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
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
