"""Run authenticated W4 smoke cases; a successful HTTP call does not prove LLM quality."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from apps.ai.smoke import run_cases


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',default='http://localhost:8000')
    parser.add_argument('--cases',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    token=os.environ.get('W4_SMOKE_TOKEN')
    if not token:
        parser.error('Set W4_SMOKE_TOKEN in the environment; never put the token on the command line.')
    content=Path(args.cases).read_bytes()
    cases=json.loads(content)
    if not isinstance(cases,list) or not cases:parser.error('Cases must be a nonempty JSON list.')
    rows=run_cases(args.base_url,token,cases)
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    (output/'guardrail_results.jsonl').write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows),encoding='utf-8')
    commit=subprocess.run(['git','rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip()
    manifest={'run_type':'http_smoke','created_at':datetime.now(timezone.utc).isoformat(),'commit':commit,
        'cases_sha256':hashlib.sha256(content).hexdigest(),'total':len(rows),'passed':sum(row['passed'] for row in rows),
        'llm_verified':False,'note':'Verify operator model/index manifest and viewer manually before claiming an end-to-end LLM demo.'}
    (output/'run_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(manifest,ensure_ascii=False))
    return 0 if manifest['passed']==manifest['total'] else 1


if __name__=='__main__':
    raise SystemExit(main())
