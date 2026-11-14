from pathlib import Path
import tempfile
import unittest
from scripts.comparison.group_report import render
from scripts.comparison.protocol import write_json


class GroupReportTests(unittest.TestCase):
    def test_report_rejects_partial_assessment(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            write_json(folder/'summary.json',{'status':'A_ONLY','primary_outputs':450})
            with self.assertRaises(ValueError):render(folder)
            self.assertFalse((folder/'evaluation-report.md').exists())


if __name__=='__main__':unittest.main()
