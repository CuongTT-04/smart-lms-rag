"""Offline PDF extraction for W2; does not enqueue web jobs or create embeddings."""
import argparse
import json
import sys
from pathlib import Path
from uuid import UUID

REPO_ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO_ROOT))
from backend.apps.documents.processors.parser import extract_pdf, ExtractionError
from backend.apps.documents.processors.metadata import write_extraction

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf",type=Path)
    parser.add_argument("--course-id",required=True,type=UUID)
    parser.add_argument("--document-id",required=True,type=UUID)
    parser.add_argument("--version-id",required=True,type=UUID)
    parser.add_argument("--subject-code")
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    source=args.pdf.resolve()
    destination=args.output.resolve()
    if destination == source:
        parser.error("Output cannot replace the original input PDF.")
    if destination.is_relative_to((REPO_ROOT/"data/corpus").resolve()):
        parser.error("Corpus originals/sidecars are read-only; choose data/processed or private runtime storage.")
    if destination.suffix.lower() != ".json":
        parser.error("Extraction output must use the .json extension.")
    try:
        result=extract_pdf(args.pdf)
        write_extraction(result,{"course_id":str(args.course_id),"document_id":str(args.document_id),
            "version_id":str(args.version_id),"subject_code":args.subject_code},args.output)
    except ExtractionError as exc:
        print(json.dumps({"status":"FAILED","error_code":exc.code,"message":str(exc)},ensure_ascii=False),file=sys.stderr)
        return 1
    print(json.dumps({"status":"EXTRACTED","pages":result.page_count,"output":str(args.output),"rag_ready":False}))
    return 0

if __name__ == "__main__": raise SystemExit(main())
