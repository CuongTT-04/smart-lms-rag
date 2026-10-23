"""HTTP smoke runner. Never records bearer tokens, prompts or answer bodies."""
import json
from time import monotonic
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError
from urllib.parse import urlparse


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def transport(base_url, token, payload):
    url=base_url.rstrip('/')+'/api/ai/chat/'
    parsed=urlparse(url)
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Invalid URL')
    if parsed.scheme!='https' and parsed.hostname not in ('localhost','127.0.0.1','::1'):
        raise ValueError('Use HTTPS outside loopback')
    request=Request(url,data=json.dumps(payload).encode(),method='POST',headers={
        'Authorization':f'Bearer {token}','Content-Type':'application/json','Accept':'application/json'})
    try:
        response=build_opener(NoRedirect).open(request,timeout=120)
    except HTTPError as exc:
        response=exc
    with response:
        content=response.read(2*1024*1024+1)
        if len(content)>2*1024*1024: raise ValueError('Response too large')
        data=json.loads(content)
        if not isinstance(data,dict): raise ValueError('Expected object')
        return response.code,data


def run_cases(base_url, token, cases, *, transport=transport):
    rows=[]
    ids=set()
    for case in cases:
        if (not isinstance(case,dict) or not isinstance(case.get('case_id'),str) or case['case_id'] in ids
                or not isinstance(case.get('payload'),dict) or not isinstance(case.get('expected'),dict)
                or type(case['expected'].get('http_status')) is not int):
            raise ValueError('Invalid/duplicate case schema')
        ids.add(case['case_id'])
        started=monotonic()
        expected=case['expected']
        try:
            status,body=transport(base_url,token,case['payload'])
            citations=body.get('citations',[])
            actual={'http_status':status,'status':body.get('status'),'code':body.get('code'),
                'request_id':body.get('request_id'),'citation_count':len(citations) if isinstance(citations,list) else 0}
            passed=all(actual.get(key)==value for key,value in expected.items())
            if body.get('status')=='ANSWERED':
                passed=passed and bool(body.get('answer')) and actual['citation_count']>0
        except Exception:
            actual={'code':'NETWORK_ERROR'};passed=False
        rows.append({'case_id':case['case_id'],'run_type':'http_smoke', 'expected':expected,'actual':actual,
            'passed':passed,'elapsed_ms':round((monotonic()-started)*1000,3)})
    return rows
