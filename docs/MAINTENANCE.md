# 维护与验证

- `desktop.py` 管理配置与生命周期。 `hub.py` 管理队列、消息身份与授权。 `remote_console.py` 提供独立回环网页。
- `plugin/` 是可独立打包的麦麦适配器，根目录包含 `_manifest.json`、`plugin.py`、`LICENSE`。安装只修改目标 Bot 的插件目录。生命周期与归属遵循 [消息网关规范](https://docs.maibot.chat/develop/plugin/message-gateway)。未来投稿需要独立插件仓库及其 Release，按 [投稿流程](https://docs.maibot.chat/develop/plugin/submission) 提交。
- `upstream-overlay/` 给出鲸鲸固定基线的完整改动文件。`Prepare-Source.ps1` 重建工作目录，编译语音只依赖 `voice-worker/` 及指定的上游音频源文件。`relay.lock.txt` 与 `maibot.lock.txt` 固定 Windows x64 Python 依赖版本。
- 基于 2026-11-17 的移植改动包括异步 Webhook、图文转发、自身文字观察、播放器和麦克风执行闸、前台一次发送、禁用进程内存写入、限定本地数据库凭据，以及排除原版的主动行为。更新上游时对照这些语义重新移植，保留接收和执行层的检查。

## 验证

```powershell
.\.venv\Scripts\python.exe -m unittest test_relay test_remote test_emoji
.\.venv\Scripts\python.exe smoke_local.py
```

队列测试使用合成消息和临时数据库。启动测试仅启动此实例的 Node 与麦麦宿主，检查微信 webhook 拒绝未认证请求，以及麦麦管理地址正常响应和两个子进程退出。麦麦 1.4.5 manifest 校验器验证了插件结构。桌面界面已检查启动和关闭，语音工作进程在两个不同目录构建后取得相同 SHA-256，并确认无任务参数时退出。实际 Bot 使用模型、原生微信 UIA、前台送达、Windows 录音与虚拟声卡仍需单独验证。

## 发布维护

使用 `build_source.py` 的路径白名单生成源码包及插件包。用户数据、模型、运行时、账号标识、上游品牌图标和可执行文件均不进入这些包。核对包清单和 SHA-256，并保留上游通知。Python 与 NuGet 依赖由用户依照各自条款安装。受控测试发现操作结果不确定时，先人工检查目标会话及草稿，再决定后续操作。
