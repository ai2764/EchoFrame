from pathlib import Path

from app.config import Settings
from app.services.musetalk import MuseTalkClient


def test_official_musetalk_cli_uses_portable_relative_paths(tmp_path, monkeypatch):
    app_root = tmp_path / "EchoFrame"
    musetalk_root = tmp_path / "engines" / "musetalk"
    run_dir = tmp_path / "data" / "runs" / "run_test"
    app_root.mkdir()
    (musetalk_root / "scripts").mkdir(parents=True)
    run_dir.mkdir(parents=True)
    monkeypatch.chdir(app_root)

    audio = run_dir / "voice.wav"
    video = run_dir / "base.mp4"
    output = run_dir / "talk.mp4"
    audio.write_bytes(b"wav")
    video.write_bytes(b"mp4")

    settings = Settings(
        data_dir=Path("../data"),
        musetalk_root=Path("../engines/musetalk"),
        musetalk_python="../runtime/musetalk-python/python.exe",
        musetalk_ffmpeg_dir="../runtime/ffmpeg",
    )
    client = MuseTalkClient(settings)
    captured = {}

    def fake_run(cmd, cwd, timeout, run_state):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        result_arg = cmd[cmd.index("--result_dir") + 1]
        result_dir = (cwd / result_arg).resolve()
        result_dir.mkdir(parents=True)
        (result_dir / "result.mp4").write_bytes(b"result")

    monkeypatch.setattr(client, "_run", fake_run)

    client._run_official_cli(audio, video, output, run_dir, None)

    cfg_path = musetalk_root / ".echoframe" / run_dir.name / "musetalk.yaml"
    config_text = cfg_path.read_text(encoding="utf-8")
    cmd = captured["cmd"]

    assert output.read_bytes() == b"result"
    assert "video_path: \".echoframe/run_test/base.mp4\"" in config_text
    assert "audio_path: \".echoframe/run_test/voice.wav\"" in config_text
    assert Path(cmd[0]).is_absolute()
    assert Path(cmd[0]).as_posix().endswith("/runtime/musetalk-python/python.exe")
    assert cmd[cmd.index("--inference_config") + 1] == ".echoframe/run_test/musetalk.yaml"
    assert cmd[cmd.index("--result_dir") + 1] == ".echoframe/run_test/musetalk_results"
    assert cmd[cmd.index("--ffmpeg_path") + 1] == "../../runtime/ffmpeg"
    assert str(tmp_path) not in config_text
    assert all(
        not Path(value).is_absolute()
        for value in (
            cmd[cmd.index("--inference_config") + 1],
            cmd[cmd.index("--result_dir") + 1],
            cmd[cmd.index("--ffmpeg_path") + 1],
        )
    )
