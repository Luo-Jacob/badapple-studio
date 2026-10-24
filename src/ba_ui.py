# -*- coding: utf-8 -*-
"""圆角界面组件库：卡片、按钮、开关、滚动容器。

tkinter/ttk 本身画不出圆角，这里统一用 Canvas 自绘，
配色沿用工作区既有规范（浅色卡片 + 蓝色主色）。
"""
import math

import tkinter as tk
from tkinter import ttk

# ---------------------------------------------------------------------------
# 主题
# ---------------------------------------------------------------------------
BG = "#eef2f8"          # 窗口底色
CARD = "#ffffff"        # 卡片
SOFT = "#f6f8fc"        # 卡片内浅底
BORDER = "#e3e9f2"      # 描边
TEXT = "#1f2937"
MUTED = "#6b7280"
HINT = "#94a3b8"
ACCENT = "#3b82f6"
ACCENT_D = "#2563eb"
ACCENT_L = "#eff6ff"
DANGER = "#ef4444"
DANGER_D = "#dc2626"
OK = "#10b981"

FONT = ("Microsoft YaHei UI", 9)
FONT_B = ("Microsoft YaHei UI", 9, "bold")
FONT_TITLE = ("Microsoft YaHei UI", 14, "bold")
FONT_SMALL = ("Microsoft YaHei UI", 8)


def round_points(x1, y1, x2, y2, r, steps=5):
    """圆角矩形的顶点序列（供 create_polygon 使用）"""
    r = min(r, (x2 - x1) / 2.0, (y2 - y1) / 2.0)
    if r <= 0:
        return [x1, y1, x2, y1, x2, y2, x1, y2]
    pts = []
    for cx, cy, a0 in ((x2 - r, y1 + r, -90), (x2 - r, y2 - r, 0),
                       (x1 + r, y2 - r, 90), (x1 + r, y1 + r, 180)):
        for i in range(steps + 1):
            a = math.radians(a0 + 90.0 * i / steps)
            pts.extend([cx + r * math.cos(a), cy + r * math.sin(a)])
    return pts


class RoundCard(tk.Canvas):
    """圆角卡片：外框自绘，内容放进 .body（普通 Frame）"""

    def __init__(self, master, radius=16, pad=16, fill=CARD,
                 border=BORDER, **kw):
        self._fill = fill
        self._border = border
        self._radius = radius
        self._pad = pad
        self._bg = kw.pop("bg", BG)
        tk.Canvas.__init__(self, master, highlightthickness=0, bd=0,
                           bg=self._bg, **kw)
        self.body = tk.Frame(self, bg=fill)
        self._win = self.create_window(pad, pad, anchor="nw", window=self.body)
        self.bind("<Configure>", self._on_resize)
        self.body.bind("<Configure>", self._on_body)

    def _on_body(self, _e=None):
        h = self.body.winfo_reqheight()
        if h > 0:
            self.configure(height=h + self._pad * 2)
        w = max(10, self.winfo_width() - self._pad * 2)
        self.itemconfigure(self._win, width=w)

    def _on_resize(self, event=None):
        self.delete("bg")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4 or h < 4:
            return
        pts = round_points(1, 1, w - 1, h - 1, self._radius)
        self.create_polygon(pts, fill=self._fill, outline=self._border,
                            smooth=True, tags="bg")
        self.tag_lower("bg")
        self._on_body()


class RoundButton(tk.Canvas):
    """圆角按钮。kind: primary / ghost / danger / soft"""

    STYLE = {
        "primary": (ACCENT, ACCENT_D, "#ffffff", ACCENT),
        "ghost": (CARD, "#f1f5fb", TEXT, BORDER),
        "danger": (DANGER, DANGER_D, "#ffffff", DANGER),
        "soft": (ACCENT_L, "#dbeafe", ACCENT_D, "#c7dbfd"),
    }

    def __init__(self, master, text="", command=None, kind="ghost",
                 width=110, height=34, radius=11, font=FONT_B, **kw):
        self._kind = kind
        self._text = text
        self._cmd = command
        self._radius = radius
        self._state = "normal"
        self._font = font
        bg = kw.pop("bg", BG)
        tk.Canvas.__init__(self, master, width=width, height=height,
                           highlightthickness=0, bd=0, bg=bg, **kw)
        self.bind("<Button-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self._draw("normal")

    def _colors(self, state):
        base, hover, fg_line = self.STYLE[self._kind][0], self.STYLE[self._kind][1], self.STYLE[self._kind][3]
        fill = base
        if state == "hover":
            fill = hover
        elif state == "pressed":
            fill = self.STYLE[self._kind][1]
        if self._state == "disabled":
            fill, fg_line = "#eef1f6", "#dde3ec"
        return fill, fg_line

    def _draw(self, state):
        self.delete("all")
        w, h = int(self["width"]), int(self["height"])
        fill, line = self._colors(state)
        fg = self.STYLE[self._kind][2]
        if self._state == "disabled":
            fg = "#aab3c0"
        pts = round_points(1, 1, w - 1, h - 1, self._radius)
        self.create_polygon(pts, fill=fill, outline=line, smooth=True)
        self.create_text(w / 2, h / 2, text=self._text, fill=fg, font=self._font)

    def _enter(self, _e):
        if self._state != "disabled":
            self._draw("hover")

    def _leave(self, _e):
        if self._state != "disabled":
            self._draw("normal")

    def _press(self, _e):
        if self._state == "disabled":
            return
        self._draw("pressed")

    def _release(self, _e):
        if self._state == "disabled":
            return
        self._draw("hover")
        if self._cmd:
            self._cmd()

    def configure(self, **kw):
        if "state" in kw:
            self._state = kw.pop("state")
            self._draw("normal")
        if "text" in kw:
            self._text = kw.pop("text")
            self._draw("normal")
        if "kind" in kw:
            self._kind = kw.pop("kind")
            self._draw("normal")
        if kw:
            tk.Canvas.configure(self, **kw)

    config = configure

    def cget(self, key):
        if key == "state":
            return self._state
        if key == "text":
            return self._text
        return tk.Canvas.cget(self, key)


class Switch(tk.Canvas):
    """小开关：圆角轨道 + 圆滑块"""

    def __init__(self, master, text="", variable=None, command=None,
                 width=170, height=26, bg=BG):
        tk.Canvas.__init__(self, master, width=width, height=height,
                           highlightthickness=0, bd=0, bg=bg)
        self._var = variable
        self._cmd = command
        self._text = text
        if self._var is not None:
            try:
                self._var.trace_add("write", lambda *_: self._draw())
            except Exception:
                pass
        self.bind("<Button-1>", self._toggle)
        self._draw()

    def _on(self):
        try:
            return bool(self._var.get())
        except Exception:
            return False

    def _toggle(self, _e=None):
        if self._var is not None:
            self._var.set(not self._on())
        self._draw()
        if self._cmd:
            self._cmd()

    def _draw(self):
        self.delete("all")
        h = int(self["height"])
        w = int(self["width"])
        on = self._on()
        track = ACCENT if on else "#d3dae5"
        x1, y1 = 2, h / 2 - 9
        x2, y2 = x1 + 36, h / 2 + 9
        pts = round_points(x1, y1, x2, y2, 9)
        self.create_polygon(pts, fill=track, outline=track, smooth=True)
        cx = x2 - 9 if on else x1 + 9
        self.create_oval(cx - 7, h / 2 - 7, cx + 7, h / 2 + 7,
                         fill="#ffffff", outline="#ffffff")
        if self._text:
            self.create_text(x2 + 10, h / 2, anchor="w", text=self._text,
                             fill=TEXT, font=FONT)


class ScrolledFrame(tk.Frame):
    """带滚轮的纵向滚动容器，内容为 .inner"""

    def __init__(self, master, bg=BG, **kw):
        tk.Frame.__init__(self, master, bg=bg, **kw)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window((0, 0), window=self.inner,
                                              anchor="nw")
        sb = ttk.Scrollbar(self, orient="vertical",
                           command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner.bind("<Configure>", self._on_inner)
        self.canvas.bind("<Configure>", self._on_canvas)
        for w in (self.canvas, self.inner):
            w.bind("<MouseWheel>", self._wheel)
            w.bind("<Button-4>", self._wheel)
            w.bind("<Button-5>", self._wheel)

    def _on_inner(self, _e):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas(self, e):
        self.canvas.itemconfigure(self._win, width=e.width)

    def _wheel(self, e):
        d = 0
        if getattr(e, "delta", 0):
            d = -1 if e.delta > 0 else 1
        elif getattr(e, "num", 0) == 4:
            d = -1
        elif getattr(e, "num", 0) == 5:
            d = 1
        self.canvas.yview_scroll(d * 2, "units")
        return "break"


def apply_theme(root):
    """统一一下 ttk 原生控件的外观（输入框、下拉、滑块）"""
    st = ttk.Style()
    try:
        st.theme_use("clam")
    except Exception:
        pass
    st.configure("TCombobox", fieldbackground="#ffffff", background="#ffffff",
                 bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                 arrowcolor=MUTED, padding=(6, 4), relief="flat")
    st.map("TCombobox", fieldbackground=[("readonly", "#ffffff")],
           bordercolor=[("focus", ACCENT)])
    st.configure("TEntry", fieldbackground="#ffffff", bordercolor=BORDER,
                 lightcolor=BORDER, darkcolor=BORDER, padding=(6, 5),
                 relief="flat")
    st.map("TEntry", bordercolor=[("focus", ACCENT)])
    st.configure("TFrame", background=BG)
    st.configure("Horizontal.TScale", background=CARD, troughcolor="#e8edf5",
                 bordercolor=BORDER, lightcolor=ACCENT, darkcolor=ACCENT)
    st.configure("Vertical.TScrollbar", background="#dfe5ee",
                 troughcolor=BG, bordercolor=BG, arrowcolor=MUTED)
    st.configure("TProgressbar", troughcolor="#e8edf5", background=ACCENT,
                 bordercolor="#e8edf5", lightcolor=ACCENT, darkcolor=ACCENT,
                 thickness=8)
    st.configure("Hint.TLabel", background=CARD, foreground=MUTED, font=FONT_SMALL)
    st.configure("Sub.TLabel", background=CARD, foreground=TEXT, font=FONT)
    try:
        root.configure(bg=BG)
    except Exception:
        pass
