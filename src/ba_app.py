# -*- coding: utf-8 -*-
"""Bad Apple Studio 主界面。

布局：左侧参数（可滚动）+ 右侧预览/输出/日志。
默认只露出新手需要的选项，打开「高级设置」才展开专业参数。
"""
import os
import queue
import subprocess
import threading
import time

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
from tkinter.scrolledtext import ScrolledText
from PIL import Image, ImageTk

from ba_ui import (BG, CARD, SOFT, BORDER, TEXT, MUTED, HINT, ACCENT,
                   ACCENT_L, ACCENT_D, DANGER, FONT, FONT_B, FONT_TITLE,
                   FONT_SMALL, RoundCard, RoundButton, Switch, ScrolledFrame,
                   apply_theme)
import badapple_studio as core

APP_NAME = core.APP_NAME
UI_QUEUE = queue.Queue()

MODE_ITEMS = [
    ("overlay", "叠加到素材", "黑色变透明，露出下面的素材"),
    ("dual", "双素材填充", "黑色→素材A，白色→素材B"),
    ("recolor", "纯换色", "黑/白各换成一个颜色"),
    ("alpha", "导出透明素材", "抠好透明的 GIF / MKV"),
]


def _fmt_mmss(sec):
    sec = int(sec or 0)
    return "%02d:%02d" % divmod(sec, 60)


class App(object):
    def __init__(self, root):
        self.root = root
        self.busy = False
        self.cancel_flag = False
        self.proc = None
        self.preview_proc = None
        self.preview_id = 0
        self.preview_timer = None
        self.preview_photo = None
        self.start_ts = 0
        self.total_seconds = 0.0
        self.last_out = ""
        self.fg_info = {}
        self.bg_info = {}
        self.bg2_info = {}
        self.fg_map = {}
        self.bg_map = {}
        self.tmpdir = os.path.join(core.tempfile.gettempdir(), "BAStudio_prev")
        os.makedirs(self.tmpdir, exist_ok=True)

        core.ensure_material_tree()

        # ---- 变量 ----
        self._combo_sync = []           # (控件, 变量, 值->中文) 用于配置回填
        self.var_fg = tk.StringVar()
        self.var_fg_lab = tk.StringVar()
        self.var_bg = tk.StringVar()
        self.var_bg_lab = tk.StringVar()
        self.var_bg2 = tk.StringVar()
        self.var_bg2_lab = tk.StringVar()
        self.var_mode = tk.StringVar(value="overlay")
        self.var_target = tk.StringVar(value="black")
        self.var_tol = tk.DoubleVar(value=0.10)
        self.var_soft = tk.DoubleVar(value=0.03)
        self.var_invert = tk.BooleanVar(value=False)
        self.var_c1 = tk.StringVar(value="#111827")
        self.var_c2 = tk.StringVar(value="#f43f5e")
        self.var_fit = tk.StringVar(value="裁切填满（不留黑边）")
        self.var_res = tk.StringVar(value="跟随 Bad Apple")
        self.var_fps = tk.StringVar(value="30")
        self.var_crf = tk.IntVar(value=20)
        self.var_preset = tk.StringVar(value="veryfast")
        self.var_dur = tk.StringVar(value="loop_bg")
        self.var_audio = tk.StringVar(value="fg")
        self.var_export = tk.StringVar(value="gif")
        self.var_adv = tk.BooleanVar(value=False)
        self.var_out = tk.StringVar()
        self.var_time = tk.DoubleVar(value=0.0)
        self.var_progress = tk.DoubleVar(value=0.0)
        self.var_status = tk.StringVar(value="就绪")
        self.var_pct = tk.StringVar(value="0%")
        self.var_cap = tk.StringVar(value="正在检查 ffmpeg…")
        self.var_note = tk.StringVar(value="选好片源就能看到预览")

        apply_theme(root)
        root.title(APP_NAME)
        root.geometry("1180x820")
        root.minsize(1020, 700)
        root.configure(bg=BG)
        self._build()
        self._load_config()
        self._scan_all()
        self.root.after(150, self._check_cap)
        self.root.after(250, self._poll)

    # ------------------------------------------------------------------
    # 界面搭建
    # ------------------------------------------------------------------
    def _build(self):
        top = tk.Frame(self.root, bg=BG)
        top.pack(fill="x", padx=18, pady=(14, 8))
        tk.Label(top, text="Bad Apple Studio", font=FONT_TITLE,
                 bg=BG, fg=TEXT).pack(side="left")
        tk.Label(top, text="影绘换色 · 抠像合成", font=FONT,
                 bg=BG, fg=MUTED).pack(side="left", padx=(10, 0), pady=(4, 0))
        Switch(top, text="高级设置", variable=self.var_adv,
               command=self._apply_adv, width=150).pack(side="right", pady=(4, 0))
        self.var_mat = tk.StringVar()
        tk.Label(top, textvariable=self.var_mat, font=FONT_SMALL, bg=BG,
                 fg=HINT).pack(side="right", padx=(0, 14), pady=(6, 0))
        RoundButton(top, text="打开素材目录", kind="ghost", width=110,
                    command=self._open_material, bg=BG).pack(side="right", padx=(0, 10))

        main = tk.Frame(self.root, bg=BG)
        main.pack(fill="both", expand=True, padx=18, pady=(0, 14))

        left = ScrolledFrame(main, bg=BG, width=500)
        left.pack(side="left", fill="both", expand=True)
        left.pack_propagate(False)
        self.left = left.inner

        right = tk.Frame(main, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(14, 0))

        self._card_source()
        self._card_mode()
        self._card_fill()
        self._card_audio()
        self._card_key_simple()
        self._card_recolor()
        self._card_fmt()
        self._card_adv()
        self._card_preview(right)
        self._card_out(right)
        self._card_log(right)
        self._left_cards = [self.card_source, self.card_mode, self.card_fill,
                            self.card_audio, self.card_key, self.card_recolor,
                            self.card_fmt, self.card_adv]
        self.var_mode.set("overlay")
        self._relayout_left()

    def _card(self, parent, title, pad=16):
        c = RoundCard(parent, radius=16, pad=pad, bg=BG)
        c.pack(fill="x", pady=(0, 12))
        if title:
            tk.Label(c.body, text=title, font=FONT_B, bg=CARD,
                     fg=TEXT).pack(anchor="w", pady=(0, 6))
        return c

    def _row(self, parent):
        r = tk.Frame(parent, bg=CARD)
        r.pack(fill="x", pady=(2, 0))
        return r

    def _hint(self, parent, text, var=None):
        return tk.Label(parent, text=(text if var is None else ""),
                        textvariable=var, font=FONT_SMALL, bg=CARD, fg=MUTED,
                        justify="left", anchor="w")

    def _title(self, parent, text):
        tk.Label(parent, text=text, font=FONT, bg=CARD,
                 fg=TEXT).pack(anchor="w", pady=(8, 2))

    # ---------------- ① 片源 ----------------
    def _card_source(self):
        self.card_source = c = self._card(self.left, "① Bad Apple 片源")
        self._picker(c.body, self.var_fg_lab, self.var_fg,
                     self._on_fg_pick, self._browse_fg, "fg")
        self.var_fg_desc = tk.StringVar(value="未选择")
        self._hint(c.body, "", self.var_fg_desc).pack(anchor="w", pady=(6, 0))

    # ---------------- ② 用途 ----------------
    def _card_mode(self):
        self.card_mode = c = self._card(self.left, "② 想做什么")
        self.mode_btns = {}
        grid = tk.Frame(c.body, bg=CARD)
        grid.pack(fill="x")
        for i, (key, name, desc) in enumerate(MODE_ITEMS):
            b = RoundButton(grid, text=name, width=108, height=38,
                            command=lambda k=key: self._set_mode(k), bg=CARD)
            b.grid(row=0, column=i, padx=(0, 8), sticky="w")
            self.mode_btns[key] = b
        self.var_mode_desc = tk.StringVar(value=MODE_ITEMS[0][2])
        self._hint(c.body, "", self.var_mode_desc).pack(anchor="w", pady=(8, 0))

    def _set_mode(self, key):
        self.var_mode.set(key)
        for k, b in self.mode_btns.items():
            b.configure(kind=("primary" if k == key else "ghost"))
        for k, _name, desc in MODE_ITEMS:
            if k == key:
                self.var_mode_desc.set(desc)
        self._refresh_mode_ui()

    # ---------------- ③ 填充素材 ----------------
    def _card_fill(self):
        self.card_fill = c = self._card(self.left, "③ 填充进来的素材")
        self._title(c.body, "素材 A（黑色部分显示）")
        self._picker(c.body, self.var_bg_lab, self.var_bg,
                     self._on_bg_pick, self._browse_bg, "bg")
        self.var_bg_desc = tk.StringVar(value="未选择")
        self._hint(c.body, "", self.var_bg_desc).pack(anchor="w", pady=(4, 0))

        self.row_bg2 = tk.Frame(c.body, bg=CARD)
        self.row_bg2.pack(fill="x", pady=(10, 0))
        tk.Label(self.row_bg2, text="素材 B（白色部分显示，可留空）",
                 font=FONT, bg=CARD, fg=TEXT).pack(anchor="w", pady=(0, 2))
        self._picker(self.row_bg2, self.var_bg2_lab, self.var_bg2,
                     self._on_bg2_pick, self._browse_bg2, "bg2", empty=True)
        self.var_bg2_desc = tk.StringVar(value="未选择")
        self._hint(self.row_bg2, "", self.var_bg2_desc).pack(anchor="w", pady=(4, 0))

        self.row_swap = row = self._row(c.body)
        RoundButton(row, text="⇄ 交换 A / B", kind="ghost", width=100,
                    command=self._swap_ab, bg=CARD).pack(side="left", pady=(8, 0))

    # ---------------- ④ 声音 ----------------
    def _card_audio(self):
        self.card_audio = c = self._card(self.left, "④ 用谁的声音")
        self.var_audio_lab = tk.StringVar()
        cb = ttk.Combobox(c.body, textvariable=self.var_audio_lab, font=FONT,
                          state="readonly")
        cb.pack(fill="x")
        cb.bind("<<ComboboxSelected>>", self._on_audio_pick)
        self.combo_audio = cb
        self.var_audio_desc = tk.StringVar(value="")
        self._hint(c.body, "", self.var_audio_desc).pack(anchor="w", pady=(6, 0))

    def _audio_options(self):
        """按当前片源/素材生成声音选项：[(显示名, 值)]"""
        mode = self.var_mode.get()
        if mode == "alpha":
            return [("透明素材不带声音", "none")]

        def tag(path, info):
            if not path:
                return ""
            name = os.path.splitext(os.path.basename(path))[0]
            return name + ("" if info.get("has_audio") else "（无音轨）")

        fg_name = tag(self.var_fg.get(), self.fg_info)
        opts = [("Bad Apple 原声" + ("（%s）" % fg_name if fg_name else ""), "fg")]
        if mode in ("overlay", "dual"):
            if self.var_bg.get():
                opts.append(("素材 A 的声音（%s）" % tag(self.var_bg.get(), self.bg_info), "bg"))
        if mode == "dual":
            if self.var_bg2.get():
                opts.append(("素材 B 的声音（%s）" % tag(self.var_bg2.get(), self.bg2_info), "bg2"))
        voices = [k for k in ("fg", "bg", "bg2")
                  if (self.fg_info if k == "fg" else
                      self.bg_info if k == "bg" else self.bg2_info).get("has_audio")]
        if len(voices) >= 2:
            opts.append(("全部混在一起", "mix"))
        opts.append(("不要声音", "none"))
        return opts

    def _refresh_audio_options(self):
        if not hasattr(self, "combo_audio"):
            return
        opts = self._audio_options()
        self._audio_lab2val = {lab: val for lab, val in opts}
        self._audio_val2lab = {val: lab for lab, val in opts}
        self.combo_audio["values"] = [lab for lab, _ in opts]
        cur = self.var_audio.get()
        if cur not in self._audio_val2lab:
            cur = "fg" if "fg" in self._audio_val2lab else "none"
            self.var_audio.set(cur)
        self.var_audio_lab.set(self._audio_val2lab[cur])
        self._describe_audio(cur)

    def _describe_audio(self, val):
        txt = {
            "fg": "用 Bad Apple 片源自己的声音",
            "bg": "用素材 A 的声音（片源原声会被丢掉）",
            "bg2": "用素材 B 的声音（片源原声会被丢掉）",
            "mix": "把各路声音混在一起",
            "none": "输出没有声音",
        }.get(val, "")
        has = {"fg": self.fg_info, "bg": self.bg_info, "bg2": self.bg2_info}.get(val)
        if val in ("fg", "bg", "bg2") and has is not None and not has.get("has_audio"):
            txt += "；所选素材没有音轨，实际会回退到片源原声（若也没有则静音）"
        self.var_audio_desc.set(txt)

    def _on_audio_pick(self, _e=None):
        val = self._audio_lab2val.get(self.var_audio_lab.get(), "fg")
        self.var_audio.set(val)
        self._describe_audio(val)

    # ---------------- ⑤ 透明目标（简洁） ----------------
    def _card_key_simple(self):
        self.card_key = c = self._card(self.left, "⑤ 把哪种颜色变透明")
        box = tk.Frame(c.body, bg=CARD)
        box.pack(fill="x")
        for txt, val in (("黑色变透明（留白剪影）", "black"),
                         ("白色变透明（留黑剪影）", "white")):
            ttk.Radiobutton(box, text=txt, value=val, variable=self.var_target,
                            command=self._schedule_preview).pack(side="left", padx=(0, 14))
        RoundButton(box, text="⇄", kind="ghost", width=38, bg=CARD,
                    command=self._swap_target).pack(side="right")

    # ---------------- 换色 ----------------
    def _card_recolor(self):
        self.card_recolor = c = self._card(self.left, "换成什么颜色")
        row = tk.Frame(c.body, bg=CARD)
        row.pack(fill="x")
        self.sw_c1 = tk.Label(row, bg=self.var_c1.get(), width=4, height=1,
                              relief="flat", bd=0)
        self.sw_c1.pack(side="left", padx=(0, 6))
        RoundButton(row, text="黑色部分 →", kind="ghost", width=92, bg=CARD,
                    command=lambda: self._pick_color(self.var_c1)).pack(side="left")
        tk.Label(row, textvariable=self.var_c1, font=FONT, bg=CARD,
                 fg=MUTED, width=9).pack(side="left", padx=(6, 12))
        self.sw_c2 = tk.Label(row, bg=self.var_c2.get(), width=4, height=1)
        self.sw_c2.pack(side="left", padx=(0, 6))
        RoundButton(row, text="白色部分 →", kind="ghost", width=92, bg=CARD,
                    command=lambda: self._pick_color(self.var_c2)).pack(side="left")
        tk.Label(row, textvariable=self.var_c2, font=FONT, bg=CARD,
                 fg=MUTED, width=9).pack(side="left", padx=(6, 0))
        RoundButton(c.body, text="⇄ 交换", kind="ghost", width=90, bg=CARD,
                    command=self._swap_colors).pack(anchor="w", pady=(8, 0))
        self.var_c1.trace_add("write", lambda *_: self.sw_c1.configure(bg=self.var_c1.get()))
        self.var_c2.trace_add("write", lambda *_: self.sw_c2.configure(bg=self.var_c2.get()))

    # ---------------- 透明素材格式 ----------------
    def _card_fmt(self):
        self.card_fmt = c = self._card(self.left, "导出格式")
        box = tk.Frame(c.body, bg=CARD)
        box.pack(fill="x")
        for txt, val in (("透明 GIF（小，可直接发）", "gif"),
                         ("透明 MKV（无损，适合剪映）", "mkv")):
            ttk.Radiobutton(box, text=txt, value=val, variable=self.var_export,
                            command=self._schedule_preview).pack(anchor="w", pady=2)

    # ---------------- 高级 ----------------
    def _card_adv(self):
        self.card_adv = c = self._card(self.left, "高级设置")
        # 抠像细节
        self._title(c.body, "边缘处理")
        self._slider(c.body, "容差（把多少接近黑/白的像素也算进去）",
                     self.var_tol, 0.0, 0.5)
        self._slider(c.body, "边缘柔化（越大过渡越柔和）", self.var_soft, 0.0, 0.2)
        ttk.Checkbutton(c.body, text="反转透明区域", variable=self.var_invert,
                        command=self._schedule_preview).pack(anchor="w", pady=(4, 0))
        # 画面
        self._title(c.body, "画面")
        g = tk.Frame(c.body, bg=CARD)
        g.pack(fill="x")
        self._combo_row(g, "素材放不下时", self.var_fit, 0,
                        ["裁切填满（不留黑边）", "完整显示（补黑边）", "拉伸铺满"])
        self._combo_row(g, "输出尺寸", self.var_res, 1,
                        ["跟随 Bad Apple", "1920x1080", "1280x720", "640x360"])
        self._combo_row(g, "帧率", self.var_fps, 2,
                        ["跟随 Bad Apple", "60", "30", "25", "24"])
        # 时长与声音
        self._title(c.body, "时长与声音")
        g2 = tk.Frame(c.body, bg=CARD)
        g2.pack(fill="x")
        self._combo_row(g2, "长度按谁算", self.var_dur, 0,
                        [("按 Bad Apple 全长（素材循环）", "loop_bg"),
                         ("取较短的那个", "shortest"),
                         ("按素材长度（Bad Apple 循环）", "loop_fg")])
        # 画质
        self._title(c.body, "画质与速度")
        g3 = tk.Frame(c.body, bg=CARD)
        g3.pack(fill="x")
        tk.Label(g3, text="画质（数字越小越清晰）", font=FONT_SMALL, bg=CARD,
                 fg=MUTED).grid(row=0, column=0, sticky="w")
        ttk.Spinbox(g3, from_=14, to=30, textvariable=self.var_crf, width=6,
                    font=FONT).grid(row=0, column=1, sticky="w", padx=(8, 16))
        tk.Label(g3, text="编码速度", font=FONT_SMALL, bg=CARD,
                 fg=MUTED).grid(row=0, column=2, sticky="w")
        cb = ttk.Combobox(g3, textvariable=self.var_preset, state="readonly",
                          font=FONT, width=12)
        cb["values"] = ["veryfast", "fast", "medium", "slow"]
        cb.grid(row=0, column=3, sticky="w", padx=(8, 0))
        RoundButton(c.body, text="恢复默认参数", kind="ghost", width=110,
                    command=self._reset_adv, bg=CARD).pack(anchor="w", pady=(10, 0))

    def _combo_row(self, parent, text, var, row, values):
        pairs = []
        for v in values:
            if isinstance(v, tuple):
                pairs.append(v)
            else:
                pairs.append((v, v))
        tk.Label(parent, text=text, font=FONT_SMALL, bg=CARD,
                 fg=MUTED).grid(row=row, column=0, sticky="w", pady=3)
        cb = ttk.Combobox(parent, font=FONT, width=26, state="readonly")
        cb["values"] = [p[0] for p in pairs]
        cb.grid(row=row, column=1, sticky="w", padx=(10, 0), pady=3)
        lab2val = dict(pairs)
        val2lab = {v: k for k, v in pairs}
        cur = var.get()
        cb.set(lab2val.get(cur, val2lab.get(cur, pairs[0][0])))

        def on_pick(_e=None):
            var.set(lab2val.get(cb.get(), cb.get()))
            self._schedule_preview()
        cb.bind("<<ComboboxSelected>>", on_pick)
        self._combo_sync.append((cb, var, val2lab))
        return cb

    def _slider(self, parent, text, var, lo, hi):
        tk.Label(parent, text=text, font=FONT_SMALL, bg=CARD,
                 fg=MUTED).pack(anchor="w", pady=(6, 0))
        r = tk.Frame(parent, bg=CARD)
        r.pack(fill="x")
        lab = tk.Label(r, text="%.2f" % var.get(), width=5, bg=CARD,
                       fg=TEXT, font=FONT)
        lab.pack(side="right")
        s = ttk.Scale(r, from_=lo, to=hi, variable=var, orient="horizontal",
                      command=lambda e: (lab.configure(text="%.3f" % var.get()),
                                         self._schedule_preview()))
        s.pack(side="left", fill="x", expand=True)

    # ---------------- 预览 ----------------
    def _card_preview(self, parent):
        c = RoundCard(parent, radius=16, pad=14, bg=BG)
        c.pack(fill="both", expand=True)
        tk.Label(c.body, text="预览", font=FONT_B, bg=CARD, fg=TEXT).pack(anchor="w")
        self.preview_box = tk.Frame(c.body, bg=SOFT, height=380)
        self.preview_box.pack(fill="both", expand=True, pady=(6, 0))
        self.lab_preview = tk.Label(self.preview_box, bg=SOFT, bd=0)
        self.lab_preview.pack(fill="both", expand=True, padx=8, pady=8)
        self.lab_preview.bind("<Configure>", lambda e: self._schedule_preview())

        row = tk.Frame(c.body, bg=CARD)
        row.pack(fill="x", pady=(8, 0))
        RoundButton(row, text="◀ 1s", kind="ghost", width=60, bg=CARD,
                    command=lambda: self._step(-1.0)).pack(side="left")
        self.sld_time = ttk.Scale(row, from_=0, to=100, orient="horizontal",
                                  variable=self.var_time,
                                  command=lambda e: self._schedule_preview())
        self.sld_time.pack(side="left", fill="x", expand=True, padx=8)
        RoundButton(row, text="1s ▶", kind="ghost", width=60, bg=CARD,
                    command=lambda: self._step(1.0)).pack(side="left")
        self.var_time_lab = tk.StringVar(value="00:00")
        tk.Label(row, textvariable=self.var_time_lab, width=6, bg=CARD,
                 fg=TEXT, font=FONT).pack(side="left")
        self._hint(c.body, "", self.var_note).pack(anchor="w", pady=(6, 0))

    # ---------------- 输出 ----------------
    def _card_out(self, parent):
        c = RoundCard(parent, radius=16, pad=14, bg=BG)
        c.pack(fill="x", pady=(12, 0))
        tk.Label(c.body, text="输出", font=FONT_B, bg=CARD, fg=TEXT).pack(anchor="w")
        row = tk.Frame(c.body, bg=CARD)
        row.pack(fill="x", pady=(6, 0))
        ttk.Entry(row, textvariable=self.var_out, font=FONT).pack(
            side="left", fill="x", expand=True)
        RoundButton(row, text="另存为…", kind="ghost", width=80, bg=CARD,
                    command=self._pick_out).pack(side="left", padx=(8, 0))

        btns = tk.Frame(c.body, bg=CARD)
        btns.pack(fill="x", pady=(12, 0))
        self.btn_run = RoundButton(btns, text="开始合成", kind="primary",
                                   width=120, height=38, command=self._start, bg=CARD)
        self.btn_run.pack(side="left")
        self.btn_cancel = RoundButton(btns, text="取消", kind="danger",
                                      width=90, height=38, command=self._cancel,
                                      bg=CARD)
        self.btn_cancel.pack(side="left", padx=(10, 0))
        self.btn_cancel.configure(state="disabled")
        RoundButton(btns, text="打开输出目录", kind="ghost", width=110,
                    height=38, command=self._open_out_dir, bg=CARD).pack(side="right")

        head = tk.Frame(c.body, bg=CARD)
        head.pack(fill="x", pady=(12, 0))
        tk.Label(head, textvariable=self.var_status, font=FONT_SMALL, bg=CARD,
                 fg=MUTED).pack(side="left")
        tk.Label(head, textvariable=self.var_pct, font=FONT, bg=CARD,
                 fg=TEXT, width=6).pack(side="right")
        ttk.Progressbar(c.body, variable=self.var_progress, maximum=100).pack(
            fill="x", pady=(6, 0))

    def _card_log(self, parent):
        c = RoundCard(parent, radius=16, pad=12, bg=BG)
        c.pack(fill="both", expand=True, pady=(12, 0))
        head = tk.Frame(c.body, bg=CARD)
        head.pack(fill="x")
        tk.Label(head, text="日志", font=FONT_B, bg=CARD, fg=TEXT).pack(side="left")
        tk.Label(head, textvariable=self.var_cap, font=FONT_SMALL, bg=CARD,
                 fg=HINT).pack(side="left", padx=(12, 0))
        RoundButton(head, text="清空", kind="ghost", width=60, height=26,
                    command=lambda: self.log.delete("1.0", "end"),
                    bg=CARD).pack(side="right")
        self.log = ScrolledText(c.body, height=7, font=("Consolas", 9),
                                bg="#fbfcfe", fg=TEXT, relief="flat", bd=0,
                                highlightthickness=0)
        self.log.pack(fill="both", expand=True, pady=(6, 0))

    # ------------------------------------------------------------------
    # 素材选择控件
    # ------------------------------------------------------------------
    def _picker(self, parent, var_lab, var_path, on_pick, on_browse, tag,
                empty=False):
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x")
        cb = ttk.Combobox(row, textvariable=var_lab, font=FONT)
        cb.pack(side="left", fill="x", expand=True)
        cb.bind("<<ComboboxSelected>>", lambda e: on_pick())
        RoundButton(row, text="浏览…", kind="ghost", width=64, height=28,
                    command=on_browse, bg=CARD).pack(side="left", padx=(6, 0))
        RoundButton(row, text="↻", kind="ghost", width=34, height=28,
                    command=lambda: self._scan_all(), bg=CARD).pack(side="left",
                                                                    padx=(6, 0))
        if tag == "fg":
            self.combo_fg = cb
        elif tag == "bg":
            self.combo_bg = cb
        else:
            self.combo_bg2 = cb
        return cb

    def _label_for(self, path):
        info = core.probe(path)
        base = os.path.splitext(os.path.basename(path))[0]
        if info.get("is_image"):
            return "%s（图片 %dx%d）" % (base, info.get("width", 0), info.get("height", 0))
        if info.get("ok") and info.get("duration"):
            return "%s（%s · %dx%d）" % (base, _fmt_mmss(info["duration"]),
                                        info.get("width", 0), info.get("height", 0))
        return base

    def _scan_all(self):
        """扫描片源目录与素材目录，刷新三个下拉"""
        # 片源
        self.fg_map = {}
        for p in self._scan_dir(core.material_sub("片源")) + self._scan_dir(core.material_dir()):
            self.fg_map[self._label_for(p)] = p
        self.combo_fg["values"] = list(self.fg_map.keys())
        if not self.var_fg.get() or not os.path.exists(self.var_fg.get()):
            if self.fg_map:
                self.var_fg.set(list(self.fg_map.values())[0])
        self._sync_label(self.fg_map, self.var_fg, self.var_fg_lab, self.combo_fg)
        self._on_fg_change()

        # 素材（内置 + 底层目录）
        mats = [("内置 · " + k, v) for k, v in core.builtin_videos().items()]
        for p in self._scan_dir(core.material_sub("底层")):
            mats.append((self._label_for(p), p))
        self.media_pairs = mats
        names = ["（不填充）"] + [m[0] for m in mats]
        for cb, var, var_lab in ((self.combo_bg, self.var_bg, self.var_bg_lab),
                                 (self.combo_bg2, self.var_bg2, self.var_bg2_lab)):
            cb["values"] = names
        self.bg_map = dict(mats)
        self._sync_label(self.bg_map, self.var_bg, self.var_bg_lab,
                         self.combo_bg, empty_text="（不填充）")
        self._sync_label(self.bg_map, self.var_bg2, self.var_bg2_lab,
                         self.combo_bg2, empty_text="（不填充）")
        self._refresh_bg()
        self._refresh_bg2()
        self.var_mat.set("素材目录：" + core.material_dir())
        self._schedule_preview()

    def _scan_dir(self, d):
        out = []
        if os.path.isdir(d):
            for n in sorted(os.listdir(d)):
                if n.lower().endswith(core.MEDIA_EXT):
                    out.append(os.path.join(d, n))
        return out[:40]

    def _sync_label(self, mapping, var_path, var_lab, combo, empty_text=""):
        p = var_path.get()
        if not p:
            var_lab.set(empty_text)
            return
        for lab, real in mapping.items():
            if os.path.normcase(real) == os.path.normcase(p):
                var_lab.set(lab)
                return
        var_lab.set(os.path.basename(p))

    def _pick_from(self, mapping, var_lab, var_path, empty_text="（不填充）"):
        lab = var_lab.get()
        if not lab or lab == empty_text:
            var_path.set("")
            return
        p = mapping.get(lab)
        if p:
            var_path.set(p)
        elif lab and os.path.exists(lab):
            var_path.set(lab)

    def _on_fg_pick(self):
        self._pick_from(self.fg_map, self.var_fg_lab, self.var_fg)
        self._on_fg_change()

    def _on_bg_pick(self):
        self._pick_from(self.bg_map, self.var_bg_lab, self.var_bg, "（不填充）")
        self._refresh_bg()
        self._schedule_preview()

    def _on_bg2_pick(self):
        self._pick_from(self.bg_map, self.var_bg2_lab, self.var_bg2, "（不填充）")
        self._refresh_bg2()
        self._schedule_preview()

    def _browse_fg(self):
        p = filedialog.askopenfilename(title="选择 Bad Apple 片源",
                                       filetypes=[("媒体", "*" + ";*".join(core.MEDIA_EXT)),
                                                  ("所有文件", "*.*")])
        if p:
            self.var_fg.set(p)
            self.var_fg_lab.set(os.path.basename(p))
            self._on_fg_change()

    def _browse_bg(self):
        p = self._ask_media("选择素材 A（黑色部分显示的内容）")
        if p is not None:
            self.var_bg.set(p)
            self.var_bg_lab.set(os.path.basename(p))
            self._refresh_bg()
            self._schedule_preview()

    def _browse_bg2(self):
        p = self._ask_media("选择素材 B（白色部分显示的内容）")
        if p is not None:
            self.var_bg2.set(p)
            self.var_bg2_lab.set(os.path.basename(p))
            self._refresh_bg2()
            self._schedule_preview()

    def _ask_media(self, title):
        return filedialog.askopenfilename(
            title=title,
            filetypes=[("媒体", "*" + ";*".join(core.MEDIA_EXT)),
                       ("所有文件", "*.*")]) or None

    def _on_fg_change(self):
        self._sync_label(self.fg_map, self.var_fg, self.var_fg_lab, self.combo_fg)
        self.fg_info = core.probe(self.var_fg.get())
        if not self.fg_info.get("ok"):
            for _lab, p in self.fg_map.items():
                if os.path.exists(p) and os.path.normcase(p) != os.path.normcase(self.var_fg.get()):
                    self.var_fg.set(p)
                    self._sync_label(self.fg_map, self.var_fg, self.var_fg_lab, self.combo_fg)
                    self.fg_info = core.probe(p)
                    break
        if self.fg_info.get("ok"):
            self.var_fg_desc.set(core.describe(self.var_fg.get()))
            dur = self.fg_info.get("duration") or 0
            self.sld_time.configure(to=max(1.0, dur))
            self.var_time.set(min(self.var_time.get(), max(0.0, dur)))
            self._refresh_mode_ui()
            self._refresh_audio_options()
            self._schedule_preview()
        else:
            self.var_fg_desc.set("读取失败：" + (self.fg_info.get("error") or "未知错误"))

    def _refresh_bg(self):
        self.bg_info = core.probe(self.var_bg.get()) if self.var_bg.get() else {}
        self.var_bg_desc.set(core.describe(self.var_bg.get()) if self.var_bg.get()
                             else "未选择（黑色部分保持纯黑）")
        self._refresh_audio_options()

    def _refresh_bg2(self):
        self.bg2_info = core.probe(self.var_bg2.get()) if self.var_bg2.get() else {}
        self.var_bg2_desc.set(core.describe(self.var_bg2.get()) if self.var_bg2.get()
                              else "未选择（白色部分保持白色剪影）")
        self._refresh_audio_options()

    # ------------------------------------------------------------------
    # 交互
    # ------------------------------------------------------------------
    def _apply_adv(self):
        self._relayout_left()

    def _relayout_left(self):
        """按当前模式/高级开关重排左侧卡片（整体 forget 后按序 pack）"""
        need = ("card_fill", "card_key", "card_recolor", "card_fmt", "card_adv")
        if not all(hasattr(self, n) for n in need):
            return
        mode = self.var_mode.get()
        show = []
        if mode in ("overlay", "dual"):
            show.append(self.card_fill)
        if mode != "alpha":
            show.append(self.card_audio)
        if mode in ("overlay", "alpha"):
            show.append(self.card_key)
        if mode == "recolor":
            show.append(self.card_recolor)
        if mode == "alpha":
            show.append(self.card_fmt)
        seq = [self.card_source, self.card_mode] + show
        if self.var_adv.get():
            seq.append(self.card_adv)
        for c in self._left_cards:
            try:
                c.pack_forget()
            except Exception:
                pass
        for c in seq:
            c.pack(fill="x", pady=(0, 12))

        # 素材 B 只在双素材模式出现
        if mode == "dual":
            self.row_bg2.pack(fill="x", pady=(10, 0), before=self.row_swap)
        else:
            self.row_bg2.pack_forget()
        self._refresh_audio_options()
        self.root.update_idletasks()

    def _refresh_mode_ui(self):
        if not hasattr(self, "_left_cards"):
            return
        self._relayout_left()
        if not self.var_out.get():
            self.var_out.set(os.path.join(core.material_sub("输出", True),
                                          self._default_name()))
        self._schedule_preview()

    def _swap_target(self):
        self.var_target.set("white" if self.var_target.get() == "black" else "black")
        self._schedule_preview()

    def _swap_colors(self):
        a, b = self.var_c1.get(), self.var_c2.get()
        self.var_c1.set(b)
        self.var_c2.set(a)
        self._schedule_preview()

    def _swap_ab(self):
        a, b = self.var_bg.get(), self.var_bg2.get()
        self.var_bg.set(b)
        self.var_bg2.set(a)
        self._sync_label(self.bg_map, self.var_bg, self.var_bg_lab,
                         self.combo_bg, "（不填充）")
        self._sync_label(self.bg_map, self.var_bg2, self.var_bg2_lab,
                         self.combo_bg2, "（不填充）")
        self._refresh_bg()
        self._refresh_bg2()
        self._schedule_preview()

    def _pick_color(self, var):
        rgb, hexv = colorchooser.askcolor(color=var.get(), parent=self.root,
                                          title="选择颜色")
        if hexv:
            var.set(hexv)
            self._schedule_preview()

    def _reset_adv(self):
        self.var_tol.set(0.10)
        self.var_soft.set(0.03)
        self.var_invert.set(False)
        self.var_fit.set("裁切填满（不留黑边）")
        self.var_res.set("跟随 Bad Apple")
        self.var_fps.set("30")
        self.var_crf.set(20)
        self.var_preset.set("veryfast")
        self.var_dur.set("loop_bg")
        self.var_audio.set("fg")
        self._refresh_audio_options()
        self._schedule_preview()

    def _step(self, dt):
        self.var_time.set(max(0.0, self.var_time.get() + dt))
        self.var_time_lab.set(_fmt_mmss(self.var_time.get()))
        self._schedule_preview()

    def _open_material(self):
        d = core.material_dir()
        if os.path.isdir(d):
            try:
                os.startfile(d)  # noqa: S606
            except Exception:
                pass

    def _open_out_dir(self):
        d = os.path.dirname(self.var_out.get() or "")
        if not os.path.isdir(d):
            d = core.material_sub("输出", True)
        try:
            os.startfile(d)  # noqa: S606
        except Exception:
            pass

    def _default_name(self):
        mode = self.var_mode.get()
        base = {"overlay": "合成_叠加", "dual": "合成_双素材",
                "recolor": "合成_换色", "alpha": "透明素材"}.get(mode, "合成")
        ext = self.var_export.get() if mode == "alpha" else "mp4"
        return "%s_%s.%s" % (base, time.strftime("%m%d%H%M"), ext)

    def _pick_out(self):
        mode = self.var_mode.get()
        ext = ("." + self.var_export.get()) if mode == "alpha" else ".mp4"
        p = filedialog.asksaveasfilename(
            title="输出文件", defaultextension=ext,
            initialfile=self._default_name(),
            initialdir=core.material_sub("输出", True),
            filetypes=[("媒体", "*.mp4 *.mkv *.gif"), ("所有文件", "*.*")])
        if p:
            self.var_out.set(p)

    # ------------------------------------------------------------------
    # 参数收集
    # ------------------------------------------------------------------
    def collect(self):
        o = core.Options()
        o.mode = self.var_mode.get()
        o.fg = self.var_fg.get()
        o.bg = self.var_bg.get() if o.mode in ("overlay", "dual") else ""
        o.bg2 = self.var_bg2.get() if o.mode == "dual" else ""
        o.key_target = self.var_target.get()
        o.tolerance = float(self.var_tol.get())
        o.softness = float(self.var_soft.get())
        o.invert = bool(self.var_invert.get())
        o.color1 = self.var_c1.get()
        o.color2 = self.var_c2.get()
        o.fit = {"裁切填满（不留黑边）": "crop", "完整显示（补黑边）": "pad",
                 "拉伸铺满": "stretch"}.get(self.var_fit.get(), "crop")
        o.duration_policy = self.var_dur.get()
        o.audio_policy = self.var_audio.get()
        o.crf = int(self.var_crf.get())
        o.preset = self.var_preset.get()
        o.export_format = (self.var_export.get() if o.mode == "alpha" else "mp4")

        if not self.fg_info:
            self.fg_info = core.probe(o.fg)
        if not self.bg_info and o.bg:
            self.bg_info = core.probe(o.bg)
        if not self.bg2_info and o.bg2:
            self.bg2_info = core.probe(o.bg2)

        res = self.var_res.get()
        if res == "跟随 Bad Apple":
            o.width, o.height = core.even_size(self.fg_info.get("width") or 1280,
                                               self.fg_info.get("height") or 720)
        elif "x" in res:
            try:
                a, b = res.split("x")[:2]
                o.width, o.height = core.even_size(int(a), int(b))
            except ValueError:
                o.width, o.height = 1280, 720
        else:
            o.width, o.height = 1280, 720

        try:
            o.fps = float(self.var_fps.get())
        except ValueError:
            o.fps = self.fg_info.get("fps") or 30.0
        if not o.fps:
            o.fps = self.fg_info.get("fps") or 30.0
        o.out = self.var_out.get() or os.path.join(core.material_sub("输出", True),
                                                   self._default_name())
        return o

    # ------------------------------------------------------------------
    # 预览
    # ------------------------------------------------------------------
    def _schedule_preview(self, *_):
        self.var_time_lab.set(_fmt_mmss(self.var_time.get()))
        if self.busy:
            return
        if self.preview_timer:
            try:
                self.root.after_cancel(self.preview_timer)
            except Exception:
                pass
        self.preview_timer = self.root.after(320, self._run_preview)

    def _run_preview(self):
        if self.busy:
            return
        o = self.collect()
        if not o.fg or not os.path.exists(o.fg):
            self.var_note.set("先在素材目录里放一个 Bad Apple 片源")
            return
        if o.mode == "overlay" and not o.bg:
            self.var_note.set("再选一个素材 A 就能预览叠加效果")
            return
        if o.mode == "dual" and not (o.bg or o.bg2):
            self.var_note.set("至少选一个素材（A 或 B）")
            return
        self.preview_id += 1
        rid = self.preview_id
        png = os.path.join(self.tmpdir, "preview_%d.png" % rid)
        try:
            args = self._preview_args(o, png)
        except Exception as exc:
            self.var_note.set("预览失败：%s" % exc)
            return
        threading.Thread(target=self._preview_worker, args=(rid, args, png, o),
                         daemon=True).start()

    def _preview_args(self, o, png):
        w, h = core.even_size(o.width, o.height)
        fps = o.fps
        graph, vout, layout = core.build_graph(o, w, h, fps)
        t = max(0.0, float(self.var_time.get()))
        args = [core.ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error"]
        args += ["-ss", "%.3f" % t, "-i", o.fg]
        for idx, path, info in ((layout.get("a"), o.bg, self.bg_info),
                                (layout.get("b"), o.bg2, self.bg2_info)):
            if idx is None or not path:
                continue
            if core.is_image(path):
                args.extend(["-loop", "1", "-framerate", core._fps_expr(fps)])
            else:
                d = float(info.get("duration") or 0.0)
                bt = (t % d) if d > 0 else t
                args.extend(["-ss", "%.3f" % bt])
            args.extend(["-i", path])
        graph += (";[vout]scale=960:960:force_original_aspect_ratio=decrease:"
                  "force_divisible_by=2[pvout]")
        args += ["-filter_complex", graph, "-map", "[pvout]",
                 "-frames:v", "1", "-an", "-c:v", "png", png]
        return args

    def _preview_worker(self, rid, args, png, o):
        try:
            if self.preview_proc and self.preview_proc.poll() is None:
                try:
                    self.preview_proc.kill()
                except Exception:
                    pass
            r = subprocess.run(args, capture_output=True, text=True,
                               encoding="utf-8", errors="replace",
                               creationflags=core.CREATE_NO_WINDOW)
            if r.returncode != 0:
                UI_QUEUE.put(("preview_fail", rid, (r.stderr or "")[-400:]))
                return
            UI_QUEUE.put(("preview_ok", rid, png, o.mode == "alpha"))
        except Exception as exc:
            UI_QUEUE.put(("preview_fail", rid, str(exc)))

    def _show_preview(self, png, transparent):
        try:
            with Image.open(png) as im:
                if transparent and im.mode in ("RGBA", "LA", "PA"):
                    im = im.convert("RGBA")
                    cb = core.checkerboard(im.size)
                    cb.paste(im, (0, 0), im)
                    im = cb
                else:
                    im = im.convert("RGB")
                bw = max(120, self.preview_box.winfo_width() - 16)
                bh = max(90, self.preview_box.winfo_height() - 16)
                im.thumbnail((bw, bh), Image.LANCZOS)
                self.preview_photo = ImageTk.PhotoImage(im)
                self.lab_preview.configure(image=self.preview_photo)
        except Exception as exc:
            self.var_note.set("预览渲染失败：%s" % exc)

    # ------------------------------------------------------------------
    # 导出
    # ------------------------------------------------------------------
    def _start(self):
        if self.busy:
            return
        o = self.collect()
        if not o.fg or not os.path.exists(o.fg):
            messagebox.showwarning(APP_NAME, "请先选择 Bad Apple 片源")
            return
        if o.mode == "overlay" and not o.bg:
            messagebox.showwarning(APP_NAME, "「叠加到素材」需要先选一个素材 A")
            return
        if o.mode == "dual" and not (o.bg or o.bg2):
            messagebox.showwarning(APP_NAME, "「双素材填充」至少需要一个素材")
            return
        self.fg_info = core.probe(o.fg)
        self.bg_info = core.probe(o.bg) if o.bg else {}
        self.bg2_info = core.probe(o.bg2) if o.bg2 else {}
        if not self.fg_info.get("ok"):
            messagebox.showerror(APP_NAME, "片源无法读取：" + self.fg_info.get("error", ""))
            return
        for label, path, info in (("素材 A", o.bg, self.bg_info),
                                  ("素材 B", o.bg2, self.bg2_info)):
            if path and not info.get("ok"):
                messagebox.showerror(APP_NAME, "%s 无法读取：%s" % (label, info.get("error", "")))
                return

        out = o.out
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        args, total = core.build_cmd(o, self.fg_info, self.bg_info, out,
                                     progress=True, bg2_info=self.bg2_info)
        self.last_out = out
        self.total_seconds = total
        self.busy = True
        self.cancel_flag = False
        self.start_ts = time.time()
        self.btn_run.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        self.var_status.set("正在合成…")
        self.var_progress.set(0)
        self.var_pct.set("0%")
        self._log("输出：%s" % out)
        self._log("模式=%s 目标=%s tol=%.3f soft=%.3f %dx%d@%g 时长=%.2fs" % (
            o.mode, o.key_target, o.tolerance, o.softness,
            o.width, o.height, o.fps, total))
        try:
            self.proc = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                stdin=subprocess.PIPE, text=True, encoding="utf-8",
                errors="replace", creationflags=core.CREATE_NO_WINDOW)
        except Exception as exc:
            self._finish(False, "启动 ffmpeg 失败：%s" % exc)
            return
        threading.Thread(target=self._read_progress, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def _read_progress(self):
        total = float(getattr(self, "total_seconds", 0.0) or 0.0)
        p = self.proc
        try:
            for line in p.stdout:
                if not line:
                    break
                line = line.strip()
                if line.startswith("out_time_us="):
                    try:
                        us = int(line.split("=", 1)[1])
                    except ValueError:
                        continue
                    if total > 0:
                        UI_QUEUE.put(("progress", min(100.0, us / 1e6 / total * 100.0)))
                elif line.startswith("speed="):
                    UI_QUEUE.put(("speed", line.split("=", 1)[1]))
                elif line == "progress=end":
                    UI_QUEUE.put(("progress", 100.0))
        except Exception:
            pass
        finally:
            try:
                p.wait(timeout=20)
            except Exception:
                pass
            UI_QUEUE.put(("done_export", p.returncode == 0 and not self.cancel_flag,
                          p.returncode))

    def _read_stderr(self):
        p = self.proc
        try:
            tail = []
            for line in p.stderr:
                if not line:
                    break
                tail.append(line.rstrip())
                if len(tail) > 200:
                    tail.pop(0)
            if tail:
                UI_QUEUE.put(("stderr", "\n".join(tail[-10:])))
        except Exception:
            pass

    def _cancel(self):
        self.cancel_flag = True
        self.var_status.set("正在取消…")
        try:
            if self.proc and self.proc.stdin:
                self.proc.stdin.write("q\n")
                self.proc.stdin.flush()
        except Exception:
            pass

        def killer():
            p = self.proc
            for wait in (3.0, 2.0):
                if p is None or p.poll() is not None:
                    break
                time.sleep(wait)
                if p.poll() is None:
                    try:
                        p.terminate()
                    except Exception:
                        pass
            if p and p.poll() is None:
                try:
                    p.kill()
                except Exception:
                    pass
        threading.Thread(target=killer, daemon=True).start()

    def _finish(self, ok, msg):
        self.busy = False
        self.btn_run.configure(state="normal")
        self.btn_cancel.configure(state="disabled")
        self.var_status.set(msg)
        self.var_progress.set(100.0 if ok else 0.0)
        self.var_pct.set("100%" if ok else "--")
        self._log(msg)
        self._save_config()
        if ok:
            self._log("完成：%s" % self.last_out)
        else:
            p = self.last_out
            if p and os.path.exists(p) and p.endswith(".mp4"):
                try:
                    os.remove(p)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # 队列轮询
    # ------------------------------------------------------------------
    def _poll(self):
        try:
            while True:
                self._handle(UI_QUEUE.get_nowait())
        except queue.Empty:
            pass
        self.root.after(200, self._poll)

    def _handle(self, item):
        kind = item[0]
        if kind == "progress":
            v = float(item[1])
            self.var_progress.set(v)
            self.var_pct.set("%.0f%%" % v)
            el = time.time() - self.start_ts if self.start_ts else 0
            self.var_status.set("正在合成… 已用 %s" % core.fmt_time(el))
        elif kind == "speed":
            self.var_status.set("正在合成… 速率 %s" % item[1])
        elif kind == "done_export":
            ok, code = item[1], item[2]
            if self.cancel_flag:
                self._finish(False, "已取消，未生成文件")
            else:
                el = time.time() - self.start_ts if self.start_ts else 0
                self._finish(ok, ("完成，用时 %s" % core.fmt_time(el)) if ok
                             else "失败（退出码 %s）" % code)
                self._schedule_preview()
        elif kind == "stderr":
            if item[1].strip():
                self._log(item[1])
        elif kind == "preview_ok":
            rid, png = item[1], item[2]
            if rid == self.preview_id:
                try:
                    self._show_preview(png, item[3])
                    self.var_note.set("预览已更新（透明区域显示为棋盘格）")
                finally:
                    try:
                        os.remove(png)
                    except Exception:
                        pass
        elif kind == "preview_fail":
            if item[1] == self.preview_id:
                self.var_note.set("预览失败：" + (item[2] or "").replace("\n", " ")[:300])
        elif kind == "cap":
            miss_f, miss_e = item[1], item[2]
            if not miss_f and not miss_e:
                self.var_cap.set("ffmpeg 就绪")
                self._log("ffmpeg 能力检查通过")
            else:
                self.var_cap.set("ffmpeg 缺少组件！")
                self._log("缺少滤镜：%s / 缺少编码器：%s" % (miss_f, miss_e))

    def _check_cap(self):
        def work():
            UI_QUEUE.put(("cap",) + tuple(core.check_capabilities()))
        threading.Thread(target=work, daemon=True).start()

    def _log(self, msg):
        ts = time.strftime("%H:%M:%S")
        try:
            self.log.insert("end", "[%s] %s\n" % (ts, msg))
            self.log.see("end")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 配置
    # ------------------------------------------------------------------
    def _load_config(self):
        try:
            if not os.path.exists(core.CONFIG_FILE):
                return
            import json
            with open(core.CONFIG_FILE, "r", encoding="utf-8") as fp:
                d = json.load(fp)
        except Exception:
            return
        self.var_mode.set(d.get("mode", "overlay"))
        self.var_target.set(d.get("key_target", "black"))
        self.var_tol.set(d.get("tolerance", 0.10))
        self.var_soft.set(d.get("softness", 0.03))
        self.var_invert.set(d.get("invert", False))
        self.var_c1.set(d.get("color1", "#111827"))
        self.var_c2.set(d.get("color2", "#f43f5e"))
        self.var_fit.set(d.get("fit", "裁切填满（不留黑边）"))
        self.var_dur.set(d.get("duration_policy", "loop_bg"))
        self.var_audio.set(d.get("audio_policy", "fg"))
        self.var_res.set(d.get("res", "跟随 Bad Apple"))
        self.var_fps.set(d.get("fps", "30"))
        self.var_crf.set(d.get("crf", 20))
        self.var_preset.set(d.get("preset", "veryfast"))
        self.var_export.set(d.get("export", "gif"))
        self.var_adv.set(bool(d.get("advanced", False)))
        fg = d.get("fg") or ""
        if fg and os.path.exists(fg):
            self.var_fg.set(fg)
        for var, key in ((self.var_bg, "bg"), (self.var_bg2, "bg2")):
            v = d.get(key) or ""
            if v and (os.path.exists(v) or v in core.builtin_videos().values()):
                var.set(v)

    def _save_config(self):
        try:
            import json
            os.makedirs(os.path.dirname(core.CONFIG_FILE), exist_ok=True)
            data = {
                "mode": self.var_mode.get(), "key_target": self.var_target.get(),
                "tolerance": self.var_tol.get(), "softness": self.var_soft.get(),
                "invert": self.var_invert.get(), "color1": self.var_c1.get(),
                "color2": self.var_c2.get(), "fit": self.var_fit.get(),
                "duration_policy": self.var_dur.get(),
                "audio_policy": self.var_audio.get(), "res": self.var_res.get(),
                "fps": self.var_fps.get(), "crf": self.var_crf.get(),
                "preset": self.var_preset.get(), "export": self.var_export.get(),
                "advanced": self.var_adv.get(),
                "fg": self.var_fg.get(), "bg": self.var_bg.get(),
                "bg2": self.var_bg2.get(),
            }
            with open(core.CONFIG_FILE, "w", encoding="utf-8") as fp:
                json.dump(data, fp, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _on_close(self):
        self._save_config()
        try:
            if self.proc and self.proc.poll() is None:
                self.proc.kill()
        except Exception:
            pass
        self.root.destroy()


def create_app(root):
    return App(root)


def launch_gui():
    root = tk.Tk()
    app = create_app(root)
    root.protocol("WM_DELETE_WINDOW", app._on_close)
    root.mainloop()
