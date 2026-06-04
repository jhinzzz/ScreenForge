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
        let refIndex = 0;

        // Web 端具有明确交互语义的 role 集合
        const interactiveRoles = new Set(['button', 'link', 'menuitem', 'option', 'tab', 'switch', 'checkbox', 'radio', 'combobox']);
        // 纯结构或绝对无用的标签。注意 iframe 不在此列：我们要递归进入其内容
        // 文档（见 walk）而不是把 iframe 框本身当作元素。
        const ignoreTags = new Set(['script', 'style', 'noscript', 'head', 'meta', 'title', 'br', 'hr', 'svg', 'path', 'g', 'img', 'video', 'audio', 'iframe']);

        // 判定元素是否处于 inert 子树。closest('[inert]') 只在同一棵树内向上找，
        // 看不到 shadow host / iframe 之外的祖先 —— 故由 walk 把跨边界继承来的
        // inert 状态(inherited)一并算入，与 offX/offY 跨边界传递的方式一致。
        function isInertEl(el, inherited) {
            if (inherited) return true;
            try { return el.closest('[inert]') !== null; } catch (e) { return false; }
        }

        // 处理单个元素：offX/offY 是从内层文档（iframe）坐标系到顶层视口坐标系
        // 的偏移量，保证 shadow/iframe 内元素的 bbox 仍然是顶层坐标，ref 点击不会错位。
        // inheritedInert：宿主/iframe 跨边界继承来的 inert 状态（见 walk）。
        function processEl(el, offX, offY, inheritedInert) {
            const tag = el.tagName.toLowerCase();
            if (ignoreTags.has(tag)) return;

            // 1. 物理可见性校验 (过滤幽灵节点)
            let rect;
            try { rect = el.getBoundingClientRect(); } catch (e) { return; }
            if (rect.width === 0 || rect.height === 0) return;
            let style;
            try { style = (el.ownerDocument.defaultView || window).getComputedStyle(el); } catch (e) { return; }
            if (style.visibility === 'hidden' || style.opacity === '0' || style.display === 'none') return;

            // 2. 交互意图判定。disabled / aria-disabled 的控件不可点：标 clickable=false
            //    （仍然收录，便于断言其存在/禁用），否则 LLM 会去点禁用按钮并卡超时。
            //    用 :disabled 伪类而非 el.disabled —— 后者只反映元素自身的 disabled
            //    属性，看不到「<fieldset disabled> 传播给后代控件」这一规范行为
            //    （含首个 <legend> 内控件豁免、嵌套 fieldset 由外层继续禁用）。
            //    :disabled 正是浏览器对「actually disabled」的实现，一次到位且权威。
            const ariaDisabled = el.getAttribute('aria-disabled') === 'true';
            let nativeDisabled;
            try { nativeDisabled = el.matches(':disabled'); }
            catch (e) { nativeDisabled = el.disabled === true; }
            const isDisabled = nativeDisabled || ariaDisabled;
            // inert 子树（开 <dialog> 时背景标 inert 的标准模式）会吞掉点击 ——
            // 这类控件仍可见会被收录，但若仍标 clickable，LLM 会去点模态背后的死
            // 按钮然后 no-op/超时，故同样判为不可点。但 inert ≠ disabled（前者是"被
            // 遮挡/暂不可交互"，后者是"控件本身被禁用"），分开上报：让 LLM 能推断
            // "有模态需先关掉"而非"表单被禁用"，也避免 assert disabled 误判通过。
            const isInert = isInertEl(el, inheritedInert);
            const isInteractive = !isDisabled && !isInert && (
                                  ['a', 'button', 'input', 'select', 'textarea'].includes(tag) ||
                                  el.hasAttribute('onclick') ||
                                  interactiveRoles.has(el.getAttribute('role')) ||
                                  style.cursor === 'pointer');

            // 3. 智能文本提取 (防止父容器吞噬子节点文本造成大量重复)
            const directText = Array.from(el.childNodes)
                .filter(node => node.nodeType === Node.TEXT_NODE)
                .map(node => node.nodeValue.trim())
                .join(' ').trim();

            let fullText = el.innerText ? el.innerText.trim() : '';
            if (tag === 'input' || tag === 'textarea') fullText = el.value || '';
            if (fullText.length > 100) fullText = fullText.substring(0, 100) + '...';

            const ariaLabel = el.getAttribute('aria-label') || el.getAttribute('title') || el.getAttribute('alt') || '';

            // 4. 噪音与垃圾数据剔除策略
            //    收录条件用「语义可交互」(标签/role 本身可交互，忽略 disabled)，
            //    这样禁用按钮也会被收录(clickable=false)，而纯排版 wrapper 仍被丢弃。
            const isSemanticControl = ['a', 'button', 'input', 'select', 'textarea'].includes(tag) ||
                                      el.hasAttribute('onclick') ||
                                      interactiveRoles.has(el.getAttribute('role'));
            const keepForLayout = isInteractive || isSemanticControl;
            if (!keepForLayout && !directText && !ariaLabel) return;

            // For a kept (interactive/semantic) element, prefer innerText but
            // fall back to its own directText — otherwise a clickable shadow
            // HOST whose light text isn't slotted (innerText==='') would be
            // dropped by the empty-shell guard below, leaving it invisible to
            // the LLM (the exact blind spot this change targets).
            const displayText = keepForLayout ? (fullText || directText) : (directText.length > 0 ? fullText : directText);

            const placeholder = el.getAttribute('placeholder') || '';
            const type = el.getAttribute('type') || '';
            const name = el.getAttribute('name') || '';

            if (!displayText && !ariaLabel && !placeholder && !['input', 'select', 'textarea'].includes(tag)) return;

            // 5. 构建低 Token 结构体
            refIndex++;
            const nodeData = { "ref": "@" + refIndex, "class": tag, "clickable": isInteractive };
            if (el.id) nodeData.id = el.id;
            if (name) nodeData.name = name;
            if (type) nodeData.type = type;
            if (placeholder) nodeData.placeholder = placeholder;
            if (ariaLabel) nodeData.desc = ariaLabel;
            if (displayText) nodeData.text = displayText;
            if (isDisabled) nodeData.disabled = true;
            if (isInert) nodeData.inert = true;
            nodeData.x = Math.round(rect.x + offX);
            nodeData.y = Math.round(rect.y + offY);
            nodeData.w = Math.round(rect.width);
            nodeData.h = Math.round(rect.height);

            elements.push(nodeData);
        }

        // 递归遍历：普通子树 + shadow DOM + 同源 iframe。这是修复"压缩器对
        // shadow DOM / iframe 失明"的核心：querySelectorAll('*') 不穿透 shadow
        // root，也不进入 iframe 文档，导致整类应用对 LLM 不可见。
        function walk(root, offX, offY, depth, inheritedInert) {
            // Depth cap: static DOM can't form true cycles (an iframe's
            // contentDocument is always a fresh document; a shadow root can't
            // contain its own host), so this is insurance against pathologically
            // deep generated pages approaching the JS recursion limit.
            if (depth > 50) return;
            let nodes;
            try { nodes = root.querySelectorAll('*'); } catch (e) { return; }
            nodes.forEach(el => {
                const tag = el.tagName ? el.tagName.toLowerCase() : '';

                // 同源 iframe：进入其内容文档，并按 iframe 在顶层的位置做坐标偏移。
                // 跨域 iframe 访问 contentDocument 会抛异常 —— 那是浏览器安全边界，
                // 无法穿透，静默跳过(诚实:我们不假装能看到跨域内容)。
                if (tag === 'iframe') {
                    // inert 跨 iframe 边界继承：frame 内文档看不到父文档的 inert 祖先，
                    // 故在此判定 iframe 自身或其祖先是否 inert，向内传递。
                    const frameInert = inheritedInert || isInertEl(el, false);
                    let doc = null, frameRect = null, insetX = 0, insetY = 0;
                    try {
                        frameRect = el.getBoundingClientRect();
                        // getBoundingClientRect gives the iframe's BORDER-box origin,
                        // but the content document starts inside the border+padding.
                        // Without this inset every child is reported too far up-left
                        // (Chromium's default 2px iframe border alone shifts a ref
                        // click off-target; thick-bordered embed/payment frames more).
                        const cs = (el.ownerDocument.defaultView || window).getComputedStyle(el);
                        insetX = (parseFloat(cs.borderLeftWidth) || 0) + (parseFloat(cs.paddingLeft) || 0);
                        insetY = (parseFloat(cs.borderTopWidth) || 0) + (parseFloat(cs.paddingTop) || 0);
                        doc = el.contentDocument;
                    } catch (e) { doc = null; }
                    if (doc && doc.documentElement) {
                        walk(doc.documentElement, offX + frameRect.x + insetX, offY + frameRect.y + insetY, depth + 1, frameInert);
                    }
                    return;
                }

                processEl(el, offX, offY, inheritedInert);

                // shadow root（open 模式）：递归进入。坐标系与宿主一致，偏移不变。
                // inert 同样跨 shadow 边界继承：closest 不穿透 shadow root，故把
                // 宿主自身/继承来的 inert 状态算好后传入。
                if (el.shadowRoot) {
                    walk(el.shadowRoot, offX, offY, depth + 1, isInertEl(el, inheritedInert));
                }
            });
        }

        walk(document.documentElement, 0, 0, 0, false);

        // 6. 最终去重 (防止某些前端库生成多个不可见的克隆 DOM)
        const uniqueElements = [];
        const seen = new Set();
        elements.forEach(el => {
            const dedupKeys = Object.keys(el).filter(k => k !== 'ref').sort();
            const key = JSON.stringify(el, dedupKeys);
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
        print(f"[Warning] Failed to extract Web DOM: {e}")
        return '{"ui_elements": []}'
