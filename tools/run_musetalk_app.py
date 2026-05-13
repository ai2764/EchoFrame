import argparse
import os
import shutil
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--musetalk-root", required=True)
    parser.add_argument("--audio", required=True)
    parser.add_argument("--video", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--ffmpeg-path", default="")
    parser.add_argument("--bbox-shift", type=int, default=0)
    parser.add_argument("--extra-margin", type=int, default=10)
    parser.add_argument("--parsing-mode", default="jaw")
    parser.add_argument("--left-cheek-width", type=int, default=90)
    parser.add_argument("--right-cheek-width", type=int, default=90)
    parser.add_argument("--use-float16", action="store_true")
    args = parser.parse_args()

    root = Path(args.musetalk_root).resolve()
    app_py = root / "app.py"
    if not app_py.exists():
        raise FileNotFoundError(app_py)

    if args.ffmpeg_path:
        os.environ["PATH"] = f"{args.ffmpeg_path}{os.pathsep}{os.environ.get('PATH', '')}"

    old_cwd = Path.cwd()
    old_argv = sys.argv[:]
    try:
        os.chdir(root)
        sys.path.insert(0, str(root))
        sys.argv = [str(app_py)]
        if args.ffmpeg_path:
            sys.argv += ["--ffmpeg_path", args.ffmpeg_path]
        if args.use_float16:
            sys.argv += ["--use_float16"]

        source = app_py.read_text(encoding="utf-8")
        marker = "\ncss = "
        idx = source.find(marker)
        if idx < 0:
            raise RuntimeError("could not find Gradio launch marker in MuseTalk app.py")
        ns = {"__file__": str(app_py), "__name__": "__musetalk_batch__"}
        exec(compile(source[:idx], str(app_py), "exec"), ns)
        out_path, _info = ns["inference"](
            str(Path(args.audio).resolve()),
            str(Path(args.video).resolve()),
            args.bbox_shift,
            args.extra_margin,
            args.parsing_mode,
            args.left_cheek_width,
            args.right_cheek_width,
            None,
        )
        dst = Path(args.output).resolve()
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(out_path).resolve(), dst)
        return 0
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)


if __name__ == "__main__":
    raise SystemExit(main())
