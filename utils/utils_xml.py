import xml.etree.ElementTree as ET
import json
import re

def compress_android_xml(raw_xml: str) -> str:
    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError:
        return '{"ui_elements": []}'

    elements = []

    for node in root.iter():
        attrib = node.attrib
        text = attrib.get("text", "").strip()
        desc = attrib.get("content-desc", "").strip()
        res_id = attrib.get("resource-id", "").strip()
        clickable = attrib.get("clickable") == "true"
        node_class = attrib.get("class", "").split(".")[-1]

        # ==========================================
        # 节约 Token
        # ==========================================

        # 1. 抛弃底层系统噪音和通知图标
        if "com.android.systemui" in res_id or "OpenVPN" in desc or "VoLTE" in desc:
            continue

        # 2. 致命拦截：抛弃派网特有的“变态轮盘/数字碎片轴”
        # 这种 desc 往往超长，包含无数个逗号分隔的数字
        if len(desc) > 30 and "0, 1, 2" in desc:
            continue

        # 3. 抛弃纯粹的独立符号/单数字 (如单独渲染的 "$", ",", "+", "1")
        # 如果它不可点击，且完全由单字符或纯数字标点组成，大模型不需要看它
        if not clickable and re.match(r'^[\$\¥\€\£\d\.\,\+\-\%]+$', text) and len(text) <= 5:
            continue

        # ==========================================
        # 组装发给大模型的有效节点
        # ==========================================
        if text or desc or clickable:
            el_info = {"class": node_class}
            if text: el_info["text"] = text
            if desc: el_info["desc"] = desc
            if clickable: el_info["clickable"] = True

            if res_id:
                # 只取 ID 最后一部分，并去掉可能导致失效的 8 位随机后缀
                clean_id = res_id.split("/")[-1]
                clean_id = re.sub(r'_[a-f0-9]{8}$', '', clean_id)
                el_info["id"] = clean_id

            elements.append(el_info)

    return json.dumps({"ui_elements": elements}, ensure_ascii=False)
