# -*- coding: utf-8 -*-
"""用真实片源生成演示产物：内置底视频叠加 / 双素材填充 / 纯换色 / 透明 GIF"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import badapple_studio as m  # noqa: E402

OUT = os.path.join(m.base_dir(), "build", "demo")
os.makedirs(OUT, exist_ok=True)

FG = os.path.join(m.material_sub("片源", True), "BadApple_完整版_5m23.mp4")
BI = m.builtin_videos()
FLOW = BI.get("内置_流光") or list(BI.values())[0]
AURORA = BI.get("内置_极光") or list(BI.values())[-1]
print("片源:", os.path.basename(FG))
print("内置底:", list(BI.keys()))


def export(name, opt):
    info_fg = m.probe(opt.fg)
    info_a = m.probe(opt.bg) if opt.bg else {}
    info_b = m.probe(opt.bg2) if opt.bg2 else {}
    path = os.path.join(OUT, name)
    args, total = m.build_cmd(opt, info_fg, info_a, path, bg2_info=info_b)
    r = subprocess.run(args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace",
                       creationflags=m.CREATE_NO_WINDOW)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-600:])
    print("%-26s OK  %.1fs  %.1fMB" % (name, total,
                                       os.path.getsize(path) / 1e6))
    return path


# 1 内置底视频叠加（30 秒）
o = m.Options()
o.mode, o.fg, o.bg = "overlay", FG, FLOW
o.key_target = "black"
o.width, o.height, o.fps = 1280, 720, 30
o.duration_policy = "shortest"
o.audio_policy = "fg"
export("demo_叠加_内置流光.mp4", o)

# 2 双素材填充：黑区->流光，白区->极光（30 秒）
o = m.Options()
o.mode, o.fg, o.bg, o.bg2 = "dual", FG, FLOW, AURORA
o.width, o.height, o.fps = 1280, 720, 30
o.duration_policy = "shortest"
o.audio_policy = "fg"
export("demo_双素材填充.mp4", o)

# 3 纯换色（全曲）
o = m.Options()
o.fg = FG
o.mode = "recolor"
o.width, o.height, o.fps = 1280, 720, 30
o.color1 = "#111827"
o.color2 = "#f43f5e"
o.audio_policy = "fg"
export("demo_换色.mp4", o)

# 4 透明 GIF（全曲）
o = m.Options()
o.fg = FG
o.mode = "alpha"
o.export_format = "gif"
o.width, o.height, o.fps = 480, 270, 15
export("demo_透明GIF.gif", o)

print("演示产物目录:", OUT)
