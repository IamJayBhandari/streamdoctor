import unittest
from unittest.mock import patch, MagicMock
import importlib

fastapi_spec = importlib.util.find_spec('fastapi')
if fastapi_spec:
    from fastapi.testclient import TestClient
    from streamdoctor.rest import app

    client = TestClient(app)
else:
    client = None


@unittest.skipUnless(fastapi_spec, "fastapi not installed; skipping REST tests")
class RestTests(unittest.TestCase):

    def test_health(self):
        r = client.get('/health')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json().get('status'), 'ok')

    @patch('streamdoctor.api.analyze_stream')
    def test_analyze_success(self, analyze_mock):
        fake = MagicMock()
        fake.to_dict.return_value = {'analysis': {}, 'diagnosis': {}}
        analyze_mock.return_value = fake

        r = client.post('/analyze', json={"url": "rtsp://example/1", "duration": 10})
        self.assertEqual(r.status_code, 200)
        self.assertIn('analysis', r.json())

    @patch('streamdoctor.api.analyze_and_diagnose')
    def test_diagnose_success(self, diagnose_mock):
        fake = MagicMock()
        fake.to_dict.return_value = {'analysis': {}, 'diagnosis': {}, 'remediation': {}}
        diagnose_mock.return_value = fake

        r = client.post('/diagnose', json={"url": "rtsp://example/1", "duration": 10})
        self.assertEqual(r.status_code, 200)
        self.assertIn('diagnosis', r.json())

    @patch('streamdoctor.api.plan_remediation')
    def test_remediate_success(self, plan_mock):
        fake = MagicMock()
        fake.to_dict.return_value = {'analysis': {}, 'diagnosis': {}, 'remediation': {}, 'execution': {}}
        plan_mock.return_value = fake

        r = client.post('/remediate', json={"url": "rtsp://example/1", "duration": 10})
        self.assertEqual(r.status_code, 200)
        self.assertIn('remediation', r.json())
        # default is dry-run -> execution.executed should be False or None

    def test_invalid_url(self):
        r = client.post('/analyze', json={"url": "", "duration": 10})
        self.assertEqual(r.status_code, 400)

    def test_invalid_duration(self):
        r = client.post('/analyze', json={"url": "rtsp://example/1", "duration": -5})
        self.assertEqual(r.status_code, 422)

    @patch('streamdoctor.api.analyze_stream')
    def test_analyzer_failure(self, analyze_mock):
        analyze_mock.side_effect = Exception('boom')
        r = client.post('/analyze', json={"url": "rtsp://example/1", "duration": 10})
        self.assertEqual(r.status_code, 502)


if __name__ == '__main__':
    unittest.main()
