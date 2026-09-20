import unittest
from unittest.mock import MagicMock

from streamdoctor.executor import RemediationExecutor, ExecutionResult
from streamdoctor.remediation import Remediation, REPROBE_STREAM, CONTINUE_MONITORING


class DummyAnalyzer:
    def __init__(self, url, duration):
        self.url = url
        self.duration = duration
        self.analyzed = False

    def analyze(self):
        self.analyzed = True
        # return a minimal object with required attrs
        class R:
            frames = 10
            fps = 1.0
            declared_fps = 25.0
            i_frames = 1
            p_frames = 8
        return R()


class ExecutorTests(unittest.TestCase):

    def test_dry_run_reprobe(self):
        rem = Remediation(action=REPROBE_STREAM, reason="test", confidence="HIGH", safe=True, automatic=False, mode="DRY-RUN", details=[])
        ex = RemediationExecutor()
        res = ex.execute(rem, analyzer_cls=DummyAnalyzer, url="rtsp://x", duration=5)
        self.assertFalse(res.attempted)
        self.assertFalse(res.executed)
        self.assertTrue(res.success)

    def test_reprobe_always_dry_run(self):
        rem = Remediation(action=REPROBE_STREAM, reason="test", confidence="HIGH", safe=True, automatic=False, mode="DRY-RUN", details=[])
        ex = RemediationExecutor()
        res = ex.execute(rem, analyzer_cls=DummyAnalyzer, url="rtsp://x", duration=5)
        self.assertTrue(res.success)
        self.assertFalse(res.executed)
        self.assertIn('dry-run', res.message.lower())

    def test_continue_monitoring(self):
        rem = Remediation(action=CONTINUE_MONITORING, reason="test", confidence="LOW", safe=True, automatic=False, mode="DRY-RUN", details=[])
        ex = RemediationExecutor()
        res = ex.execute(rem)
        self.assertTrue(res.success)
        self.assertFalse(res.executed)

    def test_reconnect_refused(self):
        rem = Remediation(action="RECONNECT_STREAM", reason="test", confidence="HIGH", safe=False, automatic=False, mode="DRY-RUN", details=[])
        ex = RemediationExecutor()
        res = ex.execute(rem)
        self.assertFalse(res.executed)
        self.assertFalse(res.success)
        self.assertIn('not enabled', res.message)

    def test_collect_network_trace_refused(self):
        rem = Remediation(action="COLLECT_NETWORK_TRACE", reason="test", confidence="HIGH", safe=False, automatic=False, mode="DRY-RUN", details=[])
        ex = RemediationExecutor()
        res = ex.execute(rem)
        self.assertFalse(res.executed)
        self.assertFalse(res.success)
        self.assertIn('not implemented', res.message)

    def test_unknown_action_rejected(self):
        rem = Remediation(action="UNKNOWN_ACTION", reason="test", confidence="LOW", safe=False, automatic=False, mode="DRY-RUN", details=[])
        ex = RemediationExecutor()
        res = ex.execute(rem)
        self.assertFalse(res.executed)
        self.assertFalse(res.success)

    def test_missing_analyzer_reprobe_rejected(self):
        rem = Remediation(action=REPROBE_STREAM, reason="test", confidence="HIGH", safe=True, automatic=False, mode="DRY-RUN", details=[])
        ex = RemediationExecutor()
        res = ex.execute(rem, analyzer_cls=None, url=None, duration=None)
        self.assertFalse(res.executed)
        self.assertTrue(res.success)


if __name__ == '__main__':
    unittest.main()
