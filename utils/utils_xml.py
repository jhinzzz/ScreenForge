import xml.etree.ElementTree as ET
import json


def compress_android_xml(raw_xml: str) -> str:
    """
    清洗并压缩 Android XML，提取有价值的交互节点和文本节点，降低 Token 消耗
    """
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

        # 过滤规则：有文本/描述，或者是可点击的图标，且不是系统状态栏
        if (text or desc or clickable) and "com.android.systemui" not in res_id:
            el_info = {"class": node_class}
            if text:
                el_info["text"] = text
            if desc:
                el_info["desc"] = desc
            if res_id:
                el_info["id"] = res_id
            if clickable:
                el_info["clickable"] = True

            # 去重优化：如果当前节点与上一个节点内容完全一致，合并属性（保留可点击态）
            if elements and elements[-1].get("text") == text and text != "":
                if clickable:
                    elements[-1]["clickable"] = True
                    if res_id and "id" not in elements[-1]:
                        elements[-1]["id"] = res_id
                continue

            elements.append(el_info)

    # 包装成 dict，以便适配 OpenAI 的 json_object 模式
    return json.dumps({"ui_elements": elements}, ensure_ascii=False)
