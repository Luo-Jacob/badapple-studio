# -*- coding: utf-8 -*-
"""临时脚本：用合成素材实测 lumakey 抠像滤镜链是否符合预期。
左半黑 / 右半白 代表 Bad Apple，纯红视频代表用户底层视频。
"""
import os
import subprocess

import imageio_ffmpeg
from PIL import Image

FF = imageio_ffmpeg.get_ffmpeg_exe()
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fv")
os.makedirs(OUT, exist_ok=True)

FG = os.path.join(OUT, "fg.mp4")   # 左黑右白
BG = os.path.join(OUT, "bg.mp4")   # 纯红


def run(args, tag=""):
    r = subprocess.run(args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print("[FAIL] %s\n%s" % (tag, r.stderr[-2500:]))
        raise SystemExit(1)
    return r


def make_src():
    run([FF, "-y", "-f", "lavfi", "-i", "color=black:s=320x180:r=25:d=2",
         "-vf", "drawbox=x=160:y=0:w=160:h=180:color=white:t=fill",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "10", FG],
        "make fg")
    run([FF, "-y", "-f", "lavfi", "-i", "color=red:s=320x180:r=25:d=3",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "10", BG],
        "make bg")
    print("素材就绪: %s, %s" % (FG, BG))


def shot(name, inputs, filter_complex, map_label):
    """按给定时滤镜抽一帧 PNG 返回路径"""
    png = os.path.join(OUT, name + ".png")
    args = [FF, "-y", "-hide_banner", "-loglevel", "error"]
    args += inputs
    args += ["-filter_complex", filter_complex, "-map", map_label,
             "-frames:v", "1", "-an", "-c:v", "png", png]
    run(args, "shot:" + name)
    return png


def px(png, x, y):
    with Image.open(png) as im:
        return tuple(im.convert("RGB").getpixel((x, y)))


def check(name, png, expect_left, expect_right, tol=18):
    l = px(png, 70, 90)
    r = px(png, 250, 90)

    def near(a, b):
        return all(abs(a[i] - b[i]) <= tol for i in range(3))

    ok = near(l, expect_left) and near(r, expect_right)
    print("  %-34s 左%-16s 右%-16s => %s" % (name, l, r, "PASS" if ok else "FAIL"))
    return ok


# ---------------------------------------------------------------------------
# 前景链：尺寸归一 -> 亮度抠像 -> 保留 alpha
# ---------------------------------------------------------------------------
def fg_branch(th, tol, soft, padcolor, tag):
    return (
        "[0:v]setpts=PTS-STARTPTS,fps=25,"
        "scale=320:180:force_original_aspect_ratio=decrease,"
        "pad=320:180:(ow-iw)/2:(oh-ih)/2:color=%s,setsar=1," % padcolor
        + "%s" % "" +
        "lumakey=threshold=%s:tolerance=%s:softness=%s[fg]" % (th, tol, soft), tag
    )


def main():
    make_src()
    inputs = ["-ss", "0.5", "-i", FG, "-ss", "0.5", "-i", BG]
    results = {}

    # ---- B1: 黑透明，叠在红底上。期望：左=红(露出底) 右=白(保留) ----
    fc = ("[0:v]setpts=PTS-STARTPTS,fps=25,"
          "scale=320:180:force_original_aspect_ratio=decrease,"
          "pad=320:180:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,"
          "format=yuva420p,"
          "lumakey=threshold=0:tolerance=0.10:softness=0.03[fg];"
          "[1:v]setpts=PTS-STARTPTS,fps=25,"
          "scale=320:180:force_original_aspect_ratio=increase,"
          "crop=320:180:(iw-320)/2:(ih-180)/2,setsar=1,"
          "format=yuv420p[base];"
          "[base][fg]overlay=x=0:y=0:shortest=1:eof_action=endall:"
          "repeatlast=0:format=yuv420:alpha=straight,"
          "format=yuv420p[vout]")
    results["B1 黑透明"] = check("B1 黑透明(threshold=0)",
                                 shot("b1", inputs, fc, "[vout]"),
                                 (255, 0, 0), (255, 255, 255))

    # ---- B2-a: 白透明，用 threshold=1 ----
    fc = ("[0:v]setpts=PTS-STARTPTS,fps=25,"
          "scale=320:180:force_original_aspect_ratio=decrease,"
          "pad=320:180:(ow-iw)/2:(oh-ih)/2:color=white,setsar=1,"
          "format=yuva420p,"
          "lumakey=threshold=1:tolerance=0.10:softness=0.03[fg];"
          "[1:v]setpts=PTS-STARTPTS,fps=25,"
          "scale=320:180:force_original_aspect_ratio=increase,"
          "crop=320:180:(iw-320)/2:(ih-180)/2,setsar=1,"
          "format=yuv420p[base];"
          "[base][fg]overlay=x=0:y=0:shortest=1:eof_action=endall:"
          "repeatlast=0:format=yuv420:alpha=straight,"
          "format=yuv420p[vout]")
    results["B2a 白透明"] = check("B2a 白透明(threshold=1)",
                                  shot("b2a", inputs, fc, "[vout]"),
                                  (0, 0, 0), (255, 0, 0))

    # ---- B2-b: 白透明，negate 路径 ----
    fc = ("[0:v]setpts=PTS-STARTPTS,fps=25,"
          "scale=320:180:force_original_aspect_ratio=decrease,"
          "pad=320:180:(ow-iw)/2:(oh-ih)/2:color=white,setsar=1,"
          "format=yuva420p,negate=negate_alpha=0,"
          "lumakey=threshold=0:tolerance=0.10:softness=0.03,"
          "negate=negate_alpha=0[fg];"
          "[1:v]setpts=PTS-STARTPTS,fps=25,"
          "scale=320:180:force_original_aspect_ratio=increase,"
          "crop=320:180:(iw-320)/2:(ih-180)/2,setsar=1,"
          "format=yuv420p[base];"
          "[base][fg]overlay=x=0:y=0:shortest=1:eof_action=endall:"
          "repeatlast=0:format=yuv420:alpha=straight,"
          "format=yuv420p[vout]")
    results["B2b 白透明"] = check("B2b 白透明(negate 路径)",
                                  shot("b2b", inputs, fc, "[vout]"),
                                  (0, 0, 0), (255, 0, 0))

    # ---- A1: 纯换色，黑->绿 白->蓝 ----
    fc = ("[0:v]setpts=PTS-STARTPTS,fps=25,"
          "scale=320:180:force_original_aspect_ratio=decrease,"
          "pad=320:180:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,"
          "split=2[base_src][key_src];"
          "[base_src]format=rgb24,lutrgb=r=0:g=255:b=0[color1];"
          "[key_src]format=yuva420p,"
          "lumakey=threshold=0:tolerance=0.10:softness=0.03,"
          "format=rgba,lutrgb=r=0:g=0:b=255[color2a];"
          "[color1][color2a]overlay=x=0:y=0:shortest=1:eof_action=endall:"
          "repeatlast=0:format=rgb:alpha=straight,"
          "format=yuv420p[vout]")
    results["A1 换色"] = check("A1 黑->绿 白->蓝",
                               shot("a1", inputs, fc, "[vout]"),
                               (0, 255, 0), (0, 0, 255))

    # ---- A2: 导出带 alpha（WebM VP9 + GIF） ----
    fc2 = ("[0:v]setpts=PTS-STARTPTS,fps=25,"
           "scale=320:180:force_original_aspect_ratio=decrease,"
           "pad=320:180:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,"
           "format=yuva420p,"
           "lumakey=threshold=0:tolerance=0.10:softness=0.03[vout]")
    webm = os.path.join(OUT, "a2.webm")
    gif = os.path.join(OUT, "a2.gif")
    run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", FG,
         "-filter_complex", fc2, "-map", "[vout]", "-t", "1",
         "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-lossless", "1",
         "-auto-alt-ref", "0", webm], "webm")
    run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", webm,
         "-vf", "zoompan=d=1:fps=25", "-t", "1", "-loop", "0", gif], "gif")
    # 回放 webm 叠到红底上验证 alpha 真的保留
    fc3 = ("[1:v]format=yuv420p[base];"
           "[base][0:v]overlay=x=0:y=0:shortest=1:format=yuv420:alpha=straight,"
           "format=yuv420p[vout]")
    results["A2 WebM alpha"] = check(
        "A2 WebM 叠红底回验",
        shot("a2_webm", ["-ss", "0.3", "-i", webm, "-ss", "0.3", "-i", BG],
             fc3, "[vout]"),
        (255, 0, 0), (255, 255, 255))

    print("\n素材产物目录: %s" % OUT)
    print("汇总: %s" % results)
    bad = [k for k, v in results.items() if not v]
    print("结论: %s" % ("全部通过" if not bad else "失败项 -> %s" % bad))


if __name__ == "__main__":
    main()
