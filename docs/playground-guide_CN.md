# Playground 实时镜像台 — 使用指南

**中文** | [English](./playground-guide.md)

> **一句话**：一边让 ScreenForge 跑用例，一边在浏览器里实时看到**生成的 pytest 代码逐行长出来 + 每步的页面截图**。
>
> 本文是**面向使用者的 quickstart**。架构、红线契约、内存模型见 [capability-matrix_CN.md](./capability-matrix_CN.md#playground-实时镜像台live-mirror2026-06)。

---

## 心智模型：这是两个进程

实时镜像**不是一条命令**，而是**两个进程配合**——这是最容易踩坑的地方：

```
┌─────────────────────────────┐         ┌──────────────────────────────────┐
│  进程 1：展示服务器           │  HTTP   │  进程 2：执行进程（每步一个/多步） │
│  screenforge --playground    │◄────────┤  screenforge --action ...         │
│                              │  POST   │            --playground-sink       │
│  常驻，:7860                 │  /step  │            --session-id <名字>     │
│  浏览器打开它看效果           │         │  跑完即退；把每步推给服务器        │
└─────────────────────────────┘         └──────────────────────────────────┘
         ▲
         │ 浏览器访问 http://127.0.0.1:7860
       （你）
```

- **进程 1（服务器）**：`screenforge --playground`，常驻在 `:7860`。**你用浏览器打开它**。它本身不操作任何页面，只负责展示。
- **进程 2（执行）**：真正驱动 UI 的 `--action` / `--workflow` / `main.py`。加上 `--playground-sink` 后，它每成功一步就把**代码 + 截图**推给进程 1。

> **为什么分两个进程？** 执行进程是**短命的**——一条 `--action` 跑完就退出。展示界面必须常驻才能持续显示，所以独立成一个服务器。两者之间用 HTTP 通信（无共享内存）。

---

## Quickstart（Web，最省事）

### 第 1 步：起服务器（终端 A，常驻）

```bash
screenforge --playground
# → Starting Playground on http://127.0.0.1:7860
```

浏览器打开 **http://127.0.0.1:7860**。现在是空的，等着接收步骤。

> 启动日志里若反复出现 `CDP screencast disconnected: Connection refused ... Reconnecting` —— **正常无害**，见[故障排查](#故障排查)。

### 第 2 步：喂步骤进去（终端 B）

**关键：多步必须带同一个 `--session-id`**，否则连不成一条时间线（见下一节）。

```bash
# 第 1 步：打开页面
screenforge --action goto --platform web \
  --extra-value "https://example.com" \
  --session-id demo --playground-sink --json

# 第 2 步：断言标题存在
screenforge --action assert_exist --platform web \
  --locator-type text --locator-value "Example Domain" \
  --session-id demo --playground-sink --json

# 第 3 步：点击链接
screenforge --action click --platform web \
  --locator-type text --locator-value "Learn more" \
  --session-id demo --playground-sink --json
```

每跑一条，浏览器里**立刻**多一行代码 + 一帧截图。三步跑完，你会看到一条完整的 `demo` 时间线：`goto → assert → click`。

> 第一次跑 `--action --platform web` 会自动拉起一个**可见的 Chromium**（持久化，后续命令复用）。这也顺带消除了第 1 步那个 `Connection refused` 日志。

---

## 为什么多步必须带 `--session-id`？（最重要的一点）

这是**隐性但关键**的契约：

- **每条裸 `--action` 命令都是独立进程，有独立的随机 `run_id`。**
- Playground 按 `run_id` 把步骤分到不同的**时间线桶**里。
- 所以**不带 `--session-id` 的多条命令，会各自落进不同的桶**——你看到的不是一条连续的 5 步流程，而是 5 条互不相干的单步记录。

`--session-id <名字>` 让多条命令**共享同一个 `run_id`**，从而：

1. 步骤编号连续（1, 2, 3…），而不是每条都从 1 开始；
2. 在 playground 里呈现为**一条**时间线；
3. 落盘也归到同一个会话目录。

> **一个 session = 一条时间线。** 换了 session（或裸跑无 session），playground 会**清空历史、重新开始**一条新时间线——不会把两条流程的步骤混在一起。

完成后收尾（可选，归档该会话）：

```bash
screenforge --session-end demo
```

### 用 workflow 则天生连续，无需 session-id

多步 YAML 是**单进程内循环**，步骤天然连续，直接开 sink 即可：

```bash
screenforge --workflow ./workflows/login.yaml --platform web \
  --playground-sink --json
```

---

## 人类录制模式（main.py）

交互式录制（你敲自然语言，AI 决策）也能镜像：

```bash
python main.py --platform web --playground-sink
```

整个录制会话作为一条时间线持续推送，对标 Cypress Studio 的"边录边看"。

---

## 选项速查

| 选项 | 用在哪个进程 | 说明 |
|---|---|---|
| `--playground` | 服务器 | 起常驻展示进程 |
| `--playground-port <N>` | 服务器 | 改端口（默认 `7860`） |
| `--playground-sink` | 执行进程 | **开关**：把每步推给服务器（**默认关**，关闭时零开销） |
| `--playground-url <URL>` | 执行进程 | 服务器地址（默认 `http://127.0.0.1:7860`） |
| `--session-id <名字>` | 执行进程 | **多步必带**：把多条命令绑成一条时间线 |

> `--playground-sink` 默认关 —— 纯 CI / agent 跑测试**零开销**（连截图都不抓）。只在你想"边写边看"时才开。

---

## 界面功能

### 一键在 IDE 中打开生成的用例

顶栏有一个 **「Open in <你的 IDE>」** 按钮。playground 启动时会**自动扫描你 PATH 上已装的编辑器**（VS Code / Trae / Cursor / Windsurf / Zed / Sublime / IntelliJ / PyCharm / Vim / Neovim），按钮文案随之变化——比如你装了 Trae，就显示「Open in Trae」。

- **点按钮**（或按 `⌘E` / `Ctrl-E`）：用当前选中的编辑器打开**正在生成的那个 `test_*.py`**，并定位到最新一行。
- **点右侧 `▾`**：下拉切换编辑器；**选择会记到 `localStorage`**，下次自动用它。
- 装了多个就都列出来；**一个都没检测到**时按钮自动禁用，并提示你装一个带 CLI 的编辑器（如 `code` / `trae`）。

> 打开动作由**常驻 playground 进程**执行（它跑 `trae -g <file>:<line>` 这类命令）——浏览器本身不能起进程。服务器只绑 `127.0.0.1`，且用固定参数列表（非 shell 字符串）调用，文件路径无法被注入成命令。

### 连接状态指示（Live / Idle / Disconnected）

顶栏右侧的状态点如实反映**目标设备/网页**是否还在产出步骤，而不是只看浏览器到服务器的连接：

| 状态 | 含义 |
|---|---|
| 🟢 **Live** | 正在持续收到步骤/截图（运行中） |
| 🟡 **Idle** | 连接正常，但目标已**安静 ~4s**（run 结束或暂停）——不是出错 |
| 🔴 **Disconnected** | 到 playground 的 SSE 真的断了（服务器没了） |

> 为什么需要 Idle：浏览器到 playground 的 SSE 是**常驻**的，永远"连着"。所以 run 跑完后，单看连接会一直显示绿灯——那是假的"Live"。改成**按活动判定**：超过 ~4s 没有新步骤就降为 Idle（琥珀色，截图角标也同步变 `IDLE`），下一步到达又自动转回 Live。

### 明亮 / 黑暗主题切换

顶栏的 **☀/🌙 按钮**在明暗两套主题间切换：

- **黑暗（默认）**：锻造台风格——近黑底 + 熔融橙（ember）信号色，开发者工具质感。
- **明亮**：「冷却的钢 · 蓝图纸」——暖纸面 + 墨蓝文字，同一套 ember 标识加深到 `#ea580c` 以满足明亮底的 WCAG AA 对比度；代码高亮另配了一套明亮专用的墨色 Prism 配色（函数名沿用品牌橙）。
- **记忆**：选择写入 `localStorage`；下次打开**首屏即按上次的主题渲染**（`<head>` 内预设，无黑白闪烁）。没选过则跟随系统 `prefers-color-scheme`。

> 截图区里的**被测页面**始终按其本来面貌显示（明亮主题下不会被强行染白）——playground 只切换自己的界面外壳，不改你应用的样子。

### 时间旅行（点击帧回溯）

底部**胶片轨（filmstrip）**和右下**步骤历史**里的每一项都可点击：点任意一帧 / 一步，左侧大截图会**跳回那一步的画面**，同时右侧代码栏**高亮对应行**。三处（截图 / 代码 / 历史）联动。

---

## 故障排查

| 现象 | 原因 | 解法 |
|---|---|---|
| 启动日志刷 `CDP screencast disconnected: Connection refused` | 服务器在等一个还没起的浏览器（CDP `:9333`）。这是 Web 的**连续帧预览**附加层，跟 sink 推送**无关**。 | **无害，忽略**。第一次跑 `--action --platform web` 起了浏览器后自动消失。 |
| 浏览器里看到两个 `#1` 步骤 / 步骤数对不上 | 喂了**多条无 `--session-id`**（或跨了不同 session）的命令，多条时间线被并到一起。 | 多步统一带**同一个** `--session-id`。换 session 时 playground 会自动清空重来。 |
| 页面一直空白，无任何步骤 | 执行进程没带 `--playground-sink`，或 `--playground-url` 指错地址/端口。 | 给执行命令加 `--playground-sink`，确认 URL 与服务器端口一致。 |
| `Address already in use` / 端口被占 | `:7860` 已被占用（可能上次的服务器没退）。 | 换端口 `--playground-port 7861`（执行侧同步 `--playground-url http://127.0.0.1:7861`），或先杀掉占用进程。 |
| `[E013] Playground requires extra dependencies` | 没装 playground extra。 | `pip install screenforge[playground]`（含 `fastapi`/`uvicorn`/`websockets`）。 |
| 某步只有代码、没截图 | 该步截图抓取自身失败（degrade 容错）。 | 设计如此：**绝不**因截图失败中断执行；代码仍会推送。 |
| 「Open in IDE」按钮是灰的 / 显示「No editor found」 | playground 在 PATH 上没扫到任何已装编辑器的 CLI。 | 装一个编辑器的命令行入口（VS Code：命令面板 → "Shell Command: Install 'code' command"；Trae/Cursor 同理）。装好重启 playground。 |
| run 跑完了状态还显示绿色 `Live` | 旧行为。现在已改为按活动判定：~4s 无新步骤会自动转 `Idle`。 | 升级到含本次改动的版本即可；若仍长绿，确认你看的是最新 `index.html`。 |

---

## 边界（当前版本）

- **代码栏只读**：本轮不支持在 playground 里编辑代码回写（会与 codegen 自动落盘冲突）。
- **时间旅行是单会话内回溯**：点击帧/步可在**当前 run** 内跳转截图 + 高亮代码（见上）。跨会话的历史帧持久化回放（关页面后再翻旧 run）仍留作未来迭代。
- **移动端"实时"是步进式**：Android/iOS 每步截图约 0.5–2s（设备物理上限），前端如实呈现离散快照，不伪装连续视频。

更深入的架构与红线契约见 [capability-matrix_CN.md](./capability-matrix_CN.md#playground-实时镜像台live-mirror2026-06)。
