# Changelog

本项目的版本变更记录遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 的结构。

## [2.0.4] - 2026-08-12

### 修复

- 改为读取浏览器渲染后的好友动态并调用页面点赞按钮。
- 删除已失效的静态 HTML 解析和内部接口参数处理。

## [2.0.3] - 2026-08-12

### 修复

- 缺少本地驱动时直接下载，不再先等待 Selenium Manager 超时。

## [2.0.2] - 2026-08-12

### 修复

- Selenium Manager 无法获取驱动时，自动下载与本机 Chrome 主版本匹配的 ChromeDriver。
- 从 Windows 默认安装目录读取 Chrome 版本。

## [2.0.1] - 2026-08-12

### 变更

- 精简项目结构，将配置处理合并回两个主脚本。
- 删除额外的批处理入口和单元测试目录。
- README 改为中立的项目与使用说明。
- 命令行参数仅保留账号、间隔、单次检查和登录相关选项。

## [2.0.0] - 2026-08-12

### 新增

- 新增命令行参数，可直接设置 QQ 号、轮询间隔、登录方式和单次运行模式。
- 新增 `install.bat`、`start.bat` 和 `login.bat`，降低 Windows 首次使用门槛。
- 新增配置解析、令牌计算和响应解析的单元测试。

### 变更

- QQ 号改为首次运行时输入或通过 `--qq` 传入，不再需要修改两个 Python 文件。
- 使用 Selenium Manager 自动匹配 ChromeDriver，同时保留 `--driver` 手动指定能力。
- 使用当前虚拟环境的 Python 启动登录脚本。
- 默认轮询间隔调整为 30 秒，并为同一动态增加 5 分钟重试冷却。
- 登录等待改为显式超时，网络请求增加连接/读取超时和仅 GET 的有限重试。
- 点赞结果会解析服务端结果码，不再将所有 HTTP 200 响应视为成功。
- 配置写入改为原子替换，避免登录中断留下损坏的 JSON 文件。

### 安全

- 新增 `.gitignore`，默认排除 Cookie 配置、日志、虚拟环境和浏览器驱动。
- 日志只记录必要的状态信息，不输出 Cookie 或令牌内容。

[2.0.0]: https://github.com/help660vip/auto-liking-qzone-windows/releases/tag/v2.0.0
[2.0.1]: https://github.com/help660vip/auto-liking-qzone-windows/releases/tag/v2.0.1
[2.0.2]: https://github.com/help660vip/auto-liking-qzone-windows/releases/tag/v2.0.2
[2.0.3]: https://github.com/help660vip/auto-liking-qzone-windows/releases/tag/v2.0.3
[2.0.4]: https://github.com/help660vip/auto-liking-qzone-windows/releases/tag/v2.0.4
