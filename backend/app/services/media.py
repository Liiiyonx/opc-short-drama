"""媒体服务：ffmpeg/ffprobe 封装（W4）。

能力：
- probe_duration_ms：探测音频时长（毫秒）
- render_silence_mp3：生成静音 MP3（mock TTS / 占位）
- build_srt：按时间轴行生成 SRT 字幕文本
- concat_audio：多段音频拼接
- scene_frame_png：确定性演示帧（渐变 + 构图 + 镜头信息，替代纯色占位）
- video_qc_report：成片质检（黑帧 / 纯色帧 / 削波 / 音轨 / 时长分辨率）
- burn_video：图片序列 + 音频 + SRT 烧字幕 → MP4（图文动态短剧路线）
"""
import json
import os
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

_FFMPEG = "ffmpeg"
_FFPROBE = "ffprobe"

# 演示帧场景配色（按镜头序号循环）：暗调电影感双色渐变 + 强调色
_SCENE_PALETTES = [
    ("#0B1D3A", "#2B5FA8", "#4FA3E3"),  # 深蓝·都市夜景
    ("#1A0F2E", "#5B2A86", "#B07CE8"),  # 紫夜·悬疑
    ("#2E1065", "#7C3AED", "#C4A6F5"),  # 高紫·逆袭高光
    ("#0F2E1D", "#2F9E6E", "#8CE0B8"),  # 深绿·成长/校园
    ("#3A1D0B", "#C2703A", "#F0B37E"),  # 暖棕·落日/市井
    ("#0B2E2A", "#1F8A70", "#7BD8C0"),  # 青·出海/商务
]


class MediaError(Exception):
    """媒体处理失败（ffmpeg 缺失或执行错误）。"""


def _run(cmd: list[str], stdin_data: bytes | None = None, timeout: int = 120) -> bytes:
    try:
        proc = subprocess.run(
            cmd,
            input=stdin_data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
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


def _run_log(cmd: list[str], timeout: int = 120) -> str:
    """执行命令并返回合并日志文本（stdout+stderr），供解析过滤器输出。

    与 _run 不同：非零退出码不抛错（分析类命令允许部分失败），只回传日志。
    """
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise MediaError("未找到 ffmpeg/ffprobe") from exc
    except subprocess.TimeoutExpired:
        return ""
    return (proc.stderr + proc.stdout).decode("utf-8", "ignore")


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


@lru_cache(maxsize=None)
def _find_font() -> str | None:
    """按平台候选顺序找第一个存在的 CJK/常用字体（drawtext 需要显式 fontfile）。"""
    candidates = [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/PingFang.ttc",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _escape_drawtext(text: str) -> str:
    """drawtext 的 text= 值转义（冒号/引号/反斜杠/百分号）。"""
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
        .replace("\n", " ")
        .strip()
    )


def _filter_path(path: str) -> str:
    """filtergraph 内的文件路径转义（Windows 盘符冒号必须转义，否则被当选项分隔符）。"""
    return path.replace("\\", "/").replace(":", "\\:")


def _clip_text(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    return text[:limit] + ("…" if len(text) > limit else "")


def scene_frame_png(
    index: int,
    width: int = 720,
    height: int = 1280,
    scene: str = "",
    dialogue: str = "",
) -> bytes:
    """确定性演示帧：暗调双色渐变 + 顶/底信息栏 + 噪点纹理 + 镜头标注。

    替代旧纯色占位（纯色帧会拉低成片说服力且过不了质检闸门）。
    无系统字体时退化为纯图形构图（渐变+色带+噪点），依然不是纯色。
    """
    base_c, deep_c, accent = _SCENE_PALETTES[index % len(_SCENE_PALETTES)]
    has_font = _find_font() is not None

    # 底图：优先 gradients 滤镜（ffmpeg 4.4+）；老版本退化为深色底 + 同款色带构图
    if has_font:
        try:
            return _scene_frame(index, width, height, base_c, deep_c, accent, scene, dialogue)
        except MediaError:
            pass  # gradients 滤镜不可用 → 落到 solid 兜底
    return _scene_frame(index, width, height, deep_c, deep_c, accent, scene, dialogue)


def _scene_frame(
    index: int,
    width: int,
    height: int,
    c0: str,
    c1: str,
    accent: str,
    scene: str,
    dialogue: str,
) -> bytes:
    src = (
        f"gradients=s={width}x{height}:c0={c0}:c1={c1}:"
        f"x0=0:y0=0:x1={width}:y1={height}:d=1"
        if c0 != c1
        else f"color=c={c1}:s={width}x{height}:d=1"
    )
    # 构图层：顶部/底部信息栏 + 强调色细线 + 颗粒噪点 + 暗角
    # （像素坐标在 Python 算好，避免 filtergraph 表达式在不同 ffmpeg 版本的求值差异）
    bar_top = max(90, height // 12)
    bar_bottom = max(120, height // 9)
    accent_h = max(4, height // 260)
    filters = [
        f"drawbox=x=0:y=0:w={width}:h={bar_top}:color=black@0.38:t=fill",
        f"drawbox=x=0:y={height - bar_bottom}:w={width}:h={bar_bottom}:color=black@0.5:t=fill",
        f"drawbox=x=0:y={bar_top}:w={width}:h={accent_h}:color={accent}@0.9:t=fill",
        "noise=alls=6:allf=t+u",
        "vignette",
    ]
    font_path = _find_font()
    if font_path:
        font_file = _filter_path(font_path)
        font_size_tag = max(20, height // 40)
        font_size_scene = max(16, height // 52)
        font_size_dialog = max(22, height // 38)
        shot_tag = _escape_drawtext(f"SHOT {index + 1:02d}")
        scene_text = _escape_drawtext(_clip_text(scene, 26))
        dialog_text = _escape_drawtext(_clip_text(dialogue, 30))
        margin = max(18, width // 30)
        filters.extend(
            [
                (
                    f"drawtext=fontfile='{font_file}':text='{shot_tag}'"
                    f":x={margin}:y={margin}:fontsize={font_size_tag}:"
                    "fontcolor=white@0.92"
                ),
                (
                    f"drawtext=fontfile='{font_file}':text='{scene_text}'"
                    f":x={margin}:y={margin + font_size_tag + 8}:fontsize={font_size_scene}:"
                    "fontcolor=white@0.62"
                ),
                (
                    f"drawtext=fontfile='{font_file}':text='{dialog_text}'"
                    f":x={margin}:y={height - bar_bottom - font_size_dialog // 2}"
                    f":fontsize={font_size_dialog}:fontcolor=white@0.95"
                ),
            ]
        )
    return _run(
        [
            _FFMPEG,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            src,
            "-vf",
            ",".join(filters),
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


def placeholder_png(index: int, width: int = 720, height: int = 1280) -> bytes:
    """旧接口兼容层：转发到确定性演示帧（无镜头文案）。"""
    return scene_frame_png(index, width, height)


def video_qc_report(video: bytes) -> dict:
    """成片质检闸门（P0-08）：黑帧 / 纯色占位帧 / 削波 / 音轨 / 时长分辨率。

    返回 {pass, issues, stats}；issues 为空 = 通过。QC 在 worker 内对样片执行，
    非阻塞性问题（分辨率等）记入 stats 不计失败。
    """
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp.write(video)
        tmp_path = Path(tmp.name)
    try:
        # 1) 容器/流信息
        info = json.loads(
            _run(
                [
                    _FFPROBE,
                    "-v",
                    "error",
                    "-show_streams",
                    "-show_format",
                    "-of",
                    "json",
                    str(tmp_path),
                ]
            ).decode("utf-8", "ignore")
        )
        streams = info.get("streams", [])
        v_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
        a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
        duration_s = float(info.get("format", {}).get("duration") or 0)
        stats = {
            "duration_ms": int(duration_s * 1000),
            "width": v_stream.get("width"),
            "height": v_stream.get("height"),
            "video_codec": v_stream.get("codec_name"),
            "has_audio": a_stream is not None,
        }

        issues: list[str] = []
        if duration_s < 0.5:
            issues.append(f"成片时长过短（{duration_s:.2f}s）")
        if duration_s > 900:
            issues.append(f"成片时长异常（{duration_s:.0f}s > 900s）")
        if a_stream is None:
            issues.append("缺少音轨")

        # 2) 画面体检（取前 5s）：黑帧检测 + signalstats 纯色帧检测，单次解码
        #    blackdetect 与 metadata=print 都写 av_log（stderr），用 _run_log 捕获
        frame_log = _run_log(
            [
                _FFMPEG,
                "-hide_banner",
                "-t",
                "5",
                "-i",
                str(tmp_path),
                "-vf",
                "blackdetect=d=0.2:pic_th=0.98,signalstats,metadata=print",
                "-f",
                "null",
                "-",
            ]
        )
        for line in frame_log.splitlines():
            if "black_duration" in line:
                try:
                    dur = float(line.rsplit("black_duration:", 1)[1].split()[0])
                except (ValueError, IndexError):
                    continue
                if dur > 0.3:
                    issues.append(f"开头黑帧超过 0.3s（{dur:.2f}s）")

        # signalstats：任一帧 YMAX-YMIN 过小 = 疑似纯色占位帧
        flat_frames = 0
        y_min = None
        for line in frame_log.splitlines():
            if "lavfi.signalstats.YMIN" in line:
                try:
                    y_min = float(line.rsplit("=", 1)[1])
                except ValueError:
                    y_min = None
            elif "lavfi.signalstats.YMAX" in line and y_min is not None:
                try:
                    y_max = float(line.rsplit("=", 1)[1])
                except ValueError:
                    y_max = None
                else:
                    if (y_max - y_min) < 6:
                        flat_frames += 1
                y_min = None
        if flat_frames:
            issues.append(f"检测到 {flat_frames} 帧疑似纯色占位画面")

        # 3) 音频削波（volumedetect max_volume ≥ -0.2dB 视为削波风险）
        if a_stream is not None:
            vol_log = _run_log(
                [
                    _FFMPEG,
                    "-hide_banner",
                    "-i",
                    str(tmp_path),
                    "-af",
                    "volumedetect",
                    "-f",
                    "null",
                    "-",
                ]
            )
            for line in vol_log.splitlines():
                if "max_volume" in line:
                    try:
                        max_vol = float(line.rsplit(":", 1)[1].replace("dB", "").strip())
                    except ValueError:
                        break
                    if max_vol >= -0.2:
                        issues.append(f"音频削波风险（max {max_vol:.2f}dB）")
                    break

        stats["qc_pass"] = not issues
        return {"pass": not issues, "issues": issues, "stats": stats}
    finally:
        tmp_path.unlink(missing_ok=True)


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
        # 编码超时随音频时长放大（长剧在 4C VPS 上可能远超固定 120s）：
        # 图文合成约 0.3-1x 实时，留 3 倍余量 + 60s 装载
        try:
            audio_dur_s = float(
                _run(
                    [
                        _FFPROBE,
                        "-v",
                        "error",
                        "-show_entries",
                        "format=duration",
                        "-of",
                        "csv=p=0",
                        str(audio_path),
                    ]
                )
                .decode()
                .strip()
            )
        except (MediaError, ValueError, IndexError):
            audio_dur_s = 120.0
        encode_timeout = max(300, int(audio_dur_s * 3) + 60)

        # mp4 muxer 不支持非 seekable 管道输出，落临时文件后再读回
        # -threads 2：max_jobs=4 并发合成时限制单任务线程，防 4C VPS CPU 争抢
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
                "-threads",
                "2",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-shortest",
                "-movflags",
                "+faststart",
                str(out_path),
            ],
            timeout=encode_timeout,
        )
        return out_path.read_bytes()
