from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.qlora.data import read_json
from scripts.qlora.runtime import write_json
from scripts.qlora.storage import budget, check_training_storage, GIB

RECIPE = Path(__file__).resolve().parents[3] / 'configs/qlora-pilot.json'


class StorageTests(unittest.TestCase):
    def test_known_budget_fits_19_gib_without_requiring_20(self):
        result = budget(15_232_000_000, int(19.153 * GIB), int(19.153 * GIB), True)
        self.assertTrue(result['passed'])

    def test_shared_volume_reserves_download_and_output_together(self):
        self.assertFalse(budget(14 * GIB, 16 * GIB, 16 * GIB, True)['passed'])
        self.assertTrue(budget(14 * GIB, 15 * GIB, 2 * GIB, False)['passed'])

    def test_cached_base_needs_only_output_budget(self):
        self.assertTrue(budget(0, 2 * GIB, 2 * GIB, True)['passed'])
        self.assertFalse(budget(0, GIB, GIB, True)['passed'])

    def test_separate_volumes_must_both_fit(self):
        self.assertFalse(budget(14 * GIB, 14 * GIB, 50 * GIB, False)['passed'])
        self.assertFalse(budget(14 * GIB, 50 * GIB, GIB, False)['passed'])

    def test_metadata_check_does_not_download_weights(self):
        config = read_json(RECIPE)
        files = [SimpleNamespace(rfilename='model-00001-of-00002.safetensors', size=8),
                 SimpleNamespace(rfilename='model-00002-of-00002.safetensors', size=16),
                 SimpleNamespace(rfilename='pytorch_model.bin', size=99999)]
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            cached = root / 'one'
            cached.write_bytes(b'12345678')
            with patch('huggingface_hub.HfApi') as api, \
                 patch('huggingface_hub.try_to_load_from_cache', side_effect=[str(cached), None]), \
                 patch('huggingface_hub.hf_hub_download') as download, \
                 patch('scripts.qlora.storage.shutil.disk_usage', return_value=SimpleNamespace(free=25 * GIB)):
                api.return_value.model_info.return_value = SimpleNamespace(sha=config['revision'], siblings=files)
                result = check_training_storage(config, root / 'cache', root, allow_download=True)
                self.assertEqual(result['missing_weight_bytes'], 16)
                self.assertEqual(result['cached_weight_bytes'], 8)
                self.assertTrue(result['passed'])
                download.assert_not_called()
                self.assertEqual(api.return_value.model_info.call_args.kwargs['revision'], config['revision'])

    def test_wrong_revision_or_unknown_size_is_rejected(self):
        config = read_json(RECIPE)
        with tempfile.TemporaryDirectory() as name:
            for revision, size in (('wrong', 8), (config['revision'], None)):
                with patch('huggingface_hub.HfApi') as api:
                    api.return_value.model_info.return_value = SimpleNamespace(sha=revision, siblings=[
                        SimpleNamespace(rfilename='model.safetensors', size=size)])
                    with self.assertRaises(ValueError):
                        check_training_storage(config, Path(name) / 'cache', name, allow_download=True)

    def test_offline_uses_only_complete_pinned_cache(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            index = root / 'index.json'
            shard = root / 'shard'
            shard.write_bytes(b'1234')
            write_json(index, {'weight_map': {'layer': 'model-00001-of-00001.safetensors'}})
            with patch('huggingface_hub.hf_hub_download', return_value=str(index)) as download, \
                 patch('huggingface_hub.try_to_load_from_cache', return_value=str(shard)), \
                 patch('huggingface_hub.HfApi') as api, \
                 patch('scripts.qlora.storage.shutil.disk_usage', return_value=SimpleNamespace(free=3 * GIB)):
                result = check_training_storage(read_json(RECIPE), root / 'cache', root)
                self.assertEqual(result['missing_weight_bytes'], 0)
                self.assertTrue(download.call_args.kwargs['local_files_only'])
                api.assert_not_called()
