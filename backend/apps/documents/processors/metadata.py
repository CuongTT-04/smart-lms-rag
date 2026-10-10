"""Validated UTF-8 extraction envelope, written atomically."""
import json
import os
import tempfile
from pathlib import Path
from uuid import UUID
from .parser import ExtractionResult

def write_extraction(result: ExtractionResult, metadata: dict, output_path: Path) -> None:
    output_path=Path(output_path).resolve()
    corpus_root=Path(__file__).resolve().parents[4]/"data/corpus"
    if output_path.is_relative_to(corpus_root.resolve()):
        raise ValueError("Corpus originals and metadata are read-only.")
    if output_path.suffix.lower() != ".json":
        raise ValueError("Extraction output must use the .json extension.")
    scope = {}
    for key in ("course_id", "document_id", "version_id"):
        scope[key] = str(UUID(str(metadata[key])))
    payload = {
        "schema_version": "1.0", **scope,
        "subject_code": metadata.get("subject_code"),
        "checksum_sha256": result.checksum_sha256,
        "parser": {"name": "docling", "version": result.parser_version,
                   "ocr_enabled": result.ocr_enabled, "table_structure_enabled": False},
        "page_count": result.page_count,
        "pages": [dict(page_number=p.page_number, text=p.text, status=p.status,
                       warnings=list(p.warnings)) for p in result.pages],
        "extraction_status": "EXTRACTED", "rag_ready": False,
        "indexed_at": None,
    }
    output_path=Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_name=None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output_path.parent,
                                        suffix=".tmp", delete=False) as stream:
            temp_name=stream.name
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
        os.replace(temp_name, output_path)
    finally:
        if temp_name and os.path.exists(temp_name): os.unlink(temp_name)
