"""Lossless document reconstruction: models choose source IDs, never rewrite text."""
from __future__ import annotations
from collections import Counter
import hashlib
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class Group(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_ids: list[str] = Field(min_length=1)
    kind: Literal["paragraph", "heading", "table_row", "context"] = "paragraph"
    reason: str
    uncertain: bool = False

class Grouping(BaseModel):
    model_config = ConfigDict(extra="forbid")
    groups: list[Group] = Field(min_length=1)

class MergePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    groups: list[Group]


def complete_merge_plan(blocks, proposal):
    """Preserve unmentioned sources as singletons; never repair invalid references."""
    parsed = MergePlan.model_validate(proposal)
    positions = {b["id"]: i for i, b in enumerate(blocks)}
    used = set()
    groups = []
    for group in parsed.groups:
        for sid in group.source_ids:
            if sid not in positions:
                raise ValueError("Zusammenführung enthält fremde Block-IDs")
            if sid in used:
                raise ValueError("Zusammenführung verwendet Block-IDs mehrfach")
            used.add(sid)
        groups.append(group.model_dump())
    for block in blocks:
        if block["id"] not in used:
            groups.append({"source_ids": [block["id"]], "kind": block["kind"] if block["kind"] in {"paragraph", "heading", "table_row", "context"} else "paragraph",
                "reason": "Originalblock ohne Zusammenführung unverändert erhalten", "uncertain": False})
    groups.sort(key=lambda group: positions[group["source_ids"][0]])
    result = {"groups": groups}
    validate_and_materialize(blocks, result)
    return result


REQ_ID = re.compile(r"^(?:[A-Z][A-Z0-9]{0,10}(?:[.-][A-Z]{1,6})?[-.]\d+[a-z]?)\b", re.I)
STATUS = re.compile(r"(?:APPROVED|DISCUSS|REJECTED|FREIGEGEBEN)\s*$", re.I)


def layout_groups(blocks: list[dict]) -> dict:
    """Conservative merge of adjacent fragments, never drop a source block."""
    groups = []
    by_id = {b["id"]: b for b in blocks}
    for block in blocks:
        text = block["text"].strip()
        previous = groups[-1] if groups else None
        prior = by_id[previous["source_ids"][-1]] if previous else None
        join = False
        if prior and previous["kind"] not in {"heading", "context"} and block["kind"] not in {"heading", "table_row", "context"}:
            first = by_id[previous["source_ids"][0]]
            old = prior["text"].strip()
            a, b = prior.get("coordinates") or {}, block.get("coordinates") or {}
            gap = b.get("y0", 1e9) - a.get("y1", 0)
            same_column = abs(a.get("x0", -1e6) - b.get("x0", 1e6)) < 16
            close = prior["page"] == block["page"] and same_column and 0 <= gap <= 16
            height_a = (a.get("y1", 0) - a.get("y0", 0)) / max(1, prior["text"].count("\n") + 1)
            height_b = (b.get("y1", 0) - b.get("y0", 0)) / max(1, block["text"].count("\n") + 1)
            tight = close and gap <= min(8, max(2, height_a * .85)) and abs(height_a - height_b) <= max(2, min(height_a, height_b) * .2)
            continuation = old and not re.search(r"[.!?:;]$", old) and text and (text[0].islower() or text.startswith(("(", ",")))
            # Old PDF extractors frequently split the requirement ID, text and status columns.
            furniture = bool(re.match(r"^(?:PLP [–-]|A-SPICE|Abb\.|Self-Documenting Workbench \||ANGEBOTSANFRAGE /|\d+(?:\.\d+)*\s+[A-ZÄÖÜ])", text))
            req_row = bool(REQ_ID.match(first["text"])) and not STATUS.search(old) and not furniture and abs(gap) <= 35 and (len(previous["source_ids"]) == 1 or bool(STATUS.search(text)))
            join = not REQ_ID.match(text) and not furniture and (tight or close and continuation or req_row and prior["page"] == block["page"])
        if join:
            previous["source_ids"].append(block["id"])
            previous["reason"] = "Zusammengehörige Absatz-/Anforderungsfragmente anhand Layout und ID"
        else:
            groups.append({"source_ids": [block["id"]], "kind": block["kind"] if block["kind"] in {"paragraph", "heading", "table_row", "context"} else "paragraph", "reason": "Originalabschnitt unverändert", "uncertain": False})
    return {"groups": groups}


def validate_and_materialize(blocks, grouping):
    parsed = Grouping.model_validate(grouping)
    ids = [b["id"] for b in blocks]
    given = [sid for group in parsed.groups for sid in group.source_ids]
    if Counter(given) != Counter(ids) or len(ids) != len(set(ids)):
        counts = Counter(given)
        missing = sum(sid not in counts for sid in ids)
        duplicate = sum(max(0, count - 1) for count in counts.values())
        foreign = sum(count for sid, count in counts.items() if sid not in set(ids))
        raise ValueError(f"Aufbereitung muss jeden Originalblock genau einmal enthalten; keine fremden IDs (fehlend: {missing}, mehrfach: {duplicate}, fremd: {foreign})")
    by_id = {b["id"]: b for b in blocks}
    position = {sid: i for i, sid in enumerate(ids)}
    firsts = []
    out = []
    for group in parsed.groups:
        indexes = [position[sid] for sid in group.source_ids]
        if indexes != sorted(indexes):
            raise ValueError("Quellen innerhalb eines Abschnitts stehen nicht in Originalreihenfolge")
        firsts.append(indexes[0])
        sources = [by_id[sid] for sid in group.source_ids]
        requirement_ids = {match.group(0) for source in sources if (match := REQ_ID.match(source["text"].strip()))}
        if len(requirement_ids) > 1:
            raise ValueError("Verschiedene Anforderungs-IDs dürfen nicht zu einem Absatz zusammengeführt werden")
        # No generated body text is accepted: reconstruct exclusively from original strings.
        text = "\n".join(x["text"] for x in sources)
        out.append({**group.model_dump(), "text": text, "pages": list(dict.fromkeys(x["page"] for x in sources if x["page"] is not None)), "sources": [{"id": x["id"], "page": x["page"], "coordinates": x.get("coordinates"), "checksum": hashlib.sha256(x["text"].encode()).hexdigest()} for x in sources]})
    if firsts != sorted(firsts):
        raise ValueError("Abschnitte stehen nicht in Dokumentreihenfolge")
    return out


def prepare_blocks(blocks, provider=None):
    if not blocks:
        raise ValueError("Keine Textblöcke vorhanden")
    # Full-document context; reject oversized documents explicitly rather than truncate.
    if sum(len(b["text"]) for b in blocks) > 240000:
        raise ValueError("Dokument ist für die vollständige Modellaufbereitung zu groß; Dokument aufteilen")
    if len({b["id"] for b in blocks}) != len(blocks):
        raise ValueError("Originaldokument enthält doppelte Block-IDs; Extraktion prüfen")
    attempts = 0
    if provider:
        # Short opaque IDs reduce copying errors; the original provenance stays server-side.
        aliases = {f"B{i:05d}": b["id"] for i, b in enumerate(blocks, 1)}
        model_blocks = [{**b, "id": alias} for alias, b in zip(aliases, blocks)]
        context = {"blocks": model_blocks, "allowed_source_ids": list(aliases),
            "instruction": "Lies das gesamte Dokument einschließlich Layout. Gib nur sinnvolle Zusammenführungen in groups zurück. Nicht erwähnte Blöcke bleiben automatisch einzeln erhalten. groups darf leer sein. Verwende nur erlaubte IDs, jede höchstens einmal. Keine IDs erfinden, kürzen oder aus dem Dokumenttext übernehmen."}
        for attempts in (1, 2):
            grouping = provider.run_role("document_preparer", context, MergePlan)
            try:
                # Validate aliases and all grouping rules before restoring original IDs.
                restored = complete_merge_plan(model_blocks, grouping)
                for group in restored["groups"]:
                    group["source_ids"] = [aliases[sid] for sid in group["source_ids"]]
                groups = validate_and_materialize(blocks, restored)
                break
            except ValueError as exc:
                reason = "Antwort entspricht nicht dem Zusammenführungsschema" if hasattr(exc, "errors") else str(exc)
                if attempts == 2:
                    raise ValueError(f"Modell-Zusammenführungen weiterhin ungültig: {reason}. Originalblöcke bleiben unverändert; keine Prüfschritt-Revision übernommen.") from None
                try:
                    parsed = MergePlan.model_validate(grouping)
                    counts = Counter(sid for group in parsed.groups for sid in group.source_ids)
                except ValueError:
                    counts = Counter()
                context = {**context, "correction": {
                    "duplicate_ids": [sid for sid in aliases if counts[sid] > 1],
                    "foreign_id_count": sum(count for sid, count in counts.items() if sid not in aliases),
                    "validation_reason": reason,
                    "instruction": "Korrigiere nur die Zusammenführungen. Jede erwähnte ID höchstens einmal und nur erlaubte IDs verwenden, innerhalb jeder Gruppe in Originalreihenfolge; unterschiedliche Anforderungsnummern nicht zusammenführen. Nicht zu verbindende Blöcke weglassen, diese bleiben serverseitig erhalten."}}
    else:
        groups = validate_and_materialize(blocks, layout_groups(blocks))
    return {"method": "model" if provider else "layout", "groups": groups, "metrics": {"model_attempts": attempts, "original_blocks": len(blocks), "prepared_sections": len(groups), "joined_groups": sum(len(x["source_ids"]) > 1 for x in groups), "uncertain_groups": sum(x["uncertain"] for x in groups), "source_coverage": "100%"}}
