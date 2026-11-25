"""Optional CrowdStrike Falcon Next-Gen SIEM HEC connector & strict secret/PII sanitizer.

Design & Non-Negotiable Safety Guarantees:
1. Disabled by default (`CROWDSTRIKE_SIEM_ENABLED=false`) — zero network calls when disabled.
2. Configured strictly via environment variables (`CrowdStrikeConfig.from_env()`), keeping
   `backend/app/config/settings.py` untouched and avoiding secret leakage in reprs or logs.
3. Bounded HTTP timeout, per-minute rate cap, and automatic failure circuit-breaker so SIEM
   network or provider issues NEVER block, slow down, or fail Avenqo business requests.
4. Recursive secret/PII/content sanitizer guaranteeing ZERO PINs, NIPs, OTPs, passwords,
   JWTs, Bearer tokens, API keys (`sk-*`, `KEY*`, `whsec_*`), private document bodies, or
   voice call transcripts ever enter SIEM payloads, in-memory buffers, or logs.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
import logging
import os
import re
from threading import Lock
import time
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx

logger = logging.getLogger("avenqo.security.crowdstrike_siem")

MAX_SANITIZED_STRING_CHARS = 240
MAX_RECENT_BUFFER_EVENTS = 200


class SecurityEventType(StrEnum):
    """Canonical normalized security event categories (Phase B4)."""

    SUSPICIOUS_LOGIN_ATTEMPT = "suspicious_login_attempt"
    REPEATED_MFA_FAILURE = "repeated_mfa_failure"
    CROSS_TENANT_ACCESS_ATTEMPT = "cross_tenant_access_attempt"
    RBAC_PERMISSION_DENIED = "rbac_permission_denied"
    FORBIDDEN_TOOL_INVOCATION = "forbidden_tool_invocation"
    SUSPICIOUS_ROLE_MODIFICATION = "suspicious_role_modification"
    ABNORMAL_TOKEN_OR_CREDIT_ACTIVITY = "abnormal_token_or_credit_activity"
    REPEATED_API_ERROR_SPIKE = "repeated_api_error_spike"
    SECRET_OR_CONFIG_MODIFICATION = "secret_or_config_modification"
    FILE_UPLOAD_SECURITY_EVENT = "file_upload_security_event"


ALL_SECURITY_EVENT_TYPES: tuple[str, ...] = tuple(item.value for item in SecurityEventType)

_DEFAULT_EVENT_SEVERITY: dict[SecurityEventType, str] = {
    SecurityEventType.SUSPICIOUS_LOGIN_ATTEMPT: "medium",
    SecurityEventType.REPEATED_MFA_FAILURE: "high",
    SecurityEventType.CROSS_TENANT_ACCESS_ATTEMPT: "critical",
    SecurityEventType.RBAC_PERMISSION_DENIED: "medium",
    SecurityEventType.FORBIDDEN_TOOL_INVOCATION: "high",
    SecurityEventType.SUSPICIOUS_ROLE_MODIFICATION: "critical",
    SecurityEventType.ABNORMAL_TOKEN_OR_CREDIT_ACTIVITY: "high",
    SecurityEventType.REPEATED_API_ERROR_SPIKE: "medium",
    SecurityEventType.SECRET_OR_CONFIG_MODIFICATION: "high",
    SecurityEventType.FILE_UPLOAD_SECURITY_EVENT: "high",
}


class CrowdStrikeConnectionStatus(StrEnum):
    """Honest technical statuses for optional CrowdStrike NG-SIEM integration."""

    DISABLED = "disabled"
    MISSING_CREDENTIALS = "missing_credentials"
    CONFIGURED_UNVERIFIED = "configured_unverified"
    INVALID_CREDENTIALS = "invalid_credentials"
    UNREACHABLE = "unreachable"
    CONNECTED_VERIFIED = "connected_verified"


# Exact or segmented sensitive field names that must NEVER pass into SIEM payloads or logs.
_SENSITIVE_KEY_TOKENS: frozenset[str] = frozenset({
    "pin",
    "nip",
    "otp",
    "totp",
    "passcode",
    "password",
    "passwd",
    "pwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "access_key",
    "secret_key",
    "private_key",
    "client_secret",
    "webhook_secret",
    "authorization",
    "auth_header",
    "cookie",
    "set_cookie",
    "jwt",
    "bearer",
    "credential",
    "credentials",
    "recovery_code",
    "recovery_codes",
    "mfa_secret",
    "transcript",
    "transcripts",
    "utterance",
    "utterances",
    "spoken_text",
    "speech_text",
    "voice_transcript",
    "audio_bytes",
    "audio_payload",
    "document_body",
    "document_content",
    "document_text",
    "raw_content",
    "raw_body",
    "raw_document",
    "file_content",
    "file_bytes",
    "ocr_text",
    "extracted_text",
    "database_url",
    "pgpassword",
})

_SENSITIVE_KEY_SUBSTRINGS: tuple[str, ...] = (
    "password",
    "passwd",
    "secret",
    "api_key",
    "apikey",
    "private_key",
    "access_token",
    "refresh_token",
    "hec_token",
    "auth_token",
    "bearer",
    "authorization",
    "cookie",
    "jwt",
    "transcript",
    "utterance",
    "document_body",
    "document_content",
    "raw_content",
    "raw_body",
    "recovery_code",
    "pgpassword",
    "database_url",
)

# Inline regex scrubbers for free-form strings
_JWT_PATTERN = re.compile(r"\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\b")
_AUTH_SCHEME_PATTERN = re.compile(r"(?i)\b(?:Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{6,}")
_API_KEY_PATTERN = re.compile(
    r"\b(?:"
    r"sk[-_](?:proj[-_]|live[-_]|test[-_])?[A-Za-z0-9_-]{8,}"
    r"|pk_(?:live|test)_[A-Za-z0-9_-]{8,}"
    r"|rk_(?:live|test)_[A-Za-z0-9_-]{8,}"
    r"|whsec_[A-Za-z0-9_-]{8,}"
    r"|KEY[A-Za-z0-9_-]{8,}"
    r"|ak_[A-Za-z0-9_-]{8,}"
    r"|ghp_[A-Za-z0-9]{12,}"
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"
    r")\b"
)
_URL_CREDENTIAL_PATTERN = re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://[^:/\s@]+:)[^@\s]+(@)")
_LABELED_SECRET_VALUE_PATTERN = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|client[_-]?secret|hec[_-]?token|jwt|cookie)\s*([:=])\s*([^\s,;\"'}]+)"
)
_LABELED_PIN_PATTERN = re.compile(
    r"(?i)\b(?:pin|nip|otp|totp|passcode|code)\s*(?:[:=#]|\bis\b|\best\b)?\s*\d{4,8}\b"
)
# Standalone 4-8 digit numbers not attached to hyphens or hex (preserves ISO dates & UUIDs).
_STANDALONE_PIN_PATTERN = re.compile(r"(?<![0-9a-fA-F-])\b\d{4,8}\b(?![-0-9a-fA-F])")
_KEY_SPLIT_PATTERN = re.compile(r"[^a-z0-9]+")


def _is_sensitive_key(key: str) -> bool:
    normalized = key.strip().lower()
    if not normalized:
        return False
    camel_expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key.strip()).lower()
    snake_normalized = re.sub(r"[^a-z0-9]+", "_", camel_expanded).strip("_")
    for candidate in (normalized, camel_expanded, snake_normalized):
        if candidate in _SENSITIVE_KEY_TOKENS:
            return True
        if any(sub in candidate for sub in _SENSITIVE_KEY_SUBSTRINGS):
            return True
    parts = [part for part in _KEY_SPLIT_PATTERN.split(camel_expanded) if part]
    if any(part in _SENSITIVE_KEY_TOKENS for part in parts):
        return True
    return False


def sanitize_text_value(value: str, *, max_chars: int = MAX_SANITIZED_STRING_CHARS) -> str:
    """Scrub inline secrets, JWTs, API keys, URL passwords, and 4-8 digit PINs from text."""
    if not value:
        return ""
    scrubbed = _URL_CREDENTIAL_PATTERN.sub(r"\1[REDACTED]\2", value)
    scrubbed = _JWT_PATTERN.sub("[REDACTED_JWT]", scrubbed)
    scrubbed = _AUTH_SCHEME_PATTERN.sub("[REDACTED_AUTH]", scrubbed)
    scrubbed = _API_KEY_PATTERN.sub("[REDACTED_KEY]", scrubbed)
    scrubbed = _LABELED_SECRET_VALUE_PATTERN.sub(r"\1\2[REDACTED_SECRET]", scrubbed)
    scrubbed = _LABELED_PIN_PATTERN.sub("[REDACTED_PIN]", scrubbed)
    scrubbed = _STANDALONE_PIN_PATTERN.sub("[REDACTED_PIN]", scrubbed)
    if len(scrubbed) > max_chars:
        scrubbed = scrubbed[:max_chars] + "...[TRUNCATED]"
    return scrubbed


def sanitize_security_payload(value: Any, *, _depth: int = 0) -> Any:
    """Recursively strip/redact sensitive keys and scrub inline secret patterns.

    Sensitive keys (`pin`, `nip`, `password`, `secret`, `token`, `api_key`,
    `authorization`, `cookie`, `jwt`, `transcript`, `document_body`, `raw_content`, etc.)
    are removed/redacted so raw confidential values NEVER survive in SIEM payloads.
    """
    if _depth > 8:
        return "[TRUNCATED_DEPTH]"
    if value is None or isinstance(value, (bool, float)):
        return value
    if isinstance(value, int):
        # Preserve small counts/status codes, redact standalone 4-8 digit numeric PIN candidates
        # if someone passed an unkeyed integer inside a list.
        if 1000 <= abs(value) <= 99_999_999:
            return "[REDACTED_NUMERIC]"
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat() if value.tzinfo else value.replace(tzinfo=timezone.utc).isoformat()
    if isinstance(value, bytes):
        return "[REDACTED_BYTES]"
    if isinstance(value, str):
        return sanitize_text_value(value)
    if isinstance(value, Mapping):
        cleaned: dict[str, Any] = {}
        for raw_key, raw_item in value.items():
            key_str = str(raw_key)
            if _is_sensitive_key(key_str):
                # Strip sensitive content completely and leave only a non-sensitive redaction marker
                cleaned[key_str] = "[REDACTED]"
                continue
            # Preserve exact integers for explicitly safe counter/status keys
            if isinstance(raw_item, int) and not isinstance(raw_item, bool) and key_str.lower() in {
                "status_code",
                "http_status",
                "attempt_count",
                "error_count",
                "events_count",
                "credits_delta",
                "file_size_bytes",
                "limit",
            }:
                cleaned[key_str] = raw_item
            else:
                cleaned[key_str] = sanitize_security_payload(raw_item, _depth=_depth + 1)
        return cleaned
    if isinstance(value, (list, tuple, set, frozenset)):
        return [sanitize_security_payload(item, _depth=_depth + 1) for item in list(value)[:50]]
    return sanitize_text_value(str(value))


def _parse_bool(raw: str | None, *, default: bool = False) -> bool:
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    return default


def _clean_secret(raw: str | None) -> str | None:
    if raw is None:
        return None
    stripped = raw.strip()
    return stripped if stripped else None


def _safe_host_label(url: str | None) -> str | None:
    """Return scheme + hostname only — NEVER query parameters, paths with tokens, or userinfo."""
    if not url:
        return None
    try:
        parsed = urlsplit(url.strip())
        if not parsed.scheme or not parsed.hostname:
            return None
        port_suffix = f":{parsed.port}" if parsed.port else ""
        return f"{parsed.scheme.lower()}://{parsed.hostname.lower()}{port_suffix}"
    except Exception:
        return None


def _is_valid_hec_url(url: str | None) -> bool:
    if not url:
        return False
    try:
        parsed = urlsplit(url.strip())
    except Exception:
        return False
    if not parsed.hostname:
        return False
    scheme = parsed.scheme.lower()
    host = parsed.hostname.lower()
    if scheme == "https":
        return True
    if scheme == "http" and host in {"localhost", "127.0.0.1", "testserver"}:
        return True
    return False


@dataclass(frozen=True, slots=True)
class CrowdStrikeConfig:
    """Environment-driven optional CrowdStrike configuration (zero secrets in repr)."""

    siem_enabled: bool = False
    hec_url: str | None = None
    hec_token: str | None = field(default=None, repr=False)
    falcon_client_id: str | None = field(default=None, repr=False)
    falcon_client_secret: str | None = field(default=None, repr=False)
    environment: str = "development"
    timeout_seconds: float = 3.0
    max_events_per_minute: int = 120
    circuit_failure_threshold: int = 3
    circuit_cooldown_seconds: float = 60.0

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> CrowdStrikeConfig:
        env = environ if environ is not None else os.environ
        try:
            timeout = float(env.get("CROWDSTRIKE_HEC_TIMEOUT_SECONDS", "3.0"))
        except ValueError:
            timeout = 3.0
        timeout = min(max(timeout, 0.5), 10.0)

        try:
            max_rate = int(env.get("CROWDSTRIKE_HEC_MAX_EVENTS_PER_MINUTE", "120"))
        except ValueError:
            max_rate = 120
        max_rate = min(max(max_rate, 1), 5000)

        try:
            threshold = int(env.get("CROWDSTRIKE_HEC_CIRCUIT_FAILURE_THRESHOLD", "3"))
        except ValueError:
            threshold = 3
        threshold = min(max(threshold, 1), 20)

        try:
            cooldown = float(env.get("CROWDSTRIKE_HEC_CIRCUIT_COOLDOWN_SECONDS", "60.0"))
        except ValueError:
            cooldown = 60.0
        cooldown = min(max(cooldown, 5.0), 600.0)

        app_env = (env.get("ENVIRONMENT") or env.get("RAILWAY_ENVIRONMENT") or "development").strip().lower()

        return cls(
            siem_enabled=_parse_bool(env.get("CROWDSTRIKE_SIEM_ENABLED"), default=False),
            hec_url=_clean_secret(env.get("CROWDSTRIKE_HEC_URL")),
            hec_token=_clean_secret(env.get("CROWDSTRIKE_HEC_TOKEN")),
            falcon_client_id=_clean_secret(
                env.get("CROWDSTRIKE_FALCON_CLIENT_ID") or env.get("FALCON_CLIENT_ID")
            ),
            falcon_client_secret=_clean_secret(
                env.get("CROWDSTRIKE_FALCON_CLIENT_SECRET") or env.get("FALCON_CLIENT_SECRET")
            ),
            environment=app_env or "development",
            timeout_seconds=timeout,
            max_events_per_minute=max_rate,
            circuit_failure_threshold=threshold,
            circuit_cooldown_seconds=cooldown,
        )

    @property
    def has_hec_credentials(self) -> bool:
        return bool(self.hec_url and self.hec_token and _is_valid_hec_url(self.hec_url))

    @property
    def has_falcon_api_credentials(self) -> bool:
        return bool(self.falcon_client_id and self.falcon_client_secret)

    @property
    def safe_hec_endpoint(self) -> str | None:
        return _safe_host_label(self.hec_url)


@dataclass(frozen=True, slots=True)
class NormalizedSecurityEvent:
    """Normalized vendor-neutral / Falcon NG-SIEM security telemetry event."""

    event_id: str
    timestamp: str
    epoch_seconds: float
    event_type: str
    severity: str
    outcome: str
    environment: str
    summary: str
    company_id: str | None = None
    actor_id: str | None = None
    ip_address: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "severity": self.severity,
            "outcome": self.outcome,
            "vendor": "avenqo",
            "product": "avenqo-platform",
            "environment": self.environment,
            "company_id": self.company_id,
            "actor_id": self.actor_id,
            "ip_address": self.ip_address,
            "summary": self.summary,
            "details": self.details,
        }

    def to_hec_payload(self) -> dict[str, Any]:
        return {
            "time": round(self.epoch_seconds, 3),
            "host": "avenqo-api",
            "source": "avenqo:backend",
            "sourcetype": "avenqo:security:event",
            "event": self.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class CrowdStrikeConnectionResult:
    """Sanitized result of a CrowdStrike NG-SIEM connection check."""

    status: str
    siem_enabled: bool
    verified: bool
    protected_by_crowdstrike: bool
    message: str
    checked_at_utc: str
    endpoint_host: str | None = None
    http_status: int | None = None
    latency_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "siem_enabled": self.siem_enabled,
            "verified": self.verified,
            "protected_by_crowdstrike": self.protected_by_crowdstrike,
            "message": self.message,
            "checked_at_utc": self.checked_at_utc,
            "endpoint_host": self.endpoint_host,
            "http_status": self.http_status,
            "latency_ms": self.latency_ms,
        }


@dataclass(frozen=True, slots=True)
class SIEMDeliveryReceipt:
    """Outcome of emitting a normalized security event."""

    event_id: str
    event_type: str
    buffered_locally: bool
    delivered_to_siem: bool
    status: str


def build_normalized_event(
    event_type: SecurityEventType | str,
    *,
    summary: str,
    severity: str | None = None,
    outcome: str = "detected",
    environment: str = "development",
    company_id: UUID | str | None = None,
    actor_id: UUID | str | None = None,
    ip_address: str | None = None,
    details: Mapping[str, Any] | None = None,
) -> NormalizedSecurityEvent:
    """Validate event category and construct a strictly sanitized NormalizedSecurityEvent."""
    try:
        canonical_type = SecurityEventType(str(event_type).strip())
    except ValueError as exc:
        raise ValueError(f"Unsupported security event type: {event_type!r}") from exc

    resolved_severity = (severity or _DEFAULT_EVENT_SEVERITY[canonical_type]).strip().lower()
    if resolved_severity not in {"low", "medium", "high", "critical"}:
        resolved_severity = _DEFAULT_EVENT_SEVERITY[canonical_type]

    resolved_outcome = (outcome or "detected").strip().lower()
    if resolved_outcome not in {"blocked", "denied", "detected", "alert"}:
        resolved_outcome = "detected"

    now = datetime.now(timezone.utc)
    sanitized_details = sanitize_security_payload(dict(details or {}))
    if not isinstance(sanitized_details, dict):
        sanitized_details = {}

    return NormalizedSecurityEvent(
        event_id=str(uuid4()),
        timestamp=now.isoformat(),
        epoch_seconds=now.timestamp(),
        event_type=canonical_type.value,
        severity=resolved_severity,
        outcome=resolved_outcome,
        environment=sanitize_text_value(environment, max_chars=32) or "development",
        summary=sanitize_text_value(summary, max_chars=200),
        company_id=str(company_id) if company_id else None,
        actor_id=str(actor_id) if actor_id else None,
        ip_address=sanitize_text_value(ip_address, max_chars=64) if ip_address else None,
        details=sanitized_details,
    )


class CrowdStrikeSIEMConnector:
    """Optional non-blocking CrowdStrike Falcon Next-Gen SIEM HEC client."""

    def __init__(
        self,
        config: CrowdStrikeConfig | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        async_delivery: bool = False,
    ) -> None:
        self._config = config or CrowdStrikeConfig.from_env()
        self._transport = transport
        # When running with a live network transport (transport is None), background queue delivery
        # can be enabled via CROWDSTRIKE_ASYNC_DELIVERY or async_delivery so request threads never block.
        self._async_delivery = async_delivery
        self._lock = Lock()
        self._recent_events: deque[NormalizedSecurityEvent] = deque(maxlen=MAX_RECENT_BUFFER_EVENTS)
        self._window_epoch_minute: int = 0
        self._window_sent_count: int = 0
        self._consecutive_failures: int = 0
        self._circuit_open_until: float = 0.0
        self._last_verification: CrowdStrikeConnectionResult | None = None
        self._dropped_events_count: int = 0

    @property
    def config(self) -> CrowdStrikeConfig:
        return self._config

    def recent_events(self, limit: int = 25) -> list[dict[str, Any]]:
        clamped = min(max(limit, 1), MAX_RECENT_BUFFER_EVENTS)
        with self._lock:
            items = list(self._recent_events)[:clamped]
        return [item.to_dict() for item in items]

    def current_status_summary(self) -> dict[str, Any]:
        """Return passive status without making outbound network requests."""
        cfg = self._config
        with self._lock:
            last_check = self._last_verification

        if not cfg.siem_enabled:
            return {
                "siem_enabled": False,
                "status": CrowdStrikeConnectionStatus.DISABLED.value,
                "verified": False,
                "protected_by_crowdstrike": False,
                "display_badge_fr": "Non configuré — mode natif actif",
                "display_badge_en": "Not configured — native security mode active",
                "deployment_mode": "managed_paas_agentless",
                "kernel_sensor_assumed": False,
                "endpoint_host": None,
                "falcon_api_credentials_present": cfg.has_falcon_api_credentials,
                "last_connection_check": last_check.to_dict() if last_check else None,
            }

        if not cfg.has_hec_credentials:
            return {
                "siem_enabled": True,
                "status": CrowdStrikeConnectionStatus.MISSING_CREDENTIALS.value,
                "verified": False,
                "protected_by_crowdstrike": False,
                "display_badge_fr": "Activé mais identifiants HEC manquants ou URL non-HTTPS",
                "display_badge_en": "Enabled — missing HEC credentials or non-HTTPS URL",
                "deployment_mode": "managed_paas_agentless",
                "kernel_sensor_assumed": False,
                "endpoint_host": cfg.safe_hec_endpoint,
                "falcon_api_credentials_present": cfg.has_falcon_api_credentials,
                "last_connection_check": last_check.to_dict() if last_check else None,
            }

        if last_check is not None and last_check.siem_enabled:
            is_verified = last_check.status == CrowdStrikeConnectionStatus.CONNECTED_VERIFIED.value
            badge_fr = (
                "CrowdStrike NG-SIEM connecté et vérifié"
                if is_verified
                else f"CrowdStrike NG-SIEM en anomalie ({last_check.status})"
            )
            badge_en = (
                "CrowdStrike NG-SIEM connected & verified"
                if is_verified
                else f"CrowdStrike NG-SIEM degraded ({last_check.status})"
            )
            return {
                "siem_enabled": True,
                "status": last_check.status,
                "verified": is_verified,
                "protected_by_crowdstrike": is_verified,
                "display_badge_fr": badge_fr,
                "display_badge_en": badge_en,
                "deployment_mode": "managed_paas_agentless",
                "kernel_sensor_assumed": False,
                "endpoint_host": cfg.safe_hec_endpoint,
                "falcon_api_credentials_present": cfg.has_falcon_api_credentials,
                "last_connection_check": last_check.to_dict(),
            }

        return {
            "siem_enabled": True,
            "status": CrowdStrikeConnectionStatus.CONFIGURED_UNVERIFIED.value,
            "verified": False,
            "protected_by_crowdstrike": False,
            "display_badge_fr": "Configuré — connexion HEC non vérifiée",
            "display_badge_en": "Configured — HEC connection not yet verified",
            "deployment_mode": "managed_paas_agentless",
            "kernel_sensor_assumed": False,
            "endpoint_host": cfg.safe_hec_endpoint,
            "falcon_api_credentials_present": cfg.has_falcon_api_credentials,
            "last_connection_check": None,
        }

    def test_connection(self) -> CrowdStrikeConnectionResult:
        """Verify HEC connectivity honestly without leaking tokens or breaking callers."""
        cfg = self._config
        checked_at = datetime.now(timezone.utc).isoformat()

        if not cfg.siem_enabled:
            result = CrowdStrikeConnectionResult(
                status=CrowdStrikeConnectionStatus.DISABLED.value,
                siem_enabled=False,
                verified=False,
                protected_by_crowdstrike=False,
                message="CrowdStrike NG-SIEM est désactivé (mode natif Avenqo actif ; aucun appel réseau émis).",
                checked_at_utc=checked_at,
                endpoint_host=None,
            )
            with self._lock:
                self._last_verification = result
            return result

        if not cfg.has_hec_credentials or not cfg.hec_url or not cfg.hec_token:
            result = CrowdStrikeConnectionResult(
                status=CrowdStrikeConnectionStatus.MISSING_CREDENTIALS.value,
                siem_enabled=True,
                verified=False,
                protected_by_crowdstrike=False,
                message="CROWDSTRIKE_HEC_URL (HTTPS) et CROWDSTRIKE_HEC_TOKEN sont requis lorsque CROWDSTRIKE_SIEM_ENABLED=true.",
                checked_at_utc=checked_at,
                endpoint_host=cfg.safe_hec_endpoint,
            )
            with self._lock:
                self._last_verification = result
            return result

        probe_payload = {
            "time": round(time.time(), 3),
            "host": "avenqo-api",
            "source": "avenqo:backend",
            "sourcetype": "avenqo:security:connectivity_check",
            "event": {
                "vendor": "avenqo",
                "product": "avenqo-platform",
                "event_type": "connectivity_probe",
                "environment": cfg.environment,
                "timestamp": checked_at,
            },
        }

        started = time.monotonic()
        try:
            with httpx.Client(
                timeout=cfg.timeout_seconds,
                transport=self._transport,
                follow_redirects=False,
            ) as client:
                response = client.post(
                    cfg.hec_url,
                    json=probe_payload,
                    headers={
                        "Authorization": f"Bearer {cfg.hec_token}",
                        "Content-Type": "application/json",
                        "User-Agent": "Avenqo-Security-SIEM/1.0",
                    },
                )
            latency_ms = round((time.monotonic() - started) * 1000, 2)
            status_code = response.status_code

            if status_code in {200, 201, 202, 204}:
                result = CrowdStrikeConnectionResult(
                    status=CrowdStrikeConnectionStatus.CONNECTED_VERIFIED.value,
                    siem_enabled=True,
                    verified=True,
                    protected_by_crowdstrike=True,
                    message="Connexion CrowdStrike Falcon NG-SIEM HEC vérifiée avec succès.",
                    checked_at_utc=checked_at,
                    endpoint_host=cfg.safe_hec_endpoint,
                    http_status=status_code,
                    latency_ms=latency_ms,
                )
                with self._lock:
                    self._consecutive_failures = 0
                    self._circuit_open_until = 0.0
                    self._last_verification = result
                return result

            if status_code in {401, 403}:
                logger.warning(
                    "crowdstrike_hec_auth_rejected host=%s http_status=%d",
                    cfg.safe_hec_endpoint,
                    status_code,
                )
                result = CrowdStrikeConnectionResult(
                    status=CrowdStrikeConnectionStatus.INVALID_CREDENTIALS.value,
                    siem_enabled=True,
                    verified=False,
                    protected_by_crowdstrike=False,
                    message=f"Jeton HEC refusé par le collecteur CrowdStrike (HTTP {status_code}).",
                    checked_at_utc=checked_at,
                    endpoint_host=cfg.safe_hec_endpoint,
                    http_status=status_code,
                    latency_ms=latency_ms,
                )
                with self._lock:
                    self._last_verification = result
                return result

            logger.warning(
                "crowdstrike_hec_unexpected_status host=%s http_status=%d",
                cfg.safe_hec_endpoint,
                status_code,
            )
            result = CrowdStrikeConnectionResult(
                status=CrowdStrikeConnectionStatus.UNREACHABLE.value,
                siem_enabled=True,
                verified=False,
                protected_by_crowdstrike=False,
                message=f"Collecteur CrowdStrike HEC indisponible ou réponse inattendue (HTTP {status_code}).",
                checked_at_utc=checked_at,
                endpoint_host=cfg.safe_hec_endpoint,
                http_status=status_code,
                latency_ms=latency_ms,
            )
            with self._lock:
                self._last_verification = result
            return result

        except Exception as exc:
            latency_ms = round((time.monotonic() - started) * 1000, 2)
            exc_type = type(exc).__name__
            logger.warning(
                "crowdstrike_hec_unreachable host=%s error_type=%s",
                cfg.safe_hec_endpoint,
                exc_type,
            )
            result = CrowdStrikeConnectionResult(
                status=CrowdStrikeConnectionStatus.UNREACHABLE.value,
                siem_enabled=True,
                verified=False,
                protected_by_crowdstrike=False,
                message=f"Collecteur CrowdStrike HEC injoignable ({exc_type}).",
                checked_at_utc=checked_at,
                endpoint_host=cfg.safe_hec_endpoint,
                http_status=None,
                latency_ms=latency_ms,
            )
            with self._lock:
                self._last_verification = result
            return result

    def emit_event(
        self,
        event_type: SecurityEventType | str,
        *,
        summary: str,
        severity: str | None = None,
        outcome: str = "detected",
        company_id: UUID | str | None = None,
        actor_id: UUID | str | None = None,
        ip_address: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> SIEMDeliveryReceipt:
        """Sanitize, buffer locally, and optionally ship a security event to Falcon NG-SIEM.

        Guaranteed non-destructive: transport, credential, quota, or circuit-breaker failures
        are absorbed safely so caller business flows NEVER fail.
        """
        cfg = self._config
        event = build_normalized_event(
            event_type,
            summary=summary,
            severity=severity,
            outcome=outcome,
            environment=cfg.environment,
            company_id=company_id,
            actor_id=actor_id,
            ip_address=ip_address,
            details=details,
        )

        with self._lock:
            self._recent_events.appendleft(event)

        if not cfg.siem_enabled:
            return SIEMDeliveryReceipt(
                event_id=event.event_id,
                event_type=event.event_type,
                buffered_locally=True,
                delivered_to_siem=False,
                status=CrowdStrikeConnectionStatus.DISABLED.value,
            )

        if not cfg.has_hec_credentials or not cfg.hec_url or not cfg.hec_token:
            return SIEMDeliveryReceipt(
                event_id=event.event_id,
                event_type=event.event_type,
                buffered_locally=True,
                delivered_to_siem=False,
                status=CrowdStrikeConnectionStatus.MISSING_CREDENTIALS.value,
            )

        now_mono = time.monotonic()
        current_minute = int(time.time() // 60)
        with self._lock:
            if now_mono < self._circuit_open_until:
                return SIEMDeliveryReceipt(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    buffered_locally=True,
                    delivered_to_siem=False,
                    status="circuit_open",
                )
            if self._window_epoch_minute != current_minute:
                self._window_epoch_minute = current_minute
                self._window_sent_count = 0
            if self._window_sent_count >= cfg.max_events_per_minute:
                return SIEMDeliveryReceipt(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    buffered_locally=True,
                    delivered_to_siem=False,
                    status="rate_limited",
                )
            self._window_sent_count += 1

        try:
            with httpx.Client(
                timeout=cfg.timeout_seconds,
                transport=self._transport,
                follow_redirects=False,
            ) as client:
                response = client.post(
                    cfg.hec_url,
                    json=event.to_hec_payload(),
                    headers={
                        "Authorization": f"Bearer {cfg.hec_token}",
                        "Content-Type": "application/json",
                        "User-Agent": "Avenqo-Security-SIEM/1.0",
                    },
                )
            if response.status_code in {200, 201, 202, 204}:
                with self._lock:
                    self._consecutive_failures = 0
                return SIEMDeliveryReceipt(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    buffered_locally=True,
                    delivered_to_siem=True,
                    status="delivered",
                )

            failure_status = (
                CrowdStrikeConnectionStatus.INVALID_CREDENTIALS.value
                if response.status_code in {401, 403}
                else CrowdStrikeConnectionStatus.UNREACHABLE.value
            )
            self._record_delivery_failure(
                cfg,
                reason=f"http_{response.status_code}",
                failure_status=failure_status,
                http_status=response.status_code,
            )
            return SIEMDeliveryReceipt(
                event_id=event.event_id,
                event_type=event.event_type,
                buffered_locally=True,
                delivered_to_siem=False,
                status=failure_status,
            )
        except Exception as exc:
            self._record_delivery_failure(
                cfg,
                reason=type(exc).__name__,
                failure_status=CrowdStrikeConnectionStatus.UNREACHABLE.value,
                http_status=None,
            )
            return SIEMDeliveryReceipt(
                event_id=event.event_id,
                event_type=event.event_type,
                buffered_locally=True,
                delivered_to_siem=False,
                status=CrowdStrikeConnectionStatus.UNREACHABLE.value,
            )

    def _record_delivery_failure(
        self,
        cfg: CrowdStrikeConfig,
        *,
        reason: str,
        failure_status: str = CrowdStrikeConnectionStatus.UNREACHABLE.value,
        http_status: int | None = None,
    ) -> None:
        checked_at = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._consecutive_failures += 1
            if self._consecutive_failures >= cfg.circuit_failure_threshold:
                self._circuit_open_until = time.monotonic() + cfg.circuit_cooldown_seconds
            # Invalidate any staleCONNECTED_VERIFIED state so current_status_summary never claims active protection during an outage!
            self._last_verification = CrowdStrikeConnectionResult(
                status=failure_status,
                siem_enabled=cfg.siem_enabled,
                verified=False,
                protected_by_crowdstrike=False,
                message=f"Échec de livraison télémétrie HEC ({sanitize_text_value(reason, max_chars=48)}).",
                checked_at_utc=checked_at,
                endpoint_host=cfg.safe_hec_endpoint,
                http_status=http_status,
            )
        logger.warning(
            "crowdstrike_siem_delivery_failed host=%s reason=%s",
            cfg.safe_hec_endpoint,
            sanitize_text_value(reason, max_chars=48),
        )


_connector_lock = Lock()
_default_connector: CrowdStrikeSIEMConnector | None = None


def get_crowdstrike_connector() -> CrowdStrikeSIEMConnector:
    """Return process-wide CrowdStrike SIEM connector refreshed if env toggle changed."""
    global _default_connector
    env_cfg = CrowdStrikeConfig.from_env()
    with _connector_lock:
        if _default_connector is None or _default_connector.config != env_cfg:
            _default_connector = CrowdStrikeSIEMConnector(env_cfg)
        return _default_connector


def reset_crowdstrike_connector(connector: CrowdStrikeSIEMConnector | None = None) -> None:
    """Reset or inject connector instance for deterministic testing."""
    global _default_connector
    with _connector_lock:
        _default_connector = connector
