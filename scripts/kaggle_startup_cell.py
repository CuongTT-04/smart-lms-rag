# This source is embedded at the end of the notebook by append_kaggle_startup.py.
# It needs no earlier notebook cells, no baseline index and no evaluation runs.
def _ohayo_find_checkpoint(input_root, working_root):
    candidates=list(input_root.rglob('checkpoint-manifest.json'))
    if not candidates:
        working=working_root/'ohayo-model'/'checkpoint-manifest.json'
        if working.is_file():candidates=[working]
    if len(candidates)==1:return str(candidates[0].parent)
    if not candidates:
        raise RuntimeError('Khong tim thay checkpoint trong Input hoac /kaggle/working/ohayo-model. '
                           'Gan Output da luu vao Input, hoac dat OHAYO_CHECKPOINT toi thu muc checkpoint.')
    raise RuntimeError('Tim thay nhieu checkpoint. Dat os.environ["OHAYO_CHECKPOINT"] = mot trong: '
                       + ', '.join(str(p.parent) for p in candidates))


def _ohayo_tunnel_error(error):
    """Keep only allowlisted diagnostics, never raw logs/credential values."""
    import re
    raw = ' '.join(str(value) for value in (
        error, getattr(error, 'ngrok_error', ''), getattr(error, 'body', '')))
    codes = sorted(set(re.findall(r'ERR_NGROK_[0-9]+', raw)))
    markers = [word for word in ('inspect', 'bind_tls', 'certificate', 'authentication',
        'authtoken', 'quota', 'session', 'endpoint', 'connection refused', 'download')
        if word in raw.lower()]
    from urllib.parse import urlsplit
    status = getattr(error, 'status_code', None)
    status = str(status) if type(status) is int else '?'
    path = urlsplit(getattr(error, 'url', '')).path
    path = path if path in ('/api/endpoints', '/api/tunnels') else '?'
    return ' | '.join([type(error).__name__, 'HTTP=' + status, 'path=' + path,
                       ', '.join(codes) or 'khong co ma ERR_NGROK',
                       'dau hieu: ' + (', '.join(markers) or 'chua xac dinh')])


def _ohayo_start(runtime_factory=None, service_signature='single-v1', source_bundle=None):
    import hashlib
    import importlib
    import importlib.metadata as metadata
    import json
    import os
    from pathlib import Path, PurePosixPath
    import subprocess
    import sys
    import zipfile

    # Install only when needed; never replace Kaggle's CUDA torch.
    from packaging.specifiers import SpecifierSet
    requirements = {'transformers': '==4.57.6', 'bitsandbytes': '==0.48.2',
                    'accelerate': '>=1.6,<2', 'pyngrok': '>=7,<10'}
    missing = []
    for name, constraint in requirements.items():
        try:
            valid = metadata.version(name) in SpecifierSet(constraint)
        except metadata.PackageNotFoundError:
            valid = False
        if not valid:
            missing.append(name + constraint)
    if missing:
        subprocess.run([sys.executable, '-m', 'pip', 'install', *missing], check=True)
        importlib.invalidate_caches()
    for name in requirements:
        loaded = sys.modules.get(name)
        if loaded is not None and getattr(loaded, '__version__', metadata.version(name)) != metadata.version(name):
            raise RuntimeError('Thu vien trong kernel khac ban vua cai. Chon Restart & Clear Cell Outputs '
                               '(KHONG Factory Reset), roi chay lai cell cuoi nay.')
    # A fresh interpreter confirms disk imports before any model allocation.
    probe = subprocess.run([sys.executable, '-c',
        'from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig; import bitsandbytes'],
        capture_output=True, text=True)
    if probe.returncode:
        raise RuntimeError('Kiem tra import that bai:\n' + probe.stderr[-4000:])

    def secret(label):
        value = os.environ.get(label)
        if not value:
            try:
                from kaggle_secrets import UserSecretsClient
                value = UserSecretsClient().get_secret(label)
            except Exception:
                raise RuntimeError('Them va bat quyen Secret ' + label + ' trong Add-ons > Secrets.') from None
        return value
    api_token = secret('OHAYO_INFERENCE_TOKEN')
    ngrok_token = secret('NGROK_AUTHTOKEN')
    if len(api_token) < 32 or not api_token.isascii() or any(c.isspace() for c in api_token):
        raise RuntimeError('OHAYO_INFERENCE_TOKEN can token ngau nhien ASCII >=32 ky tu, khong co khoang trang.')

    existing = globals().get('_ohayo_service')
    if existing and existing.get('signature', 'single-v1') != service_signature:
        raise RuntimeError('Da doi che do/source. Chon Restart & Clear Cell Outputs (KHONG Factory Reset), '
                           'roi chi chay cell khoi dong moi.')
    if existing and existing['thread_alive']() and existing['token_hash'] == hashlib.sha256(api_token.encode()).hexdigest():
        # Confirm the tunnel still exists; do not silently start another model/server.
        from pyngrok import ngrok
        if existing['url'] in {t.public_url for t in ngrok.get_tunnels(pyngrok_config=existing['ngrok_config'])}:
            print('SAN SANG (dung lai dich vu):', existing['url'])
            return existing
        existing['server'].shutdown()
        if hasattr(existing['server'], 'wait_idle') and not existing['server'].wait_idle(timeout=110):
            raise RuntimeError('Model van dang xu ly. Doi hoan tat roi chay lai cell.')
        existing['server'].server_close()
    elif existing:
        existing['server'].shutdown()
        if hasattr(existing['server'], 'wait_idle') and not existing['server'].wait_idle(timeout=110):
            raise RuntimeError('Model van dang xu ly. Doi hoan tat roi chay lai cell.')
        existing['server'].server_close()
        from pyngrok import ngrok
        ngrok.disconnect(existing['url'], pyngrok_config=existing['ngrok_config'])

    # Load verified provider source from the existing Input (ZIP or extracted dataset).
    package_override = os.environ.get('OHAYO_SOURCE_PACKAGE', '')
    input_root = Path('/kaggle/input')
    if source_bundle is not None:
        package = None
    elif not package_override:
        candidates = list(input_root.rglob('generation-provider.zip'))
        candidates += [p.parent for p in input_root.rglob('generation-provider-manifest.json')]
        if len(candidates) != 1:
            raise RuntimeError('Can mot goi OHAYO Generation Provider trong Input; '
                               'neu nhieu goi, dat os.environ["OHAYO_SOURCE_PACKAGE"] = duong_dan.')
        package = candidates[0]
    else:
        package = Path(package_override)
    manifest_name = 'generation-provider-manifest.json'
    if source_bundle is not None:
        manifest = source_bundle['manifest']
        payloads = {name: content.encode('utf-8') for name, content in source_bundle['files'].items()}
        if set(payloads) != set(manifest['files']) or sum(map(len, payloads.values())) > 8 * 1024**2:
            raise RuntimeError('Embedded source khong khop manifest')
    elif package.is_dir():
        manifest = json.loads((package / manifest_name).read_text(encoding='utf-8'))
        payloads = {}
        for name in manifest['files']:
            relative = PurePosixPath(name)
            target = package / name
            if (relative.is_absolute() or '..' in relative.parts or '\\' in name
                    or not target.resolve().is_relative_to(package.resolve()) or target.is_symlink()):
                raise RuntimeError('Duong dan source khong hop le')
            payloads[name] = target.read_bytes()
    else:
        with zipfile.ZipFile(package) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or sum(p.file_size for p in archive.infolist()) > 8 * 1024**2:
                raise RuntimeError('Source ZIP khong hop le')
            manifest = json.loads(archive.read(manifest_name))
            if set(names) != set(manifest['files']) | {manifest_name}:
                raise RuntimeError('ZIP khong khop manifest')
            payloads = {name: archive.read(name) for name in manifest['files']}
    if manifest.get('schema_version') != 1 or manifest.get('purpose') != 'local_generation_provider_source':
        raise RuntimeError('Sai source manifest')
    for name, content in payloads.items():
        relative = PurePosixPath(name)
        if (relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name
                or hashlib.sha256(content).hexdigest() != manifest['files'][name]):
            raise RuntimeError('Checksum/duong dan source khong hop le')
    root = Path('/kaggle/working/ohayo-provider-source')
    # Imported modules must match the selected source, including modules from cell 8.
    for name, module in list(sys.modules.items()):
        if name == 'apps' or name.startswith('apps.'):
            location = getattr(module, '__file__', None)
            if location:
                path = Path(location).resolve()
                if not path.is_relative_to(root.resolve()):
                    raise RuntimeError('Da import apps tu source khac. Restart Python roi chay cell cuoi.')
                relative = path.relative_to(root.resolve()).as_posix()
                if relative not in payloads or path.read_bytes() != payloads[relative]:
                    raise RuntimeError('Source dang chay khac Input. Restart Python roi chay cell cuoi.')
    for name, content in payloads.items():
        target = root / name
        if not target.resolve().is_relative_to(root.resolve()):
            raise RuntimeError('Source destination khong hop le')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    sys.path.insert(0, str(root / 'backend'))
    importlib.invalidate_caches()
    import torch
    from apps.ai.providers import LocalModelProvider, ModelConfig
    from apps.ai.rag import RAGPipeline, GenerationConfig
    if not torch.cuda.is_available():
        raise RuntimeError('Can bat GPU trong Settings truoc khi chay.')
    if runtime_factory is not None:
        pipeline, cfg = runtime_factory(torch, LocalModelProvider, ModelConfig, RAGPipeline, GenerationConfig, input_root)
    else:
        provider = globals().get('provider') or globals().get('_ohayo_provider')
        if provider is None:
            model, tokenizer = globals().get('model'), globals().get('tokenizer')
            if model is not None and tokenizer is not None:
                old_config = globals().get('config', {})
                checkpoint = globals().get('LOCAL_CHECKPOINT') or None
                provider = LocalModelProvider.from_loaded(model, tokenizer, ModelConfig(
                    revision=old_config.get('revision', ModelConfig().revision), checkpoint_path=checkpoint))
            else:
                checkpoint = os.environ.get('OHAYO_CHECKPOINT', '')
                if not checkpoint:
                    checkpoint = _ohayo_find_checkpoint(input_root,Path('/kaggle/working'))
                provider = LocalModelProvider(ModelConfig(checkpoint_path=checkpoint, local_files_only=True))
        globals()['_ohayo_provider'] = provider  # Preserve even if tunnel startup fails.
        provider.count_tokens([{'role': 'user', 'content': 'Xin chao.'}])  # Loads once; no generation.
        pipeline = RAGPipeline(provider, GenerationConfig(model=provider.config, prompt_version='bounded_guidance'))
        cfg = provider.config
    public_config = {'model': cfg.model_id, 'revision': cfg.revision, 'prompt_version': 'bounded_guidance',
        'max_input_tokens': cfg.max_input_tokens, 'max_output_tokens': cfg.max_new_tokens,
        'timeout_seconds': cfg.timeout_seconds, 'temperature': 0.0}
    # OHAYO_GATEWAY_SOURCE is embedded in this same cell; no extra source upload needed.
    gateway = {}
    exec(OHAYO_GATEWAY_SOURCE, gateway)
    server = gateway['start_gateway'](pipeline, api_token, public_config)
    from pyngrok import ngrok, conf
    # pyngrok 9 defaults to /api/endpoints. Our bind_tls/inspect options use
    # the supported tunnels schema; select it explicitly (agent remains v3).
    ngrok_config = conf.PyngrokConfig(auth_token=ngrok_token, config_version='2')
    try:
        tunnel = ngrok.connect(addr='http://127.0.0.1:8765', proto='http',
                               bind_tls=True, inspect=False, pyngrok_config=ngrok_config)
        url = tunnel.public_url
        if not url.startswith('https://'):
            ngrok.disconnect(url, pyngrok_config=ngrok_config)
            raise RuntimeError('Tunnel phai la HTTPS')
    except Exception as exc:
        server.shutdown()
        server.server_close()
        raise RuntimeError('Khong mo duoc HTTPS tunnel. Kiem tra NGROK_AUTHTOKEN, Internet '
                           'va quota ngrok; model van duoc giu de chay lai cell. '
                           'Chi tiet an toan: ' + _ohayo_tunnel_error(exc)) from None
    import threading
    # server itself records its service thread for repeat-start checks.
    service = {'server': server, 'url': url, 'ngrok_config': ngrok_config, 'signature': service_signature,
        'thread_alive': server.service_thread.is_alive,
        'token_hash': hashlib.sha256(api_token.encode()).hexdigest()}
    globals()['_ohayo_service'] = service
    from urllib.request import Request, urlopen
    with urlopen(Request('http://127.0.0.1:8765/health',
                 headers={'Authorization': 'Bearer ' + api_token}), timeout=5) as response:
        if not json.load(response)['ready']:
            raise RuntimeError('Health check chua san sang')
    config_path = Path('/kaggle/working/w4-generation-kaggle.json')
    config_path.write_text(json.dumps(public_config, indent=2), encoding='utf-8')
    print('SAN SANG:', url)
    print('AI_GENERATOR=apps.ai.remote.generate_answer')
    print('AI_INFERENCE_URL=' + url)
    print('Tai w4-generation-kaggle.json cho backend. AI_INFERENCE_TOKEN dung cung Secret '
          'OHAYO_INFERENCE_TOKEN (khong dan token vao chat/notebook output).')
    print('Backend van can FAISS/catalog khop tai lieu PostgreSQL. Cell nay khong tao retrieval index.')
    return service


_ohayo_service = _ohayo_start()
