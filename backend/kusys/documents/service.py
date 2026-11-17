from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from kusys.common.config import get_settings

settings = get_settings()

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".png"}
MIME_BY_EXT = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".png": "image/png",
}

@dataclass(frozen=True, slots=True)
class Extracted:
    page_number: int | None
    block_index: int
    block_type: str
    source_text: str
    normalized_text: str
    coordinates: dict | None
    table_meta: dict | None
    source_checksum: str
    text_source: str
    quality_status: str
    heading_path: str | None = None


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def quality(text: str) -> str:
    n = len(normalize_text(text))
    if n >= settings.ocr_threshold_chars_per_page:
        return "good"
    if n >= max(20, settings.ocr_threshold_chars_per_page // 3):
        return "review"
    return "insufficient"


def validate_upload(filename: str, mime_type: str | None, data: bytes) -> tuple[str, str]:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("Nur PDF, DOCX und PNG sind zulässig")
    if len(data) > settings.max_upload_bytes:
        raise ValueError("Datei überschreitet die maximal zulässige Größe")
    expected = MIME_BY_EXT[ext]
    if mime_type and mime_type not in {expected, "application/octet-stream"}:
        raise ValueError("MIME-Typ passt nicht zur Dateiendung")
    if ext == ".pdf" and not data.startswith(b"%PDF"):
        raise ValueError("Ungültige PDF-Signatur")
    if ext == ".png" and not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Ungültige PNG-Signatur")
    if ext == ".docx" and not data.startswith(b"PK"):
        raise ValueError("Ungültige DOCX-Signatur")
    return ext, expected


class DocumentService:
    def extract(self, path: Path) -> tuple[list[Extracted], dict]:
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return self._extract_pdf(path)
        if suffix == ".docx":
            return self._extract_docx(path)
        if suffix == ".png":
            return self._extract_png(path)
        raise ValueError(f"Nicht unterstütztes Format: {suffix}")

    def extract_text(self, path: Path) -> str:
        blocks, _ = self.extract(path)
        return "\n".join(x.source_text for x in blocks)

    def _extract_pdf(self, path: Path) -> tuple[list[Extracted], dict]:
        import fitz
        blocks: list[Extracted] = []
        page_texts: list[str] = []
        with fitz.open(path) as doc:
            if doc.needs_pass:
                raise ValueError("Passwortgeschützte PDFs sind nicht zulässig")
            if len(doc) > settings.max_pdf_pages:
                raise ValueError("PDF überschreitet die maximale Seitenanzahl")
            for page_idx, page in enumerate(doc):
                text = page.get_text("text") or ""
                page_texts.append(text)
        needs_ocr = any(len(normalize_text(t)) < settings.ocr_threshold_chars_per_page for t in page_texts)
        ocr_path: Path | None = None
        ocr_available = bool(shutil.which("ocrmypdf") and shutil.which("tesseract"))
        if needs_ocr and ocr_available:
            tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            tmp.close()
            ocr_path = Path(tmp.name)
            cmd = ["ocrmypdf", "--skip-text", "--deskew", "--rotate-pages", str(path), str(ocr_path)]
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=900)
            if proc.returncode != 0:
                ocr_path.unlink(missing_ok=True)
                ocr_path = None
        selected_path = ocr_path or path
        with fitz.open(selected_path) as doc:
            for page_idx, page in enumerate(doc):
                native = page_texts[page_idx]
                selected = page.get_text("text") or ""
                use_ocr = bool(ocr_path and len(normalize_text(native)) < settings.ocr_threshold_chars_per_page and len(normalize_text(selected)) > len(normalize_text(native)))
                source = "ocr" if use_ocr else "native"
                blocks.extend(self._pdf_layout(page, page_idx + 1, source))
        if ocr_path:
            ocr_path.unlink(missing_ok=True)
        return blocks, {"page_count": len(page_texts), "whole_document_ocr": bool(ocr_path), "ocr_needed": needs_ocr, "layout_version": "layout-v2", "ocr_available": ocr_available}

    def _pdf_layout(self, page, page_number: int, source: str) -> list[Extracted]:
        """Keep table rows together and preserve paragraph geometry and reading order."""
        import fitz
        candidates = []
        table_rects = []
        try:
            tables = page.find_tables().tables
        except (AttributeError, RuntimeError, ValueError):
            tables = []
        for ti, table in enumerate(tables):
            table_rects.append(fitz.Rect(table.bbox))
            for ri, (row, cells) in enumerate(zip(table.rows, table.extract())):
                text = " | ".join((cell or "").strip() for cell in cells)
                if not text.strip(" |"):
                    continue
                x0, y0, x1, y1 = row.bbox
                candidates.append((y0, x0, "table_row", text,
                    {"x0": x0, "y0": y0, "x1": x1, "y1": y1, "page_width": page.rect.width, "page_height": page.rect.height},
                    {"table": ti, "row": ri, "cells": cells}))
        data = page.get_text("dict", sort=True)
        font_sizes = [span["size"] for block in data["blocks"] if block.get("type") == 0 for line in block["lines"] for span in line["spans"] if span.get("text", "").strip()]
        body_size = sorted(font_sizes)[len(font_sizes) // 2] if font_sizes else 10
        for block in data["blocks"]:
            if block.get("type") != 0:
                continue
            lines = []
            sizes = []
            boxes = []
            def flush():
                if not lines:
                    return
                text = "\n".join(lines).strip()
                rect = fitz.Rect(boxes[0])
                for box in boxes[1:]:
                    rect |= fitz.Rect(box)
                # Large short text is a heading, not a paragraph to be joined with its body.
                kind = "heading" if len(text) < 180 and min(sizes, default=0) > body_size * 1.2 else "paragraph"
                candidates.append((rect.y0, rect.x0, kind, text,
                    {"x0": rect.x0, "y0": rect.y0, "x1": rect.x1, "y1": rect.y1, "page_width": page.rect.width, "page_height": page.rect.height, "line_boxes": list(boxes)}, None))
                lines.clear(); sizes.clear(); boxes.clear()
            for line in block["lines"]:
                rect = fitz.Rect(line["bbox"])
                # Tables were extracted by row; do not duplicate their words as paragraphs.
                if any(table.contains(rect.tl + (rect.br - rect.tl) * .5) for table in table_rects):
                    flush()
                    continue
                text = "".join(span.get("text", "") for span in line["spans"])
                if text.strip():
                    lines.append(text); boxes.append(line["bbox"])
                    sizes.extend(span["size"] for span in line["spans"])
            flush()
        # Table detectors occasionally omit footnotes or repeat merged cells. Keep native
        # blocks when token coverage differs; better a visible fragment than silent text loss.
        from collections import Counter
        tokens = lambda text: Counter(re.findall(r"\w+|[^\w\s|]", text))
        if tokens("\n".join(item[3] for item in candidates)) != tokens(page.get_text("text")):
            candidates = []
            for raw in page.get_text("blocks", sort=True):
                if len(raw) > 6 and raw[6] != 0:
                    continue
                if not str(raw[4]).strip():
                    continue
                x0, y0, x1, y1 = raw[:4]
                candidates.append((y0, x0, "paragraph", str(raw[4]).strip(),
                    {"x0": x0, "y0": y0, "x1": x1, "y1": y1, "page_width": page.rect.width, "page_height": page.rect.height, "layout_fallback": True}, None))
        return [self._block(page_number, i, kind, text, coords=coords, table_meta=meta, text_source=source)
                for i, (_, _, kind, text, coords, meta) in enumerate(sorted(candidates, key=lambda item: (round(item[0], 1), item[1])))]

    def _extract_docx(self, path: Path) -> tuple[list[Extracted], dict]:
        from docx import Document
        try:
            doc = Document(path)
        except Exception as exc:
            raise ValueError("DOCX kann nicht gelesen werden; passwortgeschützte oder beschädigte Dateien sind nicht zulässig") from exc
        blocks: list[Extracted] = []
        idx = 0
        heading_stack: list[str] = []
        for p in doc.paragraphs:
            text = p.text.strip()
            if not text:
                continue
            style = (p.style.name or "") if p.style else ""
            is_heading = style.lower().startswith("heading") or style.lower().startswith("überschrift")
            btype = "heading" if is_heading else ("list_item" if p.style and "list" in style.lower() else "paragraph")
            if is_heading:
                m = re.search(r"(\d+)$", style)
                level = int(m.group(1)) if m else 1
                heading_stack[:] = heading_stack[: max(0, level - 1)]
                heading_stack.append(text)
            blocks.append(self._block(None, idx, btype, text, heading_path=" > ".join(heading_stack)))
            idx += 1
        for ti, table in enumerate(doc.tables):
            for ri, row in enumerate(table.rows):
                cells = [c.text.strip() for c in row.cells]
                text = " | ".join(cells)
                if text.strip(" |"):
                    blocks.append(self._block(None, idx, "table_row", text, table_meta={"table": ti, "row": ri, "cells": cells}))
                    idx += 1
        return blocks, {"page_count": None, "whole_document_ocr": False, "ocr_available": False}

    def _extract_png(self, path: Path) -> tuple[list[Extracted], dict]:
        if not shutil.which("tesseract"):
            raise RuntimeError("Tesseract ist für PNG-OCR erforderlich")
        proc = subprocess.run(["tesseract", str(path), "stdout", "-l", "deu+eng"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
        if proc.returncode != 0:
            proc = subprocess.run(["tesseract", str(path), "stdout", "-l", "eng"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
        if proc.returncode != 0:
            raise RuntimeError("PNG-OCR fehlgeschlagen")
        text = proc.stdout.decode("utf-8", errors="replace")
        return [self._block(1, 0, "paragraph", text, text_source="ocr")], {"page_count": 1, "whole_document_ocr": True, "ocr_available": True}

    @staticmethod
    def _block(page: int | None, idx: int, btype: str, text: str, *, coords: dict | None = None, table_meta: dict | None = None, text_source: str = "native", heading_path: str | None = None) -> Extracted:
        norm = normalize_text(text)
        return Extracted(
            page_number=page,
            block_index=idx,
            block_type=btype,
            source_text=text,
            normalized_text=norm,
            coordinates=coords,
            table_meta=table_meta,
            source_checksum=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            text_source=text_source,
            quality_status=quality(text),
            heading_path=heading_path,
        )
