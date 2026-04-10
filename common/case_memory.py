import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

import config.config as config
from common.logs import log


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _normalize_text(value: str) -> str:
    return str(value or "").strip()


def _slugify(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", _normalize_text(value)).strip("-")
    return text.lower() or "memory"


def _build_memory_id(
    platform: str,
    control_kind: str,
    control_label: str,
    source_ref: str,
) -> str:
    identity_seed = f"{platform}|{control_kind}|{control_label}|{source_ref}"
    digest = hashlib.sha1(identity_seed.encode("utf-8")).hexdigest()[:10]
    human_label = _slugify(source_ref or control_label)[:48]
    return f"{platform}:{control_kind}:{human_label}:{digest}"


def _merge_unique_strings(existing: list[str], incoming: list[str]) -> list[str]:
    merged = []
    seen = set()
    for item in [*existing, *incoming]:
        normalized = _normalize_text(item)
        if not normalized or normalized in seen:
            continue
        merged.append(normalized)
        seen.add(normalized)
    return merged


def _merge_locator_hints(
    existing: list["LocatorHint"],
    incoming: list["LocatorHint"],
) -> list["LocatorHint"]:
    merged: list["LocatorHint"] = []
    seen = set()
    for item in [*existing, *incoming]:
        key = (
            _normalize_text(item.action),
            _normalize_text(item.locator_type),
            _normalize_text(item.locator_value),
        )
        if not all(key) or key in seen:
            continue
        merged.append(
            LocatorHint(
                action=key[0],
                locator_type=key[1],
                locator_value=key[2],
            )
        )
        seen.add(key)
    return merged


class LocatorHint(BaseModel):
    action: str = ""
    locator_type: str = ""
    locator_value: str = ""


class CaseMemoryEntry(BaseModel):
    memory_id: str
    platform: str
    control_kind: str
    control_label: str
    source_ref: str = ""
    success_count: int = 0
    failure_count: int = 0
    last_status: str = ""
    last_run_id: str = ""
    last_used_at: str = ""
    successful_actions: list[str] = Field(default_factory=list)
    locator_hints: list[LocatorHint] = Field(default_factory=list)
    pytest_asset: dict[str, Any] = Field(default_factory=dict)
    recommended_next_step: dict[str, Any] | None = None


class CaseMemoryDocument(BaseModel):
    version: int = 1
    updated_at: str = ""
    entries: list[CaseMemoryEntry] = Field(default_factory=list)


def _collect_successful_actions(step_records: list[dict[str, Any]]) -> list[str]:
    return [
        _normalize_text(item.get("action_description", ""))
        for item in step_records
        if item.get("event") == "action_executed"
        and item.get("success") is True
        and _normalize_text(item.get("action_description", ""))
    ]


def _collect_locator_hints(
    summary: dict[str, Any],
    step_records: list[dict[str, Any]],
) -> list[LocatorHint]:
    hints: list[LocatorHint] = []
    control_summary = summary.get("control_summary", {}) or {}
    tuples_seen = set()

    def _append_hint(action: str, locator_type: str, locator_value: str) -> None:
        normalized_action = _normalize_text(action)
        normalized_type = _normalize_text(locator_type)
        normalized_value = _normalize_text(locator_value)
        if (
            not normalized_action
            or not normalized_type
            or normalized_type.lower() == "global"
            or not normalized_value
            or normalized_value.lower() == "global"
        ):
            return
        key = (normalized_action, normalized_type, normalized_value)
        if key in tuples_seen:
            return
        tuples_seen.add(key)
        hints.append(
            LocatorHint(
                action=normalized_action,
                locator_type=normalized_type,
                locator_value=normalized_value,
            )
        )

    _append_hint(
        control_summary.get("action", ""),
        control_summary.get("locator_type", ""),
        control_summary.get("locator_value", ""),
    )

    for item in step_records:
        _append_hint(
            item.get("action", ""),
            item.get("locator_type", ""),
            item.get("locator_value", ""),
        )

    return hints


class CaseMemoryStore:
    def __init__(self, file_path: str | Path | None = None):
        self._file_path = Path(file_path or config.CASE_MEMORY_PATH).expanduser()

    @property
    def file_path(self) -> Path:
        return self._file_path

    def load_document(self) -> CaseMemoryDocument:
        if not self._file_path.exists():
            return CaseMemoryDocument(updated_at=_now_iso())

        try:
            payload = json.loads(self._file_path.read_text(encoding="utf-8"))
            return CaseMemoryDocument.model_validate(payload)
        except Exception as e:
            log.warning(f"⚠️ [Warning] 读取 case memory 失败，已降级为空文档: {e}")
            return CaseMemoryDocument(updated_at=_now_iso())

    def save_document(self, document: CaseMemoryDocument) -> None:
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._file_path.with_suffix(self._file_path.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(document.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(self._file_path)

    def query_entries(
        self,
        platform: str = "",
        control_kind: str = "",
        query: str = "",
        source_ref: str = "",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        document = self.load_document()
        normalized_platform = _normalize_text(platform).lower()
        normalized_kind = _normalize_text(control_kind).lower()
        normalized_query = _normalize_text(query).lower()
        normalized_source_ref = _normalize_text(source_ref)
        limit = max(1, int(limit or 20))

        matched_entries = []
        for entry in document.entries:
            if normalized_platform and entry.platform.lower() != normalized_platform:
                continue
            if normalized_kind and entry.control_kind.lower() != normalized_kind:
                continue
            if normalized_source_ref and entry.source_ref != normalized_source_ref:
                continue
            if normalized_query:
                haystacks = [
                    entry.control_label.lower(),
                    entry.source_ref.lower(),
                    " ".join(entry.successful_actions).lower(),
                ]
                if not any(normalized_query in haystack for haystack in haystacks):
                    continue
            matched_entries.append(entry.model_dump())

        matched_entries.sort(
            key=lambda item: (
                item.get("last_used_at", ""),
                item.get("success_count", 0),
            ),
            reverse=True,
        )
        return matched_entries[:limit]

    def find_entry(
        self,
        platform: str,
        control_kind: str,
        control_label: str,
        source_ref: str = "",
    ) -> dict[str, Any] | None:
        normalized_platform = _normalize_text(platform).lower()
        normalized_kind = _normalize_text(control_kind).lower()
        normalized_label = _normalize_text(control_label)
        normalized_source_ref = _normalize_text(source_ref)
        document = self.load_document()

        for entry in document.entries:
            if entry.platform.lower() != normalized_platform:
                continue
            if entry.control_kind.lower() != normalized_kind:
                continue
            if normalized_source_ref and entry.source_ref == normalized_source_ref:
                return entry.model_dump()
            if normalized_label and entry.control_label == normalized_label:
                return entry.model_dump()
        return None

    def upsert_from_run(
        self,
        summary: dict[str, Any],
        step_records: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if _normalize_text(summary.get("execution_mode", "")) != "run":
            return None

        control_summary = summary.get("control_summary", {}) or {}
        control_kind = _normalize_text(control_summary.get("control_kind", ""))
        if not control_kind or control_kind == "doctor":
            return None

        platform = _normalize_text(summary.get("platform", ""))
        control_label = _normalize_text(control_summary.get("control_label", "")) or _normalize_text(
            summary.get("goal", "")
        )
        source_ref = _normalize_text(control_summary.get("source_ref", ""))
        if not platform or not control_label:
            return None

        document = self.load_document()
        existing_entry = None
        for entry in document.entries:
            if entry.platform != platform or entry.control_kind != control_kind:
                continue
            if source_ref and entry.source_ref == source_ref:
                existing_entry = entry
                break
            if entry.control_label == control_label:
                existing_entry = entry
                break

        if existing_entry is None:
            existing_entry = CaseMemoryEntry(
                memory_id=_build_memory_id(
                    platform=platform,
                    control_kind=control_kind,
                    control_label=control_label,
                    source_ref=source_ref,
                ),
                platform=platform,
                control_kind=control_kind,
                control_label=control_label,
                source_ref=source_ref,
            )
            document.entries.append(existing_entry)

        status = _normalize_text(summary.get("status", ""))
        if status == "success":
            existing_entry.success_count += 1
        else:
            existing_entry.failure_count += 1

        existing_entry.last_status = status
        existing_entry.last_run_id = _normalize_text(summary.get("run_id", ""))
        existing_entry.last_used_at = _normalize_text(summary.get("finished_at", "")) or _now_iso()
        existing_entry.successful_actions = _merge_unique_strings(
            existing_entry.successful_actions,
            _collect_successful_actions(step_records),
        )
        existing_entry.locator_hints = _merge_locator_hints(
            existing_entry.locator_hints,
            _collect_locator_hints(summary, step_records),
        )
        existing_entry.pytest_asset = dict(summary.get("pytest_asset", {}) or {})
        existing_entry.recommended_next_step = dict(summary.get("failure_analysis", {}) or {}) or None

        document.updated_at = existing_entry.last_used_at
        self.save_document(document)
        return existing_entry.model_dump()
