"""Private storage, outside public MEDIA_ROOT, with server-owned relative keys."""
import hashlib
import uuid
from pathlib import Path
from django.conf import settings
from pypdf import PdfReader
from .exceptions import DocumentError

def private_root():
    root=Path(getattr(settings,"DOCUMENTS_STORAGE_ROOT",Path(settings.BASE_DIR)/".private/documents")).resolve()
    media=Path(settings.MEDIA_ROOT).resolve()
    if root.is_relative_to(media):
        raise DocumentError("UNSAFE_STORAGE", "Private documents must be outside MEDIA_ROOT.",503)
    root.mkdir(parents=True,exist_ok=True)
    return root

def private_path(key):
    root=private_root();path=(root/key).resolve()
    if path==root or not path.is_relative_to(root):
        raise DocumentError("INVALID_STORAGE_KEY","Invalid private storage key.",503)
    return path

def stage_upload(upload):
    if upload is None:raise DocumentError("FILE_REQUIRED","A PDF file is required.",400)
    key="incoming/"+uuid.uuid4().hex+".pdf";path=private_path(key);path.parent.mkdir(parents=True,exist_ok=True)
    limit=getattr(settings,"DOCUMENTS_MAX_BYTES",20*1024*1024);size=0;digest=hashlib.sha256()
    try:
        with path.open("xb") as stream:
            for chunk in upload.chunks():
                size+=len(chunk)
                if size>limit:raise DocumentError("SIZE_LIMIT","PDF exceeds 20 MiB.",413)
                digest.update(chunk);stream.write(chunk)
        with path.open("rb") as stream:
            if not stream.read(1024).lstrip().startswith(b"%PDF-"):
                raise DocumentError("UNSUPPORTED_FORMAT","W2 accepts PDF files only.",415)
        try:
            reader=PdfReader(path)
            if reader.is_encrypted:raise DocumentError("ENCRYPTED_PDF","Encrypted PDFs are not supported.",400)
            count=len(reader.pages)
            if not count:raise DocumentError("INVALID_PDF","PDF has no pages.",400)
            if count>getattr(settings,"DOCUMENTS_MAX_PAGES",100):
                raise DocumentError("PAGE_LIMIT","PDF exceeds 100 pages.",400)
        except DocumentError:raise
        except Exception as exc:raise DocumentError("INVALID_PDF","PDF is corrupt or unreadable.",400) from exc
        return path,size,digest.hexdigest(),count
    except Exception:
        path.unlink(missing_ok=True);raise
