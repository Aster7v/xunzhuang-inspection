# FishBot 巡检项目台：后端联调

## 阿里云部署与 BIOT 网关

当前部署通过 `/fishbot/` 提供页面，页面/API 使用访问账号保护；`/fishbot/api/ingest` 使用独立 Bearer 令牌接收网关数据。BIOT 保持在可信局域网，网关使用 HTTPS 出站转发，参见 `gateway/README.md`。服务器未配置直接连接内网 Broker 的地址。默认不设置报警阈值，不提供控制功能。

此目录是可独立运行的后端雏形：接收 MQTT 遥测，存 SQLite，经只读 HTTP API 提供给页面；不包含 Broker、设备端固件、ROS 2 桥接、摄像头视频流或车辆控制。默认监听本机，公开部署前需配置 HTTPS、访问控制、Broker 认证/授权和数据保护，并确认赛道要求。

## 本地启动（Ubuntu / Python 3）

在项目根目录：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
export MQTT_HOST=127.0.0.1
export MQTT_PORT=1883
export MQTT_TOPIC=fishbot/esp32/telemetry
python backend/server.py
```

在同一台电脑打开 `http://127.0.0.1:8000`。需另行安装并配置 MQTT Broker；以上地址仅用于 Broker 和后端同机的例子，板子填写的地址应是它能访问到的 Broker 地址。未配置 `MQTT_HOST` 时仍可启动页面和 API，MQTT 状态显示未配置。

允许用环境变量 `MQTT_USERNAME` / `MQTT_PASSWORD` 配置账号；`MQTT_TLS=true` 启用 TLS 和系统 CA 校验。不要把密码写入页面、源代码或版本库。

## 消息约定（联调用示例，非既定设备协议）

ESP32 向配置的主题发布 UTF-8 JSON 对象，例如：

```json
{"device_id":"esp32-extra","pir":1,"note":"test"}
```

仅接受不超过 4096 字节的扁平 JSON 对象；最大保留最近 5000 条。时间由服务端记录。数据原样展示，不表示硬件、传感器或 ROS 2 已经接好，也不对报警做安全判断。请结合实物确认字段、单位、采样频率和主题后修改固件。

## 页面与 API

- `GET /api/status`：后端和 MQTT 连接状态，已接收消息的最新时间。
- `GET /api/readings`：最近 30 条记录。
- 前后端同一域名最简单。若页面与 API 分离，设置 `CORS_ORIGIN` 为页面的完整来源（例如 `https://example.com`），浏览器页面填入 API 地址。HTTPS 页面不能直接访问 HTTP API。

没有认证的 API 仅适合可信网络中的联调。公开部署时应通过反向代理实现登录认证、TLS、限流和备份，限制数据库访问；Broker 使用账号、ACL、TLS，不应开放匿名公网访问。当前无真实控制指令，不支持操作小车；要增加控制需单独设计授权、超时、急停和现场安全机制。
