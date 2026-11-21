"""Export a standalone cell that reuses the two already-loaded Qwen providers."""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def patch_source():
    sources = {name: (ROOT / 'backend/apps/ai' / path).read_text(encoding='utf-8')
               for name, path in [('tutoring', 'rag/tutoring.py'), ('pipeline', 'rag/pipeline.py'),
                                  ('gateway', 'inference_gateway.py')]}
    source = 'AYO_TUTORING_SOURCES = ' + repr(sources) + '\n' + '''
def _ayo_install_tutoring_patch():
    import json, sys, types
    from urllib.request import Request, urlopen
    from kaggle_secrets import UserSecretsClient
    providers = globals().get('_ohayo_dual_providers')
    service = globals().get('_ohayo_service')
    if not providers or len(providers) != 2 or not service:
        raise RuntimeError('Chay cell khoi dong Qwen T4 x2 truoc, roi chay lai cell nay.')
    for name, code in AYO_TUTORING_SOURCES.items():
        compile(code, 'ayo-tutoring-' + name, 'exec')
    token = UserSecretsClient().get_secret('OHAYO_INFERENCE_TOKEN')
    with urlopen(Request('http://127.0.0.1:8765/health',
            headers={'Authorization': 'Bearer ' + token}), timeout=5) as response:
        config = json.load(response)['config']
    old_server = service['server']
    if not old_server.wait_idle(timeout=110):
        raise RuntimeError('Con yeu cau dang xu ly; cho hoan tat roi chay lai cell nay.')
    module = types.ModuleType('apps.ai.rag.tutoring')
    module.__package__ = 'apps.ai.rag'
    exec(AYO_TUTORING_SOURCES['tutoring'], module.__dict__)
    sys.modules[module.__name__] = module
    namespace = dict(__package__='apps.ai.rag')
    exec(AYO_TUTORING_SOURCES['pipeline'], namespace)
    from apps.ai.rag import GenerationConfig
    pipelines = [namespace['RAGPipeline'](p, GenerationConfig(model=p.config,
        prompt_version='bounded_guidance')) for p in providers]
    gateway = {}
    exec(AYO_TUTORING_SOURCES['gateway'], gateway)
    old_server.shutdown()
    old_server.server_close()
    server = gateway['start_gateway'](pipelines, token, config)
    service.update(server=server, thread_alive=server.service_thread.is_alive)
    with urlopen(Request('http://127.0.0.1:8765/health',
            headers={'Authorization': 'Bearer ' + token}), timeout=5) as response:
        health = json.load(response)
    assert health['ready'] and 'diagnosed_hint_v1' in health['capabilities']
    print('STAGED_HINT_READY | diagnosed_hint_v1 | actual draft diagnosis | models preserved')
    print('AI_INFERENCE_URL=' + service['url'])

_ayo_install_tutoring_patch()
'''
    compile(source, 'ayo-tutoring-cell', 'exec')
    return source


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--export', required=True, type=Path)
    args = parser.parse_args()
    args.export.write_text(patch_source(), encoding='utf-8', newline='\n')
    print('Exported:', args.export)
