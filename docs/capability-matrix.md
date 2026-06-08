# ScreenForge Capability Matrix

本文档描述当前仓库中已经落地并验证过的能力边界。若上层 Agent 需要机器可读版本，请直接执行 `python agent_cli.py --capabilities`；若需要机器可读执行入口，可使用 `--tool-request`、`--tool-stdin` 或 `--mcp-server`。

## 平台支持总览

| 平台 | 连接能力 | 页面结构采集 | 截图 | 物理动作执行 | 视频/状态产物 | 当前成熟度 |
|---|---|---|---|---|---|---|
| Android | `uiautomator2` | XML 压缩 | 支持 | 支持 | `scrcpy` 录像 | 高 |
| iOS | `facebook-wda` | 暂未实现结构压缩 | 支持 | 基础支持 | 暂无原生录像 | 低 |
| Web | Playwright + CDP | DOM 压缩（穿透 open shadow DOM + 同源 iframe） | 支持 | 支持 | Playwright 视频 + storage state | 中 |

> ℹ️ **Web DOM 压缩器穿透能力（2026-06）**：`compress_web_dom` 递归遍历 open shadow
> DOM 与同源/`srcdoc` iframe，iframe 内元素的 bbox 会按 iframe 的位置 + 边框 + 内边距
> 偏移回顶层坐标，保证 ref/坐标点击不错位。**不可交互判定**（均仍收录便于断言，但标
> `clickable:false`，避免 LLM 去点死元素卡超时）：
> - `disabled` / `aria-disabled` 控件 → `disabled:true`；用 `:disabled` 伪类判定，
>   故 `<fieldset disabled>` 传播给后代控件（含首个 `<legend>` 内豁免、嵌套继承）也覆盖。
> - `inert` 子树（开 `<dialog>` 时背景标 inert 的标准模式）→ 独立的 `inert:true` 字段
>   （**不**当作 `disabled`，二者语义不同），且 inert 状态会跨 shadow / 同源 iframe 边界继承。
>
> **不可穿透**：closed shadow root、跨域 iframe（浏览器安全边界，静默跳过）。
>
> **虚拟滚动列表（react-window / 虚拟化表格）只见视口**：此类组件只把视口内的行渲染进 DOM，
> 视口外的行根本不存在，压缩器看不到也不应编造。这是固有限制而非缺陷——用 workflow B 的
> `action scroll → 重新 inspect_ui` 循环即可拿到新行（已有 live 测试钉死：滚动后 re-inspect
> 能取到新切片、旧行不再上报）。不要试图强制渲染全部行（token 会爆）。
>
> **重复同名控件消歧（`scope` / `dup_index`）**：当多个可点击控件 (role, name) 相同
> （如列表每行一个 "Delete"），压缩器对这些**有歧义**的元素补两字段：`scope`（所在行的
> 唯一标识叶子文本，如 "Bob Jones"）与 `dup_index`（DOM 序）。非歧义元素不补（0 额外 token）。
> codegen 据 `scope` 生成作用域定位器 `get_by_text('Bob Jones', exact=True).locator('..').get_by_role('button', name='Delete')`
> —— **不带 `.first`**，strict-mode 兜底：定位器不唯一就报错，绝不静默点第一行。`scope` 经
> 组内唯一性校验（被多行共用或为空则不采纳）+ exact 精确匹配（避免 "Bob" 命中 "Bob Jones"）。
> 实在消歧不了（同名行标识相同 / 超长 / 无行标识）→ 只留 `dup_index`，codegen 走诚实
> `pytest.skip`，绝不写 `.first`（点第一行的谎）或 `.nth(k)`（位置坐标式脆弱）。

> ℹ️ **禁用控件统一 schema（三端一致，2026-06）**：被禁用 / 不可交互的控件在三端压缩器都用
> **同一个 `disabled: true` 字段**上报（Web `:disabled`/`aria-disabled`，Android `enabled="false"`，
> iOS WDA `enabled="false"`），且都**仍收录**控件（便于断言存在/禁用态）但不标 `clickable`，避免
> LLM 去点死控件卡超时。早期 iOS 曾用相反的 `enabled:false` 键，已统一到 `disabled:true`，让单个
> LLM 大脑跨端只需认一种「不可交互」词汇。Android 真机验证：数据漫游页空 SIM 卡槽（天然禁用）已正确
> 标 `disabled` 且不可点。

> ℹ️ **Android 列表行标签提升（RecyclerView / Preference，2026-06）**：Android 列表行的主导形态是
> **可点击容器**（LinearLayout/ViewGroup，无自身 text/desc）+ 标签在**不可点击的子 TextView** 里。
> 扁平压缩会把一行拆成两个元素——一个无法定位的 headless 可点击块（无 text/desc/id）+ 一个标
> `clickable:false` 的文本节点，导致**没有任何元素「既可点击又带标签」**：LLM 大脑被 P4 契约告知唯一
> 有标签的东西（如「应用」）不可点而回避它；外部 agent 看到一堆无法定位的可点击块。真机实测（Settings
> 主屏）：18 个可点击元素中 16 个无法定位。压缩器现在把每行的**标题**（或首个可存活）标签子节点提升为
> `clickable:true`——真实节点、真实 id，点击它会冒泡到可点击祖先（真机验证）——并抑制冗余的空容器。
> **零坐标。诚实边界**：禁用行不提升；纯图标容器（无标签）或其唯一标签会被 id/desc 过滤器丢弃的容器，
> 保持为诚实的 headless 可点击块而**非凭空消失**；嵌套卡片各自提升自己的标签，外层 wrapper 不偷内层标签
> （围着已提升内层卡片的外层 wrapper 保持为无定位符的可点击块，是已知诚实限制）。真机前后对比：
> 18 可点击 / 0 带标签可点击 / 16 无法定位 → 20 / 19 / 0。

## 元素定位能力

> ⚠️ **ref / bbox / 截图标注 / 视觉 fallback 仅 Web 端可用。** 移动端的 UI 树压缩器
> (`utils_xml.py` / `utils_ios.py`) 不产出 ref 编号或 bbox 坐标，视觉 fallback 在
> `executor.py` 也只对 `platform == "web"` 生效。机器可读版本见
> `python agent_cli.py --capabilities` 的 `locators` / `features` 字段。

| 能力 | Android | iOS | Web | 说明 |
|---|---|---|---|---|
| ref 编号 (@N) | 不支持 | 不支持 | 支持 | 仅 `compress_web_dom` 为每个 Web 元素分配 ref；移动端不产出 |
| bbox 坐标 (x,y,w,h) | 不支持 | 不支持 | 支持 | 仅 Web 元素附带边界框坐标，用于坐标点击或视觉比对 |
| 截图标注 | 不支持 | 不支持 | 支持 | `--vision` 模式下仅 Web 自动生成带 ref 标注的截图 |
| 视觉 fallback (VLM) | 不支持 | 不支持 | 支持 | 仅 Web：DOM 无法定位时调用 VLM 从截图解析坐标（`executor.py` 内 gate 在 web） |
| css 选择器 | 不适用 | 不适用 | 支持 | Web 端首选定位方式 |
| resourceId | 支持 | 映射到 name | 不适用 | Android 原生 resource-id；iOS 映射到 `name` |
| text / description | 支持 | 支持（映射到 label） | 支持 | 跨平台通用，按可见文本或无障碍描述定位 |

## CLI 模式支持

| 模式 | Android | iOS | Web | 说明 |
|---|---|---|---|---|
| `run` | 支持 | 基础支持 | 支持 | 默认自主探索并生成 pytest 脚本 |
| `action` | 支持 | 基础支持 | 支持 | 单步即时动作执行 |
| `workflow` | 支持 | 基础支持 | 支持 | 半结构化 YAML 工作流执行 |
| `doctor` | 支持 | 支持 | 支持 | 只检查环境与前置条件 |
| `plan-only` | 支持 | 基础支持 | 支持 | 生成执行前计划，不执行物理动作 |
| `dry-run` | 支持 | 基础支持 | 支持 | 走决策链输出 would-execute 结果，不执行物理动作 |
| `resume-run-id` | 支持 | 支持 | 支持 | 从已有 run report 恢复最小上下文 |
| `mcp-server` | 支持 | 支持 | 支持 | 以 stdio 方式暴露最小 MCP tools 接口 |

## 人类入口与 Agent 入口分工

| 入口 | 面向对象 | 是否允许自然语言直接驱动 | 是否允许内部第三方 LLM 推理 | 推荐用途 |
|---|---|---|---|---|
| `main.py` | 人类 | 允许 | 允许 | 自然语言调试、交互式录制 |
| `agent_cli.py --action/--workflow` | Agent / 研发 | 不推荐 | 不需要 | 结构化执行、排障、代码生成 |
| `--tool-request` / `--tool-stdin` / `--mcp-server` | Agent | 不允许 | 不允许 | `inspect_ui -> load_case_memory -> execute` |

> `agent_cli.py` 是 6 行 shim，所有逻辑实现在 `cli/` 包内。

## 已落地动作类型

| 动作 | Android | iOS | Web | 说明 |
|---|---|---|---|---|
| `click` | 支持 | 基础支持 | 支持 | 标准点击 |
| `long_click` | 支持 | 基础支持 | 通过延迟 click 模拟 | |
| `hover` | 忽略 | 忽略 | 支持 | 仅 Web 真正生效 |
| `input` | 支持 | 基础支持 | 支持 | |
| `swipe` | 支持 | 依赖底层能力 | 支持 | Web 通过滚轮模拟 |
| `press` | 支持 | 基础支持 | 支持 | |
| `scroll_into_view` | 不适用 | 不适用 | 支持 | 仅 Web：元素级滚动进视口（优于盲目 swipe）。移动端无稳健的免坐标等价实现 |
| `select` | 不适用 | 不适用 | 支持 | 仅 Web：原生 `<select>` 选项选择。`extra_value` = 选项文本或 value |
| `upload` | 不适用 | 不适用 | 支持 | 仅 Web：文件 `<input>` 上传。`extra_value` = 文件路径 |
| `double_click` | 不适用 | 不适用 | 支持 | 仅 Web：双击 |
| `right_click` | 不适用 | 不适用 | 支持 | 仅 Web：右键（触发上下文菜单） |
| `drag` | 不适用 | 不适用 | 支持 | 仅 Web：拖拽。locator 定位源，`extra_value` = 目标(css 或文本)。指针式拖拽；HTML5 dataTransfer 原生 DnD 不在覆盖范围 |
| `wait_for` | 支持 | 基础支持 | 支持 | 显式同步：等待元素出现/消失，替代死等。`extra_value` = `visible`(默认)/`hidden` |
| `assert_exist` | 支持 | 基础支持 | 支持 | 元素出现（Web 端 `wait_for(visible)` 自动轮询） |
| `assert_not_exist` | 支持 | 基础支持 | 支持 | 元素消失/不存在（Web `to_be_hidden`、Android `wait_gone`） |
| `assert_text_equals` | 支持 | 基础支持 | 支持 | 文本完全相等（Web 端用 `expect().to_have_text` 自动重试） |
| `assert_text_contains` | 支持 | 基础支持 | 支持 | 文本包含子串（动态文本首选，Web `expect().to_contain_text`） |
| `assert_value` | 支持 | 基础支持 | 支持 | 表单字段值（Web `expect().to_have_value`、移动端取 text） |
| `assert_url` | 不适用 | 不适用 | 支持 | 仅 Web：页面 URL 含子串（global 动作，`expect().to_have_url` 自动重试） |

> ℹ️ **Web 断言采用 Playwright `expect()` 自动重试**：生成的测试代码对文本/值/可见性断言使用 `expect(locator).to_*(..., timeout=...)`，会轮询至条件满足或超时，消除异步 UI 上"读一次就比较"的 flaky。`execute()` 实时裁决路径保持有界轮询返回布尔值，供自治循环与 `--json` 区分"断言失败"与"引擎错误"。`goto/press/swipe` 生成代码不再写入固定 `wait_for_timeout` 死等——`goto` 用 `wait_until='load'` 同步，后续动作依赖定位器自身的 auto-wait。

> ℹ️ **失败反馈工效（2026-06）**：`--action --json` 失败时，engine_error（非断言失败）
> 返回结构化诊断：`error_code` + `fix`（与 stderr `[E0xx]` 同一来源，见 `common/error_codes.py`）、
> did-you-mean `candidates`（`difflib` 对页面元素 text/desc/name 相似度排序，过 0.55 阈值，
> 每个候选含 `{text, score, locator}`，`locator` 可直接重试）、`recommended_next_step`，以及
> **当前 `ui_tree`**（agent 无需再发一次 `inspect_ui`）。**诚实边界**：相似度全低于阈值 → 空
> `candidates` + re-inspect 建议，绝不编造；连接断导致抓不到页面 → `ui_tree` 退化为空、
> `candidates` 随之为空（payload 形态不变，不编造元素）；`assertion_failed:true`
> 是裁决不是定位问题 → 不附候选、不给 retry 建议。成功 payload 与 `inspect_ui` 新增 `current_url`
> （仅 web；移动端无 URL 概念，诚实返回 ""）。MCP `execute` 出口为最小增强（`failure_diagnosis`
> = `{error_code, message, fix}`，无候选——run-report 形态无 live ui_elements；且需运行报告把
> executor 的 error_code 透传进 summary 后才生效，当前为诚实空对象）。

## 自愈引擎

| 能力 | 状态 | 说明 |
|---|---|---|
| 结构化 JSON 输出 | 已落地 | `HealResult` dataclass，返回 `confidence / fix_description / fixed_code` |
| 4 策略 JSON 解析 | 已落地 | 直接 JSON → JSON fence → 平衡括号提取 → markdown code block → 原文 fallback |
| AST 语法校验 | 已落地 | `ast.parse(fixed_code)` 验证，语法错误则 confidence=0.0 |
| 置信度阈值 | 已落地 | 低于 `AUTO_HEAL_MIN_CONFIDENCE`（默认 0.7）时跳过自愈 |
| 覆盖前备份 | 已落地 | `shutil.copy2` 生成 `.bak` 文件后再覆盖测试脚本 |

## 当前已知边界

1. `APP_ENV_CONFIG` 当前仓库默认只配置了 `dev` 环境，其他环境需用户自行补充。
2. iOS 目前只具备基础接入能力，尚未实现和 Android / Web 同等级的结构采集、录像和启动流程。
3. Web 当前依赖已启动的 Chrome CDP 会话，使用前需要准备好 `WEB_CDP_URL`。
4. `plan-only` 和 `dry-run` 是控制面能力，重点是预览与排障，不替代正式 `run` 模式。
5. `mcp-server` 当前暴露 `ui_agent_capabilities`、`ui_agent_inspect_ui`、`ui_agent_load_case_memory`、`ui_agent_execute` 和 `ui_agent_load_run` 五个 tools。
6. 视觉 fallback (VLM) 依赖 `VISION_API_KEY` / `VISION_BASE_URL` / `VISION_MODEL_NAME` 配置，未配置时自动降级到纯 DOM/XML 定位。
7. 真正的 `run` 执行完成后，会自动更新 `memory/case_memory.json`，供后续 Agent 运行复用测试资产。
