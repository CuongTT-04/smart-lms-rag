"""Render raw training measurements; interpretation never appears inside figures."""
import argparse
import csv
import math
from pathlib import Path

from scripts.qlora.data import read_json, read_rows, require
from scripts.qlora.runtime import inventory, verify_inventory, write_json

FIGURES = ('loss-curve.png','optimizer.png','memory.png','runtime.png')


def series(run):
    logs = read_rows(run/'train-metrics.jsonl')
    train = sorted([r for r in logs if 'loss' in r], key=lambda r:r['step'])
    evaluation = sorted([r for r in logs if 'eval_loss' in r], key=lambda r:r['step'])
    resources = read_rows(run/'resource-metrics.jsonl')
    require(bool(train) and bool(evaluation) and len(resources) == len(train), 'CHART_LOG_COVERAGE')
    require([r['step'] for r in train] == [r['step'] for r in resources] == list(range(1,len(train)+1)), 'CHART_STEPS')
    for row in train+evaluation+resources:
        require(all(math.isfinite(v) for v in row.values() if isinstance(v,(int,float))), 'CHART_NONFINITE')
    return train, evaluation, resources


def render(run, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    run, output = Path(run), Path(output)
    require(not output.exists(), 'CHART_OUTPUT_EXISTS')
    train, evaluation, resources = series(run)
    output.mkdir(parents=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,
                         'axes.spines.right':False,'savefig.facecolor':'white'})
    steps = [r['step'] for r in train]
    def save(fig, name):
        for ax in fig.axes:
            ax.grid(axis='y',alpha=0.18)
        fig.savefig(output/name, dpi=160)
        plt.close(fig)
    fig, ax = plt.subplots(figsize=(10,5),layout='constrained')
    ax.plot(steps,[r['loss'] for r in train],color='#16799b',label='Train loss per update')
    ax.plot([r['step'] for r in evaluation],[r['eval_loss'] for r in evaluation],
            color='#b73957',marker='o',label='Validation loss')
    ax.set(title='QLoRA training and validation loss',xlabel='Optimizer step',ylabel='Completion loss')
    ax.legend(frameon=False)
    save(fig,FIGURES[0])
    fig, axes = plt.subplots(1,2,figsize=(11,4.5),layout='constrained')
    for ax, key, title, color in zip(axes,('learning_rate','grad_norm'),('Learning rate','Gradient norm'),('#16799b','#278366')):
        ax.plot(steps,[r[key] for r in train],color=color)
        ax.set(title=title,xlabel='Optimizer step',ylabel=title)
    axes[0].ticklabel_format(axis='y',style='sci',scilimits=(0,0))
    save(fig,FIGURES[1])
    fig, axes = plt.subplots(1,2,figsize=(11,4.5),layout='constrained')
    for ax, keys, title in zip(axes,(('allocated_bytes','reserved_bytes'),('peak_allocated_bytes','peak_reserved_bytes')),
                               ('GPU memory at update end','Cumulative GPU memory peaks')):
        for key,color in zip(keys,('#16799b','#b73957')):
            ax.plot(steps,[r[key]/2**30 for r in resources],color=color,label=key.replace('_bytes','').replace('_',' ').title())
        ax.set(title=title,xlabel='Optimizer step',ylabel='GiB')
        ax.legend(frameon=False)
    save(fig,FIGURES[2])
    fig, axes = plt.subplots(1,2,figsize=(11,4.5),layout='constrained')
    axes[0].plot(steps,[r['elapsed_seconds']/60 for r in resources],color='#16799b')
    axes[0].set(title='Elapsed training time',xlabel='Optimizer step',ylabel='Minutes')
    axes[1].plot(steps,[r['cumulative_updates_per_second'] for r in resources],color='#278366')
    axes[1].set(title='Cumulative optimizer throughput',xlabel='Optimizer step',ylabel='Updates / second')
    save(fig,FIGURES[3])
    values = {r['step']:dict(validation_loss=r['eval_loss']) for r in evaluation}
    for row, resource in zip(train, resources):
        values.setdefault(row['step'],{}).update(train_loss=row['loss'],gradient_norm=row['grad_norm'],
            learning_rate=row['learning_rate'],epoch=row['epoch'],
            **{k:v for k,v in resource.items() if k not in ('step','epoch')})
    fields = ['step','epoch','train_loss','validation_loss','gradient_norm','learning_rate',
        'elapsed_seconds','cumulative_updates_per_second','allocated_bytes','reserved_bytes','peak_allocated_bytes','peak_reserved_bytes']
    with (output/'metrics.csv').open('x',encoding='utf-8',newline='') as stream:
        writer = csv.DictWriter(stream,fieldnames=fields)
        writer.writeheader()
        for step,row in sorted(values.items()):
            writer.writerow(dict(step=step,**row))
    best = min(evaluation,key=lambda r:r['eval_loss'])
    summary = dict(status='CHARTS_FROM_MEASURED_LOGS',figure_files=list(FIGURES),
        validation_initial=evaluation[0]['eval_loss'],validation_final=evaluation[-1]['eval_loss'],
        validation_best=best['eval_loss'],validation_best_step=best['step'],
        final_above_observed_best=evaluation[-1]['eval_loss']>best['eval_loss'],
        plotting_version=matplotlib.__version__,
        notes=['Training loss is a batch/update log, not evaluation of the full train split.',
               'Validation uses the fixed validation split; holdout is never evaluated here.',
               'Resource observations are update-end snapshots and cumulative peaks, not continuous sampling.',
               'Elapsed/throughput include prior periodic validation and checkpoint work after training starts, exclude step-zero validation/base loading.',
               'Lower loss does not establish answer quality; compare old/new adapters on dev.',
               'Interpretation is separate from PNG figures. No training rerun is needed to render these logs.'])
    write_json(output/'summary.json',summary)
    return summary


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    manifest=read_json(args.run/'run-manifest.json')
    verify_inventory(args.run,manifest['files'])
    require(inventory(args.run,('run-manifest.json',))==manifest['files'],'RUN_FILE_SET')
    require(not args.output.resolve().is_relative_to(args.run.resolve()),'RENDER_OUTSIDE_SEALED_RUN')
    render(args.run,args.output)
