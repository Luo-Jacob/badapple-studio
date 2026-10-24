# -*- coding: utf-8 -*-
"""Bad Apple Studio —— 影绘视频换色 / 抠像合成工具

特性:
  1. 模式 A 换色：把影绘视频里的黑/白分别换成任意两种颜色
  2. 模式 B 叠加：把黑（或白）变透明，叠到自己的视频上合成输出
  3. 模式 C 导出：导出抠好透明通道的 GIF / MKV(ffv1)，供二次创作
  4. 实时抽帧预览，参数所见即所得，全部处理走 ffmpeg 滤镜（不依赖 numpy/OpenCV）

依赖:
  ffmpeg 二进制。打包后用随程序的 ffmpeg_bin/*，开发态从 imageio_ffmpeg 取。

隐蔽命令行:
  python badapple_studio.py --selftest [工作目录]   无界面跑一遍管线自检
"""
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

# ---------------------------------------------------------------------------
# 常量与路径
# ---------------------------------------------------------------------------
APP_NAME = "Bad Apple Studio"
APP_VERSION = "1.0.0"

BG = "#f4f6f9"
CARD = "#ffffff"
TEXT = "#1f2937"
MUTED = "#6b7280"
ACCENT = "#2563eb"
DANGER = "#dc2626"
BORDER = "#e5e7eb"

FONT = ("Microsoft YaHei UI", 9)
FONT_B = ("Microsoft YaHei UI", 9, "bold")
FONT_TITLE = ("Microsoft YaHei UI", 13, "bold")

VIDEO_EXT = (".mp4", ".mkv", ".webm", ".mov", ".avi", ".flv", ".m4v", ".ts", ".gif")
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff")
MEDIA_EXT = VIDEO_EXT + IMAGE_EXT


def is_image(path):
    return bool(path) and os.path.splitext(path)[1].lower() in IMAGE_EXT

CREATE_NO_WINDOW = 0
if hasattr(subprocess, "CREATE_NO_WINDOW"):
    CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW")



def base_dir():
    """返回工作根目录：打包态取 exe 所在目录，开发态取 src 的上级"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def program_dir():
    """程序所在目录：打包态 = exe 同级，开发态 = 项目根"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return base_dir()


def material_dir():
    """素材根目录：程序同级的 BadApple 文件夹（不存在时用项目根）"""
    d = os.path.join(program_dir(), "BadApple")
    if os.path.isdir(d):
        return d
    return os.path.join(base_dir(), "BadApple")


def builtin_dir():
    """内置素材目录：打包态在 _internal/builtin，开发态在项目根 assets/builtin"""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        d = os.path.join(meipass, "builtin")
        if os.path.isdir(d):
            return d
    return os.path.join(base_dir(), "assets", "builtin")


def material_sub(name, create=False):
    """素材子目录：片源 / 底层 / 输出"""
    d = os.path.join(material_dir(), name)
    if create:
        os.makedirs(d, exist_ok=True)
    return d


README_TEXT = """Bad Apple Studio —— 素材目录

【片源】放 Bad Apple 影绘视频（黑白的那个），程序启动时自动扫描。
【底层】放要垫在下面的素材，视频和图片都行，程序启动时自动扫描；
        不放也没关系，程序自带三个动态底视频可直接选。
【输出】合成结果默认保存在这里。

想加自己的素材：把文件丢进对应文件夹，回到程序点下拉框旁边的 ↻ 刷新即可。
"""


def ensure_material_tree():
    """确保素材目录结构存在（含一份使用说明），返回素材根目录"""
    root = material_dir()
    for sub in ("片源", "底层", "输出"):
        os.makedirs(os.path.join(root, sub), exist_ok=True)
    readme = os.path.join(root, "使用说明.txt")
    if not os.path.exists(readme):
        try:
            with open(readme, "w", encoding="utf-8") as fp:
                fp.write(README_TEXT)
        except Exception:
            pass
    return root


def builtin_videos():
    """内置底层视频：{显示名: 路径}"""
    d = builtin_dir()
    out = {}
    if os.path.isdir(d):
        for name in sorted(os.listdir(d)):
            if name.lower().endswith(VIDEO_EXT):
                out[os.path.splitext(name)[0]] = os.path.join(d, name)
    return out


def assets_dir():
    """片源目录（兼容旧布局，优先级低于 BadApple/片源）"""
    cands = [os.path.join(material_dir(), "片源"), material_dir()]
    for d in cands:
        if os.path.isdir(d):
            return d
    return cands[0]


ASSETS_DIR = assets_dir()
CONFIG_DIR = os.path.join(base_dir(), "BAlib")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

_FFMPEG = None


def ffmpeg_exe():
    """定位 ffmpeg 可执行文件：优先程序内的 ffmpeg_bin，其次 imageio_ffmpeg"""
    global _FFMPEG
    if _FFMPEG:
        return _FFMPEG
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        d = os.path.join(meipass, "ffmpeg_bin")
        if os.path.isdir(d):
            hits = sorted(
                f for f in os.listdir(d)
                if f.lower().startswith("ffmpeg") and f.lower().endswith(".exe")
            )
            if hits:
                _FFMPEG = os.path.join(d, hits[0])
                return _FFMPEG
    try:
        import imageio_ffmpeg  # noqa: WPS433 打包态不会走到这里
        _FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        _FFMPEG = "ffmpeg"
    return _FFMPEG


def even_size(w, h):
    """尺寸统一取偶数，避免 yuv420p 编码报错"""
    return max(2, int(w) // 2 * 2), max(2, int(h) // 2 * 2)


def hex_to_rgb(v):
    v = (v or "#000000").lstrip("#")
    if len(v) != 6:
        v = "000000"
    try:
        return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)
    except ValueError:
        return 0, 0, 0


def fmt_time(sec):
    try:
        sec = float(sec)
    except Exception:
        return "--:--"
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    if h:
        return "%02d:%02d:%02d" % (h, m, s)
    return "%02d:%02d" % (m, s)


# ---------------------------------------------------------------------------
# 选项容器
# ---------------------------------------------------------------------------
class Options(object):
    """一次合成所需的全部参数"""

    def __init__(self):
        self.mode = "overlay"            # overlay | dual | recolor | alpha
        self.fg = ""                     # Bad Apple 片源（上层）
        self.bg = ""                     # 底层素材 A（黑区显示）
        self.bg2 = ""                    # 底层素材 B（白区显示，仅 dual）
        self.key_target = "black"        # black=黑变透明 / white=白变透明
        self.tolerance = 0.10
        self.softness = 0.03
        self.invert = False
        self.color1 = "#000000"          # 模式 A：黑色区域替换色
        self.color2 = "#ffffff"          # 模式 A：白色区域替换色
        self.fit = "crop"                # crop=裁切填满 pad=完整显示 stretch=拉伸
        self.duration_policy = "loop_bg"  # shortest | loop_bg | loop_fg
        self.audio_policy = "fg"         # fg | bg | bg2 | mix | none
        self.width = 0
        self.height = 0
        self.fps = 0.0
        self.crf = 18
        self.preset = "medium"
        self.export_format = "mp4"       # mp4 | gif | mkv
        self.out = ""

    def copy(self):
        n = Options()
        n.__dict__.update(self.__dict__)
        return n


# ---------------------------------------------------------------------------
# 媒体探测
# ---------------------------------------------------------------------------
_DUR_RE = re.compile(r"Duration:\s*(\d+):(\d+):([\d.]+)")
_STREAM_RE = re.compile(r"Stream #\d+:\d+.*?:\s*(Video|Audio):")
_VIDEO_RE = re.compile(r"Video:.*?,\s*(\d{2,5})x(\d{2,5})")
_FPS_RE = re.compile(r"([\d.]+)\s*fps")


def probe(path):
    """读取视频的基本信息。失败返回 ok=False 与错误信息"""
    info = {"ok": False, "width": 0, "height": 0, "fps": 30.0,
            "duration": 0.0, "has_audio": False, "error": ""}
    if not path or not os.path.exists(path):
        info["error"] = "文件不存在"
        return info
    if is_image(path):
        # 图片：没有时长和帧率，按「无限长」处理，时长由上层策略决定
        try:
            from PIL import Image
            with Image.open(path) as im:
                info["width"], info["height"] = im.size
            info["ok"] = True
            info["duration"] = 0.0
            info["fps"] = 0.0
            info["is_image"] = True
            return info
        except Exception as exc:
            info["error"] = "图片读取失败：" + str(exc)
            return info
    try:
        r = subprocess.run(
            [ffmpeg_exe(), "-hide_banner", "-i", path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            creationflags=CREATE_NO_WINDOW,
        )
    except Exception as exc:
        info["error"] = str(exc)
        return info
    txt = r.stderr or ""
    if "Invalid data found" in txt:
        info["error"] = "无法识别的媒体文件"
        return info
    m = _DUR_RE.search(txt)
    if m:
        info["duration"] = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    for line in txt.splitlines():
        sm = _STREAM_RE.search(line)
        if not sm:
            continue
        kind = sm.group(1)
        if kind == "Video" and not info["width"]:
            vm = _VIDEO_RE.search(line)
            if vm:
                info["width"] = int(vm.group(1))
                info["height"] = int(vm.group(2))
            fm = _FPS_RE.search(line)
            if fm:
                try:
                    info["fps"] = float(fm.group(1))
                except ValueError:
                    pass
        elif kind == "Audio":
            info["has_audio"] = True
    info["ok"] = info["width"] > 0
    info["is_image"] = False
    if not info["ok"] and not info["error"]:
        info["error"] = "没有找到视频流"
    return info


def describe(path):
    if not path:
        return "未选择"
    p = probe(path)
    if not p["ok"]:
        return os.path.basename(path) + "（" + (p["error"] or "读取失败") + "）"
    if p.get("is_image"):
        return "%s · 图片 %dx%d" % (os.path.basename(path), p["width"], p["height"])
    return "%s · %dx%d · %.2f fps · %s" % (
        os.path.basename(path), p["width"], p["height"],
        p["fps"], fmt_time(p["duration"]))


# ---------------------------------------------------------------------------
# 滤镜图构建
# ---------------------------------------------------------------------------
def _fps_expr(v):
    """帧率统一用分数形式，避免浮点被解析成整数"""
    if not v:
        return "30"
    if abs(v - 30000.0 / 1001.0) < 0.01:
        return "30000/1001"
    if abs(v - 24000.0 / 1001.0) < 0.01:
        return "24000/1001"
    return ("%g" % v)


def _normalize(label, w, h, fps, fit, pad_color):
    """把一路视频规整到统一尺寸/帧率"""
    head = "[%s]setpts=PTS-STARTPTS,fps=%s" % (label, _fps_expr(fps))
    if fit == "stretch":
        return head + ",scale=%d:%d,setsar=1" % (w, h)
    if fit == "crop":
        return (head + ",scale=%d:%d:force_original_aspect_ratio=increase,"
                "crop=%d:%d:(iw-%d)/2:(ih-%d)/2,setsar=1") % (w, h, w, h, w, h)
    return (head + ",scale=%d:%d:force_original_aspect_ratio=decrease,"
            "pad=%d:%d:(ow-iw)/2:(oh-ih)/2:color=%s,setsar=1") % (w, h, w, h, pad_color)


def _key_value(o):
    """抠像中心：黑 -> 0，白 -> 1"""
    return 1.0 if o.key_target == "white" else 0.0


def build_graph(o, w, h, fps):
    """生成 -filter_complex 的字符串（不含 -map）。

    返回 (图, 目标标签, layout)；layout 说明各路素材占用的输入序号，
    a=底层素材A、b=底层素材B，None 表示该路不占输入（用纯色兜底）。
    """
    th = _key_value(o)
    tol = "%.4f" % float(o.tolerance)
    soft = "%.4f" % float(o.softness)
    invert = ",negate=components=a" if o.invert else ""
    key_filter = "lumakey=threshold=%s:tolerance=%s:softness=%s" % (
        ("%g" % th), tol, soft)
    one = {"a": None, "b": None}

    if o.mode == "dual":
        # 黑区 -> 素材A，白区 -> 素材B；留空的一侧保留原本的黑/白
        key_black = "lumakey=threshold=0:tolerance=%s:softness=%s" % (tol, soft)
        head = (_normalize("0:v", w, h, fps, "pad", "black")
                + ",format=yuva420p," + key_black)
        ov = ("overlay=x=0:y=0:shortest=1:eof_action=endall:repeatlast=0:"
              "format=yuv420:alpha=straight,format=yuv420p[vout]")
        parts = []
        idx = 1
        if o.bg:
            parts.append(_normalize("1:v", w, h, fps, o.fit, "black")
                         + ",format=yuv420p[ba]")
            one["a"] = 1
            idx = 2
        else:
            # 没给 A：黑区铺纯黑
            parts.append("color=black:s=%dx%d:r=%s,setsar=1,format=yuv420p[ba]"
                         % (w, h, _fps_expr(fps)))
        if o.bg2:
            # 白区用 alphaextract 取出「哪里是白」当遮罩，把 B 贴上去
            parts.insert(0, head + "[fgw]")
            parts.append("[fgw]alphaextract,format=gray[mask]")
            parts.append(_normalize("%d:v" % idx, w, h, fps, o.fit, "black")
                         + ",format=yuv420p[bb]")
            one["b"] = idx
            parts.append("[bb][mask]alphamerge[bp]")
            parts.append("[ba][bp]" + ov)
        else:
            # 没给 B：白区保留原本的白色剪影
            parts.insert(0, head + "[fgw]")
            parts.append("[ba][fgw]" + ov)
        return ";".join(parts), "[vout]", one

    if o.mode == "recolor":
        # 换色永远以黑作为抠除色：黑区域 -> color1，白区域 -> color2
        parts = [
            _normalize("0:v", w, h, fps, "pad", "black") + ",split=2[fgb][fgk]",
            "[fgb]format=rgb24,lutrgb=r=%d:g=%d:b=%d[c1]" % hex_to_rgb(o.color1),
            ("[fgk]format=yuva420p,%s%s,format=rgba,"
             "lutrgb=r=%d:g=%d:b=%d[c2]") % (
                key_filter, invert, *hex_to_rgb(o.color2)),
            ("[c1][c2]overlay=x=0:y=0:shortest=1:eof_action=endall:"
             "repeatlast=0:format=rgb:alpha=straight,format=yuv420p[vout]"),
        ]
        return ";".join(parts), "[vout]", one

    if o.mode == "overlay":
        one["a"] = 1
        key_color = "white" if o.key_target == "white" else "black"
        parts = [
            _normalize("0:v", w, h, fps, "pad", key_color)
            + ",format=yuva420p," + key_filter + invert + "[fg]",
            _normalize("1:v", w, h, fps, o.fit, "black")
            + ",format=yuv420p[base]",
            ("[base][fg]overlay=x=0:y=0:shortest=1:eof_action=endall:"
             "repeatlast=0:format=yuv420:alpha=straight,"
             "format=yuv420p[vout]"),
        ]
        return ";".join(parts), "[vout]", one

    # alpha：导出带透明通道的中间素材
    key_color = "white" if o.key_target == "white" else "black"
    parts = [
        _normalize("0:v", w, h, fps, "pad", key_color)
        + ",format=yuva420p," + key_filter + invert
        + ",format=yuva420p[vout]",
    ]
    return ";".join(parts), "[vout]", one


def total_duration(o, fg_info, bg_info, bg2_info=None):
    """按策略算出输出总时长（秒）。未知返回 0"""
    fd = float(fg_info.get("duration") or 0.0)
    if o.mode in ("recolor", "alpha"):
        return fd
    bd = float(bg_info.get("duration") or 0.0)
    bd2 = float((bg2_info or {}).get("duration") or 0.0)
    if o.duration_policy == "loop_bg":
        return fd
    if o.duration_policy == "loop_fg":
        return bd or bd2
    # shortest：图片（时长 0）视为无限长，不参与取小
    cands = [d for d in (fd, bd, bd2) if d > 0]
    if len(cands) >= 2:
        return min(cands)
    return fd or bd or bd2


def _audio_graph(o, fg_info, bg_info, bg2_info=None, layout=None):
    """返回 (附加滤镜字符串, 音频映射标签)。不需要返回 (None, None)"""
    layout = layout or {}
    idx_a = layout.get("a")
    idx_b = layout.get("b")
    if o.audio_policy == "none" or o.mode == "alpha":
        return None, None

    cands = []
    if fg_info.get("has_audio"):
        cands.append(0)
    if idx_a is not None and (bg_info or {}).get("has_audio"):
        cands.append(idx_a)
    if idx_b is not None and (bg2_info or {}).get("has_audio"):
        cands.append(idx_b)
    if not cands:
        return None, None

    def one(i):
        return ("[%d:a:0]asetpts=PTS-STARTPTS,aresample=async=1:first_pts=0[aout]"
                % i, "[aout]")

    if o.audio_policy == "mix" and len(cands) >= 2:
        sel = cands[:3]
        g = ""
        labels = []
        for n, i in enumerate(sel):
            g += ("[%d:a:0]asetpts=PTS-STARTPTS,aresample=async=1:"
                  "first_pts=0[a%d];" % (i, n))
            labels.append("[a%d]" % n)
        g += "".join(labels) + (
            "amix=inputs=%d:duration=longest:dropout_transition=0:weights=%s:"
            "normalize=1[aout]" % (len(labels), " ".join(["1"] * len(labels))))
        return g, "[aout]"

    prefer = {"fg": 0, "bg": idx_a, "bg2": idx_b}.get(o.audio_policy)
    if prefer in cands:
        return one(prefer)
    return one(cands[0])


def build_cmd(o, fg_info, bg_info, out_path, progress=False, bg2_info=None):
    """构造完整的 ffmpeg 命令（列表形式）"""
    w, h = even_size(o.width, o.height)
    fps = o.fps or (fg_info.get("fps") or 30.0)
    graph, vout, layout = build_graph(o, w, h, fps)

    total = total_duration(o, fg_info, bg_info, bg2_info)

    args = [ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error"]
    if progress:
        args += ["-progress", "pipe:1", "-stats_period", "0.25", "-nostats"]

    def add_input(path, loop):
        """图片本身没有时长，用 -loop 1 铺满；视频按需 -stream_loop"""
        if is_image(path):
            args.extend(["-loop", "1", "-framerate", _fps_expr(fps)])
        elif loop:
            args.extend(["-stream_loop", "-1"])
        args.extend(["-i", path])

    loop_fg = o.duration_policy == "loop_fg" and o.mode != "alpha"
    add_input(o.fg, loop_fg)
    if layout.get("a") is not None:
        add_input(o.bg, o.duration_policy == "loop_bg")
    if layout.get("b") is not None:
        add_input(o.bg2, o.duration_policy == "loop_bg")

    ag, alabel = _audio_graph(o, fg_info, bg_info, bg2_info, layout)

    fmt = o.export_format
    if fmt == "gif":
        # 透明 GIF：调色板需要专门预留一个透明色
        graph = graph + (
            ";[vout]split[pa][pb];"
            "[pa]palettegen=reserve_transparent=1:transparency_color=black[p];"
            "[pb][p]paletteuse=alpha_threshold=128[gifout]")
        vout = "[gifout]"
    args += ["-filter_complex", graph + (";" + ag if ag else "")]

    if fmt == "gif":
        args += ["-map", vout, "-loop", "0"]
    elif fmt == "mkv":
        args += ["-map", vout, "-c:v", "ffv1", "-level", "3",
                 "-pix_fmt", "yuva420p"]
    else:
        args += ["-map", vout, "-c:v", "libx264", "-preset", o.preset,
                 "-crf", str(o.crf), "-pix_fmt", "yuv420p",
                 "-movflags", "+faststart"]

    if alabel:
        args += ["-map", alabel, "-c:a", "aac", "-b:a", "192k"]
    else:
        args += ["-an"]

    if total > 0:
        args += ["-t", "%.3f" % total]
    args += [out_path]
    return args, total


# ---------------------------------------------------------------------------
# 自检（无界面）—— 供打包后冒烟使用
# ---------------------------------------------------------------------------
def run_selftest(workdir=None):
    """合成素材 -> 跑四种模式 -> 回读像素判定。返回结果清单"""
    workdir = workdir or os.path.join(tempfile.gettempdir(), "BAStudio_selftest")
    os.makedirs(workdir, exist_ok=True)
    ff = ffmpeg_exe()
    fg = os.path.join(workdir, "fg.mp4")
    bg = os.path.join(workdir, "bg.mp4")

    def ff_run(args):
        r = subprocess.run(args, capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           creationflags=CREATE_NO_WINDOW)
        if r.returncode != 0:
            raise RuntimeError(" ".join(args[:8]) + " => " + r.stderr[-900:])
        return r

    ff_run([ff, "-y", "-f", "lavfi", "-i", "color=black:s=320x180:r=25:d=3",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
            "-vf", "drawbox=x=160:y=0:w=160:h=180:color=white:t=fill",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-shortest", fg])
    ff_run([ff, "-y", "-f", "lavfi", "-i", "color=red:s=640x360:r=25:d=5",
            "-f", "lavfi", "-i", "sine=frequency=880:duration=5",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-shortest", bg])

    fg_info = probe(fg)
    bg_info = probe(bg)
    results = {}
    shot = os.path.join(workdir, "shot.png")

    def render_png(out_path, expect_alpha):
        """导出后再取一帧；带透明的产物要叠到红底上才能判定是否真的透明"""
        if expect_alpha:
            ff_run([ff, "-y", "-ss", "0.5", "-i", out_path, "-ss", "0.5", "-i", bg,
                    "-filter_complex",
                    "[0:v]scale=320:180,format=yuva420p[fg];"
                    "[1:v]scale=320:180,format=yuv420p[base];"
                    "[base][fg]overlay=x=0:y=0:shortest=1:eof_action=endall:"
                    "format=yuv420:alpha=straight,format=yuv420p[vout]",
                    "-map", "[vout]", "-frames:v", "1", "-an", shot])
        else:
            ff_run([ff, "-y", "-ss", "0.5", "-i", out_path, "-frames:v", "1", shot])
        from PIL import Image
        with Image.open(shot) as im:
            im = im.convert("RGB")
            return tuple(im.getpixel((70, 90))), tuple(im.getpixel((250, 90)))

    def near(a, b, tol=20):
        return all(abs(a[i] - b[i]) <= tol for i in range(3))

    def case(name, options, expect):
        o = options
        o.width, o.height = 320, 180
        o.fps = 25
        ext = "gif" if o.export_format == "gif" else ("mkv" if o.export_format == "mkv" else "mp4")
        out = os.path.join(workdir, "%s.%s" % (name, ext))
        args, _ = build_cmd(o, fg_info, bg_info, out)
        ff_run(args)
        got = render_png(out, o.mode == "alpha")
        ok = near(got[0], expect[0]) and near(got[1], expect[1])
        results[name] = (ok, got, expect)
        return ok

    RED = (255, 0, 0)
    WHITE = (255, 255, 255)
    BLACK = (0, 0, 0)

    o = Options()
    o.fg, o.bg = fg, bg
    o.mode = "overlay"
    o.key_target = "black"
    o.duration_policy = "shortest"
    o.audio_policy = "fg"
    o.fit = "crop"
    case("B1_黑透明_叠加", o, (RED, WHITE))

    o = o.copy()
    o.key_target = "white"
    case("B2_白透明_叠加", o, (BLACK, RED))

    o = Options()
    o.fg = fg
    o.mode = "recolor"
    o.color1 = "#00ff00"
    o.color2 = "#0000ff"
    o.audio_policy = "fg"
    case("A1_黑转绿_白转蓝", o, ((0, 255, 0), (0, 0, 255)))

    o = Options()
    o.fg = fg
    o.mode = "alpha"
    o.export_format = "gif"
    case("C1_透明GIF", o, (RED, WHITE))     # 叠到红底：黑区域应透出红色

    o = Options()
    o.fg = fg
    o.mode = "alpha"
    o.export_format = "mkv"
    case("C2_透明MKV", o, (RED, WHITE))

    lines = []
    for k, (ok, got, exp) in results.items():
        lines.append("%-16s %s  实际=%s  期望=%s" % (k, "PASS" if ok else "FAIL", got, exp))
    return lines, fg_info, bg_info, workdir


def check_capabilities():
    """检查当前 ffmpeg 是否具备需要的滤镜/编码器"""
    need_filters = ["lumakey", "negate", "overlay", "lutrgb", "amix",
                    "palettegen", "paletteuse", "format", "scale", "crop",
                    "pad", "fps", "setpts"]
    need_enc = ["libx264", "aac", "gif", "ffv1"]
    try:
        out = subprocess.run([ffmpeg_exe(), "-hide_banner", "-filters"],
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace", creationflags=CREATE_NO_WINDOW).stdout
        have = set(re.findall(r"^\s*\S+\s+(\S+)\s+\S", out, re.M))
        miss_f = [n for n in need_filters if n not in have]
    except Exception as exc:
        miss_f = ["无法执行 ffmpeg: %s" % exc]
    try:
        out = subprocess.run([ffmpeg_exe(), "-hide_banner", "-encoders"],
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace", creationflags=CREATE_NO_WINDOW).stdout
        miss_e = [n for n in need_enc if not re.search(r"\b%s\b" % n, out)]
    except Exception as exc:
        miss_e = ["无法执行 ffmpeg: %s" % exc]
    return miss_f, miss_e


_checker_cache = {}


def checkerboard(size, tile=16):
    """透明预览用的棋盘格底图"""
    key = (size, tile)
    if key in _checker_cache:
        return _checker_cache[key].copy()
    from PIL import Image, ImageDraw
    w, h = size
    img = Image.new("RGB", (w, h), "#ffffff")
    d = ImageDraw.Draw(img)
    for y in range(0, h, tile):
        for x in range(0, w, tile):
            if (x // tile + y // tile) % 2 == 0:
                d.rectangle([x, y, x + tile - 1, y + tile - 1], fill="#dfe5ee")
    _checker_cache[key] = img.copy()
    return img


# ---------------------------------------------------------------------------
# 界面（独立模块，避免与核心逻辑互相纠缠）
# ---------------------------------------------------------------------------
# 以脚本方式直接运行时，让 ba_app 拿到的是同一份模块实例
sys.modules.setdefault("badapple_studio", sys.modules.get("__main__"))

from ba_app import create_app, launch_gui  # noqa: E402


def main():
    if "--info" in sys.argv:
        print("ffmpeg =", ffmpeg_exe())
        print("素材目录 =", material_dir())
        print("内置底视频目录 =", builtin_dir())
        for k, p in builtin_videos().items():
            print("  内置:", k, "->", describe(p))
        d = assets_dir()
        if os.path.isdir(d):
            for name in sorted(os.listdir(d)):
                if name.lower().endswith(VIDEO_EXT):
                    print("  片源:", name, "->", describe(os.path.join(d, name)))
        else:
            print("  （片源目录不存在）")
        return 0
    if "--selftest" in sys.argv:
        wd = None
        if "--selftest" in sys.argv:
            i = sys.argv.index("--selftest")
            if i + 1 < len(sys.argv) and not sys.argv[i + 1].startswith("-"):
                wd = sys.argv[i + 1]
        print("ffmpeg =", ffmpeg_exe())
        miss_f, miss_e = check_capabilities()
        print("缺少滤镜: %s" % (miss_f or "无"))
        print("缺少编码器: %s" % (miss_e or "无"))
        lines, fi, bi, work = run_selftest(wd)
        print("片源探测: %sx%s %.2ffps %.2fs audio=%s" % (
            fi.get("width"), fi.get("height"), fi.get("fps"),
            fi.get("duration"), fi.get("has_audio")))
        for ln in lines:
            print(ln)
        print("工作目录:", work)
        return 0
    launch_gui()
    return 0


if __name__ == "__main__":
    sys.exit(main())
