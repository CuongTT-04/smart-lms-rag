"""Plot authenticated pilot logs on CPU, without loading model or checkpoint state."""
import argparse
import csv
from pathlib import Path
import sys

from .data import read_json, read_rows, require, sha_file
from .runtime import inventory, verify_inventory, write_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--verification', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    run, output = args.run.resolve(), args.output.resolve()
    receiver = read_json(args.verification)
    manifest_sha = sha_file(run / 'run-manifest.json')
    require(receiver['status'] == 'GPU_PILOT_RECEIVED_AND_VERIFIED'
            and receiver['run_manifest_sha256'] == manifest_sha, 'VERIFIED_PILOT_REQUIRED')
    manifest = read_json(run / 'run-manifest.json')
    verify_inventory(run, manifest['files'])
    require(set(inventory(run, ('run-manifest.json', 'SHA256SUMS.txt'))) == set(manifest['files']),
            'UNLISTED_RUN_FILES')
    require(not output.exists() and not output.is_relative_to(run), 'NEW_EXTERNAL_OUTPUT_REQUIRED')
    logs = read_rows(run / 'train-metrics.jsonl')
    training = sorted((r for r in logs if 'loss' in r), key=lambda r: r['step'])
    evaluation = sorted((r for r in logs if 'eval_loss' in r), key=lambda r: r['step'])
    require([r['step'] for r in training] == list(range(1, 51))
            and [r['step'] for r in evaluation] == [25, 50], 'PILOT_LOG_COVERAGE')
    vram = read_json(run / 'vram.json')
    updates = read_json(run / 'adapter-update-report.json')
    totals = next(r for r in logs if 'train_runtime' in r)
    first, last = evaluation[0]['eval_loss'], evaluation[1]['eval_loss']
    loss = [r['loss'] for r in training]
    analysis = dict(run=run.name, run_manifest_sha256=manifest_sha,
        config_sha256=manifest['config_sha256'], data_manifest_sha256=manifest['data_manifest_sha256'],
        train_records=128, validation_records=32, validation_loss_step25=first,
        validation_loss_step50=last, validation_loss_reduction_percent=(first - last) / first * 100,
        mean_train_loss_first10=sum(loss[:10]) / 10, mean_train_loss_last10=sum(loss[-10:]) / 10,
        trainer_reported_mean_train_loss=totals['train_loss'],
        trainer_runtime_seconds=totals['train_runtime'], epochs=totals['epoch'],
        applied_updates=updates['applied_updates'], scaler_skipped_updates=updates['scaler_skipped_updates'],
        adapter_delta_l2=updates['adapter_delta_l2'],
        peak_allocated_gib=vram['peak_allocated_bytes'] / 1024 ** 3,
        peak_reserved_gib=vram['peak_reserved_bytes'] / 1024 ** 3,
        validation_trend='DECREASED_BETWEEN_TWO_MEASURED_POINTS' if last < first else 'NOT_DECREASED',
        overfitting='NOT_RULED_OUT_WITH_ONLY_TWO_VALIDATION_POINTS',
        answer_quality='NOT_EVALUATED', independent_gpu_reload='NOT_RUN', gpu_resume='NOT_RUN',
        measurement_notes=[
            'Training loss is a rounded per-step log, not a full-train evaluation at checkpoint time.',
            'The moving average is trailing five steps, not additional validation measurements.',
            'Training runtime includes Trainer evaluation/checkpoint work, excludes initial base loading.',
            'VRAM values are run peaks, not a memory timeline; no inference timing is available.',
            'No step-0 base validation loss exists in this run; no base-versus-adapter quality claim.'])
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    output.mkdir(parents=True)
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'axes.titleweight': 'bold', 'savefig.facecolor': 'white'})
    steps = [r['step'] for r in training]
    rolling = [sum(loss[max(0, i - 4):i + 1]) / min(i + 1, 5) for i in range(len(loss))]
    fig, ax = plt.subplots(figsize=(11, 5.5), layout='constrained')
    ax.plot(steps, loss, color='#82a6bd', alpha=0.7, linewidth=1.2, label='Train loss (per step)')
    ax.plot(steps, rolling, color='#136d91', linewidth=2.3, label='Train loss (5-step moving mean)')
    ax.plot([25, 50], [first, last], color='#b33157', marker='o', linestyle='--', linewidth=1.7,
            label='Validation loss (32 records, 2 measurements)')
    for step, value in ((25, first), (50, last)):
        ax.annotate(f'{value:.4f}', (step, value), xytext=(-7, 14),
                    textcoords='offset points', ha='right', color='#9e2346', fontweight='bold')
    ax.set(xlabel='Optimizer step', ylabel='Completion-token cross-entropy loss',
           xlim=(1, 52), ylim=(0, max(loss) * 1.12), title='QLoRA pilot: training and validation loss')
    ax.grid(axis='y', alpha=0.18)
    ax.legend(loc='upper right', frameon=False, fontsize=9)
    fig.supxlabel('Two validation points only; lower loss does not establish better answers.', fontsize=10)
    fig.savefig(output / 'loss-curve.png', dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(13, 4.6), layout='constrained')
    axes[0].plot(steps, [r['grad_norm'] for r in training], color='#187d67')
    axes[0].set(title='Logged gradient norm', xlabel='Optimizer step', ylabel='Norm')
    axes[1].plot(steps, [r['learning_rate'] for r in training], color='#915c30')
    axes[1].set(title='Logged learning rate', xlabel='Optimizer step', ylabel='Learning rate')
    axes[1].ticklabel_format(axis='y', style='sci', scilimits=(0, 0))
    memory = [analysis['peak_allocated_gib'], analysis['peak_reserved_gib']]
    bars = axes[2].bar(['Allocated', 'Reserved'], memory, color=['#136d91', '#b33157'], width=0.55)
    axes[2].bar_label(bars, labels=[f'{v:.2f} GiB' for v in memory], padding=5)
    axes[2].set(title='GPU memory peaks', ylabel='GiB', ylim=(0, max(memory) * 1.2))
    for axis in axes:
        axis.grid(axis='y', alpha=0.15)
        axis.set_axisbelow(True)
    fig.suptitle('QLoRA pilot: observed training diagnostics', fontsize=15, fontweight='bold')
    fig.supxlabel('Training metrics only. Answer correctness, citations and inference latency are not measured here.', fontsize=10)
    fig.savefig(output / 'training-diagnostics.png', dpi=180)
    plt.close(fig)
    with (output / 'training-metrics.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['step', 'train_loss', 'validation_loss',
                                                   'gradient_norm', 'learning_rate', 'epoch'])
        writer.writeheader()
        evaluations = {r['step']: r['eval_loss'] for r in evaluation}
        for row in training:
            writer.writerow(dict(step=row['step'], train_loss=row['loss'],
                validation_loss=evaluations.get(row['step'], ''), gradient_norm=row['grad_norm'],
                learning_rate=row['learning_rate'], epoch=row['epoch']))
    analysis['plotting_versions'] = {'matplotlib': matplotlib.__version__}
    write_json(output / 'analysis.json', analysis)
    write_json(output / 'manifest.json', dict(run_manifest_sha256=manifest_sha,
        receiver_verification_sha256=sha_file(args.verification),
        generator_sha256=sha_file(__file__), files=inventory(output)))
    print(__import__('json').dumps(analysis, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
