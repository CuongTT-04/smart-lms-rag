"""Subprocess conversion boundary; writes no document content to stdout."""
import json
import sys
from dataclasses import asdict
from pathlib import Path
from .parser import extract_pdf, ExtractionError

def main():
    source, output, max_pages, max_bytes = sys.argv[1:]
    try:
        result=extract_pdf(Path(source),max_pages=int(max_pages),max_bytes=int(max_bytes))
        payload=asdict(result);code=0
    except ExtractionError as exc:
        payload={"error_code":exc.code};code=1
    except Exception:
        payload={"error_code":"CONVERSION_FAILED"};code=1
    Path(output).write_text(json.dumps(payload,ensure_ascii=False),encoding="utf-8")
    return code

if __name__ == "__main__":
    raise SystemExit(main())
