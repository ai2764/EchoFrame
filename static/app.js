let avatarId = null;
let mode = "fast";
let currentController = null;
let serverRunActive = false;
let lastStatusRunId = "";
let lastRenderedResultRunId = "";
let cameraStream = null;
let healthPollInFlight = false;
let servicesPollInFlight = false;
let gpuPollInFlight = false;
let runStatusPollInFlight = false;
const HEALTH_POLL_MS = 15000;
const SERVICES_POLL_MS = 5000;
const GPU_POLL_MS = 2000;
const RUN_STATUS_POLL_MS = 2000;
const RESOLUTION_MIN = 120;
const RESOLUTION_MAX = 512;
const RESOLUTION_DEFAULT = 320;
const STAGES = [
  ["llm", "LLM"],
  ["tts", "TTS"],
  ["audio_probe", "Audio Probe"],
  ["base_video", "Base Video"],
  ["musetalk", "MuseTalk"],
  ["total", "Total"],
];
const MODE_LABELS = {
  fast: "Running MuseTalk",
  wan_loop: "Running Wan Loop + MuseTalk",
  wan: "Running Wan Full + MuseTalk",
};
const SERVICE_LABELS = {
  lm_studio: "LM Studio",
  cosyvoice: "CosyVoice",
  comfyui: "ComfyUI",
  musetalk: "MuseTalk",
  ffmpeg: "ffmpeg",
  gpu: "GPU",
};

const $ = (id) => document.getElementById(id);

function setState(text) {
  $("runState").textContent = text;
}

function statusClass(ok) {
  return ok ? "ok" : "bad";
}

function renderHealthRow(name, value) {
  const health = $("health");
  let row = $(`health-${name}`);
  if (!row) {
    row = document.createElement("div");
    row.className = "healthItem";
    row.id = `health-${name}`;
    row.innerHTML = "<strong></strong><span></span>";
    health.appendChild(row);
  }
  const status = row.querySelector("span");
  row.querySelector("strong").textContent = name;
  status.className = statusClass(value.ok);
  status.textContent = `${value.ok ? "OK" : "OFF"} ${value.detail || ""}`;
}

function initStageStatus() {
  const box = $("stageStatus");
  box.innerHTML = "";
  for (const [key, label] of STAGES) {
    const chip = document.createElement("div");
    chip.className = "stageChip idle";
    chip.id = `stage-${key}`;
    chip.innerHTML = `<span class="dot"></span><strong>${label}</strong><em>not run</em>`;
    box.appendChild(chip);
  }
}

function setStage(key, status, duration = null) {
  const chip = $(`stage-${key}`);
  if (!chip) return;
  chip.classList.remove("idle", "running", "done", "failed", "cancelled");
  chip.classList.add(status);
  const text = status === "running"
    ? "running"
    : status === "done"
      ? `${duration ?? 0}s`
      : status === "cancelled"
        ? "cancelled"
      : status === "failed"
        ? "failed"
        : "not run";
  chip.querySelector("em").textContent = text;
}

function resetRunStatus() {
  for (const [key] of STAGES) {
    setStage(key, "idle");
  }
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
  await Promise.allSettled([refreshServices(), refreshHealth(), refreshGpu(), refreshRunStatus()]);
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
        <button type="button" data-action="start">Start</button>
        <button type="button" data-action="restart">Restart</button>
        <button type="button" data-action="stop">Stop</button>
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
    ok ? "OK" : online ? "ONLINE" : "OFF",
    installed ? "" : "not installed",
    modelsOk === false ? "models missing" : "",
    value.port ? `:${value.port}` : "",
  ].filter(Boolean);
  status.textContent = parts.join(" ");
  status.title = value.detail || "";
  for (const button of row.querySelectorAll("button")) {
    button.dataset.name = name;
    button.disabled = !value.startable;
  }
}

async function refreshServices() {
  if (servicesPollInFlight || document.hidden) return;
  servicesPollInFlight = true;
  try {
    const res = await fetch("/api/services", { cache: "no-store" });
    const data = await res.json();
    for (const [name, value] of Object.entries(data)) {
      renderServiceRow(name, value);
    }
  } catch (err) {
    const services = $("services");
    services.innerHTML = `<div class="serviceItem bad"><div class="serviceMeta"><strong>Services</strong><span>${err.message}</span></div></div>`;
  } finally {
    servicesPollInFlight = false;
  }
}

async function serviceAction(name, action) {
  setState(`${action} ${SERVICE_LABELS[name] || name}`);
  const res = await fetch(`/api/services/${encodeURIComponent(name)}/${action}`, { method: "POST" });
  const data = await res.json();
  if (!res.ok || !data.ok) {
    throw new Error(data.detail || `${action} failed`);
  }
  if (data.status) renderServiceRow(name, data.status);
  await refreshServices();
}

async function refreshHealth() {
  if (healthPollInFlight) return;
  healthPollInFlight = true;
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    for (const [name, value] of Object.entries(data)) {
      renderHealthRow(name, value);
    }
  } catch (err) {
    const health = $("health");
    health.innerHTML = `<div class="healthItem"><strong>app</strong><span class="bad">${err.message}</span></div>`;
  } finally {
    healthPollInFlight = false;
  }
}

async function refreshGpu() {
  if (gpuPollInFlight || document.hidden) return;
  gpuPollInFlight = true;
  try {
    const res = await fetch("/api/gpu", { cache: "no-store" });
    const data = await res.json();
    renderHealthRow("gpu", data);
  } catch (err) {
    renderHealthRow("gpu", { ok: false, detail: err.message });
  } finally {
    gpuPollInFlight = false;
  }
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
    setState(runId ? `Running ${runId}` : "Running");
    if (runId) lastStatusRunId = runId;
    return;
  }
  if (!isNewRun && !currentController) return;
  if (runId) lastStatusRunId = runId;
  if (data.result) renderResult(data.result);
  if (data.status === "done") {
    setState(runId ? `Done ${runId}` : "Done");
  } else if (data.status === "cancelled") {
    markRunningCancelled();
    setState("Stopped");
  } else if (data.status === "failed") {
    markRunningFailed();
    setState(data.error || "Failed");
  }
}

async function uploadAvatar(file) {
  const form = new FormData();
  form.append("image", file);
  setState("Uploading");
  const res = await fetch("/api/avatar", { method: "POST", body: form });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Upload failed");
  avatarId = data.avatar_id;
  const preview = $("avatarPreview");
  preview.src = data.image_url;
  preview.style.display = "block";
  setState("Avatar ready");
}

async function openCamera() {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("Camera is not available in this browser");
  }
  stopCamera();
  cameraStream = await navigator.mediaDevices.getUserMedia({
    video: {
      facingMode: "user",
      width: { ideal: 1280 },
      height: { ideal: 1280 },
    },
    audio: false,
  });
  $("cameraVideo").srcObject = cameraStream;
  $("cameraBox").hidden = false;
  $("cameraShot").hidden = false;
  $("cameraClose").hidden = false;
  $("cameraOpen").hidden = true;
  setState("Camera ready");
}

function stopCamera() {
  if (cameraStream) {
    for (const track of cameraStream.getTracks()) track.stop();
  }
  cameraStream = null;
  if ($("cameraVideo")) $("cameraVideo").srcObject = null;
  if ($("cameraBox")) $("cameraBox").hidden = true;
  if ($("cameraShot")) $("cameraShot").hidden = true;
  if ($("cameraClose")) $("cameraClose").hidden = true;
  if ($("cameraOpen")) $("cameraOpen").hidden = false;
}

async function captureCameraPhoto() {
  const video = $("cameraVideo");
  if (!cameraStream || !video.videoWidth || !video.videoHeight) {
    throw new Error("Camera is not ready");
  }
  const size = RESOLUTION_MAX;
  const side = Math.min(video.videoWidth, video.videoHeight);
  const sx = Math.floor((video.videoWidth - side) / 2);
  const sy = Math.floor((video.videoHeight - side) / 2);
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(video, sx, sy, side, side, 0, 0, size, size);
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
  if (!blob) throw new Error("Could not capture photo");
  const file = new File([blob], `camera-${Date.now()}.png`, { type: "image/png" });
  await uploadAvatar(file);
  stopCamera();
}

async function generate() {
  if (!avatarId) throw new Error("Upload an avatar first");
  const message = $("message").value.trim();
  const replyOverride = $("replyOverride").value.trim();
  if (!message && !replyOverride) throw new Error("Enter a message or manual reply");
  const controller = new AbortController();
  currentController = controller;
  setRunning(true);
  lastStatusRunId = "";
  lastRenderedResultRunId = "";
  resetRunStatus();
  setState(MODE_LABELS[mode] || "Running");
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
        voice_id: $("voiceId").value.trim() || null,
        resolution: getResolution(),
      }),
    });
    if (!res.ok || !res.body) throw new Error("Generation failed");
    await readEventStream(res.body);
    setState("Done");
  } catch (err) {
    if (err.name === "AbortError") {
      setState("Stopped");
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
    throw new Error(event.message || "Generation failed");
  }
  if (event.type === "cancelled") {
    markRunningCancelled();
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
  setState("Stopping");
  $("stop").disabled = true;
  try {
    await fetch("/api/stop", { method: "POST" });
  } catch {
    // The local abort below still stops the UI request.
  }
  if (currentController) currentController.abort();
  setServerRunActive(false);
  markRunningCancelled();
  setState("Stopped");
}

function renderResult(data) {
  const runId = data.run_id || "";
  if (runId && runId === lastRenderedResultRunId) return;
  $("reply").textContent = data.reply;
  $("instruct").textContent = data.cosyvoice_instruct;
  $("ttsSent").textContent = data.tts_instruct_sent || "(empty; stable preset voice)";
  $("wanPrompt").textContent = data.wan_prompt;
  $("duration").textContent = `${data.audio_duration}s`;
  $("resultResolution").textContent = data.resolution ? `${data.resolution}x${data.resolution}` : "";
  $("timings").innerHTML = Object.entries(data.timings || {})
    .map(([key, value]) => `<span class="timing">${key}: ${value}s</span>`)
    .join("");
  setMediaSrc($("video"), data.video_url);
  setMediaSrc($("audio"), data.audio_url);
  if (runId) lastRenderedResultRunId = runId;
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

$("cameraOpen").addEventListener("click", async () => {
  try {
    await openCamera();
  } catch (err) {
    setState(err.message);
  }
});

$("cameraShot").addEventListener("click", async () => {
  try {
    await captureCameraPhoto();
  } catch (err) {
    setState(err.message);
  }
});

$("cameraClose").addEventListener("click", () => {
  stopCamera();
  setState("Camera closed");
});

$("send").addEventListener("click", async () => {
  try {
    await generate();
  } catch (err) {
    setState(err.message);
  }
});

$("stop").addEventListener("click", stopWorkflow);
$("refreshHealth").addEventListener("click", refreshAll);
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
setResolution(RESOLUTION_DEFAULT);
refreshAll();
refreshGpu();
setInterval(refreshGpu, GPU_POLL_MS);
setInterval(refreshServices, SERVICES_POLL_MS);
setInterval(refreshHealth, HEALTH_POLL_MS);
setInterval(refreshRunStatus, RUN_STATUS_POLL_MS);
