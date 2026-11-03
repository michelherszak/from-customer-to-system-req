from __future__ import annotations

from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path


def _money(value) -> str:
    return f"{Decimal(str(value)):,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", ".")


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts: list[str] = []
    def handle_data(self, data: str) -> None:
        if data.strip(): self.parts.append(data.strip())


def _html_text(value: str) -> str:
    parser = _TextExtractor(); parser.feed(value or "")
    return " ".join(parser.parts)


def _labels(language: str) -> dict[str, str]:
    if language.lower().startswith("en"):
        return {
            "offer":"Quotation","recipient":"Recipient","scope":"Scope of supply","requirement":"Requirement",
            "description":"Description","price":"Price","schedule":"Schedule","finish":"Planned completion",
            "net":"Net","vat":"VAT","gross":"Gross","validity":"Validity","days":"days","payment":"Payment plan",
            "phase":"Phase","percent":"Percent","amount":"Amount","work_packages":"Work packages",
        }
    return {
        "offer":"Angebot","recipient":"Empfänger","scope":"Leistungsumfang","requirement":"Anforderung",
        "description":"Beschreibung","price":"Preis","schedule":"Termin","finish":"Geplanter Projektabschluss",
        "net":"Netto","vat":"MwSt.","gross":"Brutto","validity":"Gültigkeit","days":"Tage","payment":"Zahlungsplan",
        "phase":"Phase","percent":"Anteil","amount":"Betrag","work_packages":"Arbeitspakete",
    }


def _add_requirements(doc, snapshot: dict, labels: dict) -> None:
    doc.add_heading(labels["scope"], 2)
    table = doc.add_table(rows=1, cols=3); table.style = "Table Grid"
    for idx, text in enumerate((labels["requirement"], labels["description"], labels["price"])):
        table.rows[0].cells[idx].text = text
    for a in snapshot["pricing"].get("attribution", []):
        row = table.add_row().cells
        row[0].text = a.get("key") or a["requirement_id"]
        row[1].text = a.get("title") or ""
        row[2].text = _money(a["sales_eur"])


def _add_schedule(doc, snapshot: dict, labels: dict) -> None:
    doc.add_heading(labels["schedule"], 2)
    doc.add_paragraph(f"{labels['finish']}: {snapshot['schedule']['project_finish']}")


def _add_price(doc, snapshot: dict, labels: dict) -> None:
    pricing = snapshot["pricing"]
    doc.add_heading(labels["price"], 2)
    table = doc.add_table(rows=0, cols=2); table.style = "Table Grid"
    for label, key in ((labels["net"],"net_eur"),(labels["vat"],"vat_eur"),(labels["gross"],"gross_eur")):
        cells=table.add_row().cells; cells[0].text=label; cells[1].text=_money(pricing[key])


def _add_custom_positions(doc, snapshot: dict, labels: dict) -> None:
    positions=snapshot.get("positions") or []
    if not positions:return
    doc.add_heading(labels["scope"],2)
    table=doc.add_table(rows=1,cols=3);table.style="Table Grid"
    table.rows[0].cells[0].text="Pos.";table.rows[0].cells[1].text=labels["description"];table.rows[0].cells[2].text=labels["price"]
    for item in positions:
        row=table.add_row().cells;row[0].text=str(item.get("position_no",""));row[1].text=str(item.get("title","")) + (("\n"+str(item.get("description"))) if item.get("description") else "");row[2].text=_money(item.get("sales_eur",0))

def _add_custom_texts(doc, snapshot: dict, language: str) -> None:
    for block in snapshot.get("text_blocks",[]):
        if str(block.get("language","de")).lower().startswith(language.lower()[:2]):
            text=_html_text(str(block.get("content_html") or ""))
            if text:doc.add_paragraph(text)

def _add_payment_plan(doc, snapshot: dict, labels: dict) -> None:
    doc.add_heading(labels["payment"], 2)
    table=doc.add_table(rows=1,cols=3); table.style="Table Grid"
    for idx,text in enumerate((labels["phase"],labels["percent"],labels["amount"])): table.rows[0].cells[idx].text=text
    for item in snapshot.get("payment_plan",[]):
        row=table.add_row().cells; row[0].text=item["phase"];row[1].text=f"{item['percent']} %";row[2].text=_money(item["amount_eur"])


def export_offer_docx(path: Path, snapshot: dict) -> Path:
    from docx import Document
    from docx.shared import Cm

    doc = Document()
    config=(snapshot.get("template") or {}).get("config_json") or {}
    margins=config.get("margins_mm") or [20,20,20,20]
    sec=doc.sections[0]
    sec.top_margin=Cm(float(margins[0])/10);sec.right_margin=Cm(float(margins[1])/10);sec.bottom_margin=Cm(float(margins[2])/10);sec.left_margin=Cm(float(margins[3])/10)
    if config.get("header_text"): sec.header.paragraphs[0].text=str(config["header_text"])
    if config.get("footer_text"): sec.footer.paragraphs[0].text=str(config["footer_text"])

    header=snapshot.get("offer_header",{})
    language=header.get("language","de");labels=_labels(language)
    customer=snapshot.get("customer",{})
    doc.add_heading(labels["offer"],0);doc.add_heading(snapshot.get("project_name","Projekt"),1)
    doc.add_paragraph(f"{header.get('offer_number',snapshot.get('offer_number',''))} · {header.get('variant',snapshot.get('variant_name',''))}")
    if customer or header.get("recipient"):
        doc.add_heading(labels["recipient"],2);doc.add_paragraph(header.get("recipient") or customer.get("company_name",""))
        if customer.get("address"):doc.add_paragraph(customer["address"])
        if customer.get("contact_name"):doc.add_paragraph(customer["contact_name"])

    _add_custom_texts(doc,snapshot,language)
    handlers={"requirements":lambda:_add_custom_positions(doc,snapshot,labels) if snapshot.get("positions") else _add_requirements(doc,snapshot,labels),"schedule_finish":lambda:_add_schedule(doc,snapshot,labels),"schedule":lambda:_add_schedule(doc,snapshot,labels),"price":lambda:_add_price(doc,snapshot,labels),"payment_plan":lambda:_add_payment_plan(doc,snapshot,labels)}
    blocks=(snapshot.get("template") or {}).get("content_blocks") or []
    rendered=set()
    if blocks:
        for block in blocks:
            if not isinstance(block,dict):continue
            if block.get("type") in {"rich_text","text"}:
                text=_html_text(str(block.get("html") or block.get("content") or ""))
                if text: doc.add_paragraph(text)
            elif block.get("type")=="system":
                key=str(block.get("placeholder") or "")
                if key in handlers: handlers[key]();rendered.add(key)
    if "requirements" not in rendered:
        (_add_custom_positions(doc,snapshot,labels) if snapshot.get("positions") else _add_requirements(doc,snapshot,labels))
    if not ({"schedule","schedule_finish"}&rendered):_add_schedule(doc,snapshot,labels)
    if "price" not in rendered:_add_price(doc,snapshot,labels)
    if "payment_plan" not in rendered:_add_payment_plan(doc,snapshot,labels)
    doc.add_paragraph(f"{labels['validity']}: {header.get('validity_days',30)} {labels['days']}")
    doc.save(path);return path


def export_offer_xlsx(path: Path, snapshot: dict, internal: bool = True) -> Path:
    from openpyxl import Workbook
    wb=Workbook(); summary=wb.active;summary.title="Zusammenfassung";p=snapshot["pricing"]
    summary.append(["Projekt",snapshot.get("project_name")]);summary.append(["Angebot",snapshot.get("offer_number")]);summary.append(["Variante",snapshot.get("variant_name")]);summary.append([]);summary.append(["Kennzahl","Wert EUR"])
    for label,key in (("Arbeitsverkauf","labor_sales_eur"),("Materialverkauf","material_sales_eur"),("Risiko","risk_eur"),("Rabatt","discount_eur"),("Netto","net_eur"),("MwSt.","vat_eur"),("Brutto","gross_eur")):summary.append([label,float(Decimal(p[key]))])
    if internal:summary.append(["Deckungsbeitrag",float(Decimal(p["margin_eur"]))])
    summary["D5"]="Prüfformel Brutto";summary["E5"]="=B11+B12"  # transparent workbook check; server values remain authoritative

    req=wb.create_sheet("Anforderungen");headers=["Anforderung","Titel","Budget"]
    if internal:headers += ["Kosten","Deckungsbeitrag"]
    headers += ["Verkauf","Budgetabweichung"];req.append(headers)
    for a in p.get("attribution",[]):
        row=[a.get("key"),a.get("title"),float(Decimal(a["budget_eur"])) if a.get("budget_eur") is not None else None]
        if internal:row += [float(Decimal(a["cost_eur"])),float(Decimal(a["margin_eur"]))]
        row += [float(Decimal(a["sales_eur"])),float(Decimal(a["budget_delta_eur"])) if a.get("budget_delta_eur") is not None else None];req.append(row)

    work=wb.create_sheet("Arbeitspakete");work.append(["ID","Name","Rolle","Phase","Planstunden","Max FTE","Anforderungen"])
    for x in snapshot.get("work_packages",[]):work.append([x.get("key"),x.get("name"),x.get("role"),x.get("phase"),x.get("plan_hours"),float(Decimal(x.get("max_fte","1"))),", ".join(x.get("requirement_ids",[]))])

    sched=wb.create_sheet("Terminplan");sched.append(["Arbeitspaket","Start","Ende","Dauer Tage","Puffer","Kritisch"])
    for x in snapshot["schedule"].get("packages",[]):sched.append([x["id"],x["start"],x["finish"],x["duration_days"],x["total_float_days"],x["critical"]])

    clar=wb.create_sheet("Klärungsliste");clar.append(["ID","Klärung","Antwort","Status"])
    for x in snapshot.get("clarifications",[]):clar.append([x.get("key"),x.get("text"),x.get("answer"),x.get("status")])

    calc=wb.create_sheet("Kalkulation");calc.append(["Position","Kosten EUR","Verkauf EUR"]);calc.append(["Arbeit",float(Decimal(p["labor_cost_eur"])),float(Decimal(p["labor_sales_eur"]))]);calc.append(["Material",float(Decimal(p["material_cost_eur"])),float(Decimal(p["material_sales_eur"]))]);calc.append(["Risiko",None,float(Decimal(p["risk_eur"]))]);calc.append(["Rabatt",None,-float(Decimal(p["discount_eur"]))]);calc.append(["Netto",None,float(Decimal(p["net_eur"]))]);calc.append(["MwSt.",None,float(Decimal(p["vat_eur"]))]);calc.append(["Brutto",None,float(Decimal(p["gross_eur"]))])

    materials=wb.create_sheet("Sachpositionen");materials.append(["ID","Beschreibung"] + (["Kosten EUR"] if internal else []) + ["Verkauf EUR","Anforderungen"])
    for x in snapshot.get("materials",[]):
        row=[x.get("key"),x.get("description")]
        if internal:row.append(float(Decimal(x.get("cost_eur","0"))))
        row += [float(Decimal(x.get("sales_eur","0"))),", ".join(x.get("requirement_ids",[]))];materials.append(row)

    roles=wb.create_sheet("Rollen-Kosten intern");roles.append(["Rolle","Art","Kapazität FTE","Kosten/h","Einkauf/h","Aufschlag %","Verkauf/h"])
    for x in snapshot.get("rate_card",[]):roles.append([x.get("name"),x.get("kind"),float(Decimal(x.get("capacity_fte","0"))),float(Decimal(x["internal_cost_rate"])) if x.get("internal_cost_rate") else None,float(Decimal(x["purchase_rate"])) if x.get("purchase_rate") else None,float(Decimal(x["markup_percent"])) if x.get("markup_percent") else None,float(Decimal(x.get("sales_rate","0")))])
    if not internal: wb.remove(roles)

    positions=wb.create_sheet("Angebotspositionen");positions.append(["Position","Titel","Beschreibung","Verkauf EUR"])
    for x in snapshot.get("positions",[]):positions.append([x.get("position_no"),x.get("title"),x.get("description"),float(Decimal(x.get("sales_eur","0")))])

    pay=wb.create_sheet("Zahlungsplan");pay.append(["Phase","Prozent","Betrag EUR"])
    for x in snapshot.get("payment_plan",[]):pay.append([x["phase"],x["percent"],float(Decimal(x["amount_eur"]))])
    wb.save(path);return path
