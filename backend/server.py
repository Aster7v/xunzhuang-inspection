"""FishBot telemetry gateway: MQTT -> SQLite -> read-only HTTP API + frontend."""
import io
import hmac
import json
import os
import re
import sqlite3
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
DB = os.environ.get('FISHBOT_DB', str(ROOT / 'fishbot.sqlite3'))
TOPIC = os.environ.get('MQTT_TOPIC', 'fishbot/esp32/telemetry')
HOST = os.environ.get('MQTT_HOST', '')
PORT = int(os.environ.get('MQTT_PORT', '1883'))
ORIGIN = os.environ.get('CORS_ORIGIN', '')
status = {'mqtt_connected': False, 'last_message_at': None, 'last_error': None}
INGEST_TOKEN = os.environ.get('FISHBOT_INGEST_TOKEN', '')
ALARM_FIELD = os.environ.get('FISHBOT_ALARM_FIELD', '')
ALARM_ABOVE = os.environ.get('FISHBOT_ALARM_ABOVE', '')
gateway = {'seen': 0, 'mqtt_connected': False, 'topic': None}
lock = threading.Lock()

def connect_db():
    db = sqlite3.connect(DB, timeout=10)
    db.execute('CREATE TABLE IF NOT EXISTS readings (id INTEGER PRIMARY KEY, received_at INTEGER NOT NULL, topic TEXT NOT NULL, payload TEXT NOT NULL)')
    return db

def record_message(topic, body, forwarded=False):
    if (not forwarded and topic != TOPIC) or len(body) > 4096:
        return False
    try:
        data = json.loads(body.decode('utf-8'))
        if not isinstance(data, dict) or len(data) > 30:
            return False
        if not forwarded:
            data['data_source'] = 'unverified_device'
        data.pop('threshold_alert', None)
        if ALARM_FIELD and ALARM_ABOVE and isinstance(data.get(ALARM_FIELD), (int, float)) and not isinstance(data.get(ALARM_FIELD), bool):
            if data[ALARM_FIELD] > float(ALARM_ABOVE):
                data['threshold_alert'] = f'{ALARM_FIELD} 超过已配置阈值 {ALARM_ABOVE}'
        if any(not isinstance(k, str) or len(k) > 64 or not (v is None or isinstance(v, (str, int, float, bool))) or (isinstance(v, str) and len(v) > 200) for k, v in data.items()):
            return False
        encoded = json.dumps(data, ensure_ascii=False, allow_nan=False)
    except (UnicodeError, ValueError, TypeError):
        return False
    now = int(time.time())
    with connect_db() as db:
        db.execute('INSERT INTO readings(received_at,topic,payload) VALUES(?,?,?)', (now, topic, encoded))
        db.execute('DELETE FROM readings WHERE id NOT IN (SELECT id FROM readings ORDER BY id DESC LIMIT 5000)')
    with lock:
        status['last_message_at'] = now
    return True

def start_mqtt():
    if not HOST:
        status['last_error'] = '尚未配置 MQTT_HOST'
        return
    try:
        import paho.mqtt.client as mqtt
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if os.environ.get('MQTT_USERNAME'):
            client.username_pw_set(os.environ['MQTT_USERNAME'], os.environ.get('MQTT_PASSWORD', ''))
        if os.environ.get('MQTT_TLS', '').lower() in ('1', 'true', 'yes'):
            client.tls_set()
        def on_connect(client, userdata, flags, reason_code, properties):
            with lock:
                status['mqtt_connected'] = not reason_code.is_failure
                status['last_error'] = None if not reason_code.is_failure else 'MQTT 连接被拒绝'
            if not reason_code.is_failure:
                client.subscribe(TOPIC, qos=1)
        def on_disconnect(client, userdata, flags, reason_code, properties):
            with lock:
                status['mqtt_connected'] = False
                status['last_error'] = 'MQTT 已断开，正在尝试重新连接'
        def on_message(client, userdata, msg):
            record_message(msg.topic, msg.payload)
        client.on_connect, client.on_disconnect, client.on_message = on_connect, on_disconnect, on_message
        client.reconnect_delay_set(min_delay=1, max_delay=30)
        status['last_error'] = '等待 MQTT 连接'
        client.connect_async(HOST, PORT, 60)
        client.loop_start()
        return client
    except Exception as exc:
        status['last_error'] = 'MQTT 初始化失败：' + type(exc).__name__

class Handler(BaseHTTPRequestHandler):
    def respond(self, code, body, content_type='application/json; charset=utf-8'):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if ORIGIN and self.headers.get('Origin') == ORIGIN:
            self.send_header('Access-Control-Allow-Origin', ORIGIN)
            self.send_header('Vary', 'Origin')
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/api/status':
            with lock:
                snapshot = dict(status)
                age = time.time() - gateway['seen']
                if gateway['seen'] and age < 45:
                    snapshot.update(mqtt_connected=gateway['mqtt_connected'], topic=gateway['topic'], gateway_online=True, last_error=None)
                else:
                    snapshot['gateway_online'] = False
            snapshot.update({'backend': 'online', 'topic': TOPIC, 'mqtt_configured': bool(HOST), 'server_time': int(time.time())})
            if snapshot['gateway_online']:
                snapshot.update(topic=gateway['topic'], mqtt_configured=True)
            elif gateway['seen']:
                snapshot.update(mqtt_configured=True, last_error='网关超时或离线，等待重新连接')
            self.respond(200, json.dumps(snapshot, ensure_ascii=False).encode())
        elif path == '/api/readings':
            with connect_db() as db:
                rows = db.execute('SELECT received_at, topic, payload FROM readings ORDER BY id DESC LIMIT 30').fetchall()
            data = [{'received_at': t, 'topic': topic, 'payload': json.loads(payload)} for t, topic, payload in rows]
            self.respond(200, json.dumps(data, ensure_ascii=False).encode())
        elif path == '/fishbot-server-kit.zip':
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as archive:
                for name in ('dist/index.html', 'backend/server.py', 'backend/requirements.txt', 'backend/README.md', 'gateway/biot_gateway.py', 'gateway/ros2_mqtt_bridge.py', 'gateway/README.md'):
                    archive.write(ROOT / name, name)
            self.respond(200, buf.getvalue(), 'application/zip')
        elif path in ('/', '/index.html'):
            self.respond(200, (ROOT / 'dist' / 'index.html').read_bytes(), 'text/html; charset=utf-8')
        else:
            self.respond(404, b'{"error":"not found"}')
    def do_POST(self):
        if urlparse(self.path).path != '/api/ingest':
            self.respond(404, b'{"error":"not found"}'); return
        auth = self.headers.get('Authorization', '')
        if not INGEST_TOKEN or not hmac.compare_digest(auth, 'Bearer ' + INGEST_TOKEN):
            self.respond(401, b'{"error":"unauthorized"}'); return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 8192: raise ValueError()
            envelope = json.loads(self.rfile.read(size))
            if not isinstance(envelope, dict): raise ValueError()
            topic = envelope.get('topic')
            connected = envelope.get('mqtt_connected')
            if not isinstance(topic, str) or not re.fullmatch(r'[A-Za-z0-9_/-]{1,128}', topic) or 'control' in topic.lower() or not isinstance(connected, bool): raise ValueError()
            if 'payload' in envelope:
                payload = envelope['payload']
                if not isinstance(payload, dict) or payload.get('data_source') not in ('simulation', 'unverified_device'): raise ValueError()
                if not record_message(topic, json.dumps(payload, ensure_ascii=False, allow_nan=False).encode(), forwarded=True): raise ValueError()
            with lock:
                gateway.update(seen=time.time(), mqtt_connected=connected, topic=topic)
            self.respond(200, b'{"ok":true}')
        except (ValueError, TypeError, UnicodeError):
            self.respond(400, b'{"error":"invalid message"}')
    def log_message(self, format, *args):
        pass

def main():
    with connect_db():
        pass
    client = start_mqtt()
    host = os.environ.get('HTTP_HOST', '127.0.0.1')
    port = int(os.environ.get('HTTP_PORT', '8000'))
    print(f'FishBot service listening on {host}:{port}', flush=True)
    try:
        ThreadingHTTPServer((host, port), Handler).serve_forever()
    finally:
        if client:
            client.loop_stop()
            client.disconnect()

if __name__ == '__main__':
    main()
