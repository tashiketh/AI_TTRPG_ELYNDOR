# game_config.py
import copy
import json
import logging
from pathlib import Path
from typing import Any, Optional


logger = logging.getLogger("GameConfig")


class GameConfig:
    """Load root game_config.json with safe defaults for missing or invalid values."""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = Path(config_path) if config_path else Path(__file__).resolve().parent.parent / "game_config.json"
        self._data = self._load()

    def _load(self) -> dict:
        try:
            if self.config_path.exists():
                loaded = json.loads(self.config_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    return loaded
        except Exception as e:
            logger.warning(f"Could not load game config from {self.config_path}: {e}")
        return {}

    def reload(self):
        """Reload config from disk for tests or long-running tools."""
        self._data = self._load()

    def _lookup_node(self, dotted_path: str) -> Any:
        node: Any = self._data
        for part in str(dotted_path or "").split("."):
            if not isinstance(node, dict) or part not in node:
                return None
            node = node[part]
        return node

    def get(self, dotted_path: str, default: Any = None) -> Any:
        """Return a setting value, supporting metadata objects with value/default keys."""
        node = self._lookup_node(dotted_path)
        if node is None:
            return default
        if isinstance(node, dict) and "value" in node:
            return node.get("value", node.get("default", default))
        return node

    def int(self, dotted_path: str, default: int, min_value: Optional[int] = None,
            max_value: Optional[int] = None) -> int:
        """Return a validated integer setting."""
        try:
            value = int(float(self.get(dotted_path, default)))
        except (TypeError, ValueError):
            value = int(default)
        if min_value is not None:
            value = max(min_value, value)
        if max_value is not None:
            value = min(max_value, value)
        return value

    def float(self, dotted_path: str, default: float, min_value: Optional[float] = None,
              max_value: Optional[float] = None) -> float:
        """Return a validated float setting."""
        try:
            value = float(self.get(dotted_path, default))
        except (TypeError, ValueError):
            value = float(default)
        if min_value is not None:
            value = max(min_value, value)
        if max_value is not None:
            value = min(max_value, value)
        return value

    def metadata(self, dotted_path: str) -> dict:
        """Return a copy of a setting metadata object for UI/debugging."""
        node = self._lookup_node(dotted_path)
        if isinstance(node, dict):
            return copy.deepcopy(node)
        return {}


game_config = GameConfig()
