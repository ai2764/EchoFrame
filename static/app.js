let avatarId = null;
let mode = "fast";
let videoBackend = "ltx_ia2v";
let currentController = null;
let serverRunActive = false;
let prepareInFlight = false;
let lastStatusRunId = "";
let lastRenderedResultRunId = "";
let lastResult = null;
let servicesPollInFlight = false;
let gpuPollInFlight = false;
let runStatusPollInFlight = false;
const SERVICES_POLL_MS = 5000;
const GPU_POLL_MS = 2000;
const RUN_STATUS_POLL_MS = 2000;
const RESOLUTION_MIN = 120;
const RESOLUTION_MAX = 1028;
const RESOLUTION_DEFAULT = 320;
const UI_LANG_KEY = "echoframe.uiLang";
const STAGE_LABELS = {
  llm: "stageLlm",
  tts: "stageTts",
  audio_probe: "stageAudioProbe",
  native_audio_export: "stageNativeAudioExport",
  pre_ltx_vram_release: "ltxVramRelease",
  ltx_ia2v: "stageLtxIa2v",
  ltx_native_audio: "stageLtxNativeAudio",
  post_ltx_tts_preload: "ttsPreload",
  pre_wan_comfy_release: "preWanComfyRelease",
  base_video: "stageBaseVideo",
  post_wan_comfy_release: "postWanComfyRelease",
  musetalk: "stageMuseTalk",
  total: "stageTotal",
};
const WORKFLOW_STAGES = {
  ltx_ia2v: ["llm", "tts", "audio_probe", "pre_ltx_vram_release", "ltx_ia2v", "post_ltx_tts_preload", "total"],
  ltx_native_audio: ["llm", "ltx_native_audio", "native_audio_export", "total"],
  musetalk: [
    "pre_wan_comfy_release",
    "llm",
    "tts",
    "audio_probe",
    "base_video",
    "post_wan_comfy_release",
    "musetalk",
    "total",
  ],
};
const WORKFLOW_LABELS = {
  ltx_ia2v: "workflowLtx",
  ltx_native_audio: "workflowLtxNative",
  musetalk: "workflowWanMuseTalk",
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
    prepare: "\u51c6\u5907",
    workspace: "\u5de5\u4f5c\u53f0",
    gpu: "GPU",
    gpuWaiting: "等待 GPU 状态",
    gpuUnavailable: "GPU 不可用",
    utilization: "占用率",
    avatar: "头像",
    mode: "模式",
    language: "语言",
    workflow: "工作流",
    workflowLtx: "LTX IA2V",
    workflowLtxNative: "LTX 原生声画",
    workflowWanMuseTalk: "Wan + MuseTalk",
    workflowHintLtx: "TTS \u51fa\u58f0\uff0cLTX \u51fa\u89c6\u9891",
    workflowHintNative: "LTX \u540c\u65f6\u51fa\u58f0\u97f3\u548c\u89c6\u9891",
    workflowHintWan: "TTS \u51fa\u58f0\uff0cWan \u51fa\u5e95\u7247\uff0cMuseTalk \u5bf9\u53e3\u578b",
    flowText: "文本",
    flowTts: "TTS",
    flowLtx: "LTX",
    flowLtxAv: "LTX 声画",
    flowWan: "Wan",
    flowMuseTalk: "口型",
    flowMp4: "MP4",
    videoPrompt: "视频提示词",
    modeFast: "静图 + MuseTalk",
    modeWanLoop: "Wan 循环",
    modeWanFull: "Wan 完整",
    resolution: "分辨率",
    size: "尺寸",
    input: "\u8f93\u5165",
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
    output: "\u8f93\u51fa",
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
    runningLtxIa2v: "正在运行 LTX IA2V",
    runningLtxNativeAudio: "正在运行 LTX 原生声画",
    runningWanLoop: "正在运行 Wan Loop + MuseTalk",
    runningWan: "正在运行 Wan Full + MuseTalk",
    preparingWorkflow: "\u51c6\u5907\u4e2d {workflow}",
    preparedWorkflow: "\u51c6\u5907\u5b8c\u6210: {detail}",
    prepareFailed: "\u51c6\u5907\u5931\u8d25",
    cancelledState: "已取消",
    stageLlm: "LLM",
    stageTts: "TTS",
    stageAudioProbe: "音频检查",
    stageNativeAudioExport: "音轨导出",
    stageBaseVideo: "底片",
    stageMuseTalk: "MuseTalk",
    stageLtxIa2v: "LTX IA2V",
    stageLtxNativeAudio: "LTX 原生声画",
    ltxVramRelease: "LTX \u524d\u91ca\u653e\u663e\u5b58",
    preWanComfyRelease: "先释放 Comfy",
    postWanComfyRelease: "Wan 后释放 Comfy",
    ttsPreload: "TTS \u56de\u8f7d",
    ttsPreloadFailed: "TTS \u56de\u8f7d\u5931\u8d25",
    stageTotal: "总计",
    notRun: "未运行",
    stageRunning: "运行中",
    stageDone: "{duration}s",
    stageCancelled: "已取消",
    stageFailed: "失败",
    ttsPresetVoice: "(空；使用稳定预设声音)",
    regenLlm: "重新生成文本",
    regenTts: "重新生成语音",
    regenNativeAudio: "重新生成声画",
    regenVideo: "重新生成视频",
    regenerateNeedResult: "请先完成一次生成",
    regeneratingStage: "正在重新生成 {stage}",
  },
  en: {
    idle: "Idle",
    services: "Services",
    refresh: "Refresh",
    prepare: "Prepare",
    workspace: "Workspace",
    gpu: "GPU",
    gpuWaiting: "Waiting for GPU status",
    gpuUnavailable: "GPU unavailable",
    utilization: "Utilization",
    avatar: "Avatar",
    workflow: "Workflow",
    workflowLtx: "LTX IA2V",
    workflowLtxNative: "LTX Native A/V",
    workflowWanMuseTalk: "Wan + MuseTalk",
    workflowHintLtx: "TTS voice, LTX video",
    workflowHintNative: "LTX voice and video",
    workflowHintWan: "TTS voice, Wan base, MuseTalk lips",
    flowText: "Text",
    flowTts: "TTS",
    flowLtx: "LTX",
    flowLtxAv: "LTX A/V",
    flowWan: "Wan",
    flowMuseTalk: "Lip",
    flowMp4: "MP4",
    videoPrompt: "Video Prompt",
    mode: "Mode",
    language: "Language",
    modeFast: "Still + MuseTalk",
    modeWanLoop: "Wan Loop",
    modeWanFull: "Wan Full",
    resolution: "Resolution",
    size: "Size",
    input: "Input",
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
    output: "Output",
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
    runningLtxIa2v: "Running LTX IA2V",
    runningLtxNativeAudio: "Running LTX Native A/V",
    runningWanLoop: "Running Wan Loop + MuseTalk",
    runningWan: "Running Wan Full + MuseTalk",
    preparingWorkflow: "Preparing {workflow}",
    preparedWorkflow: "Prepared: {detail}",
    prepareFailed: "Prepare failed",
    cancelledState: "Cancelled",
    stageLlm: "LLM",
    stageTts: "TTS",
    stageAudioProbe: "Audio Probe",
    stageNativeAudioExport: "Audio Export",
    stageBaseVideo: "Base Video",
    stageMuseTalk: "MuseTalk",
    stageLtxIa2v: "LTX IA2V",
    stageLtxNativeAudio: "LTX Native A/V",
    ltxVramRelease: "Pre-LTX VRAM release",
    preWanComfyRelease: "Release Comfy first",
    postWanComfyRelease: "Post-Wan Comfy release",
    ttsPreload: "TTS reload",
    ttsPreloadFailed: "TTS reload failed",
    stageTotal: "Total",
    notRun: "not run",
    stageRunning: "running",
    stageDone: "{duration}s",
    stageCancelled: "cancelled",
    stageFailed: "failed",
    ttsPresetVoice: "(empty; stable preset voice)",
    regenLlm: "Regenerate Text",
    regenTts: "Regenerate Voice",
    regenNativeAudio: "Regenerate A/V",
    regenVideo: "Regenerate Video",
    regenerateNeedResult: "Generate a result first",
    regeneratingStage: "Regenerating {stage}",
  },
};

let uiLang = chooseInitialLanguage();
let runStateKey = "idle";
let runStateParams = {};
let activeStageWorkflow = videoBackend;

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
  updateRegenerateButtons();
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

function stageEntries(workflow = activeStageWorkflow) {
  const keys = WORKFLOW_STAGES[workflow] || WORKFLOW_STAGES.ltx_ia2v;
  return keys.map((key) => [key, STAGE_LABELS[key] || key]);
}

function visibleStageKeys() {
  return stageEntries().map(([key]) => key);
}

function initStageStatus(workflow = activeStageWorkflow) {
  activeStageWorkflow = WORKFLOW_STAGES[workflow] ? workflow : "ltx_ia2v";
  const box = $("stageStatus");
  box.innerHTML = "";
  for (const [key, labelKey] of stageEntries(activeStageWorkflow)) {
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
  for (const [key, labelKey] of stageEntries()) {
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
  if (status === "failed") {
    return duration == null ? tr("stageFailed") : `${tr("stageFailed")} ${duration}s`;
  }
  return tr("notRun");
}

function resetRunStatus(workflow = activeStageWorkflow) {
  initStageStatus(workflow);
  setRunError("");
  $("timings").innerHTML = "";
}

function setRunning(running) {
  $("send").disabled = running;
  $("stop").disabled = !running;
  const prepareButton = $("prepareWorkflow");
  if (prepareButton) prepareButton.disabled = running || prepareInFlight;
  updateRegenerateButtons();
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
  const isActive = Boolean(data.active);
  setServerRunActive(isActive);
  // Polling returns the latest completed run forever. Once that run has already
  // been rendered, ignore it so workflow selection can show its own idle stages.
  if (!isActive && !isNewRun && !currentController) return;
  const resultWorkflow = data.result?.final_video_backend;
  if (resultWorkflow && resultWorkflow !== activeStageWorkflow) {
    initStageStatus(resultWorkflow);
  }
  for (const [stage, item] of Object.entries(data.stages || {})) {
    setStage(stage, item.status || "idle", item.duration);
  }
  if (data.status === "running") {
    setRunError("");
    setStateKey(runId ? "runningRun" : "running", { id: runId });
    if (runId) lastStatusRunId = runId;
    return;
  }
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

async function prepareCurrentWorkflow() {
  if (prepareInFlight || currentController || serverRunActive) return;
  prepareInFlight = true;
  setRunning(true);
  $("stop").disabled = true;
  setRunError("");
  setStateKey("preparingWorkflow", { workflow: workflowLabel(videoBackend) });
  try {
    const res = await fetch("/api/prepare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        final_video_backend: videoBackend,
        mode,
        resolution: getResolution(),
      }),
    });
    const data = await res.json();
    if (!res.ok || data.ok === false) throw new Error(data.detail || tr("prepareFailed"));
    setStateKey("preparedWorkflow", { detail: data.detail || workflowLabel(videoBackend) });
    refreshAll();
  } finally {
    prepareInFlight = false;
    setRunning(Boolean(currentController || serverRunActive));
  }
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
  resetRunStatus(videoBackend);
  setStateKey(runningStateKey());
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
        final_video_backend: videoBackend,
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

async function regenerate(stage) {
  if (!lastResult || !lastResult.run_id) throw new Error(tr("regenerateNeedResult"));
  const controller = new AbortController();
  currentController = controller;
  setRunning(true);
  lastStatusRunId = "";
  lastRenderedResultRunId = "";
  resetRunStatus(lastResult.final_video_backend || videoBackend);
  setStateKey("regeneratingStage", { stage: regenerateStageLabel(stage) });
  try {
    const res = await fetch("/api/regenerate-stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
      body: JSON.stringify({
        run_id: lastResult.run_id,
        stage,
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
  for (const key of visibleStageKeys()) {
    const chip = $(`stage-${key}`);
    if (chip && chip.classList.contains("running")) setStage(key, "failed");
  }
}

function markRunningCancelled() {
  for (const key of visibleStageKeys()) {
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
  lastResult = data;
  $("reply").textContent = data.reply;
  $("instruct").textContent = data.cosyvoice_instruct;
  $("ttsSent").textContent = data.tts_instruct_sent || tr("ttsPresetVoice");
  $("resultWorkflow").textContent = workflowLabel(data.final_video_backend || videoBackend);
  $("wanPrompt").textContent = data.wan_prompt;
  $("duration").textContent = `${data.audio_duration}s`;
  $("resultResolution").textContent = data.resolution ? `${data.resolution}x${data.resolution}` : "";
  $("timings").innerHTML = Object.entries(data.timings || {})
    .map(([key, value]) => `<span class="timing">${escapeHtml(timingLabel(key))}: ${value}s</span>`)
    .join("");
  setMediaSrc($("video"), data.video_url);
  if (runId) lastRenderedResultRunId = runId;
  updateRegenerateButtons();
}

function updateRegenerateButtons() {
  const disabled = Boolean(currentController || serverRunActive || prepareInFlight || !lastResult?.run_id);
  const nativeAudio = lastResult?.final_video_backend === "ltx_native_audio";
  for (const id of ["regenLlm", "regenTts", "regenVideo"]) {
    const button = $(id);
    if (button) button.disabled = disabled;
  }
  const ttsButton = $("regenTts");
  if (ttsButton) ttsButton.textContent = tr(nativeAudio ? "regenNativeAudio" : "regenTts");
}

function runningStateKey() {
  if (videoBackend === "ltx_native_audio") return "runningLtxNativeAudio";
  if (videoBackend === "ltx_ia2v") return "runningLtxIa2v";
  if (mode === "wan_loop") return "runningWanLoop";
  if (mode === "wan") return "runningWan";
  return "runningMuseTalk";
}

function workflowLabel(backend) {
  return tr(WORKFLOW_LABELS[backend] || "workflow");
}

function updateWorkflowControls() {
  const useMusetalk = videoBackend === "musetalk";
  const modeGroup = $("wanModeGroup");
  if (modeGroup) {
    modeGroup.hidden = !useMusetalk;
    modeGroup.querySelectorAll("button").forEach((button) => {
      button.disabled = !useMusetalk;
    });
  }
  if (!useMusetalk) {
    mode = "fast";
    document.querySelectorAll(".mode").forEach((button) => {
      button.classList.toggle("active", button.dataset.mode === mode);
    });
  }
}

function regenerateStageLabel(stage) {
  if (stage === "llm") return tr("regenLlm");
  if (stage === "tts" && lastResult?.final_video_backend === "ltx_native_audio") return tr("regenNativeAudio");
  if (stage === "tts") return tr("regenTts");
  if (stage === "video") return tr("regenVideo");
  return stage;
}

function timingLabel(key) {
  const labels = {
    ...STAGE_LABELS,
    pre_ltx_vram_release: "ltxVramRelease",
    post_ltx_tts_preload: "ttsPreload",
    post_ltx_tts_preload_failed: "ttsPreloadFailed",
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

document.querySelectorAll(".workflow").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".workflow").forEach((b) => b.classList.remove("active"));
    button.classList.add("active");
    videoBackend = button.dataset.backend;
    updateWorkflowControls();
    if (!currentController && !serverRunActive) resetRunStatus(videoBackend);
  });
});

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
$("prepareWorkflow").addEventListener("click", async () => {
  try {
    await prepareCurrentWorkflow();
  } catch (err) {
    setRunError(err.message);
    setStateKey("prepareFailed");
  }
});
$("regenLlm").addEventListener("click", async () => {
  try {
    await regenerate("llm");
  } catch (err) {
    setRunError(err.message);
    setStateKey("failed");
  }
});
$("regenTts").addEventListener("click", async () => {
  try {
    await regenerate("tts");
  } catch (err) {
    setRunError(err.message);
    setStateKey("failed");
  }
});
$("regenVideo").addEventListener("click", async () => {
  try {
    await regenerate("video");
  } catch (err) {
    setRunError(err.message);
    setStateKey("failed");
  }
});
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
initStageStatus(videoBackend);
updateWorkflowControls();
applyTranslations();
setResolution(RESOLUTION_DEFAULT);
refreshAll();
refreshGpu();
setInterval(refreshGpu, GPU_POLL_MS);
setInterval(refreshServices, SERVICES_POLL_MS);
setInterval(refreshRunStatus, RUN_STATUS_POLL_MS);
