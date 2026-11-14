"""Real course-filtered retrieval and one frozen packing for BOTH grounded arms."""
import argparse
from dataclasses import asdict
import itertools
import json
import math
import os
from pathlib import Path
import random
import time

from scripts.comparison.protocol import canonical, digest, file_hash, read_rows, validate_cache, write_json, write_rows

ROOT = Path(__file__).resolve().parents[2]


def build_messages(row, arm):
    if arm not in {'base','rag','tuned_rag'}: raise ValueError('Unknown arm')
    prompt = (ROOT/'data/comparison'/('base-system.txt' if arm=='base' else 'rag-system.txt')).read_text(encoding='utf-8')
    payload = {'question':row['question'],'mode':'qa'}
    if arm != 'base':
        payload.update(evidence=[{'evidence_id':f'E{i}.1','citation_label':i,'text':c['text']}
                                 for i,c in enumerate(row['contexts'],1)],exercise=None)
    return [{'role':'system','content':prompt},{'role':'user','content':canonical(payload).decode('utf-8')}]


def chat_tokens(tokenizer,messages):
    result = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True, return_dict=False)
    if not isinstance(result,list) or not all(type(value) is int for value in result):
        raise ValueError('Chat tokenizer must return a flat list of integer token IDs')
    return result


def evidence_tokens(tokenizer,contexts):
    evidence = [{'evidence_id':f'E{i}.1','citation_label':i,'text':c['text']} for i,c in enumerate(contexts,1)]
    return len(tokenizer.encode(canonical(evidence).decode('utf-8'),add_special_tokens=False))


def pack_contexts(row,tokenizer,evidence_budget=3072,total_budget=4096):
    packed = []
    original = row['contexts']
    if len(chat_tokens(tokenizer,build_messages({**row,'contexts':[]},'rag'))) > total_budget:
        raise ValueError('Question/system exceed total token budget')
    for context in original:
        text = context['text']
        def fits(value):
            candidate = packed + [{**context,'text':value}]
            return (evidence_tokens(tokenizer,candidate) <= evidence_budget and
                    len(chat_tokens(tokenizer,build_messages({**row,'contexts':candidate},'rag'))) <= total_budget)
        if fits(text): packed.append(dict(context)); continue
        # Unicode code point prefix, then verified using actual Qwen chat template.
        low,high = 0,len(text)
        while low < high:
            mid = (low+high+1)//2
            if fits(text[:mid]): low = mid
            else: high = mid-1
        if text[:low].strip(): packed.append({**context,'text':text[:low], 'packed_char_end':context.get('char_start',0)+low})
        break
    result = {**row,'contexts':packed,'contexts_sha256':digest(packed)}
    result['packing'] = {'method':'ranked_unicode_prefix_verified_with_Qwen_chat_template',
        'retrieved_chunks':[{'chunk_id':c['chunk_id'],'document_id':c.get('document_id'),'page_number':c['page_number'],
                             'text_sha256':digest(c['text'])} for c in original],
        'original_contexts_sha256':digest(original),'truncated':packed!=original,
        'evidence_tokens':evidence_tokens(tokenizer,packed),'chat_tokens':len(chat_tokens(tokenizer,build_messages(result,'rag'))),
        'max_evidence_tokens':evidence_budget,'max_input_tokens':total_budget}
    return result


def retrieval_metrics(retrieved,gold):
    if not gold: return None
    unique = list(dict.fromkeys(retrieved))[:5]
    relevant = [int(p in gold) for p in unique]
    hits = sum(relevant)
    dcg = sum(value/math.log2(rank+2) for rank,value in enumerate(relevant))
    ideal = sum(1/math.log2(rank+2) for rank in range(min(5,len(gold))))
    return {'page_recall_at_5':hits/len(gold), 'mrr_at_5':next((1/(i+1) for i,r in enumerate(relevant) if r),0),
            'ndcg_unique_page_at_5':dcg/ideal, 'all_gold_pages_found':hits==len(gold)}


def schedule(inputs):
    permutations = list(itertools.permutations(('base','rag','tuned_rag')))
    random.Random(42).shuffle(permutations)
    return [{'qa_id':row['qa_id'],'arms':list(permutations[i%6])} for i,row in enumerate(inputs)]
