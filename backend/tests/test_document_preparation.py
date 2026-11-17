from collections import Counter
import re
import pytest
from pydantic import ValidationError
from kusys.documents.preparation import prepare_blocks, validate_and_materialize
from kusys.documents.service import DocumentService


def block(key, text, page=1, y=100, kind="paragraph"):
    return {"id": key, "text": text, "page": page, "kind": kind, "coordinates": {"x0": 30, "x1": 400, "y0": y, "y1": y+12}}


def test_requirement_id_body_and_status_stay_together():
    originals = [block("a", "SYS1-01 Teilerkennung", y=100), block("b", "Das System muss Teile erkennen.", y=115), block("c", "ADVA PM APPROVED", y=130), block("d", "SYS1-02 Zweite Anforderung", y=160)]
    out = prepare_blocks(originals)
    assert out["groups"][0]["source_ids"] == ["a", "b", "c"]
    assert out["groups"][0]["text"] == "\n".join(x["text"] for x in originals[:3])
    assert out["groups"][1]["source_ids"] == ["d"]
    assert out["metrics"]["source_coverage"] == "100%"


@pytest.mark.parametrize("ids", [["a"], ["a", "a", "b"], ["a", "b", "unknown"], ["b", "a"]])
def test_rejects_lost_duplicated_foreign_or_reordered_sources(ids):
    originals = [block("a", "Text A"), block("b", "Text B")]
    with pytest.raises(ValueError):
        validate_and_materialize(originals, {"groups": [{"source_ids": ids, "kind": "paragraph", "reason": "test"}]})


def test_rejects_model_rewriting_source_text():
    with pytest.raises(ValidationError):
        validate_and_materialize([block("a", "Original")], {"groups": [{"source_ids": ["a"], "reason": "test", "text": "Erfundener Inhalt"}]})


def test_rejects_distinct_requirements_in_same_group():
    originals = [block("a", "SYS1-01 Erste Forderung"), block("b", "SYS1-02 Zweite Forderung")]
    with pytest.raises(ValueError, match="Verschiedene"):
        validate_and_materialize(originals, {"groups": [{"source_ids": ["a", "b"], "reason": "test"}]})


def test_model_can_reconstruct_cross_page_continuation_with_page_provenance():
    originals = [block("a", "Das System muss die", page=1), block("header", "Seite 2", page=2, kind="context"), block("b", "Protokolle archivieren.", page=2)]
    class Model:
        def run_role(self, role, context, schema):
            assert role == "document_preparer"
            assert len(context["blocks"]) == 3
            ids = [b["id"] for b in context["blocks"]]
            return {"groups": [{"source_ids": [ids[0], ids[2]], "reason": "Satzfortsetzung über Seitenumbruch"}, {"source_ids": [ids[1]], "kind": "context", "reason": "Kopfzeile"}]}
    out = prepare_blocks(originals, Model())
    assert out["method"] == "model"
    assert out["groups"][0]["pages"] == [1, 2]
    assert len(out["groups"][0]["sources"]) == 2
    assert "Seite 2" not in out["groups"][0]["text"]


def test_headings_and_page_furniture_are_not_merged_into_requirements():
    originals = [block("a", "SYS1-01 Kurzer Titel", y=100), block("b", "PLP – Dokumentkopf", y=118), block("c", "5 Softwareanforderungen", y=135, kind="heading")]
    assert len(prepare_blocks(originals)["groups"]) == 3


def test_native_pdf_preserves_all_text_and_table_rows(tmp_path, monkeypatch):
    import fitz
    monkeypatch.setattr("kusys.documents.service.shutil.which", lambda value: None)
    doc = fitz.open()
    page = doc.new_page()
    for x in (30, 160, 450): page.draw_line((x,100),(x,190))
    for y in (100,130,160,190): page.draw_line((30,y),(450,y))
    page.insert_text((35,120), "ID")
    page.insert_text((165,120), "Beschreibung")
    page.insert_text((35,150), "REQ-01")
    page.insert_text((165,150), "Das System muss Texte erhalten.")
    page.insert_text((35,180), "REQ-02")
    page.insert_text((165,180), "Das System soll Tabellen erhalten.")
    path = tmp_path / "native.pdf"
    doc.save(path); doc.close()
    blocks, meta = DocumentService().extract(path)
    with fitz.open(path) as original:
        native = original[0].get_text("text")
    tokens = lambda text: Counter(re.findall(r"\w+|[^\w\s|]", text))
    assert tokens("\n".join(x.source_text for x in blocks)) == tokens(native)
    assert any(x.block_type == "table_row" and "REQ-01" in x.source_text and "Texte" in x.source_text for x in blocks)
    assert all(x.text_source == "native" for x in blocks)
    assert meta["layout_version"] == "layout-v2"


def test_wrapped_german_nouns_and_abbreviations_stay_in_paragraph():
    originals = [block("a", "Angefragte Leistung: Umsetzung bzw.", y=100), block("b", "Absicherung des Basisumfangs und", y=115), block("c", "Dokumentation.", y=130)]
    assert prepare_blocks(originals)["groups"][0]["source_ids"] == ["a", "b", "c"]


def test_generic_customer_ids_are_kept_separate():
    originals = [block("a", "B-01 | Basisumfang", y=100), block("b", "Alle Leistungen sind anzubieten.", y=120), block("c", "B-02 | Lokaler Betrieb", y=155), block("d", "Die Daten bleiben lokal.", y=175)]
    out = prepare_blocks(originals)
    assert [x["source_ids"] for x in out["groups"]] == [["a", "b"], ["c", "d"]]


def test_model_repairs_missing_duplicate_and_foreign_ids_without_losing_provenance():
    originals=[block("original-long-id-a","Original A"),block("original-long-id-b","Original B")]
    class Model:
        calls=0
        def run_role(self, role, context, schema):
            self.calls+=1
            a,b=context["allowed_source_ids"]
            if self.calls==1:
                return {"groups":[{"source_ids":[a,a,"foreign"],"reason":"invalid"}]}
            assert context["correction"]["duplicate_ids"]==[a]
            assert context["correction"]["foreign_id_count"]==1
            return {"groups":[{"source_ids":[a,b],"reason":"repaired"}]}
    model=Model()
    out=prepare_blocks(originals,model)
    assert model.calls==2
    assert out["groups"][0]["source_ids"]==[b["id"] for b in originals]
    assert out["groups"][0]["text"]=="Original A\nOriginal B"
    assert out["metrics"]["model_attempts"]==2


def test_invalid_model_grouping_stops_after_one_repair():
    class Model:
        calls=0
        def run_role(self,role,context,schema):
            self.calls+=1
            return {"groups":[{"source_ids":["foreign"],"reason":"invalid"}]}
    model=Model()
    with pytest.raises(ValueError,match="Zusammenführungen"):
        prepare_blocks([block("original","Unverändert")],model)
    assert model.calls==2


def test_sparse_merge_plan_keeps_all_unmentioned_blocks_once():
    originals=[block("a","Anfang"),block("b","Fortsetzung"),block("header","Kopf",kind="context"),block("c","Ende")]
    class Model:
        def run_role(self,role,context,schema):
            ids=context["allowed_source_ids"]
            return {"groups":[{"source_ids":ids[:2],"reason":"Ein Absatz"}]}
    out=prepare_blocks(originals,Model())
    assert [g["source_ids"] for g in out["groups"]]==[["a","b"],["header"],["c"]]
    assert Counter(sid for group in out["groups"] for sid in group["source_ids"])==Counter(b["id"] for b in originals)
    assert out["metrics"]["model_attempts"]==1


def test_empty_merge_plan_preserves_every_original_text_and_checksum():
    originals=[block("a","Original A"),block("b","Original B")]
    class Model:
        def run_role(self,role,context,schema): return {"groups":[]}
    out=prepare_blocks(originals,Model())
    assert [g["text"] for g in out["groups"]]==[b["text"] for b in originals]
    assert all(g["sources"][0]["checksum"] for g in out["groups"])
