import json

from backend.app.ai.llm.exceptions import LLMProviderError
from backend.app.ai.llm.gemini_provider import GeminiProvider


class VertexProvider(GeminiProvider):
    name = "vertex"

    def __init__(
        self,
        project: str,
        location: str,
        model: str,
        temperature: float,
        max_tokens: int,
        request_timeout_seconds: float = 60.0,
        *,
        enabled: bool = False,
        service_account_email: str = "",
        service_account_json: str | None = None,
    ) -> None:
        super().__init__(None, model, temperature, max_tokens, request_timeout_seconds)
        self._project, self._location = project, location
        self._enabled = enabled
        self._service_account_email = service_account_email.strip()
        self._service_account_json = service_account_json

    def _client(self):
        if not self._enabled or not all((self._project.strip(), self._location.strip(), self._model.strip())):
            raise LLMProviderError("Le fournisseur IA n'est pas configure")
        if self._client_instance is not None:
            return self._client_instance
        try:
            import google.auth
            from google import genai
            from google.genai import types

            scopes = ["https://www.googleapis.com/auth/cloud-platform"]
            if self._service_account_json:
                info = json.loads(self._service_account_json)
                if (
                    info.get("type") != "service_account"
                    or info.get("client_email") != self._service_account_email
                    or info.get("project_id") != self._project
                ):
                    raise ValueError("Vertex service account configuration mismatch")
                credentials, credential_project = google.auth.load_credentials_from_dict(
                    info,
                    scopes=scopes,
                )
                if credential_project and credential_project != self._project:
                    raise ValueError("Vertex credential project mismatch")
            else:
                credentials, _ = google.auth.default(scopes=scopes)
            self._client_instance = genai.Client(
                enterprise=True,
                vertexai=True,
                project=self._project,
                location=self._location,
                credentials=credentials,
                http_options=types.HttpOptions(
                    api_version="v1",
                    timeout=max(1, int(self._request_timeout_seconds * 1000)),
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            )
        except Exception as exc:
            raise LLMProviderError("Le fournisseur IA Vertex est indisponible") from exc
        return self._client_instance