"""Model input compatibility validation (Phase 31.1).

Reuses metadata already embedded in the trained sklearn pipeline itself (the
fitted `ColumnTransformer`'s required column names, via
`shared.ai_engine.preprocessing.tabular.build_preprocessor`) — no second
model registry, no invented schema. Historical models trained before this
check existed still expose the same `ColumnTransformer` metadata (sklearn
always retains it on the fitted pipeline), so this applies retroactively
without any migration.

Models whose pipeline does not expose a "preprocessor" step (e.g. a bare
estimator saved by an older/simpler pipeline) simply skip this check: no
metadata is fabricated to force a compatibility decision that cannot be
made honestly (documented limitation, see docs/ai-predictive-copilot.md).
"""

from __future__ import annotations

from typing import Any, Mapping


class ModelInputIncompatible(ValueError):
    """Raised when the tenant's current data does not satisfy this model's required inputs."""


def _preprocessor_transformers(pipeline: Any) -> tuple[tuple[str, Any, Any], ...]:
    named_steps = getattr(pipeline, "named_steps", None)
    if named_steps is None:
        return ()
    preprocessor = named_steps.get("preprocessor")
    if preprocessor is None:
        return ()
    # Prefer the fitted attribute (`transformers_`); fall back to the
    # constructor config (`transformers`), both hold the same column lists.
    transformers = getattr(preprocessor, "transformers_", None) or getattr(preprocessor, "transformers", None)
    return tuple(transformers) if transformers else ()


def required_columns_for(pipeline: Any) -> tuple[str, ...]:
    """Exact column names the fitted preprocessor was trained on."""

    columns: list[str] = []
    for _name, _transformer, transformer_columns in _preprocessor_transformers(pipeline):
        if isinstance(transformer_columns, (list, tuple)):
            columns.extend(transformer_columns)
    return tuple(dict.fromkeys(columns))


def numerical_columns_for(pipeline: Any) -> tuple[str, ...]:
    """Column names routed through the "numerical" transformer bucket."""

    for name, _transformer, transformer_columns in _preprocessor_transformers(pipeline):
        if name == "numerical" and isinstance(transformer_columns, (list, tuple)):
            return tuple(transformer_columns)
    return ()


def _looks_numeric(value: object) -> bool:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return True
    try:
        float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return True


def validate_input_compatibility(pipeline: Any, features: Mapping[str, Any]) -> None:
    """Raises `ModelInputIncompatible` for missing/incompatible required fields.

    Only checks for MISSING required columns (extra fields are safely
    ignored by the fitted `ColumnTransformer`, `remainder="drop"`) and
    obviously incompatible types for numerical fields — it never guesses a
    substitute value and never silently coerces a dangerous schema.
    """

    required = required_columns_for(pipeline)
    if not required:
        return

    missing = [column for column in required if column not in features or features[column] is None]
    if missing:
        raise ModelInputIncompatible(
            f"Required fields are missing for this prediction: {', '.join(missing)}."
        )

    incompatible = [
        column
        for column in numerical_columns_for(pipeline)
        if column in features and not _looks_numeric(features[column])
    ]
    if incompatible:
        raise ModelInputIncompatible(
            f"These fields must be numeric for this prediction: {', '.join(incompatible)}."
        )
