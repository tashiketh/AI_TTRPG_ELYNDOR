# inventory_tools.py
import json
import os
import re
import random
import shutil
import glob
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from path_config import path_config
from game_config import game_config

# Constants - Adjusted for very slow degradation
ITEM_CONDITION_THRESHOLDS = {
    "pristine": (1.0, 0.95),    # 95-100% HP
    "good": (0.94, 0.85),       # 85-94% HP
    "worn": (0.84, 0.70),       # 70-84% HP
    "damaged": (0.69, 0.50),    # 50-69% HP
    "broken": (0.49, 0.30),     # 30-49% HP
    "destroyed": (0.29, 0.0)    # 0-29% HP
}

# Durability factors - items last hundreds of uses
DURABILITY_FACTORS = {
    "weapon": {
        "normal_use": 0.001,      # 0.1% damage per use (1000 uses to go from pristine to destroyed)
        "heavy_use": 0.002,       # 0.2% damage per use
        "block_use": 0.005        # 0.5% damage per block (still very durable)
    },
    "shield": {
        "normal_use": 0.001,      # 0.1% damage per use
        "block_use": 0.003        # 0.3% damage per block
    },
    "armor": {
        "normal_use": 0.0005,      # 0.05% damage per hit taken
        "heavy_use": 0.001        # 0.1% damage per heavy hit
    },
    "tool": {
        "normal_use": 0.0005,      # 0.05% damage per use
        "intensive_use": 0.001     # 0.1% damage per intensive use
    },
    "default": {
        "normal_use": 0.0001       # 0.01% damage per use (very slow degradation)
    }
}

COPPER_PER_SILVER = game_config.int("currency.copper_per_silver", 100, min_value=1)
COPPER_PER_GOLD = game_config.int("currency.copper_per_gold", COPPER_PER_SILVER * 100, min_value=1)
COPPER_PER_PLATINUM = game_config.int("currency.copper_per_platinum", COPPER_PER_GOLD * 100, min_value=1)

CONDITION_STAT_MODS = {
    "pristine": {"damage_adjust": 1.0, "speed_adjust": 1.0, "price_adjust": 1.0},
    "good": {"damage_adjust": 1.0, "speed_adjust": 1.0, "price_adjust": 0.9},
    "worn": {"damage_adjust": 0.9, "speed_adjust": 1.05, "price_adjust": 0.6},
    "damaged": {"damage_adjust": 0.7, "speed_adjust": 1.15, "price_adjust": 0.35},
    "broken": {"damage_adjust": 0.35, "speed_adjust": 1.4, "price_adjust": 0.1},
    "destroyed": {"damage_adjust": 0.0, "speed_adjust": 2.0, "price_adjust": 0.0},
}

_CRAFT_CACHE: Optional[Dict[str, Any]] = None


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def currency_to_copper(copper: Any = 0, silver: Any = 0, gold: Any = 0, platinum: Any = 0) -> int:
    """Convert denomination amounts into canonical copper."""
    return (
        _coerce_int(copper, 0)
        + (_coerce_int(silver, 0) * COPPER_PER_SILVER)
        + (_coerce_int(gold, 0) * COPPER_PER_GOLD)
        + (_coerce_int(platinum, 0) * COPPER_PER_PLATINUM)
    )


def split_currency(copper_total: Any) -> Dict[str, int]:
    """Return display denominations for a copper balance."""
    remaining = max(0, _coerce_int(copper_total, 0))
    platinum, remaining = divmod(remaining, COPPER_PER_PLATINUM)
    gold, remaining = divmod(remaining, COPPER_PER_GOLD)
    silver, copper = divmod(remaining, COPPER_PER_SILVER)
    return {"platinum": platinum, "gold": gold, "silver": silver, "copper": copper}


def format_currency(copper_total: Any) -> str:
    """Format canonical copper as compact denominations."""
    parts = [
        (amount, label)
        for label, amount in split_currency(copper_total).items()
        if amount
    ]
    if not parts:
        return "0 copper"
    return ", ".join(f"{amount} {label}" for amount, label in parts)


def currency_snapshot(player: Dict[str, Any]) -> Dict[str, Any]:
    """Return a UI/prompt-friendly currency snapshot."""
    currency = player.get("currency", {}) if isinstance(player, dict) else {}
    copper = currency.get("copper", 0) if isinstance(currency, dict) else currency
    copper = max(0, _coerce_int(copper, 0))
    return {
        "copper": copper,
        "display": format_currency(copper),
        "denominations": split_currency(copper),
    }


def _currency_item_value_in_copper(item: Dict[str, Any], quantity: int = 1) -> int:
    """Return wallet value for ordinary loose coin items; special coins remain inventory."""
    if not isinstance(item, dict):
        return 0
    tags = {str(tag).strip().lower() for tag in item.get("tags", []) if str(tag).strip()}
    special_tags = {"foreign", "counterfeit", "cursed", "marked", "sealed", "collectible", "ancient"}
    if tags & special_tags:
        return 0
    text = " ".join(str(item.get(field, "")) for field in ("name", "archetype", "type", "description")).lower()
    ordinary_money = "currency" in tags or "coin" in text or "coins" in text or "money" in text
    if not ordinary_money:
        return 0
    denomination = ""
    for candidate in ("platinum", "gold", "silver", "copper"):
        if candidate in tags or re.search(rf"\b{candidate}\b", text):
            denomination = candidate
            break
    if not denomination:
        return 0
    value = {
        "copper": 1,
        "silver": COPPER_PER_SILVER,
        "gold": COPPER_PER_GOLD,
        "platinum": COPPER_PER_PLATINUM,
    }[denomination]
    qty = _coerce_int(item.get("qty", item.get("quantity", quantity)), quantity)
    return max(0, qty) * value


def normalize_player_currency(player: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate legacy gold and ordinary coin inventory into player.currency.copper."""
    if not isinstance(player, dict):
        return {"copper": 0, "display": "0 copper", "denominations": split_currency(0)}
    currency = player.get("currency", {})
    if isinstance(currency, dict):
        copper = currency_to_copper(
            currency.get("copper", 0),
            currency.get("silver", 0),
            currency.get("gold", 0),
            currency.get("platinum", 0),
        )
    else:
        copper = _coerce_int(currency, 0)

    if "gold" in player:
        copper += currency_to_copper(gold=player.get("gold", 0))
        player.pop("gold", None)

    inventory = player.get("inventory")
    if isinstance(inventory, dict):
        for item_id, item in list(inventory.items()):
            value = _currency_item_value_in_copper(item, 1)
            if value > 0:
                copper += value
                del inventory[item_id]

    player["currency"] = {"copper": max(0, copper)}
    return currency_snapshot(player)


def add_currency_to_player(player: Dict[str, Any], copper: Any = 0, silver: Any = 0,
                           gold: Any = 0, platinum: Any = 0) -> Dict[str, Any]:
    """Add spendable currency to a player wallet."""
    snapshot = normalize_player_currency(player)
    delta = currency_to_copper(copper, silver, gold, platinum)
    player["currency"]["copper"] = max(0, snapshot["copper"] + delta)
    return currency_snapshot(player)


def add_currency_to_wallet(copper: Any = 0, silver: Any = 0, gold: Any = 0,
                           platinum: Any = 0, entity_id: str = "player") -> Dict[str, Any]:
    """Add currency to the save file wallet."""
    if entity_id != "player":
        return {"success": False, "message": "Only player currency is supported right now"}
    try:
        with open(path_config.game_state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception as e:
        return {"success": False, "message": f"Cannot load game state: {str(e)}"}
    player = state.setdefault("player", {})
    delta = currency_to_copper(copper, silver, gold, platinum)
    snapshot = add_currency_to_player(player, copper=delta)
    _backup_and_save(state)
    return {
        "success": True,
        "message": f"Added {format_currency(delta)}",
        "currency": snapshot,
        "copper_added": delta,
    }


def _canonical_text(value: Any) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def _dedupe_tags(tags: List[Any]) -> List[str]:
    clean_tags = []
    seen = set()
    for tag in tags:
        clean = str(tag or "").strip().lower()
        if clean and clean not in seen:
            clean_tags.append(clean)
            seen.add(clean)
    return clean_tags


def _load_craft_reference() -> Dict[str, Any]:
    """Load item templates plus material and quality modifiers from craft.json."""
    global _CRAFT_CACHE
    if _CRAFT_CACHE is not None:
        return _CRAFT_CACHE
    try:
        with open(path_config.crafting_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    craft = data.get("craft", {}) if isinstance(data, dict) else {}
    _CRAFT_CACHE = {
        "items": data.get("items", {}) if isinstance(data, dict) else {},
        "materials": craft.get("materials", {}) if isinstance(craft, dict) else {},
        "quality": craft.get("quality", {}) if isinstance(craft, dict) else {},
    }
    return _CRAFT_CACHE


def _find_item_template(item_data: Dict[str, Any], templates: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """Find the closest craft.json template for a loose item description."""
    if not templates:
        return "", {}
    tags = item_data.get("tags", []) if isinstance(item_data.get("tags"), list) else []
    candidates = [
        item_data.get("archetype"),
        item_data.get("name"),
        item_data.get("type"),
        *tags,
    ]
    canonical_templates = {_canonical_text(key): key for key in templates}
    for candidate in candidates:
        key = canonical_templates.get(_canonical_text(candidate))
        if key:
            return key, templates.get(key, {})

    search_text = " ".join(str(value or "") for value in [
        item_data.get("archetype"),
        item_data.get("name"),
        item_data.get("type"),
        item_data.get("description"),
        " ".join(str(tag) for tag in tags),
    ])
    words = {word.rstrip("s") for word in re.findall(r"[a-z0-9]+", search_text.lower())}
    for key in sorted(templates, key=len, reverse=True):
        key_words = {word.rstrip("s") for word in re.findall(r"[a-z0-9]+", str(key).lower())}
        if key_words and key_words.issubset(words):
            return key, templates.get(key, {})
    return "", {}


def _infer_materials(item: Dict[str, Any], material_mods: Dict[str, Any],
                     weapon_like: bool = False) -> List[str]:
    tags = item.get("tags", []) if isinstance(item.get("tags"), list) else []
    text = " ".join(str(value or "") for value in [
        item.get("archetype"),
        item.get("name"),
        item.get("type"),
        item.get("description"),
        " ".join(str(tag) for tag in tags),
    ]).lower()
    materials = []
    for material in material_mods:
        material_text = str(material).lower()
        if material_text in tags or re.search(rf"\b{re.escape(material_text)}\b", text):
            materials.append(material_text)
    if not materials and weapon_like and "iron" in material_mods:
        materials.append("iron")
    return materials


def _infer_quality(item: Dict[str, Any], quality_mods: Dict[str, Any]) -> str:
    tags = item.get("tags", []) if isinstance(item.get("tags"), list) else []
    quality = str(item.get("quality") or "").strip().lower()
    if quality in quality_mods:
        return quality
    for tag in tags:
        tag_text = str(tag).strip().lower()
        if tag_text in quality_mods:
            return tag_text
    return "standard"


def _round_stat(value: float) -> float:
    rounded = round(float(value), 2)
    return int(rounded) if rounded.is_integer() else rounded


def normalize_inventory_item(item_data: Dict[str, Any], quantity: int = 1,
                             condition: str = "pristine") -> Dict[str, Any]:
    """Return a display-ready item with template stats and normalized tags."""
    item = dict(item_data or {})
    reference = _load_craft_reference()
    templates = reference["items"]
    material_mods = reference["materials"]
    quality_mods = reference["quality"]

    template_key, template = _find_item_template(item, templates)
    base_tags = template.get("tags", []) if isinstance(template.get("tags"), list) else []
    given_tags = item.get("tags", []) if isinstance(item.get("tags"), list) else []
    merged = dict(template)
    merged.update(item)

    if not merged.get("archetype"):
        merged["archetype"] = item.get("name") or item.get("type") or template.get("archetype") or template_key or "item"
    if not merged.get("name"):
        merged["name"] = str(merged.get("archetype") or template.get("archetype") or template_key or "Item").strip()

    max_hp = merged.get("max_hp", 100)
    hp = merged.get("hp", max_hp)
    merged["max_hp"] = max_hp
    merged["hp"] = hp
    inferred_condition = get_item_condition(merged["hp"], merged["max_hp"])
    merged["condition"] = inferred_condition or str(condition or "pristine").lower()

    weapon_like = "weapon" in _dedupe_tags(base_tags + given_tags) or any(
        field in template for field in ("damage", "speed", "range")
    )
    materials = _infer_materials({**merged, "tags": base_tags + given_tags}, material_mods, weapon_like)
    quality = _infer_quality({**merged, "tags": base_tags + given_tags}, quality_mods)

    tags = _dedupe_tags(base_tags + given_tags + ([template_key] if template_key else []) + materials + [quality, merged["condition"]])
    merged["tags"] = tags
    merged["quality"] = quality

    material_key = materials[0] if materials else ""
    mat_mod = material_mods.get(material_key, {})
    qual_mod = quality_mods.get(quality, {})
    cond_mod = CONDITION_STAT_MODS.get(merged["condition"], CONDITION_STAT_MODS["pristine"])

    if template:
        if "damage" in template and "damage" not in item:
            merged["damage"] = _round_stat(
                template.get("damage", 0)
                * mat_mod.get("damage_adjust", 1.0)
                * qual_mod.get("damage_adjust", 1.0)
                * cond_mod.get("damage_adjust", 1.0)
            )
        if "speed" in template and "speed" not in item:
            merged["speed"] = _round_stat(
                template.get("speed", 1.0)
                * mat_mod.get("speed_adjust", 1.0)
                * qual_mod.get("speed_adjust", 1.0)
                * cond_mod.get("speed_adjust", 1.0)
            )
        if "price" in template and "price" not in item:
            merged["price"] = int(round(
                template.get("price", 0)
                * mat_mod.get("price_adjust", 1.0)
                * qual_mod.get("price_adjust", 1.0)
                * cond_mod.get("price_adjust", 1.0)
            ))
        if "weight" in template and "weight" not in item:
            merged["weight"] = _round_stat(template.get("weight", 0) * mat_mod.get("weight_adjust", 1.0))
        for field in ("range", "AC", "base_armor"):
            if field in template and field not in item:
                merged[field] = template[field]

    merged.setdefault("durability", 1.0)
    merged.setdefault("location", None)
    merged.setdefault("qty", quantity)
    merged.setdefault("quantity", merged.get("qty", quantity))
    merged.setdefault("uses_since_repair", 0)
    if merged.get("description") is None:
        merged["description"] = ""
    return merged


def normalize_inventory_collection(inventory: Any) -> Dict[str, Dict[str, Any]]:
    """Normalize an inventory dict for UI/API use."""
    if not isinstance(inventory, dict):
        return {}
    normalized = {}
    for item_id, item in inventory.items():
        if isinstance(item, dict):
            if _currency_item_value_in_copper(item, 1) > 0:
                continue
            normalized_item = normalize_inventory_item(
                item,
                quantity=int(item.get("qty", item.get("quantity", 1)) or 1),
                condition=str(item.get("condition", "pristine")),
            )
            normalized_item.setdefault("id", item_id)
            normalized[item_id] = normalized_item
    return normalized

def _backup_and_save(state: Dict):
    """Create backup then overwrite game state file."""
    if os.path.exists(path_config.game_state_path):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(path_config.backup_dir, f"state_backup_{ts}.json")
        shutil.copy(path_config.game_state_path, backup_path)

        # Keep only 5 newest backups
        backups = sorted(glob.glob(os.path.join(path_config.backup_dir, "state_backup_*.json")),
                         key=os.path.getmtime, reverse=True)
        for old in backups[5:]:
            os.remove(old)

    with open(path_config.game_state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=4)

def get_item_condition(hp: int, max_hp: int) -> str:
    """Determine the condition of an item based on its current HP."""
    if max_hp <= 0:
        return "destroyed"

    ratio = hp / max_hp

    for condition, (upper, lower) in ITEM_CONDITION_THRESHOLDS.items():
        if lower <= ratio <= upper:
            return condition

    return "destroyed"

def add_item_to_inventory(
    item_data: Dict,
    entity_id: str = "player",
    quantity: int = 1,
    condition: str = "pristine"
) -> Dict:
    """
    Add an item to inventory with proper durability tracking.

    Args:
        item_data: Dictionary containing item properties
        entity_id: ID of entity receiving the item
        quantity: Number of items to add
        condition: Initial condition of the item

    Returns:
        Dictionary with success status and item details
    """
    try:
        with open(path_config.game_state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception as e:
        return {"success": False, "message": f"Cannot load game state: {str(e)}"}

    # Determine which inventory to use
    if entity_id == "player":
        player = state.setdefault("player", {})
        normalize_player_currency(player)
        currency_value = _currency_item_value_in_copper(item_data, quantity)
        if currency_value > 0:
            snapshot = add_currency_to_player(player, copper=currency_value)
            _backup_and_save(state)
            return {
                "success": True,
                "message": f"Added {format_currency(currency_value)} to currency",
                "currency": snapshot,
                "copper_added": currency_value,
            }
        inventory = player.setdefault("inventory", {})
    else:
        npc_data = state["npcs"].setdefault(entity_id, {})
        inventory = npc_data.setdefault("inventory", {})

    item_data = normalize_inventory_item(item_data, quantity=quantity, condition=condition)

    # Generate unique item ID
    base_name = item_data.get("archetype") or item_data.get("name") or "item"
    base_name = re.sub(r"[^a-z0-9]+", "_", str(base_name).lower()).strip("_") or "item"
    item_id = f"{base_name}_{random.randint(10000, 99999)}"

    # Set default values with high durability
    item_data.setdefault("hp", item_data.get("max_hp", 100))  # Default HP increased
    item_data.setdefault("max_hp", item_data.get("max_hp", 100))  # Default max HP increased
    item_data.setdefault("condition", condition)
    item_data.setdefault("durability", 1.0)  # 0.0 to 1.0
    item_data.setdefault("location", None)
    item_data.setdefault("qty", quantity)
    item_data.setdefault("uses_since_repair", 0)

    # Ensure condition matches HP
    current_condition = get_item_condition(item_data["hp"], item_data["max_hp"])
    item_data["condition"] = current_condition

    # Add to inventory
    inventory[item_id] = item_data

    # Save with backup
    _backup_and_save(state)

    return {
        "success": True,
        "message": f"Added {quantity}x {item_data.get('archetype', 'item')} to inventory",
        "item_id": item_id,
        "details": item_data
    }

def update_item_durability(
    item_id: str,
    damage: int,
    entity_id: str = "player",
    usage_type: str = "normal"
) -> Dict:
    """
    Update an item's durability after taking damage.

    Args:
        item_id: ID of the item to update
        damage: Amount of damage to apply (raw damage before durability factors)
        entity_id: ID of entity who owns the item
        usage_type: Type of usage (normal, heavy, block, etc.)

    Returns:
        Dictionary with success status and updated item details
    """
    try:
        with open(path_config.game_state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception as e:
        return {"success": False, "message": f"Cannot load game state: {str(e)}"}

    # Find the inventory containing the item
    inventory = None
    if entity_id == "player":
        inventory = state["player"].get("inventory", {})
    else:
        npc_data = state["npcs"].get(entity_id, {})
        inventory = npc_data.get("inventory", {})

    if not inventory or item_id not in inventory:
        return {"success": False, "message": f"Item {item_id} not found in {entity_id}'s inventory"}

    item = inventory[item_id]

    # Determine durability factor based on item type and usage
    durability_factor = DURABILITY_FACTORS["default"]["normal_use"]

    # Get item tags to determine type
    tags = item.get("tags", [])

    if "weapon" in tags:
        if usage_type == "heavy":
            durability_factor = DURABILITY_FACTORS["weapon"]["heavy_use"]
        elif usage_type == "block":
            durability_factor = DURABILITY_FACTORS["weapon"]["block_use"]
        else:
            durability_factor = DURABILITY_FACTORS["weapon"]["normal_use"]
    elif "shield" in tags and usage_type == "block":
        durability_factor = DURABILITY_FACTORS["shield"]["block_use"]
    elif "shield" in tags:
        durability_factor = DURABILITY_FACTORS["shield"]["normal_use"]
    elif "armor" in tags:
        if usage_type == "heavy":
            durability_factor = DURABILITY_FACTORS["armor"]["heavy_use"]
        else:
            durability_factor = DURABILITY_FACTORS["armor"]["normal_use"]
    elif any(tag in ["tool", "utility"] for tag in tags):
        if usage_type == "intensive":
            durability_factor = DURABILITY_FACTORS["tool"]["intensive_use"]
        else:
            durability_factor = DURABILITY_FACTORS["tool"]["normal_use"]

    # Calculate actual damage based on durability factor
    actual_damage = int(damage * durability_factor)

    # Apply damage (minimum 0 to prevent healing items through usage)
    item["hp"] = max(0, item["hp"] - max(0, actual_damage))

    # Track uses for maintenance purposes
    item["uses_since_repair"] = item.get("uses_since_repair", 0) + 1

    # Update condition
    new_condition = get_item_condition(item["hp"], item.get("max_hp", 100))
    item["condition"] = new_condition

    # Update durability ratio
    item["durability"] = item["hp"] / item.get("max_hp", 100)

    # Save changes
    _backup_and_save(state)

    return {
        "success": True,
        "message": f"Item {item_id} took {actual_damage} damage (raw: {damage})",
        "item_id": item_id,
        "new_hp": item["hp"],
        "new_condition": new_condition,
        "durability": item["durability"],
        "uses_since_repair": item["uses_since_repair"],
        "damage_type": usage_type
    }

def repair_item(
    item_id: str,
    repair_amount: int = None,
    entity_id: str = "player",
    use_repair_kit: bool = False,
    maintenance_repair: bool = False
) -> Dict:
    """
    Repair an item, restoring its HP.

    Args:
        item_id: ID of the item to repair
        repair_amount: Specific amount to repair (None for full repair)
        entity_id: ID of entity who owns the item
        use_repair_kit: Whether to consume a repair kit
        maintenance_repair: Whether this is routine maintenance (small repair)

    Returns:
        Dictionary with success status and repair details
    """
    try:
        with open(path_config.game_state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception as e:
        return {"success": False, "message": f"Cannot load game state: {str(e)}"}

    # Find the inventory containing the item
    inventory = None
    if entity_id == "player":
        inventory = state["player"].get("inventory", {})
        player_inventory = inventory
    else:
        npc_data = state["npcs"].get(entity_id, {})
        inventory = npc_data.get("inventory", {})
        player_inventory = None

    if not inventory or item_id not in inventory:
        return {"success": False, "message": f"Item {item_id} not found in {entity_id}'s inventory"}

    item = inventory[item_id]

    if item["condition"] == "destroyed":
        return {"success": False, "message": f"Item {item_id} is destroyed and cannot be repaired"}

    max_hp = item.get("max_hp", 100)
    current_hp = item["hp"]

    if current_hp >= max_hp:
        return {"success": False, "message": f"Item {item_id} is already at full durability"}

    # Determine repair amount
    if maintenance_repair:
        # Small maintenance repair (5-15% of max HP)
        repair_amount = random.randint(int(max_hp * 0.05), int(max_hp * 0.15))
    elif repair_amount is None:
        # Full repair
        repair_amount = max_hp - current_hp
    else:
        # Specific repair amount
        repair_amount = min(repair_amount, max_hp - current_hp)

    # Check for repair kit if requested
    if use_repair_kit and player_inventory:
        repair_kits = [kid for kid, kit in player_inventory.items()
                      if "repair_kit" in kit.get("tags", []) and kit.get("qty", 0) > 0]

        if not repair_kits:
            return {"success": False, "message": "No repair kits available"}

        # Use the first repair kit found
        repair_kit_id = repair_kits[0]
        repair_kit = player_inventory[repair_kit_id]

        # Consume one use from the repair kit
        if repair_kit.get("qty", 1) > 1:
            repair_kit["qty"] -= 1
        else:
            del player_inventory[repair_kit_id]

    # Apply repair
    item["hp"] = min(max_hp, current_hp + repair_amount)

    # Reset uses since repair if this was a significant repair
    if not maintenance_repair:
        item["uses_since_repair"] = 0

    # Update condition and durability
    new_condition = get_item_condition(item["hp"], max_hp)
    item["condition"] = new_condition
    item["durability"] = item["hp"] / max_hp

    # Save changes
    _backup_and_save(state)

    return {
        "success": True,
        "message": f"Repaired {item_id} for {repair_amount} HP",
        "item_id": item_id,
        "new_hp": item["hp"],
        "new_condition": new_condition,
        "repair_amount": repair_amount,
        "used_repair_kit": use_repair_kit,
        "maintenance_repair": maintenance_repair,
        "uses_since_repair": item.get("uses_since_repair", 0)
    }

def get_inventory_summary(entity_id: str = "player") -> Dict:
    """
    Get a summary of an entity's inventory with item conditions.

    Args:
        entity_id: ID of entity to get inventory for

    Returns:
        Dictionary with inventory summary
    """
    try:
        with open(path_config.game_state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception as e:
        return {"success": False, "message": f"Cannot load game state: {str(e)}"}

    # Find the inventory
    if entity_id == "player":
        inventory = state["player"].get("inventory", {})
    else:
        npc_data = state["npcs"].get(entity_id, {})
        inventory = npc_data.get("inventory", {})

    # Categorize items
    weapons = []
    armor = []
    shields = []
    consumables = []
    containers = []
    tools = []
    other = []

    for item_id, item in inventory.items():
        tags = item.get("tags", [])
        item_summary = {
            "id": item_id,
            "name": item.get("archetype", "Unknown"),
            "condition": item.get("condition", "unknown"),
            "hp": f"{item.get('hp', 0)}/{item.get('max_hp', 1)}",
            "location": item.get("location", "none"),
            "uses": item.get("uses_since_repair", 0)
        }

        if "weapon" in tags:
            weapons.append(item_summary)
        elif "armor" in tags:
            armor.append(item_summary)
        elif "shield" in tags:
            shields.append(item_summary)
        elif any(tag in ["food", "potion", "medicine"] for tag in tags):
            consumables.append(item_summary)
        elif "container" in tags:
            containers.append(item_summary)
        elif any(tag in ["tool", "utility"] for tag in tags):
            tools.append(item_summary)
        else:
            other.append(item_summary)

    return {
        "success": True,
        "entity": entity_id,
        "summary": {
            "weapons": weapons,
            "armor": armor,
            "shields": shields,
            "consumables": consumables,
            "containers": containers,
            "tools": tools,
            "other": other
        },
        "total_items": len(inventory)
    }

def equip_item(
    item_id: str,
    entity_id: str = "player",
    slot: str = None
) -> Dict:
    """
    Equip an item to a specific equipment slot.

    Args:
        item_id: ID of the item to equip
        entity_id: ID of entity equipping the item
        slot: Equipment slot (e.g., "main_hand", "off_hand", "head", "torch", etc.)

    Returns:
        Dictionary with success status and equip details
    """
    try:
        with open(path_config.game_state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception as e:
        return {"success": False, "message": f"Cannot load game state: {str(e)}"}

    # Find the inventory containing the item
    inventory = None
    equipment = None

    if entity_id == "player":
        inventory = state["player"].get("inventory", {})
        equipment = state["player"].setdefault("equipment", {})
    else:
        npc_data = state["npcs"].setdefault(entity_id, {})
        inventory = npc_data.get("inventory", {})
        equipment = npc_data.setdefault("equipment", {})

    if not inventory or item_id not in inventory:
        return {"success": False, "message": f"Item {item_id} not found in {entity_id}'s inventory"}

    item = inventory[item_id]

    # Determine appropriate slot if not specified
    if slot is None:
        tags = item.get("tags", [])
        if "weapon" in tags:
            # Check if two-handed
            if item.get("two_handed", False):
                slot = "two_handed"
            else:
                # Try main hand first, then off hand
                if equipment.get("main_hand") is None:
                    slot = "main_hand"
                elif equipment.get("off_hand") is None:
                    slot = "off_hand"
                else:
                    return {"success": False, "message": "Both hands are full"}
        elif "shield" in tags:
            slot = "off_hand"
        elif "armor" in tags:
            armor_type = item.get("armor_type", "torch")
            if armor_type == "head":
                slot = "head"
            elif armor_type == "torch":
                slot = "torch"
            elif armor_type == "chest":
                slot = "chest"
            elif armor_type == "legs":
                slot = "legs"
            elif armor_type == "feet":
                slot = "feet"
            else:
                slot = "torch"
        else:
            return {"success": False, "message": f"Item {item_id} cannot be equipped"}

    # Unequip current item in slot if any
    if slot in equipment and equipment[slot] is not None:
        unequipped_item_id = equipment[slot]
        if unequipped_item_id in inventory:
            inventory[unequipped_item_id]["location"] = None

    # Equip new item
    equipment[slot] = item_id
    item["location"] = f"equipped_{slot}"

    # Save changes
    _backup_and_save(state)

    return {
        "success": True,
        "message": f"Equipped {item_id} in {slot} slot",
        "item_id": item_id,
        "slot": slot,
        "previous_item": equipment.get(f"previous_{slot}")
    }

def unequip_item(
    slot: str,
    entity_id: str = "player"
) -> Dict:
    """
    Unequip an item from a specific equipment slot.

    Args:
        slot: Equipment slot to unequip
        entity_id: ID of entity unequipping the item

    Returns:
        Dictionary with success status and unequip details
    """
    try:
        with open(path_config.game_state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception as e:
        return {"success": False, "message": f"Cannot load game state: {str(e)}"}

    # Find the equipment
    if entity_id == "player":
        inventory = state["player"].get("inventory", {})
        equipment = state["player"].get("equipment", {})
    else:
        npc_data = state["npcs"].get(entity_id, {})
        inventory = npc_data.get("inventory", {})
        equipment = npc_data.get("equipment", {})

    if not equipment or slot not in equipment or equipment[slot] is None:
        return {"success": False, "message": f"No item equipped in {slot} slot"}

    item_id = equipment[slot]

    if item_id not in inventory:
        return {"success": False, "message": f"Equipped item {item_id} not found in inventory"}

    # Unequip the item
    item = inventory[item_id]
    item["location"] = None
    equipment[slot] = None

    # Save changes
    _backup_and_save(state)

    return {
        "success": True,
        "message": f"Unequipped {item_id} from {slot} slot",
        "item_id": item_id,
        "slot": slot
    }

def get_equipment_summary(entity_id: str = "player") -> Dict:
    """
    Get a summary of an entity's equipped items.

    Args:
        entity_id: ID of entity to get equipment for

    Returns:
        Dictionary with equipment summary
    """
    try:
        with open(path_config.game_state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception as e:
        return {"success": False, "message": f"Cannot load game state: {str(e)}"}

    # Find the equipment and inventory
    if entity_id == "player":
        inventory = state["player"].get("inventory", {})
        equipment = state["player"].get("equipment", {})
    else:
        npc_data = state["npcs"].get(entity_id, {})
        inventory = npc_data.get("inventory", {})
        equipment = npc_data.get("equipment", {})

    # Build equipment summary
    equipped_items = {}

    for slot, item_id in equipment.items():
        if item_id and item_id in inventory:
            item = inventory[item_id]
            equipped_items[slot] = {
                "id": item_id,
                "name": item.get("archetype", "Unknown"),
                "condition": item.get("condition", "unknown"),
                "hp": f"{item.get('hp', 0)}/{item.get('max_hp', 1)}",
                "tags": item.get("tags", []),
                "uses": item.get("uses_since_repair", 0)
            }
        else:
            equipped_items[slot] = None

    return {
        "success": True,
        "entity": entity_id,
        "equipment": equipped_items,
        "equipped_count": sum(1 for item in equipped_items.values() if item is not None)
    }

def check_item_breakage(item_id: str, entity_id: str = "player") -> Dict:
    """
    Check if an item is broken and handle breakage effects.

    Args:
        item_id: ID of the item to check
        entity_id: ID of entity who owns the item

    Returns:
        Dictionary with breakage status and effects
    """
    try:
        with open(path_config.game_state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception as e:
        return {"success": False, "message": f"Cannot load game state: {str(e)}"}

    # Find the inventory containing the item
    inventory = None
    equipment = None

    if entity_id == "player":
        inventory = state["player"].get("inventory", {})
        equipment = state["player"].get("equipment", {})
    else:
        npc_data = state["npcs"].get(entity_id, {})
        inventory = npc_data.get("inventory", {})
        equipment = npc_data.get("equipment", {})

    if not inventory or item_id not in inventory:
        return {"success": False, "message": f"Item {item_id} not found in {entity_id}'s inventory"}

    item = inventory[item_id]

    if item["condition"] != "destroyed":
        return {"success": True, "message": f"Item {item_id} is not destroyed", "broken": False}

    # Item is destroyed - handle effects
    effects = []

    # Check if item was equipped
    equipped_slot = None
    for slot, equipped_item_id in equipment.items():
        if equipped_item_id == item_id:
            equipped_slot = slot
            equipment[slot] = None
            effects.append(f"Unequipped from {slot} slot")
            break

    # Remove the item from inventory
    del inventory[item_id]
    effects.append("Removed from inventory")

    # Save changes
    _backup_and_save(state)

    return {
        "success": True,
        "message": f"Item {item_id} was destroyed",
        "broken": True,
        "equipped_slot": equipped_slot,
        "effects": effects
    }

def perform_routine_maintenance(entity_id: str = "player") -> Dict:
    """
    Perform routine maintenance on all equipped items.

    Args:
        entity_id: ID of entity performing maintenance

    Returns:
        Dictionary with maintenance results
    """
    try:
        with open(path_config.game_state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception as e:
        return {"success": False, "message": f"Cannot load game state: {str(e)}"}

    # Find the equipment and inventory
    if entity_id == "player":
        inventory = state["player"].get("inventory", {})
        equipment = state["player"].get("equipment", {})
    else:
        npc_data = state["npcs"].get(entity_id, {})
        inventory = npc_data.get("inventory", {})
        equipment = npc_data.get("equipment", {})

    maintenance_results = []
    items_maintained = 0

    # Perform maintenance on all equipped items
    for slot, item_id in equipment.items():
        if item_id and item_id in inventory:
            item = inventory[item_id]

            # Only maintain items that need it (not pristine and not destroyed)
            if item.get("condition") not in ["pristine", "destroyed"]:
                # Perform maintenance repair
                repair_result = repair_item(item_id, entity_id=entity_id, maintenance_repair=True)

                if repair_result["success"]:
                    maintenance_results.append({
                        "item_id": item_id,
                        "item_name": item.get("archetype", "Unknown"),
                        "old_condition": repair_result.get("old_condition", item.get("condition")),
                        "new_condition": repair_result["new_condition"],
                        "repair_amount": repair_result["repair_amount"]
                    })
                    items_maintained += 1

    # Save changes
    _backup_and_save(state)

    return {
        "success": True,
        "message": f"Performed routine maintenance on {items_maintained} items",
        "items_maintained": items_maintained,
        "maintenance_results": maintenance_results
    }

# Example usage
if __name__ == "__main__":
    # Test adding an item
    test_item = {
        "archetype": "steel_sword",
        "tags": ["weapon", "melee", "edged"],
        "damage": 25,
        "speed": 2.0,
        "max_hp": 100,  # Increased durability
        "hp": 100,
        "weight": 2.5
    }

    result = add_item_to_inventory(test_item, "player", 1, "pristine")
    print("Add item result:", result)

    if result["success"]:
        item_id = result["item_id"]

        # Test damaging the item (simulate 10 normal uses)
        for i in range(10):
            damage_result = update_item_durability(item_id, 100, "player", "normal")  # 100 raw damage
            print(f"Use {i+1} - Damage result:", damage_result)

        # Test repairing the item
        repair_result = repair_item(item_id, 10, "player")
        print("Repair result:", repair_result)

        # Get inventory summary
        summary = get_inventory_summary("player")
        print("Inventory summary:", summary)
