let avatarId = null;
let mode = "fast";
let currentController = null;
let serverRunActive = false;
let lastStatusRunId = "";
let lastRenderedResultRunId = "";
let servicesPollInFlight = false;
let gpuPollInFlight = false;
let runStatusPollInFlight = false;
const SERVICES_POLL_MS = 5000;
const GPU_POLL_MS = 2000;
const RUN_STATUS_POLL_MS = 2000;
const RESOLUTION_MIN = 120;
const RESOLUTION_MAX = 512;
const RESOLUTION_DEFAULT = 320;
const UI_LANG_KEY = "echoframe.uiLang";
const STAGES = [
  ["llm", "stageLlm"],
  ["tts", "stageTts"],
  ["audio_probe", "stageAudioProbe"],
  ["base_video", "stageBaseVideo"],
  ["musetalk", "stageMuseTalk"],
  ["total", "stageTotal"],
];
const MODE_LABELS = {
  fast: "runningMuseTalk",
  wan_loop: "runningWanLoop",
  wan: "runningWan",
};
const SERVICE_LABELS = {
  lm_studio: "LM Studio",
  cosyvoice: "CosyVoice",
  comfyui: "ComfyUI",
  musetalk: "MuseTalk",
  ffmpeg: "ffmpeg",
  gpu: "GPU",
};

const TRANSLATIONS = {
  zh: {
    idle: "空闲",
    services: "服务",
    refresh: "刷新",
    gpu: "GPU",
    gpuWaiting: "等待 GPU 状态",
    gpuUnavailable: "GPU 不可用",
    utilization: "占用率",
    avatar: "头像",
    mode: "模式",
    language: "语言",
    modeFast: "快速",
    modeWanLoop: "Wan 循环",
    modeWanFull: "Wan 完整",
    resolution: "分辨率",
    size: "尺寸",
    message: "聊天模式",
    messagePlaceholder: "输入问题，让 LLM 生成口播文本...",
    spokenText: "口播文本",
    spokenTextPlaceholder: "输入要直接生成的口播文本...",
    voice: "声音",
    voiceFemale: "女声",
    voiceMale: "男声",
    generate: "生成",
    stop: "停止",
    runStatus: "运行状态",
    reply: "回复",
    ttsSent: "TTS 发送",
    audio: "音频",
    timings: "耗时",
    video: "视频",
    ok: "正常",
    online: "在线",
    off: "离线",
    notInstalled: "未安装",
    modelsMissing: "模型缺失",
    modelLoaded: "模型已加载",
    modelUnloaded: "模型未加载",
    start: "启动",
    restart: "重启",
    actionStart: "启动 {name}",
    actionRestart: "重启 {name}",
    actionFailed: "{action}失败",
    noActiveAiProcess: "没有活动 AI 进程",
    aiProcessCount: "{count} 个 AI 进程",
    uploadAvatarFirst: "请先上传头像",
    enterMessageOrSpokenText: "请输入消息或口播文本",
    uploading: "上传中",
    avatarReady: "头像已就绪",
    uploadFailed: "上传失败",
    generationFailed: "生成失败",
    failed: "失败",
    stopped: "已停止",
    stopping: "停止中",
    done: "完成",
    doneRun: "完成 {id}",
    running: "运行中",
    runningRun: "运行中 {id}",
    runningMuseTalk: "正在运行 MuseTalk",
    runningWanLoop: "正在运行 Wan Loop + MuseTalk",
    runningWan: "正在运行 Wan Full + MuseTalk",
    cancelledState: "已取消",
    stageLlm: "LLM",
    stageTts: "TTS",
    stageAudioProbe: "音频检查",
    stageBaseVideo: "底片",
    stageMuseTalk: "MuseTalk",
    stageTotal: "总计",
    notRun: "未运行",
    stageRunning: "运行中",
    stageDone: "{duration}s",
    stageCancelled: "已取消",
    stageFailed: "失败",
    ttsPresetVoice: "(空；使用稳定预设声音)",
  },
  en: {
    idle: "Idle",
    services: "Services",
    refresh: "Refresh",
    gpu: "GPU",
    gpuWaiting: "Waiting for GPU status",
    gpuUnavailable: "GPU unavailable",
    utilization: "Utilization",
    avatar: "Avatar",
    mode: "Mode",
    language: "Language",
    modeFast: "Fast",
    modeWanLoop: "Wan Loop",
    modeWanFull: "Wan Full",
    resolution: "Resolution",
    size: "Size",
    message: "Chat Mode",
    messagePlaceholder: "Ask a question and let the LLM write the spoken text...",
    spokenText: "Spoken Text",
    spokenTextPlaceholder: "Enter the exact spoken text...",
    voice: "Voice",
    voiceFemale: "Female",
    voiceMale: "Male",
    generate: "Generate",
    stop: "Stop",
    runStatus: "Run Status",
    reply: "Reply",
    ttsSent: "TTS Sent",
    audio: "Audio",
    timings: "Timings",
    video: "Video",
    ok: "OK",
    online: "ONLINE",
    off: "OFF",
    notInstalled: "not installed",
    modelsMissing: "models missing",
    modelLoaded: "model loaded",
    modelUnloaded: "model unloaded",
    start: "Start",
    restart: "Restart",
    actionStart: "Start {name}",
    actionRestart: "Restart {name}",
    actionFailed: "{action} failed",
    noActiveAiProcess: "No active AI compute process",
    aiProcessCount: "{count} AI {plural}",
    uploadAvatarFirst: "Upload an avatar first",
    enterMessageOrSpokenText: "Enter a message or spoken text",
    uploading: "Uploading",
    avatarReady: "Avatar ready",
    uploadFailed: "Upload failed",
    generationFailed: "Generation failed",
    failed: "Failed",
    stopped: "Stopped",
    stopping: "Stopping",
    done: "Done",
    doneRun: "Done {id}",
    running: "Running",
    runningRun: "Running {id}",
    runningMuseTalk: "Running MuseTalk",
    runningWanLoop: "Running Wan Loop + MuseTalk",
    runningWan: "Running Wan Full + MuseTalk",
    cancelledState: "Cancelled",
    stageLlm: "LLM",
    stageTts: "TTS",
    stageAudioProbe: "Audio Probe",
    stageBaseVideo: "Base Video",
    stageMuseTalk: "MuseTalk",
    stageTotal: "Total",
    notRun: "not run",
    stageRunning: "running",
    stageDone: "{duration}s",
    stageCancelled: "cancelled",
    stageFailed: "failed",
    ttsPresetVoice: "(empty; stable preset voice)",
  },
};

let uiLang = chooseInitialLanguage();
let runStateKey = "idle";
let runStateParams = {};

const $ = (id) => document.getElementById(id);

function chooseInitialLanguage() {
  const saved = localStorage.getItem(UI_LANG_KEY);
  if (saved === "zh" || saved === "en") return saved;
  return navigator.language?.toLowerCase().startsWith("zh") ? "zh" : "en";
}

function tr(key, params = {}) {
  const source = TRANSLATIONS[uiLang] || TRANSLATIONS.en;
  const fallback = TRANSLATIONS.en[key] || key;
  const text = source[key] || fallback;
  return text.replace(/\{(\w+)\}/g, (_, name) => String(params[name] ?? ""));
}

function applyTranslations() {
  document.documentElement.lang = uiLang === "zh" ? "zh-CN" : "en";
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = tr(node.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
    node.setAttribute("placeholder", tr(node.dataset.i18nPlaceholder));
  });
  document.querySelectorAll("[data-i18n-aria]").forEach((node) => {
    node.setAttribute("aria-label", tr(node.dataset.i18nAria));
  });
  document.querySelectorAll(".lang").forEach((button) => {
    button.classList.toggle("active", button.dataset.lang === uiLang);
  });
  updateRunStateText();
  updateStageTexts();
}

function setLanguage(lang) {
  uiLang = lang === "zh" ? "zh" : "en";
  localStorage.setItem(UI_LANG_KEY, uiLang);
  applyTranslations();
  lastStatusRunId = "";
  lastRenderedResultRunId = "";
  refreshAll();
}

function setStateKey(key, params = {}) {
  runStateKey = key;
  runStateParams = params;
  updateRunStateText();
}

function setState(text) {
  runStateKey = "";
  runStateParams = {};
  $("runState").textContent = text;
}

function updateRunStateText() {
  if (!runStateKey) return;
  $("runState").textContent = tr(runStateKey, runStateParams);
}

function setRunError(text = "") {
  const box = $("runError");
  if (!box) return;
  box.textContent = text;
  box.hidden = !text;
}

function initStageStatus() {
  const box = $("stageStatus");
  box.innerHTML = "";
  for (const [key, labelKey] of STAGES) {
    const chip = document.createElement("div");
    chip.className = "stageChip idle";
    chip.id = `stage-${key}`;
    chip.dataset.status = "idle";
    chip.dataset.duration = "";
    chip.innerHTML = `<span class="dot"></span><strong>${tr(labelKey)}</strong><em>${tr("notRun")}</em>`;
    box.appendChild(chip);
  }
}

function setStage(key, status, duration = null) {
  const chip = $(`stage-${key}`);
  if (!chip) return;
  chip.classList.remove("idle", "running", "done", "failed", "cancelled");
  chip.classList.add(status);
  chip.dataset.status = status;
  chip.dataset.duration = duration == null ? "" : String(duration);
  chip.querySelector("em").textContent = stageStatusText(status, duration);
}

function updateStageTexts() {
  for (const [key, labelKey] of STAGES) {
    const chip = $(`stage-${key}`);
    if (!chip) continue;
    chip.querySelector("strong").textContent = tr(labelKey);
    const duration = chip.dataset.duration ? Number(chip.dataset.duration) : null;
    chip.querySelector("em").textContent = stageStatusText(chip.dataset.status || "idle", duration);
  }
}

function stageStatusText(status, duration = null) {
  if (status === "running") return tr("stageRunning");
  if (status === "done") return tr("stageDone", { duration: duration ?? 0 });
  if (status === "cancelled") return tr("stageCancelled");
  if (status === "failed") return tr("stageFailed");
  return tr("notRun");
}

function resetRunStatus() {
  for (const [key] of STAGES) {
    setStage(key, "idle");
  }
  setRunError("");
  $("timings").innerHTML = "";
}

function setRunning(running) {
  $("send").disabled = running;
  $("stop").disabled = !running;
}

function setServerRunActive(active) {
  serverRunActive = active;
  if (!currentController) {
    setRunning(active);
  }
}

async function refreshAll() {
  await Promise.allSettled([refreshServices(), refreshGpu(), refreshRunStatus()]);
}

function renderServiceRow(name, value) {
  const services = $("services");
  let row = $(`service-${name}`);
  if (!row) {
    row = document.createElement("div");
    row.className = "serviceItem";
    row.id = `service-${name}`;
    row.innerHTML = `
      <div class="serviceMeta">
        <strong></strong>
        <span></span>
      </div>
      <div class="serviceActions">
        <button type="button"></button>
      </div>
    `;
    services.appendChild(row);
  }
  const ok = Boolean(value.ok);
  const online = Boolean(value.online);
  const installed = value.installed !== false;
  const modelsOk = value.models_ok;
  const status = row.querySelector(".serviceMeta span");
  row.classList.toggle("ok", ok);
  row.classList.toggle("bad", !ok);
  row.querySelector("strong").textContent = SERVICE_LABELS[name] || name;
  const parts = [
    ok ? tr("ok") : online ? tr("online") : tr("off"),
    serviceDetailText(name, value),
    installed ? "" : tr("notInstalled"),
    modelsOk === false ? tr("modelsMissing") : "",
    value.port ? `:${value.port}` : "",
  ].filter(Boolean);
  status.textContent = parts.join(" ");
  status.title = value.detail || "";
  const action = servicePrimaryAction(name, value);
  const actions = row.querySelector(".serviceActions");
  actions.innerHTML = "";
  if (!action) return;
  const button = document.createElement("button");
  button.type = "button";
  button.dataset.name = name;
  button.dataset.action = action;
  button.textContent = tr(action === "start" ? "start" : "restart");
  button.disabled = !value.startable;
  actions.appendChild(button);
}

function serviceDetailText(name, value) {
  const detail = String(value.detail || "");
  if (name !== "lm_studio") return "";
  const loaded = detail.match(/loaded:\s*(.+)$/i);
  if (loaded) return `${tr("modelLoaded")}: ${loaded[1]}`;
  if (detail.toLowerCase().includes("no loaded llm")) return tr("modelUnloaded");
  return "";
}

function servicePrimaryAction(name, value) {
  if (!value.startable) return "";
  if (value.ok) return "";
  if (value.installed === false || value.models_ok === false) return "";
  if (value.online) return name === "comfyui" ? "restart" : "";
  return "start";
}

async function refreshServices() {
  if (servicesPollInFlight || document.hidden) return;
  servicesPollInFlight = true;
  try {
    const res = await fetch("/api/services", { cache: "no-store" });
    const data = await res.json();
    for (const [name, value] of Object.entries(data)) {
      if (name === "gpu") continue;
      renderServiceRow(name, value);
    }
  } catch (err) {
    const services = $("services");
    services.innerHTML = `<div class="serviceItem bad"><div class="serviceMeta"><strong>${tr("services")}</strong><span>${escapeHtml(err.message)}</span></div></div>`;
  } finally {
    servicesPollInFlight = false;
  }
}

async function serviceAction(name, action) {
  const serviceName = SERVICE_LABELS[name] || name;
  const actionKey = action === "start" ? "start" : "restart";
  setStateKey(action === "start" ? "actionStart" : "actionRestart", { name: serviceName });
  const res = await fetch(`/api/services/${encodeURIComponent(name)}/${action}`, { method: "POST" });
  const data = await res.json();
  if (!res.ok || !data.ok) {
    throw new Error(data.detail || tr("actionFailed", { action: tr(actionKey) }));
  }
  if (data.status) renderServiceRow(name, data.status);
  await refreshServices();
}

async function refreshGpu() {
  if (gpuPollInFlight || document.hidden) return;
  gpuPollInFlight = true;
  try {
    const res = await fetch("/api/gpu", { cache: "no-store" });
    const data = await res.json();
    renderGpu(data);
  } catch (err) {
    renderGpu({ ok: false, detail: err.message, processes: [] });
  } finally {
    gpuPollInFlight = false;
  }
}

function renderGpu(data) {
  const ok = Boolean(data.ok);
  const badge = $("gpuBadge");
  badge.className = `statusBadge ${ok ? "ok" : "bad"}`;
  badge.textContent = ok ? tr("ok") : tr("off");
  $("gpuPanel").classList.toggle("ok", ok);
  $("gpuPanel").classList.toggle("bad", !ok);
  $("gpuName").textContent = data.name || data.detail || tr("gpuUnavailable");

  const util = numberOrZero(data.utilization);
  const memUsed = numberOrZero(data.memory_used);
  const memTotal = numberOrZero(data.memory_total);
  const memPct = memTotal > 0 ? Math.min(100, Math.round((memUsed / memTotal) * 100)) : 0;
  $("gpuUtilText").textContent = data.utilization == null ? "--%" : `${util}%`;
  $("gpuUtilBar").style.width = `${Math.min(100, util)}%`;
  $("gpuMemText").textContent = memTotal ? `${memUsed} / ${memTotal} MiB` : "-- / --";
  $("gpuMemBar").style.width = `${memPct}%`;
  $("gpuTemp").textContent = data.temperature == null ? "-- C" : `${data.temperature} C`;

  const processes = Array.isArray(data.processes) ? data.processes : [];
  $("gpuProcessCount").textContent = aiProcessCountText(processes.length);
  const box = $("gpuProcesses");
  if (!processes.length) {
    box.innerHTML = `<div class="gpuProcess empty">${tr("noActiveAiProcess")}</div>`;
    return;
  }
  box.innerHTML = processes.map((item) => `
    <div class="gpuProcess">
      <strong>${escapeHtml(item.label || "Process")}</strong>
      <span>PID ${escapeHtml(item.pid || "?")}</span>
      ${gpuProcessMemoryHtml(item)}
    </div>
  `).join("");
}

function gpuProcessMemoryHtml(item) {
  if (item.memory_available && item.used_memory) {
    return `<em>${escapeHtml(item.used_memory)}</em>`;
  }
  return "";
}

function aiProcessCountText(count) {
  return tr("aiProcessCount", { count, plural: count === 1 ? "process" : "processes" });
}

function numberOrZero(value) {
  return Number.isFinite(Number(value)) ? Number(value) : 0;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function refreshRunStatus() {
  if (runStatusPollInFlight || document.hidden) return;
  runStatusPollInFlight = true;
  try {
    const res = await fetch("/api/run-status", { cache: "no-store" });
    const data = await res.json();
    applyRunStatus(data);
  } catch {
    // Keep the visible SSE state if the pull endpoint is briefly unavailable.
  } finally {
    runStatusPollInFlight = false;
  }
}

function applyRunStatus(data) {
  if (!data || !data.exists) {
    setServerRunActive(false);
    return;
  }
  const runId = data.run_id || "";
  const isNewRun = runId && runId !== lastStatusRunId;
  setServerRunActive(Boolean(data.active));
  for (const [stage, item] of Object.entries(data.stages || {})) {
    setStage(stage, item.status || "idle", item.duration);
  }
  if (data.status === "running") {
    setRunError("");
    setStateKey(runId ? "runningRun" : "running", { id: runId });
    if (runId) lastStatusRunId = runId;
    return;
  }
  if (!isNewRun && !currentController) return;
  if (runId) lastStatusRunId = runId;
  if (data.result) renderResult(data.result);
  if (data.status === "done") {
    setRunError("");
    setStateKey(runId ? "doneRun" : "done", { id: runId });
  } else if (data.status === "cancelled") {
    setRunError("");
    markRunningCancelled();
    setStateKey("stopped");
  } else if (data.status === "failed") {
    markRunningFailed();
    setRunError(data.error || tr("failed"));
    setStateKey("failed");
  }
}

async function uploadAvatar(file) {
  const form = new FormData();
  form.append("image", file);
  setStateKey("uploading");
  const res = await fetch("/api/avatar", { method: "POST", body: form });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || tr("uploadFailed"));
  avatarId = data.avatar_id;
  const preview = $("avatarPreview");
  preview.src = data.image_url;
  preview.style.display = "block";
  setStateKey("avatarReady");
}

async function generate() {
  if (!avatarId) throw new Error(tr("uploadAvatarFirst"));
  const message = $("message").value.trim();
  const replyOverride = $("replyOverride").value.trim();
  if (!message && !replyOverride) throw new Error(tr("enterMessageOrSpokenText"));
  const controller = new AbortController();
  currentController = controller;
  setRunning(true);
  lastStatusRunId = "";
  lastRenderedResultRunId = "";
  resetRunStatus();
  setStateKey(MODE_LABELS[mode] || "running");
  try {
    const res = await fetch("/api/chat-stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
      body: JSON.stringify({
        avatar_id: avatarId,
        message,
        reply_override: replyOverride || null,
        mode,
        voice: $("voiceChoice").value,
        resolution: getResolution(),
      }),
    });
    if (!res.ok || !res.body) throw new Error(tr("generationFailed"));
    await readEventStream(res.body);
    setStateKey("done");
  } catch (err) {
    if (err.name === "AbortError") {
      setStateKey("stopped");
      return;
    }
    throw err;
  } finally {
    if (currentController === controller) currentController = null;
    setRunning(false);
  }
}

async function readEventStream(body) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() || "";
    for (const raw of events) {
      const line = raw.split("\n").find((part) => part.startsWith("data: "));
      if (!line) continue;
      handleEvent(JSON.parse(line.slice(6)));
    }
  }
}

function handleEvent(event) {
  if (event.type === "stage") {
    setStage(event.stage, event.status, event.duration);
    return;
  }
  if (event.type === "result") {
    renderResult(event.data);
    return;
  }
  if (event.type === "error") {
    markRunningFailed();
    setRunError(event.message || tr("generationFailed"));
    throw new Error(event.message || tr("generationFailed"));
  }
  if (event.type === "cancelled") {
    markRunningCancelled();
    setRunError("");
    throw new DOMException(event.message || "Workflow cancelled", "AbortError");
  }
}

function markRunningFailed() {
  for (const [key] of STAGES) {
    const chip = $(`stage-${key}`);
    if (chip && chip.classList.contains("running")) setStage(key, "failed");
  }
}

function markRunningCancelled() {
  for (const [key] of STAGES) {
    const chip = $(`stage-${key}`);
    if (chip && chip.classList.contains("running")) setStage(key, "cancelled");
  }
}

async function stopWorkflow() {
  if (!currentController && !serverRunActive) return;
  setStateKey("stopping");
  $("stop").disabled = true;
  try {
    await fetch("/api/stop", { method: "POST" });
  } catch {
    // The local abort below still stops the UI request.
  }
  if (currentController) currentController.abort();
  setServerRunActive(false);
  markRunningCancelled();
  setStateKey("stopped");
}

function renderResult(data) {
  const runId = data.run_id || "";
  if (runId && runId === lastRenderedResultRunId) return;
  $("reply").textContent = data.reply;
  $("instruct").textContent = data.cosyvoice_instruct;
  $("ttsSent").textContent = data.tts_instruct_sent || tr("ttsPresetVoice");
  $("wanPrompt").textContent = data.wan_prompt;
  $("duration").textContent = `${data.audio_duration}s`;
  $("resultResolution").textContent = data.resolution ? `${data.resolution}x${data.resolution}` : "";
  $("timings").innerHTML = Object.entries(data.timings || {})
    .map(([key, value]) => `<span class="timing">${escapeHtml(timingLabel(key))}: ${value}s</span>`)
    .join("");
  setMediaSrc($("video"), data.video_url);
  if (runId) lastRenderedResultRunId = runId;
}

function timingLabel(key) {
  const labels = {
    llm: "stageLlm",
    tts: "stageTts",
    audio_probe: "stageAudioProbe",
    base_video: "stageBaseVideo",
    musetalk: "stageMuseTalk",
    total: "stageTotal",
  };
  return labels[key] ? tr(labels[key]) : key;
}

function setMediaSrc(element, url) {
  if (!url) return;
  if (element.getAttribute("src") !== url) {
    element.setAttribute("src", url);
  }
}

function clampResolution(value) {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) return RESOLUTION_DEFAULT;
  const clamped = Math.max(RESOLUTION_MIN, Math.min(RESOLUTION_MAX, parsed));
  return clamped % 2 === 0 ? clamped : clamped - 1;
}

function getResolution() {
  return clampResolution($("resolutionNumber").value || $("resolutionRange").value);
}

function setResolution(value) {
  const resolution = clampResolution(value);
  $("resolutionRange").value = resolution;
  $("resolutionNumber").value = resolution;
  $("resolutionValue").textContent = resolution;
}

document.querySelectorAll(".mode").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".mode").forEach((b) => b.classList.remove("active"));
    button.classList.add("active");
    mode = button.dataset.mode;
  });
});

document.querySelectorAll(".lang").forEach((button) => {
  button.addEventListener("click", () => setLanguage(button.dataset.lang));
});

$("resolutionRange").addEventListener("input", (event) => setResolution(event.target.value));
$("resolutionNumber").addEventListener("change", (event) => setResolution(event.target.value));
$("resolutionNumber").addEventListener("input", (event) => {
  $("resolutionValue").textContent = clampResolution(event.target.value);
});

$("avatarInput").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    await uploadAvatar(file);
  } catch (err) {
    setState(err.message);
  }
});

$("send").addEventListener("click", async () => {
  try {
    await generate();
  } catch (err) {
    setRunError(err.message);
    setStateKey("failed");
  }
});

$("stop").addEventListener("click", stopWorkflow);
$("refreshAllStatus").addEventListener("click", refreshAll);
$("refreshServices").addEventListener("click", refreshServices);
$("services").addEventListener("click", async (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  try {
    await serviceAction(button.dataset.name, button.dataset.action);
  } catch (err) {
    setState(err.message);
  }
});
initStageStatus();
applyTranslations();
setResolution(RESOLUTION_DEFAULT);
refreshAll();
refreshGpu();
setInterval(refreshGpu, GPU_POLL_MS);
setInterval(refreshServices, SERVICES_POLL_MS);
setInterval(refreshRunStatus, RUN_STATUS_POLL_MS);
