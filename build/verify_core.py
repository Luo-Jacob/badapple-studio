# -*- coding: utf-8 -*-
"""验证改造后的核心层：双层填充 / 图片素材 / 内置底视频 / 素材目录"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import badapple_studio as m  # noqa: E402

from PIL import Image  # noqa: E402

FF = m.ffmpeg_exe()
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fv")
FG = os.path.join(OUT, "fg2.mp4")
A = os.path.join(OUT, "red.mp4")
B = os.path.join(OUT, "blue.mp4")
IMG = os.path.join(OUT, "green.png")

print("material_dir :", m.material_dir())
print("片源目录     :", m.assets_dir())
print("内置底视频   :", list(m.builtin_videos().keys()))


def run(o, bg2_info=None, out="out.mp4"):
    info_fg = m.probe(o.fg)
    info_a = m.probe(o.bg) if o.bg else {}
    p = os.path.join(OUT, out)
    args, total = m.build_cmd(o, info_fg, info_a, p, bg2_info=bg2_info)
    if os.path.exists(p):
        os.remove(p)
    r = subprocess.run(args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace",
                       creationflags=m.CREATE_NO_WINDOW)
    if r.returncode != 0:
        print("  ffmpeg 失败:", r.stderr[-600:])
        return None, total, args
    return p, total, args


def px(p):
    png = os.path.join(OUT, "_shot.png")
    subprocess.run([FF, "-y", "-hide_banner", "-loglevel", "error",
                    "-ss", "0.5", "-i", p, "-frames:v", "1", png],
                   capture_output=True)
    im = Image.open(png).convert("RGB")
    return im.getpixel((70, 90)), im.getpixel((250, 90))


def check(label, got, want):
    ok = all(abs(got[i][j] - want[i][j]) <= 22 for i in range(2) for j in range(3))
    print("%-22s 左=%-16s 右=%-16s 期望=%s -> %s" %
          (label, got[0], got[1], want, "PASS" if ok else "FAIL"))
    return ok


RED, BLUE, WHITE, BLACK, GREEN = (255, 0, 0), (0, 0, 255), (255, 255, 255), (0, 0, 0), (0, 128, 0)
res = []

# 1. 双层：黑区红、白区蓝
o = m.Options()
o.mode, o.fg, o.bg, o.bg2 = "dual", FG, A, B
o.width, o.height, o.fps = 320, 180, 25
p, total, _ = run(o, m.probe(B), "core_dual.mp4")
res.append(check("双层 黑->A 白->B", px(p), (RED, BLUE)))
print("   时长=%.1fs" % total)

# 2. 只给 A（白区保留白色剪影）
o = m.Options()
o.mode, o.fg, o.bg = "dual", FG, A
o.width, o.height, o.fps = 320, 180, 25
p, _, _ = run(o, None, "core_a.mp4")
res.append(check("双层 只给A", px(p), (RED, WHITE)))

# 3. 只给 B（黑区保持黑）
o = m.Options()
o.mode, o.fg, o.bg2 = "dual", FG, B
o.width, o.height, o.fps = 320, 180, 25
p, _, _ = run(o, m.probe(B), "core_b.mp4")
res.append(check("双层 只给B", px(p), (BLACK, BLUE)))

# 4. 图片当素材
o = m.Options()
o.mode, o.fg, o.bg, o.bg2 = "dual", FG, IMG, B
o.width, o.height, o.fps = 320, 180, 25
p, _, _ = run(o, m.probe(B), "core_img.mp4")
res.append(check("双层 图片作A", px(p), (GREEN, BLUE)))

# 5. 内置底视频作 A
bi = m.builtin_videos()
if bi:
    bp = list(bi.values())[0]
    o = m.Options()
    o.mode, o.fg, o.bg = "overlay", FG, bp
    o.width, o.height, o.fps = 320, 180, 25
    o.duration_policy = "loop_bg"
    p, total, _ = run(o, None, "core_builtin.mp4")
    got = px(p)
    ok = got[1] is not None and (max(got[0]) - min(got[0])) > 5
    print("%-22s 左(黑区)=%-16s 右(白区)=%-16s -> %s" %
          ("内置底视频作A", got[0], got[1], "PASS" if ok else "FAIL"))
    res.append(ok)

# 6. 原有叠加模式无回归
o = m.Options()
o.mode, o.fg, o.bg = "overlay", FG, A
o.width, o.height, o.fps = 320, 180, 25
p, _, _ = run(o, None, "core_overlay.mp4")
res.append(check("叠加模式回归", px(p), (RED, WHITE)))

print()
print("全部通过:", all(res), "(%d/%d)" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
