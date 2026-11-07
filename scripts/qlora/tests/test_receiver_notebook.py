import unittest
from pathlib import Path
import json

class ReceiverNotebookTests(unittest.TestCase):
    def test_receiver_changes_only_bootstrap_and_label_not_frozen_gpu_logic(self):
        from scripts.qlora.build_receiver import receiver_notebook
        root=Path(__file__).resolve().parents[3]
        original=json.loads((root/'notebooks/qlora_verification.ipynb').read_text(encoding='utf8'))
        result=receiver_notebook(original,'f'*64)
        for i in (4,5,6):self.assertEqual(result['cells'][i]['source'],original['cells'][i]['source'])
        self.assertIn('f'*64,''.join(result['cells'][1]['source']))
        self.assertIn('qlora-cuong-verification',''.join(result['cells'][1]['source']))
        self.assertFalse(result['metadata']['ohayo_receiver']['gpu_executed'])
        for i,c in enumerate(result['cells']):
            if c['cell_type']=='code':compile(''.join(c['source']),f'cell-{i}','exec')

    def test_identical_bundle_copies_in_existing_inputs_are_accepted(self):
        import hashlib, tempfile
        from scripts.qlora.build_receiver import receiver_notebook
        root=Path(__file__).resolve().parents[3]
        original=json.loads((root/'notebooks/qlora_verification.ipynb').read_text(encoding='utf8'))
        content=b'authenticated fixture'; sha=hashlib.sha256(content).hexdigest()
        notebook=receiver_notebook(original,sha)
        code=''.join(notebook['cells'][1]['source']).split('def unpack(')[0]
        namespace={};exec(code,namespace)
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            for name in ('existing','new'):
                (base/name).mkdir();(base/name/'tools.bundle').write_bytes(content)
            namespace['INPUT']=base
            self.assertEqual(namespace['obtain']('tools.bundle'),content)

    def test_environment_probe_and_evaluation_use_same_python_environment(self):
        import ast
        from types import SimpleNamespace
        from scripts.qlora.build_receiver import receiver_notebook
        root=Path(__file__).resolve().parents[3]
        original=json.loads((root/'notebooks/qlora_verification.ipynb').read_text(encoding='utf8'))
        result=receiver_notebook(original,'f'*64)
        tree=ast.parse(''.join(result['cells'][2]['source']))
        assignment=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='command' for t in n.targets))
        environment=Path('/kaggle/working/qlora-cuong-env')
        scope=dict(sys=SimpleNamespace(executable='/python'),HANDOFF=Path('/handoff'),REPORT=Path('/report'),VENV=environment)
        command=eval(compile(ast.Expression(assignment.value),'<probe-args>','eval'),scope)
        self.assertIn('--environment',command)
        self.assertEqual(command[command.index('--environment')+1],str(environment))

if __name__=='__main__':unittest.main()
