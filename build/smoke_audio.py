# -*- coding: utf-8 -*-
"""验证「用谁的声音」：靠过零率判断输出音轨来自 440Hz 片源还是 880Hz 素材"""
import os
import subprocess
import sys
import wave

BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(BASE, "src"))
import badapple_studio as m  # noqa: E402

import tkinter as tk  # noqa: E402

FF = m.ffmpeg_exe()
OUT = os.path.join(BASE, "build", "fv")
os.makedirs(OUT, exist_ok=True)


def run(args):
    r = subprocess.run(args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace",
                       creationflags=m.CREATE_NO_WINDOW)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-600:])
    return r


# 片源：左黑右白，音轨 440Hz
FG = os.path.join(OUT, "fg_a.mp4")
run([FF, "-y", "-hide_banner", "-loglevel", "error",
     "-f", "lavfi", "-i", "color=black:s=320x180:r=25:d=8",
     "-f", "lavfi", "-i", "sine=frequency=440:duration=8",
     "-vf", "drawbox=x=160:y=0:w=160:h=180:color=white:t=fill",
     "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", FG])
# 素材 A：蓝色，音轨 880Hz
A = os.path.join(OUT, "bg_a880.mp4")
run([FF, "-y", "-hide_banner", "-loglevel", "error",
     "-f", "lavfi", "-i", "color=blue:s=320x180:r=25:d=8",
     "-f", "lavfi", "-i", "sine=frequency=880:duration=8",
     "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", A])
# 素材 B：绿色，音轨 220Hz
B = os.path.join(OUT, "bg_b220.mp4")
run([FF, "-y", "-hide_banner", "-loglevel", "error",
     "-f", "lavfi", "-i", "color=green:s=320x180:r=25:d=8",
     "-f", "lavfi", "-i", "sine=frequency=220:duration=8",
     "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", B])
print("素材就绪：片源 440Hz / 素材A 880Hz / 素材B 220Hz")


def zero_cross_rate(path):
    """把音频抽成 8k 单声道 wav，算每秒过零次数（≈ 2×频率）"""
    if not m.probe(path).get("has_audio"):
        return None
    wav = os.path.join(OUT, "_z.wav")
    run([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", path,
         "-vn", "-ac", "1", "-ar", "8000", "-c:a", "pcm_s16le", wav])
    with wave.open(wav) as w:
        n = w.getnframes()
        raw = w.readframes(n)
    data = [int.from_bytes(raw[i:i + 2], "little", signed=True)
            for i in range(0, min(len(raw), 40000), 2)]
    zc = sum(1 for i in range(1, len(data))
             if (data[i - 1] < 0) != (data[i] < 0))
    return zc / (len(data) / 8000.0)


def hz(zcr):
    return None if zcr is None else zcr / 2.0


root = tk.Tk()
root.withdraw()
app = m.create_app(root)
root.update()

app.var_fg.set(FG)
app._on_fg_change()
app.var_bg.set(A)
app._refresh_bg()
app.var_bg2.set(B)
app._refresh_bg2()
app.var_res.set("320x180")
app.var_fps.set("25")
app.var_crf.set(28)
app.var_preset.set("veryfast")
app.var_dur.set("shortest")

print("声音下拉:", list(app.combo_audio["values"]))
print("当前:", app.var_audio_lab.get(), "->", app.var_audio.get())


def export(name, mode, audio):
    app._set_mode(mode)
    app._refresh_audio_options()
    app.var_audio.set(audio)
    app._on_audio_pick() if app.var_audio_lab.get() else None
    # 直接用值设置（绕过下拉文案）
    app.var_audio.set(audio)
    out = os.path.join(OUT, name)
    if os.path.exists(out):
        os.remove(out)
    app.var_out.set(out)
    root.update()
    app._start()
    t0 = __import__("time").time()
    while app.busy and __import__("time").time() - t0 < 300:
        root.update()
        __import__("time").sleep(0.02)
    ok = os.path.exists(out)
    z = zero_cross_rate(out) if ok else None
    print("%-22s 模式=%-8s 音源=%-5s -> %s  输出频率≈%s Hz" %
          (name, mode, audio, "成功" if ok else "失败",
           ("%.0f" % hz(z)) if z else "无音轨"))
    return hz(z) if z else None


res = []
f_fg = export("au_fg.mp4", "overlay", "fg")
res.append(("片源原声 440Hz", f_fg, 440))

f_bg = export("au_bg.mp4", "overlay", "bg")
res.append(("素材A 880Hz", f_bg, 880))

f_bg2 = export("au_bg2.mp4", "dual", "bg2")
res.append(("素材B 220Hz", f_bg2, 220))

f_none = export("au_none.mp4", "overlay", "none")
res.append(("不要声音", f_none, None))

f_mix = export("au_mix.mp4", "dual", "mix")
print("混音（440+880+220 叠加，频率会混合，只判断有音轨）:", f_mix)

root.destroy()

allok = True
for name, got, want in res:
    if want is None:
        ok = got is None
    else:
        ok = got is not None and abs(got - want) < 60
    print("%-16s 期望=%s 实测=%s -> %s" %
          (name, want, "无" if got is None else "%.0f" % got, "PASS" if ok else "FAIL"))
    allok = allok and ok
print("\n音频来源全部正确:", allok)
sys.exit(0 if allok else 1)
