import csv
import io
import re
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
        memory_text = row[2].strip()
        memory_mib = _to_int(memory_text)
        rows.append(
            {
                "pid": row[0].strip(),
                "process_name": row[1].strip(),
                "used_memory": memory_text if memory_mib is not None else "",
                "used_memory_mib": memory_mib,
                "memory_available": memory_mib is not None,
            }
        )
    return rows


def gpu_status() -> dict:
    totals = _gpu_totals()
    processes = []
    for app in list_gpu_compute_apps():
        item = _format_ai_process(app)
        if item:
            processes.append(item)
    detail = _format_gpu_detail(totals, processes)
    return {
        "ok": bool(totals) or bool(processes),
        "detail": detail,
        "name": totals.get("name", "NVIDIA GPU") if totals else "GPU",
        "utilization": totals.get("utilization") if totals else None,
        "memory_used": totals.get("memory_used") if totals else None,
        "memory_total": totals.get("memory_total") if totals else None,
        "temperature": totals.get("temperature") if totals else None,
        "processes": processes,
    }


def gpu_summary() -> str:
    return gpu_status()["detail"]


def _gpu_totals() -> dict:
    cmd = [
        "nvidia-smi",
        "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
        "--format=csv,noheader,nounits",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
    except Exception:
        return {}
    if result.returncode != 0:
        return {}
    first = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
    fields = [f.strip() for f in first.split(",")]
    if len(fields) < 5:
        return {}
    name, util, used, total, temp = fields[:5]
    return {
        "name": name,
        "utilization": _to_int(util),
        "memory_used": _to_int(used),
        "memory_total": _to_int(total),
        "temperature": _to_int(temp),
    }


def _format_ai_process(app: dict) -> dict | None:
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
        return None
    if "[insufficient permissions]" in lower:
        return None

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
        return None

    return {
        "label": label,
        "pid": pid,
        "process_name": raw,
        "used_memory": mem,
        "used_memory_mib": app.get("used_memory_mib"),
        "memory_available": bool(app.get("memory_available")),
    }


def _format_gpu_detail(totals: dict, processes: list[dict]) -> str:
    parts = []
    if totals:
        parts.append(
            f"GPU {totals['utilization']}% util, VRAM {totals['memory_used']}/{totals['memory_total']} MiB, {totals['temperature']}C"
        )
    if processes:
        active = []
        for item in processes:
            mem = item.get("used_memory") or ""
            mem_suffix = f" {mem}" if mem and mem != "[N/A]" else ""
            active.append(f"{item['label']} pid {item['pid']}{mem_suffix}")
        parts.append("AI: " + "; ".join(active))
    else:
        parts.append("AI: no active AI compute process")
    return " | ".join(parts)


def _to_int(value: str) -> int | None:
    match = re.search(r"\d+", str(value))
    return int(match.group(0)) if match else None
