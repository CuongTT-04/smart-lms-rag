"""Score saved top-k results; accepts normalized JSON QA or pilot CSV plus source map."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from apps.ai.evaluation.metrics import evaluate, export_report, load_pilot_csv


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qa", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--source-map", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output_dir.resolve()
    if not output.is_relative_to((ROOT / "data/processed").resolve()) or output == (ROOT / "data/processed").resolve():
        parser.error("Output must be in a subdirectory of data/processed.")
    if any(path.resolve().is_relative_to(output) for path in (args.qa, args.predictions, args.source_map) if path):
        parser.error("Keep input files outside the output directory.")
    try:
        predictions = json.loads(args.predictions.read_text(encoding="utf-8"))
        if args.qa.suffix.lower() == ".csv":
            if args.source_map is None:
                parser.error("Pilot CSV requires --source-map; filenames are not document/version IDs.")
            cases = load_pilot_csv(args.qa, json.loads(args.source_map.read_text(encoding="utf-8")))
        else:
            cases = json.loads(args.qa.read_text(encoding="utf-8"))["cases"]
        provenance = dict(predictions.get("provenance", {}))
        for name, path in (("dataset_sha256", args.qa), ("predictions_sha256", args.predictions), ("source_map_sha256", args.source_map)):
            if path:
                provenance[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        rows, metrics = evaluate(cases, predictions["predictions"], requested_top_k=predictions["requested_top_k"], provenance=provenance)
        report = export_report(output, rows, metrics)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
