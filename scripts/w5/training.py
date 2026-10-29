"""Check exporter payload against candidates with the actual pinned tokenizer."""
import hashlib
from .common import digest, projected, prompt_data_strings


def check_training_format(records, payloads, tokenizer, contract):
    findings=[];counts=[];cfg=contract['training']
    if len(records)!=len(payloads): raise ValueError('Candidate/payload counts differ')
    for record,payload in zip(records,payloads):
        rid=record['record_id']
        try:
            _,expected=projected(record,contract)
            completion=[{'role':'assistant','content':record['target_text']}]
            if set(payload)!={'prompt','completion'} or payload['prompt']!=expected or payload['completion']!=completion:
                raise ValueError('Payload differs from trusted prompt/target or contains forbidden metadata')
            data=[*prompt_data_strings(record),record['target_text']]
            import re
            if any(re.search(r'<\|[^<>\r\n]{1,80}\|>',s) or any(t and t in s for t in tokenizer.all_special_tokens) for s in data):
                raise ValueError('Special token in untrusted prompt/target data')
            prompt=tokenizer.apply_chat_template(expected,tokenize=True,add_generation_prompt=True)
            full=tokenizer.apply_chat_template(expected+completion,tokenize=True,add_generation_prompt=False)
            if not isinstance(full,list) or not all(type(t) is int for t in full+prompt): raise ValueError('Invalid tokenizer output')
            if full[:len(prompt)]!=prompt: raise ValueError('Chat template prefix differs; completion-only boundary is not safe')
            target=full[len(prompt):]
            if not target: raise ValueError('No supervised target tokens')
            newline=tokenizer.encode('\n',add_special_tokens=False)
            tail=target[:-len(newline)] if newline and target[-len(newline):]==newline else target
            eos=tokenizer.eos_token_id
            if not tail or tail[-1]!=eos or len(tail)<2: raise ValueError('Missing target/EOS at completion end')
            if len(prompt)>cfg['max_prompt_tokens'] or len(target)>cfg['max_completion_tokens'] or len(full)>cfg['max_sequence_tokens']:
                raise ValueError('Token budget exceeded; do not truncate silently')
            labels=[-100]*len(prompt)+target
            if labels[:len(prompt)]!=[-100]*len(prompt) or labels[len(prompt):]!=target: raise ValueError('Invalid completion-only mask')
            counts.append(dict(record_id=rid,prompt_tokens=len(prompt),completion_tokens=len(target),sequence_tokens=len(full),
                supervised_tokens=len(target),eos_supervised=True,content_sha256=record['content_sha256'],sft_sha256=digest(payload)))
        except (ValueError,TypeError,KeyError,AttributeError) as exc:
            findings.append(dict(record_id=rid,code='TRAINING_FORMAT',detail=str(exc)))
    return dict(schema_version='w5-tokenization-v1',contract_fingerprint=contract['fingerprint'],passed=not findings,
        records=counts,findings=findings,chat_template_sha256=hashlib.sha256(tokenizer.chat_template.encode()).hexdigest(),
        tokenizer_revision=cfg['tokenizer_revision'],mask_kind='CPU reference completion-only labels; padding must be -100',
        trainer_integration='NOT_RUN_W6',model_weights_loaded=False)
