import json
from django.test import SimpleTestCase


class SmokeHarnessTests(SimpleTestCase):
    def test_network_failure_is_recorded_and_does_not_hide_case(self):
        # docker bind-mount contains backend only; test a backend-shared runner module.
        from apps.ai.smoke import run_cases
        cases=[{'case_id':'one','payload':{'question':'Q'},'expected':{'http_status':200,'status':'ANSWERED'}}]
        rows=run_cases('http://localhost:8000','private-token',cases,transport=lambda *args: (_ for _ in ()).throw(TimeoutError()))
        self.assertEqual(len(rows),1)
        self.assertFalse(rows[0]['passed'])
        self.assertEqual(rows[0]['actual']['code'],'NETWORK_ERROR')
        self.assertNotIn('private-token',json.dumps(rows))

    def test_wrong_status_or_empty_citation_is_not_success(self):
        from apps.ai.smoke import run_cases
        cases=[{'case_id':'one','payload':{},'expected':{'http_status':200,'status':'ANSWERED'}}]
        rows=run_cases('http://localhost:8000','token',cases,transport=lambda *args:(200,{'status':'ANSWERED','citations':[]}))
        self.assertFalse(rows[0]['passed'])
