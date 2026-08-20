from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RetrievedSource:
    source_type: str
    identifier: str
    name: str
    content: str
    metadata: dict[str, object]