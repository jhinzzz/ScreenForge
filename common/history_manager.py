from datetime import datetime
from typing import Dict, List, Optional

from common.logs import log


class StepHistoryManager:
    def __init__(self, max_history: int = 50, initial_content: Optional[List[str]] = None):
        self._history: List[Dict] = []
        self._initial_content: List[str] = initial_content.copy() if initial_content else []
        self._current_file_content: List[str] = self._initial_content.copy()
        self._max_history: int = max_history

    def add_step(self, code_content: List[str], action_description: str) -> None:
        """记录一步历史，包括代码内容、时间戳和动作描述"""
        log.debug(f"[HistoryManager] 添加前 - 代码行数: {len(code_content)}, 动作: {action_description}")
        log.debug(f"[HistoryManager] 添加前 - 当前文件内容行数: {len(self._current_file_content)}, 历史记录数: {len(self._history)}")

        # 计算添加后的新状态
        new_file_state = self._current_file_content.copy()
        new_file_state.extend(code_content)

        timestamp = datetime.now().isoformat()
        record = {
            "timestamp": timestamp,
            "action_description": action_description,
            "code_content": code_content.copy(),
            "file_state": new_file_state
        }
        self._history.append(record)
        self._current_file_content = new_file_state
        self._trim_history()

        log.debug(f"[HistoryManager] 添加后 - 当前文件内容行数: {len(self._current_file_content)}, 历史记录数: {len(self._history)}")

    def _trim_history(self) -> None:
        """限制历史记录不超过最大值"""
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    def rollback(self) -> bool:
        """回退一步历史，返回是否成功回退"""
        if not self._history:
            return False
        log.debug(f"[HistoryManager] 回退前 - 历史记录数: {len(self._history)}, 当前文件内容行数: {len(self._current_file_content)}")

        self._history.pop()

        if self._history:
            self._current_file_content = self._history[-1]["file_state"].copy()
            log.debug(f"[HistoryManager] 回退后 - 当前文件内容行数: {len(self._current_file_content)}")
        else:
            self._current_file_content = self._initial_content.copy()
            log.debug(f"[HistoryManager] 回退后 - 当前文件内容行数: {len(self._current_file_content)}")

        return True

    def set_initial_content(self, initial_content: List[str]) -> None:
        """设置初始内容"""
        self._initial_content = initial_content.copy()
        if not self._history:
            self._current_file_content = self._initial_content.copy()

    def clear_history(self) -> None:
        """清除所有历史记录"""
        self._history = []
        self._current_file_content = self._initial_content.copy()

    def get_current_file_content(self) -> List[str]:
        """获取当前文件内容"""
        return self._current_file_content.copy()

    def get_history(self) -> List[Dict]:
        """获取完整历史记录"""
        return self._history.copy()

    def get_history_count(self) -> int:
        """获取历史记录数量"""
        return len(self._history)

    def get_last_step(self) -> Optional[Dict]:
        """获取最后一步的信息，包括时间戳、动作描述等"""
        if not self._history:
            return None
        return self._history[-1].copy()
