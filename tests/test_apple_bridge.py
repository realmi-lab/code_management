"""Apple judge bridge HTTP surface: OpenAI-compatible shape, token auth, honest refusals. No Swift worker involved."""
import importlib.util
import json
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('apple_bridge_under_test', ROOT / 'extensions' / 'apple_bridge' / 'bridge.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

TOKEN = 'synthetic-bridge-token'
SCHEMA = {'type': 'object', 'required': ['grounded_ratio', 'verdict'],
          'properties': {'grounded_ratio': {'type': 'number'}, 'verdict': {'type': 'string', 'enum': ['PASS', 'FAIL']}}}


class FakePool:
    def __init__(self, reply=None, error=None):
        self.requests, self.reply, self.error = [], reply, error

    def call(self, request):
        self.requests.append(request)
        if self.error:
            raise self.error
        content = self.reply if isinstance(self.reply, str) else json.dumps(self.reply, ensure_ascii=False)
        return {'id': request['id'], 'content': content, 'duration_ms': 5}

    def close(self):
        pass


class BridgeServerTest(unittest.TestCase):
    def serve(self, pool, token=TOKEN):
        server = bridge.make_server(pool, token, port=0, log_handle=open('/dev/null', 'w'))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f'http://127.0.0.1:{server.server_address[1]}'

    def request(self, base, path, body=None, token=TOKEN):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
        req = urllib.request.Request(base + path, data=data, headers=headers, method='POST' if body is not None else 'GET')
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.load(error)

    def test_schema_request_reaches_worker_and_returns_openai_shape(self):
        pool = FakePool(reply={'grounded_ratio': 1.0, 'verdict': 'PASS'})
        base = self.serve(pool)
        status, payload = self.request(base, '/v1/chat/completions', {
            'model': bridge.MODEL_ID, 'temperature': 0, 'max_tokens': 300,
            'messages': [{'role': 'system', 'content': '형식을 지키세요'}, {'role': 'user', 'content': '판정 질문'}],
            'response_format': {'type': 'json_schema', 'json_schema': {'name': 'grounding', 'schema': SCHEMA}}})
        self.assertEqual(status, 200)
        self.assertEqual(payload['object'], 'chat.completion')
        self.assertEqual(payload['model'], bridge.MODEL_ID)
        self.assertEqual(json.loads(payload['choices'][0]['message']['content']), {'grounded_ratio': 1.0, 'verdict': 'PASS'})
        self.assertNotIn('usage', payload, 'the framework reports no token counts; none may be invented')
        sent = pool.requests[-1]
        self.assertEqual((sent['system'], sent['prompt'], sent['temperature'], sent['max_tokens']), ('형식을 지키세요', '판정 질문', 0.0, 300))
        self.assertEqual((sent['schema'], sent['schema_name']), (SCHEMA, 'grounding'))
        status, models = self.request(base, '/v1/models')
        self.assertEqual((status, [m['id'] for m in models['data']]), (200, [bridge.MODEL_ID]))

    def test_missing_or_wrong_token_is_rejected_before_the_worker_runs(self):
        pool = FakePool(reply='x')
        base = self.serve(pool)
        body = {'model': bridge.MODEL_ID, 'messages': [{'role': 'user', 'content': 'hi'}]}
        self.assertEqual(self.request(base, '/v1/chat/completions', body, token=None)[0], 401)
        self.assertEqual(self.request(base, '/v1/chat/completions', body, token='wrong')[0], 401)
        self.assertEqual(self.request(base, '/v1/models', token=None)[0], 401)
        self.assertEqual(pool.requests, [])

    def test_other_models_streaming_and_json_object_are_refused_not_substituted(self):
        pool = FakePool(reply='x')
        base = self.serve(pool)
        status, payload = self.request(base, '/v1/chat/completions', {'model': 'gpt-4o', 'messages': [{'role': 'user', 'content': 'hi'}]})
        self.assertEqual((status, payload['error']['code']), (404, 'model_not_found'))
        status, payload = self.request(base, '/v1/chat/completions', {'model': bridge.MODEL_ID, 'stream': True, 'messages': [{'role': 'user', 'content': 'hi'}]})
        self.assertEqual((status, payload['error']['code']), (400, 'unsupported_parameter'))
        status, payload = self.request(base, '/v1/chat/completions', {'model': bridge.MODEL_ID, 'response_format': {'type': 'json_object'},
                                                                      'messages': [{'role': 'user', 'content': 'hi'}]})
        self.assertEqual((status, payload['error']['code']), (400, 'unsupported_parameter'))
        self.assertEqual(self.request(base, '/v1/chat/completions', {'model': bridge.MODEL_ID, 'messages': []})[0], 400)
        self.assertEqual(pool.requests, [])

    def test_worker_errors_and_timeouts_surface_as_gateway_errors(self):
        base = self.serve(FakePool(error=bridge.BridgeError(504, '시간 초과', 'timeout')))
        status, payload = self.request(base, '/v1/chat/completions', {'model': bridge.MODEL_ID, 'messages': [{'role': 'user', 'content': 'hi'}]})
        self.assertEqual((status, payload['error']['code']), (504, 'timeout'))
        with self.assertRaises(bridge.BridgeError) as raised:
            bridge.completion({'id': 'x', 'error': 'guardrailViolation', 'error_type': 'generation_error'})
        self.assertEqual((raised.exception.status, raised.exception.code), (502, 'model_error'))

    def test_multi_turn_messages_are_rendered_with_roles_and_text_parts(self):
        request = bridge.worker_request({'model': bridge.MODEL_ID, 'messages': [
            {'role': 'system', 'content': [{'type': 'text', 'text': '규칙 A'}]},
            {'role': 'user', 'content': '첫 질문'}, {'role': 'assistant', 'content': '첫 답'}, {'role': 'user', 'content': '둘째 질문'}]})
        self.assertEqual(request['system'], '규칙 A')
        self.assertEqual(request['prompt'], 'user: 첫 질문\n\nassistant: 첫 답\n\nuser: 둘째 질문')
        self.assertNotIn('temperature', request)
        self.assertNotIn('schema', request)


if __name__ == '__main__':
    unittest.main()
