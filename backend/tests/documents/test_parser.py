"""W2 parser contract tests; no Django/database is required."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from uuid import uuid4
from reportlab.pdfgen.canvas import Canvas
from PIL import Image
from reportlab.lib.utils import ImageReader
from apps.documents.processors.parser import extract_pdf, ExtractionError
from apps.documents.processors.metadata import write_extraction

class ParserTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "sample.pdf"
    def pdf(self, pages):
        c = Canvas(str(self.path))
        for text in pages:
            if text: c.drawString(50, 750, text)
            c.showPage()
        c.save()
    def test_pages_preserve_physical_positions(self):
        self.pdf(["FIRST_PAGE_ONLY", "SECOND_PAGE_ONLY"])
        result = extract_pdf(self.path)
        self.assertEqual([p.page_number for p in result.pages], [1, 2])
        self.assertIn("FIRST_PAGE_ONLY", result.pages[0].text)
        self.assertNotIn("SECOND_PAGE_ONLY", result.pages[0].text)
        self.assertIn("SECOND_PAGE_ONLY", result.pages[1].text)
        self.assertEqual(result.page_count, 2)
        self.assertFalse(result.ocr_enabled)
    def test_furniture_text_is_not_silently_dropped(self):
        self.pdf(["BODY"])
        from docling.datamodel.base_models import ConversionStatus
        from docling_core.types.doc import ContentLayer
        body=SimpleNamespace(text="BODY",prov=[SimpleNamespace(page_no=1,charspan=(0,4))])
        footer=SimpleNamespace(text="FOOTER",prov=[SimpleNamespace(page_no=1,charspan=(0,6))])
        def items(**kwargs):
            yield body,0
            if ContentLayer.FURNITURE in (kwargs.get("included_content_layers") or set()): yield footer,0
        doc=SimpleNamespace(pages={1:object()},iterate_items=items)
        converter=SimpleNamespace(convert=lambda *a,**kw:SimpleNamespace(status=ConversionStatus.SUCCESS,document=doc))
        with patch(extract_pdf.__module__ + "._get_converter",return_value=converter):
            result=extract_pdf(self.path)
        self.assertIn("FOOTER",result.pages[0].text)
    def test_multi_page_text_splits_by_provenance_charspan(self):
        self.pdf(["ONE", "TWO"])
        from docling.datamodel.base_models import ConversionStatus
        item=SimpleNamespace(text="ONE TWO", prov=[SimpleNamespace(page_no=1,charspan=(0,3)), SimpleNamespace(page_no=2,charspan=(4,7))])
        doc=SimpleNamespace(pages={1:object(),2:object()}, iterate_items=lambda **kw:iter([(item,0)]))
        conversion=SimpleNamespace(status=ConversionStatus.SUCCESS,document=doc)
        converter=SimpleNamespace(convert=lambda *a,**kw:conversion)
        with patch(extract_pdf.__module__ + "._get_converter",return_value=converter):
            result=extract_pdf(self.path)
        self.assertEqual([p.text for p in result.pages],["ONE","TWO"])
    def test_file_changed_during_conversion_is_rejected(self):
        self.pdf(["ONE"])
        from docling.datamodel.base_models import ConversionStatus
        item=SimpleNamespace(text="ONE",prov=[SimpleNamespace(page_no=1,charspan=(0,3))])
        doc=SimpleNamespace(pages={1:object()},iterate_items=lambda **kw:iter([(item,0)]))
        def convert(*args,**kwargs):
            with self.path.open("ab") as stream: stream.write(b"changed")
            return SimpleNamespace(status=ConversionStatus.SUCCESS,document=doc)
        with patch(extract_pdf.__module__ + "._get_converter",return_value=SimpleNamespace(convert=convert)):
            with self.assertRaises(ExtractionError) as ctx: extract_pdf(self.path)
        self.assertEqual(ctx.exception.code,"SOURCE_CHANGED")
    def test_corrupt_pdf_rejected(self):
        self.path.write_bytes(b"%PDF-1.7 corrupted")
        with self.assertRaises(ExtractionError) as ctx: extract_pdf(self.path)
        self.assertEqual(ctx.exception.code, "INVALID_PDF")
    def test_image_only_pdf_requires_ocr(self):
        c = Canvas(str(self.path))
        c.drawImage(ImageReader(Image.new("RGB", (100, 100), "black")), 50, 50)
        c.showPage(); c.save()
        with self.assertRaises(ExtractionError) as ctx: extract_pdf(self.path)
        self.assertEqual(ctx.exception.code, "OCR_REQUIRED")
    def test_blank_page_is_preserved(self):
        self.pdf(["FIRST_PAGE_ONLY", None, "LAST_PAGE_ONLY"])
        result = extract_pdf(self.path)
        self.assertEqual(len(result.pages), 3)
        self.assertEqual(result.pages[1].status, "BLANK")
    def test_page_limit_rejected(self):
        self.pdf(["ONE", "TWO"])
        with self.assertRaises(ExtractionError) as ctx: extract_pdf(self.path, max_pages=1)
        self.assertEqual(ctx.exception.code, "PAGE_LIMIT")
    def test_size_limit_rejected(self):
        self.pdf(["ONE"])
        with self.assertRaises(ExtractionError) as ctx: extract_pdf(self.path, max_bytes=1)
        self.assertEqual(ctx.exception.code, "SIZE_LIMIT")
    def test_missing_file_rejected(self):
        with self.assertRaises(ExtractionError) as ctx: extract_pdf(self.path)
        self.assertEqual(ctx.exception.code, "FILE_NOT_FOUND")
    def test_metadata_has_uuid_scope_and_atomic_utf8_output(self):
        self.pdf(["ONE"])
        result = extract_pdf(self.path)
        meta = {k: str(uuid4()) for k in ["course_id", "document_id", "version_id"]}
        target = Path(self.temp.name)/"extraction.json"
        write_extraction(result, meta, target)
        obj=json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(obj["course_id"],meta["course_id"])
        self.assertEqual(obj["pages"][0]["page_number"],1)
        self.assertFalse(obj["rag_ready"])
        self.assertEqual(obj["parser"]["name"],"docling")
        self.assertFalse(list(target.parent.glob("*.tmp")))
    def test_subject_code_cannot_masquerade_as_runtime_uuid(self):
        self.pdf(["ONE"])
        result=extract_pdf(self.path)
        with self.assertRaises(ValueError):
            write_extraction(result, {"course_id":"KTCTMLN", "document_id":str(uuid4()), "version_id":str(uuid4())}, Path(self.temp.name)/"bad.json")

if __name__ == "__main__": unittest.main()
