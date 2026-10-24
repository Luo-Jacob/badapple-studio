# -*- coding: utf-8 -*-
"""验证双层填充：黑区显示素材A、白区显示素材B（alphaextract + alphamerge 路线）"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import badapple_studio as m  # noqa: E402

from PIL import Image  # noqa: E402

FF = m.ffmpeg_exe()
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fv")
os.makedirs(OUT, exist_ok=True)

FG = os.path.join(OUT, "fg2.mp4")       # 左黑右白
A = os.path.join(OUT, "red.mp4")        # 素材A：红
B = os.path.join(OUT, "blue.mp4")       # 素材B：蓝
IMG = os.path.join(OUT, "green.png")    # 图片素材：绿


def run(args):
    r = subprocess.run(args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace",
                       creationflags=m.CREATE_NO_WINDOW)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-900:])
    return r


# --- 造素材 ---
run([FF, "-y", "-hide_banner", "-loglevel", "error",
     "-f", "lavfi", "-i", "color=black:s=320x180:r=25:d=3",
     "-vf", "drawbox=x=160:y=0:w=160:h=180:color=white:t=fill",
     "-c:v", "libx264", "-pix_fmt", "yuv420p", FG])
run([FF, "-y", "-hide_banner", "-loglevel", "error",
     "-f", "lavfi", "-i", "color=red:s=320x180:r=25:d=3",
     "-c:v", "libx264", "-pix_fmt", "yuv420p", A])
run([FF, "-y", "-hide_banner", "-loglevel", "error",
     "-f", "lavfi", "-i", "color=blue:s=320x180:r=25:d=3",
     "-c:v", "libx264", "-pix_fmt", "yuv420p", B])
run([FF, "-y", "-hide_banner", "-loglevel", "error",
     "-f", "lavfi", "-i", "color=green:s=320x180:d=1", "-frames:v", "1", IMG])
print("素材就绪")


def shot(name, args):
    png = os.path.join(OUT, name + ".png")
    run([FF, "-y", "-hide_banner", "-loglevel", "error"] + args + ["-frames:v", "1", png])
    im = Image.open(png).convert("RGB")
    return im.getpixel((70, 90)), im.getpixel((250, 90))


# --- 双层填充：黑区->红(A)，白区->蓝(B) ---
DUAL = (
    "[0:v]setpts=PTS-STARTPTS,fps=25,scale=320:180,setsar=1,format=yuva420p,"
    "lumakey=threshold=0:tolerance=0.10:softness=0.03[fgw];"
    "[fgw]alphaextract,format=gray[mask];"
    "[1:v]setpts=PTS-STARTPTS,fps=25,scale=320:180,setsar=1,format=yuv420p[ba];"
    "[2:v]setpts=PTS-STARTPTS,fps=25,scale=320:180,setsar=1,format=yuv420p[bb];"
    "[bb][mask]alphamerge[bp];"
    "[ba][bp]overlay=x=0:y=0:shortest=1:eof_action=endall:"
    "format=yuv420:alpha=straight,format=yuv420p[vout]"
)
got = shot("dual", ["-i", FG, "-i", A, "-i", B,
                    "-filter_complex", DUAL, "-map", "[vout]"])
print("双层填充  左(黑区)=%-16s 右(白区)=%-16s 期望 红/蓝" % (got[0], got[1]))
ok_dual = got[0][0] > 200 and got[0][2] < 60 and got[1][2] > 200 and got[1][0] < 60

# --- 只填黑区（B 留空 -> 白区保持白色剪影） ---
ONE = (
    "[0:v]setpts=PTS-STARTPTS,fps=25,scale=320:180,setsar=1,format=yuva420p,"
    "lumakey=threshold=0:tolerance=0.10:softness=0.03[fgw];"
    "[1:v]setpts=PTS-STARTPTS,fps=25,scale=320:180,setsar=1,format=yuv420p[ba];"
    "[ba][fgw]overlay=x=0:y=0:shortest=1:eof_action=endall:"
    "format=yuv420:alpha=straight,format=yuv420p[vout]"
)
got1 = shot("only_black", ["-i", FG, "-i", A,
                           "-filter_complex", ONE, "-map", "[vout]"])
print("只扣黑    左(黑区)=%-16s 右(白区)=%-16s 期望 红/白" % (got1[0], got1[1]))
ok_one = got1[0][0] > 200 and got1[0][2] < 60 and min(got1[1]) > 200

# --- 图片当素材B（绿） ---
got2 = shot("img_bg", ["-i", FG, "-i", A, "-loop", "1", "-framerate", "25", "-i", IMG,
                       "-filter_complex", DUAL, "-map", "[vout]"])
print("图片素材B 左(黑区)=%-16s 右(白区)=%-16s 期望 红/绿" % (got2[0], got2[1]))
ok_img = got2[0][0] > 200 and got2[0][2] < 60 and got2[1][1] > 100 and got2[1][0] < 120

print()
print("双层填充:", "PASS" if ok_dual else "FAIL")
print("只扣黑  :", "PASS" if ok_one else "FAIL")
print("图片素材:", "PASS" if ok_img else "FAIL")
sys.exit(0 if (ok_dual and ok_one and ok_img) else 1)
