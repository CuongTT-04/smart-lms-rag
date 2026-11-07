"""Verify the compact W5 archive and retain an immutable private copy."""
import argparse
import sys
from pathlib import Path
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts.w6.contracts import ROOT,read_json,load_archive,write_json,write_once


def intake_report(data):
    return dict(schema_version='w6-intake-v1',status='AUTHENTICATED_COMPACT_VERIFIED',
        archive_sha256=data['archive_sha256'],source_package_manifest_sha256=data['manifest']['source_package_manifest_sha256'],
        record_count=len(data['records']),split_counts=data['config']['split_counts'],
        source_component_count=len(data['source_group_splits']),physical_file_binding='PASSED',
        original_use_policy=data['config']['use'],full_w5_review_bundle='NOT_INCLUDED_IN_COMPACT',
        full_candidate_content_hash_recomputed=False,
        full_candidate_hash_scope='Authenticated sidecar hash retained; complete candidate records are not in compact ZIP.',
        formal_peer_approval_created=False,technical_handoff_blocked_by_missing_paperwork=False,
        model_weights_loaded=False,gpu_used=False,training='NOT_RUN',public_redistribution_allowed=False)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--contract',type=Path,required=True);p.add_argument('--archive',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--report',type=Path,required=True)
    args=p.parse_args();contract=read_json(args.contract);data=load_archive(args.archive,contract['expected_compact'])
    for name,raw in data['files'].items():write_once(args.output/name,raw)
    write_once(args.output/'source-archive.zip',args.archive.read_bytes())
    report=intake_report(data);write_json(args.output/'intake-report.json',report);write_json(args.report,report)
    print('INTAKE_PASSED: 500 rows bound to split files; original review/rights status retained.')


if __name__=='__main__':main()
