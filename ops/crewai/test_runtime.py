"""Real CrewAI execution with an in-memory LLM; no cloud key or network needed."""
import json
import os
import threading
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from crewai import BaseLLM
from runtime import execute, Handler, build_llm, validation_issues, SCHEMAS
from pydantic import ValidationError
from contracts import Plan

class StubLLM(BaseLLM):
    def __init__(self, result):
        super().__init__(model="synthetic-test-model")
        self.result = result
        self.calls = 0
    def call(self, messages, tools=None, callbacks=None, available_functions=None, **kwargs):
        self.calls += 1
        return "Final Answer: " + json.dumps(self.result)
    def supports_function_calling(self): return False
    def supports_stop_words(self): return False
    def get_context_window_size(self): return 100000


class RuntimeTests(unittest.TestCase):
    def test_real_crewai_executes_all_five_role_tasks(self):
        req = {"requirements":[{"key":"REQ-1","title":"Transport","text":"Teile transportieren","source_section_id":"s1"}]}
        design = {"system_requirements":[{"key":"SYS-1","title":"Steuerung","text":"Der Transportdienst verarbeitet einen Auftrag atomar.","parent_keys":["REQ-1"],"rationale":"Auftragsverarbeitung erforderlich","verification_method":"test","verification_criterion":"Ein Auftrag erzeugt genau ein Ergebnis."}],"architecture":[{"key":"ARC-1","name":"Transportdienst","description":"Verarbeitet Aufträge","covers":["SYS-1"]}]}
        plan = {"work_packages":[{"key":"AP-1","name":"Transportdienst umsetzen","description":"Dienst und Verifikation","role":"Software Engineering","min_hours":8,"likely_hours":12,"max_hours":16,"phase":"Realisierung","system_requirement_keys":["SYS-1"],"estimate_basis":"Referenzaufwand"}]}
        assessment = {"target_key":"SYS-1","owner":"systems_engineer","verdict":"accepted",**{k:"Konkret geprüft" for k in ("source_fidelity","necessity","completeness","feasibility","verifiability","sizing")}}
        samples = {"requirements_engineer":req,"systems_engineer":design,"work_planner":plan,"review_engineer":{"summary":"Geprüft","assessments":[assessment]},"document_preparer":{"groups":[{"source_ids":["s1"],"reason":"Ein Absatz"}]}}
        for role, sample in samples.items():
            with self.subTest(role=role):
                llm = StubLLM(sample)
                output = execute({"role":role,"prompt":"Liefere das verlangte JSON.","context":{"source":"synthetischer Test"}}, llm_override=llm)
                self.assertEqual(output["engine"],"crewai")
                self.assertEqual(output["version"],"1.15.39")
                self.assertGreater(llm.calls,0)
                self.assertEqual(set(output["result"]),set(sample) | ({"clarifications"} if role=="requirements_engineer" else set()))

    def test_schema_repair_is_targeted_bounded_and_redacted(self):
        try:
            Plan.model_validate({"work_packages":[{"key":"SECRET-CUSTOMER-TEXT","phase":"SECRET-INVALID-PHASE"}]})
        except ValidationError as exc:
            invalid = exc
        issues = validation_issues(invalid)
        self.assertTrue(any(x["path"] == "work_packages.0.phase" for x in issues))
        self.assertNotIn("SECRET",json.dumps(issues))
        payload={"role":"work_planner","prompt":"Test","context":{"system_requirements":[]}}
        with patch("runtime.execute_once",side_effect=[invalid,{"result":"valid"}]) as run:
            self.assertEqual(execute(payload),{"result":"valid"})
            self.assertEqual(run.call_count,2)
            self.assertEqual(run.call_args.args[0]["context"]["output_correction"]["issues"],issues)
        with patch("runtime.execute_once",side_effect=invalid) as run:
            with self.assertRaises(ValidationError): execute(payload)
            self.assertEqual(run.call_count,2)
        with patch("runtime.execute_once",side_effect=RuntimeError("Authentication failed")) as run:
            with self.assertRaises(RuntimeError): execute(payload)
            self.assertEqual(run.call_count,1)

    def test_native_cloud_sdk_adapters_construct_without_network(self):
        for provider, model, endpoint in (("openai","gpt-5.4-mini","https://api.openai.com/v1"), ("anthropic","claude-sonnet-5-5","https://api.anthropic.com"), ("gemini","gemini-3.8-flash","https://generativelanguage.googleapis.com/v1beta")):
            with self.subTest(provider=provider):
                llm = build_llm({"provider":provider,"model":model,"endpoint":endpoint,"api_key":"synthetic-not-a-real-key"})
                self.assertIsInstance(llm, BaseLLM)

    def test_openai_adapter_sends_completion_token_limit(self):
        import httpx
        from openai import OpenAI
        captured=[]
        def handle(request):
            captured.append(json.loads(request.content))
            return httpx.Response(200,json={"id":"synthetic","object":"chat.completion","created":0,"model":"gpt-5.4","choices":[{"index":0,"message":{"role":"assistant","content":"OK"},"finish_reason":"stop"}],"usage":{"prompt_tokens":4,"completion_tokens":1,"total_tokens":5}})
        llm=build_llm({"provider":"openai","model":"gpt-5.4","api_key":"synthetic","endpoint":"https://api.openai.com/v1"})
        with httpx.Client(transport=httpx.MockTransport(handle)) as client:
            native=OpenAI(api_key="synthetic",http_client=client)
            with patch.object(llm,"_get_sync_client",return_value=native):
                self.assertEqual(llm.call([{"role":"user","content":"Reply OK"}]),"OK")
        self.assertEqual(captured[0]["max_completion_tokens"],24000)
        self.assertNotIn("max_tokens",captured[0])

    def test_all_role_schemas_have_closed_objects_for_openai(self):
        from openai.lib._pydantic import to_strict_json_schema
        def check(node):
            if isinstance(node, dict):
                if node.get("type")=="object":
                    self.assertIs(node.get("additionalProperties"),False)
                    self.assertEqual(set(node.get("required",[])),set(node.get("properties",{})))
                for value in node.values():check(value)
            elif isinstance(node,list):
                for value in node:check(value)
        for role,schema in SCHEMAS.items():
            with self.subTest(role=role):check(to_strict_json_schema(schema))

    def test_private_http_requires_token_and_hides_exception_details(self):
        server = ThreadingHTTPServer(("127.0.0.1",0), Handler)
        thread = threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with patch.dict(os.environ,{"KUSYS_CREW_TOKEN":"internal-test-token"}):
                with self.assertRaises(HTTPError) as denied:
                    urlopen(Request(base+"/execute",data=b"{}"))
                self.assertEqual(denied.exception.code,401)
                request = Request(base+"/execute",data=json.dumps({"role":"requirements_engineer","api_key":"fake-test-key"}).encode(),headers={"Authorization":"Bearer internal-test-token"})
                with patch("runtime.execute",side_effect=RuntimeError("private-secret-must-not-leak")):
                    with self.assertRaises(HTTPError) as failed: urlopen(request)
                self.assertEqual(failed.exception.code,502)
                self.assertNotIn("private-secret",failed.exception.read().decode())
                with patch("runtime.execute",side_effect=RuntimeError("include anthropic-workspace-id; private-secret")):
                    with self.assertRaises(HTTPError) as workspace: urlopen(request)
                detail=json.loads(workspace.exception.read())
                self.assertEqual(detail["error"],"cloud_workspace_required")
                self.assertNotIn("private-secret",str(detail))
                class BadRequestError(Exception):
                    status_code=400
                for message,expected in (("Your credit balance is too low; private-secret", "cloud_billing_required"), ("prompt is too long; private-secret", "cloud_context_exceeded"), ("invalid parameter; private-secret", "cloud_request_invalid")):
                    with patch("runtime.execute",side_effect=BadRequestError(message)):
                        with self.assertRaises(HTTPError) as bad: urlopen(request)
                    detail=json.loads(bad.exception.read())
                    self.assertEqual(detail["error"],expected)
                    self.assertEqual(detail["upstream_status"],400)
                    self.assertNotIn("private-secret",str(detail))
        finally:
            server.shutdown(); server.server_close(); thread.join()

if __name__ == "__main__": unittest.main()
