"""PDF-text extraction with Docling; independent of Django and HTTP."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
from pypdf import PdfReader

MAX_BYTES = 20 * 1024 * 1024
MAX_PAGES = 100

class ExtractionError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)

@dataclass(frozen=True)
class ExtractedPage:
    page_number: int
    text: str
    status: str
    warnings: tuple[str, ...] = ()

@dataclass(frozen=True)
class ExtractionResult:
    page_count: int
    pages: tuple[ExtractedPage, ...]
    parser_version: str
    checksum_sha256: str
    ocr_enabled: bool = False
    def to_dict(self):
        return asdict(self)

_converter = None

def _get_converter():
    global _converter
    if _converter is None:
        try:
            from docling.document_converter import DocumentConverter, PdfFormatOption
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            options = PdfPipelineOptions(do_ocr=False, do_table_structure=False)
            _converter = DocumentConverter(allowed_formats=[InputFormat.PDF],
                format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})
        except ImportError as exc:
            raise ExtractionError("DEPENDENCY_MISSING", "Install backend/requirements.txt.") from exc
    return _converter

def extract_pdf(path: Path, *, max_pages: int = MAX_PAGES, max_bytes: int = MAX_BYTES) -> ExtractionResult:
    path = Path(path)
    if not path.is_file():
        raise ExtractionError("FILE_NOT_FOUND", "PDF file does not exist.")
    if path.stat().st_size > max_bytes:
        raise ExtractionError("SIZE_LIMIT", "PDF exceeds the configured upload size.")
    original_digest = sha256(path.read_bytes()).hexdigest()
    try:
        with path.open("rb") as stream:
            if not stream.read(1024).lstrip().startswith(b"%PDF-"):
                raise ValueError("Not a PDF header")
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise ExtractionError("ENCRYPTED_PDF", "Encrypted PDFs are not accepted in W2.")
        count = len(reader.pages)
        if not count:
            raise ValueError("No pages")
        if count > max_pages:
            raise ExtractionError("PAGE_LIMIT", "PDF exceeds the configured page count.")
        raw_texts = [page.extract_text() or "" for page in reader.pages]
        images = [bool(page.images) for page in reader.pages]
        for i, (text, has_image) in enumerate(zip(raw_texts, images), start=1):
            if not text.strip() and has_image:
                raise ExtractionError("OCR_REQUIRED", f"Page {i} is image-only; provide a text PDF or enable OCR in a later phase.")
        if not any(text.strip() for text in raw_texts):
            raise ExtractionError("TEXT_LAYER_REQUIRED", "No usable text layer; this is not a successful extraction.")
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError("INVALID_PDF", "PDF is corrupt or cannot be read.") from exc
    try:
        conversion = _get_converter().convert(path, raises_on_error=True)
        from docling.datamodel.base_models import ConversionStatus
        if conversion.status != ConversionStatus.SUCCESS:
            raise ExtractionError("INCOMPLETE_CONVERSION", "Docling did not complete every page.")
        doc = conversion.document
        if len(doc.pages) != count:
            raise ExtractionError("PAGE_MAPPING_ERROR", "Converted page count does not match the PDF.")
        collected: dict[int, list[str]] = {i: [] for i in range(1, count + 1)}
        from docling_core.types.doc import ContentLayer
        for item, _level in doc.iterate_items(included_content_layers={ContentLayer.BODY, ContentLayer.FURNITURE}):
            text = getattr(item, "text", None)
            if text is None and hasattr(item, "export_to_markdown"):
                text = item.export_to_markdown(doc=doc)
            if not text or not text.strip():
                continue
            provs = getattr(item, "prov", [])
            if not provs:
                raise ExtractionError("PAGE_MAPPING_ERROR", "Text item has no source page provenance.")
            numbers = {prov.page_no for prov in provs}
            if any(number not in collected for number in numbers):
                raise ExtractionError("PAGE_MAPPING_ERROR", "Text provenance references an invalid page.")
            if len(numbers) == 1:
                collected[numbers.pop()].append(text.strip())
            else:
                # TextItem provenance carries the source character interval for each page.
                # Do not copy a merged paragraph or a whole multi-page table to every page.
                previous_end = 0
                for prov in sorted(provs, key=lambda p: p.charspan[0]):
                    start, end = prov.charspan
                    if not (previous_end <= start < end <= len(text)) or text[previous_end:start].strip():
                        raise ExtractionError("PAGE_MAPPING_ERROR", "Multi-page provenance has missing/overlapping character spans.")
                    segment = text[start:end].strip()
                    if segment: collected[prov.page_no].append(segment)
                    previous_end = end
                if text[previous_end:].strip():
                    raise ExtractionError("PAGE_MAPPING_ERROR", "Multi-page provenance leaves unmapped source text.")
        pages = []
        for number in range(1, count + 1):
            text = "\n".join(collected[number])
            if raw_texts[number - 1].strip() and not text.strip():
                raise ExtractionError("INCOMPLETE_CONVERSION", f"Page {number} had text but conversion lost it.")
            warnings = ("IMAGE_CONTENT_NOT_TRANSCRIBED",) if images[number - 1] else ()
            pages.append(ExtractedPage(number, text, "OK" if text.strip() else "BLANK", warnings))
        if sha256(path.read_bytes()).hexdigest() != original_digest:
            raise ExtractionError("SOURCE_CHANGED", "Source changed during conversion; discard the result and retry a fixed version.")
        return ExtractionResult(count, tuple(pages), version("docling"), original_digest)
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError("CONVERSION_FAILED", "Docling conversion failed; check local diagnostic logs and model availability.") from exc
