import json
import os
import random
import shutil
import glob
from math import sqrt, log, exp
from datetime import datetime
from idlelib.help import copy_strip
from typing import Dict, List, Any
from helper_functions import roll_generic_check

# ── Paths ──────────────────────────────────────────────────────────────────────
from path_config import path_config

GAME_STATE_PATH = path_config.game_state_path
CRAFTING_PATH   = path_config.crafting_path          # your materials/quality file
BACKUP_DIR      = path_config.backup_dir
MAGIC_PATH      = path_config.magic_path
SPELL_LIBRARY_PATH = path_config.references_dir / "spell_library.json"

# ── Global caches (loaded once on import) ──────────────────────────────────────
MATERIAL_MODS: Dict[str, Dict] = {}
QUALITY_MODS: Dict[str, Dict] = {}

def _load_craft_modifiers():
    global MATERIAL_MODS, QUALITY_MODS
    try:
        with open(CRAFTING_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            craft = data["craft"]  # <-- new

        MATERIAL_MODS.clear()
        QUALITY_MODS.clear()

        for key, val in craft.items():
            if key in ["botched", "poor", "standard", "fine", "masterwork"]:
                QUALITY_MODS[key] = val
            else:
                MATERIAL_MODS[key] = val

    except Exception as e:
        print(f"[craft] Failed to load craft.json: {e}")
        # Set safe defaults so code doesn't crash
        MATERIAL_MODS["iron"] = {"damage_adjust": 1.0, "speed_adjust": 1.0, "price_adjust": 1.0, "AC_adjust": 1.0, "weight_adjust": 1.0, "dc_adjust": 0}
        QUALITY_MODS["standard"] = {"damage_adjust": 1.0, "speed_adjust": 1.0, "price_adjust": 1.0, "AC_adjust": 1.0}

# Load automatically when this module is imported
_load_craft_modifiers()

def _backup_and_save(state: Dict):
    """Create backup then overwrite game state file."""
    if os.path.exists(GAME_STATE_PATH):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(BACKUP_DIR, f"state_backup_{ts}.json")
        shutil.copy(GAME_STATE_PATH, backup_path)

        # Keep only 5 newest backups
        backups = sorted(glob.glob(os.path.join(BACKUP_DIR, "state_backup_*.json")),
                         key=os.path.getmtime, reverse=True)
        for old in backups[5:]:
            os.remove(old)

    with open(GAME_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=4)

def craft_item(
    archetype_key: str,
    desired_materials: List[str],
    materials_provided: bool = False,
    tools_quality: str = "none",            # "none", "makeshift", "proper", "high_quality"
    skill_used: str = "smithing",
    stats_used: List[str] = None,
    situational_bonus: float = 0.0,
    entity_id: str = "player"
) -> Dict:
    """
    Crafts an item using the given archetype, materials, and tools.
    Returns dict with success status, message, item_id(s), and details.
    """
    # ── Load templates and state ───────────────────────────────────────────────
    try:
        with open(CRAFTING_PATH, "r", encoding="utf-8") as f:
            inv = json.load(f)
        items = inv["items"]
        archetype = items.get(archetype_key.lower())
        if not archetype:
            return {"success": False, "message": f"Archetype '{archetype_key}' not found"}

        with open(GAME_STATE_PATH, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception as e:
        return {"success": False, "message": f"Load failed: {str(e)}"}

    player = state["player"]
    inventory = player.setdefault("inventory", {})

    # ── Early tool check ────────────────────────────────────────────────────────
    if tools_quality == "none":
        return {"success": False, "message": "No suitable tools available — crafting cannot begin"}

    # ── Infer stats if missing ──────────────────────────────────────────────────
    if not stats_used:
        if skill_used in ["smithing", "woodworking"]:
            stats_used = ["Crea", "Str"]
        elif skill_used == "alchemy":
            stats_used = ["Crea", "Ins"]
        else:
            stats_used = ["Crea"]

    # ── Calculate base requirements ─────────────────────────────────────────────
    base_weight = archetype.get("weight", 0.1)
    is_alchemy = skill_used == "alchemy"

    if is_alchemy:
        waste_factor = 0.20
        time_hours = 6.0
    else:
        waste_factor = 1.20 if tools_quality != "high_quality" else 1.10
        time_hours = 2.0 + (base_weight * waste_factor * 3.0)  # setup + 3 h/kg

    required_weight = base_weight * waste_factor

    # ── Check / deduct materials ────────────────────────────────────────────────
    if not materials_provided:
        available_weight = 0.0
        for item in inventory.values():
            if any(m in item.get("tags", []) for m in desired_materials):
                available_weight += item.get("qty", 1) * item.get("weight", 0)

        if available_weight < required_weight:
            return {"success": False, "message": f"Insufficient materials — need ~{required_weight:.2f} kg"}

        # Deduct (simple: from largest stacks first)
        to_deduct = required_weight
        for item_id, item in list(inventory.items()):
            if any(m in item.get("tags", []) for m in desired_materials):
                qty = item.get("qty", 1)
                unit_w = item.get("weight", 0)
                deduct_qty = min(qty, to_deduct / unit_w if unit_w > 0 else 0)
                item["qty"] = max(0, qty - deduct_qty)
                to_deduct -= deduct_qty * unit_w
                if item["qty"] <= 0:
                    del inventory[item_id]
                if to_deduct <= 0.001:
                    break

    # ── Apply tools_quality adjustments ─────────────────────────────────────────
    dc_adjust = 0
    margin_bonus = 0
    quality_cap = None

    if tools_quality == "makeshift":
        dc_adjust = 5
        quality_cap = "standard"
    elif tools_quality == "high_quality":
        dc_adjust = -5
        margin_bonus = 10

    # Base DC (example scaling)
    dc = 50 + int(time_hours // 2) + dc_adjust

    # ── Perform check ───────────────────────────────────────────────────────────
    check_result = roll_generic_check(
        entity_id=entity_id,
        stats_used=stats_used,
        skill_used=skill_used,
        difficulty_class=dc,
        situational_bonus=situational_bonus
    )

    if not check_result["success"]:
        return {"success": False, "message": "Crafting failed", "details": check_result}

    margin = check_result["margin"] + margin_bonus

    # ── Determine quality ───────────────────────────────────────────────────────
    if margin < 5:
        quality = "botched"
    elif margin < 10:
        quality = "poor"
    elif margin < 25:
        quality = "standard"
    elif margin < 35:
        quality = "fine"
    else:
        quality = "masterwork"

    if quality_cap and quality not in ["poor", "standard"]:
        quality = "standard"

    # ── Apply modifiers from craft.json ─────────────────────────────────────────
    # Assume one primary material for simplicity; extend to multi if needed
    primary_mat = desired_materials[0] if desired_materials else "iron"
    mat_mod = MATERIAL_MODS.get(primary_mat, {
        "damage_adjust": 1.0, "speed_adjust": 1.0,
        "price_adjust": 1.0, "AC_adjust": 1.0,
        "weight_adjust": 1.0, "dc_adjust": 0
    })

    qual_mod = QUALITY_MODS.get(quality, {
        "damage_adjust": 1.0, "speed_adjust": 1.0,
        "price_adjust": 1.0, "AC_adjust": 1.0
    })

    # Final values
    final_damage = archetype.get("damage", 0) * mat_mod["damage_adjust"] * qual_mod["damage_adjust"]
    final_speed  = archetype.get("speed", 1.0) * mat_mod["speed_adjust"] * qual_mod["speed_adjust"]
    final_price  = archetype.get("price", 0) * mat_mod["price_adjust"] * qual_mod["price_adjust"]
    final_ac     = archetype.get("AC", 0) * mat_mod["AC_adjust"] * qual_mod["AC_adjust"]
    final_weight = archetype.get("weight", 0.1) * mat_mod.get("weight_adjust", 1.0)

    # ── Create item instance ────────────────────────────────────────────────────
    item_id = f"{archetype_key.lower().replace(' ', '_')}_{random.randint(1000,9999)}"

    new_item = {
        "archetype": archetype_key,
        "tags": archetype.get("tags", []) + [quality] + desired_materials,
        "damage": final_damage,
        "speed": final_speed,
        "price": final_price,
        "weight": final_weight,
        "AC": final_ac if final_ac else None,
        "description": f"{quality.capitalize()} {primary_mat} {archetype_key}",
        "location": None,
        "qty": 1
    }

    inventory[item_id] = new_item

    # ── Save with backup ────────────────────────────────────────────────────────
    _backup_and_save(state)

    return {
        "success": True,
        "message": f"Crafted {quality} {archetype_key}",
        "item_id": item_id,
        "details": new_item
    }

def add_found_or_purchased_item(
        archetype_key: str = None,  # optional: use template from items.json
        item_data: Dict = None,  # optional: full custom item dict (overrides template)
        qty: int = 1,
        quality: str = "standard",  # "standard", "fine", "poor", etc.
        materials: List[str] = None,  # optional: e.g. ["steel", "leather"]
        location: str = None,  # optional: "backpack_001" or null
        entity_id: str = "player",
        game_state_path: str = GAME_STATE_PATH
) -> Dict:
    """
    Adds a new item instance to inventory (from template or custom data).

    Returns: {"success": bool, "message": str, "item_id": str}
    """
    if not archetype_key and not item_data:
        return {"success": False, "message": "Must provide either archetype_key or item_data"}

    try:
        with open(game_state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception as e:
        return {"success": False, "message": f"Cannot load game state: {str(e)}"}

    player = state["player"]
    inventory = player.setdefault("inventory", {})

    # ── Get base data ───────────────────────────────────────────────────────────
    if archetype_key:
        try:
            with open(CRAFTING_PATH, "r", encoding="utf-8") as f:
                inv = json.load(f)
            templates = inv["items"]
            base = templates.get(archetype_key.lower())
            if not base:
                return {"success": False, "message": f"Archetype '{archetype_key}' not found"}
        except Exception as e:
            return {"success": False, "message": f"Cannot load items.json: {str(e)}"}
    else:
        base = {}  # fully custom

    # Merge with any overrides from item_data
    item = base.copy()
    if item_data:
        item.update(item_data)

    # Apply quality/materials if provided
    if quality and quality != "standard":
        item["tags"] = item.get("tags", []) + [quality]
        item["description"] = f"{quality.capitalize()} {item.get('description', archetype_key or 'item')}"

    if materials:
        item["tags"] = item.get("tags", []) + materials
        item["description"] = f"{' '.join(materials)} {item.get('description', archetype_key or 'item')}"

    # ── Generate unique ID ──────────────────────────────────────────────────────
    prefix = archetype_key.lower().replace(" ", "_") if archetype_key else "custom"
    item_id = f"{prefix}_{random.randint(10000, 99999)}"

    # Set defaults & final values
    item.setdefault("qty", qty)
    item.setdefault("location", location)
    item.setdefault("archetype", archetype_key)
    item.setdefault("quality", quality)

    # Add to inventory
    inventory[item_id] = item

    # Save with backup
    _backup_and_save(state)

    return {
        "success": True,
        "message": f"Added {qty}x {quality} {archetype_key or 'custom item'} to inventory",
        "item_id": item_id,
        "details": item
    }

DEFAULT_SPELL_TAGS: Dict[str, Dict[str, Any]] = {
    "attack": {"description": "spell is intended to harm a target", "prereqs_all": None},
    "area": {"description": "legacy area tag", "prereqs_all": None},
    "detection": {"description": "legacy detection tag", "prereqs_all": None},
    "life-signs": {"description": "legacy life detection tag", "prereqs_all": None},
    "mind": {"description": "legacy mental tag", "prereqs_all": None},
    "non-lethal": {"description": "legacy nonlethal tag", "prereqs_all": None},
    "single-target": {"description": "legacy single target tag", "prereqs_all": None},
    "weapon": {"description": "spell affects or creates a weapon-like effect", "prereqs_all": None},
}


def _spell_key(spell_name: str) -> str:
    """Normalize a spell name into an inventory key."""
    return str(spell_name or "spell").strip().lower().replace(" ", "_")


def _load_spell_tag_library() -> Dict[str, Dict[str, Any]]:
    """Load spell tags, merging compatibility defaults for existing saves."""
    tag_library = DEFAULT_SPELL_TAGS.copy()
    with open(MAGIC_PATH, "r", encoding="utf-8") as f:
        magic_data = json.load(f)
    tag_library.update(magic_data.get("spell_tags", {}))
    return tag_library


def _get_spell_learned_value(spell: Dict[str, Any]) -> float:
    """Return learned progress as a 0..100 float."""
    if "learned" in spell:
        learned = spell.get("learned")
        if isinstance(learned, bool):
            return 100.0 if learned else 0.0
        try:
            return max(0.0, min(100.0, float(learned)))
        except (TypeError, ValueError):
            return 0.0
    if "learned_progress" in spell:
        try:
            return max(0.0, min(100.0, float(spell.get("learned_progress", 0))))
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def is_spell_learned(spell: Dict[str, Any]) -> bool:
    """A spell is castable only when learned reaches 100."""
    return _get_spell_learned_value(spell) >= 100.0


def normalize_spell_collection(spells: Any) -> Dict[str, Dict[str, Any]]:
    """Normalize old list-based and new dict-based spell inventories."""
    normalized: Dict[str, Dict[str, Any]] = {}
    if isinstance(spells, dict):
        iterator = spells.items()
    elif isinstance(spells, list):
        iterator = []
        for spell in spells:
            if isinstance(spell, dict):
                key = _spell_key(spell.get("name") or spell.get("spell_name"))
                iterator.append((key, spell))
    else:
        return normalized

    for key, spell in iterator:
        if not isinstance(spell, dict):
            continue
        clean_spell = spell.copy()
        clean_spell.setdefault("name", clean_spell.get("spell_name", str(key).replace("_", " ").title()))
        if "base_MP_cost" in clean_spell and "base_mp_cost" not in clean_spell:
            clean_spell["base_mp_cost"] = clean_spell["base_MP_cost"]
        if "MP_cost" not in clean_spell and "base_mp_cost" in clean_spell:
            clean_spell["MP_cost"] = clean_spell["base_mp_cost"]
        clean_spell["learned"] = _get_spell_learned_value(clean_spell)
        clean_spell.pop("learned_progress", None)
        normalized[str(key)] = clean_spell
    return normalized


def calculate_spell_complexity(tags: List[str], mp_cost: float = 0) -> int:
    """Calculate spell complexity from its effect grammar."""
    tag_library = _load_spell_tag_library()
    complexity = 0.0
    for tag in tags:
        tag_data = tag_library.get(tag, {})
        complexity += float(tag_data.get("complexity_weight", 1.0))
    if mp_cost >= 500:
        complexity += 1
    if mp_cost >= 1000:
        complexity += 1
    return max(1, int(round(complexity)))


def _safe_eval_spell_formula(formula: str, variables: Dict[str, Any]) -> float:
    """Evaluate legacy spell formula snippets with a tiny allowlist."""
    safe_builtins = {
        "min": min,
        "max": max,
        "abs": abs,
        "round": round,
        "pow": pow,
        "sqrt": sqrt,
        "log": log,
        "exp": exp,
        "hasattr": hasattr,
    }
    return float(eval(formula, {"__builtins__": safe_builtins}, variables))


def calculate_spell_mp_cost(
    tags: List[str],
    is_attack: bool = False,
    damage: int = None,
    range: Any = None,
    radius: int = None,
    duration_seconds: float = 1.0,
    target_count: int = 1,
    healing: int = None,
    shield_hp: int = None,
    gravity_delta: float = None,
    effect_power: int = None,
) -> Dict[str, Any]:
    """
    Calculate MP cost from tags and effect budget.

    Physical energy uses 1 MP = 1 damage = 100 joules.
    Healing and shield map to HP. Gravity uses 10 * abs(delta_g) * seconds
    where delta_g is the fractional gravity change; values over 1 are treated
    as percentages, so 10 means 10%.
    """
    warnings: List[str] = []
    tag_library = _load_spell_tag_library()
    duration_seconds = max(1.0, float(duration_seconds or 1.0))
    target_count = max(1, int(target_count or 1))

    base_mp_cost = 0.0
    if is_attack:
        base_mp_cost = max(base_mp_cost, float(damage or effect_power or 0))
    if healing is not None:
        base_mp_cost = max(base_mp_cost, float(healing))
    if shield_hp is not None:
        base_mp_cost = max(base_mp_cost, float(shield_hp))
    if gravity_delta is not None or "gravity" in tags:
        delta = abs(float(gravity_delta if gravity_delta is not None else 0.1))
        if delta > 1:
            delta = delta / 100.0
        base_mp_cost = max(base_mp_cost, 10.0 * delta * duration_seconds)

    if base_mp_cost <= 0:
        base_mp_cost = float(effect_power or 100)
        warnings.append(f"Abstract spell: base MP cost set to {base_mp_cost}")

    if "temporal" in tags:
        base_mp_cost *= duration_seconds
        warnings.append("Temporal spell: base MP cost multiplied by seconds")

    if target_count > 1 and "area_of_effect" not in tags:
        base_mp_cost *= target_count

    variables = {
        "base_mp_cost": base_mp_cost,
        "range": range or 0,
        "radius": radius or 0,
        "duration_seconds": duration_seconds,
        "target_count": target_count,
    }
    intrinsic_effect_tags = set()
    if healing is not None:
        intrinsic_effect_tags.add("healing")
    if shield_hp is not None:
        intrinsic_effect_tags.add("shield")
    if gravity_delta is not None or "gravity" in tags:
        intrinsic_effect_tags.add("gravity")
    if "temporal" in tags:
        intrinsic_effect_tags.add("temporal")

    final_cost = base_mp_cost
    final_damage = float(damage or 0)
    for tag_name in tags:
        tag_data = tag_library.get(tag_name, {})
        if tag_data.get("cost_multiplier") is not None:
            final_cost *= float(tag_data["cost_multiplier"])
        if tag_data.get("flat_cost") is not None:
            final_cost += float(tag_data["flat_cost"])
        modifier = tag_data.get("cost_modifier")
        if modifier:
            if tag_name in intrinsic_effect_tags:
                continue
            try:
                final_cost = _safe_eval_spell_formula(f"final_cost {modifier}", {**variables, "final_cost": final_cost})
            except Exception as e:
                warnings.append(f"Skipped invalid cost modifier for tag '{tag_name}': {e}")

        damage_modifier = tag_data.get("damage_modifier")
        if is_attack and damage_modifier:
            try:
                final_damage = _safe_eval_spell_formula(f"final_damage {damage_modifier}", {
                    **variables,
                    "final_damage": final_damage,
                })
            except Exception as e:
                warnings.append(f"Skipped invalid damage modifier for tag '{tag_name}': {e}")

    if is_attack:
        final_cost = max(final_cost, final_damage)

    return {
        "base_mp_cost": round(base_mp_cost, 2),
        "MP_cost": round(max(1.0, final_cost), 2),
        "damage": round(final_damage, 2) if is_attack else None,
        "warnings": warnings,
    }


def calculate_spell_research_dc(complexity: int, mp_cost: float) -> int:
    """Research/learning DC dictated by complexity and MP cost."""
    return max(15, int(round(25 + (complexity * 6) + (sqrt(max(1.0, float(mp_cost))) * 0.7))))


def calculate_spell_cast_time(mp_cost: float, creativity: float, spellcasting_skill: float = 0.0,
                              charge_factor: float = 1.0) -> float:
    """Combat casting time based on mana output from Crea and spellcasting skill."""
    charge_factor = max(0.1, min(2.0, float(charge_factor or 1.0)))
    mana_cost = max(1.0, float(mp_cost)) * charge_factor
    creativity_multiplier = 4.0 ** ((float(creativity or 10) - 10.0) / 15.0)
    skill_multiplier = 1.0 + (0.04 * float(spellcasting_skill or 0.0))
    mana_output_per_second = max(1.0, 50.0 * creativity_multiplier * skill_multiplier)
    return max(0.8, round(mana_cost / mana_output_per_second, 1))


def calculate_total_known_complexity(spells: Dict) -> int:
    """Sum complexity of fully learned spells."""
    total = 0
    for spell in normalize_spell_collection(spells).values():
        if is_spell_learned(spell):
            total += spell.get("complexity", 0)
    return total

def study_spell(
        spell_key: str,
        game_state_path: str = None
) -> Dict:
    """
    Perform one 1-hour study session on a spell.
    Calculates DC, rolls, adds margin to learned_progress.

    Returns: {"success": bool, "message": str, "progress_added": int, "new_progress": int}
    """
    game_state_path = game_state_path or GAME_STATE_PATH
    if not os.path.exists(game_state_path):
        return {"success": False, "message": "Game state file not found"}

    try:
        with open(game_state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception as e:
        return {"success": False, "message": f"Failed to read game state: {str(e)}"}

    player = state.setdefault("player", {})
    spells = normalize_spell_collection(player.get("spells", {}))
    player["spells"] = spells

    spell = spells.get(spell_key)
    if not spell:
        return {"success": False, "message": f"Spell '{spell_key}' not found"}

    complexity = spell.get("complexity", 0)
    if complexity <= 0:
        return {"success": False, "message": "Spell has no complexity — invalid"}

    mp_cost = spell.get("MP_cost", spell.get("base_mp_cost", 100))
    dc = calculate_spell_research_dc(complexity, mp_cost)

    roll_result = roll_generic_check(
        entity_id="player",
        stats_used=["Ins", "Crea"],
        skill_used="research",
        difficulty_class=int(dc)
    )

    if not roll_result["success"]:
        return {
            "success": False,
            "message": f"Study failed (DC {dc:.1f}, margin {roll_result['margin']})",
            "progress_added": 0,
            "new_progress": spell.get("learned", 0),
            "research_dc": dc,
        }

    try:
        with open(game_state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
        player = state.setdefault("player", {})
        spells = normalize_spell_collection(player.get("spells", {}))
        player["spells"] = spells
        spell = spells.get(spell_key)
        if not spell:
            return {"success": False, "message": f"Spell '{spell_key}' not found after research roll"}
    except Exception as e:
        return {"success": False, "message": f"Failed to reload after research roll: {str(e)}"}

    margin = max(1, roll_result["margin"])
    current_progress = _get_spell_learned_value(spell)
    new_progress = min(100.0, current_progress + margin)

    spell["learned"] = new_progress

    try:
        with open(game_state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=4)
    except Exception as e:
        return {"success": False, "message": f"Failed to save: {str(e)}"}

    return {
        "success": True,
        "message": f"Study successful! +{margin}% progress (DC {dc:.1f})",
        "progress_added": margin,
        "new_progress": new_progress,
        "learned": new_progress >= 100.0,
        "research_dc": dc,
    }

def create_spell(
    spell_name: str,
    tags: List[str],
    description: str,
    is_attack: bool,
    damage: int= None,
    range: int= None,
    radius: int= None,
    duration_seconds: float = 1.0,
    target_count: int = 1,
    healing: int = None,
    shield_hp: int = None,
    gravity_delta: float = None,
    effect_power: int = None,
    parent_spell: str = None,
    competitive_caster_stat: str = None,  # e.g. "Will"
    competitive_caster_skill: str = None,  # e.g. "spellcasting"
    competitive_defender_stat: str = None,  # e.g. "Will"
    competitive_defender_skill: str = None,  # e.g. "mental_resistance"
    game_state_path: str = None,
) -> Dict[str, Any]:
    """
    Proposes a new spell based on player inputs.
    Validates tags, calculates complexity and base MP cost, infers fields.

    Returns:
        {
            "success": bool,
            "message": str,
            "proposed_spell": dict | None,
            "warnings": list[str]
        }
    """

    warnings = []
    game_state_path = game_state_path or GAME_STATE_PATH

    # ── Basic validation ────────────────────────────────────────────────────────
    if not spell_name or not spell_name.strip():
        return {"success": False, "message": "Spell name is required", "proposed_spell": None, "warnings": []}

    if not tags or not isinstance(tags, list):
        return {"success": False, "message": "Tags must be a non-empty list", "proposed_spell": None, "warnings": []}

    if is_attack and (damage is None or not isinstance(damage, int) or damage <= 0):
        return {"success": False, "message": "Damage must be a positive integer when has_damage=True", "proposed_spell": None, "warnings": []}

    if range is not None and not isinstance(range, (int, list)):
        return {"success": False, "message": "Range must be int or list[int]", "proposed_spell": None, "warnings": []}

    if radius is not None and (not isinstance(radius, int) or radius <= 0):
        return {"success": False, "message": "Radius must be positive integer or null", "proposed_spell": None, "warnings": []}

    if not description or not description.strip():
        return {"success": False, "message": "Description is required", "proposed_spell": None, "warnings": []}

    try:
        tag_library = _load_spell_tag_library()
    except Exception as e:
        return {"success": False, "message": f"Failed to load magic.json: {str(e)}", "proposed_spell": None, "warnings": []}

    # ── Validate tags & prereqs ─────────────────────────────────────────────────
    active_tags_set = set(tags)
    for tag in tags:
        if tag not in tag_library:
            return {"success": False, "message": f"Unknown tag: '{tag}'", "proposed_spell": None, "warnings": []}

        tag_data = tag_library[tag]
        # Check prereqs_any (OR)
        or_reqs = tag_data.get("prereqs_any", [])
        if or_reqs and not any(req in active_tags_set for req in or_reqs):
            return {"success": False, "message": f"Tag '{tag}' requires any of: {or_reqs}", "proposed_spell": None, "warnings": []}

        # Check prereqs_all (AND)
        and_reqs = tag_data.get("prereqs_all")
        if and_reqs and not all(req in active_tags_set for req in and_reqs):
            return {"success": False, "message": f"Tag '{tag}' requires all of: {and_reqs}", "proposed_spell": None, "warnings": []}

    cost_result = calculate_spell_mp_cost(
        tags=tags,
        is_attack=is_attack,
        damage=damage,
        range=range,
        radius=radius,
        duration_seconds=duration_seconds,
        target_count=target_count,
        healing=healing,
        shield_hp=shield_hp,
        gravity_delta=gravity_delta,
        effect_power=effect_power,
    )
    warnings.extend(cost_result.get("warnings", []))
    base_mp_cost = cost_result["base_mp_cost"]
    final_cost = cost_result["MP_cost"]
    final_damage = cost_result.get("damage")
    complexity = calculate_spell_complexity(tags, final_cost)
    research_dc = calculate_spell_research_dc(complexity, final_cost)

    # ── Infer other fields ──────────────────────────────────────────────────────
    attack_stats = ["Crea"]  # default; can be customized later
    attack_skill = "spellcasting"  # default
    is_scalable = is_attack or (radius is not None and radius > 0)

    competitive_check = None

    if "competitive_condition" in tags:
        competitive_check = {
            "type": "opposed",
            "roll": "weighted_roll",
            "caster": {
                "stats": [competitive_caster_stat],
                "skill": competitive_caster_skill
            },
            "defender": {
                "stats": [competitive_defender_stat],
                "skill": competitive_defender_skill
            }
        }

    # ── Build proposed spell ────────────────────────────────────────────────────
    proposed_spell = {
        "name": spell_name.strip(),
        "base_mp_cost": base_mp_cost,
        "complexity": complexity,
        "research_dc": research_dc,
        "tags": tags,
        "range": range,
        "radius": radius,
        "duration_seconds": duration_seconds,
        "target_count": target_count,
        "description": description.strip(),
        "has_damage": is_attack,
        "damage": final_damage if is_attack else None,
        "healing": healing,
        "shield_hp": shield_hp,
        "gravity_delta": gravity_delta,
        "effect_power": effect_power,
        "MP_cost": final_cost,
        "learned": 0.0,
        "parent_spell": parent_spell,
        "scalable": is_scalable,
        "competitive_check": competitive_check,
        "attack": {
            "stats": attack_stats,
            "skill": attack_skill
        } if is_attack else None,
        # Add more inferred fields as needed (e.g. sustained, scaling)
    }

    proposed_spell_clean = {k: v for k, v in proposed_spell.items() if v is not None}

    try:
        with open(game_state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception as e:
        return {"success": False, "message": f"Failed to load game state: {str(e)}", "proposed_spell": None, "warnings": warnings}

    spell_key = spell_name.lower().replace(" ", "_")
    player = state.setdefault("player", {})
    spell_inventory = normalize_spell_collection(player.get("spells", {}))
    counter = 1
    original_key = spell_key
    while spell_key in spell_inventory:
        spell_key = f"{original_key}_{counter}"
        counter += 1

    spell_inventory[spell_key] = proposed_spell_clean
    player["spells"] = spell_inventory

    with open(game_state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=4)

    return {
        "success": True,
        "message": "Spell proposal added to player spell inventory",
        "spell_key": spell_key,
        "proposed_spell": proposed_spell_clean,
        "warnings": warnings
    }
