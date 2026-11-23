"""No model calls: exact wire-prefix drift and private-only diagnostic fields."""
import json
import unittest

from src.adapters.request_fingerprint import RequestFingerprints


class RequestFingerprintTests(unittest.TestCase):
    def test_append_retry_change_and_private_payload(self):
        recorder = RequestFingerprints()
        image = {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,PRIVATE_PIXELS'}}
        request = {'model': 'route', 'messages': [{'role': 'system', 'content': 'PRIVATE_SYSTEM'},
                    {'role': 'user', 'content': [image, image, {'type': 'text', 'text': 'PRIVATE_TEXT'}]}]}
        body = lambda: json.dumps(request).encode()
        first = recorder.observe(body(), 'one')
        self.assertEqual(first['image_occurrences'], 2)
        self.assertEqual(first['unique_image_payloads'], 1)
        self.assertIsNone(first['shared_prefix_messages'])
        retry = recorder.observe(body(), 'one')
        self.assertEqual(first['body_sha256'], retry['body_sha256'])
        self.assertEqual(retry['shared_prefix_messages'], 2)
        request['messages'].append({'role': 'assistant', 'content': 'extra'})
        self.assertEqual(recorder.observe(body(), 'one')['shared_prefix_messages'], 2)
        request['messages'][0]['content'] += ' changed'
        self.assertEqual(recorder.observe(body(), 'one')['shared_prefix_messages'], 0)
        request['max_tokens'] = 393216
        self.assertFalse(recorder.observe(body(), 'one')['envelope_unchanged'])
        self.assertIsNone(recorder.observe(body(), 'two')['shared_prefix_messages'])
        for secret in ('PRIVATE_SYSTEM', 'PRIVATE_TEXT', 'PRIVATE_PIXELS', 'data:image', 'extra', 'one'):
            self.assertNotIn(secret, json.dumps(first))

    def test_unknown_session_and_bounded_memory(self):
        recorder = RequestFingerprints(capacity=1)
        body = b'{"messages":[]}'
        recorder.observe(body, 'first')
        recorder.observe(body, 'second')
        self.assertIsNone(recorder.observe(body, 'first')['previous_message_count'])
        recorder.observe(body, '')
        self.assertIsNone(recorder.observe(body, '')['previous_message_count'])

    def test_malformed_media_is_left_for_provider_validation(self):
        body = json.dumps({'messages': [{'role': 'user', 'content': [
            {'type': 'image_url', 'image_url': None}, {'type': 'image_url', 'image_url': 'invalid'},
            {'type': 'image_url', 'image_url': {'url': 12}}]}]}).encode()
        self.assertEqual(RequestFingerprints().observe(body, 'one')['image_occurrences'], 0)
