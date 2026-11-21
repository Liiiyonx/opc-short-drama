"""答辩样片生成器（P0-08 第二周：高质量视觉样片流水线）。

把「剧本 → 分镜图 → 配音 → 字幕 → 动态成片」做成确定性可复现的脚本流水线：

    scenarios/<name>/input.json      # 剧本/角色卡/镜头表/配音配置（手写，可审计）
        → images/shot_NN.png         # 程序化场景图（ffmpeg gradients + 构图模板，非纯色）
        → audio/voice_NN.mp3         # edge-tts 真实配音（逐镜）
        → subtitles.srt              # 镜头级字幕（安全区内）
        → final.mp4                  # 1080×1920 Ken Burns 动态 + 交叉溶解 + 配音 + 低音量氛围垫乐
        → qc-report.json             # 复用 app.services.media 的成片质检闸门
        → license-manifest.json      # 全素材来源/许可证/生成参数（合规口径）

用法（backend/ 目录）：
    python -m scripts.generate_scenario ../scenarios/north-america-revenge
    python -m scripts.generate_scenario --all

所有素材均为程序化生成或 edge-tts 合成（授权清晰），不含任何第三方版权素材。
真实图像生成模型接入后，仅需替换 images/ 生成函数（见 P1 分镜图生成）。
"""
import asyncio
import json
import random
import sys
import time
from pathlib import Path

from app.services.media import (
    _find_font,
    _run,
    probe_duration_ms,
    video_qc_report,
)

BASE = Path(__file__).resolve().parent.parent.parent  # 仓库根
FPS = 30
FADE = 0.4  # 交叉溶解时长（秒）
HEAD_PAD = 0.15  # 每镜配音前静音
TAIL_MIN = 0.3  # 每镜配音后最小静音

# 氛围垫乐根音（按题材情绪，Hz）：逆袭 A、电商 G、文化 C
_ROOT_BY_MOOD = {"tense": 110.0, "warm": 98.0, "serene": 130.81}


# ---------------------------------------------------------------- 场景图模板
# 每个模板返回 drawbox/drawtext 过滤链（在 gradients 底图上作画）。
# 全部像素坐标在 Python 计算 —— 避免 filtergraph 表达式的版本差异。

def _rect(x, y, w, h, color, alpha=1.0):
    a = f"@{alpha}" if alpha < 1.0 else ""
    return f"drawbox=x={x}:y={y}:w={w}:h={h}:color={color}{a}:t=fill"


def _moon(rng):
    """月亮：亮核 + 双层光晕（矩形近似，夜间场景通用）。"""
    mx = rng.randint(140, 940)
    my = rng.randint(160, 520)
    return [
        _rect(mx - 26, my - 26, 78, 78, "#FFF4D6", 0.10),
        _rect(mx - 12, my - 12, 50, 50, "#FFF4D6", 0.22),
        _rect(mx, my, 26, 26, "#FFF9E8", 0.95),
    ]


def _tpl_skyline(rng, palette):
    """夜景都市：天空渐变 + 建筑剪影 + 零散窗灯 + 星点 + 月。"""
    c_top, c_horizon, accent = palette
    W, H = 1080, 1920
    parts = []
    parts.extend(_moon(rng))
    # 星点（上半屏）
    for _ in range(46):
        x, y = rng.randint(20, W - 24), rng.randint(60, 900)
        parts.append(_rect(x, y, rng.randint(2, 4), rng.randint(2, 4), "#FFFFFF", rng.uniform(0.25, 0.7)))
    # 天际线建筑
    x = -rng.randint(0, 60)
    while x < W:
        bw = rng.randint(90, 190)
        bh = rng.randint(520, 1010)
        parts.append(_rect(x, H - bh - 120, bw, bh, "#0A0E18", 0.96))
        # 窗灯
        for _ in range(rng.randint(4, 12)):
            wx = x + rng.randint(8, max(9, bw - 26))
            wy = H - bh - 120 + rng.randint(14, max(15, bh - 40))
            if wx < x + bw - 18 and wy < H - 160:
                parts.append(_rect(wx, wy, 10, 14, accent, rng.uniform(0.5, 0.95)))
        x += bw + rng.randint(6, 30)
    parts.append(_rect(0, H - 120, W, 120, "#05070D", 1.0))
    parts.append(_rect(0, 0, W, H, c_horizon, 0.10))  # 地平线暖色氛围罩
    return parts


def _tpl_office(rng, palette):
    """办公室内景：墙面 + 大窗框 + 窗外迷你天际线 + 桌面剪影。"""
    c_top, c_horizon, accent = palette
    W, H = 1080, 1920
    parts = []
    # 窗外天际线（先画，位于窗框内）
    wx0, wy0, ww, wh = 120, 420, 840, 700
    for _ in range(7):
        bw = rng.randint(70, 120)
        bx = wx0 + rng.randint(0, ww - bw)
        bh = rng.randint(180, 420)
        parts.append(_rect(bx, wy0 + wh - bh, bw, bh, "#131B2E", 0.95))
        for _ in range(rng.randint(2, 6)):
            parts.append(_rect(
                bx + rng.randint(6, max(7, bw - 16)),
                wy0 + wh - bh + rng.randint(10, max(11, bh - 30)),
                7, 10, accent, rng.uniform(0.6, 0.95)))
    # 窗框 + 十字棂
    parts.append(_rect(wx0 - 14, wy0 - 14, ww + 28, wh + 28, "#1B2540", 1.0))
    parts.append(_rect(wx0, wy0, ww, wh, "#22304F", 0.22))  # 玻璃反光
    parts.append(_rect(wx0 + ww // 2 - 6, wy0, 12, wh, "#1B2540", 1.0))
    parts.append(_rect(wx0, wy0 + wh // 2 - 6, ww, 12, "#1B2540", 1.0))
    # 墙面氛围 + 桌面
    parts.append(_rect(0, 1500, W, H - 1500, "#141C30", 0.98))
    parts.append(_rect(0, 1460, W, 44, "#2A3860", 1.0))
    # 台灯暖光
    parts.append(_rect(rng.randint(560, 800), 1290, 130, 170, c_horizon, 0.30))
    return parts


def _tpl_rooftop(rng, palette):
    """天台黄昏：月 + 远景色平线 + 护栏剪影。"""
    c_top, c_horizon, accent = palette
    W, H = 1080, 1920
    parts = []
    parts.extend(_moon(rng))
    # 远景城市带
    for _ in range(12):
        bw = rng.randint(50, 110)
        bx = rng.randint(0, W - bw)
        bh = rng.randint(60, 200)
        parts.append(_rect(bx, 1010 - bh, bw, bh, "#111A2C", 0.9))
    parts.append(_rect(0, 1000, W, 16, accent, 0.5))  # 地平线光带
    # 护栏
    parts.append(_rect(0, 1400, W, 26, "#0A0E18", 1.0))
    for px in range(0, W + 90, 90):
        parts.append(_rect(px, 1400, 18, 400, "#0A0E18", 1.0))
    parts.append(_rect(0, 1786, W, 134, "#05070D", 1.0))
    return parts


def _tpl_market(rng, palette):
    """市集/小店：雨棚条纹 + 成排摊位货架 + 串灯 + 地面。"""
    c_top, c_horizon, accent = palette
    W, H = 1080, 1920
    parts = []
    awning_colors = ["#C96F4A", "#3E8E7E", "#D9C8A9", "#8A4B5C"]
    # 雨棚（上 1/3 处）
    x = 0
    while x < W:
        parts.append(_rect(x, 500, 66, 150, awning_colors[x // 66 % len(awning_colors)], 0.96))
        x += 66
    parts.append(_rect(0, 646, W, 30, "#141C30", 1.0))
    # 两排串灯
    for row_y in (430, 720):
        for lx in range(40, W, 84):
            parts.append(_rect(lx, row_y, 12, 16, "#FFD98A", rng.uniform(0.75, 0.95)))
    # 成排摊位（铺满中下部，高低起伏）
    x = -rng.randint(0, 40)
    while x < W:
        bw = rng.randint(170, 260)
        bh = rng.randint(380, 620)
        parts.append(_rect(x, 1660 - bh, bw, bh, "#10151F", 0.97))
        # 货架横板 + 货品色块
        shelf_y = 1660 - bh + 60
        parts.append(_rect(x + 12, shelf_y, bw - 24, 16, c_horizon, 0.6))
        for _ in range(rng.randint(2, 4)):
            parts.append(_rect(
                x + rng.randint(16, max(17, bw - 60)), shelf_y - rng.randint(30, 60),
                rng.randint(26, 44), rng.randint(24, 30),
                ["#C96F4A", "#3E8E7E", "#D9C8A9", "#8A4B5C"][rng.randrange(4)], 0.85))
        x += bw + rng.randint(8, 26)
    # 地面
    parts.append(_rect(0, 1640, W, 280, "#05070D", 1.0))
    parts.append(_rect(0, 1640, W, 12, accent, 0.25))
    return parts


def _tpl_containers(rng, palette):
    """港口集装箱：堆垛色块 + 龙门吊剪影 + 水面反光。"""
    c_top, c_horizon, accent = palette
    W, H = 1080, 1920
    parts = []
    container_colors = ["#2F6F8F", "#B85C4A", "#1F4E5F", "#8A6E3E", "#4A5D23"]
    y = 1080
    for tier in range(3):
        x = -rng.randint(0, 40)
        while x < W:
            cw, ch = rng.randint(200, 320), 150
            parts.append(_rect(x, y - ch, cw, ch - 6, container_colors[rng.randrange(len(container_colors))], 0.97))
            parts.append(_rect(x, y - ch, cw, 8, "#000000", 0.35))
            x += cw + rng.randint(4, 14)
        y -= 150
    # 龙门吊
    cx = rng.randint(120, 300)
    parts.append(_rect(cx, 300, 34, 800, "#0A0E18", 1.0))
    parts.append(_rect(cx, 300, rng.randint(420, 640), 30, "#0A0E18", 1.0))
    parts.append(_rect(cx + rng.randint(200, 400), 330, 8, 120, "#0A0E18", 1.0))
    # 水面与反光
    parts.append(_rect(0, 1540, W, H - 1540, "#0B1626", 1.0))
    for _ in range(26):
        rx = rng.randint(0, W - 90)
        ry = rng.randint(1560, H - 40)
        parts.append(_rect(rx, ry, rng.randint(50, 130), 6, accent, rng.uniform(0.15, 0.45)))
    return parts


_TEMPLATES = {
    "skyline": _tpl_skyline,
    "office": _tpl_office,
    "rooftop": _tpl_rooftop,
    "market": _tpl_market,
    "containers": _tpl_containers,
}


def scene_image(template: str, palette, seed: int, out_path: Path) -> None:
    """单镜场景图：gradients 底图 + 模板构图 + 颗粒 + 暗角 → PNG。"""
    rng = random.Random(seed)
    c0, c1, _accent = palette[0], palette[1], palette[2]
    parts = _TEMPLATES[template](rng, palette)
    parts.extend(["noise=alls=5:allf=t+u", "vignette"])
    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i",
        f"gradients=s=1080x1920:c0={c0}:c1={c1}:x0=0:y0=0:x1=0:y1=1920:d=1",
        "-vf", ",".join(parts),
        "-frames:v", "1", "-c:v", "png", str(out_path),
    ], timeout=120)


# ---------------------------------------------------------------- 配音

async def _tts_segment(text: str, voice_id: str, rate: str, out_path: Path) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(text, voice_id, rate=rate)
    await communicate.save(str(out_path))


# ---------------------------------------------------------------- 镜头剪辑

_KEN_BURNS = {
    "push_in":  lambda total: (f"min(1+0.12*on/{total},1.12)", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
    "pull_out": lambda total: (f"max(1.12-0.12*on/{total},1.0)", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
    "pan_left": lambda total: ("1.08", f"(iw-iw/zoom)*(1-on/{total})", "ih/2-(ih/zoom/2)"),
    "pan_right": lambda total: ("1.08", f"(iw-iw/zoom)*(on/{total})", "ih/2-(ih/zoom/2)"),
}


def render_clip(image_path: Path, duration: float, camera_move: str, out_path: Path) -> None:
    """单镜动态剪辑：放大 2x 抑制抖动 → zoompan 运镜 → H.264。"""
    total = max(2, round(duration * FPS))
    z, x, y = _KEN_BURNS.get(camera_move, _KEN_BURNS["push_in"])(total)
    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-loop", "1", "-framerate", str(FPS), "-t", f"{duration:.3f}", "-i", str(image_path),
        "-vf",
        (
            "scale=2160:3840:flags=lanczos,"
            f"zoompan=z='{z}':x='{x}':y='{y}':d=1:s=1080x1920:fps={FPS},"
            "format=yuv420p"
        ),
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        str(out_path),
    ], timeout=300)


# ---------------------------------------------------------------- 主流程

def _seg_ms(path: Path) -> float:
    return probe_duration_ms(path.read_bytes(), ".mp3") / 1000.0


def _srt_ts(sec: float) -> str:
    ms = max(0, int(sec * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


async def generate(scenario_dir: Path) -> dict:
    t_start = time.time()
    input_path = scenario_dir / "input.json"
    spec = json.loads(input_path.read_text(encoding="utf-8"))
    images_dir = scenario_dir / "images"
    audio_dir = scenario_dir / "audio"
    images_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)

    width, height = spec.get("aspect", [1080, 1920])
    assert (width, height) == (1080, 1920), "样片统一 1080×1920（答辩口径）"
    voice_cfg = spec["voice"]
    shots = spec["shots"]
    assert len(shots) >= 6, "答辩标准：至少 6 个镜头"
    palette_map = {s["id"]: s["palette"] for s in spec["scenes"]}
    template_map = {s["id"]: s["template"] for s in spec["scenes"]}

    manifest = {
        "scenario": spec["id"],
        "title": spec["title"],
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "assets": [],
    }

    # 1) 逐镜：场景图 + 配音
    print(f"[scenario] {spec['id']} · {len(shots)} 镜")
    voice_durs = []
    for i, shot in enumerate(shots, start=1):
        img = images_dir / f"shot_{i:02d}.png"
        scene_image(template_map[shot["scene_id"]], palette_map[shot["scene_id"]],
                    seed=hash((spec["id"], i)) & 0xFFFF, out_path=img)
        manifest["assets"].append({
            "file": f"images/shot_{i:02d}.png", "type": "image",
            "source": "procedural-ffmpeg", "license": "generated (no third-party assets)",
            "template": template_map[shot["scene_id"]], "palette": palette_map[shot["scene_id"]],
            "prompt": shot.get("visual_note", ""),
        })
        seg = audio_dir / f"voice_{i:02d}.mp3"
        await _tts_segment(shot["dialogue"], voice_cfg["voice_id"], voice_cfg.get("rate", "+0%"), seg)
        voice_durs.append(_seg_ms(seg))
        manifest["assets"].append({
            "file": f"audio/voice_{i:02d}.mp3", "type": "audio",
            "source": f"edge-tts {voice_cfg['voice_id']}",
            "license": "Microsoft Edge TTS 语音合成（演示用途）",
            "text": shot["dialogue"],
        })
        print(f"  shot {i:02d} ✓ 图 + 配音 {voice_durs[-1]:.2f}s")

    # 2) 镜头时长与时间轴（含 xfade 重叠补偿）
    durations = [
        max(2.0, HEAD_PAD + v + TAIL_MIN, shot.get("duration_hint", 0))
        for shot, v in zip(shots, voice_durs)
    ]
    starts = []  # 每镜「完全可见」起点（= 前一镜溶解结束点）
    total = durations[0]
    starts.append(0.0)
    for k in range(1, len(durations)):
        offset = total - FADE
        starts.append(offset)
        total = offset + durations[k]

    # 3) SRT（安全区：底部 300px 上方，短句）
    srt_lines = []
    for i, (shot, v) in enumerate(zip(shots, voice_durs)):
        cue_start = starts[i] + HEAD_PAD
        cue_end = min(cue_start + v + 0.25, starts[i] + durations[i] - FADE - 0.1)
        srt_lines.append(f"{i + 1}\n{_srt_ts(cue_start)} --> {_srt_ts(max(cue_end, cue_start + 0.8))}\n{shot['dialogue']}\n")
    (scenario_dir / "subtitles.srt").write_text("\n".join(srt_lines), encoding="utf-8")
    manifest["assets"].append({"file": "subtitles.srt", "type": "subtitle", "source": "generated", "license": "generated"})

    # 4) 逐镜动态剪辑
    clips = []
    for i, (shot, dur) in enumerate(zip(shots, durations), start=1):
        clip = audio_dir.parent / f"clip_{i:02d}.mp4"
        render_clip(images_dir / f"shot_{i:02d}.png", dur, shot.get("camera_move", "push_in"), clip)
        clips.append(clip)
        print(f"  clip {i:02d} ✓ {dur:.2f}s {shot.get('camera_move', 'push_in')}")

    # 5) 视频：xfade 交叉溶解链
    n = len(clips)
    inputs = []
    for clip in clips:
        inputs += ["-i", str(clip)]
    fade_labels = {
        "fade", "smoothleft", "smoothright", "circleopen", "fadeblack",
    }
    chain = []
    prev = "[0:v]"
    for k in range(1, n):
        out = f"[v{k}]" if k < n - 1 else "[vsub]"
        trans = shots[k].get("transition", "fade")
        if trans not in fade_labels:
            trans = "fade"
        chain.append(f"{prev}[{k}:v]xfade=transition={trans}:duration={FADE}:offset={starts[k]:.3f}{out}")
        prev = out
    # 烧字幕必须并入复杂滤镜图（-vf 不能作用于 filter_complex 的输出流）。
    # 注意：libass 对 SRT 的脚本分辨率固定为 384×288，所有字号/边距须按该空间换算
    # （FontSize=9 ≈ 1920 高下 60px；MarginV=40 ≈ 底部 267px，处于竖屏安全区内）。
    srt_escaped = str(scenario_dir / "subtitles.srt").replace("\\", "/").replace(":", "\\:")
    subtitle_style = (
        "FontName=Microsoft YaHei,FontSize=9,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&HB4000000,BorderStyle=1,Outline=0.8,Shadow=0,"
        "Bold=1,MarginL=24,MarginR=24,MarginV=40,Alignment=2"
    )
    chain.append(f"[vsub]subtitles='{srt_escaped}':force_style='{subtitle_style}'[vout]")
    video_filter = ";".join(chain)

    # 6) 音频：逐镜段拼接（长度 = 时长 - 溶解补偿） + 氛围垫乐 + 响度规范
    voice_full = audio_dir / "voice_full.wav"
    seg_paths = []
    for i in range(n):
        seg_wav = audio_dir / f"seg_{i:02d}.wav"
        seg_dur = durations[i] - (FADE if i < n - 1 else 0.0)
        _run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(audio_dir / f"voice_{i + 1:02d}.mp3"),
            "-af", (
                f"adelay={int(HEAD_PAD * 1000)}|{int(HEAD_PAD * 1000)},"
                f"apad=whole_dur={seg_dur:.3f},atrim=0:{seg_dur:.3f},"
                "aresample=44100"
            ),
            "-ac", "2", "-c:a", "pcm_s16le", str(seg_wav),
        ], timeout=120)
        seg_paths.append(seg_wav)
    concat_list = audio_dir / "concat.txt"
    concat_list.write_text("\n".join(f"file '{p.name}'" for p in seg_paths), encoding="utf-8")
    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_list),
        "-c:a", "pcm_s16le", str(voice_full),
    ], timeout=120)

    root_hz = _ROOT_BY_MOOD.get(spec.get("mood", "tense"), 110.0)
    bgm = audio_dir / "bgm.wav"
    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i",
        (
            f"aevalsrc='0.05*sin(2*PI*{root_hz}*t)+0.045*sin(2*PI*{root_hz * 1.5}*t)"
            f"+0.04*sin(2*PI*{root_hz * 2}*t)+0.02*sin(2*PI*{root_hz * 3}*t)':s=44100:d={total:.3f}"
        ),
        "-af", "tremolo=f=0.13:d=0.65,lowpass=f=850,afade=t=in:d=1.5,afade=t=out:st=%.3f:d=2.0" % (total - 2.0),
        "-ac", "2", "-c:a", "pcm_s16le", str(bgm),
    ], timeout=120)
    manifest["assets"].append({
        "file": "audio/bgm.wav", "type": "audio", "source": "procedural-ffmpeg (aevalsrc chord pad)",
        "license": "generated",
    })

    mixed = audio_dir / "mix.wav"
    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(voice_full), "-i", str(bgm),
        "-filter_complex",
        f"[0:a][1:a]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=44100",
        "-ac", "2", "-c:a", "pcm_s16le", str(mixed),
    ], timeout=120)

    # 7) 终片：溶解视频（已含烧字幕） + 混音
    final_path = scenario_dir / "final.mp4"
    encode_timeout = max(300, int(total * 4) + 120)
    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        *inputs,
        "-filter_complex", video_filter,
        "-i", str(mixed),
        "-map", "[vout]", "-map", f"{n}:a",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k",
        "-t", f"{total:.3f}", "-movflags", "+faststart",
        str(final_path),
    ], timeout=encode_timeout)
    manifest["assets"].append({"file": "final.mp4", "type": "video", "source": "procedural (ffmpeg xfade + burn-in)",
                               "license": "generated"})

    # 8) 质检闸门（复用 compose 链路的 QC）
    qc = video_qc_report(final_path.read_bytes())
    (scenario_dir / "qc-report.json").write_text(
        json.dumps(qc, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest["qc"] = qc

    # 9) 许可证清单
    (scenario_dir / "license-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # 清理中间剪辑
    for clip in clips:
        clip.unlink(missing_ok=True)
    for p in seg_paths:
        p.unlink(missing_ok=True)
    concat_list.unlink(missing_ok=True)

    print(f"[scenario] {spec['id']} 完成：{total:.1f}s · QC {'PASS' if qc['pass'] else 'FAIL: ' + '; '.join(qc['issues'])}"
          f" · 耗时 {time.time() - t_start:.0f}s")
    if not qc["pass"]:
        raise SystemExit(f"质检未通过：{qc['issues']}")
    return {"total": total, "qc": qc}


def main():
    args = [a for a in sys.argv[1:]]
    scenarios_root = BASE / "scenarios"
    if "--all" in args:
        targets = sorted(p for p in scenarios_root.iterdir() if (p / "input.json").exists())
    else:
        targets = []
        for a in args:
            if a.startswith("--"):
                continue
            p = Path(a)
            # 依次尝试：绝对路径 → 相对当前目录 → 相对仓库根
            for cand in (p, Path.cwd() / p, BASE / p):
                if (cand / "input.json").exists():
                    targets.append(cand.resolve())
                    break
            else:
                print(f"未找到场景目录（需含 input.json）：{a}")
                raise SystemExit(1)
    if not targets:
        print("用法：python -m scripts.generate_scenario <scenario_dir | --all>")
        raise SystemExit(1)
    for t in targets:
        asyncio.run(generate(t))


if __name__ == "__main__":
    main()
