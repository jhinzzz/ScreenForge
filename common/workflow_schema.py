import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from common.capabilities import GLOBAL_ACTIONS, SUPPORTED_ACTIONS


SUPPORTED_WORKFLOW_ACTIONS = SUPPORTED_ACTIONS
GLOBAL_WORKFLOW_ACTIONS = GLOBAL_ACTIONS
WORKFLOW_VAR_PATTERN = re.compile(r"{{\s*([a-zA-Z0-9_\-]+)\s*}}")


class WorkflowLoadError(ValueError):
    pass


class WorkflowStep(BaseModel):
    name: str = ""
    action: Literal[
        "click",
        "long_click",
        "hover",
        "input",
        "swipe",
        "press",
        "assert_exist",
        "assert_text_equals",
    ]
    locator_type: str = "global"
    locator_value: str = "global"
    extra_value: str = ""
    enabled: bool = True

    @model_validator(mode="after")
    def validate_locator(self):
        if not self.enabled:
            return self

        if self.action in GLOBAL_WORKFLOW_ACTIONS:
            if not str(self.locator_type).strip():
                self.locator_type = "global"
            if not str(self.locator_value).strip():
                self.locator_value = "global"
            return self

        if not str(self.locator_type).strip() or not str(self.locator_value).strip():
            raise ValueError("元素类工作流步骤必须提供 locator_type 和 locator_value")

        return self


class WorkflowDefinition(BaseModel):
    version: int = 1
    name: str = ""
    platform: str = ""
    env: str = ""
    vars: dict[str, str] = Field(default_factory=dict)
    steps: list[WorkflowStep] = Field(min_length=1)


def load_workflow_file(file_path: str | Path) -> WorkflowDefinition:
    path = Path(file_path).expanduser().resolve()
    if not path.exists():
        raise WorkflowLoadError(f"未找到 workflow 文件: {path}")

    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise WorkflowLoadError(f"workflow YAML 解析失败: {exc}") from exc

    if not isinstance(payload, dict):
        raise WorkflowLoadError("workflow 文件顶层必须是 object")

    try:
        return WorkflowDefinition.model_validate(payload)
    except Exception as exc:
        raise WorkflowLoadError(f"workflow 校验失败: {exc}") from exc


def parse_workflow_var_overrides(items: list[str] | None) -> dict[str, str]:
    resolved = {}
    for item in items or []:
        if "=" not in str(item):
            raise WorkflowLoadError("workflow 变量覆盖格式必须为 KEY=VALUE")
        key, value = str(item).split("=", 1)
        key = key.strip()
        if not key:
            raise WorkflowLoadError("workflow 变量名不能为空")
        resolved[key] = value
    return resolved


def _render_template(value: str, variables: dict[str, str]) -> str:
    text = str(value)

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in variables:
            raise WorkflowLoadError(f"workflow 引用了未定义变量: {key}")
        return str(variables[key])

    return WORKFLOW_VAR_PATTERN.sub(replace, text)


def resolve_workflow_definition(
    workflow: WorkflowDefinition,
    overrides: dict[str, str] | None = None,
) -> WorkflowDefinition:
    variables = {key: str(value) for key, value in workflow.vars.items()}
    variables.update({key: str(value) for key, value in (overrides or {}).items()})

    resolved_steps = []
    for step in workflow.steps:
        resolved_steps.append(
            WorkflowStep.model_validate(
                {
                    "name": _render_template(step.name, variables),
                    "action": step.action,
                    "locator_type": _render_template(step.locator_type, variables),
                    "locator_value": _render_template(step.locator_value, variables),
                    "extra_value": _render_template(step.extra_value, variables),
                    "enabled": step.enabled,
                }
            )
        )

    return WorkflowDefinition.model_validate(
        {
            "version": workflow.version,
            "name": _render_template(workflow.name, variables),
            "platform": _render_template(workflow.platform, variables),
            "env": _render_template(workflow.env, variables),
            "vars": variables,
            "steps": [step.model_dump() for step in resolved_steps],
        }
    )
