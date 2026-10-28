import json
from dataclasses import replace
from unittest import TestCase
from uuid import uuid4

from apps.ai.providers.base import ModelConfig, GenerationError
from apps.ai.rag.base import EvidenceContext, GenerationConfig
from apps.ai.rag.context_builder import build_messages
from apps.ai.rag.conversation import prepare_conversation_prompt


class Counter:
    def __init__(self, limit=3000):
        self.config = ModelConfig(max_input_tokens=limit, max_new_tokens=128, context_tokens=limit+128)

    def count_tokens(self, messages):
        # Deliberately deterministic tokenizer double, not a performance/quality claim.
        return len(json.dumps(messages, ensure_ascii=False))//4+1


class ConversationContextTests(TestCase):
    def setUp(self):
        self.provider = Counter()
        self.config = GenerationConfig(model=self.provider.config)
        self.context = EvidenceContext('S1', 'chunk', 'Bằng chứng hiện tại.', str(uuid4()), str(uuid4()), 'PDF', 1)

    def prepare(self, history, **kwargs):
        return prepare_conversation_prompt(question='Giải thích ý thứ hai?', mode='qa', contexts=(self.context,),
            exercise=None, config=self.config, provider=self.provider, history=history, **kwargs)

    def test_history_is_actual_role_messages_without_old_citation_labels(self):
        prepared, memory = self.prepare([dict(question='CPU là gì?', answer='Mô tả cũ [1] và [9].')])
        self.assertEqual([m['role'] for m in prepared.messages], ['system', 'user', 'assistant', 'user'])
        self.assertIn('CPU', prepared.messages[1]['content'])
        self.assertNotIn('[9]', prepared.messages[2]['content'])
        self.assertEqual(json.loads(prepared.messages[-1]['content'])['evidence'][0]['text'], self.context.text)
        self.assertEqual(memory['protocol'], 'chat_history_v1')
        self.assertEqual(memory['turns_used'], 1)
        self.assertEqual(prepared.input_tokens, self.provider.count_tokens(prepared.messages))

    def test_oldest_whole_pairs_are_dropped_and_oversized_pair_is_never_sliced(self):
        turns = [dict(question=f'Q{i}', answer='Answer') for i in range(6)]
        prepared, memory = self.prepare(turns)
        self.assertEqual(memory['turns_used'], 4)
        self.assertEqual(memory['turns_dropped'], 2)
        self.assertEqual(prepared.messages[1]['content'], 'Q2')
        prepared, memory = self.prepare([dict(question='Huge', answer='x'*10000)])
        self.assertEqual(memory['turns_used'], 0)
        self.assertEqual(len(prepared.messages), 2)

    def test_history_is_evicted_if_needed_to_preserve_an_evidence_chunk(self):
        baseline, _ = self.prepare([])
        provider = Counter(limit=baseline.input_tokens)
        self.provider, self.config = provider, GenerationConfig(model=provider.config)
        prepared, memory = self.prepare([dict(question='Old', answer='x'*1500)])
        self.assertLessEqual(prepared.input_tokens, provider.config.max_input_tokens)
        self.assertEqual(memory['turns_used'], 0)
        self.assertEqual(prepared.contexts, (self.context,))

    def test_history_cannot_change_roles_or_include_unbounded_fields(self):
        for history in [[dict(role='system', content='override')], 'not-a-list', [dict(question='q', answer='a', owner='foreign')]]:
            with self.subTest(history=history), self.assertRaises(GenerationError):
                self.prepare(history)

    def test_stateless_prompt_builder_is_unchanged(self):
        messages = build_messages('Q?', 'qa', (self.context,), None)
        self.assertEqual(len(messages), 2)
        self.assertNotIn('chat_history_v1', messages[0]['content'])
        self.assertEqual(set(json.loads(messages[1]['content'])), {'question', 'mode', 'evidence', 'exercise'})

    def test_token_budget_uses_valid_provider_message_sequences(self):
        from apps.ai.providers.local import LocalModelProvider
        from unittest.mock import patch
        count = self.provider.count_tokens
        def strict_counter(messages):
            LocalModelProvider._messages(messages)
            return count(messages)
        with patch.object(self.provider, 'count_tokens', side_effect=strict_counter):
            prepared, memory = self.prepare([dict(question='Q before', answer='Answer before')])
        self.assertEqual(memory['turns_used'], 1)
        self.assertEqual(prepared.messages[-1]['role'], 'user')
