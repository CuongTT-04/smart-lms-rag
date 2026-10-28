import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class MemoryCellTests(unittest.TestCase):
    def module(self):
        spec = importlib.util.spec_from_file_location('append_memory', ROOT/'scripts/append_kaggle_memory.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        return module

    def test_appends_only_new_cells_and_embeds_memory_provider(self):
        module = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'sample.ipynb'
            original = dict(nbformat=4, metadata={'keep':'value'}, cells=[dict(id='old',cell_type='code',source=['old()'],outputs=[{'text':'evidence'}],execution_count=1)])
            path.write_text(json.dumps(original),encoding='utf-8')
            module.append(path)
            current=json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(current['cells'][:-2],original['cells'])
            self.assertEqual(current['metadata'],original['metadata'])
            self.assertEqual(current['cells'][-1]['id'],'ohayo-chat-memory-startup')
            code=''.join(current['cells'][-1]['source'])
            compile(code,'memory-cell','exec')
            self.assertIn('chat_history_v1',code)
            self.assertIn('backend/apps/ai/rag/conversation.py',code)
            with self.assertRaises(ValueError): module.append(path)
