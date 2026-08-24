"""Base de connaissances produit Avenqo (Phase 32) — Platform Support AI.

Charge des documents Markdown (avec frontmatter simple `id`/`title`/`tags`)
depuis un dossier configurable (`Settings.ai_support_knowledge_root`,
défaut `platform_knowledge/`). Jamais de données tenant ici : uniquement la
documentation produit versionnée dans le dépôt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    id: str
    title: str
    tags: tuple[str, ...]
    content: str
    path: str


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    raw_meta, body = match.group(1), match.group(2)
    meta: dict[str, str] = {}
    for line in raw_meta.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    return meta, body.strip()


def load_documents(root: str) -> list[KnowledgeDocument]:
    base = Path(root)
    if not base.exists():
        return []
    documents: list[KnowledgeDocument] = []
    for path in sorted(base.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        meta, body = _parse_frontmatter(text)
        raw_tags = meta.get("tags", "").strip("[]")
        tags = tuple(tag.strip() for tag in raw_tags.split(",") if tag.strip())
        documents.append(
            KnowledgeDocument(
                id=meta.get("id", path.stem),
                title=meta.get("title", path.stem),
                tags=tags,
                content=body,
                path=str(path.relative_to(base)).replace("\\", "/"),
            )
        )
    return documents


@lru_cache(maxsize=8)
def _cached_documents(root: str) -> tuple[KnowledgeDocument, ...]:
    return tuple(load_documents(root))


def get_documents(root: str) -> tuple[KnowledgeDocument, ...]:
    return _cached_documents(root)
