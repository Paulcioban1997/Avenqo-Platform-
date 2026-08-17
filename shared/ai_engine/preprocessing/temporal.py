"""Préparation d'une série temporelle pour le forecasting (runtime actif).

Aucune dépendance vers `shared.ai_engine.core`/`shared.ai_engine.families`
(moteur orphelin) : la détection de la colonne temporelle réutilise
`TargetResolutionService` côté dispatcher (comme la colonne cible) — cette
préparation est une implémentation propre à la couche active, jamais une
copie du moteur orphelin.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


class InvalidTimeColumnError(ValueError):
    """Aucune date exploitable n'a pu être extraite de la colonne temporelle déclarée."""


class InsufficientObservationsError(ValueError):
    """La série contient moins d'observations que le minimum requis après nettoyage."""


@dataclass(frozen=True, slots=True)
class TimeSeriesPreparation:
    """Résultat propre, trié et régularisé, prêt pour le backtesting."""

    frame: pd.DataFrame  # colonnes "__time__"/"__target__", triées, fréquence régulière
    frequency: str
    observations: int
    invalid_dates_dropped: int
    duplicate_periods_aggregated: int
    irregular_intervals: bool


def prepare_time_series(
    data: pd.DataFrame,
    time_column: str,
    target_column: str,
    *,
    frequency: str = "auto",
    aggregation: str = "sum",
    minimum_observations: int = 8,
) -> TimeSeriesPreparation:
    """Nettoie, agrège et régularise une série temporelle brute.

    Étapes (aucune fuite d'information future à ce stade — uniquement du
    nettoyage historique) : parsing tolérant des dates, suppression des
    dates invalides, agrégation des doublons temporels, régularisation sur
    une fréquence unique (avec interpolation des éventuels trous internes).
    """

    if time_column not in data.columns:
        raise InvalidTimeColumnError(f"Colonne temporelle absente du dataset: {time_column}")
    if target_column not in data.columns:
        raise ValueError(f"Colonne cible absente du dataset: {target_column}")

    parsed = pd.to_datetime(data[time_column], errors="coerce", format="mixed")
    valid_mask = parsed.notna()
    invalid_dropped = int((~valid_mask).sum())

    frame = pd.DataFrame(
        {
            "__time__": parsed[valid_mask],
            "__target__": pd.to_numeric(data.loc[valid_mask, target_column], errors="coerce"),
        }
    ).dropna(subset=["__target__"])
    if frame.empty:
        raise InvalidTimeColumnError(
            "Aucune date valide n'a pu être extraite de la colonne temporelle."
        )

    frame = frame.sort_values("__time__")
    resolved_frequency = frequency if frequency != "auto" else _infer_frequency(frame["__time__"])
    aggregator = "mean" if aggregation == "mean" else "sum"

    periods = frame["__time__"].dt.to_period(resolved_frequency)
    duplicate_periods = int(periods.duplicated().sum())
    aggregated = (
        frame.assign(__period__=periods)
        .groupby("__period__", as_index=False)["__target__"]
        .agg(aggregator)
    )

    period_index = pd.period_range(
        aggregated["__period__"].min(), aggregated["__period__"].max(), freq=resolved_frequency
    )
    full_frame = pd.DataFrame({"__period__": period_index}).merge(aggregated, on="__period__", how="left")
    irregular = bool(full_frame["__target__"].isna().any())
    full_frame["__target__"] = full_frame["__target__"].interpolate(limit_direction="both")
    full_frame["__time__"] = full_frame["__period__"].dt.to_timestamp()
    final_frame = full_frame[["__time__", "__target__"]].reset_index(drop=True)

    if len(final_frame) < minimum_observations:
        raise InsufficientObservationsError(
            f"Série trop courte après préparation ({len(final_frame)} observations, "
            f"minimum requis {minimum_observations})."
        )

    return TimeSeriesPreparation(
        frame=final_frame,
        frequency=resolved_frequency,
        observations=len(final_frame),
        invalid_dates_dropped=invalid_dropped,
        duplicate_periods_aggregated=duplicate_periods,
        irregular_intervals=irregular,
    )


def _infer_frequency(timestamps: pd.Series) -> str:
    """Fréquence pandas (jour/semaine/mois) inférée depuis l'écart médian observé."""

    ordered = timestamps.sort_values()
    if len(ordered) < 2:
        return "D"
    deltas = ordered.diff().dropna()
    if deltas.empty:
        return "D"
    median_seconds = float(np.median(deltas.dt.total_seconds()))
    if median_seconds <= 2 * 86400:
        return "D"
    if median_seconds <= 10 * 86400:
        return "W"
    return "M"
