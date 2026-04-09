import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

from common.capabilities import (
    ACTIONS_REQUIRING_EXTRA_VALUE,
    SUPPORTED_ACTIONS,
    get_capabilities_payload,
)
from common.runtime_modes import MODE_DOCTOR, MODE_DRY_RUN, MODE_PLAN_ONLY, MODE_RUN


SUPPORTED_TOOL_MODES = (MODE_RUN, MODE_DOCTOR, MODE_PLAN_ONLY, MODE_DRY_RUN)


class ToolRequestError(ValueError):
    pass


class WorkflowToolControl(BaseModel):
    path: str
    vars: dict[str, str] = Field(default_factory=dict)


class ActionToolControl(BaseModel):
    action: str
    action_name: str = ""
    locator_type: str = ""
    locator_value: str = ""
    extra_value: str = ""

    @model_validator(mode="after")
    def validate_action(self):
        if self.action not in SUPPORTED_ACTIONS:
            raise ValueError(f"不支持的即时动作类型: {self.action}")
        if self.action not in {"swipe", "press"}:
            if not str(self.locator_type).strip() or not str(self.locator_value).strip():
                raise ValueError("元素类即时动作必须提供 locator_type 和 locator_value")
        if self.action in ACTIONS_REQUIRING_EXTRA_VALUE and not str(self.extra_value).strip():
            raise ValueError("该即时动作必须提供 extra_value")
        return self


class ToolRequest(BaseModel):
    operation: Literal["capabilities", "execute", "load_run"]
    mode: Literal["run", "doctor", "plan_only", "dry_run"] = MODE_RUN
    platform: Literal["android", "ios", "web"] = "android"
    env: str = "dev"
    vision: bool = False
    context: str = ""
    output: str = ""
    resume_run_id: str = ""
    run_id: str = ""
    goal: str = ""
    workflow: WorkflowToolControl | None = None
    action: ActionToolControl | None = None

    @model_validator(mode="after")
    def validate_request(self):
        if self.operation == "capabilities":
            return self

        control_count = int(bool(str(self.goal).strip())) + int(self.workflow is not None) + int(
            self.action is not None
        )
        if self.operation == "load_run":
            if control_count:
                raise ValueError("load_run tool request 不能同时携带 goal、workflow 或 action")
            if not str(self.run_id).strip():
                raise ValueError("load_run tool request 必须提供 run_id")
            return self

        if self.mode == MODE_DOCTOR:
            if control_count:
                raise ValueError("doctor tool request 不能同时携带 goal、workflow 或 action")
            return self

        if control_count != 1:
            raise ValueError("execute tool request 必须且只能提供一种控制面：goal、workflow 或 action")
        return self


def _validate_tool_request_payload(payload: dict, source_label: str) -> ToolRequest:
    try:
        return ToolRequest.model_validate(payload)
    except ValidationError as exc:
        raise ToolRequestError(f"{source_label} 校验失败: {exc}") from exc


def load_tool_request(file_path: str | Path) -> ToolRequest:
    path = Path(file_path).expanduser().resolve()
    if not path.exists():
        raise ToolRequestError(f"未找到 tool request 文件: {path}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ToolRequestError(f"tool request JSON 解析失败: {exc}") from exc

    return _validate_tool_request_payload(payload, "tool request")


def load_tool_request_from_stdin(raw_text: str) -> ToolRequest:
    if not str(raw_text).strip():
        raise ToolRequestError("tool stdin 为空，无法解析请求")

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ToolRequestError(f"tool stdin JSON 解析失败: {exc}") from exc

    return _validate_tool_request_payload(payload, "tool stdin")


def build_cli_arg_overrides(request: ToolRequest) -> dict:
    overrides = {
        "goal": "",
        "context": request.context,
        "env": request.env,
        "platform": request.platform,
        "vision": request.vision,
        "json": False,
        "doctor": request.mode == MODE_DOCTOR,
        "plan_only": request.mode == MODE_PLAN_ONLY,
        "dry_run": request.mode == MODE_DRY_RUN,
        "resume_run_id": request.resume_run_id,
        "workflow": "",
        "workflow_var": [],
        "action": "",
        "action_name": "",
        "locator_type": "",
        "locator_value": "",
        "extra_value": "",
        "output": request.output,
        "capabilities": False,
        "tool_request": "",
        "tool_stdin": False,
        "mcp_server": False,
    }

    if request.workflow:
        overrides["workflow"] = request.workflow.path
        overrides["workflow_var"] = [
            f"{key}={value}" for key, value in request.workflow.vars.items()
        ]
    elif request.action:
        overrides["action"] = request.action.action
        overrides["action_name"] = request.action.action_name
        overrides["locator_type"] = request.action.locator_type
        overrides["locator_value"] = request.action.locator_value
        overrides["extra_value"] = request.action.extra_value
    else:
        overrides["goal"] = request.goal

    return overrides


def build_capabilities_response() -> dict:
    return {
        "ok": True,
        "operation": "capabilities",
        "capabilities": get_capabilities_payload(),
    }
