"""Centralized resource caps for automatic training runs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TrainingExecutionControls:
    search_max_rows: int = 50_000
    final_fit_max_rows: int = 120_000
    unsupervised_max_rows: int = 30_000
    recommendation_search_max_rows: int = 80_000
    recommendation_final_fit_max_rows: int = 160_000
    explainability_max_rows: int = 2_000
    search_max_parallel_jobs: int = 1

    @classmethod
    def from_settings(cls, settings) -> "TrainingExecutionControls":
        return cls(
            search_max_rows=settings.training_search_max_rows,
            final_fit_max_rows=settings.training_final_fit_max_rows,
            unsupervised_max_rows=settings.training_unsupervised_max_rows,
            recommendation_search_max_rows=settings.training_recommendation_search_max_rows,
            recommendation_final_fit_max_rows=settings.training_recommendation_final_fit_max_rows,
            explainability_max_rows=settings.training_explainability_max_rows,
            search_max_parallel_jobs=settings.training_search_max_parallel_jobs,
        )
