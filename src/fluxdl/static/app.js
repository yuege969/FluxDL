"use strict";

const state = {
  mode: "video",
  format: "mp4",
  video: null,
  tasks: [],
  subtitleJobs: [],
  subtitleTaskId: null,
  pollTimer: null,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const els = {
  url: $("#url-input"),
  inspect: $("#inspect-btn"),
  paste: $("#paste-btn"),
  download: $("#download-btn"),
  emptyPreview: $("#empty-preview"),
  videoPreview: $("#video-preview"),
  thumb: $("#video-thumb"),
  duration: $("#video-duration"),
  source: $("#video-source"),
  uploader: $("#video-uploader"),
  title: $("#video-title"),
  views: $("#video-views"),
  date: $("#video-date"),
  qualities: $("#quality-list"),
  qualityGroup: $("#quality-group"),
  quality: $("#quality-select"),
  videoFormats: $("#video-formats"),
  audioFormats: $("#audio-formats"),
  formatHint: $("#format-hint"),
  subtitles: $("#subtitle-toggle"),
  thumbnail: $("#thumbnail-toggle"),
  queue: $("#queue-list"),
  queueEmpty: $("#queue-empty"),
  statusDot: $("#status-dot"),
  systemLabel: $("#system-label"),
  version: $("#version-tag"),
  location: $("#download-location"),
  toast: $("#toast"),
  clear: $("#clear-history"),
  subtitleDialog: $("#subtitle-dialog"),
  subtitleForm: $("#subtitle-form"),
  subtitleClose: $("#subtitle-close"),
  subtitleVideoTitle: $("#subtitle-video-title"),
  subtitleModel: $("#subtitle-model"),
  subtitleTarget: $("#subtitle-target"),
  subtitleEmbed: $("#subtitle-embed"),
  subtitleSubmit: $("#subtitle-submit"),
};

function toast(message) {
  els.toast.textContent = message;
  els.toast.classList.add("show");
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => els.toast.classList.remove("show"), 2600);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || `请求失败 (${response.status})`);
  }
  return data;
}

function formatDuration(value) {
  if (!Number.isFinite(value)) return "时长未知";
  const seconds = Math.round(value);
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const rest = seconds % 60;
  return [hours, minutes, rest]
    .filter((_, index) => index > 0 || hours > 0)
    .map((part) => String(part).padStart(2, "0"))
    .join(":");
}

function formatBytes(value) {
  if (!Number.isFinite(value) || value <= 0) return "—";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
  return `${(value / 1024 ** index).toFixed(index > 1 ? 1 : 0)} ${units[index]}`;
}

function compactNumber(value) {
  if (!Number.isFinite(value)) return "播放量未知";
  return `${new Intl.NumberFormat("zh-CN", { notation: "compact", maximumFractionDigits: 1 }).format(value)} 次观看`;
}

function formatDate(value) {
  if (!value || value.length !== 8) return "日期未知";
  return `${value.slice(0, 4)}.${value.slice(4, 6)}.${value.slice(6, 8)}`;
}

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value ?? "";
  return div.innerHTML;
}

function statusText(status) {
  return {
    queued: "等待中",
    downloading: "下载中",
    processing: "处理中",
    completed: "已完成",
    failed: "失败",
    cancelled: "已取消",
    interrupted: "已中断",
  }[status] || status;
}

function renderVideo(video) {
  state.video = video;
  els.emptyPreview.classList.add("hidden");
  els.videoPreview.classList.remove("hidden");
  els.thumb.src = video.thumbnail || "";
  els.thumb.alt = `${video.title} 的视频封面`;
  els.duration.textContent = formatDuration(video.duration);
  els.source.textContent = (video.extractor || "VIDEO").toUpperCase();
  els.uploader.textContent = video.uploader || "未知发布者";
  els.title.textContent = video.title;
  els.views.textContent = compactNumber(video.viewCount);
  els.date.textContent = formatDate(video.uploadDate);
  els.qualities.replaceChildren(
    ...(video.heights || []).slice(0, 6).map((height) => {
      const chip = document.createElement("span");
      chip.textContent = height >= 2160 ? `4K · ${height}P` : `${height}P`;
      return chip;
    }),
  );
  if (!video.heights?.length) {
    const chip = document.createElement("span");
    chip.textContent = "自动选择画质";
    els.qualities.append(chip);
  }
  els.download.disabled = false;
  $("#workspace").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function inspectVideo() {
  const url = els.url.value.trim();
  if (!/^https?:\/\//i.test(url)) {
    toast("请先粘贴有效的视频链接");
    els.url.focus();
    return;
  }
  els.inspect.disabled = true;
  els.inspect.querySelector("span").textContent = "正在解析…";
  try {
    const { video } = await api("/api/inspect", {
      method: "POST",
      body: JSON.stringify({ url }),
    });
    renderVideo(video);
    toast("视频解析完成");
  } catch (error) {
    toast(error.message);
  } finally {
    els.inspect.disabled = false;
    els.inspect.querySelector("span").textContent = "解析视频";
  }
}

function selectMode(mode) {
  state.mode = mode;
  state.format = mode === "video" ? "mp4" : "mp3";
  $$("[data-mode]").forEach((button) => {
    const active = button.dataset.mode === mode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  els.qualityGroup.classList.toggle("hidden", mode === "audio");
  els.videoFormats.classList.toggle("hidden", mode !== "video");
  els.audioFormats.classList.toggle("hidden", mode !== "audio");
  els.formatHint.textContent = mode === "video" ? "兼容性优先" : "需要 FFmpeg";
  $$("#video-formats .format-option, #audio-formats .format-option").forEach((button) => {
    button.classList.toggle("active", button.dataset.format === state.format);
  });
}

function selectFormat(button) {
  state.format = button.dataset.format;
  button.parentElement.querySelectorAll(".format-option").forEach((item) => {
    item.classList.toggle("active", item === button);
  });
}

async function startDownload() {
  if (!state.video) {
    toast("请先解析视频");
    return;
  }
  els.download.disabled = true;
  els.download.querySelector("span").textContent = "正在加入队列…";
  try {
    await api("/api/download", {
      method: "POST",
      body: JSON.stringify({
        url: els.url.value.trim(),
        title: state.video.title,
        mode: state.mode,
        quality: state.mode === "video" ? els.quality.value : "best",
        container: state.format,
        subtitles: els.subtitles.checked,
        thumbnail: els.thumbnail.checked,
      }),
    });
    await refreshTasks();
    $(".queue-section").scrollIntoView({ behavior: "smooth", block: "start" });
    toast("已加入下载队列");
  } catch (error) {
    toast(error.message);
  } finally {
    els.download.disabled = false;
    els.download.querySelector("span").textContent = "开始下载";
  }
}

function renderTasks() {
  if (!state.tasks.length) {
    els.queue.replaceChildren(els.queueEmpty);
    els.queueEmpty.classList.remove("hidden");
    return;
  }
  els.queueEmpty.classList.add("hidden");
  const fragment = document.createDocumentFragment();
  for (const task of state.tasks) {
    const row = document.createElement("article");
    row.className = `task-row ${task.status}`;
    const active = ["queued", "downloading", "processing"].includes(task.status);
    const subtitleJob = state.subtitleJobs.find((job) => job.taskId === task.id);
    const subtitleActive = subtitleJob && !["completed", "failed"].includes(subtitleJob.status);
    const shownProgress = subtitleActive ? subtitleJob.progress : task.progress;
    const detail = subtitleActive
      ? escapeHtml(subtitleJob.message)
      : subtitleJob?.status === "failed"
        ? escapeHtml(subtitleJob.error || "字幕生成失败")
      : task.error
      ? escapeHtml(task.error)
      : task.warning
        ? escapeHtml(task.warning)
      : task.status === "downloading"
        ? `${formatBytes(task.downloaded)}${task.total ? ` / ${formatBytes(task.total)}` : ""} · ${formatBytes(task.speed)}/s`
        : task.filename
          ? escapeHtml(task.filename)
          : `${escapeHtml(task.container.toUpperCase())} · ${task.quality === "best" ? "最佳质量" : `${escapeHtml(task.quality)}P`}`;
    const subtitleFile = subtitleJob?.outputs?.findLast?.((name) => name.endsWith(".srt"));
    const embeddedFile = subtitleJob?.outputs?.find((name) => name.endsWith(".mkv"));
    const completedActions = task.status === "completed" && task.filename
      ? [
          subtitleActive
            ? `<button type="button" disabled>字幕 ${Math.round(subtitleJob.progress)}%</button>`
            : `<button type="button" data-subtitle="${task.id}">AI 字幕</button>`,
          subtitleFile
            ? `<a href="/api/files/${encodeURIComponent(subtitleFile)}">字幕 ↓</a>`
            : "",
          embeddedFile
            ? `<a href="/api/files/${encodeURIComponent(embeddedFile)}">字幕版 ↓</a>`
            : `<a href="/api/files/${encodeURIComponent(task.filename)}">视频 ↓</a>`,
        ].join("")
      : "";
    const action = completedActions
      ? completedActions
      : active
        ? `<button type="button" data-cancel="${task.id}">取消</button>`
        : ["failed", "cancelled", "interrupted"].includes(task.status)
          ? `<button type="button" data-retry="${task.id}">重试</button>`
        : "";
    row.innerHTML = `
      <div class="task-main">
        <div class="task-title-line">
          <span class="task-kind">${task.mode === "audio" ? "AUDIO" : "VIDEO"}</span>
          <span class="task-title" title="${escapeHtml(task.title)}">${escapeHtml(task.title)}</span>
        </div>
        <div class="task-track"><i style="width:${Math.max(0, Math.min(shownProgress, 100))}%"></i></div>
        <div class="task-detail"><span>${subtitleActive ? "AI 字幕" : statusText(task.status)}</span><span>${detail}</span></div>
      </div>
      <div class="task-stat">
        <b>${Math.round(shownProgress)}%</b>
        <span>${subtitleActive ? "本地处理中" : task.eta ? `约 ${task.eta}s` : statusText(task.status)}</span>
      </div>
      <div class="task-action">${action}</div>
    `;
    fragment.append(row);
  }
  els.queue.replaceChildren(fragment);
  $$("[data-cancel]").forEach((button) => {
    button.addEventListener("click", () => cancelTask(button.dataset.cancel));
  });
  $$("[data-retry]").forEach((button) => {
    button.addEventListener("click", () => retryTask(button.dataset.retry));
  });
  $$("[data-subtitle]").forEach((button) => {
    button.addEventListener("click", () => openSubtitleDialog(button.dataset.subtitle));
  });
}

async function refreshTasks() {
  try {
    const [{ tasks }, { jobs }] = await Promise.all([
      api("/api/tasks"),
      api("/api/subtitles/jobs"),
    ]);
    state.tasks = tasks;
    state.subtitleJobs = jobs;
    renderTasks();
    const active = tasks.some((task) => ["queued", "downloading", "processing"].includes(task.status))
      || jobs.some((job) => !["completed", "failed"].includes(job.status));
    window.clearTimeout(state.pollTimer);
    state.pollTimer = window.setTimeout(refreshTasks, active ? 800 : 4000);
  } catch {
    window.clearTimeout(state.pollTimer);
    state.pollTimer = window.setTimeout(refreshTasks, 5000);
  }
}

function openSubtitleDialog(taskId) {
  const task = state.tasks.find((item) => item.id === taskId);
  if (!task) return;
  state.subtitleTaskId = taskId;
  els.subtitleVideoTitle.textContent = task.title;
  els.subtitleDialog.showModal();
}

async function createSubtitles(event) {
  event.preventDefault();
  if (!state.subtitleTaskId) return;
  els.subtitleSubmit.disabled = true;
  els.subtitleSubmit.querySelector("span").textContent = "正在启动本地模型…";
  try {
    await api("/api/subtitles", {
      method: "POST",
      body: JSON.stringify({
        taskId: state.subtitleTaskId,
        model: els.subtitleModel.value,
        target: els.subtitleTarget.value,
        embed: els.subtitleEmbed.checked,
      }),
    });
    els.subtitleDialog.close();
    toast("AI 字幕任务已开始，首次运行需要下载模型");
    await refreshTasks();
  } catch (error) {
    toast(error.message);
  } finally {
    els.subtitleSubmit.disabled = false;
    els.subtitleSubmit.querySelector("span").textContent = "开始生成";
  }
}

async function cancelTask(id) {
  try {
    await api(`/api/tasks/${id}/cancel`, { method: "POST", body: "{}" });
    toast("正在取消任务");
    await refreshTasks();
  } catch (error) {
    toast(error.message);
  }
}

async function retryTask(id) {
  const previous = state.tasks.find((task) => task.id === id);
  if (!previous) return;
  try {
    await api("/api/download", {
      method: "POST",
      body: JSON.stringify({
        url: previous.url,
        title: previous.title,
        mode: previous.mode,
        quality: previous.quality,
        container: previous.container,
        subtitles: false,
        thumbnail: false,
      }),
    });
    toast("已使用稳定连接模式重新加入队列");
    await refreshTasks();
  } catch (error) {
    toast(error.message);
  }
}

async function clearHistory() {
  try {
    await api("/api/history/clear", { method: "POST", body: "{}" });
    await refreshTasks();
    toast("已清除完成记录");
  } catch (error) {
    toast(error.message);
  }
}

async function checkHealth() {
  try {
    const health = await api("/api/health");
    els.statusDot.className = `status-dot ${health.ready ? "online" : "offline"}`;
    els.systemLabel.textContent = health.ready ? "本地引擎就绪" : "yt-dlp 未安装";
    els.version.textContent = health.version ? `v${health.version}` : "未就绪";
    els.location.textContent = `保存至 ${health.downloadDir}`;
    if (!health.ffmpeg) {
      els.thumbnail.disabled = true;
      els.thumbnail.closest(".toggle-row").title = "安装 FFmpeg 后可用";
      const audioMode = $('[data-mode="audio"]');
      audioMode.disabled = true;
      audioMode.title = "安装 FFmpeg 后可使用音频转换";
      els.systemLabel.textContent = "引擎就绪 · 未安装 FFmpeg";
    }
  } catch {
    els.statusDot.className = "status-dot offline";
    els.systemLabel.textContent = "本地服务未连接";
  }
}

els.inspect.addEventListener("click", inspectVideo);
els.url.addEventListener("keydown", (event) => {
  if (event.key === "Enter") inspectVideo();
});
els.paste.addEventListener("click", async () => {
  try {
    els.url.value = await navigator.clipboard.readText();
    els.url.focus();
  } catch {
    toast("请使用快捷键粘贴链接");
  }
});
els.download.addEventListener("click", startDownload);
els.clear.addEventListener("click", clearHistory);
els.subtitleClose.addEventListener("click", () => els.subtitleDialog.close());
els.subtitleForm.addEventListener("submit", createSubtitles);
$$("[data-mode]").forEach((button) => button.addEventListener("click", () => selectMode(button.dataset.mode)));
$$(".format-option").forEach((button) => button.addEventListener("click", () => selectFormat(button)));

checkHealth();
refreshTasks();
