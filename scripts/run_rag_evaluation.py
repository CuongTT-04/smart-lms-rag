"""Evaluate pinned offline retrieval -> application generation; human grades are separate."""

import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from apps.ai.evaluation.generation import file_hash, load_qa_files, run_evaluation, summarize_reviews
from apps.ai.evaluation.snapshot import OfflineSnapshotRetriever, label_cases, read_snapshot


def source_provenance():
    commit, dirty = None, None
    if (ROOT / ".git").exists():
        try:
            commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=True).stdout.strip()
            dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, check=True).stdout)
        except (OSError, subprocess.SubprocessError):
            pass
    files = [path for folder in ("providers", "rag", "prompts", "evaluation", "embeddings", "retrieval")
             for path in (ROOT / "backend/apps/ai" / folder).glob("*.py")]
    files.append(Path(__file__).resolve())
    return {"git_commit": commit, "working_tree_dirty": dirty,
            "source_sha256": {p.relative_to(ROOT).as_posix(): file_hash(p) for p in files}}


def prepare_inputs(qa_paths, source_map_path, index_dir, *, case_ids=None, expected_total=None):
    cases, inputs = load_qa_files(qa_paths)
    if expected_total is not None and len(cases) != expected_total:
        raise ValueError(f"Expected {expected_total} QA, found {len(cases)}. Do not label a partial dataset as full.")
    source_map = json.loads(Path(source_map_path).read_text(encoding="utf-8"))
    snapshot, chunks = read_snapshot(index_dir, source_map)
    cases = label_cases(cases, source_map)
    available = len(cases)
    selected = cases
    if case_ids:
        if len(set(case_ids)) != len(case_ids):
            raise ValueError("Duplicate sample QA selector.")
        keyed = {case["qa_id"]: case for case in cases}
        selected = [keyed[qid] for qid in case_ids]
    return selected, source_map, {
        "dataset_inputs": inputs, "source_map_sha256": file_hash(source_map_path),
        "dataset_available_count": available, "selected_count": len(selected),
        "merged_dataset_sha256": hashlib.sha256(json.dumps(cases, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
        "index_file_sha256": snapshot["index_sha256"], "chunk_count": len(chunks),
        "metadata_checks_passed": True, "faiss_deserialization_verified": False,
        "label_error_count": sum(bool(c.get("label_error")) for c in selected),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qa", type=Path, action="append", help="Repeat for baseline, A additions and later B additions.")
    parser.add_argument("--source-map", type=Path, default=ROOT / "data/qa/source_map.json")
    parser.add_argument("--index-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--case-id", action="append")
    parser.add_argument("--expected-total", type=int)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--allow-embedding-download", action="store_true")
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--generation-config", type=Path, help="LocalModelProvider ModelConfig JSON, not a public client option.")
    parser.add_argument("--prompt-version", default="bounded_guidance",
                        choices=("grounded_text", "grounded_text_guarded", "bounded_guidance",
                                 "concise_grounded_qa", "direct_grounded_qa", "routed_grounded_qa", "frozen_baseline", "efficient_grounded"),
                        help="Explicit prompt revision; use frozen_baseline to reproduce the pre-QLoRA notebook.")
    parser.add_argument("--guardrail-results", type=Path)
    parser.add_argument("--summarize-scores", type=Path, metavar="RUN_DIR")
    parser.add_argument("--score-rules", type=Path, metavar="RUN_ZIP_OR_DIR",
                        help="Screen saved predictions offline; no retrieval/model calls or human score changes.")
    args = parser.parse_args(argv)
    if args.score_rules:
        if args.summarize_scores or not args.output_dir:
            parser.error("--score-rules requires --output-dir and cannot be combined with --summarize-scores.")
        from apps.ai.evaluation.factuality import score_saved_run
        print(json.dumps(score_saved_run(args.score_rules, args.output_dir), ensure_ascii=False, indent=2))
        return
    if args.summarize_scores:
        print(json.dumps(summarize_reviews(args.summarize_scores), ensure_ascii=False, indent=2))
        return
    if not args.index_dir:
        parser.error("--index-dir is required; this command never builds an index.")
    qa = args.qa or [ROOT / "data/qa/qa_baseline.json", ROOT / "data/qa/qa_additions.json"]
    if args.output_dir:
        target = args.output_dir.resolve()
        protected = [p.resolve() for p in [*qa, args.source_map, args.index_dir, ROOT / "data/corpus"]]
        if any(target == p or target.is_relative_to(p) or p.is_relative_to(target) for p in protected):
            raise ValueError("Output must not overlap input datasets, corpus or index.")
    cases, source_map, preflight = prepare_inputs(qa, args.source_map, args.index_dir,
                                                 case_ids=args.case_id, expected_total=args.expected_total)
    if args.validate_only:
        print(json.dumps(preflight, ensure_ascii=False, indent=2))
        return
    if not args.output_dir:
        parser.error("--output-dir is required for generation.")
    from apps.ai.providers import LocalModelProvider, ModelConfig
    from apps.ai.rag import GenerationConfig, RAGPipeline

    model_config = ModelConfig.from_file(args.generation_config) if args.generation_config else ModelConfig(
        checkpoint_path=str(args.checkpoint.resolve()) if args.checkpoint else None,
        cache_dir=os.environ.get("HF_HOME"))
    retriever = OfflineSnapshotRetriever(args.index_dir, source_map, allow_embedding_download=args.allow_embedding_download)
    pipeline = RAGPipeline(LocalModelProvider(model_config), GenerationConfig(model=model_config, prompt_version=args.prompt_version))
    metrics = run_evaluation(cases, pipeline, retriever, args.output_dir, run_kind="live_model",
                             provenance={**preflight, **retriever.provenance, **source_provenance()},
                             total_available=preflight["dataset_available_count"], guardrail_results=args.guardrail_results)
    with (args.output_dir / "pip-freeze.txt").open("w", encoding="utf-8") as stream:
        subprocess.run([sys.executable, "-m", "pip", "freeze"], stdout=stream, check=True)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
