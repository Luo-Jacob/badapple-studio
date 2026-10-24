# -*- coding: utf-8 -*-
"""GUI 无头冒烟：构建界面 -> 片源/素材切换 -> 各模式导出 -> 预览 -> 取消"""
import os
import sys
import time

BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(BASE, "src"))
import badapple_studio as m  # noqa: E402

import tkinter as tk  # noqa: E402

IMG = os.path.join(BASE, "build", "fv", "green.png")
OUTDIR = os.path.join(BASE, "build")

root = tk.Tk()
root.withdraw()
app = m.create_app(root)
root.deiconify()
root.update()

print("== 界面构建 OK，ffmpeg:", app.var_cap.get())
print("== 素材目录:", m.material_dir())

# ---- 片源下拉 ----
labels = list(app.combo_fg["values"])
print("== 片源下拉 %d 项:" % len(labels))
for lab in labels:
    print("   -", lab)
assert len(labels) >= 2, "片源下拉应包含两个片源"

# ---- 素材下拉（内置 + 用户素材）----
media = list(app.combo_bg["values"])
print("== 素材下拉 %d 项:" % len(media))
for x in media[:6]:
    print("   -", x)
builtin = [x for x in media if x.startswith("内置")]
assert builtin, "素材下拉应含内置底视频"

# 用 3m39 版跑得快些
app.var_fg_lab.set([l for l in labels if "3m39" in l][0])
app._on_fg_pick()


def pick_bg(which, label_sub, use_image=False):
    if use_image:
        getattr(app, "var_" + which).set(IMG)
        getattr(app, "var_" + which + "_lab").set(os.path.basename(IMG))
    else:
        lab = [x for x in media if label_sub in x][0]
        getattr(app, "var_" + which + "_lab").set(lab)
        getattr(app, "_on_" + which + "_pick")()
    root.update()


def wait_run(limit=400):
    t0 = time.time()
    while app.busy and time.time() - t0 < limit:
        root.update()
        time.sleep(0.02)


def export(name, mode):
    app._set_mode(mode)
    app.var_dur.set("shortest")
    app.var_crf.set(28)
    app.var_preset.set("veryfast")
    app.var_res.set("640x360")
    out = os.path.join(OUTDIR, name)
    app.var_out.set(out)
    root.update()
    if os.path.exists(out):
        os.remove(out)
    app._start()
    wait_run()
    ok = os.path.exists(out) and os.path.getsize(out) > 0
    size = os.path.getsize(out) if os.path.exists(out) else 0
    print("== 导出 %-24s 模式=%-8s -> %s %.1fMB  %s" %
          (name, mode, "成功" if ok else "失败", size / 1e6, app.var_status.get()))
    return ok


res = []
# 1 叠加到内置底视频
pick_bg("bg", "流光")
res.append(export("smoke_叠加_内置底.mp4", "overlay"))

# 2 双素材填充：黑->流光，白->极光
pick_bg("bg", "流光")
pick_bg("bg2", "极光")
res.append(export("smoke_双素材.mp4", "dual"))

# 3 双素材，B 用图片
pick_bg("bg", "流光")
pick_bg("bg2", "", use_image=True)
res.append(export("smoke_双素材_图片B.mp4", "dual"))

# 4 纯换色
app._set_mode("recolor")
app.var_c1.set("#111827")
app.var_c2.set("#f43f5e")
res.append(export("smoke_换色.mp4", "recolor"))

# 5 透明 GIF
app._set_mode("alpha")
app.var_export.set("gif")
res.append(export("smoke_透明.gif", "alpha"))

# ---- 高级设置开合 ----
app.var_adv.set(True)
app._apply_adv()
root.update()
adv_visible = bool(app.card_adv.winfo_ismapped())
app.var_adv.set(False)
app._apply_adv()
root.update()
adv_hidden = not bool(app.card_adv.winfo_ismapped())
print("== 高级设置 展开=%s 收起=%s" % (adv_visible, adv_hidden))
res.append(adv_visible and adv_hidden)

# ---- 预览 ----
app._set_mode("overlay")
pick_bg("bg", "流光")
app.var_time.set(5.0)
app._schedule_preview()
t0 = time.time()
while time.time() - t0 < 30:
    root.update()
    time.sleep(0.02)
    if "已更新" in app.var_note.get() or "失败" in app.var_note.get():
        break
print("== 预览:", app.var_note.get())
res.append("已更新" in app.var_note.get())

# ---- 取消流程 ----
out3 = os.path.join(OUTDIR, "smoke_cancel.mp4")
app._set_mode("overlay")
app.var_out.set(out3)
root.update()
app._start()
time.sleep(2.0)
app._cancel()
wait_run(60)
print("== 取消:", app.var_status.get(), "残留:", os.path.exists(out3))
res.append(not os.path.exists(out3))

root.destroy()
allok = all(res)
print("== 冒烟结果:", "全部通过" if allok else "有失败项", "(%d/%d)" % (sum(res), len(res)))
sys.exit(0 if allok else 1)
