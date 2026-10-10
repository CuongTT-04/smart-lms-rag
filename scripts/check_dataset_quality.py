from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
import csv
from datetime import datetime

try:
    from pypdf import PdfReader
except ImportError:
    print("Thiếu thư viện pypdf. Cài đặt bằng: pip install pypdf")
    sys.exit(1)

try:
    import pytesseract
except ImportError:
    pytesseract = None


BASE_DIR = Path("../data/corpus")
VALID_COURSES = {"CNXHKH", "KTCTMLN", "THMLN"}
REQUIRED_METADATA_KEYS = {
    "course_id",
    "course_name",
    "chapter_id",
    "document_id",
    "file_name",
    "file_type",
    "source",
    "page_count",
    "license",
    "checksum",
}
BAD_TEXT_MARKERS = ["�", "????", "\x00"]
ENABLE_OCR = False

# Xác định đường dẫn tuyệt đối theo vị trí file này để đảm bảo script
# hoạt động đúng khi được gọi từ thư mục khác. REPORT_DIR sẽ trỏ về
# `data/reports` ở gốc repo, còn BASE_DIR trỏ về `data/corpus`.
REPO_ROOT = Path(__file__).resolve().parent.parent
BASE_DIR = REPO_ROOT / "data" / "corpus"
REPORT_DIR = REPO_ROOT / "data" / "reports"


def sha256_of_file(path: Path) -> str:
    # Tính SHA-256 của file để phát hiện trùng lặp hoặc thay đổi nội dung
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def is_valid_chapter_name(name: str) -> bool:
    return bool(re.fullmatch(r"ch\d{2}\.pdf", name, flags=re.IGNORECASE))


def chapter_number_from_name(name: str):
    match = re.fullmatch(r"ch(\d{2})\.pdf", name, flags=re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def read_pdf_pages(path: Path):
    # Đọc các trang PDF và trích xuất text layer nếu có
    try:
        reader = PdfReader(str(path))
        pages = reader.pages
        texts = []
        for page in pages:
            texts.append(page.extract_text() or "")
        text = "\n".join(texts)
        return len(pages), text, None
    except Exception as exc:
        return None, "", str(exc)


def has_bad_encoding(text: str) -> bool:
    if any(marker in text for marker in BAD_TEXT_MARKERS):
        return True
    if text and all(ord(ch) < 32 and ch not in "\n\r\t" for ch in text[:200]):
        return True
    return False


def count_vietnamese_chars(text: str) -> int:
    pattern = re.compile(r"[a-zA-ZàáảãạâầấẩẫậăằắẳẵặèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđĐÀÁẢÃẠÂẦẤẨẪẬĂẰẮẲẴẶÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴĐ]", re.UNICODE)
    return len(pattern.findall(text))


def metadata_path_for(pdf_path: Path) -> Path:
    return pdf_path.with_suffix(".json")


def validate_metadata(pdf_path: Path, page_count: int, checksum: str):
    # Kiểm tra file metadata (.json) kèm theo PDF: tồn tại, định dạng, và các trường bắt buộc
    issues = []
    meta_path = metadata_path_for(pdf_path)
    if not meta_path.exists():
        issues.append("Thiếu file metadata JSON (.json) theo quy định của dataset")
        return issues

    try:
        with meta_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        issues.append(f"File metadata JSON lỗi định dạng: {exc}")
        return issues

    missing_keys = sorted(k for k in REQUIRED_METADATA_KEYS if k not in data or data.get(k) in (None, "", []))
    if missing_keys:
        issues.append(f"Metadata thiếu trường: {', '.join(missing_keys)}")

    if str(data.get("course_id", "")).strip() not in VALID_COURSES:
        issues.append(f"course_id không hợp lệ: {data.get('course_id')}")

    expected_name = pdf_path.name
    if str(data.get("file_name", "")).strip() != expected_name:
        issues.append(f"file_name không khớp với tên file thực tế: {data.get('file_name')} != {expected_name}")

    if str(data.get("file_type", "")).upper() != "PDF":
        issues.append(f"file_type không hợp lệ: {data.get('file_type')}")

    if int(data.get("page_count", 0) or 0) != page_count:
        issues.append(f"page_count metadata không khớp với PDF thật: {data.get('page_count')} != {page_count}")

    if str(data.get("checksum", "")).strip() != checksum:
        issues.append("checksum metadata không khớp với hash SHA-256 của file")

    return issues


def check_file_sequence(course_dir: Path):
    # Kiểm tra trình tự chương (thiếu chương, trùng lặp, thứ tự không đúng)
    files = sorted(course_dir.glob("*.pdf"), key=lambda p: p.name.lower())
    chapters = []
    for file in files:
        num = chapter_number_from_name(file.name)
        if num is not None:
            chapters.append(num)

    if not chapters:
        return []

    expected = list(range(1, max(chapters) + 1))
    missing = [n for n in expected if n not in chapters]
    duplicates = sorted({n for n in chapters if chapters.count(n) > 1})
    issues = []
    if missing:
        issues.append(f"Thiếu chương: {', '.join(f'ch{n:02d}.pdf' for n in missing)}")
    if duplicates:
        issues.append(f"Chương trùng lặp: {', '.join(f'ch{n:02d}.pdf' for n in duplicates)}")

    ordered = chapters == sorted(chapters)
    if not ordered:
        issues.append("Thứ tự chương không đúng trình tự")

    return issues


def optional_ocr_check(pdf_path: Path, text: str):
    # Quy tắc đơn giản để quyết định có cần chạy OCR hay không
    if len(text.strip()) >= 200 and count_vietnamese_chars(text) >= 20:
        return False, "PDF có text layer đủ tốt, không cần OCR"

    if not ENABLE_OCR:
        return True, "PDF có thể là scan hoặc text quá yếu; cần chạy OCR bằng Tesseract nếu muốn xác nhận nội dung"

    if pytesseract is None:
        return True, "OCR library không cài đặt; cần cài thêm pytesseract và Tesseract OCR nếu muốn chạy OCR thật"

    try:
        from PIL import Image
        import pdf2image
    except ImportError:
        return True, "PDF có thể là scan nhưng dependency OCR phụ trợ chưa cài: pillow/pdf2image"

    try:
        images = pdf2image.convert_from_path(str(pdf_path), first_page=1, last_page=min(2, len(pdf_path.name)))
        ocr_text = "\n".join(pytesseract.image_to_string(img) for img in images)
        if len(ocr_text.strip()) >= 50:
            return False, "OCR đã chạy thành công và tạo được text"
        return True, "PDF scan hoặc text yếu; cần OCR lại và kiểm tra chất lượng OCR"
    except Exception as exc:
        return True, f"OCR không chạy được: {exc}"


def check_file(path: Path):
    # Thực hiện các kiểm tra chất lượng cho một file PDF đơn lẻ
    result = {
        "file": str(path),
        "course": path.parent.name,
        "status": "OK",
        "issues": [],
        "can_open": False,
        "page_count": 0,
        "text_length": 0,
        "needs_ocr": False,
        "hash": "",
        "metadata_status": "OK",
    }

    if not path.exists():
        result["issues"].append("File không tồn tại")
        result["status"] = "REMOVE"
        return result

    if path.parent.name not in VALID_COURSES:
        result["issues"].append(f"Thư mục môn học không hợp lệ: {path.parent.name}")
        result["status"] = "NEED_FIX"

    if not is_valid_chapter_name(path.name):
        result["issues"].append(f"Tên file không đúng quy ước: {path.name}")
        result["status"] = "NEED_FIX"

    page_count, text, error = read_pdf_pages(path)
    if page_count is None:
        result["issues"].append(f"Không mở được PDF: {error}")
        result["status"] = "REMOVE"
        return result

    result["can_open"] = True
    result["page_count"] = page_count
    result["text_length"] = len(text.strip())
    result["hash"] = sha256_of_file(path)

    if page_count <= 0:
        result["issues"].append("Số trang bằng 0 hoặc không hợp lệ")
        result["status"] = "NEED_FIX"

    if len(text.strip()) < 200:
        result["issues"].append("Text layer quá ngắn hoặc rỗng -> có khả năng là PDF scan hoặc PDF nội dung yếu")
        result["needs_ocr"] = True
        if result["status"] == "OK":
            result["status"] = "NEED_FIX"

    if has_bad_encoding(text):
        result["issues"].append("Có thể có lỗi encoding hoặc ký tự lạ trong nội dung")
        if result["status"] == "OK":
            result["status"] = "NEED_FIX"

    if count_vietnamese_chars(text) == 0 and text.strip():
        result["issues"].append("Văn bản không chứa ký tự tiếng Việt hợp lệ; cần kiểm tra lại OCR hoặc nguồn PDF")
        result["needs_ocr"] = True
        if result["status"] == "OK":
            result["status"] = "NEED_FIX"

    if chapter_number_from_name(path.name) is None:
        result["issues"].append("Không xác định được số chương từ tên file")
        result["status"] = "NEED_FIX"

    metadata_issues = validate_metadata(path, page_count, result["hash"])
    if metadata_issues:
        result["issues"].extend(metadata_issues)
        result["metadata_status"] = "NEED_FIX"
        if result["status"] == "OK":
            result["status"] = "NEED_FIX"

    ocr_flag, ocr_message = optional_ocr_check(path, text)
    if ocr_flag:
        result["needs_ocr"] = True
        result["issues"].append(f"Cần OCR: {ocr_message}")
        if result["status"] == "OK":
            result["status"] = "NEED_FIX"

    return result


def main():
    # Kiểm tra thư mục dataset gốc
    if not BASE_DIR.exists():
        print(f"Không tìm thấy thư mục {BASE_DIR}")
        return

    pdf_files = sorted(BASE_DIR.rglob("*.pdf"))
    if not pdf_files:
        print(f"Không có file PDF nào trong {BASE_DIR}")
        return

    results = [check_file(p) for p in pdf_files]

    hash_map = defaultdict(list)
    for item in results:
        hash_map[item["hash"]].append(item["file"])

    duplicate_files = []
    for files in hash_map.values():
        if len(files) > 1:
            duplicate_files.extend(files)

    for item in results:
        if item["file"] in duplicate_files:
            item["issues"].append("File trùng lặp với file khác")
            if item["status"] == "OK":
                item["status"] = "NEED_FIX"

    # Ghi báo cáo CSV kết quả kiểm tra vào REPORT_DIR dưới gốc repo
    try:
        report_dir = REPORT_DIR
        report_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        report_path = report_dir / f"dataset_quality_report_{timestamp}.csv"
        fieldnames = [
            "file",
            "course",
            "status",
            "can_open",
            "page_count",
            "text_length",
            "needs_ocr",
            "metadata_status",
            "hash",
            "issues",
        ]
        with report_path.open("w", encoding="utf-8", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for r in results:
                writer.writerow({
                    "file": r.get("file"),
                    "course": r.get("course"),
                    "status": r.get("status"),
                    "can_open": r.get("can_open"),
                    "page_count": r.get("page_count"),
                    "text_length": r.get("text_length"),
                    "needs_ocr": r.get("needs_ocr"),
                    "metadata_status": r.get("metadata_status", ""),
                    "hash": r.get("hash", ""),
                    "issues": " | ".join(r.get("issues", [])),
                })
        print(f"\nCSV report written to: {report_path}")
    except Exception as e:
        print(f"Không thể ghi báo cáo CSV: {e}")

    course_sequence_issues = defaultdict(list)
    for course_dir in sorted(BASE_DIR.iterdir()):
        if course_dir.is_dir() and course_dir.name in VALID_COURSES:
            course_sequence_issues[course_dir.name] = check_file_sequence(course_dir)

    print("=" * 100)
    print("BÁO CÁO KIỂM TRA CHẤT LƯỢNG DATASET PDF")
    print("=" * 100)
    print(f"Tổng số file PDF: {len(results)}")
    print(f"Số file hợp lệ: {sum(1 for r in results if r['status'] == 'OK')}")
    print(f"Số file cần sửa: {sum(1 for r in results if r['status'] == 'NEED_FIX')}")
    print(f"Số file loại bỏ: {sum(1 for r in results if r['status'] == 'REMOVE')}")
    print(f"Số file trùng lặp: {len(duplicate_files)}")

    print("\n1) Kiểm tra trình tự chương theo môn học:")
    for course_name, issues in course_sequence_issues.items():
        print(f"- {course_name}:")
        if issues:
            for issue in issues:
                print(f"    - {issue}")
        else:
            print("    - Đúng chuỗi chương")

    print("\n2) Chi tiết từng file:")
    for r in results:
        print("-" * 100)
        print(f"File: {r['file']}")
        print(f"Course: {r['course']}")
        print(f"Status: {r['status']}")
        print(f"Can open: {r['can_open']}")
        print(f"Page count: {r['page_count']}")
        print(f"Text length: {r['text_length']}")
        print(f"Needs OCR: {r['needs_ocr']}")
        print(f"Metadata status: {r['metadata_status']}")
        if r["issues"]:
            print("Issues:")
            for issue in r["issues"]:
                print(f"  - {issue}")
        else:
            print("Issues: None")

    print("\n3) Danh sách file trùng lặp:")
    if duplicate_files:
        for file_path in sorted(set(duplicate_files)):
            print(f"  - {file_path}")
    else:
        print("  Không có file nào trùng lặp.")

    print("\nGợi ý xử lý:")
    print("- REMOVE: file hỏng hoặc không đọc được; bỏ khỏi dataset.")
    print("- NEED_FIX: chỉnh sửa tên file, metadata, OCR, hoặc text layer trước khi dùng.")
    print("- OK: đủ điều kiện để đưa vào ingestion và embedding.")



def audit_corpus(corpus_root: Path, repo_root: Path):
    """Read-only W2 audit; technical validity does not establish copyright permission."""
    rows=[]
    ids=defaultdict(list)
    hashes=defaultdict(list)
    for pdf in sorted(Path(corpus_root).rglob("*.pdf")):
        issues=[]; meta={}; page_count=0
        digest=sha256_of_file(pdf)
        try:
            meta=json.loads(pdf.with_suffix(".json").read_text(encoding="utf-8-sig"))
            if not isinstance(meta,dict): raise ValueError("metadata must be an object")
        except (OSError,ValueError) as exc:
            issues.append("metadata_missing_or_invalid")
            meta={}
        missing=sorted(REQUIRED_METADATA_KEYS-set(meta))
        if missing: issues.append("missing_fields:"+",".join(missing))
        for key in ("document_id","source","license"):
            if not isinstance(meta.get(key),str) or not meta[key].strip(): issues.append("empty_"+key)
        if meta.get("course_id") != pdf.parent.name: issues.append("course_id_mismatch")
        if meta.get("file_name") != pdf.name: issues.append("file_name_mismatch")
        if meta.get("file_type") != "PDF": issues.append("file_type_mismatch")
        if meta.get("checksum") != digest: issues.append("checksum_mismatch")
        try:
            reader=PdfReader(pdf)
            if reader.is_encrypted: raise ValueError("encrypted")
            page_count=len(reader.pages)
            if not page_count: issues.append("empty_pdf")
            if meta.get("page_count") != page_count: issues.append("page_count_mismatch")
            if page_count>100: issues.append("w2_page_limit")
            usable_text=False
            for number,page in enumerate(reader.pages,1):
                text=page.extract_text() or ""
                usable_text=usable_text or bool(text.strip())
                if not text.strip() and page.images: issues.append(f"ocr_required_page:{number}")
                if has_bad_encoding(text): issues.append(f"encoding_review_page:{number}")
            if not usable_text: issues.append("text_layer_required")
        except Exception:
            issues.append("unreadable_pdf")
        size=pdf.stat().st_size
        if size>20*1024*1024: issues.append("w2_size_limit")
        row={"subject":pdf.parent.name,"document_id":meta.get("document_id",""),
             "relative_path":pdf.relative_to(repo_root).as_posix(),"sha256":digest,
             "page_count":page_count,"size_bytes":size,"source":meta.get("source",""),
             "license":meta.get("license",""),"check_status":"FAIL" if issues else "PASS",
             "rights_status":"DECLARED_NOT_VERIFIED","issues":" | ".join(issues)}
        rows.append(row); hashes[digest].append(row)
        if isinstance(row["document_id"],str) and row["document_id"].strip():
            ids[row["document_id"]].append(row)
    for groups,label in [(hashes,"duplicate_sha256"),(ids,"duplicate_document_id")]:
        for group in groups.values():
            if len(group)>1:
                for row in group:
                    row["check_status"]="FAIL"
                    row["issues"]=(row["issues"]+" | "+label).strip(" |")
    orphans=[p.relative_to(repo_root).as_posix() for p in sorted(Path(corpus_root).rglob("*.json")) if not p.with_suffix(".pdf").exists()]
    return rows,orphans


def export_w2_audit(corpus_root: Path, repo_root: Path, manifest_path: Path, report_path: Path):
    rows,orphans=audit_corpus(corpus_root,repo_root)
    manifest_path.parent.mkdir(parents=True,exist_ok=True)
    fields=["subject","document_id","relative_path","sha256","page_count","size_bytes","source","license","check_status","rights_status","issues"]
    with manifest_path.open("w",encoding="utf-8",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    lines=["# Kiểm kê Corpus v1 — W2, ngày 07/10/2026", "",
           "Kiểm tra tự động, chỉ đọc PDF/metadata gốc. PASS chỉ xác nhận tiêu chí kỹ thuật được kiểm tra, không xác nhận quyền sử dụng/phát hành tài liệu.", "",
           f"- PDF: {len(rows)}; metadata JSON: {len(list(corpus_root.rglob('*.json')))}.",
           f"- PASS: {sum(r['check_status']=='PASS' for r in rows)}; FAIL: {sum(r['check_status']=='FAIL' for r in rows)}; metadata không có PDF: {len(orphans)}.",
           "- Kiểm tra checksum, số trang, cặp file/định danh, giới hạn 20 MiB/100 trang, dấu hiệu PDF cần OCR/lỗi ký tự và thông tin nguồn/license.",
           "- Source/license hiện là khai báo trong metadata, chưa có bằng chứng độc lập xác nhận cấp phép. Cần nhóm/giảng viên xác nhận phạm vi nghiên cứu nội bộ trước khi chia sẻ công khai.","",
           "| Môn | PDF | PASS | FAIL |", "|---|---:|---:|---:|"]
    for subject in sorted({r['subject'] for r in rows}):
        selected=[r for r in rows if r['subject']==subject]
        lines.append(f"| {subject} | {len(selected)} | {sum(r['check_status']=='PASS' for r in selected)} | {sum(r['check_status']=='FAIL' for r in selected)} |")
    lines += ["", "## Các vấn đề phát hiện", ""]
    problems=[f"- `{r['relative_path']}`: {r['issues']}" for r in rows if r['check_status']!='PASS']
    lines += problems or ["Không phát hiện lỗi theo các tiêu chí tự động trên. Vẫn cần đối chiếu extraction với PDF gốc; không coi đây là đánh giá chất lượng OCR/Docling hoặc kiểm chứng nội dung học thuật."]
    lines += [f"- Metadata không có PDF: `{p}`" for p in orphans]
    lines += ["", "## Bàn giao", "", "Manifest dùng đường dẫn tương đối repo, checksum SHA-256 tính lại. Nhãn môn trong corpus không phải khóa UUID runtime của LMS. Không sửa PDF/metadata để làm kết quả kiểm kê đạt.", ""]
    report_path.parent.mkdir(parents=True,exist_ok=True)
    report_path.write_text("\n".join(lines),encoding="utf-8")
    return rows,orphans


def run_cli():
    import argparse
    parser=argparse.ArgumentParser(description="Corpus quality checks; no flag preserves the W1 report.")
    parser.add_argument("--w2-audit",action="store_true")
    parser.add_argument("--corpus",type=Path,default=BASE_DIR)
    args=parser.parse_args()
    if not args.w2_audit:
        main(); return
    if not args.corpus.is_dir(): parser.error("Corpus directory does not exist")
    rows,orphans=export_w2_audit(args.corpus.resolve(),REPO_ROOT,
        REPO_ROOT/"data/data_manifest.csv",REPO_ROOT/"docs/reports/w2-corpus-check.md")
    print(f"W2 audit: {len(rows)} PDF, {sum(r['check_status']=='PASS' for r in rows)} PASS, {len(orphans)} orphan metadata")
    if not rows or orphans or any(r['check_status']=='FAIL' for r in rows): raise SystemExit(1)


if __name__ == "__main__":
    run_cli()
