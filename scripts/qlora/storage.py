"""Budget pinned safetensors downloads and run artifacts before loading any weights."""
from pathlib import Path
import re
import shutil

from .data import read_json, require

GIB = 1024 ** 3


def budget(missing_bytes, cache_free, output_free, same_volume):
    require(type(missing_bytes) is int and missing_bytes >= 0, 'INVALID_WEIGHT_SIZE')
    cache_required = missing_bytes + (GIB if missing_bytes else 0)
    output_required = 2 * GIB
    if same_volume:
        passed = min(cache_free, output_free) >= cache_required + output_required
    else:
        passed = cache_free >= cache_required and output_free >= output_required
    return dict(passed=passed, missing_weight_bytes=missing_bytes,
                cache_required_bytes=cache_required, output_required_bytes=output_required,
                cache_free_bytes=cache_free, output_free_bytes=output_free,
                shared_volume=same_volume,
                note='Reserve 1 GiB for download overhead when needed and 2 GiB for run/checkpoint/ZIP; no base copy in the ZIP.')


def check_training_storage(config, cache_dir, output, *, allow_download=False):
    from huggingface_hub import HfApi, hf_hub_download, try_to_load_from_cache
    cache = Path(cache_dir).expanduser().resolve()
    output = Path(output).resolve()
    cache.mkdir(parents=True, exist_ok=True)
    identity = dict(repo_id=config['model_id'], revision=config['revision'], cache_dir=str(cache))
    if allow_download:
        # Metadata only: no safetensors are downloaded until the budget passes.
        info = HfApi().model_info(config['model_id'], revision=config['revision'],
                                  files_metadata=True, timeout=30)
        require(info.sha == config['revision'], 'WEIGHT_METADATA_REVISION')
        weights = {item.rfilename: item.size for item in info.siblings
                   if re.fullmatch(r'model(?:-\d+-of-\d+)?\.safetensors', item.rfilename)}
        require(0 < len(weights) <= 16 and all(type(n) is int and n > 0 for n in weights.values()),
                'SAFETENSORS_SIZE_METADATA_REQUIRED')
    else:
        index = hf_hub_download(filename='model.safetensors.index.json',
                                local_files_only=True, **identity)
        names = set(read_json(index)['weight_map'].values())
        weights = {}
        for name in names:
            require(re.fullmatch(r'model-\d+-of-\d+\.safetensors', name) is not None,
                    'WEIGHT_INDEX_FILENAME')
            cached = try_to_load_from_cache(filename=name, **identity)
            require(isinstance(cached, str) and Path(cached).is_file(), 'BASE_NOT_FULLY_CACHED')
            weights[name] = Path(cached).stat().st_size
    cached_bytes = 0
    for name, size in weights.items():
        cached = try_to_load_from_cache(filename=name, **identity)
        if isinstance(cached, str) and Path(cached).is_file() and Path(cached).stat().st_size == size:
            cached_bytes += size
    total = sum(weights.values())
    result = budget(total - cached_bytes, shutil.disk_usage(cache).free,
                    shutil.disk_usage(output).free, cache.stat().st_dev == output.stat().st_dev)
    return dict(result, cache_dir=str(cache), model_id=config['model_id'], revision=config['revision'],
                total_weight_bytes=total, cached_weight_bytes=cached_bytes, weight_files=weights,
                weights_downloaded_by_check=False, offline=not allow_download)
