# QZone Auto Liker

一个在 Windows 上运行的 QQ 空间好友动态自动点赞脚本。

程序使用 Selenium 打开 Chrome 完成登录并保存 Cookie，随后使用 Requests 读取好友动态和提交点赞。登录信息只保存在本地 `config.json`。

## 功能

- 自动检查好友动态并为未点赞的动态点赞
- 支持浏览器已保存账号和手动扫码登录
- Cookie 失效时重新打开浏览器登录
- 支持指定轮询间隔或只检查一次
- 自动使用 Selenium Manager 匹配 ChromeDriver，也可以指定本地驱动

## 环境要求

- Windows 10 或 Windows 11
- Python 3.9 或更高版本
- Google Chrome

## 安装

在项目目录打开 PowerShell 或命令提示符：

```powershell
python -m pip install -r requirements.txt
```

## 使用

首次运行时指定 QQ 号：

```powershell
python main.py --qq 123456789
```

把 `123456789` 换成自己的 QQ 号。浏览器登录成功后会生成 `config.json`，以后直接运行：

```powershell
python main.py
```

手动扫码登录：

```powershell
python ck.py --qq 123456789 --manual
```

其他用法：

```powershell
# 每 60 秒检查一次
python main.py --interval 60

# 只检查一次
python main.py --once

# 使用本地 ChromeDriver
python ck.py --driver C:\tools\chromedriver.exe --manual
```

查看完整参数：

```powershell
python main.py --help
python ck.py --help
```

## 文件说明

| 文件 | 说明 |
| --- | --- |
| `main.py` | 检查动态并提交点赞 |
| `ck.py` | 登录 QQ 空间并保存 Cookie |
| `requirements.txt` | Python 依赖 |
| `config.json` | 登录信息，首次登录后生成 |
| `app.log` | 运行日志 |

## 注意事项

- `config.json` 包含 Cookie，不要发送给他人或提交到 Git。
- QQ 空间页面和接口可能发生变化，脚本届时需要相应调整。
- 自动化操作可能触发账号限制，请控制使用频率。
- 本项目仅用于学习和个人测试，使用者需要自行遵守相关服务条款。

版本记录见 [CHANGELOG.md](CHANGELOG.md)。
