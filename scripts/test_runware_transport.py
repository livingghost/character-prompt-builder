"""Runware storage HTTP requests, exact media evidence, and deletion recovery."""
from __future__ import annotations

import copy
import base64
import io
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import threading
import unittest
import uuid
from unittest.mock import patch

import transport_runware as transport
from transport_contract import Indeterminate, Refused, TIMEOUT


SERVICE = {'endpoint': {'base_url': 'https://api.runware.ai/v1'}}
MEDIA_UUID = 'be012743-84d6-4e79-8bfb-cff57e622e1b'
STORED_URL = 'https://mm.runware.ai/media-storage/test.png'
SOURCE_URL = 'https://assets.example.test/reference.png'
from PIL import Image
_image_bytes = io.BytesIO()
Image.new('RGB', (4, 3), 'steelblue').save(_image_bytes, format='PNG')
IMAGE = _image_bytes.getvalue()


def accepted(request, *, cost='0.0125'):
    entry = {'taskType': 'mediaStorage', 'taskUUID': request['taskUUID'],
             'operation': request['operation'], 'mediaUUID': MEDIA_UUID}
    if request['operation'] == 'upload':
        entry['mediaURL'] = STORED_URL
    if cost is not None:
        entry['cost'] = cost
    return {'data': [entry], 'provider_metadata': {'retained': True}}


class StorageHTTPTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.post_status = 200
        self.stored_status = 200
        self.stored_bytes = IMAGE
        self.response = accepted
        self.last_body = None
        self.delete_answers = {}
        self.lookup_processing = False
        self.delay = 0
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                owner.calls.append({'method': 'POST', 'path': self.path,
                                    'authorization': self.headers.get('Authorization'), 'payload': payload})
                if owner.delay:
                    threading.Event().wait(owner.delay)
                request = payload[0]
                if request['taskType'] == 'getResponse':
                    body = ({'data': [{'taskUUID': request['taskUUID'], 'status': 'processing'}]}
                            if owner.lookup_processing else owner.delete_answers.get(request['taskUUID'], {}))
                else:
                    body = owner.response(request) if callable(owner.response) else owner.response
                    if request.get('operation') == 'delete' and owner.post_status == 200:
                        owner.delete_answers[request['taskUUID']] = copy.deepcopy(body)
                raw = body if isinstance(body, bytes) else json.dumps(body).encode('utf-8')
                owner.last_body = raw
                self.send_response(owner.post_status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                if owner.post_status == 302:
                    self.send_header('Location', '/must-not-follow')
                self.end_headers()
                try:
                    self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def do_GET(self):
                owner.calls.append({'method': 'GET', 'path': self.path,
                                    'authorization': self.headers.get('Authorization')})
                self.send_response(owner.stored_status)
                self.send_header('Content-Length', str(len(owner.stored_bytes)))
                if owner.stored_status == 302:
                    self.send_header('Location', '/must-not-follow')
                self.end_headers()
                self.wfile.write(owner.stored_bytes)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={'poll_interval': 0.005}, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        base = 'http://127.0.0.1:' + str(self.server.server_port)
        self.real_endpoint = transport.endpoint
        self.real_stored_url = transport._stored_url
        self.enterContext(patch.object(transport, 'endpoint', return_value=base + '/v1'))
        self.enterContext(patch.object(transport, '_stored_url', side_effect=lambda url:
            base + '/stored.png' if url == STORED_URL else self.real_stored_url(url)))
        environment = {key: value for key, value in os.environ.items() if key != TIMEOUT}
        self.enterContext(patch.dict(os.environ, environment, clear=True))

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def upload(self, *, source=SOURCE_URL, key='synthetic-selected-key'):
        return transport.upload_media(IMAGE, 'image/png', SERVICE, key, source_url=source)

    def posts(self):
        return [call for call in self.calls if call['method'] == 'POST']

    def test_upload_bytes_once_and_verify_stored_bytes_before_accepting_uuid(self):
        result = self.upload(source=None)
        self.assertEqual(result['provider_id'], MEDIA_UUID)
        self.assertEqual(result['response'], json.loads(self.last_body))
        self.assertEqual(result['usage'], {'currency': 'USD', 'amount': '0.0125', 'final': True})
        self.assertEqual(len(self.posts()), 1)
        task = self.posts()[0]['payload'][0]
        self.assertEqual({k: v for k, v in task.items() if k != 'taskUUID'},
                         {'taskType': 'mediaStorage', 'operation': 'upload',
                          'media': 'data:image/png;base64,' + base64.b64encode(IMAGE).decode('ascii')})
        self.assertEqual(uuid.UUID(task['taskUUID']).version, 4)
        self.assertEqual(self.posts()[0]['authorization'], 'Bearer synthetic-selected-key')
        self.assertEqual(self.calls[1], {'method': 'GET', 'path': '/stored.png', 'authorization': None})

    def test_distinct_generation_uploads_make_distinct_requests(self):
        self.upload()
        self.upload()
        self.assertEqual(len(self.posts()), 2)
        self.assertNotEqual(self.posts()[0]['payload'][0]['taskUUID'], self.posts()[1]['payload'][0]['taskUUID'])

    def test_absent_billing_remains_unknown(self):
        self.response = lambda request: accepted(request, cost=None)
        self.assertIsNone(self.upload()['usage'])

    def test_absent_operation_echo_remains_matched_by_task_uuid(self):
        def without_echo(request):
            entry = accepted(request)['data'][0]
            del entry['operation']
            return {'data': [entry]}
        self.response = without_echo
        self.assertEqual(self.upload()['provider_id'], MEDIA_UUID)
        request = transport.prepare_delete(MEDIA_UUID, SERVICE)
        result = transport.send_delete(request, SERVICE, 'synthetic-selected-key', provider_id=MEDIA_UUID)
        self.assertEqual(result['response']['data'][0]['mediaUUID'], MEDIA_UUID)

    def test_provider_refusal_retains_complete_actual_answer(self):
        answer = {'errors': [{'code': 'invalidMedia', 'message': 'Synthetic refusal',
                              'details': {'preserve': 'provider fields'}}]}
        for status in (200, 400):
            self.post_status, self.response = status, answer
            before = len(self.calls)
            with self.subTest(status=status), self.assertRaises(Refused) as caught:
                self.upload()
            self.assertEqual(caught.exception.answer, answer)
            self.assertEqual(len(self.calls), before + 1)

    def test_redirect_and_server_failure_keep_evidence_without_resend(self):
        for status in (302, 503):
            self.post_status, self.response = status, {'message': 'Synthetic HTTP response'}
            before = len(self.calls)
            with self.subTest(status=status), self.assertRaises(Indeterminate) as caught:
                self.upload()
            self.assertEqual((caught.exception.status, caught.exception.body), (status, self.last_body))
            self.assertEqual(len(self.calls), before + 1)
            self.assertEqual(self.calls[-1]['path'], '/v1')

    def test_timeout_leaves_one_unresolved_upload(self):
        self.delay = 0.08
        with patch.object(transport, '_storage_post', wraps=transport._storage_post) as storage_post, \
                patch.dict(os.environ, {TIMEOUT: '0.02'}), self.assertRaises(Indeterminate) as caught:
            self.upload()
        self.assertEqual(storage_post.call_count, 1)
        self.assertNotIn('synthetic-selected-key', str(caught.exception))

    def test_non_object_response_remains_unknown(self):
        for body in (b'<html>Synthetic response</html>', b'[]'):
            self.response = body
            with self.subTest(body=body), self.assertRaises(Indeterminate) as caught:
                self.upload()
            self.assertEqual((caught.exception.status, caught.exception.body), (200, body))

    def test_requires_one_matching_upload_task_and_actual_media_uuid(self):
        responses = [
            lambda request: {'data': []},
            lambda request: {'data': accepted(request)['data'] * 2},
            lambda request: {'data': [{**accepted(request)['data'][0], 'taskUUID': str(uuid.uuid4())}]},
            lambda request: {'data': [{**accepted(request)['data'][0], 'mediaUUID': 'unverified-id'}]},
            lambda request: {'data': [{**accepted(request)['data'][0], 'operation': 'delete'}]},
            lambda request: {**accepted(request), 'errors': [{'code': 'storageFailed'}]},
        ]
        for index, response in enumerate(responses):
            self.response = response
            before = len(self.calls)
            with self.subTest(response=index), self.assertRaises(Indeterminate) as caught:
                self.upload()
            self.assertEqual(caught.exception.body, self.last_body)
            self.assertEqual(len(self.calls), before + 1)

    def test_stored_content_mismatch_retains_upload_response_and_stops(self):
        self.stored_bytes = b'different stored content'
        with self.assertRaises(Indeterminate) as caught:
            self.upload()
        self.assertEqual(caught.exception.body, self.last_body)
        self.assertEqual([call['method'] for call in self.calls], ['POST', 'GET'])
        # The storage answer names the identifier it issued, which the run journal keeps with the HTTP status.
        evidence = caught.exception.evidence()
        self.assertEqual(evidence['http_status'], 200)
        self.assertEqual(json.loads(evidence['body'])['data'][0]['mediaUUID'], MEDIA_UUID)

    def test_stored_content_redirect_is_not_followed(self):
        self.stored_status = 302
        with self.assertRaises(Indeterminate):
            self.upload()
        self.assertEqual([call['path'] for call in self.calls], ['/v1', '/stored.png'])

    def test_storage_host_and_actual_source_bytes_are_validated(self):
        with self.assertRaises(ValueError):
            transport.upload_media(b'not an image', 'image/png', SERVICE,
                                   'synthetic-selected-key', source_url=None)
        self.assertEqual(self.calls, [])
        self.response = lambda request: {'data': [{**accepted(request)['data'][0],
                                                 'mediaURL': 'https://unrelated.example.test/file.png'}]}
        with self.assertRaises(Indeterminate):
            self.upload()
        self.assertEqual(len(self.calls), 1)

    def test_endpoint_and_explicit_credential_precede_network(self):
        with patch.object(transport, 'endpoint', side_effect=self.real_endpoint):
            with self.assertRaises(ValueError):
                transport.upload_media(IMAGE, 'image/png', {'endpoint': {'base_url': 'https://unrelated.example.test'}},
                                       'synthetic-selected-key', source_url=SOURCE_URL)
        with self.assertRaises(ValueError):
            self.upload(key='')
        self.assertEqual(self.calls, [])

    def test_delete_receipt_and_lookup_refer_to_one_durable_operation(self):
        request = transport.prepare_delete(MEDIA_UUID, SERVICE)
        result = transport.send_delete(request, SERVICE, 'synthetic-selected-key', provider_id=MEDIA_UUID)
        self.assertEqual(result['response']['data'][0]['mediaUUID'], MEDIA_UUID)
        self.assertEqual(transport.lookup_delete(request, SERVICE, 'synthetic-selected-key', provider_id=MEDIA_UUID)['response']['data'],
                         result['response']['data'])
        self.assertEqual([call['payload'][0]['taskType'] for call in self.posts()], ['mediaStorage', 'getResponse'])
        self.assertEqual(self.posts()[0]['payload'][0], request)
        self.assertEqual(self.posts()[1]['payload'][0]['taskUUID'], request['taskUUID'])

    def test_processing_delete_lookup_does_not_send_another_deletion(self):
        request = transport.prepare_delete(MEDIA_UUID, SERVICE)
        self.lookup_processing = True
        self.assertIsNone(transport.lookup_delete(request, SERVICE, 'synthetic-selected-key', provider_id=MEDIA_UUID))
        self.assertEqual(self.posts()[0]['payload'], [{'taskType': 'getResponse', 'taskUUID': request['taskUUID']}])

    def test_missing_media_error_is_preserved_without_another_delete_send(self):
        request = transport.prepare_delete(MEDIA_UUID, SERVICE)
        answer = {'errors': [{'taskUUID': request['taskUUID'], 'code': 'fixtureMissingMedia',
                              'message': 'Synthetic missing stored media.'}]}
        self.post_status, self.response = 404, answer
        with self.assertRaises(Refused) as caught:
            transport.send_delete(request, SERVICE, 'synthetic-selected-key', provider_id=MEDIA_UUID)
        self.assertEqual(caught.exception.answer, answer)
        self.assertEqual([call['payload'][0] for call in self.posts()], [request])

    def test_delete_response_must_identify_the_owned_media(self):
        self.response = lambda request: {'data': [{**accepted(request)['data'][0],
                                                 'mediaUUID': str(uuid.uuid4())}]}
        with self.assertRaises(Indeterminate) as caught:
            transport.send_delete(transport.prepare_delete(MEDIA_UUID, SERVICE), SERVICE, 'synthetic-selected-key', provider_id=MEDIA_UUID)
        self.assertEqual(caught.exception.body, self.last_body)
        self.assertEqual(len(self.posts()), 1)

    def test_delete_request_must_target_its_owned_upload_before_any_network(self):
        request = transport.prepare_delete(MEDIA_UUID, SERVICE)
        request['media'] = str(uuid.uuid4())
        for operation in (transport.send_delete, transport.lookup_delete):
            with self.subTest(operation=operation.__name__), self.assertRaises(ValueError):
                operation(request, SERVICE, 'synthetic-selected-key', provider_id=MEDIA_UUID)
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
