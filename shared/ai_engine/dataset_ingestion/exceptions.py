"""Exceptions métier de l'ingestion universelle de datasets (Phase 26)."""

from __future__ import annotations


class DatasetIngestionError(ValueError):
    """Classe de base de toutes les erreurs métier d'ingestion de dataset."""


class UnsupportedDatasetFormat(DatasetIngestionError):
    """Le format du fichier envoyé n'est pas pris en charge."""


class InvalidDatasetFile(DatasetIngestionError):
    """Le fichier est corrompu ou ne respecte pas la structure attendue."""


class EmptyDataset(DatasetIngestionError):
    """Le fichier ne contient aucune ligne exploitable."""


class DatasetTooLarge(DatasetIngestionError):
    """Le fichier dépasse la taille maximale autorisée."""


class DatasetParseError(DatasetIngestionError):
    """Le contenu n'a pas pu être analysé dans le format déclaré."""
