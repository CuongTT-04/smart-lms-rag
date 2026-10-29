import copy
import unittest
from scripts.w5.splitting import build_split_plan


def record(i, group=None, family=None, parent=None):
    return dict(record_id=f'W5_B_{i:05}',source_group_ids=[group or f'G{i}'],variant_family_id=family or f'F{i}',parent_record_id=parent,course_code='THMLN',task_type='qa',content_sha256=str(i))


class SplitTests(unittest.TestCase):
    def test_stable_whole_components_and_nonempty(self):
        rows=[record(i) for i in range(1,21)]
        ids=[r['record_id'] for r in rows]
        a=build_split_plan(rows,ids,[]);b=build_split_plan(list(reversed(rows)),list(reversed(ids)),[])
        self.assertEqual(a,b)
        self.assertEqual([len(a['splits'][k]) for k in ('train','validation','instruction_holdout')],[16,2,2])
        self.assertEqual(len({rid for ids in a['splits'].values() for rid in ids}),20)

    def test_group_family_parent_multisource_and_confirmed_pairs_are_transitive(self):
        rows=[record(i) for i in range(1,9)]
        rows[1]['source_group_ids']=['G1','G2'];rows[2]['variant_family_id']='F2'
        rows[3]['parent_record_id']=rows[2]['record_id']
        pairs=[(rows[3]['record_id'],rows[4]['record_id'])]
        p=build_split_plan(rows,[r['record_id'] for r in rows],pairs)
        split={rid:name for name,ids in p['splits'].items() for rid in ids}
        self.assertEqual(len({split[r['record_id']] for r in rows[:5]}),1)

    def test_too_few_groups_unknown_ids_and_unselected_parent_fail(self):
        with self.assertRaises(ValueError):build_split_plan([record(1),record(2)],['W5_B_00001','W5_B_00002'],[])
        rows=[record(i) for i in range(1,5)]
        with self.assertRaises(ValueError):build_split_plan(rows,['foreign'],[])
        rows[0]['parent_record_id']='MISSING'
        with self.assertRaises(ValueError):build_split_plan(rows,[r['record_id'] for r in rows],[])
