# map_tools.py
import json
import os
import glob
import shutil
from datetime import datetime
from typing import Dict, Any, List
from path_config import path_config
from game_config import game_config

# ── Paths ──────────────────────────────────────────────────────────────────────
GAME_STATE_PATH = path_config.game_state_path
MAP_PATH = path_config.combat_map_path
BACKUP_DIR = path_config.backup_dir

GRID_SCALE_METERS = game_config.float("map.grid_scale_meters", 1, min_value=0.1)
DEFAULT_MAP_WIDTH = game_config.int("map.default_width", 10, min_value=1)
DEFAULT_MAP_HEIGHT = game_config.int("map.default_height", 10, min_value=1)

# ── Helper: atomic backup + save ───────────────────────────────────────────────
def _backup_and_save_map(map_data: Dict):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    if MAP_PATH.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = BACKUP_DIR / f"combat_map_backup_{ts}.json"
        shutil.copy(MAP_PATH, backup_path)

        backups = sorted(
            BACKUP_DIR.glob("combat_map_backup_*.json"),
            key=os.path.getmtime,
            reverse=True
        )
        for old in backups[5:]:
            old.unlink()

    with open(MAP_PATH, "w", encoding="utf-8") as f:
        json.dump(map_data, f, indent=2)


def _load_map() -> Dict:
    if MAP_PATH.exists():
        try:
            with open(MAP_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"active": False, "width": 0, "height": 0, "grid": [], "entities": {}, "metadata": {}}


def _save_map(map_data: Dict):
    map_data["last_updated"] = datetime.now().isoformat()
    _backup_and_save_map(map_data)


# ── Core functions ─────────────────────────────────────────────────────────────
def initialize_combat_map(
    width: int = DEFAULT_MAP_WIDTH,
    height: int = DEFAULT_MAP_HEIGHT,
    terrain: str = ".",
    metadata: Dict = None
) -> Dict:
    metadata = metadata or {}
    grid = [[terrain for _ in range(width)] for _ in range(height)]

    map_data = {
        "active": True,
        "width": width,
        "height": height,
        "grid": grid,
        "entities": {},
        "metadata": {**metadata, "grid_scale_meters": GRID_SCALE_METERS}
    }

    _save_map(map_data)
    return {
        "success": True,
        "message": f"Initialized {width}×{height} combat map (1m per cell)",
        "map_state": map_data,
        "map_grid": _render_map_grid(map_data),
        "legend": _render_legend(map_data)
    }


def add_entity(
    entity_id: str,
    pos: List[int],
    display_name: str,
    symbol: str = None,
    team: str = "enemy"
) -> Dict:
    map_data = _load_map()
    if not map_data["active"]:
        return {"success": False, "message": "No active combat map"}

    x, y = pos
    if not (0 <= x < map_data["width"] and 0 <= y < map_data["height"]):
        return {"success": False, "message": "Position out of bounds"}

    if symbol is None or len(symbol) != 2:
        prefix = {"player": "P", "ally": "A", "enemy": "E", "neutral": "N"}.get(team, "X")
        existing = [e["symbol"] for e in map_data["entities"].values() if e["symbol"].startswith(prefix)]
        num = 1
        while f"{prefix}{num}" in existing or f"{prefix} {num}" in existing:
            num += 1
        symbol = f"{prefix}{num}" if prefix != "P" else "P "

    map_data["entities"][entity_id] = {
        "symbol": symbol,
        "pos": pos,
        "display_name": display_name,
        "team": team
    }

    _save_map(map_data)
    return {
        "success": True,
        "message": f"Added {display_name} ({symbol}) at {pos}",
        "map_state": map_data,
        "map_grid": _render_map_grid(map_data),
        "legend": _render_legend(map_data)
    }


def move_entity(entity_id: str, new_pos: List[int]) -> Dict:
    map_data = _load_map()
    if not map_data["active"] or entity_id not in map_data["entities"]:
        return {"success": False, "message": "Invalid map or entity"}

    x, y = new_pos
    if not (0 <= x < map_data["width"] and 0 <= y < map_data["height"]):
        return {"success": False, "message": "Position out of bounds"}

    for eid, data in map_data["entities"].items():
        if eid != entity_id and data["pos"] == new_pos:
            return {"success": False, "message": "Tile occupied"}

    map_data["entities"][entity_id]["pos"] = new_pos
    _save_map(map_data)

    return {
        "success": True,
        "message": f"{entity_id} moved to {new_pos}",
        "map_state": map_data,
        "map_grid": _render_map_grid(map_data),
        "legend": _render_legend(map_data)
    }

def get_current_map_data() -> Dict:
    """Helper to get raw map data (used by combat_tools)."""
    return _load_map()


def get_distance_meters(entity1_id: str, entity2_id: str = None, target_pos: list = None) -> float:
    """Calculate Euclidean distance in meters (with -1 cell adjustment)."""

    map_data = _load_map()
    if not map_data.get("active", False) or "entities" not in map_data:
        return 0.0

    if entity1_id not in map_data["entities"]:
        return 0.0

    pos1 = map_data["entities"][entity1_id]["pos"]

    if target_pos is not None:
        pos2 = target_pos
    elif entity2_id and entity2_id in map_data["entities"]:
        pos2 = map_data["entities"][entity2_id]["pos"]
    else:
        return 0.0

    dx = abs(pos1[0] - pos2[0])
    dy = abs(pos1[1] - pos2[1])

    # TRUE EUCLIDEAN DISTANCE
    distance_cells = (dx ** 2 + dy ** 2) ** 0.5
    effective_distance = max(0.0, distance_cells)

    return round(effective_distance * GRID_SCALE_METERS, 2)

def end_combat(sync_to_game_state: bool = True) -> Dict:
    map_data = _load_map()
    map_data["active"] = False
    _save_map(map_data)

    return {
        "success": True,
        "message": "Combat ended — map deactivated",
        "map_grid": None,
        "legend": None
    }


def get_current_map(combat_state: Dict = None) -> Dict:
    """Return current map with dead entities marked in the legend."""
    map_data = _load_map()

    if not map_data.get("active", False):
        return {
            "success": True,
            "map_grid": "=== NO ACTIVE COMBAT MAP ===",
            "legend": "(no active map)",
            "active": False
        }

    return {
        "success": True,
        "map_state": map_data,
        "map_grid": _render_map_grid(map_data),
        "legend": _render_legend(map_data, combat_state),   # ← Pass combat_state
        "active": True
    }


# ── Renderers (unchanged) ─────────────────────────────────────────────────────
def _render_map_grid(map_data: Dict) -> str:
    if not map_data.get("active", False):
        return "=== NO ACTIVE COMBAT MAP ==="

    grid = map_data["grid"]
    entities = map_data["entities"]
    height = map_data["height"]
    width = map_data["width"]

    display = [["  " for _ in range(width)] for _ in range(height)]

    # Fill terrain
    for y in range(height):
        for x in range(width):
            terrain = grid[y][x]
            display[y][x] = (terrain + " ")[:2]

    # Place entities (dead ones get special handling in legend)
    for eid, data in entities.items():
        x, y = data["pos"]
        display[y][x] = data["symbol"]

    # Build grid with axis labels
    lines = []

    # Top X-axis labels
    x_labels = "   " + " ".join(f"{x:2}" for x in range(width))
    lines.append(x_labels)

    for y in range(height):
        row = [f"{y:2}"] + [" ".join(display[y])]
        lines.append(" ".join(row))

    # Bottom X-axis labels (optional, for clarity)
    lines.append(x_labels)

    return "\n".join(lines)

def _render_legend(map_data: Dict, combat_state: Dict = None) -> str:
    if not map_data.get("active", False) or not map_data.get("entities"):
        return "(no entities on map)"

    lines = []
    for eid, data in sorted(map_data["entities"].items(), key=lambda i: i[1]["symbol"]):
        display_name = data["display_name"]
        symbol = data["symbol"]

        is_dead = False
        if combat_state and "participants" in combat_state:
            participant = combat_state["participants"].get(eid)
            if participant and participant.get("hp", 1) <= 0:
                is_dead = True

        if is_dead:
            line = f"{symbol} = {display_name} (dead)"
        else:
            line = f"{symbol} = {display_name}"

        lines.append(line)

    return "\n".join(lines)


# ── Dispatcher (unchanged) ────────────────────────────────────────────────────
def execute_map_command(command: Dict) -> Dict:
    action = command.get("action", "").lower().strip()

    if action == "initialize":
        return initialize_combat_map(
            width=command.get("width", DEFAULT_MAP_WIDTH),
            height=command.get("height", DEFAULT_MAP_HEIGHT),
            terrain=command.get("terrain", "."),
            metadata=command.get("metadata", {})
        )
    elif action == "add_entity":
        return add_entity(
            entity_id=command["entity"],
            pos=command["pos"],
            display_name=command["display_name"],
            symbol=command.get("symbol"),
            team=command.get("team", "enemy")
        )
    elif action == "move":
        return move_entity(command["entity"], command["to"])
    elif action == "end_combat":
        return end_combat()
    else:
        return {"success": False, "message": f"Unknown map action: {action}"}
