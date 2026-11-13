from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.comparison.training_environment import snapshot, verify


class EnvironmentTests(unittest.TestCase):
    def test_active_resolution_not_last_system_listing(self):
        config=dict(dependencies={'transformers':'4.57.6'})
        legacy=dict(dependencies={'transformers':'5.20.2'})
        with patch('scripts.comparison.training_environment.environment',return_value=legacy), \
             patch('scripts.comparison.training_environment.version',return_value='4.57.6'):
            result=snapshot(config)
        self.assertEqual(result['dependencies'],config['dependencies'])
        self.assertEqual(result['distribution_listing_not_effective_versions'],{'transformers':'5.20.2'})

    def test_actual_version_mismatch_still_fails(self):
        with patch('scripts.comparison.training_environment.environment',return_value=dict(dependencies={})), \
             patch('scripts.comparison.training_environment.version',return_value='5.20.2'):
            with self.assertRaisesRegex(ValueError,'EFFECTIVE_ENVIRONMENT_PIN'):
                snapshot(dict(dependencies={'transformers':'4.57.6'}))

    def test_modern_snapshot_passes(self):
        config=dict(dependencies={'transformers':'4.57.6'})
        result=verify(None,None,config,dict(dependency_resolution='importlib.metadata.version',dependencies=config['dependencies']))
        self.assertEqual(result['status'],'DIRECT_EFFECTIVE_VERSION_SNAPSHOT_PASSED')

    def test_modern_wrong_version_rejected(self):
        with self.assertRaisesRegex(ValueError,'ENVIRONMENT_PIN'):
            verify(None,None,dict(dependencies={'transformers':'4.57.6'}),
                   dict(dependency_resolution='importlib.metadata.version',dependencies={'transformers':'5.20.2'}))

    def test_unrecognized_legacy_run_never_waives_pin(self):
        with patch('scripts.comparison.training_environment.sha_file',return_value='0'*64):
            with self.assertRaisesRegex(ValueError,'LEGACY_ENVIRONMENT_NOT_AUTHENTICATED'):
                verify(Path('run'),Path('package'),dict(dependencies={}),dict(dependencies={}))

    def test_no_marker_is_not_a_direct_snapshot_even_if_values_match(self):
        with patch('scripts.comparison.training_environment.sha_file',return_value='0'*64):
            with self.assertRaisesRegex(ValueError,'LEGACY_ENVIRONMENT_NOT_AUTHENTICATED'):
                verify(Path('run'),Path('package'),dict(dependencies={'x':'1'}),dict(dependencies={'x':'1'}))
