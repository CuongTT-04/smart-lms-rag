import json
import tempfile
import unittest
from pathlib import Path
from reportlab.pdfgen.canvas import Canvas
from scripts.check_dataset_quality import audit_corpus, sha256_of_file

class CorpusAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.folder=self.root/"data/corpus/KTCTMLN"
        self.folder.mkdir(parents=True)
        self.pdf=self.folder/"ch01.pdf"
        c=Canvas(str(self.pdf)); c.drawString(40,700,"CORPUS TEXT "*25); c.showPage(); c.save()
        self.meta={"course_id":"KTCTMLN","course_name":"Course","chapter_id":1,
                   "document_id":"KTCTMLN-01","file_name":"ch01.pdf","file_type":"PDF",
                   "source":"Declared internal source","page_count":1,"license":"Internal use declared",
                   "checksum":sha256_of_file(self.pdf)}
    def save(self): self.pdf.with_suffix(".json").write_text(json.dumps(self.meta),encoding="utf-8")
    def test_valid_pair_has_relative_path_and_unverified_rights(self):
        self.save(); rows,orphans=audit_corpus(self.root/"data/corpus",self.root)
        self.assertEqual(rows[0]["check_status"],"PASS")
        self.assertEqual(rows[0]["relative_path"],"data/corpus/KTCTMLN/ch01.pdf")
        self.assertEqual(rows[0]["rights_status"],"DECLARED_NOT_VERIFIED")
        self.assertEqual(orphans,[])
    def test_checksum_mismatch_is_reported(self):
        self.meta["checksum"]="bad"; self.save()
        rows,_=audit_corpus(self.root/"data/corpus",self.root)
        self.assertEqual(rows[0]["check_status"],"FAIL")
        self.assertIn("checksum",rows[0]["issues"])
    def test_invalid_document_id_is_reported_without_crashing(self):
        self.meta["document_id"]=["invalid"]
        self.save(); rows,_=audit_corpus(self.root/"data/corpus",self.root)
        self.assertEqual(rows[0]["check_status"],"FAIL")
    def test_wholly_blank_document_cannot_pass(self):
        c=Canvas(str(self.pdf)); c.showPage(); c.save()
        self.meta["checksum"]=sha256_of_file(self.pdf)
        self.save(); rows,_=audit_corpus(self.root/"data/corpus",self.root)
        self.assertEqual(rows[0]["check_status"],"FAIL")
        self.assertIn("text_layer_required",rows[0]["issues"])
    def test_empty_license_and_orphan_are_reported(self):
        self.meta["license"]=""; self.save()
        (self.folder/"orphan.json").write_text("{}",encoding="utf-8")
        rows,orphans=audit_corpus(self.root/"data/corpus",self.root)
        self.assertEqual(rows[0]["check_status"],"FAIL")
        self.assertIn("license",rows[0]["issues"])
        self.assertEqual(len(orphans),1)
if __name__ == "__main__": unittest.main()
