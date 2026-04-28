# inventory_tools.py
import json
import os
import random
import shutil
import glob
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from path_config import path_config

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
        inventory = state["player"].setdefault("inventory", {})
    else:
        npc_data = state["npcs"].setdefault(entity_id, {})
        inventory = npc_data.setdefault("inventory", {})

    # Generate unique item ID
    base_name = item_data.get("archetype", "item").lower().replace(" ", "_")
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
