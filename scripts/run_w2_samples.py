"""Reproduce two internal W2 extraction fixtures; never creates LMS accounts/courses."""
import json
import sys
import time
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.apps.documents.processors.parser import extract_pdf
from backend.apps.documents.processors.metadata import write_extraction

def main():
    output=ROOT/"data/processed/w2-samples"; output.mkdir(parents=True,exist_ok=True)
    records=[]
    for subject in ("KTCTMLN","CNXHKH"):
        pdf=ROOT/"data/corpus"/subject/"ch01.pdf"
        started=time.perf_counter(); result=extract_pdf(pdf); elapsed=time.perf_counter()-started
        fixture={"course_id":str(uuid5(NAMESPACE_URL,"offline-w2-course:"+subject)),
                 "document_id":str(uuid5(NAMESPACE_URL,"offline-w2-document:"+subject+":ch01")),
                 "version_id":str(uuid5(NAMESPACE_URL,"offline-w2-version:"+result.checksum_sha256)),
                 "subject_code":subject}
        destination=output/(subject+"-ch01-extraction.json")
        write_extraction(result,fixture,destination)
        reader=PdfReader(pdf); checks=[]
        for number in sorted({1,(result.page_count+1)//2,result.page_count}):
            original=reader.pages[number-1].extract_text() or ""
            text=result.pages[number-1].text
            tokens=set(original.split())
            checks.append({"page_number":number,"source_chars":len(original),"extracted_chars":len(text),
                "word_overlap_diagnostic":round(len(tokens & set(text.split()))/max(1,len(tokens)),4),
                "source_preview":original[:800],"extracted_preview":text[:800]})
        records.append({"subject":subject,"source":pdf.relative_to(ROOT).as_posix(),
            "output":destination.relative_to(ROOT).as_posix(),"identity_scope":"OFFLINE_FIXTURE_NOT_CREATED_IN_LMS",
            "page_count":result.page_count,"seconds":round(elapsed,3),"checksum":result.checksum_sha256,
            "parser_version":result.parser_version,
            "all_pages_numbered":[p.page_number for p in result.pages]==list(range(1,result.page_count+1)),
            "blank_pages":[p.page_number for p in result.pages if p.status=="BLANK"],
            "warning_pages":[p.page_number for p in result.pages if p.warnings],"spot_checks":checks})
        print(subject,result.page_count,"pages",round(elapsed,3),"seconds",flush=True)
    report=ROOT/"docs/reports/w2-extraction-verification.json"
    report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(json.dumps(records,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return 0
if __name__ == "__main__": raise SystemExit(main())
