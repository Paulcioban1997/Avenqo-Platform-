from dataclasses import dataclass
from typing import Any, Protocol, Sequence


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    message: str
    field: str | None = None


class ValidationRule(Protocol):
    def validate(self, data: Any) -> Sequence[ValidationIssue]: ...


class ValidationService:
    """Exécute les règles injectées sans connaître la technologie des données."""

    def __init__(self, rules: Sequence[ValidationRule] = ()) -> None:
        self._rules = tuple(rules)

    def validate(self, data: Any) -> tuple[ValidationIssue, ...]:
        return tuple(issue for rule in self._rules for issue in rule.validate(data))
