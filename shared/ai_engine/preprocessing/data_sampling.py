"""Helpers for bounded training/evaluation datasets on large tables."""

from __future__ import annotations

from typing import TypeVar

import pandas as pd
from sklearn.model_selection import train_test_split

_TargetT = TypeVar("_TargetT", pd.Series, pd.DataFrame)


def sample_frame(
    frame: pd.DataFrame,
    max_rows: int | None,
    *,
    random_seed: int = 42,
) -> pd.DataFrame:
    """Returns the original frame unless it exceeds the configured cap."""

    if max_rows is None or max_rows <= 0 or len(frame) <= max_rows:
        return frame
    return frame.sample(n=max_rows, random_state=random_seed).sort_index(kind="stable")


def sample_features_and_target(
    features: pd.DataFrame,
    target: _TargetT,
    max_rows: int | None,
    *,
    random_seed: int = 42,
    stratify: bool = False,
) -> tuple[pd.DataFrame, _TargetT]:
    """Samples features and target together while preserving their alignment."""

    if max_rows is None or max_rows <= 0 or len(features) <= max_rows:
        return features, target

    stratify_target = None
    if stratify:
        try:
            target_series = target if isinstance(target, pd.Series) else target.squeeze(axis=1)
            value_counts = target_series.value_counts(dropna=False)
            if len(value_counts) > 1 and int(value_counts.min()) >= 2:
                stratify_target = target_series
        except Exception:
            stratify_target = None

    sampled_features, _, sampled_target, _ = train_test_split(
        features,
        target,
        train_size=max_rows,
        random_state=random_seed,
        stratify=stratify_target,
    )
    return (
        sampled_features.sort_index(kind="stable"),
        sampled_target.sort_index(kind="stable"),
    )
