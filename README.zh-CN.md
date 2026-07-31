# FluxDL

[English](README.md) · [简体中文](README.zh-CN.md)

FluxDL 是一个基于 [yt-dlp](https://github.com/yt-dlp/yt-dlp) 的私密、本地优先 Web 视频下载器。你可以在浏览器中解析和下载 yt-dlp 支持的视频，并在本机生成、翻译字幕。

> [!IMPORTANT]
> 请仅下载你拥有权利或已获授权保存的内容，并遵守来源网站的服务条款及适用法律。

## 功能

- 解析视频标题、封面、时长、发布者和可用清晰度。
- 下载最佳画质，或指定 4K、2K、1080p、720p、480p。
- 视频支持 MP4、MKV；音频支持 MP3、M4A、Opus、WAV。
- 实时显示进度、速度、剩余时间，并可取消下载任务。
- 可选下载已有字幕、嵌入视频封面。
- 使用 Faster-Whisper 为无字幕视频在本机生成字幕。
- 使用 Argos Translate 离线翻译为简体中文。
- 输出 SRT，或生成带可开关字幕轨道的 MKV。
- 下载历史、模型、媒体文件和处理状态都保存在本机。
- 默认仅监听 `127.0.0.1`。

## 环境要求

- Python 3.10 或更高版本
- 推荐安装 [uv](https://docs.astral.sh/uv/)
- [FFmpeg](https://ffmpeg.org/)：用于合并高画质音视频、提取音频、嵌入封面和生成 AI 字幕

安装 FFmpeg：

```bash
# macOS
brew install ffmpeg

# Ubuntu / Debian
sudo apt install ffmpeg

# Windows
winget install Gyan.FFmpeg
```

## 快速开始

### macOS 和 Linux

```bash
git clone git@github.com:yuege969/FluxDL.git
cd fluxdl
chmod +x start.sh
./start.sh
```

启动脚本会优先使用 `uv`；如果没有安装，则自动创建 `.venv` 并通过 `pip` 安装项目。

### Windows

```powershell
git clone git@github.com:yuege969/FluxDL.git
cd fluxdl
py -m venv .venv
.\.venv\Scripts\python -m pip install --editable .
.\.venv\Scripts\fluxdl
```

服务启动后访问 [http://127.0.0.1:8765](http://127.0.0.1:8765)。

## AI 字幕

在已完成的视频任务中选择“AI 字幕”，FluxDL 可以生成：

- 原语言 SRT；
- 简体中文 SRT；
- 中英双语 SRT；
- 带可开关字幕轨道的 MKV 副本。

可选 Faster-Whisper 模型：

| 模型 | 约需下载 | 说明 |
| --- | ---: | --- |
| Tiny | 75 MB | 速度最快，精度较低 |
| Base | 145 MB | 默认选择，速度和精度均衡 |
| Small | 460 MB | 精度更高，速度较慢 |

首次使用会下载所选语音模型。中文或双语输出还需要 Argos Translate 语言包。模型就绪后，转写和翻译均在本机运行，FluxDL 不会上传提取出的音频。

## 配置

可参考 `.env.example`，或在启动前设置以下环境变量：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `FLUXDL_HOST` | `127.0.0.1` | HTTP 监听地址 |
| `FLUXDL_PORT` | `8765` | HTTP 监听端口 |
| `FLUXDL_HOME` | 当前目录 | 运行数据和模型根目录 |
| `FLUXDL_DOWNLOAD_DIR` | `<FLUXDL_HOME>/downloads` | 下载保存目录 |

示例：

```bash
FLUXDL_PORT=9000 FLUXDL_DOWNLOAD_DIR="$HOME/Downloads" ./start.sh
```

设置 `FLUXDL_HOST=0.0.0.0` 后，局域网设备可以访问此应用。FluxDL 尚未提供身份验证，因此只建议在可信网络中这样做。

## 项目结构

```text
.
├── src/fluxdl/
│   ├── server.py              # HTTP 服务、yt-dlp 任务和 API
│   ├── subtitle_engine.py     # 本地转写和翻译
│   └── static/                # 浏览器页面
├── tests/                     # 单元测试
├── downloads/                 # 本地媒体文件（Git 忽略）
├── .data/                     # 运行历史和临时音频
├── .models/                   # 本地语音模型
├── pyproject.toml             # 包信息和依赖
└── start.sh                   # macOS/Linux 启动脚本
```

## 开发

```bash
uv sync
uv run python -m unittest discover -s tests -v
uv run fluxdl
```

前端使用原生 HTML、CSS 和 JavaScript，不需要单独构建。

## 安全与隐私

FluxDL 面向单用户本地运行，并不是可直接公开部署的加固服务。除非清楚了解风险，否则请保留默认的本机监听地址。漏洞报告方式见 [SECURITY.md](SECURITY.md)。

## 参与贡献

欢迎贡献。提交 Issue 或 Pull Request 前，请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 致谢

FluxDL 使用了 [yt-dlp](https://github.com/yt-dlp/yt-dlp)、[Faster-Whisper](https://github.com/SYSTRAN/faster-whisper)、[Argos Translate](https://github.com/argosopentech/argos-translate) 和 [FFmpeg](https://ffmpeg.org/)。FluxDL 是独立项目，与这些项目及受支持网站均无隶属关系。

## 许可证

本项目使用 [MIT License](LICENSE)。
