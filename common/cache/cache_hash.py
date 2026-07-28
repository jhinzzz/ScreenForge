import hashlib
import json
import re
from typing import Any, Dict

_BLOCKLIST = frozenset(
    [
        "加密货币",
        "比特币",
        "meme币",
        "美股代币",
        "贵金属代币",
        "热门资产",
        "已上线",
        "已上架",
        "上架",
        "下架",
        "公告",
        "活动",
    ]
)


def _latin_anchor(raw_text: str) -> str:
    """A Latin/non-CJK anchor from an element's text, or '' if not anchor-like.

    Mirrors the CJK path's dynamic-data immunity: digits and symbols are
    stripped so a changing price/balance/count doesn't move the skeleton hash
    ("Balance 100" and "Balance 9999" both reduce to "balance"). Whitespace is
    collapsed and case is folded so render noise doesn't fork the fingerprint.

    ponytail: 2..24 chars keeps button/nav labels ("login", "delete account")
    and drops long description sentences — the Latin analogue of the CJK 2..6
    window. Raise the ceiling only if a real multi-word control exceeds it.
    """
    letters_only = re.sub(r"[^a-zA-Z\s]", "", raw_text)
    normalized = " ".join(letters_only.split()).lower()
    return normalized if 2 <= len(normalized) <= 24 else ""


def _extract_semantic_fingerprint(ui_json: Dict[str, Any]) -> list:
    """
    提取页面锚点指纹，免疫动态数据和渲染顺序波动。
    """
    fingerprint_features = set()
    elements = ui_json.get("ui_elements", [])

    for el in elements:
        raw_text = el.get("text", "") or el.get("desc", "")
        # 抹除所有数字、字母、符号，只保留纯汉字
        cn_text = re.sub(r"[^\u4e00-\u9fa5]", "", raw_text)

        # 标准的 UI 导航或按钮，通常在 2 到 6 个汉字之间
        if 2 <= len(cn_text) <= 6 and cn_text not in _BLOCKLIST:
            fingerprint_features.add(f"{el.get('class')}|{cn_text}")

    # Non-CJK pages (English etc.) carry NO Chinese anchors, so the loop above
    # yields nothing and every such page collapsed to one constant hash — L1's
    # exact key then replayed an action recorded on a DIFFERENT page. Fall back
    # to Latin anchors so those pages get distinct identities too. Page-level,
    # not per-element: a page WITH usable CJK anchors keeps exactly its old
    # fingerprint (Chinese behavior frozen); only a fully-anchorless page falls
    # through here.
    if not fingerprint_features:
        for el in elements:
            anchor = _latin_anchor(el.get("text", "") or el.get("desc", ""))
            if anchor:
                fingerprint_features.add(f"{el.get('class')}|{anchor}")

    # 强制排序并转为列表，保证哈希的绝对一致性
    return sorted(list(fingerprint_features))


def compute_ui_hash(ui_json: Dict[str, Any]) -> str:
    """计算用于混合缓存匹配的页面骨架 Hash"""
    fingerprint = _extract_semantic_fingerprint(ui_json)
    fingerprint_str = json.dumps(fingerprint)
    hash_obj = hashlib.sha256()
    hash_obj.update(fingerprint_str.encode("utf-8"))
    return hash_obj.hexdigest()


def compute_instruction_hash(instruction: str) -> str:
    """计算用于混合缓存 O(1) 精确匹配的指令 Hash"""
    normalized_inst = re.sub(r"\s+", " ", instruction).strip().lower()
    hash_obj = hashlib.sha256()
    hash_obj.update(normalized_inst.encode("utf-8"))
    return hash_obj.hexdigest()
