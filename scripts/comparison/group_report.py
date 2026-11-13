"""Render the completed group assessment and its figures from recorded metrics."""
import argparse
import csv
from pathlib import Path

from scripts.comparison.protocol import file_hash, read_rows, write_json
from scripts.qlora.data import read_json, require
from scripts.qlora.runtime import inventory


def number(value, digits=2):
    return 'N/A' if value is None else f'{value:.{digits}f}'.replace('.', ',')


def render(output):
    output = Path(output)
    summary = read_json(output / 'summary.json')
    require(summary['status'] == 'GROUP_900_PRIMARY_90_SECONDARY_ADJUDICATED'
            and summary['primary_outputs'] == 900 and summary['primary_questions'] == 300
            and summary['secondary_outputs'] == 90, 'COMPLETE_GROUP_ASSESSMENT_REQUIRED')
    require(not (output / 'evaluation-report.md').exists(), 'REPORT_ALREADY_EXPORTED')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np

    arms = ('base', 'rag', 'tuned_rag')
    labels = ['Base LLM', 'RAG', 'Tuned + RAG']
    colors = ['#80908b', '#3b7866', '#bb8b6a']
    metrics = summary['primary_metrics']
    technical = summary['all_900_technical_metrics']
    figures = output / 'figures'
    figures.mkdir(exist_ok=False)
    data = []
    for name, title, values, ylabel, ymax in [
        ('correctness.png', '300 Questions per Method',
         [metrics[a]['correctness_percent'] for a in arms], 'Correctness score (%)', 100),
        ('latency.png', 'Main Generation Time: 300 Outputs per Method',
         [technical[a]['generation_mean_seconds'] for a in arms], 'Mean generation time (s)', None),
    ]:
        fig, ax = plt.subplots(figsize=(9, 4.8), layout='constrained')
        bars = ax.bar(labels, values, color=colors, width=.55)
        ax.bar_label(bars, fmt='%.2f', padding=4)
        ax.set(title=title, ylabel=ylabel, ylim=(0, ymax or max(values) * 1.25))
        ax.spines[['top', 'right']].set_visible(False)
        ax.grid(axis='y', alpha=.2)
        ax.set_axisbelow(True)
        fig.savefig(figures / name, dpi=180)
        plt.close(fig)
        data.extend(dict(figure=name, label=label, metric=ylabel, value=value) for label, value in zip(labels, values))

    fig, ax = plt.subplots(figsize=(9, 4.8), layout='constrained')
    x = np.arange(2)
    for i, (key, label) in enumerate([('faithfulness_item_micro', 'Source support'),
                                     ('citation_precision_item_micro', 'Citation precision'),
                                     ('citation_coverage_item_micro', 'Citation coverage')]):
        values = [metrics[a][key] * 100 for a in arms[1:]]
        bars = ax.bar(x + (i - 1) * .24, values, width=.22,
                      label=label, color=colors[i])
        ax.bar_label(bars, fmt='%.1f', padding=3, fontsize=9)
        data.extend(dict(figure='source-support.png', label=a, metric=key, value=v)
                    for a, v in zip(labels[1:], values))
    ax.set(xticks=x, xticklabels=labels[1:], ylabel='Supported items (%)', ylim=(0, 110),
           title='Structured-Item Source and Citation Support')
    ax.spines[['top', 'right']].set_visible(False)
    ax.legend(loc='lower right')
    ax.grid(axis='y', alpha=.2)
    ax.set_axisbelow(True)
    fig.savefig(figures / 'source-support.png', dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 4.8), layout='constrained')
    comparisons = summary['paired']
    names = [c['right'] + ' vs ' + c['left'] for c in comparisons]
    for i, comp in enumerate(comparisons):
        delta = comp['correctness_delta_percentage_points']
        low, high = comp['paired_case_bootstrap_95_ci']
        ax.errorbar(delta, i, xerr=[[delta - low], [high - delta]],
                    fmt='o', capsize=5, color=colors[i])
        data.extend(dict(figure='paired-ci.png', label=names[i], metric=k, value=v)
                    for k, v in [('delta_pp', delta), ('lower_95', low), ('upper_95', high)])
    ax.axvline(0, color='#777777', linestyle='--', linewidth=1)
    ax.set(yticks=range(3), yticklabels=names, xlabel='Correctness difference (percentage points)',
           title='Paired Question Bootstrap: 95% CI, 10,000 Resamples')
    ax.spines[['top', 'right']].set_visible(False)
    ax.grid(axis='x', alpha=.2)
    fig.savefig(figures / 'paired-ci.png', dpi=180)
    plt.close(fig)
    with (output / 'figure-data.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['figure', 'label', 'metric', 'value'])
        writer.writeheader()
        writer.writerows(data)

    rows = ['# Báo cáo nhóm W7 — Base LLM, RAG và tuned+RAG', '',
        '## Thiết kế và phạm vi', '',
        'Đánh giá 300 câu trên THMLN, KTCTMLN, CNXHKH, mỗi môn 100 câu. '
        'Toàn bộ gồm 120 factual, 90 explanation, 30 multi-page và 60 insufficient. '
        'Cùng Qwen2.5-7B-Instruct revision a09a35458c702b33eeacc393d103063234e8bc28, NF4 double quant FP16. '
        'Adapter mới được huấn luyện một epoch, 193 updates trên 770 train và 114 validation; 116 holdout tách riêng. '
        'Adapter được chọn bằng dev trước khi khóa main. Hai nhánh RAG dùng cùng cache, messages và token IDs; '
        'Base không nhận học liệu. Greedy, seed 42, tối đa 512 token, một lượt sinh/câu/nhánh, một GPU T4.', '',
        'Có 900 output thực, 897 completed và 3 output_limit. Giữ cả ba lỗi trong mẫu số và chấm 0 correctness chính. '
        'Đã có 900 primary, 90 secondary và phân xử mọi bất đồng được phát hiện. '
        'Điểm nội dung được tạo bằng agent theo rubric có đối chiếu nguồn; exact judge revision và decoding không được nền tảng cung cấp.', '',
        '## Kết quả trên toàn bộ 300 câu mỗi phương pháp', '',
        '| Chỉ số | Base LLM | RAG | Tuned + RAG |', '|---|---:|---:|---:|']
    table = [
        ('Tổng điểm rubric / 600', [str(metrics[a]['correctness_total']) + '/600' for a in arms]),
        ('Điểm đúng/đủ quy đổi (%)', [number(metrics[a]['correctness_percent']) for a in arms]),
        ('Câu đạt 2/2', [str(metrics[a]['full_credit']) + '/300' for a in arms]),
        ('Từ chối đúng trên 60 câu thiếu căn cứ', [str(metrics[a]['correct_abstentions']) + '/60' for a in arms]),
        ('Từ chối rỗng nhầm trên 240 câu có đáp án', [str(metrics[a]['false_protocol_abstentions']) + '/240' for a in arms]),
        ('Bám nguồn theo item (%)', [number(None if metrics[a]['faithfulness_item_micro'] is None
                                                   else 100 * metrics[a]['faithfulness_item_micro']) for a in arms]),
        ('Citation precision theo item (%)', [number(None if metrics[a]['citation_precision_item_micro'] is None
                                                            else 100 * metrics[a]['citation_precision_item_micro']) for a in arms]),
        ('Citation coverage theo item (%)', [number(None if metrics[a]['citation_coverage_item_micro'] is None
                                                           else 100 * metrics[a]['citation_coverage_item_micro']) for a in arms]),
        ('Generation trung bình (giây)', [number(technical[a]['generation_mean_seconds']) for a in arms]),
        ('Generation p95 (giây)', [number(technical[a]['generation_p95_seconds']) for a in arms]),
        ('Output token', [str(technical[a]['output_tokens']) for a in arms]),
    ]
    rows.extend('| ' + name + ' | ' + ' | '.join(values) + ' |' for name, values in table)
    rows += ['', 'Điểm phần trăm là tổng điểm rubric chia điểm tối đa. Tỷ lệ đạt 2/2 được ghi riêng. '
        'Faithfulness/citation dùng item có mệnh đề kiểm chứng được; một item nhiều ý phải được hỗ trợ đầy đủ. '
        'Output rỗng, không parse được và item không có assertion được đếm riêng, không tự nhận 100% hỗ trợ. '
        'Base có các chỉ số nguồn/citation N/A. Xem metrics.csv để đối chiếu tử số, mẫu số và từng môn/loại.', '',
        '## So sánh theo cặp', '',
        '| So sánh | Chênh lệch điểm % | CI 95% | Thắng / thua / hòa |', '|---|---:|---|---|']
    for comp in comparisons:
        low, high = comp['paired_case_bootstrap_95_ci']
        rows.append('| ' + comp['right'] + ' so với ' + comp['left'] + ' | '
                    + number(comp['correctness_delta_percentage_points']) + ' | [' + number(low) + '; '
                    + number(high) + '] | ' + f"{comp['wins']} / {comp['losses']} / {comp['ties']}" + ' |')
    tune = next(c for c in comparisons if c['left'] == 'rag' and c['right'] == 'tuned_rag')
    low, high = tune['paired_case_bootstrap_95_ci']
    statement = ('CI còn chứa 0, nên chưa đủ cơ sở khẳng định tuning làm tăng correctness chắc chắn.'
                 if low <= 0 <= high else 'Khoảng tin cậy chênh lệch không chứa 0 trong phép resample câu hỏi này.')
    agreed = summary['agreement']
    retrieval = summary['retrieval']
    total = sum(technical[a]['generation_seconds_sum'] for a in arms)
    rows += ['', 'RAG tăng điểm đúng/đủ so với Base trong phạm vi benchmark này. '
        'Tuned+RAG chênh ' + number(tune['correctness_delta_percentage_points']) + ' điểm phần trăm so với RAG. '
        + statement + ' Các chỉ số nguồn/citation cần đọc cùng correctness và khả năng hiển thị; kết quả không cho thấy tuned thắng toàn diện.', '',
        'Bootstrap 10.000 lần, seed 42, resample theo câu hỏi để giữ ba nhánh cùng nhau. '
        'CI phản ánh biến thiên chọn câu, chưa bao gồm sai số judge hoặc độ biến thiên giữa các lần train.', '',
        '## Kiểm độc lập, đồng thuận và giới hạn', '',
        'Đã tái kiểm đủ 900 ID/arm, config/input/context hash, lịch chạy và log trạng thái LoRA; '
        'kiểm bytes/config/392 tensor của adapter, tái tính token IDs của 990 đầu vào dev/main. '
        'Đã đối chiếu 1.500 context bindings và 352 gold-page bindings trên 354 trang vật lý thuộc 27 PDF. '
        'Nguồn main không nằm trong train/validation thực 770/114. Báo cáo leakage 385/57/58 trong gói gốc là bản lịch sử; '
        'kết quả kiểm độc lập 770/114/116 được lưu riêng, giữ nguyên artifact gốc.', '',
        'A và B cùng điểm correctness ở ' + number(agreed['exact_correctness_agreement'] * 100)
        + '% của 90 lượt đối chiếu; Cohen kappa ' + number(agreed['cohen_kappa'], 4)
        + '. Đã phân xử ' + str(summary['adjudicated_outputs'])
        + ' output có bất đồng về điểm hoặc support/citation. Các review gốc A/B và quyết định mới được giữ riêng. '
        'Đây là đồng thuận giữa các lượt đánh giá tự động, có thể có sai số hoặc thiên lệch chung của model.', '',
        'Retrieval dùng chung trên 240 câu answerable: page Recall@5 '
        + number(retrieval['page_recall_at_5'] * 100) + '%, MRR@5 '
        + number(retrieval['page_mrr_at_5'], 4) + ', nDCG@5 ' + number(retrieval['page_ndcg_at_5'], 4)
        + '; truy đủ trang của câu multi-page đạt ' + number(retrieval['multi_page_all_gold_recall'] * 100)
        + '%. Adapter không làm đổi cache retrieval đã khóa.', '',
        'Tổng generation ' + number(total) + ' giây. Số đo này tách khỏi setup/load/warmup và retrieval offline, '
        'chưa phải độ trễ API end-to-end. Tuned sinh ít token hơn RAG; thời gian thấp hơn không tự chứng minh tốc độ mỗi token cao hơn.', '',
        'Benchmark chỉ phủ ba chương và có giao kiến thức đã công bố. Chấm nguồn theo item bảo thủ; '
        'exact judge revision không xác minh được. Các khác biệt theo môn/loại và lỗi nằm trong metrics.csv/errors.csv. '
        'Kết quả là bằng chứng so sánh trên bộ test đã khóa, phạm vi suy rộng cần giữ đúng giới hạn này.', '',
        '## Đầu ra gửi Dương', '',
        'Gửi review B đã khóa, 90 lượt đối chiếu, 14 quyết định phân xử, summary/metrics/paired/errors, '
        'bốn biểu đồ và log kiểm/test cùng manifest/checksum. Dương hoàn thiện Evidence/W07 sau cùng '
        'từ các artifact cuối này. Raw, benchmark, adapter và review A gốc được giữ nguyên.']
    (output / 'evaluation-report.md').write_text('\n'.join(rows) + '\n', encoding='utf-8')
    manifest = read_json(output / 'manifest.json')
    manifest['reporter_sha256'] = file_hash(__file__)
    manifest['files'] = inventory(output, ('manifest.json',))
    write_json(output / 'manifest.json', manifest)
    print('GROUP_REPORT_AND_FOUR_FIGURES_EXPORTED', output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    render(parser.parse_args().output)
