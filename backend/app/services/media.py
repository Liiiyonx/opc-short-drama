"""媒体服务：ffmpeg/ffprobe 封装（W4）。

能力：
- probe_duration_ms：探测音频时长（毫秒）
- render_silence_mp3：生成静音 MP3（mock TTS / 占位）
- build_srt：按时间轴行生成 SRT 字幕文本
- concat_audio：多段音频拼接
- placeholder_png：占位图（lavfi 纯色）
- burn_video：图片序列 + 音频 + SRT 烧字幕 → MP4（图文动态短剧路线）
"""
import subprocess
import tempfile
from pathlib import Path

_FFMPEG = "ffmpeg"
_FFPROBE = "ffprobe"

# 占位图配色（按镜头序号循环）
_PLACEHOLDER_COLORS = ["#1F3A5F", "#3A5A40", "#5C3A5F", "#5F4A1F", "#1F5A56", "#5F1F2E"]


class MediaError(Exception):
    """媒体处理失败（ffmpeg 缺失或执行错误）。"""


def _run(cmd: list[str], stdin_data: bytes | None = None) -> bytes:
    try:
        proc = subprocess.run(
            cmd,
            input=stdin_data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
        )
    except FileNotFoundError as exc:
        raise MediaError(
            "未找到 ffmpeg/ffprobe，请先安装（部署机 apt install ffmpeg）"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaError("ffmpeg 执行超时") from exc
    if proc.returncode != 0:
        raise MediaError(
            f"ffmpeg 执行失败：{proc.stderr.decode('utf-8', 'ignore')[:300]}"
        )
    return proc.stdout


def probe_duration_ms(data: bytes, suffix: str = ".mp3") -> int:
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    try:
        out = _run(
            [
                _FFPROBE,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                str(tmp_path),
            ]
        )
        return int(float(out.decode().strip().splitlines()[0]) * 1000)
    finally:
        tmp_path.unlink(missing_ok=True)


def render_silence_mp3(seconds: float) -> bytes:
    return _run(
        [
            _FFMPEG,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=24000:cl=mono",
            "-t",
            f"{seconds:.3f}",
            "-c:a",
            "libmp3lame",
            "-q:a",
            "9",
            "-f",
            "mp3",
            "pipe:1",
        ]
    )


def placeholder_png(index: int, width: int = 720, height: int = 1280) -> bytes:
    color = _PLACEHOLDER_COLORS[index % len(_PLACEHOLDER_COLORS)]
    return _run(
        [
            _FFMPEG,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s={width}x{height}:d=1",
            "-frames:v",
            "1",
            "-c:v",
            "png",
            "-f",
            "image2pipe",
            "-vcodec",
            "png",
            "pipe:1",
        ]
    )


def _srt_ts(ms: int) -> str:
    ms = max(0, int(ms))
    hours, ms = divmod(ms, 3_600_000)
    minutes, ms = divmod(ms, 60_000)
    seconds, ms = divmod(ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{ms:03d}"


def build_srt(cues: list[dict]) -> str:
    """cues: [{start_ms, end_ms, text}] → SRT 文本。"""
    blocks = []
    for i, cue in enumerate(cues, start=1):
        blocks.append(
            f"{i}\n{_srt_ts(cue['start_ms'])} --> {_srt_ts(cue['end_ms'])}\n"
            f"{cue.get('text', '')}\n"
        )
    return "\n".join(blocks)


def concat_audio(parts: list[bytes], suffix: str = ".mp3") -> bytes:
    if len(parts) == 1:
        return parts[0]
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        list_file = tmp_dir / "list.txt"
        lines = []
        for i, part in enumerate(parts):
            part_path = tmp_dir / f"part_{i:04d}{suffix}"
            part_path.write_bytes(part)
            lines.append(f"file '{part_path.as_posix()}'")
        list_file.write_text("\n".join(lines), encoding="utf-8")
        return _run(
            [
                _FFMPEG,
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_file),
                "-c",
                "copy",
                "-f",
                suffix.lstrip("."),
                "pipe:1",
            ]
        )


def _parse_srt_cues(srt_text: str) -> list[tuple[int, int]]:
    """从 SRT 提取 (start_ms, end_ms) 列表。"""
    cues: list[tuple[int, int]] = []
    for block in srt_text.strip().split("\n\n"):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 2 or "-->" not in lines[1]:
            continue
        start_raw, end_raw = [part.strip() for part in lines[1].split("-->")]

        def _to_ms(value: str) -> int:
            hours, minutes, rest = value.split(":")
            seconds, millis = rest.split(",")
            return (
                int(hours) * 3_600_000
                + int(minutes) * 60_000
                + int(seconds) * 1000
                + int(millis)
            )

        cues.append((_to_ms(start_raw), _to_ms(end_raw)))
    return cues


def burn_video(
    images: list[bytes],
    audio: bytes,
    srt_text: str,
    width: int = 720,
    height: int = 1280,
) -> bytes:
    """图片序列 + 音频 + 烧字幕 → MP4。

    每张图时长取 SRT 对应 cue 时长；图数与 cue 数不一致时均分音频时长。
    """
    if not images:
        raise MediaError("burn_video 需要至少一张图片")
    cues = _parse_srt_cues(srt_text)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for i, image in enumerate(images):
            (tmp_dir / f"img_{i:04d}.png").write_bytes(image)
        audio_path = tmp_dir / "audio.mp3"
        audio_path.write_bytes(audio)
        srt_path = tmp_dir / "sub.srt"
        srt_path.write_text(srt_text, encoding="utf-8")

        list_file = tmp_dir / "list.txt"
        lines = []
        for i in range(len(images)):
            if i < len(cues):
                duration = max(0.5, (cues[i][1] - cues[i][0]) / 1000)
            else:
                duration = 3.0
            lines.append(f"file 'img_{i:04d}.png'")
            lines.append(f"duration {duration:.3f}")
        # concat demuxer 需要最后一张图再重复一次（不加 duration）
        lines.append(f"file 'img_{len(images) - 1:04d}.png'")
        list_file.write_text("\n".join(lines), encoding="utf-8")

        srt_escaped = str(srt_path).replace("\\", "/").replace(":", "\\:")
        out_path = tmp_dir / "output.mp4"
        # mp4 muxer 不支持非 seekable 管道输出，落临时文件后再读回
        _run(
            [
                _FFMPEG,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_file),
                "-i",
                str(audio_path),
                "-vf",
                (
                    f"subtitles='{srt_escaped}',"
                    f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                    f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
                    "format=yuv420p"
                ),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-shortest",
                "-movflags",
                "+faststart",
                str(out_path),
            ]
        )
        return out_path.read_bytes()
