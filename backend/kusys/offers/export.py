from __future__ import annotations

from decimal import Decimal
from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import Path

INK = "15172E"
INK_MID = "3A3F72"
TEXT = "303741"
MUTED = "697181"
LINE = "D9DEE7"
PALE = "F3F5F8"
PALE_BLUE = "EEF1F8"
ACCENT = "FFE433"
CRITICAL = "B94718"


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


def _set_run_font(run, name: str = "Arial") -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    run.font.name = name
    r_pr = run._element.get_or_add_rPr()
    fonts = r_pr.rFonts
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        r_pr.insert(0, fonts)
    for key in ("ascii", "hAnsi", "cs", "eastAsia"):
        fonts.set(qn(f"w:{key}"), name)


def _configure_document(doc, snapshot: dict, config: dict) -> None:
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt, RGBColor
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    section = doc.sections[0]
    margins = config.get("margins_mm") or [23.5, 21.5, 19, 21.5]
    section.top_margin = Cm(float(margins[0]) / 10)
    section.right_margin = Cm(float(margins[1]) / 10)
    section.bottom_margin = Cm(float(margins[2]) / 10)
    section.left_margin = Cm(float(margins[3]) / 10)
    section.header_distance = Cm(1.15)
    section.footer_distance = Cm(1.0)

    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = "Arial"
    normal_rpr = normal._element.get_or_add_rPr()
    normal_fonts = normal_rpr.rFonts
    if normal_fonts is None:
        normal_fonts = OxmlElement("w:rFonts")
        normal_rpr.insert(0, normal_fonts)
    normal_fonts.set(qn("w:ascii"), "Arial")
    normal_fonts.set(qn("w:hAnsi"), "Arial")
    normal.font.size = Pt(10)
    normal.font.color.rgb = RGBColor.from_string(TEXT)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.12
    for name, size, before, after in (("Title", 30, 0, 7), ("Heading 1", 19, 20, 8), ("Heading 2", 13, 15, 6), ("Heading 3", 10.5, 10, 4)):
        style = styles[name]
        style.font.name = "Arial"
        style_rpr = style._element.get_or_add_rPr()
        style_fonts = style_rpr.rFonts
        if style_fonts is None:
            style_fonts = OxmlElement("w:rFonts")
            style_rpr.insert(0, style_fonts)
        style_fonts.set(qn("w:ascii"), "Arial")
        style_fonts.set(qn("w:hAnsi"), "Arial")
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor.from_string("000000")
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.keep_with_next = True
        if name == "Title" and style._element.pPr is not None:
            title_border = style._element.pPr.find(qn("w:pBdr"))
            if title_border is not None:
                style._element.pPr.remove(title_border)
    styles["Title"].paragraph_format.keep_with_next = True
    if "Subtitle" in styles:
        styles["Subtitle"].font.name = "Arial"
        styles["Subtitle"].font.size = Pt(16)
        styles["Subtitle"].font.color.rgb = RGBColor.from_string(MUTED)
        styles["Subtitle"].paragraph_format.space_after = Pt(14)

    header = section.header
    header_table = header.add_table(rows=1, cols=2, width=section.page_width - section.left_margin - section.right_margin)
    header_table.autofit = False
    header_table.columns[0].width = int((section.page_width - section.left_margin - section.right_margin) * 0.58)
    header_table.columns[1].width = int((section.page_width - section.left_margin - section.right_margin) * 0.42)
    header_table.cell(0, 0).text = str(config.get("header_text") or "KUSYS  |  ENGINEERING & PROJEKTANGEBOTE")
    offer_no = (snapshot.get("offer_header") or {}).get("offer_number") or snapshot.get("offer_number") or ""
    header_table.cell(0, 1).text = str(offer_no)
    for cell in header_table.rows[0].cells:
        _set_cell_margins(cell, top=20, start=0, bottom=70, end=0)
        for paragraph in cell.paragraphs:
            paragraph.paragraph_format.space_after = Pt(0)
            for run in paragraph.runs:
                _set_run_font(run)
                run.font.size = Pt(8)
                run.font.bold = True
                run.font.color.rgb = RGBColor.from_string(INK_MID)
    header_table.cell(0, 1).paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _set_table_borders(header_table, color=LINE, size=4, inside=False)

    footer = section.footer
    footer_table = footer.add_table(rows=1, cols=2, width=section.page_width - section.left_margin - section.right_margin)
    footer_table.autofit = False
    footer_table.columns[0].width = int((section.page_width - section.left_margin - section.right_margin) * .7)
    footer_table.columns[1].width = int((section.page_width - section.left_margin - section.right_margin) * .3)
    footer_table.cell(0, 0).text = str(config.get("footer_text") or "KuSys  ·  Angebotsunterlage")
    for cell in footer_table.rows[0].cells:
        _set_cell_margins(cell, top=20, start=0, bottom=0, end=0)
        for paragraph in cell.paragraphs:
            paragraph.paragraph_format.space_after = Pt(0)
            for run in paragraph.runs:
                _set_run_font(run)
                run.font.size = Pt(8)
                run.font.color.rgb = RGBColor.from_string(MUTED)
    right = footer_table.cell(0, 1).paragraphs[0]
    right.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = right.add_run("Seite ")
    _set_run_font(run)
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor.from_string(MUTED)
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    right._p.append(field)
    _set_table_borders(footer_table, inside=False)


def _set_cell_margins(cell, *, top: int = 90, start: int = 100, bottom: int = 90, end: int = 100) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    margins = tc_pr.first_child_found_in("w:tcMar")
    if margins is None:
        margins = OxmlElement("w:tcMar")
        tc_pr.append(margins)
    for edge, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = margins.find(qn(f"w:{edge}"))
        if node is None:
            node = OxmlElement(f"w:{edge}")
            margins.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def _set_table_borders(table, *, color: str = LINE, size: int = 4, inside: bool = True) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    tbl_pr = table._tbl.tblPr
    borders = tbl_pr.first_child_found_in("w:tblBorders")
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tbl_pr.append(borders)
    edges = ["top", "left", "bottom", "right"] + (["insideH", "insideV"] if inside else [])
    for edge in edges:
        tag = qn(f"w:{edge}")
        element = borders.find(tag)
        if element is None:
            element = OxmlElement(f"w:{edge}")
            borders.append(element)
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), str(size))
        element.set(qn("w:space"), "0")
        element.set(qn("w:color"), color)


def _format_table(table, *, widths: list[int] | None = None, header: bool = True, stripe: bool = True, numeric_columns: tuple[int, ...] = ()) -> None:
    from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor

    table.autofit = False
    if widths:
        for index, width in enumerate(widths):
            table.columns[index].width = int(width)
    for row_index, row in enumerate(table.rows):
        tr_pr = row._tr.get_or_add_trPr()
        if tr_pr.find(qn("w:cantSplit")) is None:
            tr_pr.append(OxmlElement("w:cantSplit"))
        if header and row_index == 0:
            repeat = OxmlElement("w:tblHeader")
            repeat.set(qn("w:val"), "true")
            tr_pr.append(repeat)
        for col_index, cell in enumerate(row.cells):
            if widths:
                cell.width = int(widths[col_index])
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            _set_cell_margins(cell)
            if header and row_index == 0:
                _shade_cell(cell, INK)
                font_color, bold, size = "FFFFFF", True, 8.5
            else:
                if stripe and (row_index - (1 if header else 0)) % 2 == 1:
                    _shade_cell(cell, PALE)
                font_color, bold, size = TEXT, False, 9
            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.space_before = Pt(0)
                paragraph.paragraph_format.space_after = Pt(0)
                paragraph.paragraph_format.line_spacing = 1.05
                if col_index in numeric_columns:
                    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                for run in paragraph.runs:
                    _set_run_font(run)
                    run.font.size = Pt(size)
                    run.font.bold = bold
                    run.font.color.rgb = RGBColor.from_string(font_color)
    _set_table_borders(table)


def _localized_date(value: object) -> str:
    if not value:
        return "—"
    try:
        return date.fromisoformat(str(value)[:10]).strftime("%d.%m.%Y")
    except ValueError:
        return str(value)


def _add_front_matter(doc, snapshot: dict) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor

    header = snapshot.get("offer_header") or {}
    customer = snapshot.get("customer") or {}
    pricing = snapshot.get("pricing") or {}
    offer_no = header.get("offer_number") or snapshot.get("offer_number") or ""
    variant = header.get("variant") or snapshot.get("variant_name") or "Basis"
    project_name = snapshot.get("project_name") or "Projektangebot"
    recipient = header.get("recipient") or customer.get("company_name")

    kicker = doc.add_paragraph()
    kicker.paragraph_format.space_before = Pt(20)
    kicker.paragraph_format.space_after = Pt(7)
    run = kicker.add_run("ANGEBOT  /  " + str(variant).upper())
    _set_run_font(run)
    run.font.size = Pt(9)
    run.font.bold = True
    run.font.color.rgb = RGBColor.from_string(INK_MID)
    r_pr = run._r.get_or_add_rPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), ACCENT)
    r_pr.append(shading)

    title = doc.add_paragraph(style="Title")
    title.add_run(str(project_name))
    subtitle = doc.add_paragraph("Leistungsumfang, Terminplan und Preisangebot", style="Subtitle")

    width = int(doc.sections[0].page_width - doc.sections[0].left_margin - doc.sections[0].right_margin)
    info = doc.add_table(rows=2, cols=3)
    info.cell(0, 0).text = "ANGEBOTSNUMMER"
    info.cell(0, 1).text = "ANGEBOTSDATUM"
    info.cell(0, 2).text = "GÜLTIGKEIT"
    info.cell(1, 0).text = f"{offer_no} · V{snapshot.get('version', '')}".strip(" ·")
    info.cell(1, 1).text = _localized_date(header.get("offer_date"))
    info.cell(1, 2).text = f"{header.get('validity_days', 30)} Tage"
    _format_table(info, widths=[int(width * .40), int(width * .30), int(width * .30)], header=False, stripe=False)
    for cell in info.rows[0].cells:
        _shade_cell(cell, PALE_BLUE)
        for run in cell.paragraphs[0].runs:
            run.font.size = Pt(7.5)
            run.font.bold = True
            run.font.color.rgb = RGBColor.from_string(MUTED)
    for cell in info.rows[1].cells:
        for run in cell.paragraphs[0].runs:
            run.font.size = Pt(10)
            run.font.bold = True
            run.font.color.rgb = RGBColor.from_string(INK)

    if recipient or customer.get("address") or customer.get("contact_name"):
        recipient_heading = doc.add_paragraph()
        recipient_heading.paragraph_format.space_before = Pt(14)
        recipient_heading.paragraph_format.space_after = Pt(3)
        run = recipient_heading.add_run("ANGEBOT FÜR")
        run.font.size = Pt(8)
        run.font.bold = True
        run.font.color.rgb = RGBColor.from_string(MUTED)
        recipient_paragraph = doc.add_paragraph()
        recipient_paragraph.paragraph_format.space_after = Pt(11)
        if recipient:
            run = recipient_paragraph.add_run(str(recipient))
            run.font.size = Pt(11)
            run.font.bold = True
            run.font.color.rgb = RGBColor.from_string(INK)
        trailing = [customer.get("address"), customer.get("contact_name")]
        text = "\n".join(str(value) for value in trailing if value)
        if text:
            run = recipient_paragraph.add_run(("\n" if recipient else "") + text)
            run.font.size = Pt(9)
            run.font.color.rgb = RGBColor.from_string(TEXT)

    metric_table = doc.add_table(rows=2, cols=3)
    labels = ("NETTO", "BRUTTO", "PROJEKTZEITRAUM")
    values = (
        _money(pricing.get("net_eur", 0)),
        _money(pricing.get("gross_eur", 0)),
        f"{_localized_date((snapshot.get('schedule') or {}).get('project_start'))} – {_localized_date((snapshot.get('schedule') or {}).get('project_finish'))}",
    )
    for index, label in enumerate(labels):
        metric_table.cell(0, index).text = label
        metric_table.cell(1, index).text = values[index]
    _format_table(metric_table, widths=[int(width * .28), int(width * .28), int(width * .44)], header=False, stripe=False)
    for cell in metric_table.rows[0].cells:
        _shade_cell(cell, INK)
        for run in cell.paragraphs[0].runs:
            run.font.size = Pt(7.5)
            run.font.bold = True
            run.font.color.rgb = RGBColor.from_string("C9CCE3")
    for index, cell in enumerate(metric_table.rows[1].cells):
        _shade_cell(cell, PALE_BLUE)
        for run in cell.paragraphs[0].runs:
            run.font.size = Pt(9 if index == 2 else 12)
            run.font.bold = True
            run.font.color.rgb = RGBColor.from_string(INK)

    intro = doc.add_paragraph("Dieses Angebot fasst den vorgesehenen Leistungsumfang, die geplanten Arbeitspakete, den Projektzeitraum und die Preisberechnung zusammen.")
    intro.paragraph_format.space_before = Pt(12)
    intro.paragraph_format.space_after = Pt(3)


def _labels(language: str) -> dict[str, str]:
    if language.lower().startswith("en"):
        return {
            "offer":"Quotation","recipient":"Recipient","scope":"Scope of supply","requirement":"Requirement",
            "description":"Description","price":"Price","schedule":"Schedule","finish":"Planned completion",
            "start":"Planned start","critical_path":"Critical path","weekdays":["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"],
            "months":["January","February","March","April","May","June","July","August","September","October","November","December"],
            "net":"Net","vat":"VAT","gross":"Gross","validity":"Validity","days":"days","payment":"Payment plan",
            "phase":"Phase","percent":"Percent","amount":"Amount","work_packages":"Work packages",
        }
    return {
        "offer":"Angebot","recipient":"Empfänger","scope":"Leistungsumfang","requirement":"Anforderung",
        "description":"Beschreibung","price":"Preis","schedule":"Termin","finish":"Geplanter Projektabschluss",
        "start":"Geplanter Projektstart","critical_path":"Kritischer Pfad","weekdays":["Montag","Dienstag","Mittwoch","Donnerstag","Freitag","Samstag","Sonntag"],
        "months":["Januar","Februar","März","April","Mai","Juni","Juli","August","September","Oktober","November","Dezember"],
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
    width = int(doc.sections[0].page_width - doc.sections[0].left_margin - doc.sections[0].right_margin)
    _format_table(table, widths=[int(width * .20), int(width * .56), int(width * .24)], numeric_columns=(2,))


def _shade_cell(cell, color: str) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    properties = cell._tc.get_or_add_tcPr()
    shading = properties.find(qn("w:shd"))
    if shading is None:
        shading = OxmlElement("w:shd")
        properties.append(shading)
    shading.set(qn("w:fill"), color)


def _set_cell_text(cell, value: str, *, color: str = "303741", bold: bool = False, size: float = 8) -> None:
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    cell.text = value
    for paragraph in cell.paragraphs:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
        paragraph.paragraph_format.space_before = Pt(0)
        paragraph.paragraph_format.space_after = Pt(0)
        for run in paragraph.runs:
            _set_run_font(run)
            run.font.size = Pt(size)
            run.font.bold = bold
            run.font.color.rgb = RGBColor.from_string(color)


def _add_schedule(doc, snapshot: dict, labels: dict) -> None:
    from docx.shared import Pt, RGBColor
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    schedule = snapshot.get("schedule") or {}
    schedule_heading = doc.add_heading(labels["schedule"], 2)
    schedule_heading.paragraph_format.page_break_before = True
    start_value = schedule.get("project_start")
    finish_value = schedule.get("project_finish")
    if start_value:
        doc.add_paragraph(f"{labels['start']}: {_localized_date(start_value)}  ·  {labels['finish']}: {_localized_date(finish_value)}")
    elif finish_value:
        doc.add_paragraph(f"{labels['finish']}: {_localized_date(finish_value)}")

    packages = {item.get("id"): item for item in snapshot.get("work_packages", [])}
    scheduled = []
    for item in schedule.get("packages", []):
        package = packages.get(item.get("id"))
        if package and item.get("start") and item.get("finish"):
            scheduled.append({**item, **package, "critical": bool(item.get("critical"))})
    critical_ids = schedule.get("critical_path") or []
    critical_keys = [packages[item].get("key", item) for item in critical_ids if item in packages]
    if critical_keys:
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.space_before = Pt(2)
        paragraph.paragraph_format.space_after = Pt(9)
        run = paragraph.add_run(f"{labels['critical_path']}: " + " → ".join(critical_keys))
        run.bold = True
        run.font.color.rgb = RGBColor.from_string(CRITICAL)
    if not scheduled:
        return

    first = date.fromisoformat(start_value[:10]) if start_value else min(date.fromisoformat(item["start"][:10]) for item in scheduled)
    last = date.fromisoformat(finish_value[:10]) if finish_value else max(date.fromisoformat(item["finish"][:10]) for item in scheduled)
    month_cursor = first.replace(day=1)
    project_week_start = first - timedelta(days=first.weekday())
    project_week_end = last + timedelta(days=6 - last.weekday())
    critical_set = set(critical_ids)
    weekdays = labels["weekdays"]
    while month_cursor <= last:
        next_month = (month_cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        month_end = next_month - timedelta(days=1)
        month_title = f"{labels['months'][month_cursor.month - 1]} {month_cursor.year}"
        doc.add_heading(month_title, 3)
        table = doc.add_table(rows=1, cols=7)
        table.style = "Table Grid"
        table.autofit = False
        usable_width = int(doc.sections[-1].page_width - doc.sections[-1].left_margin - doc.sections[-1].right_margin)
        # python-docx serializes grid widths as integer twips; float widths raise TypeError.
        column_width = int(usable_width / 7)
        for column, label in enumerate(weekdays):
            cell = table.rows[0].cells[column]
            cell.width = column_width
            _shade_cell(cell, "4B5058")
            _set_cell_text(cell, label, color="FFFFFF", bold=True, size=7.5)
            table.columns[column].width = column_width
        header_props = table.rows[0]._tr.get_or_add_trPr()
        repeat_header = OxmlElement("w:tblHeader")
        repeat_header.set(qn("w:val"), "true")
        header_props.append(repeat_header)
        for cell in table.rows[0].cells:
            for paragraph in cell.paragraphs:
                p_pr = paragraph._p.get_or_add_pPr()
                if p_pr.find(qn("w:keepNext")) is None:
                    p_pr.append(OxmlElement("w:keepNext"))

        month_offset = (month_cursor.weekday())  # Monday is zero.
        calendar_start = max(month_cursor - timedelta(days=month_offset), project_week_start)
        calendar_end = min(month_end + timedelta(days=(6 - month_end.weekday())), project_week_end)
        week_start = calendar_start
        while week_start <= calendar_end:
            dates = [week_start + timedelta(days=column) for column in range(7)]
            date_row = table.add_row()
            week_rows = [date_row]
            for column, day in enumerate(dates):
                cell = date_row.cells[column]
                cell.width = column_width
                in_month = day.month == month_cursor.month
                in_project = first <= day <= last
                fill = "F1F3F5" if not in_month or not in_project else "FAFBFC" if day.weekday() >= 5 else "FFFFFF"
                _shade_cell(cell, fill)
                _set_cell_text(cell, str(day.day), color="3C444D" if in_month and in_project else "A0A6AD", bold=day == first or day.day == 1, size=8)

            segments = []
            for item in scheduled:
                package_start = date.fromisoformat(item["start"][:10])
                package_finish = date.fromisoformat(item["finish"][:10])
                visible_start = max(package_start, week_start, month_cursor, first)
                visible_finish = min(package_finish, week_start + timedelta(days=6), month_end, last)
                if visible_start <= visible_finish:
                    segments.append({
                        "item": item,
                        "start_column": (visible_start - week_start).days,
                        "finish_column": (visible_finish - week_start).days,
                    })
            segments.sort(key=lambda segment: (segment["start_column"], segment["finish_column"]))
            lane_ends: list[int] = []
            placed = []
            for segment in segments:
                lane = next((index for index, end in enumerate(lane_ends) if end < segment["start_column"]), len(lane_ends))
                if lane == len(lane_ends):
                    lane_ends.append(segment["finish_column"])
                else:
                    lane_ends[lane] = segment["finish_column"]
                placed.append((segment, lane))
            for segment, _lane in placed:
                item = segment["item"]
                event_row = table.add_row()
                week_rows.append(event_row)
                cells = event_row.cells
                for cell in cells:
                    cell.width = column_width
                    _shade_cell(cell, "FFFFFF")
                first_cell = cells[segment["start_column"]]
                event_cell = first_cell if segment["finish_column"] == segment["start_column"] else first_cell.merge(cells[segment["finish_column"]])
                key = item.get("key") or item.get("id", "")
                name = item.get("name", "")
                is_critical = item.get("id") in critical_set or item.get("critical")
                fill = CRITICAL if is_critical else INK_MID
                _shade_cell(event_cell, fill)
                _set_cell_text(event_cell, f"{key} · {name}", color="FFFFFF", bold=True, size=7.5)
                _set_cell_margins(event_cell, top=60, start=75, bottom=60, end=75)
            for row in week_rows[:-1]:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        p_pr = paragraph._p.get_or_add_pPr()
                        if p_pr.find(qn("w:keepNext")) is None:
                            p_pr.append(OxmlElement("w:keepNext"))
            week_start += timedelta(days=7)
        for row in table.rows:
            row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
            for cell in row.cells:
                cell.width = column_width
                _set_cell_margins(cell, top=70, start=70, bottom=70, end=70)
        _set_table_borders(table, color=LINE, size=4)
        month_cursor = next_month


def _add_price(doc, snapshot: dict, labels: dict) -> None:
    pricing = snapshot["pricing"]
    doc.add_heading(labels["price"], 2)
    table = doc.add_table(rows=0, cols=2); table.style = "Table Grid"
    for label, key in ((labels["net"],"net_eur"),(labels["vat"],"vat_eur"),(labels["gross"],"gross_eur")):
        cells=table.add_row().cells; cells[0].text=label; cells[1].text=_money(pricing[key])
    width = int(doc.sections[0].page_width - doc.sections[0].left_margin - doc.sections[0].right_margin)
    _format_table(table, widths=[int(width * .68), int(width * .32)], header=False, numeric_columns=(1,))
    for row in table.rows[-2:]:
        _shade_cell(row.cells[0], PALE_BLUE)
        _shade_cell(row.cells[1], PALE_BLUE)
        for cell in row.cells:
            for run in cell.paragraphs[0].runs:
                run.font.bold = True


def _add_custom_positions(doc, snapshot: dict, labels: dict) -> None:
    positions=snapshot.get("positions") or []
    if not positions:return
    doc.add_heading(labels["scope"],2)
    table=doc.add_table(rows=1,cols=3);table.style="Table Grid"
    table.rows[0].cells[0].text="Pos.";table.rows[0].cells[1].text=labels["description"];table.rows[0].cells[2].text=labels["price"]
    for item in positions:
        row=table.add_row().cells;row[0].text=str(item.get("position_no",""));row[1].text=str(item.get("title","")) + (("\n"+str(item.get("description"))) if item.get("description") else "");row[2].text=_money(item.get("sales_eur",0))
    width = int(doc.sections[0].page_width - doc.sections[0].left_margin - doc.sections[0].right_margin)
    _format_table(table, widths=[int(width * .14), int(width * .62), int(width * .24)], numeric_columns=(2,))

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
    width = int(doc.sections[0].page_width - doc.sections[0].left_margin - doc.sections[0].right_margin)
    _format_table(table, widths=[int(width * .48), int(width * .22), int(width * .30)], numeric_columns=(1, 2))


def _add_customer_responses(doc, responses: list[dict]) -> None:
    from datetime import datetime
    from docx.shared import Pt, RGBColor

    if not responses:
        return
    doc.add_page_break()
    doc.add_heading("Anlage · Kundenrückmeldungen", 1)
    doc.add_paragraph("Nachrichten zum freigegebenen Angebot; der Angebotsstand selbst bleibt unverändert.")
    for item in responses:
        stamp = item.get("created_at")
        if isinstance(stamp, str):
            try:
                stamp = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            except ValueError:
                stamp = None
        heading = doc.add_paragraph()
        heading.paragraph_format.space_before = Pt(8)
        heading.paragraph_format.space_after = Pt(2)
        author = heading.add_run(str(item.get("author_name") or "Kunde"))
        author.bold = True
        author.font.color.rgb = RGBColor.from_string(INK)
        metadata = []
        if item.get("author_email"):
            metadata.append(str(item["author_email"]))
        if stamp and hasattr(stamp, "strftime"):
            metadata.append(stamp.astimezone().strftime("%d.%m.%Y, %H:%M"))
        if metadata:
            detail = heading.add_run("  ·  " + "  ·  ".join(metadata))
            detail.font.color.rgb = RGBColor.from_string(MUTED)
        body = doc.add_paragraph(str(item.get("body") or ""))
        body.paragraph_format.space_after = Pt(7)


def export_offer_docx(path: Path, snapshot: dict) -> Path:
    from docx import Document

    doc = Document()
    config=(snapshot.get("template") or {}).get("config_json") or {}
    _configure_document(doc, snapshot, config)

    header=snapshot.get("offer_header",{})
    language=header.get("language","de");labels=_labels(language)
    _add_front_matter(doc, snapshot)

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
    _add_customer_responses(doc, snapshot.get("customer_responses") or [])
    doc.core_properties.title = f"Angebot {header.get('offer_number') or snapshot.get('offer_number','')} · {snapshot.get('project_name','Projekt')}"
    doc.core_properties.subject = "Leistungsumfang, Terminplan und Preisangebot"
    doc.core_properties.author = "KuSys"
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
