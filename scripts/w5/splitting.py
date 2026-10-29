"""Deterministic grouped splitting; never split a connected source/family component."""
import hashlib
from collections import Counter
from .common import digest


def build_split_plan(records, eligible_ids, confirmed_pairs, seed=42):
    if type(seed) is not int or seed!=42: raise ValueError('W5 split seed is locked to 42')
    rows={r['record_id']:r for r in records}
    if len(rows)!=len(records) or len(set(eligible_ids))!=len(eligible_ids): raise ValueError('Duplicate record IDs')
    selected=set(eligible_ids)
    if not selected or selected-set(rows): raise ValueError('Missing or unknown eligible IDs')
    parent={rid:rid for rid in selected}
    def find(rid):
        while parent[rid]!=rid: parent[rid]=parent[parent[rid]];rid=parent[rid]
        return rid
    def union(a,b):
        a,b=find(a),find(b)
        if a!=b: parent[max(a,b)]=min(a,b)
    groups={};families={}
    for rid in sorted(selected):
        row=rows[rid]
        if not row['source_group_ids'] or not row['variant_family_id']: raise ValueError('Missing grouping identity')
        for group in row['source_group_ids']:
            if group in groups: union(rid,groups[group])
            groups[group]=rid
        family=row['variant_family_id']
        if family in families: union(rid,families[family])
        families[family]=rid
        previous=row.get('parent_record_id')
        if previous:
            if previous not in selected: raise ValueError('Parent not in eligible release set')
            union(rid,previous)
    for a,b in confirmed_pairs:
        if a not in selected or b not in selected: raise ValueError('Unknown confirmed pair')
        union(a,b)
    components={}
    for rid in sorted(selected): components.setdefault(find(rid),[]).append(rid)
    if len(components)<3: raise ValueError('At least three independent components are required; choose more sources, do not break groups')
    ordered=sorted(components.values(),key=lambda ids:(-len(ids),hashlib.sha256((str(seed)+':'+','.join(ids)).encode()).hexdigest()))
    ratios={'train':.8,'validation':.1,'instruction_holdout':.1};splits={k:[] for k in ratios}
    assignments=[]
    for index,ids in enumerate(ordered):
        empty=[k for k,v in splits.items() if not v]
        choices=empty if len(ordered)-index==len(empty) else list(splits)
        target=max(choices,key=lambda k:ratios[k]*len(selected)-len(splits[k]))
        splits[target].extend(ids);assignments.append(dict(component_id=digest(ids),split=target,record_ids=ids))
    for ids in splits.values(): ids.sort()
    stats={k:dict(count=len(ids),courses=dict(Counter(rows[i]['course_code'] for i in ids)),tasks=dict(Counter(rows[i]['task_type'] for i in ids))) for k,ids in splits.items()}
    return dict(schema_version='w5-split-v1',seed=seed,ratio_targets=ratios,splits=splits,components=assignments,
        dataset_fingerprint=digest({rid:rows[rid]['content_sha256'] for rid in sorted(selected)}),stats=stats,
        warning='Ratios are approximate; components remain intact. Instruction holdout is not an independent QA benchmark.')
