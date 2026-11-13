"""Read-only ROS 2 -> local BIOT bridge; all topics/types/fields are explicit."""
import argparse
import ipaddress
import json
import math
import socket
import time

import paho.mqtt.client as mqtt
import rclpy
from rclpy.node import Node
from rosidl_runtime_py.utilities import get_message

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--ros-topic', required=True)
parser.add_argument('--ros-type', required=True, help='e.g. package/msg/Type, confirmed from the running robot')
parser.add_argument('--field', action='append', required=True, help='output_name=dot.separated.ros.field; repeat for each field')
parser.add_argument('--biot-host', required=True)
parser.add_argument('--biot-port', type=int, default=1883)
parser.add_argument('--mqtt-topic', required=True)
parser.add_argument('--device-id', required=True)
args = parser.parse_args()
if any(not (ipaddress.ip_address(x[4][0]).is_private or ipaddress.ip_address(x[4][0]).is_loopback) for x in socket.getaddrinfo(args.biot_host, None)):
    raise SystemExit('BIOT must be on a trusted private network')
if any(c in args.mqtt_topic for c in ('+', '#')) or 'control' in args.mqtt_topic.lower():
    raise SystemExit('Only one explicit telemetry topic is allowed')
fields = []
for pair in args.field:
    key, sep, path = pair.partition('=')
    if not sep or not key.isidentifier() or not all(p.isidentifier() for p in path.split('.')):
        raise SystemExit('Invalid field mapping')
    fields.append((key, path.split('.')))

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.reconnect_delay_set(1, 30)
client.connect_async(args.biot_host, args.biot_port, 60)
client.loop_start()

class Bridge(Node):
    def __init__(self):
        super().__init__('fishbot_readonly_mqtt_bridge')
        self.create_subscription(get_message(args.ros_type), args.ros_topic, self.receive, 10)
        self.last_publish = 0.0
    def receive(self, msg):
        if time.monotonic() - self.last_publish < 0.2:
            return
        data = {'device_id': args.device_id}
        try:
            for key, path in fields:
                value = msg
                for part in path:
                    value = getattr(value, part)
                if not isinstance(value, (str, int, float, bool)) or isinstance(value, float) and not math.isfinite(value):
                    raise ValueError('only finite scalar values are supported')
                data[key] = value
            client.publish(args.mqtt_topic, json.dumps(data, allow_nan=False), qos=1)
            self.last_publish = time.monotonic()
        except (AttributeError, ValueError) as exc:
            self.get_logger().error('Field mapping error: ' + str(exc))

rclpy.init()
node = Bridge()
try:
    rclpy.spin(node)
finally:
    node.destroy_node()
    rclpy.shutdown()
    client.loop_stop()
    client.disconnect()
