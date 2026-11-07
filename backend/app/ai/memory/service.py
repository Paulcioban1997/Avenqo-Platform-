"""Avenqo Enterprise Memory Service using Mem0 OSS with Qdrant and PostgreSQL dual-layer persistence."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from backend.app.config.settings import Settings, get_settings
from backend.app.models.ai_memory import AIEnterpriseMemory, MemoryScope, MemoryType

# Ensure telemetry is disabled before any mem0 import to prevent lock contention
os.environ["MEM0_TELEMETRY"] = "False"

logger = logging.getLogger("avenqo.ai.memory")

# Redaction patterns for sensitive data
SENSITIVE_PATTERNS = [
    re.compile(r"\b(?:\d[ -]*?){13,16}\b"),  # Credit cards
    re.compile(r"(?i)\b(?:password|motdepasse|secret|api[_-]?key|bearer\s+[a-zA-Z0-9_\-\.]+)\b[:=]?\s*[\S]+"),
]


class AvenqoMemoryService:
    """Manages enterprise memory across short-term, long-term semantic, and live business layers."""

    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self._db = db
        self._settings = settings or get_settings()
        self._mem0: Any = None
        self._mem0_initialized = False

    @property
    def is_enabled(self) -> bool:
        return bool(self._settings.avenqo_memory_enabled)

    def _get_mem0(self) -> Any:
        """Lazily initialize Mem0 instance with safe vector store configuration."""
        if not self.is_enabled:
            return None
        if self._mem0_initialized:
            return self._mem0

        try:
            from mem0 import Memory
            from mem0.configs.base import MemoryConfig
            from mem0.utils.factory import EmbedderFactory, LlmFactory
            from mem0.embeddings.base import EmbeddingBase
            from mem0.llms.base import LLMBase

            storage_path = self._settings.avenqo_memory_storage_path
            os.makedirs(storage_path, exist_ok=True)

            # Determine embedder / llm providers
            has_openai_key = bool(getattr(self._settings, "openai_api_key", None) or os.environ.get("OPENAI_API_KEY"))
            has_gemini_key = bool(getattr(self._settings, "gemini_api_key", None) or os.environ.get("GEMINI_API_KEY"))

            embedder_provider = self._settings.avenqo_memory_embedder_provider
            llm_provider = self._settings.avenqo_memory_llm_provider

            # If no provider API key is present in environment, register deterministic fallback
            if not has_openai_key and not has_gemini_key:
                class DeterministicEmbedder(EmbeddingBase):
                    def __init__(self, config=None):
                        super().__init__(config)
                        self.config.embedding_dims = 64

                    def embed(self, text, *args, **kwargs):
                        h = hashlib.sha256(str(text).encode()).digest()
                        return [float(b) / 255.0 for b in (h + h)[:64]]

                    def embed_batch(self, texts, *args, **kwargs):
                        return [self.embed(t) for t in texts]

                class DeterministicLLM(LLMBase):
                    def __init__(self, config=None):
                        super().__init__(config)

                    def generate_response(self, messages, response_format=None, tools=None, tool_choice=None):
                        return json.dumps({
                            "memory": [{"text": str(messages[-1]["content"]) if messages else "", "event": "ADD"}]
                        })

                # Register fallback in current process module paths
                import sys
                module_name = "backend.app.ai.memory.fallback_providers"
                if module_name not in sys.modules:
                    import types
                    fb_mod = types.ModuleType(module_name)
                    fb_mod.DeterministicEmbedder = DeterministicEmbedder  # type: ignore[attr-defined]
                    fb_mod.DeterministicLLM = DeterministicLLM  # type: ignore[attr-defined]
                    sys.modules[module_name] = fb_mod

                from mem0.configs.llms.base import BaseLlmConfig
                EmbedderFactory.provider_to_class["openai"] = f"{module_name}.DeterministicEmbedder"
                LlmFactory.provider_to_class["openai"] = (f"{module_name}.DeterministicLLM", BaseLlmConfig)
                embedder_provider = "openai"
                llm_provider = "openai"
                embedding_dims = 64
            else:
                embedding_dims = self._settings.avenqo_memory_embedding_dims

            config_dict = {
                "vector_store": {
                    "provider": "qdrant",
                    "config": {
                        "path": storage_path,
                        "collection_name": self._settings.avenqo_memory_collection_name,
                        "embedding_model_dims": embedding_dims,
                    },
                },
                "embedder": {
                    "provider": embedder_provider,
                    "config": {"embedding_dims": embedding_dims},
                },
                "llm": {
                    "provider": llm_provider,
                    "config": {},
                },
                "history_db_path": os.path.join(storage_path, "history.db"),
            }

            self._mem0 = Memory.from_config(config_dict)
            self._mem0_initialized = True
            logger.info("Mem0 OSS successfully initialized with Qdrant storage at %s", storage_path)
            return self._mem0
        except Exception as exc:
            logger.warning("Failed to initialize Mem0 vector backend (%s). Degrading safely to SQL storage.", exc)
            self._mem0 = None
            self._mem0_initialized = True
            return None

    def _sanitize_content(self, content: str) -> str:
        """Strip sensitive data and sanitize text."""
        sanitized = content.strip()
        for pattern in SENSITIVE_PATTERNS:
            sanitized = pattern.sub("[REDACTED_SENSITIVE]", sanitized)
        return sanitized

    def add_memory(
        self,
        tenant_id: UUID,
        user_id: UUID,
        content: str,
        *,
        scope: str = MemoryScope.USER.value,
        memory_type: str = MemoryType.SEMANTIC.value,
        source_module: str = "central",
        conversation_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
        infer: bool = False,
    ) -> AIEnterpriseMemory:
        """Add a persistent memory with dual-layer PostgreSQL and Mem0 storage."""
        if not content or not content.strip():
            raise ValueError("Memory content cannot be empty.")

        clean_content = self._sanitize_content(content)
        meta = dict(metadata or {})
        memory_id = uuid4()

        # 1. Authoritative relational record in PostgreSQL
        record = AIEnterpriseMemory(
            id=memory_id,
            company_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            memory_scope=scope,
            memory_type=memory_type,
            source_module=source_module,
            content=clean_content,
            metadata_json=meta,
            is_active=True,
        )
        self._db.add(record)
        self._db.commit()
        self._db.refresh(record)

        # 2. Vector indexing in Mem0 OSS
        mem0_client = self._get_mem0()
        if mem0_client is not None:
            try:
                vector_metadata = {
                    "company_id": str(tenant_id),
                    "user_id": str(user_id),
                    "memory_scope": scope,
                    "db_id": str(memory_id),
                    "memory_type": memory_type,
                    "source_module": source_module,
                }
                # When scope is company, index with tenant agent_id or user_id
                target_user_id = str(user_id) if scope == MemoryScope.USER.value else f"company_{tenant_id}"
                vector_res = mem0_client.add(
                    clean_content,
                    user_id=target_user_id,
                    metadata=vector_metadata,
                    infer=infer,
                )
                if isinstance(vector_res, dict) and vector_res.get("results"):
                    first_res = vector_res["results"][0]
                    v_id = first_res.get("id")
                    if v_id:
                        meta["vector_id"] = str(v_id)
                        record.metadata_json = meta
                        self._db.commit()
            except Exception as exc:
                logger.warning("Mem0 vector index add failed for memory %s: %s", memory_id, exc)

        logger.info(
            "enterprise_memory_created id=%s tenant_id=%s user_id=%s scope=%s type=%s",
            memory_id,
            tenant_id,
            user_id,
            scope,
            memory_type,
        )
        return record

    def search_memories(
        self,
        tenant_id: UUID,
        user_id: UUID,
        query: str,
        *,
        limit: int = 5,
        scope: str | None = None,
        include_company_shared: bool = True,
    ) -> list[AIEnterpriseMemory]:
        """Search authorized memories using vector similarity with strict DB validation."""
        if not query or not query.strip():
            return []

        matched_db_ids: list[str] = []
        mem0_client = self._get_mem0()

        if mem0_client is not None:
            try:
                # Search user private memories
                user_res = mem0_client.search(
                    query,
                    filters={"user_id": str(user_id)},
                    top_k=limit * 2,
                )
                if isinstance(user_res, dict):
                    for item in user_res.get("results", []):
                        meta = item.get("metadata", {})
                        db_id = meta.get("db_id")
                        if db_id and meta.get("company_id") == str(tenant_id):
                            matched_db_ids.append(db_id)

                # Search company-shared memories if requested
                if include_company_shared:
                    comp_res = mem0_client.search(
                        query,
                        filters={"user_id": f"company_{tenant_id}"},
                        top_k=limit * 2,
                    )
                    if isinstance(comp_res, dict):
                        for item in comp_res.get("results", []):
                            meta = item.get("metadata", {})
                            db_id = meta.get("db_id")
                            if db_id and meta.get("company_id") == str(tenant_id):
                                matched_db_ids.append(db_id)
            except Exception as exc:
                logger.warning("Mem0 vector search failed: %s. Falling back to SQL search.", exc)

        # Authoritative PostgreSQL cross-check to enforce strict tenant and user bounds
        conditions = [
            AIEnterpriseMemory.company_id == tenant_id,
            AIEnterpriseMemory.is_active == True,  # noqa: E712
        ]

        if scope == MemoryScope.USER.value:
            conditions.append(and_(AIEnterpriseMemory.memory_scope == MemoryScope.USER.value, AIEnterpriseMemory.user_id == user_id))
        elif scope == MemoryScope.COMPANY.value:
            conditions.append(AIEnterpriseMemory.memory_scope == MemoryScope.COMPANY.value)
        elif not include_company_shared:
            conditions.append(and_(AIEnterpriseMemory.memory_scope == MemoryScope.USER.value, AIEnterpriseMemory.user_id == user_id))
        else:
            conditions.append(
                or_(
                    and_(AIEnterpriseMemory.memory_scope == MemoryScope.USER.value, AIEnterpriseMemory.user_id == user_id),
                    AIEnterpriseMemory.memory_scope == MemoryScope.COMPANY.value,
                )
            )

        # If vector search returned candidate IDs, prioritize them
        if matched_db_ids:
            parsed_uuids = []
            for d in matched_db_ids:
                try:
                    parsed_uuids.append(UUID(d))
                except Exception:
                    pass
            if parsed_uuids:
                stmt = select(AIEnterpriseMemory).where(
                    and_(*conditions, AIEnterpriseMemory.id.in_(parsed_uuids))
                )
                records = list(self._db.scalars(stmt).all())
                if records:
                    return records[:limit]

        # SQL keyword fallback if vector search yielded nothing
        words = [w.strip() for w in re.split(r"\W+", query) if len(w.strip()) >= 3]
        keyword_clauses = [AIEnterpriseMemory.content.ilike(f"%{w}%") for w in words]
        match_clause = or_(*keyword_clauses) if keyword_clauses else AIEnterpriseMemory.content.ilike(f"%{query.strip()}%")

        stmt = (
            select(AIEnterpriseMemory)
            .where(and_(*conditions, match_clause))
            .order_by(AIEnterpriseMemory.created_at.desc())
            .limit(limit)
        )
        return list(self._db.scalars(stmt).all())

    def get_memory(
        self,
        tenant_id: UUID,
        user_id: UUID,
        memory_id: UUID,
    ) -> AIEnterpriseMemory | None:
        """Retrieve a specific memory verifying tenant ownership and access scope."""
        stmt = select(AIEnterpriseMemory).where(
            and_(
                AIEnterpriseMemory.id == memory_id,
                AIEnterpriseMemory.company_id == tenant_id,
                AIEnterpriseMemory.is_active == True,  # noqa: E712
            )
        )
        record = self._db.scalar(stmt)
        if not record:
            return None
        # User scope check
        if record.memory_scope == MemoryScope.USER.value and record.user_id != user_id:
            return None
        return record

    def list_memories(
        self,
        tenant_id: UUID,
        user_id: UUID,
        *,
        scope: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AIEnterpriseMemory]:
        """List active memories for the tenant."""
        conditions = [
            AIEnterpriseMemory.company_id == tenant_id,
            AIEnterpriseMemory.is_active == True,  # noqa: E712
        ]
        if scope == MemoryScope.USER.value:
            conditions.append(and_(AIEnterpriseMemory.memory_scope == MemoryScope.USER.value, AIEnterpriseMemory.user_id == user_id))
        elif scope == MemoryScope.COMPANY.value:
            conditions.append(AIEnterpriseMemory.memory_scope == MemoryScope.COMPANY.value)
        else:
            conditions.append(
                or_(
                    and_(AIEnterpriseMemory.memory_scope == MemoryScope.USER.value, AIEnterpriseMemory.user_id == user_id),
                    AIEnterpriseMemory.memory_scope == MemoryScope.COMPANY.value,
                )
            )

        stmt = (
            select(AIEnterpriseMemory)
            .where(and_(*conditions))
            .order_by(AIEnterpriseMemory.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(self._db.scalars(stmt).all())

    def update_memory(
        self,
        tenant_id: UUID,
        user_id: UUID,
        memory_id: UUID,
        *,
        content: str | None = None,
        scope: str | None = None,
        memory_type: str | None = None,
    ) -> AIEnterpriseMemory | None:
        """Update a memory with changes propagating to vector storage."""
        record = self.get_memory(tenant_id, user_id, memory_id)
        if not record:
            return None

        if content is not None:
            clean_content = self._sanitize_content(content)
            record.content = clean_content

        if scope is not None:
            record.memory_scope = scope
        if memory_type is not None:
            record.memory_type = memory_type

        self._db.commit()
        self._db.refresh(record)

        # Propagate to Mem0 if vector_id is available
        mem0_client = self._get_mem0()
        if mem0_client is not None and record.metadata_json and record.metadata_json.get("vector_id"):
            try:
                v_id = record.metadata_json["vector_id"]
                mem0_client.update(v_id, text=record.content)
            except Exception as exc:
                logger.warning("Mem0 update failed for memory %s: %s", memory_id, exc)

        logger.info("enterprise_memory_updated id=%s tenant_id=%s user_id=%s", memory_id, tenant_id, user_id)
        return record

    def delete_memory(
        self,
        tenant_id: UUID,
        user_id: UUID,
        memory_id: UUID,
    ) -> bool:
        """Soft-delete memory in DB and remove from Mem0 vector index."""
        record = self.get_memory(tenant_id, user_id, memory_id)
        if not record:
            return False

        record.is_active = False
        self._db.commit()

        # Remove from vector index
        mem0_client = self._get_mem0()
        if mem0_client is not None and record.metadata_json and record.metadata_json.get("vector_id"):
            try:
                v_id = record.metadata_json["vector_id"]
                mem0_client.delete(v_id)
            except Exception as exc:
                logger.warning("Mem0 delete failed for vector_id %s: %s", v_id, exc)

        logger.info("enterprise_memory_deleted id=%s tenant_id=%s user_id=%s", memory_id, tenant_id, user_id)
        return True

    def delete_tenant_memories(
        self,
        tenant_id: UUID,
        user_id: UUID | None = None,
        scope: str | None = None,
    ) -> int:
        """Deactivate all memories for tenant / user."""
        conditions = [
            AIEnterpriseMemory.company_id == tenant_id,
            AIEnterpriseMemory.is_active == True,  # noqa: E712
        ]
        if user_id is not None:
            conditions.append(AIEnterpriseMemory.user_id == user_id)
        if scope is not None:
            conditions.append(AIEnterpriseMemory.memory_scope == scope)

        records = list(self._db.scalars(select(AIEnterpriseMemory).where(and_(*conditions))).all())
        mem0_client = self._get_mem0()
        count = 0
        for rec in records:
            rec.is_active = False
            count += 1
            if mem0_client is not None and rec.metadata_json and rec.metadata_json.get("vector_id"):
                try:
                    mem0_client.delete(rec.metadata_json["vector_id"])
                except Exception:
                    pass
        self._db.commit()
        logger.info("enterprise_memories_cleared count=%d tenant_id=%s", count, tenant_id)
        return count

    def retrieve_relevant_context(
        self,
        tenant_id: UUID,
        user_id: UUID,
        query: str,
        *,
        max_tokens: int = 1000,
        limit: int | None = None,
    ) -> str:
        """Retrieve and format enterprise memories as an untrusted prompt context block."""
        if not self.is_enabled:
            return ""

        effective_limit = limit or self._settings.avenqo_memory_max_context_items
        memories = self.search_memories(
            tenant_id,
            user_id,
            query,
            limit=effective_limit,
            include_company_shared=True,
        )

        if not memories:
            return ""

        lines = []
        for mem in memories:
            scope_label = "Company Shared" if mem.memory_scope == MemoryScope.COMPANY.value else "Private User"
            type_label = mem.memory_type.capitalize()
            lines.append(f"- [{scope_label} - {type_label}] {mem.content}")

        block = "\n".join(lines)
        # Approximate 4 characters per token
        if len(block) > max_tokens * 4:
            block = block[: max_tokens * 4] + "..."

        return f"<enterprise_memory untrusted=\"true\">\n{block}\n</enterprise_memory>"
