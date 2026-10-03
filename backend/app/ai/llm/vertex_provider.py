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
    ) -> None:
        super().__init__(None, model, temperature, max_tokens, request_timeout_seconds)
        self._project, self._location = project, location
        self._enabled = enabled

    def _client(self):
        if not self._enabled or not all((self._project.strip(), self._location.strip(), self._model.strip())):
            raise LLMProviderError("Le fournisseur IA n'est pas configure")
        if self._client_instance is not None:
            return self._client_instance
        try:
            import google.auth
            from google import genai
            from google.genai import types

            credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
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