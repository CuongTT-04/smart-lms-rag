import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
from scripts.ingest_documents import main, REPO_ROOT

class IngestCLITests(unittest.TestCase):
    def args(self, source, target):
        return ["ingest_documents.py", str(source), "--output",str(target),
                "--course-id",str(uuid4()),"--document-id",str(uuid4()),"--version-id",str(uuid4())]
    def test_source_output_collision_rejected_before_extraction(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/"source.pdf"; source.write_bytes(b"original")
            with patch("sys.argv",self.args(source,source)),patch("scripts.ingest_documents.extract_pdf") as extract:
                with self.assertRaises(SystemExit): main()
                extract.assert_not_called()
            self.assertEqual(source.read_bytes(),b"original")
    def test_corpus_sidecar_output_rejected_before_extraction(self):
        target=REPO_ROOT/"data/corpus/KTCTMLN/ch01.json"
        with patch("sys.argv",self.args(Path("other.pdf"),target)),patch("scripts.ingest_documents.extract_pdf") as extract:
            with self.assertRaises(SystemExit): main()
            extract.assert_not_called()
if __name__ == "__main__": unittest.main()
