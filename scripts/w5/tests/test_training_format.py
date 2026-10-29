import copy
import unittest
from pathlib import Path
from scripts.w5.common import load_contract, read_jsonl, projected
from scripts.w5.training import check_training_format

ROOT=Path(__file__).resolve().parents[3]


class Tokenizer:
    eos_token_id=99
    all_special_tokens=['<eos>']
    chat_template='fake-template-for-unit-tests'
    def encode(self, text, add_special_tokens=False):return [10] if text=='\n' else [1]*len(text)
    def apply_chat_template(self,messages,tokenize=True,add_generation_prompt=False):
        tokens=[]
        for m in messages:tokens.extend([2]+[1]*len(m['content'])+([99] if m['role']=='assistant' else [3]))
        return tokens+[2] if add_generation_prompt else tokens


class TrainingTests(unittest.TestCase):
    def setUp(self):
        self.c=load_contract(ROOT/'data/instruction/w5/contract');self.row=read_jsonl(ROOT/'data/fixtures/w5-instruction-contract.jsonl')[0]
        self.payload={'prompt':projected(self.row,self.c)[1],'completion':[{'role':'assistant','content':self.row['target_text']}]}
        self.c['training'].update(max_prompt_tokens=10000,max_completion_tokens=1000,max_sequence_tokens=11000)

    def test_exact_prompt_and_completion_only_mask(self):
        r=check_training_format([self.row],[self.payload],Tokenizer(),self.c)
        self.assertTrue(r['passed'],r)
        self.assertGreater(r['records'][0]['supervised_tokens'],0)
        self.assertTrue(r['records'][0]['eos_supervised'])

    def test_changed_prompt_completion_metadata_or_limits_fail(self):
        for kind in ('prompt','completion','metadata','limit','eos'):
            with self.subTest(kind=kind):
                p=copy.deepcopy(self.payload);c=copy.deepcopy(self.c);t=Tokenizer()
                if kind=='prompt':p['prompt'][1]['content']+='private answer key'
                if kind=='completion':p['completion'][0]['content']='wrong target'
                if kind=='metadata':p['reviews']='secret'
                if kind=='limit':c['training']['max_prompt_tokens']=2
                if kind=='eos':t.eos_token_id=98
                self.assertFalse(check_training_format([self.row],[p],t,c)['passed'])

    def test_tokenizer_cannot_silently_change_prefix(self):
        class Bad(Tokenizer):
            def apply_chat_template(self,*args,**kwargs):return [8]+super().apply_chat_template(*args,**kwargs) if kwargs.get('add_generation_prompt') else super().apply_chat_template(*args,**kwargs)
        self.assertFalse(check_training_format([self.row],[self.payload],Bad(),self.c)['passed'])
