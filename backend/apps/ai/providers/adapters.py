"""Verified, inference-only LoRA attachment; no model downloads or training."""
import hashlib
import json
from pathlib import Path

from .base import GenerationError
from .checkpoint import file_sha256
from .local import LocalModelProvider, verify_saved_qwen_pattern

TOKENIZER_FILES = {'config.json', 'tokenizer.json', 'tokenizer_config.json', 'vocab.json', 'merges.txt'}


def tokenizer_digest(data):
    # save_pretrained may change whitespace or padding metadata, not tokenization.
    keys = ('model', 'pre_tokenizer', 'normalizer', 'post_processor', 'decoder', 'added_tokens')
    semantic = {key: data.get(key) for key in keys}
    return hashlib.sha256(json.dumps(semantic, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def validate_adapter(directory, expected_sha256, config):
    try:
        root = Path(directory)
        names = {'adapter_config.json', 'adapter_model.safetensors', 'tokenizer-reference.json'}
        names |= {'tokenizer/' + name for name in TOKENIZER_FILES}
        if not root.is_dir() or root.is_symlink():
            raise ValueError('Unsafe adapter directory')
        manifest = json.loads((root / 'serving-manifest.json').read_bytes())
        if (manifest.get('schema_version') != 1 or set(manifest['files']) != names
                or manifest['model'] != config.model_id or manifest['revision'] != config.revision):
            raise ValueError('Adapter manifest identity mismatch')
        if any(p.is_symlink() for p in root.rglob('*')) or {
                p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()
        } != names | {'serving-manifest.json'}:
            raise ValueError('Unexpected adapter files')
        for name in names:
            path = root / name
            record = manifest['files'][name]
            if (path.is_symlink() or not path.is_file() or path.stat().st_size != record['size_bytes']
                    or file_sha256(path) != record['sha256']):
                raise ValueError('Adapter file integrity mismatch')
        if manifest['files']['adapter_model.safetensors']['sha256'] != expected_sha256:
            raise ValueError('Adapter is not the selected candidate')
        adapter = json.loads((root / 'adapter_config.json').read_bytes())
        if (adapter.get('base_model_name_or_path') != config.model_id
                or adapter.get('revision') != config.revision
                or adapter.get('peft_type') != 'LORA' or adapter.get('task_type') != 'CAUSAL_LM'
                or adapter.get('modules_to_save') or adapter.get('bias') != 'none'
                or adapter.get('use_dora') or adapter.get('r') != 8 or adapter.get('lora_alpha') != 16):
            raise ValueError('Unsupported adapter configuration')
        reference = json.loads((root / 'tokenizer-reference.json').read_bytes())
        if (reference['model_id'], reference['revision']) != (config.model_id, config.revision):
            raise ValueError('Tokenizer base identity mismatch')
        if set(reference['files']) != TOKENIZER_FILES:
            raise ValueError('Incomplete training tokenizer inventory')
        for name, record in reference['files'].items():
            if manifest['files']['tokenizer/' + name] != {
                    'sha256': record['sha256'], 'size_bytes': record['size_bytes']}:
                raise ValueError('Tokenizer file differs from the bound training reference')
        return manifest, reference
    except Exception as exc:
        raise GenerationError('ADAPTER_INVALID', 'Adapter identity or integrity verification failed.') from exc


def check_active_adapter(model):
    from peft.tuners.lora import LoraLayer
    layers = [module for module in model.modules() if isinstance(module, LoraLayer)]
    if (getattr(model, 'active_adapters', None) != ['default'] or not layers
            or any(layer.disable_adapters or layer.merged_adapters
                   or list(layer.active_adapters) != ['default'] for layer in layers)):
        raise GenerationError('ADAPTER_INACTIVE', 'The selected adapter is disabled, merged or not active.')
    return len(layers)


class TrainingTokenizerProvider(LocalModelProvider):
    def __init__(self, config, *, adapter_path, adapter_sha256):
        super().__init__(config)
        self.adapter_path = str(adapter_path)
        self.adapter_sha256 = adapter_sha256
        self.training_tokenizer_sha256 = None

    def _load_tokenizer(self, loader, source, kwargs):
        # Model weights still come from the verified NF4 checkpoint, but tokenizer
        # assets must be the exact files bound to adapter training, not its old export.
        validate_adapter(self.adapter_path, self.adapter_sha256, self.config)
        directory = Path(self.adapter_path) / 'tokenizer'
        tokenizer = loader.from_pretrained(str(directory), local_files_only=True,
                                            trust_remote_code=False, fix_mistral_regex=False)
        self.tokenizer_audit = verify_saved_qwen_pattern(tokenizer, directory)
        self.tokenizer_audit['source'] = 'verified_adapter_training_tokenizer'
        return tokenizer

    def _build_runtime(self):
        manifest, reference = validate_adapter(self.adapter_path, self.adapter_sha256, self.config)
        # Both inventories are checked before allocating Qwen; no checkpoint edits.
        model, tokenizer, torch = super()._build_runtime()
        saved = json.loads((Path(self.adapter_path) / 'tokenizer/tokenizer.json').read_bytes())
        expected_vocab = dict(saved['model']['vocab'])
        expected_vocab.update({token['content']: token['id'] for token in saved.get('added_tokens', [])})
        # Compare token IDs, not raw deserializer JSON: tokenizers versions may
        # serialize equivalent BPE merge entries using strings or pairs.
        if (tokenizer.get_vocab() != expected_vocab
                or tokenizer.eos_token_id != reference['eos_token_id']
                or tokenizer.pad_token_id != reference['pad_token_id']
                or hashlib.sha256(tokenizer.chat_template.encode()).hexdigest() != reference['chat_template_sha256']):
            raise GenerationError('ADAPTER_TOKENIZER_MISMATCH', 'Tokenizer IDs or chat template differ from training.')
        capacity = getattr(model.config, 'vocab_size', None)
        if (type(capacity) is not int or capacity <= max(
                *expected_vocab.values(), tokenizer.eos_token_id, tokenizer.pad_token_id)):
            raise GenerationError('ADAPTER_TOKENIZER_MISMATCH', 'Tokenizer IDs exceed the base model vocabulary.')
        self.training_tokenizer_sha256 = reference['files']['tokenizer.json']['sha256']
        return model, tokenizer, torch


class AdapterModelProvider(TrainingTokenizerProvider):
    def __init__(self, config, *, adapter_path, adapter_sha256):
        super().__init__(config, adapter_path=adapter_path, adapter_sha256=adapter_sha256)
        self.adapter_audit = None

    def _build_runtime(self):
        manifest, reference = validate_adapter(self.adapter_path, self.adapter_sha256, self.config)
        model, tokenizer, torch = super()._build_runtime()
        try:
            from peft import PeftModel, get_peft_model_state_dict
            from safetensors.torch import load_file
            model = PeftModel.from_pretrained(model, self.adapter_path, adapter_name='default',
                is_trainable=False, local_files_only=True, autocast_adapter_dtype=True)
            model.set_adapter('default')
            for parameter in model.parameters():
                parameter.requires_grad_(False)
            model.eval()
            expected = load_file(str(Path(self.adapter_path) / 'adapter_model.safetensors'), device='cpu')
            actual = get_peft_model_state_dict(model, adapter_name='default')
            if set(expected) != set(actual) or not expected:
                raise ValueError('Loaded adapter tensor inventory mismatch')
            for key, tensor in expected.items():
                loaded = actual[key].detach().cpu()
                if loaded.shape != tensor.shape or not torch.equal(loaded, tensor.to(loaded.dtype)):
                    raise ValueError('Loaded adapter weights mismatch')
            layers = check_active_adapter(model)
            self._check_runtime(model, tokenizer, torch, check_identity=False)
            self.adapter_audit = dict(arm='tuned_rag', adapter_sha256=self.adapter_sha256,
                adapter_config_sha256=manifest['files']['adapter_config.json']['sha256'],
                loaded_adapter_tensors=len(expected), tensor_values_match=True,
                active_adapter='default', lora_layers=layers, trainable_parameters=0,
                model=self.config.model_id, revision=self.config.revision,
                device=self.config.device, tokenizer_matches_training=True,
                tokenizer_source='verified_adapter_training_tokenizer',
                tokenizer_json_sha256=reference['files']['tokenizer.json']['sha256'])
            return model, tokenizer, torch
        except GenerationError:
            raise
        except Exception as exc:
            raise GenerationError('ADAPTER_LOAD_FAILED', 'Cannot attach and verify the selected adapter.') from exc

    def _ensure_runtime(self):
        runtime = super()._ensure_runtime()
        check_active_adapter(runtime[0])
        return runtime

    def serving_identity(self):
        if self._runtime is None or self.adapter_audit is None:
            raise GenerationError('ADAPTER_INACTIVE', 'Adapter has not been loaded and verified.')
        check_active_adapter(self._runtime[0])
        return dict(self.adapter_audit)
