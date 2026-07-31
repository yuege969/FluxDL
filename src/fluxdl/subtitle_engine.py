"""Local speech-to-text and subtitle translation pipeline."""

from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


ProgressCallback = Callable[["SubtitleJob"], None]


@dataclass
class SubtitleJob:
    id: str
    task_id: str
    video_filename: str
    video_title: str
    model: str
    target: str
    embed: bool
    status: str = "queued"
    progress: float = 0.0
    message: str = "等待生成"
    language: str | None = None
    outputs: list[str] = field(default_factory=list)
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def public(self) -> dict:
        return {
            "id": self.id,
            "taskId": self.task_id,
            "videoFilename": self.video_filename,
            "videoTitle": self.video_title,
            "model": self.model,
            "target": self.target,
            "embed": self.embed,
            "status": self.status,
            "progress": round(self.progress, 2),
            "message": self.message,
            "language": self.language,
            "outputs": self.outputs,
            "error": self.error,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }

    @classmethod
    def from_public(cls, data: dict) -> "SubtitleJob":
        return cls(
            id=data["id"],
            task_id=data["taskId"],
            video_filename=data.get("videoFilename", ""),
            video_title=data.get("videoTitle", "未命名视频"),
            model=data.get("model", "base"),
            target=data.get("target", "zh"),
            embed=bool(data.get("embed")),
            status=data.get("status", "failed"),
            progress=float(data.get("progress", 0)),
            message=data.get("message", ""),
            language=data.get("language"),
            outputs=list(data.get("outputs") or []),
            error=data.get("error"),
            created_at=float(data.get("createdAt", time.time())),
            updated_at=float(data.get("updatedAt", time.time())),
        )


def srt_timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def write_srt(path: Path, segments: list[dict], text_key: str = "text") -> None:
    blocks: list[str] = []
    for index, segment in enumerate(segments, 1):
        text = str(segment.get(text_key, "")).strip()
        text = re.sub(r"[ \t]+", " ", text)
        if not text:
            continue
        blocks.append(
            f"{index}\n"
            f"{srt_timestamp(float(segment['start']))} --> {srt_timestamp(float(segment['end']))}\n"
            f"{text}\n"
        )
    path.write_text("\n".join(blocks), encoding="utf-8")


def _update(job: SubtitleJob, callback: ProgressCallback, status: str, progress: float, message: str) -> None:
    job.status = status
    job.progress = progress
    job.message = message
    job.updated_at = time.time()
    callback(job)


def _run_ffmpeg(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        detail = (result.stderr or result.stdout or "FFmpeg 处理失败").strip()
        raise RuntimeError(detail[-900:])


def _translation_available(from_code: str, to_code: str) -> bool:
    os.environ.setdefault("ARGOS_CHUNK_TYPE", "MINISBD")
    import argostranslate.translate

    try:
        installed = argostranslate.translate.get_installed_languages()
        source = next(language for language in installed if language.code == from_code)
        target = next(language for language in installed if language.code == to_code)
        source.get_translation(target)
        return True
    except (StopIteration, AttributeError):
        return False


def _install_translation_route(from_code: str, to_code: str) -> None:
    if from_code == to_code or _translation_available(from_code, to_code):
        return

    import argostranslate.package

    argostranslate.package.update_package_index()
    available = argostranslate.package.get_available_packages()

    def install_pair(source: str, target: str) -> bool:
        if _translation_available(source, target):
            return True
        package = next(
            (item for item in available if item.from_code == source and item.to_code == target),
            None,
        )
        if not package:
            return False
        argostranslate.package.install_from_path(package.download())
        return True

    if install_pair(from_code, to_code):
        return
    if from_code != "en" and install_pair(from_code, "en") and install_pair("en", to_code):
        return
    raise RuntimeError(f"暂时没有可用的 {from_code} → {to_code} 本地翻译模型")


def _translate_segments(
    job: SubtitleJob,
    callback: ProgressCallback,
    segments: list[dict],
    from_code: str,
) -> None:
    os.environ.setdefault("ARGOS_CHUNK_TYPE", "MINISBD")
    import argostranslate.translate

    _update(job, callback, "translation_model", 67, "正在准备离线中文翻译模型")
    _install_translation_route(from_code, "zh")
    total = max(len(segments), 1)
    for index, segment in enumerate(segments):
        translated = argostranslate.translate.translate(segment["text"], from_code, "zh")
        segment["translated"] = translated.strip()
        job.progress = 70 + ((index + 1) / total * 17)
        job.message = f"正在翻译字幕 {index + 1}/{total}"
        job.updated_at = time.time()
        callback(job)


def run_subtitle_job(
    job: SubtitleJob,
    video_path: Path,
    download_dir: Path,
    model_dir: Path,
    work_dir: Path,
    callback: ProgressCallback,
) -> None:
    audio_path = work_dir / f"{job.id}.wav"
    work_dir.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)
    try:
        _update(job, callback, "extracting", 2, "正在提取语音音轨")
        _run_ffmpeg(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(video_path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(audio_path),
            ]
        )

        _update(job, callback, "model", 8, "正在加载 Whisper；首次使用会下载模型")
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "120")
        from faster_whisper import WhisperModel

        model = WhisperModel(
            job.model,
            device="cpu",
            compute_type="int8",
            download_root=str(model_dir),
        )
        _update(job, callback, "transcribing", 18, "正在识别语音")
        segment_stream, info = model.transcribe(
            str(audio_path),
            beam_size=5,
            vad_filter=True,
            condition_on_previous_text=True,
        )
        job.language = info.language
        duration = max(float(info.duration or 1), 1)
        segments: list[dict] = []
        for segment in segment_stream:
            segments.append(
                {
                    "start": float(segment.start),
                    "end": float(segment.end),
                    "text": segment.text.strip(),
                }
            )
            job.progress = min(64, 18 + (float(segment.end) / duration * 46))
            job.message = f"正在识别语音 · {round(float(segment.end))}/{round(duration)} 秒"
            job.updated_at = time.time()
            callback(job)

        if not segments:
            raise RuntimeError("没有识别到清晰语音，无法生成字幕")

        language = job.language or "und"
        stem = video_path.stem
        original_path = download_dir / f"{stem}.{language}.ai.srt"
        write_srt(original_path, segments)
        selected_subtitle = original_path
        job.outputs = [original_path.name]
        callback(job)

        if job.target in {"zh", "bilingual"} and language != "zh":
            _translate_segments(job, callback, segments, language)
            text_key = "translated"
            if job.target == "bilingual":
                for segment in segments:
                    segment["bilingual"] = f"{segment['text']}\n{segment['translated']}"
                text_key = "bilingual"
            suffix = "zh-Hans-bilingual" if job.target == "bilingual" else "zh-Hans"
            translated_path = download_dir / f"{stem}.{suffix}.ai.srt"
            write_srt(translated_path, segments, text_key)
            selected_subtitle = translated_path
            job.outputs.append(translated_path.name)
            callback(job)

        if job.embed:
            _update(job, callback, "embedding", 90, "正在嵌入可开关字幕")
            output_path = download_dir / f"{stem}.带AI字幕.mkv"
            _run_ffmpeg(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(video_path),
                    "-i",
                    str(selected_subtitle),
                    "-map",
                    "0",
                    "-map",
                    "1",
                    "-c",
                    "copy",
                    "-c:s",
                    "srt",
                    "-metadata:s:s:0",
                    "language=zho" if job.target != "original" else f"language={language}",
                    str(output_path),
                ]
            )
            job.outputs.append(output_path.name)

        _update(job, callback, "completed", 100, "AI 字幕已生成")
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)[-900:]
        job.message = "字幕生成失败"
        job.updated_at = time.time()
        callback(job)
    finally:
        audio_path.unlink(missing_ok=True)
