import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from app.config import Settings
from app.paths import command_for_cwd, path_for_cwd
from app.services.run_control import RunState, WorkflowCancelled


class MuseTalkClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def health(self) -> tuple[bool, str]:
        root = self.settings.musetalk_root
        if not root.exists():
            return False, "missing MuseTalk root"
        app_py = root / "app.py"
        script_py = root / "scripts" / "inference.py"
        if not app_py.exists() and not script_py.exists():
            return False, "no app.py or scripts/inference.py"
        missing = []
        for rel in (
            "models/musetalkV15/unet.pth",
            "models/musetalkV15/musetalk.json",
            "models/sd-vae/config.json",
            "models/whisper/config.json",
        ):
            if not (root / rel).exists():
                missing.append(rel)
        if missing:
            return False, "missing model files: " + ", ".join(missing[:4])
        return True, "ready"

    def lip_sync(self, audio_path: Path, video_path: Path, run_dir: Path, run_state: RunState | None = None) -> Path:
        if run_state:
            run_state.check()
        run_dir.mkdir(parents=True, exist_ok=True)
        output_path = run_dir / "talk.mp4"
        root = self.settings.musetalk_root
        script_py = root / "scripts" / "inference.py"
        if script_py.exists():
            self._run_official_cli(audio_path, video_path, output_path, run_dir, run_state)
        else:
            self._run_local_app_runner(audio_path, video_path, output_path, run_state)
        if not output_path.exists():
            raise RuntimeError("MuseTalk finished but output video was not created")
        return output_path

    def _run_local_app_runner(
        self,
        audio_path: Path,
        video_path: Path,
        output_path: Path,
        run_state: RunState | None,
    ) -> None:
        runner = Path(__file__).resolve().parents[2] / "tools" / "run_musetalk_app.py"
        cmd = [
            self.settings.musetalk_python,
            str(runner),
            "--musetalk-root",
            str(self.settings.musetalk_root),
            "--audio",
            str(audio_path),
            "--video",
            str(video_path),
            "--output",
            str(output_path),
            "--bbox-shift",
            str(self.settings.musetalk_bbox_shift),
            "--extra-margin",
            str(self.settings.musetalk_extra_margin),
            "--parsing-mode",
            self.settings.musetalk_parsing_mode,
            "--left-cheek-width",
            str(self.settings.musetalk_left_cheek_width),
            "--right-cheek-width",
            str(self.settings.musetalk_right_cheek_width),
        ]
        if self.settings.musetalk_ffmpeg_dir:
            cmd += ["--ffmpeg-path", self.settings.musetalk_ffmpeg_dir]
        if self.settings.musetalk_use_float16:
            cmd += ["--use-float16"]
        self._run(cmd, cwd=Path.cwd(), timeout=self.settings.musetalk_timeout_seconds, run_state=run_state)

    def _run_official_cli(
        self,
        audio_path: Path,
        video_path: Path,
        output_path: Path,
        run_dir: Path,
        run_state: RunState | None,
    ) -> None:
        root = self.settings.musetalk_root
        work_dir = root / ".echoframe" / run_dir.name
        work_dir.mkdir(parents=True, exist_ok=True)
        work_audio = work_dir / audio_path.name
        work_video = work_dir / video_path.name
        shutil.copy2(audio_path, work_audio)
        shutil.copy2(video_path, work_video)

        cfg_path = work_dir / "musetalk.yaml"
        cfg_path.write_text(
            "task_0:\n"
            f" video_path: \"{path_for_cwd(work_video, root, require_relative=True)}\"\n"
            f" audio_path: \"{path_for_cwd(work_audio, root, require_relative=True)}\"\n"
            f" bbox_shift: {self.settings.musetalk_bbox_shift}\n",
            encoding="utf-8",
        )
        result_dir = work_dir / "musetalk_results"
        cmd = [
            command_for_cwd(self.settings.musetalk_python, root),
            "-m",
            "scripts.inference",
            "--gpu_id",
            self.settings.musetalk_cuda_visible_devices.split(",")[0] if self.settings.musetalk_cuda_visible_devices else "0",
            "--inference_config",
            path_for_cwd(cfg_path, root, require_relative=True),
            "--result_dir",
            path_for_cwd(result_dir, root, require_relative=True),
            "--unet_model_path",
            "models/musetalkV15/unet.pth",
            "--unet_config",
            "models/musetalkV15/musetalk.json",
            "--version",
            "v15",
            "--fps",
            str(self.settings.musetalk_fps),
            "--batch_size",
            str(self.settings.musetalk_batch_size),
            "--extra_margin",
            str(self.settings.musetalk_extra_margin),
            "--parsing_mode",
            self.settings.musetalk_parsing_mode,
            "--left_cheek_width",
            str(self.settings.musetalk_left_cheek_width),
            "--right_cheek_width",
            str(self.settings.musetalk_right_cheek_width),
        ]
        if self.settings.musetalk_use_float16:
            cmd.append("--use_float16")
        if self.settings.musetalk_ffmpeg_dir:
            cmd += ["--ffmpeg_path", path_for_cwd(self.settings.musetalk_ffmpeg_dir, root, require_relative=True)]
        before = time.time()
        self._run(cmd, cwd=root, timeout=self.settings.musetalk_timeout_seconds, run_state=run_state)
        candidates = [
            p
            for p in result_dir.glob("**/*.mp4")
            if p.stat().st_mtime >= before - 1 and p.name != output_path.name
        ]
        if not candidates:
            raise RuntimeError("MuseTalk official CLI produced no mp4")
        latest = max(candidates, key=lambda p: p.stat().st_mtime)
        shutil.copy2(latest, output_path)

    def _run(self, cmd: list[str], cwd: Path, timeout: int, run_state: RunState | None) -> None:
        env = os.environ.copy()
        if self.settings.musetalk_ffmpeg_dir:
            ffmpeg_dir = path_for_cwd(self.settings.musetalk_ffmpeg_dir, cwd)
            env["PATH"] = f"{ffmpeg_dir}{os.pathsep}{env.get('PATH', '')}"
        if self.settings.musetalk_cuda_visible_devices:
            env["CUDA_VISIBLE_DEVICES"] = self.settings.musetalk_cuda_visible_devices
        env["PYTHONPATH"] = (
            f"{path_for_cwd(self.settings.musetalk_root, cwd)}{os.pathsep}{env.get('PYTHONPATH', '')}"
        )
        process = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if run_state:
            run_state.add_process(process)
        start = time.time()
        stdout = ""
        stderr = ""
        try:
            while True:
                if run_state and run_state.cancelled:
                    self._terminate(process)
                    raise WorkflowCancelled("Workflow cancelled")
                if time.time() - start > timeout:
                    self._terminate(process)
                    raise RuntimeError("MuseTalk command timed out")
                try:
                    stdout, stderr = process.communicate(timeout=0.5)
                    break
                except subprocess.TimeoutExpired:
                    continue
        finally:
            if run_state:
                run_state.remove_process(process)
        if process.returncode != 0:
            msg = stderr[-3000:] or stdout[-3000:] or "MuseTalk command failed"
            raise RuntimeError(msg)

    def _terminate(self, process: subprocess.Popen) -> None:
        if process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=5)
        except Exception:
            if process.poll() is None:
                process.kill()
