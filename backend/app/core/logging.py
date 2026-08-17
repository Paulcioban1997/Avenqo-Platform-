import logging
from typing import Optional


def configure_logging(log_level: str = "INFO") -> None:
    """Configure le format et le niveau des journaux de l'application."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
