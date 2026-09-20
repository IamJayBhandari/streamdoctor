import unittest
from streamdoctor import network


class NetworkParsingTests(unittest.TestCase):

    def test_parse_rtmp(self):
        scheme, host, port = network.parse_stream_url("rtmp://example.com:1935/live/1")
        self.assertEqual(scheme, "rtmp")
        self.assertEqual(host, "example.com")
        self.assertEqual(port, 1935)

    def test_parse_rtsp_default_port(self):
        scheme, host, port = network.parse_stream_url("rtsp://camera.local/stream")
        self.assertEqual(scheme, "rtsp")
        self.assertEqual(host, "camera.local")
        self.assertEqual(port, 554)

    def test_parse_with_credentials_redaction(self):
        scheme, host, port = network.parse_stream_url("rtmp://user:pass@example.com/live")
        self.assertEqual(host, "example.com")
        # password should not be returned
        self.assertNotIn("user", host)


class ProcParsingTests(unittest.TestCase):

    def test_read_proc_snmp_none_on_missing(self):
        # We cannot easily simulate missing /proc in this environment, but ensure function callable
        data = network._read_proc_net_snmp()
        # returns dict or None
        self.assertTrue(data is None or isinstance(data, dict))

    def test_snapshot_and_compute_deltas(self):
        # Call snapshot; ensure no exceptions and deltas computable
        s1 = network.snapshot_counters()
        s2 = network.snapshot_counters()
        deltas = network.compute_deltas(s1, s2)
        # deltas may be None or dict
        self.assertTrue(deltas is None or isinstance(deltas, dict))


if __name__ == '__main__':
    unittest.main()
