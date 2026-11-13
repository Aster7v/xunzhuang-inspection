import importlib.util
from contextlib import closing
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

temp = tempfile.TemporaryDirectory()
os.environ.update(FISHBOT_DB=str(Path(temp.name) / 'readings.sqlite'), FISHBOT_INGEST_TOKEN='test-only-token', FISHBOT_ALARM_FIELD='temperature_c', FISHBOT_ALARM_ABOVE='30')
spec = importlib.util.spec_from_file_location('fishbot_backend', Path(__file__).resolve().parents[1] / 'backend' / 'server.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class BackendTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with closing(server.connect_db()):
            pass
        cls.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.url = 'http://127.0.0.1:' + str(cls.http.server_port)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        temp.cleanup()

    def request(self, data, token=None):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        req = urllib.request.Request(self.url + '/api/ingest', data=json.dumps(data).encode(), headers=headers, method='POST')
        return urllib.request.urlopen(req, timeout=3)

    def test_authentication_and_data(self):
        message = {'topic': 'ProTest/a', 'mqtt_connected': True, 'payload': {'device_id': 'simulated', 'data_source': 'simulation', 'temperature_c': 35}}
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request(message)
        self.assertEqual(error.exception.code, 401)
        with self.request(message, 'test-only-token') as result:
            self.assertEqual(result.status, 200)
        with urllib.request.urlopen(self.url + '/api/readings', timeout=3) as result:
            row = json.load(result)[0]
        self.assertEqual(row['payload']['data_source'], 'simulation')
        self.assertIn('threshold_alert', row['payload'])
        with urllib.request.urlopen(self.url + '/api/status', timeout=3) as result:
            self.assertTrue(json.load(result)['mqtt_connected'])

    def test_control_topic_is_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request({'topic': 'robot/control', 'mqtt_connected': True}, 'test-only-token')
        self.assertEqual(error.exception.code, 400)


if __name__ == '__main__':
    unittest.main()
