# Appended profile; earlier notebook cells and baseline configs are unchanged.
def _ohayo_dual_checkpoint(input_root, working_root):
    import json
    candidates = sorted(input_root.rglob('checkpoint-manifest.json'), key=lambda p: (
        'datasets' not in p.parts, str(p)))
    if not candidates:
        fallback = working_root / 'ohayo-model' / 'checkpoint-manifest.json'
        if fallback.is_file():
            candidates = [fallback]
    if len(candidates) == 1:
        return str(candidates[0].parent)
    if len(candidates) > 1:
        manifests = [json.loads(path.read_text(encoding='utf-8')) for path in candidates]
        if manifests[0].get('files') and all(item == manifests[0] for item in manifests):
            return str(candidates[0].parent)
    raise RuntimeError('Gan checkpoint da luu vao Input; neu nhieu ban khac nhau, dat '
                       'os.environ["OHAYO_CHECKPOINT"] toi dung thu muc chua checkpoint-manifest.json.')


def _ohayo_dual_runtime(torch, Provider, ModelConfig, Pipeline, GenerationConfig, input_root):
    import os
    from pathlib import Path
    if torch.cuda.device_count() < 2:
        raise RuntimeError('Can chon GPU T4 x2 trong Settings; chua nap them model.')
    if not globals().get('_ohayo_cpu_configured'):
        threads = max(1, min(2, (os.cpu_count() or 2) // 2))
        torch.set_num_threads(threads)
        try:
            torch.set_num_interop_threads(1)
        except RuntimeError:
            pass  # It can be set only before the first interop task.
        globals()['_ohayo_cpu_configured'] = True
        print('CPU torch threads:', threads, '| tokenizer parallelism: false')
    checkpoint = os.environ.get('OHAYO_CHECKPOINT') or _ohayo_dual_checkpoint(input_root, Path('/kaggle/working'))
    configs = [ModelConfig(device=f'cuda:{index}', checkpoint_path=checkpoint, local_files_only=True,
        context_tokens=6144, max_input_tokens=3584, max_new_tokens=1024, timeout_seconds=90.0) for index in range(2)]
    providers = globals().get('_ohayo_dual_providers')
    if providers is None:
        if any(globals().get(name) is not None for name in ('model', 'provider', '_ohayo_provider')):
            raise RuntimeError('Model cu con trong RAM. Chon Restart & Clear Cell Outputs, roi chi chay cell moi.')
        providers = [Provider(config) for config in configs]
        globals()['_ohayo_dual_providers'] = providers  # Retry loads only unfinished replicas.
    if len(providers) != 2 or any(p.config.fingerprint() != c.fingerprint() for p, c in zip(providers, configs)):
        raise RuntimeError('Checkpoint/cau hinh da doi. Restart Python roi chi chay cell moi.')
    pipelines = []
    for index, provider in enumerate(providers):
        print(f'Nap/kiem tra Qwen tren cuda:{index}...')
        provider.count_tokens([{'role': 'user', 'content': 'Xin chao.'}])
        pipelines.append(Pipeline(provider, GenerationConfig(model=provider.config, prompt_version='bounded_guidance')))
    return pipelines, providers[0].config


def _ohayo_dual_start():
    import os
    os.environ['TOKENIZERS_PARALLELISM'] = 'false'
    os.environ.setdefault('OMP_NUM_THREADS', '2')
    os.environ.setdefault('MKL_NUM_THREADS', '2')
    service = _ohayo_start(runtime_factory=_ohayo_dual_runtime,
        service_signature=OHAYO_DUAL_SIGNATURE, source_bundle=OHAYO_PROVIDER_BUNDLE)
    import torch
    for index in range(2):
        print(f'GPU {index}: {torch.cuda.get_device_name(index)} | '
              f'allocated={torch.cuda.memory_allocated(index)/1024**3:.2f} GiB | '
              f'reserved={torch.cuda.memory_reserved(index)/1024**3:.2f} GiB')
    print('DUAL_GPU_READY: replicas=2 | output_limit=1024 | generation_timeout=90s')
    print('Moi cau hoi dung mot GPU; hai cau hoi dong thoi moi dung ca hai GPU.')
    return service


_ohayo_service = _ohayo_dual_start()
