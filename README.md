# WhaleMai Next

Windows 桌面端通过麦麦的双向适配器接入微信。麦麦负责模型、人格、视觉、嵌入、记忆和对话调度。桌面端负责监听、前台发送、远程人工接管和可选 API 语音。

本项目是 Whale Girl 和 MaiBot 的非官方衍生项目。当前为预发布源码。请先阅读[安装与切换](docs/INSTALL.md)和[维护与验证](docs/MAINTENANCE.md)。

## 版本

| 组件 | 固定版本 |
| --- | --- |
| Whale Girl | [main ca5ad645](https://github.com/Banan1cee/whale_girl/commit/ca5ad645b71460ee9c17171ecee3f8be673f68d1)，在 4.1.7 标签后更新发行清单 |
| MaiBot | [1.4.5 / 478f671e](https://github.com/Mai-with-u/MaiBot/commit/478f671e64467121fd3e39205c8d3507b5ce0bd6) |
| MaiBot 插件 SDK | 2.23.0 |
| 原桥接来源 | [WhaleGirl-MaiBot-Bridge / c476157](https://github.com/Ts1ngyun/WhaleGirl-MaiBot-Bridge/commit/c4761579ee307e9d5ea47139f958d439113b2d2c) 与本地 4.1 迁移差异 |

## 功能边界

| 功能 | 当前源码 |
| --- | --- |
| 入站 | 精确会话 ID 白名单。文字、普通图片、表情过滤以及自动、`/识图` 请求或关闭模式 |
| 出站 | 前台文字、图片和表情。核对账号、窗口、会话及草稿。队列、接管和超时控制。一次发送尝试 |
| 自身消息 | 本账号文字作为非触发上下文同步。每条出站记录最多匹配一条 120 秒内同文消息，仍可能把先出现的主人同文误认为回声 |
| 手机端 | 独立随机 Key、逐会话接管、远程文字代发。仅监听回环，可由用户为该网页单独配置 HTTPS 隧道 |
| API 语音 | 小写 `/v`，会话和发言人绑定，180 秒内仅消费一次。群聊缺少发言人时会拒绝。支持 BreezeBlue、MiniMax、SiliconFlow 的 API |
| 范围外 | 朋友圈、日记、鲸鲸独立聊天及模型、搜索、主动问候、提醒、RVC 和本地音色权重 |

微信端需要已获授权提供的本地数据库凭据，以及微信自身对 Windows 暴露的可核验无障碍界面。程序不会读取微信进程来恢复数据库凭据，也不会写入微信进程激活 UIA。缺少这些条件的微信安装当前无法使用此预发布进行收发。微信 UI 自动化可能受平台限制。发送结果代表本机操作或观察结果，账号限制与服务端送达需独立确认。

## 许可

基于鲸鲸 / Whale Girl（@Banan1cee、@xmuzhou、@Muzi0336）修改，AGPL-3.0-only。麦麦及第三方依赖适用各自许可证。[署名与对应源码](NOTICE.md)。
