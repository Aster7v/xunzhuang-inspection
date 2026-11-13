# 巡桩问诊 MQTT 出站网关

BIOT 仅在可信局域网运行。网关订阅一个明确的遥测主题，通过 HTTPS 和服务器签发的令牌向网站转发，不开放 MQTT 端口，也不订阅或发送车辆控制指令。默认每 15 秒发送连接心跳；断线重连由 Paho 执行。最多缓存 200 条，满队列可能丢失消息，不能用作安全联锁。

安装 `paho-mqtt>=2.1,<3`，设置 `BIOT_HOST`（本机或可信内网地址）、可选 `BIOT_PORT`、`BIOT_TOPIC`、`FISHBOT_INGEST_URL` 和 `FISHBOT_INGEST_TOKEN`，运行 `python gateway/biot_gateway.py`。不要提交令牌或在网页中填写令牌。默认来源 `unverified_device`，仅测试时设置 `FISHBOT_DATA_SOURCE=simulation`。消息必须为 UTF-8 扁平 JSON，最多 4096 字节；显示为上报数据，不等同于认证的真实设备。

原有约定主题为 `fishbot/esp32/telemetry`；现场也可明确配置 `ProTest/a` 或 `ProTest/b`。两端必须使用相同的主题。本地 BIOT 的地址由现场确认，不写入云服务器配置。

`ros2_mqtt_bridge.py` 为只读桥，必须由现场根据 `ros2 topic list`、`ros2 topic info -v` 和消息定义明确传入 ROS 话题、消息类型、字段映射、BIOT 地址、MQTT 遥测主题及设备标识；不会推测或发布运动指令。仅支持有限长度的标量字段。真实 ROS 2 和硬件尚未验证。

可在服务器配置 `FISHBOT_ALARM_FIELD` 和 `FISHBOT_ALARM_ABOVE` 为某个已确认的数值字段配置大于阈值提醒；默认关闭。提醒不构成安全认证，也不能代替独立安全保护。
