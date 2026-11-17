import io
import json
from unittest.mock import patch
from kusys.analysis.providers import CrewAIProvider
from kusys.analysis.contracts import Requirements
from kusys.common.config import get_settings


def test_provider_uses_private_crewai_runtime_and_validates_result(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings,"crew_runtime_token","test-internal")
    monkeypatch.setattr(settings,"crew_runtime_url","http://private-runtime")
    sample={"requirements":[{"key":"REQ-1","title":"Transport","text":"Teile transportieren","source_section_id":"s1"}]}
    response=io.BytesIO(json.dumps({"engine":"crewai","result":sample,"input_tokens":50,"output_tokens":20}).encode())
    provider=CrewAIProvider("openai","https://api.openai.com/v1","cloud-key-for-test","gpt-5.4-mini")
    with patch("urllib.request.urlopen",return_value=response) as send:
        out=provider.run_role("requirements_engineer",{"sections":[]},Requirements)
    request=send.call_args.args[0]
    assert request.full_url=="http://private-runtime/execute"
    assert request.get_header("Authorization")=="Bearer test-internal"
    assert json.loads(request.data)["model"]=="gpt-5.4-mini"
    assert out["requirements"][0]["key"]=="REQ-1"
    assert provider.input_tokens==50 and provider.output_tokens==20


def test_upstream_secrets_are_not_forwarded_in_errors(monkeypatch):
    import pytest
    from urllib.error import HTTPError
    settings=get_settings()
    monkeypatch.setattr(settings,"crew_runtime_token","test-internal")
    error=HTTPError("http://private/execute",502,"failed",{},io.BytesIO(json.dumps({"error":"cloud_auth_failed","detail":"secret-must-not-leak"}).encode()))
    with patch("urllib.request.urlopen",side_effect=error):
        with pytest.raises(ValueError,match="API-Schlüssel abgewiesen") as failed:
            CrewAIProvider("openai","https://api.openai.com/v1","test-secret","gpt-5.4-mini").run_role("requirements_engineer",{},Requirements)
    assert "secret-must-not-leak" not in str(failed.value)


def test_unscoped_anthropic_key_has_actionable_message(monkeypatch):
    import pytest
    from urllib.error import HTTPError
    monkeypatch.setattr(get_settings(),"crew_runtime_token","test-internal")
    error=HTTPError("http://private/execute",502,"failed",{},io.BytesIO(b'{"error":"cloud_workspace_required","type":"BadRequestError"}'))
    with patch("urllib.request.urlopen",side_effect=error):
        with pytest.raises(ValueError,match="Workspace zugeordnet"):
            CrewAIProvider("anthropic","https://api.anthropic.com","test","claude-sonnet-5-5").run_role("requirements_engineer",{},Requirements)


def test_schema_diagnostics_reach_workflow_without_raw_upstream_content(monkeypatch):
    import pytest
    from urllib.error import HTTPError
    from kusys.analysis.providers import ProviderExecutionError
    monkeypatch.setattr(get_settings(),"crew_runtime_token","test-internal")
    detail={"error":"cloud_response_invalid","validation_issues":[{"path":"work_packages.0.phase","type":"literal_error"}],"raw":"private-customer-content"}
    error=HTTPError("http://private/execute",502,"failed",{},io.BytesIO(json.dumps(detail).encode()))
    with patch("urllib.request.urlopen",side_effect=error):
        with pytest.raises(ProviderExecutionError) as failed:
            CrewAIProvider("anthropic","https://api.anthropic.com","test","claude-sonnet-5-5").run_role("work_planner",{},Requirements)
    assert failed.value.validation_issues==detail["validation_issues"]
    assert failed.value.http_status==502
    assert "private-customer-content" not in str(failed.value)


def test_billing_failure_is_actionable_and_keeps_upstream_status(monkeypatch):
    import pytest
    from urllib.error import HTTPError
    from kusys.analysis.providers import ProviderExecutionError
    monkeypatch.setattr(get_settings(),"crew_runtime_token","test-internal")
    error=HTTPError("http://private/execute",502,"failed",{},io.BytesIO(b'{"error":"cloud_billing_required","upstream_status":400}'))
    with patch("urllib.request.urlopen",side_effect=error):
        with pytest.raises(ProviderExecutionError,match="Cloud-Guthaben") as failed:
            CrewAIProvider("anthropic","https://api.anthropic.com","test","claude-sonnet-5-5").run_role("requirements_engineer",{},Requirements)
    assert failed.value.upstream_status==400
    assert failed.value.diagnostic_code=="cloud_billing_required"


def test_agent_instructions_are_sent_to_model_and_invalidate_role_checkpoint(monkeypatch):
    from kusys.analysis.checkpoints import input_key
    monkeypatch.setattr(get_settings(),"crew_runtime_token","test-internal")
    provider=CrewAIProvider("anthropic","https://api.anthropic.com","test","test-model")
    before=input_key("requirements_engineer",{},Requirements,provider)
    system_before=input_key("systems_engineer",{},Requirements,provider)
    provider.instructions={"requirements_engineer":"Use SI units."}
    assert before!=input_key("requirements_engineer",{},Requirements,provider)
    assert system_before==input_key("systems_engineer",{},Requirements,provider)
    response=io.BytesIO(json.dumps({"engine":"crewai","result":{"requirements":[{"key":"REQ-1","title":"Data","text":"Store data","source_section_id":"s1"}]}}).encode())
    with patch("urllib.request.urlopen",return_value=response) as send:
        provider.run_role("requirements_engineer",{},Requirements)
    prompt=json.loads(send.call_args.args[0].data)["prompt"]
    assert "Use SI units." in prompt
    assert "verbindlich" in prompt
