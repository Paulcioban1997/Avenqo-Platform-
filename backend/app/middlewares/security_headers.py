"""En-têtes de sécurité HTTP de base (Phase 34).

Adaptés à une API JSON servie derrière un reverse proxy TLS : ne tente pas
d'imposer une CSP pensée pour du HTML/JS servi par ce process (Flutter Web est
buildé et servi séparément — voir docs/production-deployment.md).
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Ajoute des en-têtes de sécurité standards à chaque réponse."""

    def __init__(self, app, *, force_https: bool = False) -> None:
        super().__init__(app)
        self._force_https = force_https

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Frame-Options"] = "DENY"
        # /docs et /redoc (Swagger UI / ReDoc, dev uniquement) chargent leurs
        # assets JS/CSS/favicon depuis jsdelivr et exécutent un script inline
        # d'init : une CSP "default-src 'none'" les bloque entièrement (page
        # blanche). On leur applique donc une CSP permissive dédiée au lieu de
        # la politique stricte utilisée pour le reste de l'API JSON.
        if request.url.path in ("/docs", "/redoc"):
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "img-src 'self' data: https://fastapi.tiangolo.com; "
                "font-src 'self' data: https://cdn.jsdelivr.net; "
                "connect-src 'self'; "
                "frame-ancestors 'none'"
            )
        else:
            # API JSON uniquement : aucune ressource ne doit être chargée par un
            # navigateur directement depuis ce service.
            response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        if self._force_https:
            # TLS est terminé par le reverse proxy/hébergeur — voir
            # docs/production-deployment.md (§ HTTPS). HSTS n'est activé que
            # lorsque `ENVIRONMENT=production`, pour ne jamais gêner le dev local.
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response
