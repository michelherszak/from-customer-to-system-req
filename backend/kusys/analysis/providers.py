"""All production role execution goes through the private CrewAI runtime."""
from __future__ import annotations
import json
import urllib.error
import urllib.request
from typing import Protocol
from pydantic import BaseModel
from kusys.common.config import get_settings
from kusys.analysis.prompts import PROMPTS


class AIProvider(Protocol):
    provider_id: str
    model_id: str
    def run_role(self, role: str, context: dict, schema: type[BaseModel]) -> dict: ...


class ProviderExecutionError(ValueError):
    """Contains only a curated diagnostic, never raw SDK response text."""
    def __init__(self, message, code, http_status=None, validation_issues=None, upstream_status=None):
        super().__init__(message)
        self.diagnostic_code = code
        self.http_status = http_status
        self.diagnostic_message = message
        self.validation_issues = validation_issues or []
        self.upstream_status = upstream_status if isinstance(upstream_status, int) else None


class CrewAIProvider:
    engine = "crewai"
    def __init__(self, provider_id: str, endpoint: str, api_key: str, model_id: str, timeout_seconds: int = 180):
        self.provider_id = provider_id
        self.endpoint = endpoint
        self.api_key = api_key
        self.model_id = model_id
        self.timeout_seconds = timeout_seconds
        self.input_tokens = self.output_tokens = 0
        self.instructions = {}

    def effective_prompt(self, role):
        extra = self.instructions.get(role, "").strip()
        return PROMPTS[role] + ("\nZusätzliche Firmenanweisungen (Rollenabgrenzung, Quellenregeln und Ausgabeschema bleiben verbindlich):\n" + extra if extra else "")

    def run_role(self, role: str, context: dict, schema: type[BaseModel]) -> dict:
        settings = get_settings()
        if not settings.crew_runtime_token:
            raise ValueError("CrewAI-Laufzeit ist nicht konfiguriert")
        payload = {"provider": self.provider_id, "endpoint": self.endpoint, "api_key": self.api_key,
                   "model": self.model_id, "role": role, "prompt": self.effective_prompt(role), "context": context}
        request = urllib.request.Request(settings.crew_runtime_url.rstrip("/") + "/execute",
            data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", "Authorization": "Bearer " + settings.crew_runtime_token}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                output = json.load(response)
        except urllib.error.HTTPError as exc:
            try:
                failure = json.load(exc)
                code = failure.get("error")
            except (ValueError, TypeError):
                code = None
                failure = {}
            messages = {
                "cloud_billing_required": "Cloud-Guthaben ist zu niedrig oder die Abrechnung ist nicht freigeschaltet. Beim Modellanbieter Guthaben und Abrechnung prüfen; anschließend ab dem letzten Checkpoint fortsetzen.",
                "cloud_context_exceeded": "Das Eingabepaket überschreitet das Kontextlimit des Cloud-Modells. Paketgröße und Review-Kontext reduzieren.",
                "cloud_request_invalid": "Der Cloud-Anbieter hat die Anfrage als ungültig abgewiesen (HTTP 400). Modellparameter und Anfrageformat prüfen.",
                "cloud_timeout": "Zeitlimit bei der Cloud-Ableitung überschritten. Die Aufgabe muss in kleinere Teile aufgeteilt werden.",
                "cloud_response_invalid": "Die Modellantwort passt nicht zum Ausgabeschema. Ableitung wurde nicht übernommen.",
                "cloud_workspace_required": "Anthropic: Der API-Schlüssel ist keinem Workspace zugeordnet. Bitte einen API-Schlüssel aus dem gewünschten Workspace hinterlegen.",
                "cloud_auth_failed": "Cloud-Anbieter hat den API-Schlüssel abgewiesen. Schlüssel und Anbieter prüfen.",
                "cloud_quota_exceeded": "Cloud-Kontingent oder Rate-Limit erreicht. Anbieter-Kontingent prüfen oder später erneut versuchen.",
                "cloud_model_unavailable": "Das ausgewählte Modell ist für diesen Anbieterzugang nicht verfügbar.",
                "unauthorized": "Interne CrewAI-Authentifizierung fehlgeschlagen.",
            }
            raise ProviderExecutionError(messages.get(code, f"CrewAI-Ausführung fehlgeschlagen (HTTP {exc.code}); Modellzugang und Laufzeit prüfen"), code if code in messages else "crewai_execution_failed", exc.code, failure.get("validation_issues", []) if code == "cloud_response_invalid" else [], failure.get("upstream_status")) from None
        except (urllib.error.URLError, TimeoutError):
            raise ProviderExecutionError("CrewAI-Laufzeit nicht erreichbar oder Zeitlimit überschritten", "runtime_unreachable") from None
        if output.get("engine") != "crewai":
            raise ValueError("Ungültige Antwort der CrewAI-Laufzeit")
        validated = schema.model_validate(output["result"]).model_dump(mode="json")
        self.input_tokens += int(output.get("input_tokens") or 0)
        self.output_tokens += int(output.get("output_tokens") or 0)
        return validated
