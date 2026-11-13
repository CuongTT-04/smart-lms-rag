"""Separate effective dependency resolution from a mixed site-packages listing."""
from importlib.metadata import version
from scripts.qlora.data import read_json, require, sha_file
from scripts.qlora.runtime import environment

LEGACY_PACKAGE = '5de778a2108d9309d55654e8b2d406b0588a8d11aca5afd17a9ebf55d98993f5'
LEGACY_RUN = 'd00dc8a4027622cf62f3cd3091dc900baf018e96034f0700c06378e876105aaf'


def snapshot(config):
    result = environment()
    # distributions() can contain both venv and system metadata; a dict keeps
    # the last candidate, whereas version(name) resolves the first active one.
    result['distribution_listing_not_effective_versions'] = result.pop('dependencies')
    result['dependencies'] = {name:version(name) for name in config['dependencies']}
    result['dependency_resolution'] = 'importlib.metadata.version'
    require(result['dependencies'] == config['dependencies'], 'TRAINING_EFFECTIVE_ENVIRONMENT_PIN')
    return result


def verify(run, package, config, env):
    if env.get('dependency_resolution') == 'importlib.metadata.version':
        require(env['dependencies'] == config['dependencies'], 'TRAINING_ENVIRONMENT_PIN')
        return dict(status='DIRECT_EFFECTIVE_VERSION_SNAPSHOT_PASSED')
    # This is a one-run recovery, not a general waiver for mismatching versions.
    # The exact immutable run and approved package authenticate the pin guard
    # that must return before model creation/training. Never rewrite old evidence.
    require(sha_file(package/'manifest.json') == LEGACY_PACKAGE
            and sha_file(run/'run-manifest.json') == LEGACY_RUN, 'LEGACY_ENVIRONMENT_NOT_AUTHENTICATED')
    for path in package.glob('scripts/**/*.py'):
        saved = run/'source'/path.relative_to(package)
        require(saved.is_file() and sha_file(saved) == sha_file(path), 'LEGACY_EXECUTED_SOURCE_BINDING')
    require(read_json(run/'run-manifest.json')['status'] == 'TRAINING_COMPLETED', 'LEGACY_TRAINING_NOT_COMPLETED')
    return dict(status='LEGACY_PIN_GUARD_PROVENANCE_VERIFIED_NOT_DIRECT_VERSION_SNAPSHOT',
        observed_inventory='MIXED_SITE_PACKAGES_LISTING_NOT_EFFECTIVE_VERSIONS',
        limitation='Effective versions were not recorded directly. Pin checks are inferred from the exact authenticated trainer/load_training_model control flow; do not relabel the original environment.json as a correct version snapshot.',
        original_environment_sha256=sha_file(run/'environment.json'))
