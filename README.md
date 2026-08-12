# QZone Auto Liker

一个在 Windows 上运行的 QQ 空间好友动态自动点赞脚本。浏览器只用于完成登录并获取 Cookie；登录后，程序通过 HTTP 请求轮询动态和提交点赞。

当前版本为 `2.0.0`。这一版不再要求修改源码中的 QQ 号，并补上了请求超时、失败重试冷却、登录超时和点赞结果校验。

> QQ 空间页面和接口并非公开 API，腾讯调整页面结构后脚本可能暂时失效。自动化操作也可能触发账号风控，请先阅读下方的使用边界。

## 功能

- 首次运行输入 QQ 号，后续从本地配置自动读取。
- 支持浏览器已保存账号的自动点击，也支持手动扫码登录。
- Selenium Manager 自动匹配 ChromeDriver；也可以使用本地驱动。
- Cookie 失效后重新打开浏览器登录。
- GET 请求使用有限重试；点赞 POST 不自动重放，避免重复操作。
- 同一条动态默认 5 分钟内不重复尝试。
- 支持只运行一轮，方便配合 Windows 任务计划程序。

## 运行条件

- Windows 10 或 Windows 11
- Python 3.9 或更高版本
- Google Chrome

## 快速开始

下载项目后，在项目目录依次运行：

```bat
install.bat
start.bat --qq 123456789
```

把 `123456789` 换成你的 QQ 号。首次运行会打开 Chrome：如果浏览器保存了账号，程序会尝试自动点击；否则直接在浏览器中扫码或手动登录。成功后凭据保存在本地 `config.json`，以后可以直接运行：

```bat
start.bat
```

`config.json` 包含账号 Cookie，已经被 `.gitignore` 排除。不要把它发给别人，也不要手动提交到 Git。

### 强制手动登录

如果不希望程序自动点击已保存的账号：

```bat
login.bat --qq 123456789
start.bat
```

也可以在启动主程序时使用：

```bat
start.bat --qq 123456789 --manual-login
```

### 不使用批处理文件

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py --qq 123456789
```

不需要激活虚拟环境，因此不会受到 PowerShell 执行策略影响。

## 常用参数

查看全部参数：

```bat
start.bat --help
```

常见用法：

```bat
:: 只检查一轮后退出
start.bat --once

:: 每 60 秒左右检查一次
start.bat --interval 60 --jitter 10

:: 手动指定 ChromeDriver
.venv\Scripts\python.exe ck.py --driver C:\tools\chromedriver.exe --manual

:: Chrome 通过本地代理访问网络
.venv\Scripts\python.exe ck.py --proxy http://127.0.0.1:7890 --manual
```

主要参数：

| 参数 | 默认值 | 说明 |
| --- | ---: | --- |
| `--qq` | 本地配置 | 首次运行的 QQ 号 |
| `--interval` | 30 秒 | 两轮检查之间的基础间隔 |
| `--jitter` | 5 秒 | 每轮额外随机等待的上限 |
| `--retry-delay` | 300 秒 | 同一动态再次尝试前的冷却时间 |
| `--once` | 关闭 | 只检查一次，适合任务计划 |
| `--manual-login` | 关闭 | 登录时不自动点击账号 |
| `--no-log-file` | 关闭 | 只输出到终端，不写 `app.log` |

## 项目结构

| 文件 | 作用 |
| --- | --- |
| `main.py` | 轮询动态、校验登录状态并提交点赞 |
| `ck.py` | 打开 Chrome 完成登录并保存 Cookie |
| `qzone_utils.py` | 配置校验、g_tk 计算和响应解析 |
| `tests/` | 不依赖网络的单元测试 |
| `install.bat` | 创建虚拟环境并安装依赖 |
| `start.bat` | 使用项目虚拟环境启动主程序 |
| `login.bat` | 使用手动模式刷新登录状态 |
| `config.json` | 本地登录凭据，运行后生成且不会提交 |
| `app.log` | 运行日志，不会提交 |

## 测试

```bat
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

测试不访问 QQ 空间，也不需要真实 Cookie。

## 使用边界

- 仅用于学习、个人测试和维护自己的账号。
- 不要提高请求频率、批量控制账号或用于骚扰他人。
- Cookie 等同于登录凭据；一旦泄露，请立即在 QQ 安全中心退出相关登录。
- 使用者需要自行遵守腾讯的服务条款并承担账号限制等风险。

版本变化见 [CHANGELOG.md](CHANGELOG.md)。遇到问题时，请附上 Python 版本、Chrome 版本和去除敏感信息后的日志。
