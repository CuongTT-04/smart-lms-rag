"""Allocate new W6 authoring slots without generating or counting new samples."""
import argparse
import csv
import io
import sys
from collections import Counter,defaultdict
from pathlib import Path
if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts.w6.contracts import ROOT,load_archive,read_json,require,write_json,write_once,digest


def allocate(data,source_manifest):
    sources={s['source_group_id']:s for s in source_manifest['sources']}
    groups=defaultdict(list)
    for row in data['records']:
        m=row['metadata'];require(len(m['source_group_ids'])==1,'MULTIGROUP_ALLOCATION_REQUIRES_REVIEW')
        groups[m['source_group_ids'][0]].append(m)
    result=[];counters=Counter();summary=[]
    for group,records in sorted(groups.items()):
        owners={m['author_member'] for m in records};splits={m['split'] for m in records}
        require(len(owners)==len(splits)==1,'GROUP_ALLOCATION_AMBIGUOUS')
        owner=next(iter(owners));split=next(iter(splits));source=sources[group]
        start=counters[owner]+1;tasks=Counter(m['task_type'] for m in records)
        for task,n in sorted(tasks.items()):
            for _ in range(n):
                counters[owner]+=1
                result.append(dict(record_id=f'W6_{owner}_{counters[owner]:05d}',owner_member=owner,
                    owner_name='Vũ Nam Dương' if owner=='A' else 'Trần Tuấn Cường',
                    course_code=source['course_code'],task_type=task,source_group_id=group,split=split,
                    source_checksum=source['source_checksum'],page_start=1,page_end=source['page_count'],
                    status='ALLOCATION_ONLY_NOT_AUTHORED',public_redistribution_allowed=False))
        summary.append(dict(source_group_id=group,owner_member=owner,split=split,new_record_count=len(records),
                            id_start=f'W6_{owner}_{start:05d}',id_end=f'W6_{owner}_{counters[owner]:05d}',task_counts=dict(tasks)))
    require(dict(counters)=={'A':250,'B':250},'AUTHOR_QUOTAS')
    return result,summary


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--contract',type=Path,required=True)
    p.add_argument('--archive',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();contract=read_json(args.contract);data=load_archive(args.archive,contract['expected_compact'])
    slots,groups=allocate(data,read_json(ROOT/contract['source_manifest']['path']))
    buf=io.StringIO(newline='');writer=csv.DictWriter(buf,fieldnames=list(slots[0]));writer.writeheader();writer.writerows(slots)
    write_once(args.output/'record-allocation.csv',buf.getvalue().encode('utf-8'))
    write_json(args.output/'source-allocation.json',dict(status='PLANNED_NOT_AUTHORED',slots=500,
        new_samples_created=0,source_archive_sha256=data['archive_sha256'],groups=groups,
        expected_new_split_counts=dict(Counter(r['split'] for r in slots)),allocation_sha256=digest(slots)))
    print('ALLOCATION_READY: 250 new slots per member; 27 whole-source assignments; no samples authored.')


if __name__=='__main__':main()
