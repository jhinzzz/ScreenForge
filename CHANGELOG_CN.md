# Changelog

所有 ScreenForge 的重要变更都记录在本文件中。

**中文** | [English](./CHANGELOG.md)

## [未发布]

### Changed
- **内部清理，无行为变更。** 删除死代码（未被调用的 `session_exists`、
  `*_INLINE_ACTIONS` 重导出别名、一个无用的 doctor 辅助函数、从未使用的
  `register_handler` 扩展点、`OUTPUT_SCRIPT_FILE` / `CACHE_COMPRESSION` 配置项，
  以及一个未使用的测试 fixture）。将大模型的 markdown 代码块 JSON 解析在三处调用点
  收敛为单一的 `_strip_json_fences` 辅助函数，并删除永不可达的手写 `.env` 兜底解析器
  （`python-dotenv` 是硬依赖）。把 `UIExecutor.execute_and_record` 中两段仅 Web 的
  恢复逻辑（241 → ~150 行）提取为 `_recover_web_ref` / `_try_visual_fallback` 方法。

### Added
- **为缓存键指纹补充测试**（`compute_ui_hash` / `_extract_semantic_fingerprint` /
  `compute_instruction_hash`）——此前未覆盖、且一旦出错会导致「错误缓存命中、回放错误
  动作」的关键逻辑：确定性、忽略渲染顺序、对动态数据免疫、波动词黑名单、指令归一化。

### Fixed
- `AIBrain._call_llm` 现在会在解析失败时记录原始模型输出，使格式错误的响应可与网络错误
  区分，而非静默坍缩为空决策。

## [0.6.1] - 2026-06-12

### Docs
- **围绕楔子重新定位:「让你的 AI agent 跑测试，你留下那个 pytest 文件。」**
  重写 README 首屏(中英双语),功能列表改由 pytest 产物 + 自愈领衔，并把真机护城河
  （驱动真机 iOS/Android，不只是 Chrome）从从句提到正文。发布物料包(Show HN /
  Reddit / Twitter)也对齐到同一句楔子。
- **新增真实、已提交的示例画廊**(`docs/examples/`):每个 Web 示例是一份
  `*.workflow.yaml` 加上 ScreenForge 由它生成的 pytest(可回放、绿色)，并附
  `SELFHEAL.md` 记录一次真实自愈(置信度 0.90——故意改坏定位器，引擎修好，自愈后测试通过)。
- **全新 Live Mirror hero GIF**:通过 playground 驱动真实 workflow 录制(生成的
  pytest 在真实页面旁逐行长出)，替换过时的 `demo.gif`。
- **新增架构深挖文档**(`docs/architecture-deep-dive.md`):大脑/手脚分工、L1/L2
  语义缓存、自愈 AST 门禁、工程素养即特性。
- 无代码改动——本次发版用于以新 README 和资产刷新 PyPI 页面。

### Changed
- **MCP `ui_agent_execute` 现在返回动作后的实时观测**，与 shell `--action --json`
  对齐。此前通过 MCP（面向 Claude Desktop / Cursor / Cline 主推的接入方式）驱动
  ScreenForge 的 agent 只能拿到一份 run-report 摘要，必须再调用一次 `inspect_ui`
  才能看到结果——正是 `--json` 融合本要消除的双倍往返；且 did-you-mean 恢复信息
  （`candidates` / `recommended_next_step`）与真正的 `failure_diagnosis` 一概缺失。
  现在执行模式把 shell 写往 stdout 的同一份负载暂存到共享会话管理器上，由 MCP
  处理器折叠进响应（stdout 保持为干净的 JSON-RPC 通道）。覆盖 `action` 与
  `workflow`；workflow 只返回**一份**观测——成功取最后一步（`executed_steps`），
  失败取出错步（`failed_step_index` / `failed_step_name`），绝不逐步堆叠（token
  经济）。神圣的面向 LLM 的压缩器与 `--action` 的 `0/1` 退出码契约均不受影响。
- **MCP `--goal`（自主）失败现在带有真正的 `failure_diagnosis`。** 各执行模式把
  执行器的 `error_code` 透传进 `summary.json`（`run_reporter.finalize(error_code=…)`），
  于是处理器能为这条唯一不产出实时观测、无可折叠的执行路径构建出真实的
  `error_code` + `fix`。断言判定（`result: assertion_failed`）现在会丢弃 run-report
  中的 `recommended_next_step`，以免对一个合理失败的断言诱导重试。纯增量改动——
  `--goal` 路径的控制流与退出码均不变。

## [0.6.0] - 2026-06-09

### Added
- **大脑之眼视图 —— Playground 中的只读实时分层 DOM 树面板。**
  Playground 的每一步现在可选展示 **AI 大脑实际感知到的过滤元素集合，并按真实父/子结构重新挂载**
  —— 既非浏览器 DevTools 的原始 DOM，也非 LLM 接收的扁平 token 节省输出。
  此前缺口的根因在于 LLM 压缩器为节省 token 而刻意扁平化树结构，层级信息从未被保留在人类可检视之处。
  本次新增专用旁路采集，在不触碰压缩器的前提下捕获层级：
  - 新增 `playground/dom_capture.py` —— 复用压缩器的存活/过滤谓词，但以分层方式遍历，而非扁平化。
    Web：`page.evaluate` 分层遍历，每个节点产出 `ref` `@N` + bbox `x/y/w/h`。移动端（Android/iOS）：
    解析原始 `dump_hierarchy()` / `source()` XML 并保留嵌套（无 `ref`，无 bbox —— 如实反映，非伪造）。
    `compress_web_dom` / `compress_android_xml` 完全不受影响。
  - 采集以 `--playground-sink` 为门控（默认关 = 零额外成本；sink 关闭时连尝试都不做）。
    **红线不变**：树推送是独立的 fire-and-forget `POST /api/dom`，与步骤推送解耦，绝不 join 等待，
    因此绝不拖延或改变 `--action` 的 `0/1` 退出码。
  - 服务器以跨进程稳定的 `run_key`（而非每个 `--action` 进程各自不同的 `reporter.run_id`）为键将树
    落盘，LRU ≤ 5 个 run 目录。SSE `step` 事件仅携带 `has_dom_tree` 布尔值——SSE 上零树字节。
    前端通过 `GET /api/run/{run_id}/step/{step_index}/dom` 按需拉取，仅在抽屉打开且该步骤处于
    视图时触发（大多数用户从不打开，因此 SSE 零树流量）。
  - 界面：右侧边缘可折叠抽屉（可固定；快捷键 `B`）；当前目标行 ember 高亮 +（Web）截图上 ember bbox
    叠加层；鼠标悬停任意节点（Web）→ 蓝色 bbox；完整 ARIA 键盘导航（↑/↓/←/→/Home/End，`/` 聚焦搜索）；
    点击 `@N` 徽章或按 Enter 复制定位器；`+N −N ~N` 逐步差异徽章；键控协调器逐步就地更新树，保留展开/滚动状态。
  - **移动端诚实降级**：Android/iOS 无 `ref` 徽章、无 bbox 叠加层（明确缺失，非隐藏）；悬停轨道变为
    琥珀色；一次性可关闭提示。移动端树是真正分层的 —— 相较于扁平 LLM 输出是真实改进。
    反向空间查找与 SSE 差异流推送留作未来迭代。

## [0.5.0] - 2026-06-09

### Added
- **Playground 实时镜像台（Live Mirror）—— 边写用例边看页面**。`screenforge --playground`
  起的常驻可视化进程现在能实时显示**正在生成的 pytest 代码**与**被操作的页面**，二者并排联动。
  根因不是缺数据，是"没把数据接出去那一根线"：每步 `result["code_lines"]` 与三端统一的
  `take_screenshot()` 早已现成，playground 的 `POST /api/*` 入口却是零调用的死代码。本次接上这根线：
  - 新增 `cli/playground_sink.py`——一个 **fire-and-forget 旁路观察者**，挂在 `save_to_disk` 之后，
    每步把代码 + 截图 POST 给常驻 playground。daemon 线程推送 + 分离超时 `(0.2, 0.25)`，playground
    没开/拒连/卡死一律静默 skip。**红线**：绝不因推送失败改变 `--action` 的 `0/1` 退出码或耗时
    （`--playground-sink` 默认关 = 零开销，连截图都不抓）。
  - 三个执行入口同构接入（共用 `build_step_event` 单一构造点 + `maybe_push_step` 单一守卫入口）：
    `--action` 单步、`workflow` YAML 多步、`main.py` 人类录制。
  - playground 新增 `POST /api/step`（按 `run_id` 命名空间累积**步骤元数据**，`OrderedDict` LRU
    ≤20 run × ≤500 步；base64 帧只进实时单槽 + SSE，**不进**累积日志——内存有界）+ 前端只读代码栏
    （Prism 语法高亮 + 最新行 ember 高亮 + 平滑滚底）+ 三区布局（截图 ｜ 代码近等宽并列 ｜ 动作历史）。
  - ⭐ **"时间旅行"（单会话内回溯）**：点击底部 filmstrip 任意帧 / 历史任意步，左侧大截图跳回该步画面、
    右侧代码栏高亮对应行（截图/代码/历史三处联动）。数据按 `step_index` 持久累积 +
    `GET /api/run/{run_id}/steps` 只读端点。跨会话历史帧持久化回放留作未来迭代。
  - **明亮 / 黑暗主题切换**：顶栏 ☀/🌙 按钮在锻造台黑暗主题与「冷却的钢·蓝图纸」明亮主题间切换；
    选择记入 `localStorage` 且**首屏预设无闪烁**（`<head>` 内同步设定 `data-theme`），未选过则跟随系统
    `prefers-color-scheme`。明亮主题所有文字/强调色 + 代码高亮均按 WCAG AA（≥4.5:1）重新取色；
    被测页面截图不受主题影响（始终按其本来面貌）。
  - 新增 CLI 旗标 `--playground-sink`（opt-in）/ `--playground-url`。依赖 `screenforge[playground]` extra，
    零新增基础依赖（`requests` 早已在 `requirements.txt`）。
  - **一键在 IDE 中打开生成的用例**：顶栏「Open in <IDE>」按钮**自动检测** PATH 上已装的编辑器
    （VS Code / Trae / Cursor / Windsurf / Zed / Sublime / IntelliJ / PyCharm / Vim / Neovim），下拉可切换、
    选择记入 `localStorage`，`⌘E`/`Ctrl-E` 快捷键。新增 `GET /api/editors`（仅 PATH 探测）+
    `POST /api/open`（loopback-only，固定 argv 调用——文件路径无法注入命令）。一个都没检测到则禁用并提示。
  - **诚实的连接状态**：状态指示按**活动**判定而非 SSE 连接——run 安静 ~4s 自动从 `Live` 降为 `Idle`
    （琥珀色，截图角标同步变 `IDLE`），新步骤到达再转回 `Live`；SSE 真断才显示 `Disconnected`。
    修复"run 跑完仍长亮 Live"的误导。
  - **诚实边界**：移动端"实时"是步进式刷新（每步 0.5–2s，设备物理上限），前端如实呈现离散快照，不假装连续流。

### Fixed
- **「Open in IDE」按钮在无运行时点击无反应** — 根因有二：(1) 按钮在"还没跑测试 / 无文件可开"时虽已
  `disabled`，CSS 却仍显示为完全可点（不透明、手型光标）→ 看着能点、点了没反应；(2) 顶栏 `run`/`file`
  位上是**硬编码的假文件名** `test_auto_20260608_142530.py`，让人误以为已加载真文件。修复：补 `.btn-vscode:disabled`
  置灰 + `not-allowed` 光标；三处占位符改为诚实的 `—`；从 ▾ 菜单在无文件时选编辑器会**给出可见提示**
  （"No file yet — run a test first"）而非静默。
- **底部"Coming soon"是过期文案** — 点帧回溯（截图跳转 + 代码高亮）其实**早已实现**且可用。删除
  "Coming soon" / "seed" / "visual only" 等误导文案，改为如实描述（"Tip: 点帧回溯…"）。
- **无设备连接时空状态文字颜色不统一** — 代码栏空态注释曾用一处独有的绿 `#7c8a72`，与截图/历史空态的
  中性灰不一致。根因是硬编码颜色绕过了 token 系统；本次把约 25 处图形外壳硬编码色统一收敛到设计 token
  （这也正是明亮主题得以成立的同一处根因修复），空态文字归一。

## [0.4.1] - 2026-06-08

### Fixed
- **PyPI 项目页是空白的** — `pyproject.toml` 没有声明 `readme`，因此构建出的发行包带着空的
  long-description，PyPI 上什么都不显示（既无 README，也无概览）。已补上 `readme = "README.md"`。
  由于已发布的版本不可变更，0.4.0 的页面将一直空白；本次从 0.4.1 起补齐页面内容。
- **README 链接/图片在 PyPI 上失效** — README 用的是仓库相对路径
  （`docs/assets/demo.gif`、`docs/*.md`、`LICENSE`……），这些只能在 GitHub 上解析；
  渲染到 PyPI 上会 404 / 显示破图的 hero 图。已将它们重写为绝对 GitHub URL
  （图片用 `raw.githubusercontent.com/.../main/...`，文件用 `github.com/.../blob/main/...`，
  workflows 目录用 `.../tree/main/...`）—— 在 GitHub 上渲染不变，在 PyPI 上链接可用。

### Packaging
- 发布流水线的 `pypa/gh-action-pypi-publish` 已从 `v1.11.0` 升到 `v1.14.0`（在 0.4.0 发布期间），
  这样它内置的 twine 才能解析现代 setuptools 产出的 `Metadata-Version: 2.4` wheel；旧的 pin
  会以 `InvalidDistribution: missing field Name` 拒绝一个本应合法的 wheel。

## [0.4.0] - 2026-06-08

### Fixed
- **Web DOM 压缩器看不到 shadow DOM 与 iframe** — LLM 的"眼睛"（`compress_web_dom`）用了一个扁平的
  `querySelectorAll('*')`，它既不穿透 shadow root 也不下钻进 iframe 文档，于是整个 Web-Component
  应用和嵌入的（支付/登录）frame 都是不可见的：Playwright 能点这些元素，但模型从不知道它们存在。
  压缩器现在会递归遍历 open shadow DOM 与同源/`srcdoc` iframe，把 iframe 子元素的 bounding box
  偏移回顶层文档坐标（含 iframe 自身的边框 + 内边距内缩，使 ref/坐标点击落点正确）。closed shadow
  root 与跨域 iframe 仍不可穿透（浏览器安全边界），会被诚实跳过。
- `disabled` / `aria-disabled` 控件曾被上报为 `clickable:true`，于是模型会去点它们并卡在动作超时上。
  它们现在仍被收录（便于存在/禁用断言），但标为 `clickable:false` 并带 `disabled:true` 标记。
- `<fieldset disabled>` 未传播给其后代控件 — 此前只认元素自身的 `disabled` 属性，因此被禁用 fieldset
  内部的控件被上报为 `clickable:true`，模型会卡在它们上面。"是否真禁用"现在通过 `:disabled` CSS 伪类
  判定（浏览器权威实现），一次性覆盖 fieldset 传播、首个 `<legend>` 豁免与嵌套。
- `[inert]` 子树内的控件（标准的模态背景模式——开着的 `<dialog>` 背后的一切）会吞掉点击，却被产出为
  `clickable:true`，于是模型会去点模态背后的死控件。它们现在为 `clickable:false`，且 inert 状态会
  **跨 shadow / 同源 iframe 边界继承**（像坐标偏移一样穿过压缩器的递归）。它作为独立的 `inert:true`
  字段暴露，**不**折叠进 `disabled`（二者是不同概念——被遮挡 vs 本身关闭——这样 `assert disabled`
  才不会误判通过）。
- **Android 压缩器忽略了 `enabled`** — 一个 `clickable="true" enabled="false"` 的控件（置灰按钮、
  空 SIM 卡槽）被上报为 `clickable:true`，模型会去点这个死控件并卡住（正是 Web 压缩器已修过的同一盲点）。
  Android 现在对 `enabled="false"` 抑制 `clickable` 并产出 `disabled:true`，仍收录该控件使其存在/禁用态
  保持可断言。数字噪声文本过滤器的顺序也被调整，使一个带短数字文本的禁用控件（例如一个禁用的 "+5"
  步进器）不会被静默丢弃。
- **Android 列表行无法定位** — 主导的列表形态（RecyclerView / Preference）是一个*可点击容器*
  （LinearLayout/ViewGroup，无自身标签），其文本位于一个*不可点击的子* `TextView` 里。扁平压缩器把
  一行拆成一个 headless 可点击块（无 text/desc/id → 无法定位）外加一个标为 `clickable:false` 的文本
  节点，于是**没有任何元素同时既可点击又带标签**：LLM 大脑被告知唯一带标签的东西（"应用"）不可点
  （P4 契约）而回避它，外部 agent 则看到一堆无法定位的可点击块。真机实测（Settings 主屏）：18 个可点击
  元素中 16 个无法定位。压缩器现在把每行的标题（或首个可存活的）标签子节点提升为 `clickable:true`——
  一个带真实 id 的真实节点；点击它会冒泡到可点击祖先（真机验证）——并抑制如今冗余的空容器。
  **零坐标。诚实边界**：禁用行不提升；纯图标容器（无标签）或其唯一标签会被 id/desc 过滤器丢弃的容器，
  保持为诚实的 headless 可点击块而非凭空消失；内层卡片的标签绝不被外层 wrapper 偷走。真机前后对比：
  18 可点击 / 0 带标签可点击 / 16 无法定位 → 20 / 19 / 0。
- **iOS 列表行每行被产出 2-3 次** — WDA 在每个列表行的交互控件内嵌套一个携带标签的 `StaticText`，
  于是扁平压缩器每行把同一标签产出多次：一个 `Button`/`Cell` 加一个无意义的 `StaticText` 孪生体
  （一个 Switch 行会产出 `Cell` + `StaticText` + `Switch`，三者标签完全相同）。在真实模拟器上实测
  （iOS 18.3 / 设置）：键盘页 44 个元素里 14 个（32%）是纯 StaticText 影子，设置主屏约一半的行如此。
  这种膨胀浪费 token，并让 `d(label='通用')` 产生歧义（它同时命中点击目标与其无意义文本孪生体）。
  压缩器现在把每行折叠为按标签唯一的那个可操作控件（优先级 `Switch > Button > Cell`），丢弃 StaticText
  影子。**诚实边界（均经真机验证）**：该抑制感知可见性（绝不让一个不可见的高优先级孪生体抹掉一个可见
  的行——真实在屏元素绝不能消失）；仅精确同标签匹配（不同的副标题，例如 Apple 账户行的标题/副标题，
  保留）；作用域限定在行内，不跨嵌套 `Cell` 边界（内层行的独立标签绝不被其外层 wrapper 吞掉）；无交互
  孪生体的独立文案（例如 `关`/Off）保留；`Switch` 保留其开/关 `value`。真机前后对比：设置主屏 31 → 20
  个元素，键盘页 44 → 21，且每个可定位行都保留。
- **`--action --json` 失败曾是一条死字符串**（`{"result":"engine_error",
  "error":"Action failed: click:Login"}`），既无页面也无引导，而真正有用的 `[E0xx] Fix:` 诊断只活在
  stderr 上（agent 示例通过 `2>/dev/null` 丢弃了它）。engine-error 失败现在返回一个结构化、可恢复的
  payload：`error_code` + `fix`（来自一张与 stderr 共享的单一来源表，故二者不会漂移）、did-you-mean
  `candidates`（`difflib` 对页面元素 text/desc/name 做相似度，诚实的 0.55 阈值——低于它则返回空而非
  编造一个匹配）、`recommended_next_step`，以及当前的 `ui_tree`（故无需第二次 `inspect_ui`）。断言失败
  仍是一个裸裁决（无 candidates / 无重试诱饵——裁决不是定位问题）。

### Added
- 更丰富的 Web 交互动作（弥补"无法自动化表单 / 视口外元素"的缺口）：`scroll_into_view`
  （元素定向，而非盲目 swipe）、`select`（原生 `<select>`）、`upload`（文件 input）、`double_click`、
  `right_click`（上下文菜单）和 `drag`（源 = locator，目标 = `extra_value`，css/text 自动识别）。
  Web 优先——每个都映射到一个稳定的 Playwright API；它们在移动端诚实失败，而非产出一个脆弱的坐标步骤。
  capabilities payload 现在会公布 `web_only_actions`。
- 面向真实测试生成的更丰富断言词汇：`assert_text_contains`（子串）、`assert_not_exist`（元素消失/隐藏）、
  `assert_value`（表单字段值）和 `assert_url`（Web 页面 URL 含子串，一个全局的免 locator 动作）。
  外加 `wait_for`——一个显式的同步动作（`extra_value` = `visible`/`hidden`）以替代盲目等待。
- 生成的 Web 测试现在使用 Playwright 自动重试的 `expect()` 断言（`to_have_text` / `to_contain_text` /
  `to_be_hidden` / `to_have_value` / `to_have_url`）而非读一次就比较——消除了在值稳定之前就读取它的
  异步 UI flaky。
- **重复同名控件消歧。** N 个列表行各带一个完全相同的 "Delete" 按钮，会压缩成 N 个无法区分的元素，
  于是 codegen 只能产出 `get_by_text('Delete').first`——无论模型本意指哪一个，都静默地总是点第一行。
  压缩器现在只对*有歧义*的控件（其 role+name 与某个兄弟冲突）补上 `scope`（所在行的区分性叶子文本）
  与 `dup_index`，在无歧义页面上零额外 token。codegen 产出一个作用域定位器
  `get_by_text(scope, exact=True).locator('..').<inner>`——**不带 `.first`**，strict-mode 会捕获非唯一。
  当一行无法消歧时，产出一个诚实的 `pytest.skip` 而非一个撒谎的 `.first`/`.nth`。
- `current_url` 现在被纳入 `--action --json` 成功 payload 与 `inspect_ui` payload（仅 Web；移动端诚实
  返回 `""`）——agent 真正需要的那一个读原语，无需一个单独的查询操作。
- MCP `execute` 失败会携带一个最小的 `failure_diagnosis`（`error_code` + `fix`，来自同一张单一来源表；
  无 candidates，因为 run-report 路径没有 live 元素树）。

### Changed
- `goto` 不再产出一个硬编码的 `wait_for_timeout(2000)`；它通过 `goto(wait_until='load')` 同步，并依赖
  下一个动作 locator 的 auto-wait（Playwright 推荐的就绪策略）。`press`/`swipe` 的生成代码同样去掉了
  其固定 sleep。
- 生成的测试文件不再携带一个未使用的 `import pytest`（此前在 ruff 下是 F401-dirty）。
- 生成的测试现在以用户的 goal/action/workflow 命名（`def test_<slug>`），意图写进 docstring +
  `allure.story`，而非一个不透明的 `test_auto_generated_case`。Unicode goal（例如中文）会被保留；
  纯符号/空白标签会安全回退。
- Web codegen 绝不把一个像素级 `mouse.click(x, y)` 烤进一个持久化的测试。当一个 `@N` ref 无法按 id/text
  解析时，运行时会从元素剩余的属性中恢复一个稳定的 locator（id > name > role+name > label > placeholder
  > text），对 live 页面校验它，并重新驱动该动作自己的 handler（input 仍是 input）。当不存在持久的
  locator 时，产出一个诚实的 `pytest.skip`（对于没有 DOM 节点的纯 VLM 视觉 fallback 亦然），而非一个
  会悄悄腐烂的坐标。`allure.step` 标签现在显示已解析的目标，而非一个裸的 `@N`。
- iOS 压缩器把它的 disabled 键从旧的 `enabled:false` 统一到 `disabled:true`，与 Android、Web 一致——
  单个 LLM 大脑现在跨每个平台只看到一种"无法交互"词汇。

### Docs
- 记录了（并以一个 live 测试钉死）虚拟滚动列表（react-window）只渲染视口切片——压缩器诚实地报告 DOM
  里有什么，一个 `scroll` + 重新 inspect 会浮现下一个切片。这不是 bug；也不强制渲染（token 爆炸才是
  回归）。
- `agent_guide.md` 展示了增强后的失败 payload，并指出在 `--json` 下 `error_code` + `fix` 随 stdout
  返回，因此丢弃 stderr（`2>/dev/null`）对机器使用是安全的，但在调试时会隐藏人类可读的 fix 提示。
- `capability-matrix.md` 记录了失败反馈工效、did-you-mean 诚实边界、`current_url` 以及跨平台的
  `disabled:true` schema。

## [0.3.0] - 2026-06-04

### Changed (BREAKING)
- `assert_exist` / `assert_text_equals` 现在报告真实的通过/失败。断言失败会在 `--json` 输出中携带
  `"result": "assertion_failed", "assertion_failed": true`。

### Fixed
- 移除了 Web 录制崩溃；`start_record`/`stop_record` 现在是空操作，返回 `""`（不支持 Web 录制）。
  移除了死掉的 `record_video_dir` 分支与 `_find_chromium_path`。
- 修复了文档与 `doctor` 修复建议中的安装命令；逐平台的修复建议现在指向可编辑的 extras
  （`pip install -e ".[android]"` / `".[ios]"` / `pip install -e .`）。
- 修复了 `agent_cli.py` shim 重构带来的 7 个失败测试；测试现在针对
  `cli.tool_protocol_handlers` / `cli.shared` / `cli.dispatch`。
- 让 ML 栈变为可选：`sentence_transformers` 现在在 `EmbeddingModelLoader.load()` 中惰性导入。
  把 torch/transformers/sentence-transformers/scikit-learn 移出了核心 `requirements.txt`。
- 修复了 MCP web ref 缓存泄漏：`@N`→element 缓存现在活在 `UIExecutor` 实例上而非进程全局，通过
  `_SharedAdapterManager` 做到每平台一个 executor。Ref 解析通过一个显式的 `resolve_ref` callable
  穿线。
- `not_found` 在 `--goal` 模式下不再触发熔断器。
- 删除了死掉的 `common/prompts.py`；移除了死掉的 `_find_chromium_path`。
- `config.validate_config` 现在对 `AUTO_HEAL_MIN_CONFIDENCE`（0-1）与 `AUTO_HEAL_TRIGGER_THRESHOLD`
  （>= 1）做边界检查。
- `--web-stop` 现在能可靠地杀掉浏览器：reaper 在宽限期后升级到 `SIGKILL`，且 `_is_process_alive`
  把一个 `Z`/defunct 僵尸进程当作非存活。
- 修复了 iOS `swipe` 崩溃：现在使用 facebook-wda 的 `swipe_up/down/left/right()` 而非仅限 Android 的
  `swipe_ext`。
- 修复了 Android `resourceId` 定位器：XML 压缩器现在产出完整的 resource-id（+ 可选的 `id_short` 提示）。
- 修复了 Android 对一个不存在元素的 assert/action 错误地报告成功：`execute_and_record` 现在以
  `element is not None` 为门控。

### Added
- `test_public_surface.py` —— 钉住 CLI 包的公开符号。
- `--capabilities` 中逐平台的定位器矩阵（`locators` / `features`）；ref/bbox/截图标注/视觉 fallback
  被报告为仅 Web 端可用。
- `--web-stop` —— 终止常驻的 Chromium（CDP 端口 9333）；幂等。
- `doctor` web 预检：读取 `report/web_session.json` 并把残留的常驻 Chromium 浮现为一条建议性 NOTE
  （绝不让 `--doctor` 失败）。
- 针对真实硬件的 live 冒烟测试，opt-in 且默认跳过：
  - `test_web_smoke_live.py`（`RUN_LIVE_WEB_SMOKE=1`）
  - `test_android_smoke_live.py`（`RUN_LIVE_ANDROID_SMOKE=1`）
  - `test_ios_smoke_live.py`（`RUN_LIVE_IOS_SMOKE=1`）

### Docs
- 更正了 `capability-matrix.md` / `agent_guide.md`：ref/bbox/视觉 fallback 仅 Web 端可用。
- 记录了 `--json` 断言失败契约与常驻浏览器生命周期。

## [0.2.1] - 2026-05-25

### Added
- **iOS 适配器重写**：WDA 健康检查、会话重连、`xcrun simctl` 屏幕录制、自动检测已启动模拟器的 UDID
- **Android 适配器重写**：跨 CLI 调用的会话持久化、断连时自动重连、结构化错误码（E050–E055）
- **会话模式**（`--session-id` / `--session-end`）：把多个 `--action` 调用归入一个测试文件与一段录制；
  基于 PID 的跨进程录制生命周期
- **`--json` 动作输出**：stdout 上的单行 JSON，带 `ok`、`action`、`ui_tree`、`element_count`——使动作 +
  inspect 一次调用即可
- **iOS UI 树压缩器**（`utils/utils_ios.py`）：过滤键盘按键、单数字噪声、滚动条，去重；把 123 个元素
  降到约 49 个
- **iOS executor 支持**：定位器映射（text→label，resourceId→name）与按键处理（带键盘按钮 fallback）
- **设备定向旗标**：`--device-url`（WDA URL 覆盖）、`--device-serial`（Android serial / iOS UDID 覆盖）
- **移动端配置指南**（`docs/mobile-setup.md`）：Android 与 iOS 设备连接说明

### Fixed
- `take_screenshot()` 重连中的无限递归（两个适配器）——现在用 `_retry` 标记守卫
- `--json` 模式下的 Reporter 事件噪声——action 模式通过 `json_output=False` kwarg 抑制 reporter stdout
- iOS 滚动条过滤器现在同时处理中文（"滚动条"）与英文（"scroll bar"）locale
- `cli/shared.py` 不再从 `main.py` 导入——内联了 `get_initial_header`、`save_to_disk`、`launch_app`

## [0.2.0] - 2026-05-25

### Added
- **Playground 实时查看器**：`screenforge --playground` 在 localhost:7860 启动一个 web UI，通过 SSE
  显示实时浏览器截图与动作历史
- **CDP Screencast 集成**：Playground 自动连接 Chrome DevTools Protocol 并流式传输 live 帧——无需手动
  推送截图
- **GitHub Action**：`uses: jhinzzz/ScreenForge@v1` 把 ScreenForge 加进任何 CI 流水线，自动安装
  Playwright 并上传 Allure 产物
- **`screenforge --init` 向导**：交互式首次配置（平台选择、LLM 配置、依赖检查）
- **MCP 配置指南**（`docs/mcp-setup.md`）：为 Claude Desktop、Cursor、Cline 和 Claude Code 提供 3 分钟
  配置
- **Launch kit**（`docs/launch-kit.md`）：面向 Show HN、Reddit 和 Twitter 的即贴模板
- **英文 workflow 示例**：`docs/workflows/` 下的 `web_login.yaml`、`web_search.yaml`、
  `web_form_submit.yaml`
- **Rich 进度 spinner**：AI 调用与动作执行在终端中显示动画状态（在 tool/MCP 模式下自动禁用）
- **Rich doctor 表格**：`--doctor` 在交互式终端中显示彩色编码的通过/失败表格
- **Demo GIF**：`scripts/demo.tape` 通过 VHS 生成 README demo
- **README badge**：面向使用 ScreenForge 生成测试的项目的 shields.io badge
- **可选的 `[playground]` extra**：`pip install screenforge[playground]`（fastapi + uvicorn +
  websockets）

### Changed
- **`.env_template`**：默认使用 OpenAI 端点（`api.openai.com/v1`、`gpt-4o`）而非特定厂商的中国端点
- **错误消息列出有效选项**：无效的 `--action` 现在会显示所有支持的动作
- **Doctor 使用相对路径**：修复建议文档引用不再泄漏绝对文件系统路径

### Fixed
- `scripts/demo.tape` 激活 venv 并运行 `pip install -e .` 以确保 `screenforge` CLI 可用

## [0.1.1] - 2026-05-25

### Security
- **代码生成注入加固**：`_escape_locator_value` 现在除引号/反斜杠外还转义 `\n`、`\r`、`\t`、`\0`——
  防止通过精心构造的 locator 值注入任意 Python
- **发布流水线 pin 死**：`pypa/gh-action-pypi-publish` pin 到 SHA（`fb13cb30...`）而非浮动的
  `release/v1` tag——缓解供应链攻击
- **tag-版本一致性检查**：发布 workflow 现在在发布前校验 git tag 与 `cli/_version.py` 是否匹配

### Added
- CLI 核心路径的单元测试：runtime_modes、capabilities、shorthand、parser、run_resume、run_reporter、
  dispatch（32 → 180 个测试）
- dispatch 测试中类型安全的 `SimpleNamespace` fixture（替代 MagicMock）
- AI 大脑与缓存管理器的集成测试
- 发布流水线中的预发布测试步骤
- Pre-commit hooks：ruff（lint+format）+ mypy
- `screenforge --demo` 简写命令
- `screenforge inspect` / `screenforge click "Login"` 简写 CLI 预处理器
- `.github/workflows/ci.yml`，在 push/PR 时自动运行 pytest

### Changed
- 完整的英文优先翻译：所有面向开发者的日志、CLI 输出、预检提示、MCP 错误消息
- 收窄了失败分类 token 以防止误判分类
- `MCP_SERVER_VERSION` 现在源自 `cli/_version.py`（此前硬编码，可能漂移）
- `cli/dispatch.py` 使用 `json.dumps` 构造 JSON（此前是 f-string，脆弱）
- 从 shorthand 模块移除了死代码 `inject_inspect_stdin()`

### Fixed
- `--doctor` 输出仍是中文——所有提示已翻译为英文
- `--capabilities` 泄漏绝对文件系统路径——现在使用相对路径

## [0.1.0] - 2026-05-22

### Added
- 英文优先的 README，含 Quick Start、对比表格与架构图
- `screenforge --demo` 命令，提供零配置的首次体验（无需 API key）
- `screenforge --version` 旗标
- 三层错误消息，含错误码、解释与修复建议
- `CHANGELOG.md`，用于版本透明

### Changed
- 默认的 `OPENAI_BASE_URL` 现在指向 `https://api.openai.com/v1`（此前是特定厂商的）
- 默认的 `MODEL_NAME` 现在是 `gpt-4o`（此前是特定厂商的）
- `VISION_MODEL_NAME` 默认取 `MODEL_NAME` 以实现优雅回退
- `validate_config()` 现在使用 `loguru` 而非 `print()`（修复 Agent 集成中的 stdout 污染）
- 所有面向用户的错误消息转为英文，带结构化错误码
- `docs/agent_guide.md` 完整翻译为英文

### Fixed
- 配置校验失败时 Agent 集成收到乱码 stdout（print → log.error）
- 熔断器消息现在包含诊断上下文与恢复建议

## [0.0.2] - 2026-03-30

### Changed
- 从 `CacheManager` 中抽出 `EmbeddingModelLoader` 以更好地分离关注点
- `agent_cli.py` 中的平台目录自动创建
- `main.py` 中的异常处理——不再静默吞掉错误

## [0.0.1] - 2026-03-01

### Added
- 初始发布，含 Agentic 与 Interactive 双模式
- L1/L2 混合语义缓存系统
- 跨平台适配器（Android/iOS/Web）
- 带置信度评分与 AST 校验的自愈引擎
- 带 5 个 tools 的 MCP server
- 结构化 run 产物（summary.json、steps.jsonl、artifacts.json）
