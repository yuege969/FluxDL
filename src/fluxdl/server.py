from __future__ import annotations

import argparse
import importlib.util
import json
import mimetypes
import os
import re
import shutil
import sys
import threading
import time
import traceback
import urllib.parse
import uuid
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .subtitle_engine import SubtitleJob, run_subtitle_job as execute_subtitle_job


PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = Path(os.environ.get("FLUXDL_HOME", Path.cwd())).expanduser().resolve()
PUBLIC_DIR = PACKAGE_ROOT / "static"
DOWNLOAD_DIR = Path(
    os.environ.get("FLUXDL_DOWNLOAD_DIR", PROJECT_ROOT / "downloads")
).expanduser().resolve()
DATA_DIR = PROJECT_ROOT / ".data"
HISTORY_FILE = DATA_DIR / "history.json"
SUBTITLE_HISTORY_FILE = DATA_DIR / "subtitle_jobs.json"
SUBTITLE_MODEL_DIR = PROJECT_ROOT / ".models" / "whisper"
SUBTITLE_WORK_DIR = DATA_DIR / "subtitle_audio"
MAX_BODY_SIZE = 64 * 1024
URL_PATTERN = re.compile(r"^https?://", re.IGNORECASE)
TASKS_LOCK = threading.RLock()
TASKS: dict[str, "DownloadTask"] = {}
SUBTITLE_LOCK = threading.RLock()
SUBTITLE_JOBS: dict[str, SubtitleJob] = {}


def valid_remote_url(value: str) -> bool:
    if not isinstance(value, str) or not URL_PATTERN.match(value.strip()):
        return False
    try:
        parsed = urllib.parse.urlparse(value.strip())
        return bool(parsed.netloc) and parsed.scheme in {"http", "https"}
    except ValueError:
        return False


def clean_error(message: object) -> str:
    text = re.sub(r"\x1b\[[0-9;]*m", "", str(message)).strip()
    text = re.sub(r"^ERROR:\s*", "", text, flags=re.IGNORECASE)
    return text[-600:] or "下载失败，请检查链接后重试。"


def is_ssl_disconnect(message: object) -> bool:
    text = str(message).lower()
    markers = (
        "unexpected_eof_while_reading",
        "eof occurred in violation of protocol",
        "ssl: unexpected eof",
        "connection reset by peer",
    )
    return any(marker in text for marker in markers)


def is_subtitle_rate_limit(message: object) -> bool:
    text = str(message).lower()
    return ("subtitle" in text or "subtitles" in text) and ("http error 429" in text or "too many requests" in text)


def enable_curl_fallback(options: dict[str, Any]) -> None:
    options["external_downloader"] = {"http": "curl", "https": "curl"}
    options["external_downloader_args"] = {
        "curl": [
            "--retry",
            "10",
            "--retry-all-errors",
            "--retry-delay",
            "2",
            "--connect-timeout",
            "30",
        ]
    }


def disable_subtitles(options: dict[str, Any]) -> None:
    for key in ("writesubtitles", "writeautomaticsub", "subtitleslangs", "subtitlesformat"):
        options.pop(key, None)


def ytdlp_version() -> str | None:
    try:
        import yt_dlp.version

        return yt_dlp.version.__version__
    except Exception:
        return None


def format_options(mode: str, quality: str, container: str, subtitles: bool, thumbnail: bool) -> dict[str, Any]:
    has_ffmpeg = bool(shutil.which("ffmpeg"))
    common: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "restrictfilenames": False,
        "windowsfilenames": os.name == "nt",
        "overwrites": False,
        "continuedl": True,
        "outtmpl": str(DOWNLOAD_DIR / "%(title).180B [%(id)s].%(ext)s"),
        "socket_timeout": 30,
        "retries": 12,
        "fragment_retries": 12,
        "extractor_retries": 5,
        "file_access_retries": 5,
        "concurrent_fragment_downloads": 1,
        "http_chunk_size": 10 * 1024 * 1024,
    }

    if mode == "audio":
        codec = container if container in {"mp3", "m4a", "opus", "wav"} else "mp3"
        common["format"] = "bestaudio/best"
        common["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": codec,
                "preferredquality": "0" if codec != "mp3" else "320",
            }
        ]
    else:
        height = quality if quality in {"2160", "1440", "1080", "720", "480", "360"} else None
        limit = f"[height<={height}]" if height else ""
        if not has_ffmpeg:
            common["format"] = f"b{limit}[ext=mp4]/b{limit}"
        elif container == "mp4":
            common["format"] = (
                f"bv*{limit}[ext=mp4]+ba[ext=m4a]/"
                f"b{limit}[ext=mp4]/bv*{limit}+ba/b{limit}"
            )
            common["merge_output_format"] = "mp4"
        else:
            common["format"] = f"bv*{limit}+ba/b{limit}"
            common["merge_output_format"] = "mkv"

    if subtitles:
        common.update(
            {
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": ["zh-Hans", "zh-Hant", "zh", "en"],
                "subtitlesformat": "best",
            }
        )

    if thumbnail:
        common["writethumbnail"] = True
        common.setdefault("postprocessors", []).append({"key": "EmbedThumbnail"})
        common["embedthumbnail"] = True

    return common


@dataclass
class DownloadTask:
    id: str
    url: str
    title: str
    mode: str
    quality: str
    container: str
    status: str = "queued"
    progress: float = 0.0
    speed: float | None = None
    eta: int | None = None
    downloaded: int = 0
    total: int | None = None
    filename: str | None = None
    error: str | None = None
    warning: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    cancel_requested: bool = False

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "mode": self.mode,
            "quality": self.quality,
            "container": self.container,
            "status": self.status,
            "progress": round(self.progress, 2),
            "speed": self.speed,
            "eta": self.eta,
            "downloaded": self.downloaded,
            "total": self.total,
            "filename": self.filename,
            "error": self.error,
            "warning": self.warning,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }


def save_history() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with TASKS_LOCK:
        records = [task.public() for task in sorted(TASKS.values(), key=lambda item: item.created_at, reverse=True)[:50]]
    temp = HISTORY_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(HISTORY_FILE)


def load_history() -> None:
    if not HISTORY_FILE.exists():
        return
    try:
        records = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        for item in records:
            if item.get("status") in {"queued", "downloading", "processing"}:
                item["status"] = "interrupted"
                item["error"] = "上次运行结束时任务尚未完成"
            task = DownloadTask(
                id=item["id"],
                url=item.get("url", ""),
                title=item.get("title", "未命名视频"),
                mode=item.get("mode", "video"),
                quality=item.get("quality", "best"),
                container=item.get("container", "mp4"),
                status=item.get("status", "interrupted"),
                progress=float(item.get("progress", 0)),
                speed=item.get("speed"),
                eta=item.get("eta"),
                downloaded=int(item.get("downloaded", 0)),
                total=item.get("total"),
                filename=item.get("filename"),
                error=item.get("error"),
                warning=item.get("warning"),
                created_at=float(item.get("createdAt", time.time())),
                updated_at=float(item.get("updatedAt", time.time())),
            )
            TASKS[task.id] = task
    except Exception:
        HISTORY_FILE.rename(HISTORY_FILE.with_suffix(".corrupt"))


def save_subtitle_jobs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with SUBTITLE_LOCK:
        records = [
            job.public()
            for job in sorted(
                SUBTITLE_JOBS.values(),
                key=lambda item: item.created_at,
                reverse=True,
            )[:30]
        ]
    temp = SUBTITLE_HISTORY_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(SUBTITLE_HISTORY_FILE)


def load_subtitle_jobs() -> None:
    if not SUBTITLE_HISTORY_FILE.exists():
        return
    try:
        records = json.loads(SUBTITLE_HISTORY_FILE.read_text(encoding="utf-8"))
        for item in records:
            job = SubtitleJob.from_public(item)
            if job.status not in {"completed", "failed"}:
                job.status = "failed"
                job.error = "上次运行结束时字幕尚未生成完成"
                job.message = "任务已中断"
            SUBTITLE_JOBS[job.id] = job
    except Exception:
        SUBTITLE_HISTORY_FILE.rename(SUBTITLE_HISTORY_FILE.with_suffix(".corrupt"))


def subtitle_job_changed(job: SubtitleJob) -> None:
    with SUBTITLE_LOCK:
        SUBTITLE_JOBS[job.id] = job
    save_subtitle_jobs()


def run_local_subtitle_job(job: SubtitleJob, video_path: Path) -> None:
    execute_subtitle_job(
        job,
        video_path,
        DOWNLOAD_DIR,
        SUBTITLE_MODEL_DIR,
        SUBTITLE_WORK_DIR,
        subtitle_job_changed,
    )


def inspect_url(url: str) -> dict[str, Any]:
    import yt_dlp

    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "socket_timeout": 25,
        "extract_flat": False,
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)

    if info.get("_type") == "playlist" and info.get("entries"):
        info = next((entry for entry in info["entries"] if entry), info)

    formats = info.get("formats") or []
    heights = sorted(
        {int(fmt["height"]) for fmt in formats if isinstance(fmt.get("height"), (int, float))},
        reverse=True,
    )
    return {
        "id": info.get("id"),
        "title": info.get("title") or "未命名视频",
        "description": info.get("description") or "",
        "thumbnail": info.get("thumbnail"),
        "duration": info.get("duration"),
        "uploader": info.get("uploader") or info.get("channel") or info.get("extractor_key"),
        "webpageUrl": info.get("webpage_url") or url,
        "viewCount": info.get("view_count"),
        "uploadDate": info.get("upload_date"),
        "heights": heights[:8],
        "extractor": info.get("extractor_key") or info.get("extractor"),
        "liveStatus": info.get("live_status"),
    }


def run_download(task: DownloadTask, options: dict[str, Any]) -> None:
    import yt_dlp

    started_at = time.time()

    def progress_hook(data: dict[str, Any]) -> None:
        if task.cancel_requested:
            raise yt_dlp.utils.DownloadCancelled("用户已取消下载")
        status = data.get("status")
        with TASKS_LOCK:
            if status == "downloading":
                task.status = "downloading"
                task.downloaded = int(data.get("downloaded_bytes") or 0)
                task.total = int(data.get("total_bytes") or data.get("total_bytes_estimate") or 0) or None
                task.progress = (task.downloaded / task.total * 100) if task.total else task.progress
                task.speed = data.get("speed")
                task.eta = data.get("eta")
            elif status == "finished":
                task.status = "processing"
                task.progress = 99
                task.filename = Path(data.get("filename", "")).name or task.filename
            task.updated_at = time.time()

    def postprocessor_hook(data: dict[str, Any]) -> None:
        if task.cancel_requested:
            raise yt_dlp.utils.DownloadCancelled("用户已取消下载")
        with TASKS_LOCK:
            task.status = "processing"
            info = data.get("info_dict") or {}
            filepath = info.get("filepath") or info.get("_filename")
            if filepath:
                task.filename = Path(filepath).name
            task.updated_at = time.time()

    options["progress_hooks"] = [progress_hook]
    options["postprocessor_hooks"] = [postprocessor_hook]

    try:
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        used_subtitle_fallback = False
        used_curl_fallback = False
        while True:
            try:
                with yt_dlp.YoutubeDL(options) as ydl:
                    info = ydl.extract_info(task.url, download=True)
                    task.title = info.get("title") or task.title
                break
            except yt_dlp.utils.DownloadCancelled:
                raise
            except Exception as exc:
                if (
                    not used_subtitle_fallback
                    and options.get("writesubtitles")
                    and is_subtitle_rate_limit(exc)
                ):
                    used_subtitle_fallback = True
                    disable_subtitles(options)
                    with TASKS_LOCK:
                        task.status = "queued"
                        task.warning = "字幕接口触发限流，已跳过字幕继续下载"
                        task.updated_at = time.time()
                    continue
                if (
                    not used_curl_fallback
                    and shutil.which("curl")
                    and is_ssl_disconnect(exc)
                ):
                    used_curl_fallback = True
                    enable_curl_fallback(options)
                    with TASKS_LOCK:
                        task.status = "queued"
                        task.warning = "SSL 连接不稳定，已切换兼容下载模式"
                        task.updated_at = time.time()
                    continue
                raise

        candidates = [
            path
            for path in DOWNLOAD_DIR.iterdir()
            if path.is_file()
            and not path.name.endswith((".part", ".ytdl", ".temp"))
            and path.stat().st_mtime >= started_at - 2
        ]
        media_extensions = (
            {"mp4", "mkv", "webm", "mov", "avi", "m4v"}
            if task.mode == "video"
            else {"mp3", "m4a", "opus", "wav", "flac", "aac", "ogg", "webm"}
        )
        media_candidates = [path for path in candidates if path.suffix.lower().lstrip(".") in media_extensions]
        if media_candidates:
            candidates = media_candidates
        if candidates:
            candidates.sort(key=lambda path: (path.stat().st_mtime, path.stat().st_size), reverse=True)
            task.filename = candidates[0].name

        with TASKS_LOCK:
            task.status = "completed"
            task.progress = 100
            task.speed = None
            task.eta = 0
            task.updated_at = time.time()
    except yt_dlp.utils.DownloadCancelled:
        with TASKS_LOCK:
            task.status = "cancelled"
            task.error = "下载已取消"
            task.speed = None
            task.updated_at = time.time()
    except Exception as exc:
        with TASKS_LOCK:
            task.status = "failed"
            task.error = clean_error(exc)
            task.speed = None
            task.updated_at = time.time()
    finally:
        save_history()


class FluxHandler(BaseHTTPRequestHandler):
    server_version = "FluxDL/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        if os.environ.get("FLUXDL_VERBOSE"):
            super().log_message(fmt, *args)

    def _send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_BODY_SIZE:
            raise ValueError("请求内容无效")
        try:
            return json.loads(self.rfile.read(length))
        except json.JSONDecodeError as exc:
            raise ValueError("JSON 格式无效") from exc

    def _serve_static(self, request_path: str) -> None:
        relative = "index.html" if request_path in {"", "/"} else urllib.parse.unquote(request_path.lstrip("/"))
        candidate = (PUBLIC_DIR / relative).resolve()
        if PUBLIC_DIR not in candidate.parents and candidate != PUBLIC_DIR:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if not candidate.is_file():
            candidate = PUBLIC_DIR / "index.html"
        content = candidate.read_bytes()
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8" if content_type.startswith("text/") else content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.end_headers()
        self.wfile.write(content)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Allow", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/health":
            version = ytdlp_version()
            self._send_json(
                {
                    "ready": bool(version),
                    "version": version,
                    "ffmpeg": bool(shutil.which("ffmpeg")),
                    "subtitleEngine": bool(
                        importlib.util.find_spec("faster_whisper")
                        and importlib.util.find_spec("argostranslate")
                    ),
                    "downloadDir": str(DOWNLOAD_DIR),
                }
            )
            return

        if path == "/api/tasks":
            with TASKS_LOCK:
                tasks = [task.public() for task in sorted(TASKS.values(), key=lambda item: item.created_at, reverse=True)[:50]]
            self._send_json({"tasks": tasks})
            return

        if path == "/api/subtitles/jobs":
            with SUBTITLE_LOCK:
                jobs = [
                    job.public()
                    for job in sorted(
                        SUBTITLE_JOBS.values(),
                        key=lambda item: item.created_at,
                        reverse=True,
                    )[:30]
                ]
            self._send_json({"jobs": jobs})
            return

        if path.startswith("/api/files/"):
            filename = urllib.parse.unquote(path.removeprefix("/api/files/"))
            if not filename or filename != Path(filename).name:
                self.send_error(HTTPStatus.BAD_REQUEST)
                return
            file_path = (DOWNLOAD_DIR / filename).resolve()
            if file_path.parent != DOWNLOAD_DIR or not file_path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(file_path.stat().st_size))
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{urllib.parse.quote(file_path.name)}")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            with file_path.open("rb") as handle:
                shutil.copyfileobj(handle, self.wfile)
            return

        if path.startswith("/api/"):
            self._send_json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)
            return

        self._serve_static(path)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            payload = self._read_json()
        except ValueError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return

        if path == "/api/inspect":
            url = str(payload.get("url", "")).strip()
            if not valid_remote_url(url):
                self._send_json({"error": "请输入有效的 http(s) 视频链接"}, HTTPStatus.BAD_REQUEST)
                return
            if not ytdlp_version():
                self._send_json({"error": "yt-dlp 尚未安装，请通过 start.sh 启动应用"}, HTTPStatus.SERVICE_UNAVAILABLE)
                return
            try:
                self._send_json({"video": inspect_url(url)})
            except Exception as exc:
                self._send_json({"error": clean_error(exc)}, HTTPStatus.UNPROCESSABLE_ENTITY)
            return

        if path == "/api/download":
            url = str(payload.get("url", "")).strip()
            if not valid_remote_url(url):
                self._send_json({"error": "请输入有效的视频链接"}, HTTPStatus.BAD_REQUEST)
                return
            if not ytdlp_version():
                self._send_json({"error": "yt-dlp 尚未安装，请重新运行 start.sh"}, HTTPStatus.SERVICE_UNAVAILABLE)
                return

            mode = payload.get("mode") if payload.get("mode") in {"video", "audio"} else "video"
            container = str(payload.get("container", "mp4"))
            quality = str(payload.get("quality", "best"))
            if mode == "audio" and not shutil.which("ffmpeg"):
                self._send_json({"error": "仅音频转换需要 FFmpeg，请安装后重启应用"}, HTTPStatus.UNPROCESSABLE_ENTITY)
                return
            if payload.get("thumbnail") and not shutil.which("ffmpeg"):
                self._send_json({"error": "嵌入封面需要 FFmpeg，请安装后重启应用"}, HTTPStatus.UNPROCESSABLE_ENTITY)
                return
            task = DownloadTask(
                id=uuid.uuid4().hex[:12],
                url=url,
                title=str(payload.get("title") or "正在获取视频信息…")[:220],
                mode=mode,
                quality=quality,
                container=container,
            )
            options = format_options(
                mode,
                quality,
                container,
                bool(payload.get("subtitles")),
                bool(payload.get("thumbnail")),
            )
            with TASKS_LOCK:
                TASKS[task.id] = task
            save_history()
            threading.Thread(target=run_download, args=(task, options), daemon=True, name=f"download-{task.id}").start()
            self._send_json({"task": task.public()}, HTTPStatus.ACCEPTED)
            return

        if path == "/api/subtitles":
            task_id = str(payload.get("taskId", ""))
            with TASKS_LOCK:
                task = TASKS.get(task_id)
            if not task or task.status != "completed" or not task.filename:
                self._send_json({"error": "只能为已完成的视频生成字幕"}, HTTPStatus.UNPROCESSABLE_ENTITY)
                return
            video_path = (DOWNLOAD_DIR / task.filename).resolve()
            if video_path.parent != DOWNLOAD_DIR or not video_path.is_file():
                self._send_json({"error": "找不到已下载的视频文件"}, HTTPStatus.NOT_FOUND)
                return
            if not shutil.which("ffmpeg"):
                self._send_json({"error": "生成字幕需要 FFmpeg"}, HTTPStatus.SERVICE_UNAVAILABLE)
                return
            if not (
                importlib.util.find_spec("faster_whisper")
                and importlib.util.find_spec("argostranslate")
            ):
                self._send_json({"error": "本地字幕组件尚未安装"}, HTTPStatus.SERVICE_UNAVAILABLE)
                return
            with SUBTITLE_LOCK:
                active = any(
                    job.task_id == task_id
                    and job.status not in {"completed", "failed"}
                    for job in SUBTITLE_JOBS.values()
                )
            if active:
                self._send_json({"error": "这个视频正在生成字幕"}, HTTPStatus.CONFLICT)
                return

            model = str(payload.get("model", "base"))
            if model not in {"tiny", "base", "small"}:
                model = "base"
            target = str(payload.get("target", "zh"))
            if target not in {"original", "zh", "bilingual"}:
                target = "zh"
            job = SubtitleJob(
                id=uuid.uuid4().hex[:12],
                task_id=task.id,
                video_filename=task.filename,
                video_title=task.title,
                model=model,
                target=target,
                embed=bool(payload.get("embed", True)),
            )
            subtitle_job_changed(job)
            threading.Thread(
                target=run_local_subtitle_job,
                args=(job, video_path),
                daemon=True,
                name=f"subtitle-{job.id}",
            ).start()
            self._send_json({"job": job.public()}, HTTPStatus.ACCEPTED)
            return

        cancel_match = re.fullmatch(r"/api/tasks/([a-f0-9]{12})/cancel", path)
        if cancel_match:
            with TASKS_LOCK:
                task = TASKS.get(cancel_match.group(1))
                if not task:
                    self._send_json({"error": "任务不存在"}, HTTPStatus.NOT_FOUND)
                    return
                if task.status in {"queued", "downloading", "processing"}:
                    task.cancel_requested = True
                    task.updated_at = time.time()
            self._send_json({"task": task.public()})
            return

        if path == "/api/history/clear":
            with TASKS_LOCK:
                removable = [key for key, task in TASKS.items() if task.status not in {"queued", "downloading", "processing"}]
                for key in removable:
                    del TASKS[key]
            save_history()
            self._send_json({"ok": True})
            return

        self._send_json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)


def main() -> None:
    parser = argparse.ArgumentParser(description="FluxDL local yt-dlp web application")
    parser.add_argument("--host", default=os.environ.get("FLUXDL_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("FLUXDL_PORT", "8765")))
    args = parser.parse_args()

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    load_history()
    load_subtitle_jobs()
    server = ThreadingHTTPServer((args.host, args.port), FluxHandler)
    url = f"http://{args.host}:{args.port}"
    print()
    print("  FLUXDL · 本地视频下载器")
    print(f"  打开浏览器访问：{url}")
    print(f"  文件保存位置：{DOWNLOAD_DIR}")
    print("  按 Ctrl+C 停止服务")
    print()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
    finally:
        server.server_close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
