"""Exact-input checkpoints, including safe import of the original diagnostic format."""
import hashlib
import json
from copy import deepcopy
from kusys.analysis.prompts import PROMPTS, PROMPT_VERSION


def input_key(role, context, schema, provider):
    payload = {"role": role, "context": context, "schema": schema.model_json_schema(),
        "prompt": provider.effective_prompt(role) if callable(getattr(provider,"effective_prompt",None)) else PROMPTS[role], "prompt_version": PROMPT_VERSION,
        "provider": provider.provider_id, "model": provider.model_id, "endpoint": getattr(provider, "endpoint", "")}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def source_keys(context):
    return [str(x.get("key", x.get("id", ""))) for field in ("sections", "requirements", "system_requirements", "work_packages") for x in context.get(field, [])]


class Checkpoints:
    def __init__(self, entries=(), allow_legacy=False):
        self.exact = {}
        self.legacy = []
        self.allow_legacy = allow_legacy
        self.position = 0
        for step in entries:
            if ":round-" not in step.step_name or step.step_name.startswith("review_round:"):
                continue
            role, round_no = step.step_name.split(":round-")
            value = step.result_json or {}
            outputs = iter(value.get("outputs", []))
            for event in value.get("events", []):
                if event.get("status") not in {"succeeded", "cached"}:
                    continue
                output = next(outputs, None)
                if output is None:
                    break
                item = {"role": role, "round": int(round_no), "event": event, "output": output}
                self.legacy.append(item)
                if event.get("input_key"):
                    self.exact[event["input_key"]] = output

    def get(self, key, role, round_no, context, schema):
        output = self.exact.get(key)
        # Legacy runs predate input hashes. Import only the unchanged, ordered prefix;
        # the service additionally requires unchanged project/review inputs.
        if output is None and self.allow_legacy and self.position < len(self.legacy):
            item = self.legacy[self.position]
            event = item["event"]
            if (not event.get("input_key") and item["role"] == role and item["round"] == round_no
                    and event.get("source_keys") == source_keys(context)
                    and event.get("batch") == context.get("batch")
                    and event.get("target_keys", []) == context.get("target_keys", [])):
                output = item["output"]
            else:
                self.allow_legacy = False
        self.position += 1
        if output is None:
            return None
        try:
            return deepcopy(schema.model_validate(output).model_dump(mode="json"))
        except ValueError:
            self.allow_legacy = False
            return None
