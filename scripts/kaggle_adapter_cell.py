"""Embedded serving profile; the notebook selects one arm before startup."""
_ohayo_base_runtime = _ohayo_dual_runtime


def _ohayo_selected_runtime(torch, Provider, ModelConfig, Pipeline, GenerationConfig, input_root):
    import hashlib
    from pathlib import Path
    if OHAYO_SERVING_ARM not in ('base_rag', 'tuned_rag'):
        raise RuntimeError('Invalid serving arm')
    from apps.ai.providers.adapters import AdapterModelProvider, TrainingTokenizerProvider
    selected = AdapterModelProvider if OHAYO_SERVING_ARM == 'tuned_rag' else TrainingTokenizerProvider

    def Provider(config):
        return selected(config, adapter_path=SERVING_PACKAGE / 'adapter',
                        adapter_sha256=EXPECTED_ADAPTER_SHA256)
    pipelines, config = _ohayo_base_runtime(torch, Provider, ModelConfig, Pipeline, GenerationConfig, input_root)
    for provider in globals()['_ohayo_dual_providers']:
        for parameter in provider._runtime[0].parameters():
            parameter.requires_grad_(False)
    return pipelines, config


def _ohayo_serving_identity():
    import hashlib
    replicas = []
    for provider in globals()['_ohayo_dual_providers']:
        if OHAYO_SERVING_ARM == 'tuned_rag':
            identity = provider.serving_identity()
        else:
            model = provider._runtime[0]
            if getattr(model, 'peft_config', None) or any('lora_' in name for name, _ in model.named_parameters()):
                raise RuntimeError('Base rollback still contains adapters; restart Python')
            identity = dict(arm='base_rag', adapter_sha256=None, active_adapter=None,
                            model=provider.config.model_id, revision=provider.config.revision,
                            device=provider.config.device,
                            tokenizer_source='verified_adapter_training_tokenizer',
                            tokenizer_json_sha256=provider.training_tokenizer_sha256)
        replicas.append(identity)
    if len(replicas) != 2 or any(row['arm'] != OHAYO_SERVING_ARM for row in replicas):
        raise RuntimeError('Replica identity mismatch')
    return dict(arm=OHAYO_SERVING_ARM, replicas=replicas,
                package_sha256=SERVING_PACKAGE_SHA256,
                gateway_sha256=hashlib.sha256(OHAYO_GATEWAY_SOURCE.encode()).hexdigest())


_ohayo_dual_runtime = _ohayo_selected_runtime
OHAYO_DUAL_SIGNATURE += '-' + OHAYO_SERVING_ARM + '-' + EXPECTED_ADAPTER_SHA256 + '-' + SERVING_PACKAGE_SHA256
_ohayo_service = _ohayo_dual_start()
