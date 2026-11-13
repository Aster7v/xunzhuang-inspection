# 团队协作流程

1. 接受仓库邀请后，克隆仓库并先阅读 `README.md` 和 `MQTT使用教程.md`。
2. 从最新 `main` 创建自己的分支，例如 `feature/mqtt-status`，不要把密码、令牌、数据库、私钥、真实设备隐私数据放入仓库。
3. 只修改与任务有关的文件；本地运行 `python -m unittest discover -s tests`，并运行 `python -m py_compile backend/server.py gateway/biot_gateway.py gateway/ros2_mqtt_bridge.py`。
4. 推送分支并创建 Pull Request，说明改动、测试结果、是否涉及设备或服务器，以及仍未验证的部分。由另一位成员审阅后再合并。
5. 合并代码不会自动部署到阿里云。上线前确认授权、备份和回滚方案，检查服务及生产环境配置。

模拟数据必须标记为模拟；真实 ROS 2 话题和传感器字段必须以现场检查结果为准。未经专项测试与授权，不添加或启用机器人运动控制。

如发现凭据被提交，不要仅删除文件或提交来掩盖：立即联系仓库负责人，撤销或更换受影响的凭据，再评估历史记录清理。
