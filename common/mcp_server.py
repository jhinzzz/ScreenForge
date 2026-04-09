import json
import sys
from typing import Any, Callable

from pydantic import ValidationError

from common.capabilities import (
    ACTIONS_REQUIRING_EXTRA_VALUE,
    CONTROL_PLANES,
    EXECUTION_MODES,
    SUPPORTED_ACTIONS,
    SUPPORTED_PLATFORMS,
)
from common.tool_protocol import ToolRequest


JSONRPC_VERSION = "2.0"
MCP_SERVER_NAME = "screenforge"
MCP_SERVER_VERSION = "0.1.0"
MCP_TOOL_CAPABILITIES = "ui_agent_capabilities"
MCP_TOOL_EXECUTE = "ui_agent_execute"
MCP_TOOL_LOAD_RUN = "ui_agent_load_run"
SUPPORTED_MCP_PROTOCOL_VERSIONS = (
    "2025-11-25",
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
)


def _jsonrpc_response(request_id: Any, result: dict) -> dict:
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": request_id,
        "result": result,
    }


def _jsonrpc_error(request_id: Any, code: int, message: str, data: Any | None = None) -> dict:
    error = {
        "code": code,
        "message": message,
    }
    if data is not None:
        error["data"] = data
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": request_id,
        "error": error,
    }


def _negotiate_protocol_version(requested_version: str) -> str:
    requested = str(requested_version).strip()
    if requested in SUPPORTED_MCP_PROTOCOL_VERSIONS:
        return requested
    return SUPPORTED_MCP_PROTOCOL_VERSIONS[0]


def _build_capabilities_tool_schema() -> dict:
    return {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }


def _build_execute_tool_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": list(EXECUTION_MODES),
                "description": "执行模式：run / doctor / plan_only / dry_run",
            },
            "platform": {
                "type": "string",
                "enum": list(SUPPORTED_PLATFORMS),
                "description": "目标平台",
            },
            "env": {
                "type": "string",
                "description": "环境名称，默认 dev",
            },
            "vision": {
                "type": "boolean",
                "description": "是否启用视觉模式",
            },
            "context": {
                "type": "string",
                "description": "上下文文件路径",
            },
            "output": {
                "type": "string",
                "description": "输出脚本路径",
            },
            "resume_run_id": {
                "type": "string",
                "description": "恢复上下文的 run_id",
            },
            "goal": {
                "type": "string",
                "description": "自主探索目标",
            },
            "workflow": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "workflow YAML 路径",
                    },
                    "vars": {
                        "type": "object",
                        "description": "workflow 变量覆盖",
                        "additionalProperties": {"type": "string"},
                    },
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            "action": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": list(SUPPORTED_ACTIONS),
                        "description": "即时动作类型",
                    },
                    "action_name": {
                        "type": "string",
                        "description": "即时动作名称",
                    },
                    "locator_type": {
                        "type": "string",
                        "description": "定位器类型",
                    },
                    "locator_value": {
                        "type": "string",
                        "description": "定位器值",
                    },
                    "extra_value": {
                        "type": "string",
                        "description": "动作附加值",
                    },
                },
                "required": ["action"],
                "additionalProperties": False,
            },
        },
        "additionalProperties": False,
    }


def _build_load_run_tool_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "run_id": {
                "type": "string",
                "description": "需要加载的历史运行 run_id",
            }
        },
        "required": ["run_id"],
        "additionalProperties": False,
    }


def build_mcp_tools() -> list[dict]:
    return [
        {
            "name": MCP_TOOL_CAPABILITIES,
            "title": "ScreenForge Capabilities",
            "description": "返回当前 ScreenForge 已落地的平台、模式、控制面与动作能力快照。",
            "inputSchema": _build_capabilities_tool_schema(),
        },
        {
            "name": MCP_TOOL_EXECUTE,
            "title": "ScreenForge Execute",
            "description": (
                "执行或预演 ScreenForge 请求。支持 goal、workflow、action、doctor 四类控制面；"
                f"支持的执行模式为 {', '.join(EXECUTION_MODES)}；"
                f"支持的平台为 {', '.join(SUPPORTED_PLATFORMS)}；"
                f"支持的控制面为 {', '.join(CONTROL_PLANES)}；"
                f"需要 extra_value 的动作为 {', '.join(sorted(ACTIONS_REQUIRING_EXTRA_VALUE))}。"
            ),
            "inputSchema": _build_execute_tool_schema(),
        },
        {
            "name": MCP_TOOL_LOAD_RUN,
            "title": "ScreenForge Load Run",
            "description": "按 run_id 读取历史运行的 summary、resume_context 和回放资产。",
            "inputSchema": _build_load_run_tool_schema(),
        },
    ]


def _build_initialize_result(protocol_version: str) -> dict:
    return {
        "protocolVersion": _negotiate_protocol_version(protocol_version),
        "capabilities": {
            "tools": {
                "listChanged": False,
            }
        },
        "serverInfo": {
            "name": MCP_SERVER_NAME,
            "version": MCP_SERVER_VERSION,
        },
        "instructions": (
            "Use ui_agent_capabilities to inspect ScreenForge support, and ui_agent_execute "
            "to run goal/workflow/action/doctor requests against the existing CLI execution engine."
        ),
    }


def _build_tool_result(payload: dict) -> dict:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, ensure_ascii=False, indent=2),
            }
        ],
        "structuredContent": payload,
        "isError": not bool(payload.get("ok", False)),
    }


class McpServerSession:
    def __init__(
        self,
        execute_tool_request: Callable[[ToolRequest], dict],
        load_run_payload: Callable[[str], dict] | None = None,
    ):
        self._execute_tool_request = execute_tool_request
        self._load_run_payload = load_run_payload or (
            lambda run_id: {
                "ok": False,
                "operation": "load_run",
                "exit_code": 2,
                "error": f"未配置 load_run 处理器: {run_id}",
            }
        )
        self._initialized = False

    def handle_message(self, message: dict) -> dict | None:
        if not isinstance(message, dict):
            return _jsonrpc_error(None, -32600, "无效的 JSON-RPC 请求")

        method = str(message.get("method", "")).strip()
        request_id = message.get("id")
        params = message.get("params", {}) or {}

        if method == "notifications/initialized":
            self._initialized = True
            return None

        if method == "initialize":
            self._initialized = True
            return _jsonrpc_response(
                request_id,
                _build_initialize_result(params.get("protocolVersion", "")),
            )

        if method == "ping":
            return _jsonrpc_response(request_id, {})

        if method == "tools/list":
            return _jsonrpc_response(request_id, {"tools": build_mcp_tools()})

        if method == "tools/call":
            return self._handle_tool_call(request_id, params)

        if request_id is None:
            return None

        return _jsonrpc_error(request_id, -32601, f"不支持的方法: {method}")

    def _handle_tool_call(self, request_id: Any, params: dict) -> dict:
        tool_name = str(params.get("name", "")).strip()
        arguments = params.get("arguments", {}) or {}

        if tool_name == MCP_TOOL_CAPABILITIES:
            request = ToolRequest(operation="capabilities")
        elif tool_name == MCP_TOOL_LOAD_RUN:
            run_id = str(arguments.get("run_id", "")).strip()
            if not run_id:
                return _jsonrpc_error(request_id, -32602, "tool 参数校验失败", "run_id 不能为空")
            try:
                payload = self._load_run_payload(run_id)
            except Exception as exc:
                return _jsonrpc_error(request_id, -32603, "工具执行失败", str(exc))
            return _jsonrpc_response(request_id, _build_tool_result(payload))
        elif tool_name == MCP_TOOL_EXECUTE:
            try:
                request = ToolRequest.model_validate(
                    {
                        "operation": "execute",
                        **arguments,
                    }
                )
            except ValidationError as exc:
                return _jsonrpc_error(request_id, -32602, "tool 参数校验失败", str(exc))
        else:
            return _jsonrpc_error(request_id, -32602, f"不支持的工具: {tool_name}")

        try:
            payload = self._execute_tool_request(request)
        except Exception as exc:
            return _jsonrpc_error(request_id, -32603, "工具执行失败", str(exc))

        return _jsonrpc_response(request_id, _build_tool_result(payload))


def run_stdio_mcp_server(
    execute_tool_request: Callable[[ToolRequest], dict],
    load_run_payload: Callable[[str], dict],
    stdin=None,
    stdout=None,
) -> int:
    input_stream = stdin or sys.stdin
    output_stream = stdout or sys.stdout
    session = McpServerSession(
        execute_tool_request=execute_tool_request,
        load_run_payload=load_run_payload,
    )

    for raw_line in input_stream:
        line = str(raw_line).strip()
        if not line:
            continue

        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            response = _jsonrpc_error(None, -32700, "JSON 解析失败", str(exc))
        else:
            if isinstance(message, list):
                response = _jsonrpc_error(None, -32600, "暂不支持 batch 请求")
            else:
                response = session.handle_message(message)

        if response is None:
            continue

        output_stream.write(json.dumps(response, ensure_ascii=False) + "\n")
        output_stream.flush()

    return 0
