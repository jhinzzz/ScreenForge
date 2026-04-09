import json
from urllib.parse import urlsplit, urlunsplit


def normalize_loopback_url(url: str) -> str:
    parsed = urlsplit(str(url))
    if parsed.hostname != "localhost":
        return str(url)

    normalized_netloc = parsed.netloc.replace("localhost", "127.0.0.1", 1)
    return urlunsplit(
        (
            parsed.scheme,
            normalized_netloc,
            parsed.path,
            parsed.query,
            parsed.fragment,
        )
    )

def compress_web_dom(page) -> str:
    """
    通过向 Playwright 的 page 注入 JS，提取当前页面可见的、有交互价值的元素。
    该算法采用了"物理可见性校验"与"布局噪音消除"机制，能将动辄几万行的 HTML 压缩 95% 以上的噪音，
    并将其降维成与 Android XML 结构一致且富含语义的 JSON。
    """
    js_script = """
    () => {
        const elements = [];

        // Web 端具有明确交互语义的 role 集合
        const interactiveRoles = new Set(['button', 'link', 'menuitem', 'option', 'tab', 'switch', 'checkbox', 'radio', 'combobox']);
        // 纯结构或绝对无用的标签
        const ignoreTags = new Set(['script', 'style', 'noscript', 'head', 'meta', 'title', 'br', 'hr', 'svg', 'path', 'g', 'img', 'iframe', 'video', 'audio']);

        document.querySelectorAll('*').forEach(el => {
            const tag = el.tagName.toLowerCase();
            if (ignoreTags.has(tag)) return;

            // ==========================================
            // 1. 物理可见性校验 (过滤幽灵节点)
            // ==========================================
            let rect;
            try {
                rect = el.getBoundingClientRect();
            } catch (e) {
                return;
            }
            if (rect.width === 0 || rect.height === 0) return;
            let style;
            try {
                style = window.getComputedStyle(el);
            } catch (e) {
                return;
            }
            if (style.visibility === 'hidden' || style.opacity === '0' || style.display === 'none') return;

            // ==========================================
            // 2. 交互意图判定
            // ==========================================
            const isInteractive = ['a', 'button', 'input', 'select', 'textarea'].includes(tag) ||
                                  el.hasAttribute('onclick') ||
                                  interactiveRoles.has(el.getAttribute('role')) ||
                                  style.cursor === 'pointer';

            // ==========================================
            // 3. 智能文本提取 (防止父容器吞噬子节点文本造成大量重复)
            // ==========================================
            // 仅提取当前元素直属的文本内容，不包含子标签里的内容
            const directText = Array.from(el.childNodes)
                .filter(node => node.nodeType === Node.TEXT_NODE)
                .map(node => node.nodeValue.trim())
                .join(' ').trim();

            let fullText = el.innerText ? el.innerText.trim() : '';
            // 对于表单元素，它的状态就是它的价值
            if (tag === 'input' || tag === 'textarea') fullText = el.value || '';
            // 限制过长的噪音文本
            if (fullText.length > 100) fullText = fullText.substring(0, 100) + '...';

            const ariaLabel = el.getAttribute('aria-label') || el.getAttribute('title') || el.getAttribute('alt') || '';

            // ==========================================
            // 4. 噪音与垃圾数据剔除策略
            // ==========================================
            // 策略 A: 如果它既不能点，又没有自己的文本，也没有 aria 描述，那它必定是用来排版的纯透明 wrapper -> 抛弃
            if (!isInteractive && !directText && !ariaLabel) return;

            // 对于非交互元素，优先展示直属文本，防止嵌套导致满屏都是相同的长句子
            const displayText = (isInteractive || directText.length > 0) ? fullText : directText;

            // 表单元素的核心上下文注入
            const placeholder = el.getAttribute('placeholder') || '';
            const type = el.getAttribute('type') || '';
            const name = el.getAttribute('name') || '';

            // 策略 B: 经历上述清洗后，如果仍是空壳，且不是必须要填的表单框 -> 抛弃
            if (!displayText && !ariaLabel && !placeholder && !['input', 'select', 'textarea'].includes(tag)) return;

            // ==========================================
            // 5. 构建低 Token 结构体
            // ==========================================
            // 采用按需压入（过滤掉值为 空字符串 的 Key），极致压缩 Token 消耗
            const nodeData = { "class": tag, "clickable": isInteractive };
            if (el.id) nodeData.id = el.id;
            if (name) nodeData.name = name;
            if (type) nodeData.type = type;
            if (placeholder) nodeData.placeholder = placeholder;
            if (ariaLabel) nodeData.desc = ariaLabel;
            if (displayText) nodeData.text = displayText;

            elements.push(nodeData);
        });

        // ==========================================
        // 6. 最终去重 (防止某些前端库生成多个不可见的克隆 DOM)
        // ==========================================
        const uniqueElements = [];
        const seen = new Set();
        elements.forEach(el => {
            const key = JSON.stringify(el, Object.keys(el).sort());
            if (!seen.has(key)) {
                seen.add(key);
                uniqueElements.push(el);
            }
        });

        return JSON.stringify({"ui_elements": uniqueElements});
    }
    """
    try:
        # 在 Playwright 浏览器上下文环境中执行 JS 注入并获取结果
        ui_json_str = page.evaluate(js_script)
        return ui_json_str
    except Exception as e:
        print(f"[Warning] 提取 Web DOM 失败: {e}")
        return '{"ui_elements": []}'
