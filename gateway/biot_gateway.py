"""Outbound-only BIOT MQTT to HTTPS gateway. Never subscribes to control topics."""
import ipaddress
import json
import os
import queue
import socket
import threading
import time
import urllib.request
import urllib.error
from urllib.parse import urlparse

import paho.mqtt.client as mqtt

host = os.environ.get('BIOT_HOST', '')
topic = os.environ.get('BIOT_TOPIC', 'fishbot/esp32/telemetry')
endpoint = os.environ.get('FISHBOT_INGEST_URL', '')
token = os.environ.get('FISHBOT_INGEST_TOKEN', '')
source = os.environ.get('FISHBOT_DATA_SOURCE', 'unverified_device')
if not host or not endpoint or not token or source not in ('simulation', 'unverified_device'):
    raise SystemExit('Set BIOT_HOST, FISHBOT_INGEST_URL, FISHBOT_INGEST_TOKEN and valid FISHBOT_DATA_SOURCE')
if urlparse(endpoint).scheme != 'https':
    raise SystemExit('HTTPS is required')
if any(not (ipaddress.ip_address(row[4][0]).is_private or ipaddress.ip_address(row[4][0]).is_loopback) for row in socket.getaddrinfo(host, None)):
    raise SystemExit('BIOT must resolve only to private or loopback addresses')
if any(c in topic for c in ('+', '#')) or not topic or 'control' in topic.lower():
    raise SystemExit('Use one explicit telemetry topic; control topics are not supported')

messages = queue.Queue(maxsize=200)
connected = threading.Event()
opener = urllib.request.build_opener() if os.environ.get('FISHBOT_USE_SYSTEM_PROXY') == '1' else urllib.request.build_opener(urllib.request.ProxyHandler({}))

def send(payload=None):
    packet = {'topic': topic, 'mqtt_connected': connected.is_set()}
    if payload is not None:
        packet['payload'] = payload
    request = urllib.request.Request(endpoint, data=json.dumps(packet, allow_nan=False).encode(), headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token}, method='POST')
    with opener.open(request, timeout=8) as response:
        return response.status == 200

def worker():
    while True:
        try:
            payload = messages.get(timeout=15)
        except queue.Empty:
            payload = None
        try:
            send(payload)
            if payload is not None:
                messages.task_done()
        except urllib.error.HTTPError as exc:
            print('Gateway rejected message:', exc.code, flush=True)
            if payload is not None:
                messages.task_done()
                if exc.code >= 500:
                    try: messages.put_nowait(payload)
                    except queue.Full: pass
            time.sleep(3)
        except Exception as exc:
            print('Gateway delivery failed:', type(exc).__name__, flush=True)
            if payload is not None:
                messages.task_done()
                try: messages.put_nowait(payload)
                except queue.Full: print('Gateway queue full; message dropped', flush=True)
            time.sleep(3)

def on_connect(client, userdata, flags, reason_code, properties):
    if not reason_code.is_failure:
        connected.set()
        client.subscribe(topic, qos=1)
    else:
        connected.clear()
    print('MQTT:', 'connected' if connected.is_set() else 'connection rejected', flush=True)

def on_disconnect(client, userdata, flags, reason_code, properties):
    connected.clear()
    print('MQTT disconnected; reconnecting', flush=True)

def on_message(client, userdata, message):
    try:
        if len(message.payload) > 4096: return
        payload = json.loads(message.payload.decode('utf-8'))
        if not isinstance(payload, dict): return
        payload['data_source'] = source
        json.dumps(payload, allow_nan=False)
        messages.put_nowait(payload)
    except (ValueError, UnicodeError, queue.Full):
        print('Invalid message or queue full; ignored', flush=True)

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect, client.on_disconnect, client.on_message = on_connect, on_disconnect, on_message
client.reconnect_delay_set(1, 30)
threading.Thread(target=worker, daemon=True).start()
client.connect_async(host, int(os.environ.get('BIOT_PORT', '1883')), 60)
client.loop_forever(retry_first_connection=True)
