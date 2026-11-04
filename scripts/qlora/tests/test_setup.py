from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts.qlora.data import read_json
from scripts.qlora.setup import check_hardware, main
from scripts.qlora.runtime import verify_inventory

RECIPE = Path(__file__).resolve().parents[3] / 'configs/qlora-pilot.json'


class EnvironmentTests(unittest.TestCase):
    def gpu(self):
        return SimpleNamespace(version=SimpleNamespace(cuda='12.8'), cuda=SimpleNamespace(
            device_count=Mock(return_value=1),
            is_available=Mock(return_value=True), get_device_name=Mock(return_value='Tesla T4'),
            mem_get_info=Mock(return_value=(14 * 1024 ** 3, 16 * 1024 ** 3))))

    def test_checks_t4_memory_and_disk(self):
        with patch('scripts.qlora.setup.shutil.disk_usage', return_value=SimpleNamespace(free=25 * 1024 ** 3)):
            self.assertEqual(check_hardware(self.gpu(), Path.cwd())['device'], 'Tesla T4')

    def test_rejects_cpu_or_wrong_gpu(self):
        for cuda, name in ((False, 'Tesla T4'), (True, 'Tesla P100')):
            gpu = self.gpu()
            gpu.cuda.is_available.return_value = cuda
            gpu.cuda.get_device_name.return_value = name
            with self.assertRaises(ValueError):
                check_hardware(gpu, Path.cwd())

    def test_rejects_two_visible_gpus_before_probe(self):
        gpu = self.gpu()
        gpu.cuda.device_count.return_value = 2
        with self.assertRaisesRegex(ValueError, 'NO_DATAPARALLEL'):
            check_hardware(gpu, Path.cwd())

    def test_rejects_busy_gpu_and_insufficient_disk(self):
        gpu = self.gpu()
        gpu.cuda.mem_get_info.return_value = (1024, 16 * 1024 ** 3)
        with self.assertRaisesRegex(ValueError, 'VRAM'):
            check_hardware(gpu, Path.cwd())
        with patch('scripts.qlora.setup.shutil.disk_usage', return_value=SimpleNamespace(free=1024)):
            with self.assertRaisesRegex(ValueError, '1_GIB'):
                check_hardware(self.gpu(), Path.cwd())

    def test_environment_does_not_require_space_for_unloaded_base(self):
        for available in (1024 ** 3, 4 * 1024 ** 3, 19 * 1024 ** 3):
            with patch('scripts.qlora.setup.shutil.disk_usage', return_value=SimpleNamespace(free=available)):
                report = check_hardware(self.gpu(), Path.cwd())
                self.assertEqual(report['free_working_disk_bytes'], available)
                self.assertEqual(report['training_storage_check'], 'PENDING_BEFORE_BASE_WEIGHT_LOADING')

    def test_cpu_failure_is_recorded_and_never_calls_nf4_or_qwen(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            output = root / 'report'
            with patch('scripts.qlora.setup.version', side_effect=read_json(RECIPE)['dependencies'].__getitem__), \
                 patch('torch.cuda.is_available', return_value=False), \
                 patch('scripts.qlora.setup.probe_nf4') as probe, \
                 patch('scripts.qlora.setup.load_pilot') as data:
                with self.assertRaisesRegex(ValueError, 'CUDA_REQUIRED'):
                    main(['--bundle', str(root / 'input'), '--config', str(RECIPE), '--output', str(output)])
                probe.assert_not_called()
                data.assert_not_called()
            report = read_json(output / 'environment-check.json')
            self.assertEqual(report['status'], 'FAILED')
            self.assertEqual(report['gpu_smoke'], 'NOT_RUN')
            manifest = read_json(output / 'run-manifest.json')
            self.assertEqual(manifest['status'], 'FAILED')
            verify_inventory(output, manifest['files'])

    def test_environment_only_rejects_training_flags(self):
        from scripts.qlora.kaggle import main as launch
        with self.assertRaisesRegex(ValueError, 'ENVIRONMENT_ONLY_ARGUMENT_CONFLICT'):
            launch(['--bundle', 'input', '--profile', 'smoke', '--output', 'new',
                    '--environment-only', '--allow-model-download'])

    def test_launcher_repairs_partial_env_without_ensurepip_and_targets_its_pip(self):
        import sys
        from scripts.qlora.kaggle import main as launch
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            environment = root / 'partial-env'
            (environment / 'bin').mkdir(parents=True)
            python = environment / 'bin/python'
            python.write_bytes(b'fixture-not-executable')
            calls = []
            def run(command, **kwargs):
                calls.append(command)
                return SimpleNamespace(stdout='2.8.0+cu128\n')
            # The real platform/path guards are tested separately. This fixture
            # exercises the subprocess wiring without installing into the host.
            with patch('scripts.qlora.kaggle.sys.platform', 'linux'), \
                 patch('scripts.qlora.kaggle.Path.is_dir', return_value=True), \
                 patch('scripts.qlora.kaggle.Path.is_relative_to', return_value=True), \
                 patch('scripts.qlora.kaggle.version', return_value='2.8.0+cu128'), \
                 patch('scripts.qlora.kaggle.subprocess.run', side_effect=run):
                launch(['--bundle', str(root / 'input'), '--profile', 'smoke',
                        '--environment', str(environment), '--output', str(root / 'report'),
                        '--environment-only'])
            self.assertEqual(calls[0][:4], [sys.executable, '-m', 'venv', '--without-pip'])
            self.assertIn('--system-site-packages', calls[0])
            self.assertEqual(calls[1][:5], [sys.executable, '-m', 'pip', '--python', str(python)])
            self.assertIn('--constraint', calls[1])
            self.assertIn('scripts.qlora.setup', calls[-1])
