import json
import os
import glob
import shutil
import random
import csv
from typing import Any, Dict, List, Optional, Tuple, Union
from datetime import datetime
from pathlib import Path
from path_config import path_config

# Constants
RELATIONSHIP_LEVELS = {
    "mortal enemy": -40,
    "enemy": -20,
    "adversary": -10,
    "neutral": 0,
    "friend": 5,
    "companion": 10,
    "lover": 20,
    "spouse": 30
}

# Persistent NPC state (replace with game_state integration in production)
NPC_STATE: Dict[str, Dict[str, Any]] = {}

def get_character_identity(character: Dict[str, Any]) -> Dict[str, Any]:
    """Return canonical nested identity data, with legacy fallback."""
    identity = character.get("identity") if isinstance(character, dict) else {}
    return identity if isinstance(identity, dict) else character

def get_character_field(character: Dict[str, Any], field: str, default: Any = None) -> Any:
    """Read a character/NPC field from the current template shape."""
    identity = get_character_identity(character)
    if field in identity:
        return identity.get(field, default)
    if field == "relationship":
        player_rel = identity.get("relationships", {}).get("player", {})
        if isinstance(player_rel, dict):
            return player_rel.get("relationship", default)
    return character.get(field, default)

SKILL_ALIASES = {
    "Melee Weapons": "melee weapons",
    "Ranged Weapons": "ranged weapons",
    "Spellcasting": "spellcasting",
    "Social": "communication",
    "Crafting": "smithing",
    "Survival": "survival",
}


def normalize_skill_name(skill_name: Optional[str]) -> Optional[str]:
    """Normalize skill IDs to references/skills.csv names."""
    if not skill_name:
        return None
    return SKILL_ALIASES.get(skill_name, str(skill_name).strip().lower())


def calculate_scaled_hp_mp_max(stats: Dict[str, float]) -> Dict[str, int]:
    """Calculate max HP/MP from current stats."""
    max_hp = round(0.5 * (stats.get("Vit", 10) ** 2) * stats.get("Str", 10))
    max_mp = round(0.5 * (stats.get("Will", 10) ** 2) * stats.get("Crea", 10))
    return {"HP_max": max_hp, "MP_max": max_mp}


def refresh_player_derived_maxima(game_state: Dict[str, Any]) -> Dict[str, int]:
    """
    Refresh max HP/MP after stat growth.

    Current HP/MP are preserved unless they were already full, in which case they
    rise to the new max. Values are clamped if a future formula ever lowers max.
    """
    player = game_state.setdefault("player", {})
    stats = player.get("stats", {})
    derived = player.setdefault("derived", {})

    old_hp_max = derived.get("HP_max", derived.get("HP", 0))
    old_mp_max = derived.get("MP_max", derived.get("MP", 0))
    was_full_hp = derived.get("HP", 0) >= old_hp_max
    was_full_mp = derived.get("MP", 0) >= old_mp_max

    maxima = calculate_scaled_hp_mp_max(stats)
    derived["HP_max"] = maxima["HP_max"]
    derived["MP_max"] = maxima["MP_max"]
    derived["HP"] = maxima["HP_max"] if was_full_hp else min(derived.get("HP", 0), maxima["HP_max"])
    derived["MP"] = maxima["MP_max"] if was_full_mp else min(derived.get("MP", 0), maxima["MP_max"])
    return maxima

def weighted_roll(num_dice: int = 4, die_sides: int = 25) -> int:
    """Sum of multiple dice for a bell-curved result (4d25 default)."""
    return sum(random.randint(1, die_sides) for _ in range(num_dice))

def roll_generic_check(
    entity_id: Optional[str] = None,      # None or "player" → player; else npc_id
    stats_used: Optional[List[str]] = None,       # Required: at least one stat
    skill_used: Optional[str] = None,             # Optional: single skill from skills.csv
    situational_bonus: float = 0.0,     # e.g. +5 for good RP/planning, -5 for poor
    difficulty_class: int = 50
) -> Dict[str, Any]:
    """
    Perform a general check for player or NPC.
    Uses weighted 4d25 roll + modifiers vs DC.
    Returns success, margin, roll value, and growth (player only - applied immediately).

    Args:
        entity_id: ID of entity performing check ("player" or npc_id)
        stats_used: List of stats to use (e.g., ["Str", "Agi"])
        skill_used: Skill to use (e.g., "Melee Weapons")
        situational_bonus: Bonus/penalty from situation
        difficulty_class: Target DC (higher is harder)

    Returns:
        Dict with check results including success, margin, growth, etc.
    """
    # Normalize and validate stats_used
    stats_used = (stats_used or [])[:3]  # enforce max 3
    if not stats_used:
        raise ValueError("At least one stat is required (stats_used)")

    num_stats = len(stats_used)
    primary_stat = stats_used[0]
    secondary_stats = stats_used[1:]

    # Stat growth distribution weights
    if num_stats == 1:
        stat_weights = {primary_stat: 1.00}
    elif num_stats == 2:
        stat_weights = {primary_stat: 0.75, secondary_stats[0]: 0.25}
    else:  # 3
        stat_weights = {primary_stat: 0.60, secondary_stats[0]: 0.20, secondary_stats[1]: 0.20}

    # Load entity data
    try:
        with open(path_config.game_state_path, "r", encoding="utf-8") as f:
            game_state = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        raise RuntimeError(f"Cannot load game state: {e}")

    if entity_id is None or entity_id.lower() == "player":
        stats = game_state["player"]["stats"]
        player_skills = game_state["player"].get("skills", {})
        is_player = True
    else:
        npc_data = game_state["npcs"].get(entity_id, {})
        stats = npc_data.get("stats", {})
        player_skills = {}  # NPCs don't grow here
        is_player = False

    skill_used = normalize_skill_name(skill_used)

    # Calculate modifier
    avg_stat = sum(stats.get(stat, 10) for stat in stats_used) / num_stats
    stat_mod = (avg_stat - 10)

    skill_mod = 0
    if skill_used:
        if is_player:
            skill_mod = player_skills.get(skill_used, 0)
        else:
            skill_mod = 7  # NPC fallback

    total_bonus = stat_mod + skill_mod + situational_bonus

    # Roll
    natural_roll = weighted_roll(num_dice=4, die_sides=25)
    roll = natural_roll + total_bonus

    margin = roll - difficulty_class
    success = margin >= 0

    # Growth (player only) - applied immediately
    growth_added: Dict[str, float] = {}

    if is_player and success:
        # Base growth scales with difficulty
        base_growth = difficulty_class / 100.0
        # Margin multiplier: success gives more
        margin_mult = min(2.0, max(0.5, 1 + margin / 50.0))
        total_growth_raw = base_growth * margin_mult

        def get_scaled_delta(old_value: float) -> float:
            denominator = 15 + (abs(old_value) ** 1.6) / 5
            scale_factor = 1 / denominator
            starter_bonus = min(max(-0.15 * old_value + 4, 1), 4) * scale_factor
            return starter_bonus

        scale_stat = get_scaled_delta(avg_stat)
        scale_skill = get_scaled_delta(player_skills.get(skill_used, 0)) if skill_used else 0

        # Stats growth: 100% pool
        total_growth = total_growth_raw * scale_stat
        for stat, weight in stat_weights.items():
            added = total_growth * weight
            growth_added[stat] = growth_added.get(stat, 0) + added
            stats[stat] = stats.get(stat, 10) + added  # immediate apply

        # Skill growth: separate 100% pool
        if skill_used:
            skill_growth = total_growth_raw * scale_skill
            growth_added[skill_used] = growth_added.get(skill_used, 0) + skill_growth
            player_skills[skill_used] = player_skills.get(skill_used, 0) + skill_growth

        refresh_player_derived_maxima(game_state)

    # Save updated game state
    try:
        with open(path_config.game_state_path, "w", encoding="utf-8") as f:
            json.dump(game_state, f, indent=4)
    except Exception as e:
        print(f"Warning: Failed to save game state after growth: {e}")

    return {
        "success": success,
        "margin": margin,
        "roll": roll,
        "check_total": roll,
        "natural_roll": natural_roll,
        "avg_stat": avg_stat,
        "stat_mod": stat_mod,
        "total_bonus": total_bonus,
        "situational_bonus": situational_bonus,
        "growth_added": growth_added if is_player else {},
        "entity_id": entity_id or "player",
        "check_details": {
            "stats_used": stats_used,
            "skill_used": skill_used,
            "difficulty_class": difficulty_class
        }
    }

def load_racial_bias() -> Dict[str, int]:
    """Load racial bias data from CSV file."""
    bias: Dict[str, int] = {}
    try:
        with open(path_config.racial_bias_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            headers = [h.strip().lower() for h in reader.fieldnames[1:]]  # skip first column

            # Get player race
            with open(path_config.game_state_path, "r", encoding="utf-8") as gs_file:
                player_race = json.load(gs_file)["player"]["identity"]["race"].strip().lower()

            # Find player's row and extract biases
            for row in reader:
                actor = row.get(reader.fieldnames[0], "").strip().lower()
                if actor == player_race:
                    for target in headers:
                        try:
                            bias[target] = int(row[target.strip()])
                        except (ValueError, KeyError):
                            bias[target] = -20
                    break
    except Exception as e:
        print(f"Warning: Failed to load racial bias data: {e}")
        # Return default bias
        bias = {"human": 0, "elf": -5, "dwarf": 5, "orc": -10}

    return bias

def get_baseline_bias(actor_race: str, target_race: str) -> int:
    """
    Get baseline racial bias between two races.

    Args:
        actor_race: Race of the actor
        target_race: Race of the target

    Returns:
        Bias value (int)
    """
    csv_path = path_config.racial_bias_path
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            headers = [h.strip().lower() for h in reader.fieldnames[1:]]  # skip first column

            for row in reader:
                actor = row.get(reader.fieldnames[0], "").strip().lower()
                if actor == actor_race.strip().lower():
                    for target in headers:
                        if target == target_race.strip().lower():
                            return int(row[target.strip()])
    except Exception as e:
        print(f"Warning: Failed to get baseline bias: {e}")

    return -20  # Default bias if not found

def find_npc_id_by_name(npc_input: str, npcs_dict: Dict[str, Any]) -> Optional[str]:
    """
    Find the canonical NPC ID from input that could be:
    - The exact ID (key in npcs_dict, e.g. 'npc_kraelra')
    - Or the human-readable name (case-insensitive match on 'name' field)

    Args:
        npc_input: Input string (ID or name)
        npcs_dict: Dictionary of NPCs

    Returns:
        Matching NPC ID or None if not found
    """
    input_clean = npc_input.strip()

    # Step 1: Check if input is already an existing ID (fast path)
    if input_clean in npcs_dict:
        return input_clean

    # Step 2: Fall back to name search (case-insensitive)
    input_lower = input_clean.lower()
    for key, data in npcs_dict.items():
        name = str(get_character_field(data, "name", "")).strip().lower()
        if name == input_lower:
            return key

    return None

def init_npc_state(npc_name: str) -> Dict[str, Any]:
    """
    Fetch or create NPC social state using NPC name (not ID).

    Args:
        npc_name: Name or ID of NPC

    Returns:
        NPC state dictionary
    """
    try:
        with open(path_config.game_state_path, "r") as f:
            game_state = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Warning: Could not load game state: {e}")
        game_state = {"npcs": {}}

    npcs = game_state.get("npcs", {})

    # Step 1: Try to find existing NPC by name
    npc_id = find_npc_id_by_name(npc_name, npcs)

    if npc_id:
        # Found → load existing data
        npc_data = npcs[npc_id]
        NPC_STATE[npc_id] = {
            "trust": get_character_field(npc_data, "trust", 0.0),
            "npc_race": get_character_field(npc_data, "race", "human"),
            "deviation_range": get_character_field(npc_data, "deviation_range", 15),
            "tier": get_character_field(npc_data, "tier", 0),
            "relationship": get_character_field(npc_data, "relationship", "neutral")
        }

    return NPC_STATE.get(npc_id, {})

def update_npc_state(
    npc_input: str,                     # name or id
    **fields: Any
) -> None:
    """
    Update NPC state in game state file.

    Args:
        npc_input: NPC name or ID
        **fields: Fields to update
    """
    if not path_config.game_state_path.exists():
        print("Warning: game_state.json not found - update prevented")
        return

    try:
        with open(path_config.game_state_path, "r", encoding="utf-8") as f:
            game_state = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Warning: Could not load game state: {e}")
        return

    npcs = game_state.get("npcs", {})

    # Resolve input to canonical npc_id
    npc_id = find_npc_id_by_name(npc_input, npcs)

    if not npc_id:
        print(f"No matching NPC found for '{npc_input}' - skipping update")
        return

    # Now use the resolved npc_id for update
    npc_entry = game_state["npcs"].setdefault(npc_id, {"identity": {}})
    identity = get_character_identity(npc_entry)
    for field, value in fields.items():
        if field == "relationship":
            player_rel = identity.setdefault("relationships", {}).setdefault("player", {})
            if isinstance(player_rel, dict):
                player_rel["relationship"] = value
        elif field == "trust_level":
            identity["trust"] = value
        elif field == "emotional_response":
            identity["mood"] = value
        else:
            identity[field] = value

    # Save
    try:
        if not game_state or "npcs" not in game_state or not game_state["npcs"]:
            print("Refusing to save empty/invalid game_state")
            return
        with open(path_config.game_state_path, "w", encoding="utf-8") as f:
            json.dump(game_state, f, indent=4)
    except Exception as e:
        print(f"Write failed: {e}")

def calc_situational_mods(npc_name: str, rep_known: bool = False) -> float:
    """
    Calculate situational modifiers for social interactions.

    Args:
        npc_name: Name or ID of NPC
        rep_known: Whether reputation is known

    Returns:
        Situational modifier value
    """
    if not path_config.game_state_path.exists():
        print("Warning: game_state.json not found")
        return 0.0

    try:
        with open(path_config.game_state_path, "r") as f:
            game_state = json.load(f)
            player = game_state.get("player", {})
        npcs = game_state.get("npcs", {})
        if rep_known:
            reputation = player["identity"]["reputation"]
        else:
            reputation = 0
        npc_id = find_npc_id_by_name(npc_name, npcs)
        if npc_id:
            relationship = get_character_field(npcs.get(npc_id, {}), "relationship", "neutral")
            relation_mod = RELATIONSHIP_LEVELS.get(relationship, 0)
        else:
            # Fallback to racial bias
            npc_race = game_state.get("world", {}).get("location", {}).get("kingdom", "Human")
            relation_mod = get_baseline_bias(npc_race, player["identity"]["race"])
        situational_mods = reputation + relation_mod
        return situational_mods
    except Exception as e:
        print(f"Warning: Error calculating situational mods: {e}")
        return 0.0

def create_new_npc(
    name: str,
    sex: str,
    race: str,
    role: str,
    tier: int = 0,
    personality_reference: str = "Unknown",
    location: str = "Unknown",
    known_facts: Optional[List[str]] = None,
    mood: str = "neutral",
    relationship: str = "neutral"  # optional, defaults neutral
) -> str:
    """
    Create a new NPC entry in game_state.json.

    Args:
        name: NPC name
        sex: NPC sex
        race: NPC race
        role: NPC role
        tier: NPC tier (0=generic, 1+=persistent)
        personality_reference: Personality reference
        location: Starting location
        known_facts: List of known facts
        mood: Current mood
        relationship: Relationship to player

    Returns:
        Generated NPC ID
    """
    known_facts = known_facts or []
    sex = sex.strip().lower()
    race = race.strip().lower()

    # Generate canonical ID from name (sanitize)
    npc_id = f"npc_{name.lower().replace(' ', '_').replace('-', '_')}"

    # Load current game_state
    if path_config.game_state_path.exists():
        with open(path_config.game_state_path, "r", encoding="utf-8") as f:
            game_state = json.load(f)
    else:
        game_state = {"npcs": {}}

    # Backup first
    if path_config.game_state_path.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = path_config.backup_dir / f"game_state_backup_{timestamp}.json"
        shutil.copy(path_config.game_state_path, backup_path)

    # Clean old backups (keep 5 newest)
    backups = sorted(
        path_config.backup_dir.glob("game_state_backup_*.json"),
        key=os.path.getmtime,
        reverse=True
    )
    for old in backups[5:]:
        old.unlink()

    # Prevent overwrite of existing ID
    if npc_id in game_state.get("npcs", {}):
        print(f"Warning: NPC ID '{npc_id}' already exists - Rename!!")
        return "character entry not created"

    # Compute initial trust
    player_race = game_state.get("player", {}).get("identity", {}).get("race", "Human")
    bias = get_baseline_bias(race, player_race)
    deviation_range = random.choice([5, 7, 10, 15])
    trust = round(bias / 3) + random.uniform(-deviation_range, deviation_range)

    stat_block = generate_stats(race, sex)

    # Build new NPC entry
    new_npc = {
        "name": name,
        "sex": sex,
        "race": race,
        "role": role,
        "tier": tier,
        "stats": stat_block,
        "personality_reference": personality_reference,
        "trust": trust,
        "deviation_range": deviation_range,
        "location": location,
        "relationship": relationship,
        "known_facts": known_facts,
        "mood": mood
    }

    # Add to npcs
    game_state.setdefault("npcs", {})[npc_id] = new_npc

    # Save atomically
    try:
        with open(path_config.game_state_path, "w", encoding="utf-8") as f:
            json.dump(game_state, f, indent=4)
        print(f"Created NPC '{name}' with ID '{npc_id}'")
    except Exception as e:
        print(f"Save failed: {e}")

    return npc_id

def get_random_stat(min_val: int, avg_val: int, max_val: int) -> int:
    """
    Generate a random stat value using triangular distribution centered on avg.

    Args:
        min_val: Minimum value
        avg_val: Average/peak value
        max_val: Maximum value

    Returns:
        Random stat value
    """
    return int(random.triangular(min_val, max_val, avg_val))

RACIAL_STATS: Dict[str, Dict[str, List[int]]] = {}

def generate_stats(race: str, sex: str) -> Dict[str, int]:
    """
    Generate stats for a character based on race and sex.

    Args:
        race: Character race
        sex: Character sex

    Returns:
        Dictionary of generated stats
    """
    global RACIAL_STATS

    try:
        with open(path_config.base_stats_path, "r", encoding="utf-8") as f:
            RACIAL_STATS = json.load(f)
    except Exception as e:
        print(f"Warning: Failed to load base stats: {e}")
        # Fallback to default stats
        RACIAL_STATS = {
            "human": {"Str": [8, 10, 12], "Agi": [8, 10, 12], "Vit": [8, 10, 12],
                      "Ins": [8, 10, 12], "Will": [8, 10, 12], "Crea": [8, 10, 12]},
            "elf": {"Str": [6, 8, 10], "Agi": [10, 12, 14], "Vit": [6, 8, 10],
                   "Ins": [10, 12, 14], "Will": [8, 10, 12], "Crea": [8, 10, 12]},
            "dwarf": {"Str": [10, 12, 14], "Agi": [6, 8, 10], "Vit": [10, 12, 14],
                     "Ins": [8, 10, 12], "Will": [10, 12, 14], "Crea": [8, 10, 12]}
        }

    stats: Dict[str, int] = {}
    weight_factor = 1.5  # Tune this: 1.0 = no extra weight, 2.0+ = stronger pull to avg

    for stat_name, range_vals in RACIAL_STATS.get(race, RACIAL_STATS["human"]).items():
        min_val, avg_val, max_val = range_vals
        # Weighted mode pulls harder toward average
        weighted_avg = min_val + (avg_val - min_val) * weight_factor
        weighted_avg = max(min_val, min(max_val, weighted_avg))  # clamp
        stat_value = int(random.triangular(min_val, max_val, weighted_avg))
        stats[stat_name] = stat_value

    sex = sex.strip().lower()
    if sex == "female":
        stats["Agi"] += 2
        stats["Will"] += 1
        stats["Crea"] += 1
    elif sex == "male":
        stats["Str"] += 2
        stats["Vit"] += 2

    return stats

def add_item_to_container(
        container_id: str,
        item_id: str
) -> Tuple[bool, str]:
    """
    Attempts to add an item to a container.

    Args:
        container_id: ID of container
        item_id: ID of item to add

    Returns:
        Tuple of (success: bool, message: str)
    """
    if not path_config.game_state_path.exists():
        return False, "Game state file not found"

    # Load current state
    try:
        with open(path_config.game_state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return False, f"Failed to read game state: {str(e)}"

    player = state.get("player", {})
    inventory = player.get("inventory", {})

    # Validate container exists and is actually a container
    container = inventory.get(container_id)
    if not container:
        return False, f"Container '{container_id}' not found in inventory"

    if "container" not in container.get("tags", []):
        return False, f"'{container_id}' is not a container"

    # Get container properties
    max_capacity = container.get("capacity", 0)
    current_contents = container.get("contents", [])

    # Get item to add
    item = inventory.get(item_id)
    if not item:
        return False, f"Item '{item_id}' not found in inventory"

    if item.get("location") is not None:
        return False, f"Item '{item_id}' is already in '{item['location']}' — remove it first"

    item_weight = item.get("weight", 0) * item.get("qty", 1)  # support stacking

    # Calculate current total weight inside container
    current_weight = 0.0
    for cid in current_contents:
        citem = inventory.get(cid)
        if citem:
            current_weight += citem.get("weight", 0) * citem.get("qty", 1)

    # Check if it fits
    if current_weight + item_weight > max_capacity:
        return False, f"Cannot fit: exceeds capacity ({current_weight + item_weight:.2f} / {max_capacity:.2f} weight)"

    # Add reference (we don't move the item object — just reference it)
    if item_id not in current_contents:
        item["location"] = container_id
        current_contents.append(item_id)
        container["contents"] = current_contents

        # Save atomically
        try:
            with open(path_config.game_state_path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            return True, f"Added '{item_id}' to '{container_id}'"
        except OSError as e:
            return False, f"Failed to save game state: {str(e)}"
    else:
        return False, f"'{item_id}' is already in '{container_id}'"

def remove_item_from_container(
        container_id: str,
        item_id: str
) -> Tuple[bool, str]:
    """
    Removes an item from a container's contents (leaves item in top-level inventory).

    Args:
        container_id: ID of container
        item_id: ID of item to remove

    Returns:
        Tuple of (success: bool, message: str)
    """
    if not path_config.game_state_path.exists():
        return False, "Game state file not found"

    try:
        with open(path_config.game_state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return False, f"Failed to read game state: {str(e)}"

    player = state.get("player", {})
    inventory = player.get("inventory", {})

    container = inventory.get(container_id)
    if not container or "container" not in container.get("tags", []):
        return False, f"'{container_id}' not found or not a container"

    contents = container.get("contents", [])
    if item_id not in contents:
        return False, f"'{item_id}' not in '{container_id}'"

    item = inventory.get(item_id)
    item["location"] = None
    contents.remove(item_id)
    container["contents"] = contents

    try:
        with open(path_config.game_state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        return True, f"Removed '{item_id}' from '{container_id}' (still in inventory)"
    except OSError as e:
        return False, f"Failed to save game state: {str(e)}"

def remove_item_from_inventory(
        item_id: str
) -> Tuple[bool, str]:
    """
    Completely removes an item from inventory (and any container references).

    Args:
        item_id: ID of item to remove

    Returns:
        Tuple of (success: bool, message: str)
    """
    if not path_config.game_state_path.exists():
        return False, "Game state file not found"

    try:
        with open(path_config.game_state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return False, f"Failed to read game state: {str(e)}"

    player = state.get("player", {})
    inventory = player.get("inventory", {})

    if item_id not in inventory:
        return False, f"'{item_id}' not found in inventory"

    # Remove from any container's contents
    for inv_item in inventory.values():
        if "container" in inv_item.get("tags", []):
            contents = inv_item.get("contents", [])
            if item_id in contents:
                contents.remove(item_id)
                inv_item["contents"] = contents

    # Delete the item
    del inventory[item_id]

    try:
        with open(path_config.game_state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        return True, f"Removed '{item_id}' from inventory entirely"
    except OSError as e:
        return False, f"Failed to save game state: {str(e)}"

# Example usage (for testing):
if __name__ == "__main__":
    success, msg = add_item_to_container("backpack_001", "dagger_001")
    print(f"Success: {success} | {msg}")
