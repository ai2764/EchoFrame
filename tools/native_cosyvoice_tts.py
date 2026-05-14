from __future__ import annotations

import argparse
import io
import json
import os
import random
import re
import sys
import traceback
from pathlib import Path


def main(args: argparse.Namespace | None = None) -> int:
    if args is None:
        args = parse_args()
    root = args.root.resolve()
    model_dir = args.model_dir.resolve()
    presets_path = args.presets.resolve()

    add_cosyvoice_paths(root)
    patch_modelscope_snapshot()

    import torch
    import torchaudio
    from cosyvoice.cli.cosyvoice import CosyVoice2
    from cosyvoice.utils.common import set_all_random_seed

    print("[EchoFrame TTS] loading CosyVoice2...", file=sys.stderr, flush=True)
    cosyvoice = CosyVoice2(
        str(model_dir),
        load_jit=False,
        load_trt=False,
        load_vllm=False,
        fp16=args.fp16,
    )
    print(f"[EchoFrame TTS] loaded sr={cosyvoice.sample_rate}", file=sys.stderr, flush=True)
    generate_to_file(
        cosyvoice=cosyvoice,
        torch_module=torch,
        torchaudio_module=torchaudio,
        presets_path=presets_path,
        voice_id=args.voice_id,
        text=args.text,
        instruct=args.instruct,
        speed=args.speed,
        output=args.output.resolve(),
        set_seed=set_all_random_seed,
        text_frontend=args.text_frontend,
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate one wav with local CosyVoice2.")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--presets", required=True, type=Path)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--text", default="")
    parser.add_argument("--voice-id", default="")
    parser.add_argument("--instruct", default="")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fp16", action="store_true")
    parser.add_argument("--text-frontend", action="store_true")
    args = parser.parse_args()
    if not args.worker and (not args.text or not args.voice_id or not args.output):
        parser.error("--text, --voice-id, and --output are required outside worker mode")
    return args


def run_worker(args: argparse.Namespace) -> int:
    protocol_out = sys.stdout
    sys.stdout = sys.stderr

    root = args.root.resolve()
    model_dir = args.model_dir.resolve()
    presets_path = args.presets.resolve()
    add_cosyvoice_paths(root)
    patch_modelscope_snapshot()

    import torch
    import torchaudio
    from cosyvoice.cli.cosyvoice import CosyVoice2
    from cosyvoice.utils.common import set_all_random_seed

    print("[EchoFrame TTS] loading CosyVoice2...", file=sys.stderr, flush=True)
    cosyvoice = CosyVoice2(
        str(model_dir),
        load_jit=False,
        load_trt=False,
        load_vllm=False,
        fp16=args.fp16,
    )
    print(f"[EchoFrame TTS] loaded sr={cosyvoice.sample_rate}", file=sys.stderr, flush=True)
    worker_write(protocol_out, {"event": "ready", "ok": True})
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            job = json.loads(line)
            if job.get("action") == "stop":
                worker_write(protocol_out, {"event": "stopped", "ok": True})
                break
            generate_to_file(
                cosyvoice=cosyvoice,
                torch_module=torch,
                torchaudio_module=torchaudio,
                presets_path=presets_path,
                voice_id=job["voice_id"],
                text=job["text"],
                instruct=job.get("instruct", ""),
                speed=float(job.get("speed", 1.0)),
                output=Path(job["output"]).resolve(),
                set_seed=set_all_random_seed,
                text_frontend=args.text_frontend,
            )
            worker_write(protocol_out, {"job_id": job.get("job_id"), "ok": True})
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            worker_write(protocol_out, {"job_id": job.get("job_id") if "job" in locals() else None, "ok": False, "error": str(exc)})
    return 0


def add_cosyvoice_paths(root: Path) -> None:
    candidates = [
        root,
        root / "vendor" / "cosyvoice",
        root / "CosyVoice",
    ]
    for candidate in candidates:
        if (candidate / "cosyvoice").exists():
            sys.path.insert(0, str(candidate))
            matcha = candidate / "third_party" / "Matcha-TTS"
            if matcha.exists():
                sys.path.insert(0, str(matcha))
            return
    raise FileNotFoundError("CosyVoice source tree was not found")


def patch_modelscope_snapshot() -> None:
    try:
        import modelscope
        import modelscope.hub.snapshot_download as snapshot_module
    except Exception:
        return

    original = modelscope.snapshot_download

    def local_first_snapshot_download(model_id, *args, **kwargs):
        cache_root = Path(os.environ.get("MODELSCOPE_CACHE", ""))
        local_dir = cache_root / "hub" / str(model_id)
        if local_dir.exists():
            return str(local_dir)
        kwargs["local_files_only"] = True
        return original(model_id, *args, **kwargs)

    modelscope.snapshot_download = local_first_snapshot_download
    snapshot_module.snapshot_download = local_first_snapshot_download


def load_preset(presets_path: Path, voice_id: str) -> dict:
    data = json.loads(presets_path.read_text(encoding="utf-8"))
    if voice_id not in data:
        raise KeyError(f"unknown voice_id={voice_id}")
    preset = data[voice_id]
    if not preset.get("ref_audio") or not preset.get("ref_text"):
        raise ValueError(f"voice_id={voice_id} is missing ref_audio or ref_text")
    return preset


def generate_to_file(
    *,
    cosyvoice,
    torch_module,
    torchaudio_module,
    presets_path: Path,
    voice_id: str,
    text: str,
    instruct: str,
    speed: float,
    output: Path,
    set_seed,
    text_frontend: bool,
) -> None:
    preset = load_preset(presets_path, voice_id)
    ref_audio = Path(preset["ref_audio"])
    if not ref_audio.is_absolute():
        ref_audio = presets_path.parent / ref_audio
    if not ref_audio.exists():
        raise FileNotFoundError(f"reference audio is missing for voice_id={voice_id}")

    set_seed(random.randint(1, 10**8))
    tts_text = prep_text_for_tts(text)
    instruct = instruct.strip()
    if not instruct and should_use_short_text_instruct(tts_text, preset["ref_text"]):
        instruct = neutral_instruct_for_text(tts_text)
    parts = []
    if instruct:
        directive = to_instruct2_prompt(instruct)
        chunks = cosyvoice.inference_instruct2(
            tts_text,
            directive,
            str(ref_audio),
            stream=False,
            speed=speed,
            text_frontend=text_frontend,
        )
    else:
        chunks = cosyvoice.inference_zero_shot(
            tts_text,
            preset["ref_text"],
            str(ref_audio),
            stream=False,
            speed=speed,
            text_frontend=text_frontend,
        )
    for chunk in chunks:
        parts.append(chunk["tts_speech"])
    if not parts:
        raise RuntimeError("empty output from CosyVoice")

    speech = torch_module.cat(parts, dim=1)
    if speech.abs().max() > 0.8:
        speech = speech / speech.abs().max() * 0.8

    output.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    torchaudio_module.save(buffer, speech, cosyvoice.sample_rate, format="wav")
    output.write_bytes(buffer.getvalue())


def prep_text_for_tts(text: str) -> str:
    clean = re.sub(r"\s+", " ", text.strip())
    clean = re.sub(r"\s+([，。！？；：、,.!?;:])", r"\1", clean)
    if clean and clean[-1] not in "。！？；：,.!?;:":
        clean += "。" if looks_cjk(clean) else "."
    return clean


def should_use_short_text_instruct(tts_text: str, ref_text: str) -> bool:
    text_len = content_len(tts_text)
    ref_len = content_len(ref_text)
    return 0 < text_len < max(8, int(ref_len * 0.5))


def content_len(text: str) -> int:
    return sum(1 for char in text if not char.isspace() and char not in "。！？；：、,.!?;:")


def neutral_instruct_for_text(text: str) -> str:
    return "平稳自然清晰" if looks_cjk(text) else "natural clear"


def looks_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def to_instruct2_prompt(instruct: str) -> str:
    if "<|endofprompt|>" in instruct:
        return instruct
    if instruct.isascii():
        return f"Speak in a {instruct} tone.<|endofprompt|>"
    return f"用{instruct}的语气说<|endofprompt|>"


def worker_write(out, payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False), file=out, flush=True)


if __name__ == "__main__":
    parsed = parse_args()
    if parsed.worker:
        raise SystemExit(run_worker(parsed))
    raise SystemExit(main(parsed))
