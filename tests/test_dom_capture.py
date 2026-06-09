"""Tests for playground/dom_capture.py — the sidecar HIERARCHICAL tree builders.

Unlike utils/utils_xml.py (which flattens for the LLM), these preserve parent/
child so the playground can render a real tree. They REUSE utils_xml predicates
(never modify them) and degrade to None on any failure (never crash the sink).
"""

from playground.dom_capture import build_mobile_tree, build_web_tree  # noqa: F401


class TestBuildMobileTree:
    def test_returns_none_on_parse_error(self):
        assert build_mobile_tree("<<not xml", "android") is None

    def test_empty_hierarchy_yields_empty_nodes(self):
        xml = '<hierarchy rotation="0"></hierarchy>'
        tree = build_mobile_tree(xml, "android")
        assert tree == {"platform": "android", "nodes": []}

    def test_single_clickable_node_emitted(self):
        xml = (
            '<hierarchy rotation="0">'
            '<node class="android.widget.Button" text="Login" clickable="true"/>'
            '</hierarchy>'
        )
        tree = build_mobile_tree(xml, "android")
        assert tree["platform"] == "android"
        assert len(tree["nodes"]) == 1
        n = tree["nodes"][0]
        assert n["class"] == "Button"
        assert n["text"] == "Login"
        assert n["clickable"] is True
        assert n["children"] == []

    def test_hierarchy_is_preserved_not_flattened(self):
        # A clickable container with a labeled child: the tree keeps the nesting
        # (the FLAT compressor would emit them as siblings; we must not).
        xml = (
            '<hierarchy rotation="0">'
            '<node class="android.widget.LinearLayout" text="Settings" clickable="true">'
            '  <node class="android.widget.TextView" text="Wi-Fi"/>'
            '</node>'
            '</hierarchy>'
        )
        tree = build_mobile_tree(xml, "android")
        assert len(tree["nodes"]) == 1
        parent = tree["nodes"][0]
        assert parent["text"] == "Settings"
        assert len(parent["children"]) == 1
        assert parent["children"][0]["text"] == "Wi-Fi"

    def test_dead_wrapper_collapses_lifting_children(self):
        # A non-surviving wrapper (no text/desc/clickable/disabled) must NOT appear;
        # its surviving child lifts to the wrapper's parent level.
        xml = (
            '<hierarchy rotation="0">'
            '<node class="android.widget.FrameLayout">'
            '  <node class="android.widget.Button" text="OK" clickable="true"/>'
            '</node>'
            '</hierarchy>'
        )
        tree = build_mobile_tree(xml, "android")
        assert len(tree["nodes"]) == 1
        assert tree["nodes"][0]["text"] == "OK"   # lifted, wrapper gone

    def test_disabled_emitted_without_clickable(self):
        xml = (
            '<hierarchy rotation="0">'
            '<node class="android.widget.Button" text="Send" enabled="false"/>'
            '</hierarchy>'
        )
        tree = build_mobile_tree(xml, "android")
        n = tree["nodes"][0]
        assert n["disabled"] is True
        assert "clickable" not in n

    def test_full_resource_id_emitted(self):
        xml = (
            '<hierarchy rotation="0">'
            '<node class="android.widget.Button" text="Go" clickable="true" '
            'resource-id="com.app:id/go_btn"/>'
            '</hierarchy>'
        )
        tree = build_mobile_tree(xml, "android")
        assert tree["nodes"][0]["id"] == "com.app:id/go_btn"

    def test_no_ref_and_no_bbox_on_mobile(self):
        xml = (
            '<hierarchy rotation="0">'
            '<node class="android.widget.Button" text="X" clickable="true" '
            'bounds="[0,0][100,50]"/>'
            '</hierarchy>'
        )
        n = build_mobile_tree(xml, "android")["nodes"][0]
        assert "ref" not in n
        assert "x" not in n and "w" not in n   # honest: mobile has no bbox in this shape
