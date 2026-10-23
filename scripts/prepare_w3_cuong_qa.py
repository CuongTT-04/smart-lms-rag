"""Reproducible Cường QA draft; source-checked by agent, peer approval stays pending."""
import csv
import hashlib
import json
from pathlib import Path
import unicodedata
from uuid import NAMESPACE_URL,uuid5
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
NEW=[
('KTCTMLN','ch01.pdf',25,'hint','Gợi ý cách phân biệt yếu tố có thể gạt bỏ và yếu tố không được gạt bỏ khi trừu tượng hóa quan hệ lợi ích kinh tế.', 'Bắt đầu bằng mục tiêu nghiên cứu; phân biệt tình cảm cá nhân với lợi ích kinh tế. Có thể gạt yếu tố tình cảm, nhưng không loại lợi ích kinh tế vì làm sai bản chất quan hệ.'),
('KTCTMLN','ch01.pdf',26,'qa','Chức năng nhận thức của kinh tế chính trị Mác - Lênin giúp nhìn các hiện tượng kinh tế ở mức độ nào?', 'Cung cấp tri thức về quy luật sản xuất và trao đổi, khái quát phạm trù từ hiện tượng bề mặt để nhận thức bản chất và quy luật ở tầng sâu hơn.'),
('KTCTMLN','ch01.pdf',27,'qa','Chức năng thực tiễn của kinh tế chính trị có liên hệ thế nào với điều chỉnh hành vi và giải quyết quan hệ lợi ích?', 'Làm cơ sở khoa học cho điều chỉnh hành vi, chính sách và giải quyết hài hòa quan hệ lợi ích; thúc đẩy sáng tạo và cải thiện đời sống.'),
('KTCTMLN','ch02.pdf',5,'qa','Cơ sở chung để các hàng hóa có giá trị sử dụng khác nhau trao đổi theo tỷ lệ nhất định là gì?', 'Lao động xã hội đã hao phí để sản xuất hàng hóa là thực thể chung. Giá trị là lao động xã hội của người sản xuất kết tinh trong hàng hóa.'),
('KTCTMLN','ch02.pdf',6,'qa','Hàng hóa công cộng được phân biệt với hàng hóa cá nhân như thế nào trong hộp kiến thức của giáo trình?', 'Hàng hóa cá nhân đã được một người tiêu dùng thì người khác không thể đồng thời dùng nữa; hàng hóa công cộng một người dùng vẫn không cản người khác dùng, như không khí sạch hay quốc phòng.'),
('KTCTMLN','ch02.pdf',8,'hint','Gợi ý cách giải thích vì sao mâu thuẫn giữa lao động cụ thể và lao động trừu tượng có thể dẫn đến hàng hóa không bán được.', 'Đối chiếu sản phẩm với nhu cầu xã hội và hao phí cá biệt với mức xã hội chấp nhận. Khi không phù hợp, hao phí cá biệt không được xã hội thừa nhận, tạo nguy cơ khủng hoảng.'),
('KTCTMLN','ch02.pdf',10,'qa','Giáo trình liệt kê những nhóm nhân tố nào ảnh hưởng đến năng suất lao động?', 'Trình độ khéo léo của người lao động; khoa học và ứng dụng công nghệ; sự kết hợp xã hội của sản xuất; quy mô, hiệu suất tư liệu sản xuất; điều kiện tự nhiên.'),
('KTCTMLN','ch02.pdf',10,'hint','Gợi ý cách mở đầu khi cần phân biệt cường độ lao động với năng suất lao động.', 'Xác định cường độ là mức khẩn trương, tích cực lao động; tách nó khỏi năng lực tạo sản phẩm trong một đơn vị thời gian. Dùng các định nghĩa và quan hệ giá trị trong giáo trình, không chỉ nhìn số sản phẩm tăng.'),
('KTCTMLN','ch02.pdf',12,'qa','Trao đổi ở hình thái giá trị giản đơn hay ngẫu nhiên có đặc điểm gì?', 'Là hình thái ban đầu ở thời kỳ sơ khai; các hàng hóa được trao đổi trực tiếp với nhau và việc trao đổi mang tính ngẫu nhiên.'),
('KTCTMLN','ch02.pdf',13,'qa','Vì sao khi thị trường mở rộng cần một vật ngang giá chung thống nhất?', 'Nhiều vật ngang giá khác nhau giữa các địa phương gây trở ngại trao đổi; sản xuất, phân công lao động và thị trường phát triển đòi hỏi vật ngang giá chung thống nhất, dẫn đến hình thái tiền.'),
('KTCTMLN','ch02.pdf',16,'qa','Khi dùng tiền để trả nợ hay trả tiền mua chịu, tiền đang thực hiện chức năng nào?', 'Phương tiện thanh toán, gắn với tín dụng thương mại và việc mua bán qua chế độ tín dụng.'),
('KTCTMLN','ch02.pdf',17,'qa','Dịch vụ khác hàng hóa thông thường ở khả năng cất trữ và thời điểm sản xuất, tiêu dùng như thế nào?', 'Dịch vụ là hàng hóa vô hình, không thể cất trữ; sản xuất và tiêu dùng diễn ra đồng thời.'),
('KTCTMLN','ch03.pdf',4,'hint','Gợi ý dàn ý để trình bày các bộ phận tạo nên giá trị hàng hóa sức lao động.', 'Tổ chức dàn ý theo ba nhóm: tư liệu sinh hoạt tái sản xuất sức lao động, phí đào tạo người lao động và tư liệu sinh hoạt nuôi con; nêu đây là cách đo gián tiếp qua tư liệu sinh hoạt.'),
('KTCTMLN','ch03.pdf',10,'qa','Theo giáo trình, tiền công là giá cả của hàng hóa nào và có nguồn gốc từ đâu?', 'Là giá cả của hàng hóa sức lao động, một bộ phận giá trị mới do lao động của người lao động làm thuê tạo ra.'),
('KTCTMLN','ch03.pdf',13,'qa','Tốc độ chu chuyển tư bản được xác định từ thời gian một năm và thời gian một vòng như thế nào?', 'Số vòng chu chuyển n bằng thời gian một năm CH chia thời gian một vòng ch: n=CH/ch.'),
('KTCTMLN','ch03.pdf',13,'qa','Giá trị tư bản cố định và tư bản lưu động được chuyển vào sản phẩm khác nhau như thế nào?', 'Tư bản cố định chuyển dần từng phần theo hao mòn; tư bản lưu động chuyển một lần, toàn phần khi kết thúc quá trình sản xuất.'),
('KTCTMLN','ch03.pdf',18,'qa','Giá trị thặng dư siêu ngạch hình thành khi doanh nghiệp có quan hệ nào giữa giá trị cá biệt và giá trị xã hội?', 'Khi cải tiến kỹ thuật, tăng năng suất làm giá trị cá biệt thấp hơn giá trị xã hội, doanh nghiệp thu phần giá trị thặng dư trội hơn các doanh nghiệp khác.'),
('KTCTMLN','ch03.pdf',21,'hint','Gợi ý cách lý giải tác động của năng suất lao động xã hội tới quy mô tích lũy tư bản.', 'Trình bày chuỗi quan hệ: năng suất tăng, giá trị tư liệu sinh hoạt giảm, giá trị sức lao động giảm, tăng khả năng thu giá trị thặng dư và quy mô tích lũy.'),
('CNXHKH','ch01.pdf',21,'qa','Phương pháp luận chung nhất được sử dụng khi nghiên cứu chủ nghĩa xã hội khoa học là gì?', 'Chủ nghĩa duy vật biện chứng và chủ nghĩa duy vật lịch sử của triết học Mác - Lênin.'),
('CNXHKH','ch01.pdf',18,'qa','Ba trụ cột được nêu cho phát triển nhanh và bền vững ở Việt Nam gồm những nội dung nào?', 'Phát triển kinh tế là nhiệm vụ trung tâm; xây dựng Đảng là khâu then chốt; phát triển văn hóa là nền tảng tinh thần của xã hội.'),
('CNXHKH','ch02.pdf',8,'qa','Địa vị kinh tế của giai cấp công nhân gắn với nền đại công nghiệp như thế nào?', 'Là sản phẩm của nền đại công nghiệp, chủ thể sản xuất vật chất hiện đại, đại diện phương thức sản xuất tiên tiến và lực lượng sản xuất hiện đại.'),
('CNXHKH','ch02.pdf',6,'hint','Gợi ý cách xác định hai mặt của mâu thuẫn kinh tế cơ bản trong chủ nghĩa tư bản khi bàn về sứ mệnh giai cấp công nhân.', 'Bắt đầu từ tính xã hội hóa của sản xuất; đối chiếu lực lượng sản xuất mang tính xã hội với sự chiếm hữu tư nhân tư bản về tư liệu sản xuất; liên hệ mâu thuẫn lợi ích giai cấp.'),
('CNXHKH','ch02.pdf',7,'qa','Sứ mệnh lịch sử của giai cấp công nhân có phải thay một hình thức sở hữu tư nhân bằng hình thức sở hữu tư nhân khác không?', 'Không; giáo trình nhấn mạnh xóa bỏ triệt để chế độ tư hữu về tư liệu sản xuất, không phải thay một chế độ sở hữu tư nhân bằng chế độ khác.'),
('CNXHKH','ch07.pdf',5,'qa','Vì sao giáo dục gia đình cần gắn với giáo dục xã hội?', 'Gia đình góp phần đào tạo thế hệ trẻ và xã hội hóa cá nhân; thiếu gắn kết sẽ làm cá nhân khó hòa nhập và giáo dục xã hội kém hiệu quả.'),
('CNXHKH','ch07.pdf',10,'hint','Gợi ý cách giải thích vì sao thủ tục pháp lý trong hôn nhân không phủ nhận quyền tự do kết hôn.', 'Phân biệt tình yêu riêng với quan hệ hôn nhân được xã hội thừa nhận; liên hệ trách nhiệm, bảo vệ hạnh phúc và cơ sở thực hiện đầy đủ quyền kết hôn, ly hôn chính đáng.'),
]


def main():
    pilot=list(csv.DictReader((ROOT/'data/qa/qa_pilot_v1.0.csv').open(encoding='utf-8-sig')))
    selected=pilot[25:]
    assert len(selected)==len(NEW)==25
    fields=list(pilot[0])+['mode','origin','owner','source_checksum','document_id','version_id',
        'source_pages','evidence_text','evidence_scope','source_check','peer_review_status']
    readers={};rows=[]
    def enrich(row,origin,mode):
        path=ROOT/'data/corpus'/row['course_id']/row['source_doc']
        if path not in readers:readers[path]=PdfReader(path)
        page=int(row['source_page']);assert 1<=page<=len(readers[path].pages)
        text=unicodedata.normalize('NFC',(readers[path].pages[page-1].extract_text() or '').replace('\r\n','\n').replace('\r','\n'))
        # Display evidence does not expose char offsets; trim line-end layout whitespace.
        # Chunk offsets still use the unchanged normalized extraction, not this CSV text.
        text='\n'.join(line.rstrip() for line in text.splitlines()).strip()
        assert text.strip()
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        did=str(uuid5(NAMESPACE_URL,'w3-document:'+row['course_id']+'/'+path.name))
        row={k:v.strip() if isinstance(v,str) else v for k,v in row.items()}
        return {**row,'mode':mode,'origin':origin,'owner':'TranTuanCuong_B22DCVT073',
            'source_checksum':digest,'document_id':did,'version_id':str(uuid5(NAMESPACE_URL,did+':'+digest)),
            'source_pages':json.dumps([page]),'evidence_text':text,'evidence_scope':'physical_page',
            'source_check':'agent_checked','peer_review_status':'pending_duong'}
    for row in selected:rows.append(enrich(row,'pilot','qa'))
    next_ids = {subject: max(int(row['qa_id'].rsplit('_', 1)[1]) for row in pilot
                            if row['course_id'] == subject) + 1 for subject in ('KTCTMLN', 'CNXHKH')}
    for subject,file,page,mode,question,answer in NEW:
        row={k:'' for k in pilot[0]}
        row.update(qa_id=f'{subject}_QA_{next_ids[subject]:03}',course_id=subject,question=question,
            question_type='hint' if mode=='hint' else 'short_answer',ground_truth=answer,
            source_doc=file,source_page=str(page),source_section='Đối chiếu trang PDF vật lý',difficulty='medium',
            notes='Agent-assisted draft; evidence is the whole source page. Pending peer review; not a held-out test.')
        rows.append(enrich(row,'new_w3',mode))
        next_ids[subject] += 1
    assert len({r['qa_id'] for r in rows})==50
    assert len({r['question'].strip().casefold() for r in rows})==50
    output=ROOT/'data/qa/qa_contributions.csv'
    with output.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    review=ROOT/'data/qa/qa_contribution_reviews.csv'
    with review.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['qa_id','reviewer','source_check','peer_review_status','comment'])
        writer.writeheader()
        for row in rows:writer.writerow({'qa_id':row['qa_id'],'reviewer':'Codex source-check assistance',
            'source_check':'agent_checked','peer_review_status':'pending_duong',
            'comment':'Page evidence attached; no claim of human/teacher sign-off.'})
    print(json.dumps({'rows':len(rows),'pilot':25,'new':25,'mode_hint':sum(r['mode']=='hint' for r in rows),
        'checksum':hashlib.sha256(output.read_bytes()).hexdigest(),'peer_review':'pending_duong'}))


if __name__=='__main__':main()
