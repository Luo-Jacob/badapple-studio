# Bad Apple Studio

把 **Bad Apple!! 影绘**的黑/白换成别的颜色，或者换成视频、图片 —— 一个 Windows 桌面小工具。

影绘版画面只有纯黑纯白两种颜色，天然适合抠像。这个工具做的事情就是：把黑色（或白色）变透明，让你自己的素材从下面透出来，然后合成一个视频。

> ⚠️ **本项目不包含 Bad Apple 片源**。片源是他人（上海爱丽丝幻乐团 / 同人二次创作）的作品，请自行准备，且仅作个人学习交流使用。详见文末「版权与声明」。

## 能做什么

| 模式 | 效果 |
|---|---|
| **叠加到素材** | 黑色部分变透明，露出下面的素材，白色剪影保留（也可以反过来抠白留黑） |
| **双素材填充** | 黑色部分播素材 A，白色部分播素材 B；只填一边也行，另一边保留原本的黑/白 |
| **纯换色** | 黑色换成色 1、白色换成色 2，输出不透明视频 |
| **导出透明素材** | 抠好透明通道的 GIF / MKV，丢进剪映、PR 自己排 |

素材可以是**视频或图片**。程序自带三个动态底视频（流光 / 星夜 / 极光），不用自备素材也能立刻出片。

## 界面

- 左侧选参数、右侧实时预览（抽帧渲染，透明区显示为棋盘格），拖动时间轴可以看任意一秒的效果
- **简洁模式**（默认）只留最常用的几项，文案都是大白话；右上角打开「高级设置」才展开容差、柔化、分辨率、帧率、CRF、时长策略、音轨策略等专业参数
- 开始合成后有进度条、速率和日志，可随时取消

## 快速开始

### 直接用（Windows）

到 [Releases](../../releases) 下载 `BadAppleStudio.zip`，解压后双击 `BadAppleStudio.exe`。首次启动会自动在程序旁边建好素材目录：

```
BadAppleStudio\
  BadAppleStudio.exe
  BadApple\          ← 自动创建
    片源\            ← 把 Bad Apple 影绘视频放这里
    底层\            ← 放你自己的视频/图片
    输出\            ← 合成结果默认存这里
```

把片源丢进 `片源\`，回程序点下拉框旁边的 `↻` 刷新，选好模式和素材，点「开始合成」。

### 从源码运行

```bash
pip install imageio-ffmpeg pillow
python src/badapple_studio.py
```

只依赖这两个包（ffmpeg 由 imageio-ffmpeg 提供，不用自己装）。

### 打包成 exe

```bash
pip install pyinstaller
FF=$(python -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())")

python -m PyInstaller --noconfirm --onedir --noconsole --name BadAppleStudio \
  --add-binary "$FF;ffmpeg_bin" \
  --add-data "<绝对路径>/assets/builtin;builtin" \
  --exclude-module imageio_ffmpeg \
  src/badapple_studio.py
```

两个坑：`--add-data` / `--add-binary` 的源路径必须写**绝对路径**（相对路径会被当成相对于 spec 目录）；另外 PyInstaller 在重建时会整体删除输出目录，建议每次换个新的 `--distpath`。

## 目录结构

```
src/
  badapple_studio.py   核心：媒体探测、滤镜图构造、ffmpeg 命令、自检
  ba_app.py            界面（tkinter）
  ba_ui.py             圆角组件库（Canvas 自绘卡片/按钮/开关）
assets/builtin/        内置底视频（ffmpeg lavfi 生成，可自由使用）
build/                 验证脚本（滤镜链 / 核心层 / GUI 冒烟 / 演示生成）
```

## 它是怎么抠像的

核心就一条 ffmpeg 滤镜链。`lumakey` 把亮度低于阈值的像素变透明（`threshold=0` 抠黑、`threshold=1` 抠白），`tolerance` 控制范围、`softness` 控制边缘过渡：

```
[0:v] ... ,format=yuva420p,lumakey=threshold=0:tolerance=0.10:softness=0.03[fg]
[1:v] ... ,format=yuv420p[base]
[base][fg]overlay=format=yuv420:alpha=straight,format=yuv420p[vout]
```

双素材填充多两步：用 `alphaextract` 从抠像结果里取出「哪里是白」的遮罩，再用 `alphamerge` 把素材 B 贴上去，最后叠在素材 A 上：

```
[0:v] ... lumakey=threshold=0 ...[fgw]
[fgw]alphaextract,format=gray[mask]
[bb][mask]alphamerge[bp]
[ba][bp]overlay=...
```

几个实测出来的结论：

- alpha 必须在 `overlay` **之后**才转 `yuv420p`，否则透明信息会被协商掉
- `filter_complex` 里不能留没被消费的分支，否则 ffmpeg 报 `has an unconnected output`
- imageio-ffmpeg 自带的 ffmpeg 构建**写不出 VP8/VP9 的 alpha**，所以透明导出走 GIF（调色板预留透明色）和 MKV+FFV1，没有 WebM

## 自检

打包后不方便开界面验证，程序留了两个命令行入口：

```bash
BadAppleStudio.exe --info       # 打印 ffmpeg 路径、素材目录、内置底视频、片源列表
BadAppleStudio.exe --selftest   # 造测试素材，跑 5 项像素级断言（黑透明/白透明/换色/透明GIF/透明MKV）
```

## 版权与声明

- **片源**：Bad Apple!! 原曲出自上海爱丽丝幻乐团（ZUN），影绘 PV 为同人二次创作。本项目**不附带、不分发任何片源**，也请勿将片源与本工具一起再分发。仅限个人学习交流。
- **内置底视频**：`assets/builtin/` 下三个视频由本项目的 ffmpeg 滤镜（lavfi gradients）生成，无第三方版权，可自由使用。
- **ffmpeg**：运行时由 [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg) 提供，其 Windows 构建为 GPL 授权；打包分发 exe 时需注意 GPL 的相应义务，详见 `THIRD_PARTY_NOTICES.txt`。
- **本工具源码**：GPL-3.0，见 `LICENSE`。
