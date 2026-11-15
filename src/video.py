"""Ghép ảnh panel và audio thành video YouTube hoặc Shorts."""

from __future__ import annotations

import os
import shutil
import subprocess

import cv2

from src.images import imread, write_png
from src.textutil import sample_even, sentence_cues, write_srt

_FFMPEG = None


def ffmpeg_bin() -> str:
    global _FFMPEG
    if _FFMPEG:
        return _FFMPEG
    found = shutil.which("ffmpeg")
    if found:
        _FFMPEG = found
        return found
    import imageio_ffmpeg

    _FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
    return _FFMPEG


def resolution_of(name: str, video_format: str) -> tuple[int, int]:
    table = {
        "720p": {"youtube": (1280, 720), "shorts": (720, 1280)},
        "1080p": {"youtube": (1920, 1080), "shorts": (1080, 1920)},
    }
    return table.get(name, table["720p"]).get(video_format, (1280, 720))


def audio_duration(path: str) -> float:
    import soundfile as sf

    return float(sf.info(path).duration)


def _run(args: list[str]) -> tuple[bool, str]:
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL)
    error = proc.stderr.decode("utf-8", errors="replace")
    return proc.returncode == 0, error[-2500:]


def _escape_filter_path(path: str) -> str:
    return os.path.abspath(path).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def _font() -> tuple[str | None, str]:
    candidates = [
        ("/usr/share/fonts/truetype/dejavu", "DejaVu Sans"),
        ("/usr/share/fonts/dejavu", "DejaVu Sans"),
        ("/System/Library/Fonts/Supplemental", "Arial"),
        ("/Library/Fonts", "Arial"),
    ]
    for folder, name in candidates:
        if os.path.isdir(folder):
            return folder, name
    return None, "Arial"


def _cover(image, width: int, height: int):
    ih, iw = image.shape[:2]
    if iw > 800:
        scale = 800 / float(iw)
        image = cv2.resize(image, (800, max(1, int(ih * scale))), interpolation=cv2.INTER_AREA)
        ih, iw = image.shape[:2]
    scale = max(width / float(iw), height / float(ih))
    resized = cv2.resize(
        image,
        (max(1, int(iw * scale)), max(1, int(ih * scale))),
        interpolation=cv2.INTER_AREA,
    )
    x = max(0, (resized.shape[1] - width) // 2)
    y = max(0, (resized.shape[0] - height) // 2)
    return resized[y : y + height, x : x + width]


def _contain(image, width: int, height: int):
    ih, iw = image.shape[:2]
    scale = min(width / float(iw), height / float(ih))
    size = (max(1, int(iw * scale)), max(1, int(ih * scale)))
    return cv2.resize(image, size, interpolation=cv2.INTER_AREA)


def compose_canvas(image_path: str, width: int, height: int, dest: str) -> str:
    image = imread(image_path)
    background = _cover(image, width, height)
    small = cv2.resize(background, (max(1, width // 8), max(1, height // 8)), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), 3)
    background = cv2.resize(small, (width, height), interpolation=cv2.INTER_LINEAR)
    background = cv2.convertScaleAbs(background, alpha=0.45, beta=0)
    foreground = _contain(image, int(width * 0.90), int(height * 0.90))
    canvas = background.copy()
    y = max(0, (height - foreground.shape[0]) // 2)
    x = max(0, (width - foreground.shape[1]) // 2)
    foreground = foreground[: height - y, : width - x]
    canvas[y : y + foreground.shape[0], x : x + foreground.shape[1]] = foreground
    write_png(canvas, dest)
    return dest


def _split_duration(total: float, count: int) -> list[float]:
    if count <= 1:
        return [total]
    base = total / count
    durations = [base] * (count - 1)
    durations.append(max(0.05, total - base * (count - 1)))
    return durations


def _subtitle_clause(srt_path: str, width: int, height: int) -> str:
    folder, font = _font()
    font_size = 18 if height <= 720 else 22
    margin_v = 110 if height > width else 42
    if height > width:
        font_size += 4
    style = (
        f"FontName={font},FontSize={font_size},PrimaryColour=&H00FFFFFF,"
        f"OutlineColour=&H00000000,BorderStyle=3,Outline=1,Shadow=0,Alignment=2,"
        f"MarginV={margin_v},MarginL=36,MarginR=36"
    )
    fonts = f":fontsdir='{_escape_filter_path(folder)}'" if folder else ""
    return f"[base]subtitles='{_escape_filter_path(srt_path)}'{fonts}:force_style='{style}'[vout]"


def _build_command(frames, durations, audio, srt, dest, width, height, fps, ken_burns) -> list[str]:
    binary = ffmpeg_bin()
    duration = sum(durations)
    burns = bool(ken_burns and len(frames) == 1)
    if burns:
        frame_count = max(1, int(round(duration * fps)))
        graph = (
            f"[0:v]zoompan=z='min(zoom+0.0012,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={frame_count}:s={width}x{height}:fps={fps},format=yuv420p[base]"
        )
        inputs = [binary, "-y", "-loop", "1", "-framerate", str(fps), "-i", frames[0], "-i", audio]
        audio_index = 1
    else:
        inputs = [binary, "-y"]
        parts = []
        for index, (frame, frame_duration) in enumerate(zip(frames, durations)):
            inputs.extend(["-loop", "1", "-t", f"{max(frame_duration, 0.05):.3f}", "-i", frame])
            parts.append(
                f"[{index}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps={fps},"
                f"trim=duration={max(frame_duration, 0.05):.3f},setpts=PTS-STARTPTS,format=yuv420p[p{index}]"
            )
        joined = "".join(f"[p{index}]" for index in range(len(frames)))
        parts.append(f"{joined}concat=n={len(frames)}:v=1:a=0[base]")
        graph = ";".join(parts)
        inputs.extend(["-i", audio])
        audio_index = len(frames)
    graph += ";" + (_subtitle_clause(srt, width, height) if srt else "[base]format=yuv420p[vout]")
    return inputs + [
        "-filter_complex",
        graph,
        "-map",
        "[vout]",
        "-map",
        f"{audio_index}:a:0",
        "-t",
        f"{duration:.3f}",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "21",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-ar",
        "48000",
        "-ac",
        "1",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        dest,
    ]


def _render_clip(frames, durations, audio, srt, dest, width, height, fps, ken_burns, log) -> None:
    attempts: list[tuple[bool, str | None]] = []

    def add(burns: bool, sub: str | None) -> None:
        item = (burns, sub)
        if item not in attempts:
            attempts.append(item)

    single = len(frames) == 1
    if ken_burns and single:
        add(True, srt)
    add(False, srt)
    if srt:
        if ken_burns and single:
            add(True, None)
        add(False, None)

    last_error = "ffmpeg thất bại"
    warned: set[str] = set()
    for burns, sub in attempts:
        ok, error = _run(_build_command(frames, durations, audio, sub, dest, width, height, fps, burns))
        if ok:
            return
        last_error = error or last_error
        lower = last_error.lower()
        if sub and any(token in lower for token in ("subtitle", "font", "glyph", "ass filter")) and "sub" not in warned:
            warned.add("sub")
            log("Phụ đề chưa burn được, sẽ thử cách khác.")
        elif burns and "zoom" not in warned:
            warned.add("zoom")
            log("Ken Burns chưa chạy, sẽ thử cảnh tĩnh.")
    raise RuntimeError(last_error)


def _concat(clips: list[str], dest: str, log) -> None:
    list_path = dest + ".txt"
    with open(list_path, "w", encoding="utf-8") as handle:
        for clip in clips:
            path = os.path.abspath(clip).replace("'", r"'\''")
            handle.write(f"file '{path}'\n")
    binary = ffmpeg_bin()
    ok, error = _run(
        [binary, "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", "-movflags", "+faststart", dest]
    )
    if ok:
        return
    log("Ghép nhanh không xong, encode lại toàn bộ.")
    ok, error = _run(
        [
            binary,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            list_path,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "21",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            dest,
        ]
    )
    if not ok:
        raise RuntimeError(error or "Không ghép được các cảnh.")


def _mix_bgm(video: str, bgm: str, volume: float, dest: str) -> None:
    ok, error = _run(
        [
            ffmpeg_bin(),
            "-y",
            "-i",
            video,
            "-stream_loop",
            "-1",
            "-i",
            bgm,
            "-filter_complex",
            f"[1:a]volume={max(0.0, float(volume)):.3f}[bgm];[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[a]",
            "-map",
            "0:v",
            "-map",
            "[a]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-shortest",
            "-movflags",
            "+faststart",
            dest,
        ]
    )
    if not ok:
        raise RuntimeError(error or "Không trộn được nhạc nền.")


def render_video(
    scenes: list[dict],
    output_path: str,
    *,
    video_format: str = "youtube",
    resolution: str = "720p",
    slideshow: bool = True,
    ken_burns: bool = True,
    burn_subtitles: bool = True,
    bgm_path: str | None = None,
    bgm_volume: float = 0.12,
    fps: int = 24,
    log=None,
    progress=None,
) -> tuple[str, str]:
    log = log or (lambda _message: None)
    progress = progress or (lambda _fraction, desc=None: None)
    width, height = resolution_of(resolution, video_format)
    work = os.path.join(os.path.dirname(os.path.abspath(output_path)), "clips")
    frames_dir = os.path.join(os.path.dirname(os.path.abspath(output_path)), "frames")
    os.makedirs(work, exist_ok=True)
    os.makedirs(frames_dir, exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    clips = []
    global_cues = []
    clock = 0.0
    total = max(len(scenes), 1)
    for index, scene in enumerate(scenes):
        progress(0.5 + 0.45 * index / total, desc=f"Dựng cảnh {index + 1}/{len(scenes)}")
        images = [path for path in (scene.get("images") or []) if path and os.path.isfile(path)]
        audio = scene.get("audio")
        if not images or not audio or not os.path.isfile(audio):
            continue
        duration = max(audio_duration(audio), 0.4)
        chosen = sample_even(images, 4 if slideshow else 1)
        composed = [
            compose_canvas(image, width, height, os.path.join(frames_dir, f"s{index:03d}_{frame_index:02d}.png"))
            for frame_index, image in enumerate(chosen)
        ]
        durations = _split_duration(duration, len(composed))
        narration = (scene.get("narration") or "").strip()
        srt = None
        if burn_subtitles and narration:
            srt = os.path.join(work, f"clip_{index:03d}.srt")
            write_srt(sentence_cues(narration, 0.0, duration), srt)
            global_cues.extend(sentence_cues(narration, clock, clock + duration))
        clock += duration
        dest = os.path.join(work, f"clip_{index:03d}.mp4")
        _render_clip(
            composed,
            durations,
            audio,
            srt,
            dest,
            width,
            height,
            fps,
            ken_burns and len(composed) == 1,
            log,
        )
        clips.append(dest)

    if not clips:
        raise RuntimeError("Không có cảnh nào để ghép. Hãy viết lời review trước.")
    srt_path = os.path.splitext(output_path)[0] + ".srt"
    write_srt(global_cues, srt_path)
    has_bgm = bool(bgm_path and os.path.isfile(bgm_path))
    if len(clips) == 1 and not has_bgm:
        shutil.copy2(clips[0], output_path)
    else:
        silent_target = output_path if not has_bgm else output_path + ".nobgm.mp4"
        _concat(clips, silent_target, log)
        if has_bgm:
            log("Trộn nhạc nền.")
            _mix_bgm(silent_target, bgm_path, bgm_volume, output_path)
    progress(1, desc="Xong video")
    log(f"Video: {output_path}")
    return output_path, srt_path
