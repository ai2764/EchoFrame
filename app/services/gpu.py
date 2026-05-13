import csv
import io
import subprocess


def list_gpu_compute_apps() -> list[dict]:
    cmd = [
        "nvidia-smi",
        "--query-compute-apps=pid,process_name,used_memory",
        "--format=csv,noheader",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
    except Exception:
        return []
    if result.returncode != 0:
        return []
    rows = []
    for row in csv.reader(io.StringIO(result.stdout)):
        if len(row) < 3:
            continue
        rows.append(
            {
                "pid": row[0].strip(),
                "process_name": row[1].strip(),
                "used_memory": row[2].strip(),
            }
        )
    return rows


def gpu_summary() -> str:
    gpu = _gpu_totals()
    apps = list_gpu_compute_apps()
    ai_apps = [_format_ai_process(a) for a in apps]
    ai_apps = [a for a in ai_apps if a]
    parts = []
    if gpu:
        parts.append(gpu)
    if ai_apps:
        parts.append("AI: " + "; ".join(ai_apps))
    else:
        parts.append("AI: no active AI compute process")
    return " | ".join(parts)


def _gpu_totals() -> str:
    cmd = [
        "nvidia-smi",
        "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
        "--format=csv,noheader,nounits",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    first = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
    fields = [f.strip() for f in first.split(",")]
    if len(fields) < 4:
        return ""
    util, used, total, temp = fields[:4]
    return f"GPU {util}% util, VRAM {used}/{total} MiB, {temp}C"


def _format_ai_process(app: dict) -> str:
    raw = app.get("process_name", "")
    lower = raw.lower()
    pid = app.get("pid", "?")
    mem = app.get("used_memory", "")

    ignored = (
        "chrome",
        "explorer.exe",
        "textinputhost",
        "phoneexperiencehost",
        "windowsapps",
        "applicationframehost",
        "dwm.exe",
    )
    if any(token in lower for token in ignored):
        return ""
    if "[insufficient permissions]" in lower:
        return ""

    label = ""
    if "lm studio" in lower:
        label = "LM Studio"
    elif "cosyvoice" in lower:
        label = "CosyVoice"
    elif "musetalk" in lower:
        label = "MuseTalk"
    elif "comfyui" in lower or "uv\\python" in lower or "uv/python" in lower:
        label = "ComfyUI"
    elif "python" in lower:
        label = "Python"
    else:
        return ""

    mem_suffix = f" {mem}" if mem and mem != "[N/A]" else ""
    return f"{label} pid {pid}{mem_suffix}"
