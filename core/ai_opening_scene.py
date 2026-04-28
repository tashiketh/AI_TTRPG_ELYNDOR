#!/usr/bin/env python3
"""Load the first playable scene from reference data."""

import json
from copy import deepcopy
from typing import Any, Dict, List

from path_config import path_config


OPENING_SCENE_FILE_NAME = "opening_scene.json"


def _opening_scene_path():
    return path_config.references_dir / OPENING_SCENE_FILE_NAME


def load_opening_scene_config() -> Dict[str, Any]:
    """Load the active world's opening-scene reference file."""
    path = _opening_scene_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Missing opening scene reference file: {path}. "
            "Create references/opening_scene.json for the active world."
        ) from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in opening scene reference file: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Opening scene reference must be a JSON object: {path}")
    return data


def _get_required_text(data: Dict[str, Any], section: str, key: str) -> str:
    value = data.get(section, {}).get(key) if isinstance(data.get(section), dict) else None
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"references/{OPENING_SCENE_FILE_NAME} is missing {section}.{key}")
    return text


def get_opening_scene_title() -> str:
    """Return the active world's opening-scene title."""
    data = load_opening_scene_config()
    return _get_required_text(data, "opening_scene", "title")


def get_opening_scene_text() -> str:
    """Return the active world's opening scene."""
    data = load_opening_scene_config()
    return _get_required_text(data, "opening_scene", "text")


def get_character_creation_text() -> str:
    """Return the active world's character-creation introduction."""
    data = load_opening_scene_config()
    return _get_required_text(data, "character_creation", "text")


def get_opening_scene_status() -> str:
    """Return the initial status for the opening scene."""
    data = load_opening_scene_config()
    scene = data.get("opening_scene", {}) if isinstance(data.get("opening_scene"), dict) else {}
    return str(scene.get("status") or "awaiting_player_response")


def get_opening_scene_source() -> str:
    """Return a display/debug source for the active opening-scene data."""
    data = load_opening_scene_config()
    return str(data.get("source") or f"references/{OPENING_SCENE_FILE_NAME}")


def get_opening_campaign_summary() -> str:
    """Return the initial campaign summary for the active world."""
    data = load_opening_scene_config()
    return str(data.get("campaign_summary") or "Game has just begun.").strip()


def get_opening_scene_facts() -> List[str]:
    """Return durable opening-scene facts for the game state."""
    data = load_opening_scene_config()
    facts = data.get("scene_facts", [])
    if isinstance(facts, str):
        facts = [facts]
    if not isinstance(facts, list):
        raise ValueError(f"references/{OPENING_SCENE_FILE_NAME} scene_facts must be a list")
    return [" ".join(str(fact).split()).strip() for fact in facts if str(fact).strip()]


def get_opening_world_state() -> Dict[str, Any]:
    """Return starting world/location data from the active world reference."""
    data = load_opening_scene_config()
    world = data.get("world", {})
    return deepcopy(world) if isinstance(world, dict) else {}


def show_opening_scene():
    """Display the dramatic opening scene."""
    title = get_opening_scene_title().upper()
    print(f"""
============================================================
              {title}
============================================================

{get_opening_scene_text()}
""")
