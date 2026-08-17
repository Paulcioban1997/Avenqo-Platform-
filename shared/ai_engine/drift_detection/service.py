from dataclasses import dataclass
from typing import Any, Mapping, Protocol


@dataclass(frozen=True, slots=True)
class DriftReport:
    detected: bool
    scores: Mapping[str, float]


class DriftDetector(Protocol):
    def detect(self, reference: Any, current: Any) -> DriftReport: ...
