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
        log.debug(f"[HistoryManager] Before add - code lines: {len(code_content)}, action: {action_description}")
        log.debug(f"[HistoryManager] Before add - file lines: {len(self._current_file_content)}, history count: {len(self._history)}")

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

        log.debug(f"[HistoryManager] After add - file lines: {len(self._current_file_content)}, history count: {len(self._history)}")

    def _trim_history(self) -> None:
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    def rollback(self) -> bool:
        if not self._history:
            return False
        log.debug(f"[HistoryManager] Before rollback - history: {len(self._history)}, file lines: {len(self._current_file_content)}")

        self._history.pop()

        if self._history:
            self._current_file_content = self._history[-1]["file_state"].copy()
            log.debug(f"[HistoryManager] After rollback - file lines: {len(self._current_file_content)}")
        else:
            self._current_file_content = self._initial_content.copy()
            log.debug(f"[HistoryManager] After rollback - file lines: {len(self._current_file_content)}")

        return True

    def set_initial_content(self, initial_content: List[str]) -> None:
        self._initial_content = initial_content.copy()
        if not self._history:
            self._current_file_content = self._initial_content.copy()

    def clear_history(self) -> None:
        self._history = []
        self._current_file_content = self._initial_content.copy()

    def get_current_file_content(self) -> List[str]:
        return self._current_file_content.copy()

    def get_history(self) -> List[Dict]:
        return self._history.copy()

    def get_history_count(self) -> int:
        return len(self._history)

    def get_last_step(self) -> Optional[Dict]:
        if not self._history:
            return None
        return self._history[-1].copy()
