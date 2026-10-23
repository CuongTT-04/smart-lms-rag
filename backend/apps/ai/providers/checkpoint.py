"""Validate checkpoints exported by the Kaggle setup notebook."""

import hashlib
import json
from pathlib import Path

from .base import GenerationError, ModelConfig


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_checkpoint(config: ModelConfig):
    try:
        root = Path(config.checkpoint_path)
        if not root.is_dir() or root.is_symlink():
            raise ValueError("Missing or unsafe checkpoint directory.")
        manifest_path = root / "checkpoint-manifest.json"
        if not manifest_path.is_file() or manifest_path.is_symlink():
            raise ValueError("Missing or unsafe manifest.")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (manifest.get("schema_version") != 1
                or manifest.get("model_id") != config.model_id
                or manifest.get("source_revision") != config.revision):
            raise ValueError("Checkpoint identity does not match configuration.")
        files = manifest.get("files")
        if not isinstance(files, dict) or not files:
            raise ValueError("Missing file inventory.")
        actual = set()
        for path in root.rglob("*"):
            if path.is_symlink():
                raise ValueError("Symlinks are not accepted.")
            if path.is_file() and path != manifest_path:
                actual.add(path.relative_to(root).as_posix())
        if actual != set(files):
            raise ValueError("Checkpoint file inventory differs.")
        if not {"config.json", "tokenizer_config.json", "tokenizer.json"} <= actual:
            raise ValueError("Missing configuration or tokenizer.")
        if not any(name.endswith(".safetensors") for name in actual):
            raise ValueError("Missing safetensors weights.")
        for name, record in files.items():
            relative = Path(name)
            if relative.is_absolute() or ".." in relative.parts or "\\" in name:
                raise ValueError("Unsafe checkpoint path.")
            path = root / relative
            if (path.stat().st_size != record["size_bytes"]
                    or file_sha256(path) != record["sha256"]):
                raise ValueError("Checkpoint checksum differs.")
        quant = json.loads((root / "config.json").read_text(encoding="utf-8"))["quantization_config"]
        if (quant.get("quant_method") != "bitsandbytes"
                or quant.get("load_in_4bit", quant.get("_load_in_4bit")) is not True
                or quant.get("bnb_4bit_quant_type") != "nf4"
                or quant.get("bnb_4bit_use_double_quant") is not True
                or quant.get("bnb_4bit_compute_dtype") != "float16"):
            raise ValueError("Expected NF4, double quantization and FP16 compute.")
        return manifest
    except Exception as exc:
        raise GenerationError("CHECKPOINT_INVALID", "Cannot validate the local NF4 checkpoint.") from exc
