# npc_manager.py
import json
import os
import random
import shutil
import glob
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from path_config import path_config
from helper_functions import generate_stats, get_baseline_bias

# Personality traits
PERSONALITY_TRAITS = {
    "core": ["pragmatic", "idealistic", "cynical", "optimistic", "stoic", "emotional", "curious", "reserved"],
    "social": ["friendly", "aloof", "charismatic", "awkward", "manipulative", "honest", "loyal", "selfish"],
    "work_ethic": ["diligent", "lazy", "perfectionist", "careless", "ambitious", "content", "creative", "methodical"],
    "attitude": ["cheerful", "gloomy", "confident", "insecure", "patient", "impulsive", "brave", "cautious"]
}

# Voice styles
VOICE_STYLES = {
    "formal": "Uses proper grammar and formal language",
    "casual": "Relaxed and informal speech",
    "gruff": "Rough and direct speech",
    "elegant": "Refined and sophisticated language",
    "blunt": "Direct and to the point",
    "wordy": "Uses many words to express ideas",
    "poetic": "Uses metaphorical and flowery language",
    "technical": "Uses precise and technical terms"
}

# Speech quirks
SPEECH_QUIRKS = [
    "frequent pauses",
    "ends sentences with questions",
    "uses many metaphors",
    "speaks in riddles",
    "repeats phrases",
    "uses old proverbs",
    "mumbles occasionally",
    "speaks very loudly",
    "whispers often",
    "uses hand gestures",
    "taps foot when thinking",
    "plays with hair/beard",
    "avoids eye contact",
    "stares intensely"
]

def _backup_npc_data():
    """Create backup of NPC data."""
    npc_file = path_config.references_dir / "npcs.json"
    if npc_file.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = path_config.backup_dir / f"npcs_backup_{ts}.json"
        shutil.copy(npc_file, backup_path)

        # Keep only 5 newest backups
        backups = sorted(
            path_config.backup_dir.glob("npcs_backup_*.json"),
            key=os.path.getmtime,
            reverse=True
        )
        for old in backups[5:]:
            old.unlink()

def _load_npc_data() -> Dict:
    """Load NPC data from file."""
    npc_file = path_config.references_dir / "npcs.json"
    if npc_file.exists():
        try:
            with open(npc_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: Could not load NPC data: {e}")
    return {"npcs": {}}

def _save_npc_data(data: Dict):
    """Save NPC data with backup."""
    _backup_npc_data()
    npc_file = path_config.references_dir / "npcs.json"
    with open(npc_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def _generate_unique_npc_id(name: str) -> str:
    """Generate a unique NPC ID based on name."""
    base_id = name.lower().replace(" ", "_").replace("-", "_")
    npc_data = _load_npc_data()

    counter = 1
    npc_id = f"npc_{base_id}"
    while npc_id in npc_data["npcs"]:
        npc_id = f"npc_{base_id}_{counter}"
        counter += 1

    return npc_id

def _generate_personality() -> Dict:
    """Generate a random personality profile for an NPC."""
    return {
        "core_trait": random.choice(PERSONALITY_TRAITS["core"]),
        "social_trait": random.choice(PERSONALITY_TRAITS["social"]),
        "work_ethic": random.choice(PERSONALITY_TRAITS["work_ethic"]),
        "attitude": random.choice(PERSONALITY_TRAITS["attitude"]),
        "likes": [random.choice(["music", "food", "books", "nature", "animals", "art", "weapons", "magic"]),
                 random.choice(["adventure", "peace", "wealth", "knowledge", "power", "friendship", "family"])],
        "dislikes": [random.choice(["violence", "dishonesty", "cowardice", "arrogance", "greed", "ignorance"]),
                    random.choice(["demons", "undead", "magic", "technology", "authority", "change"])],
        "fears": random.choice(["failure", "loneliness", "darkness", "magic", "death", "betrayal", "the unknown"]),
        "motivations": random.choice(["wealth", "power", "knowledge", "justice", "revenge", "protection", "freedom"])
    }

def _generate_voice_profile(npc_name: str, personality: Dict) -> Dict:
    """Generate a voice profile for an NPC."""
    return {
        "core_personality": f"{personality['core_trait'].capitalize()} {npc_name} who {personality['social_trait']} and {personality['attitude']}",
        "speech_style": random.choice(list(VOICE_STYLES.keys())),
        "quirks": random.sample(SPEECH_QUIRKS, k=random.randint(2, 4)),
        "example_dialogue": [
            f"{npc_name} {random.choice(['nods', 'smiles', 'frowns', 'laughs'])}. '{random.choice(['That sounds interesting', 'I have my doubts', 'Tell me more', 'I see your point'])}.'",
            f"'{random.choice(['By the gods!', 'Well, well', 'Hmm', 'Ah', 'Oh'])}', {npc_name} {random.choice(['exclaims', 'muses', 'says', 'replies'])}.",
            f"{npc_name} {random.choice(['leans in', 'crosses arms', 'shifts uncomfortably'])}. '{random.choice(['What do you think?', 'Are you sure?', 'Is that so?', 'Really now?'])}'"
        ],
        "forbidden": [
            random.choice(["modern slang", "flowery language", "technical jargon", "vulgarity"]),
            random.choice(["long speeches", "emotional outbursts", "lying", "boasting"])
        ]
    }

def create_npc(
    name: str,
    sex: str,
    race: str,
    role: str,
    age: int = None,
    faction: str = "none",
    location: str = "unknown",
    tier: int = 1,
    personality: Dict = None,
    inventory: Dict = None,
    relationships: Dict = None
) -> Dict:
    """
    Create a new NPC with comprehensive details.

    Args:
        name: NPC name
        sex: NPC sex (male/female/other)
        race: NPC race
        role: NPC role/profession
        age: NPC age (optional)
        faction: NPC faction/affiliation
        location: Starting location
        tier: NPC importance (1=minor, 2=significant, 3=major)
        personality: Custom personality (optional)
        inventory: Starting inventory (optional)
        relationships: Starting relationships (optional)

    Returns:
        Dictionary with NPC details and success status
    """
    # Generate NPC ID
    npc_id = _generate_unique_npc_id(name)

    # Set default values
    age = age or random.randint(18, 60)
    sex = sex.lower()

    # Generate personality if not provided
    if personality is None:
        personality = _generate_personality()

    # Generate voice profile
    voice_profile = _generate_voice_profile(name, personality)

    # Generate stats
    stats = generate_stats(race, sex)

    # Set base trust based on personality
    core_trait = personality["core_trait"]
    if core_trait in ["pragmatic", "stoic", "reserved"]:
        base_trust = 0
    elif core_trait in ["idealistic", "optimistic", "curious"]:
        base_trust = 5
    else:
        base_trust = -5

    # Create NPC data
    npc_data = {
        "npc_id": npc_id,
        "name": name,
        "sex": sex,
        "race": race,
        "age": age,
        "role": role,
        "faction": faction,
        "location": location,
        "tier": tier,
        "stats": stats,
        "personality": personality,
        "voice_profile": voice_profile,
        "trust": base_trust,
        "deviation_range": random.choice([5, 7, 10, 15]),
        "relationship": "neutral",
        "mood": "neutral",
        "status": "active",
        "inventory": inventory or {},
        "relationships": relationships or {},
        "known_facts": [],
        "quests_involved": [],
        "last_interaction": None,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }

    # Add to NPC data
    npc_file_data = _load_npc_data()
    npc_file_data["npcs"][npc_id] = npc_data
    _save_npc_data(npc_file_data)

    return {
        "success": True,
        "message": f"Created NPC '{name}' with ID '{npc_id}'",
        "npc_id": npc_id,
        "npc_data": npc_data
    }

def get_npc(npc_id: str) -> Dict:
    """
    Get detailed information about an NPC.

    Args:
        npc_id: ID of the NPC

    Returns:
        Dictionary with NPC details
    """
    npc_data = _load_npc_data()
    if npc_id not in npc_data["npcs"]:
        return {
            "success": False,
            "message": f"NPC {npc_id} not found"
        }

    return {
        "success": True,
        "npc": npc_data["npcs"][npc_id]
    }

def update_npc(npc_id: str, updates: Dict) -> Dict:
    """
    Update NPC information.

    Args:
        npc_id: ID of the NPC to update
        updates: Dictionary of fields to update

    Returns:
        Dictionary with success status
    """
    npc_data = _load_npc_data()
    if npc_id not in npc_data["npcs"]:
        return {
            "success": False,
            "message": f"NPC {npc_id} not found"
        }

    # Update fields
    npc_data["npcs"][npc_id].update(updates)
    npc_data["npcs"][npc_id]["updated_at"] = datetime.now().isoformat()

    _save_npc_data(npc_data)

    return {
        "success": True,
        "message": f"Updated NPC {npc_id}",
        "updated_fields": list(updates.keys())
    }

def update_npc_location(npc_id: str, new_location: str) -> Dict:
    """
    Update an NPC's location.

    Args:
        npc_id: ID of the NPC
        new_location: New location

    Returns:
        Dictionary with success status
    """
    return update_npc(npc_id, {
        "location": new_location,
        "last_seen": datetime.now().isoformat()
    })

def update_npc_relationship(npc_id: str, target_id: str, relationship: str) -> Dict:
    """
    Update an NPC's relationship with another character.

    Args:
        npc_id: ID of the NPC
        target_id: ID of the target (player or another NPC)
        relationship: New relationship status

    Returns:
        Dictionary with success status
    """
    npc_data = _load_npc_data()
    if npc_id not in npc_data["npcs"]:
        return {
            "success": False,
            "message": f"NPC {npc_id} not found"
        }

    # Update relationship
    relationships = npc_data["npcs"][npc_id].setdefault("relationships", {})
    relationships[target_id] = {
        "relationship": relationship,
        "last_updated": datetime.now().isoformat()
    }

    npc_data["npcs"][npc_id]["updated_at"] = datetime.now().isoformat()
    _save_npc_data(npc_data)

    return {
        "success": True,
        "message": f"Updated relationship between {npc_id} and {target_id} to {relationship}"
    }

def update_npc_mood(npc_id: str, new_mood: str) -> Dict:
    """
    Update an NPC's current mood.

    Args:
        npc_id: ID of the NPC
        new_mood: New mood

    Returns:
        Dictionary with success status
    """
    return update_npc(npc_id, {
        "mood": new_mood,
        "mood_updated_at": datetime.now().isoformat()
    })

def add_npc_inventory_item(npc_id: str, item_data: Dict) -> Dict:
    """
    Add an item to an NPC's inventory.

    Args:
        npc_id: ID of the NPC
        item_data: Dictionary containing item properties

    Returns:
        Dictionary with success status
    """
    npc_data = _load_npc_data()
    if npc_id not in npc_data["npcs"]:
        return {
            "success": False,
            "message": f"NPC {npc_id} not found"
        }

    # Generate unique item ID
    base_name = item_data.get("archetype", "item").lower().replace(" ", "_")
    item_id = f"{base_name}_{random.randint(10000, 99999)}"

    # Add to inventory
    inventory = npc_data["npcs"][npc_id].setdefault("inventory", {})
    inventory[item_id] = item_data

    npc_data["npcs"][npc_id]["updated_at"] = datetime.now().isoformat()
    _save_npc_data(npc_data)

    return {
        "success": True,
        "message": f"Added item to {npc_id}'s inventory",
        "item_id": item_id
    }

def remove_npc_inventory_item(npc_id: str, item_id: str) -> Dict:
    """
    Remove an item from an NPC's inventory.

    Args:
        npc_id: ID of the NPC
        item_id: ID of the item to remove

    Returns:
        Dictionary with success status
    """
    npc_data = _load_npc_data()
    if npc_id not in npc_data["npcs"]:
        return {
            "success": False,
            "message": f"NPC {npc_id} not found"
        }

    inventory = npc_data["npcs"][npc_id].get("inventory", {})
    if item_id not in inventory:
        return {
            "success": False,
            "message": f"Item {item_id} not found in {npc_id}'s inventory"
        }

    # Remove item
    del inventory[item_id]
    npc_data["npcs"][npc_id]["updated_at"] = datetime.now().isoformat()
    _save_npc_data(npc_data)

    return {
        "success": True,
        "message": f"Removed item {item_id} from {npc_id}'s inventory"
    }

def get_npcs_by_location(location: str) -> Dict:
    """
    Get all NPCs at a specific location.

    Args:
        location: Location to search

    Returns:
        Dictionary with list of NPCs at the location
    """
    npc_data = _load_npc_data()
    npcs_at_location = []

    for npc_id, npc_info in npc_data["npcs"].items():
        if npc_info.get("location") == location and npc_info.get("status") == "active":
            npcs_at_location.append({
                "npc_id": npc_id,
                "name": npc_info["name"],
                "role": npc_info["role"],
                "faction": npc_info["faction"],
                "relationship": npc_info.get("relationship", "neutral"),
                "mood": npc_info.get("mood", "neutral")
            })

    return {
        "success": True,
        "location": location,
        "npcs": npcs_at_location,
        "count": len(npcs_at_location)
    }

def get_npcs_by_faction(faction: str) -> Dict:
    """
    Get all NPCs belonging to a specific faction.

    Args:
        faction: Faction to search

    Returns:
        Dictionary with list of NPCs in the faction
    """
    npc_data = _load_npc_data()
    npcs_in_faction = []

    for npc_id, npc_info in npc_data["npcs"].items():
        if npc_info.get("faction") == faction and npc_info.get("status") == "active":
            npcs_in_faction.append({
                "npc_id": npc_id,
                "name": npc_info["name"],
                "role": npc_info["role"],
                "location": npc_info.get("location", "unknown"),
                "relationship": npc_info.get("relationship", "neutral")
            })

    return {
        "success": True,
        "faction": faction,
        "npcs": npcs_in_faction,
        "count": len(npcs_in_faction)
    }

def get_npc_relationships(npc_id: str) -> Dict:
    """
    Get all relationships for an NPC.

    Args:
        npc_id: ID of the NPC

    Returns:
        Dictionary with relationship information
    """
    npc_data = _load_npc_data()
    if npc_id not in npc_data["npcs"]:
        return {
            "success": False,
            "message": f"NPC {npc_id} not found"
        }

    npc_info = npc_data["npcs"][npc_id]
    relationships = npc_info.get("relationships", {})

    return {
        "success": True,
        "npc_id": npc_id,
        "relationships": relationships
    }

def sync_npcs_to_game_state() -> Dict:
    """
    Synchronize NPC data with the game state file.

    Returns:
        Dictionary with synchronization results
    """
    try:
        # Load NPC data
        npc_data = _load_npc_data()

        # Load game state
        with open(path_config.game_state_path, "r", encoding="utf-8") as f:
            game_state = json.load(f)

        # Update game state with NPC data
        game_state["npcs"] = npc_data["npcs"]

        # Save game state
        with open(path_config.game_state_path, "w", encoding="utf-8") as f:
            json.dump(game_state, f, indent=4)

        return {
            "success": True,
            "message": "NPC data synchronized with game state",
            "npc_count": len(npc_data["npcs"])
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to synchronize NPC data: {str(e)}"
        }

def generate_random_npc(location: str = "unknown", faction: str = "none") -> Dict:
    """
    Generate a random NPC with all required details.

    Args:
        location: Starting location
        faction: Faction affiliation

    Returns:
        Dictionary with created NPC details
    """
    # Random attributes
    first_names = {
        "male": ["Eldrin", "Thalion", "Borin", "Garrick", "Lirien", "Dain", "Faelan", "Kael", "Riven", "Toren"],
        "female": ["Lyra", "Mirabel", "Eowyn", "Aelara", "Isolde", "Seraphina", "Calista", "Elara", "Sylvie", "Vaelith"]
    }

    last_names = ["Ironfoot", "Stormborn", "Whisperwind", "Shadowblade", "Brightman", "Darkwood", "Frostbeard", "Stoneheart", "Moonshadow", "Riverstride"]

    sexes = ["male", "female"]
    races = ["human", "dwarf", "elf", "beastfolk", "demon"]
    roles = ["merchant", "guard", "scholar", "artisan", "hunter", "scout", "priest", "mage", "farmer", "innkeeper"]

    # Generate random NPC
    sex = random.choice(sexes)
    first_name = random.choice(first_names[sex])
    last_name = random.choice(last_names)
    full_name = f"{first_name} {last_name}"
    race = random.choice(races)
    role = random.choice(roles)
    age = random.randint(18, 60)
    tier = random.choice([1, 1, 1, 2])  # Mostly minor NPCs

    return create_npc(
        name=full_name,
        sex=sex,
        race=race,
        role=role,
        age=age,
        faction=faction,
        location=location,
        tier=tier
    )

def get_npc_summary() -> Dict:
    """
    Get a summary of all NPCs in the system.

    Returns:
        Dictionary with NPC statistics
    """
    npc_data = _load_npc_data()
    npcs = npc_data["npcs"]

    summary = {
        "total_npcs": len(npcs),
        "active_npcs": sum(1 for npc in npcs.values() if npc.get("status") == "active"),
        "by_tier": {},
        "by_race": {},
        "by_faction": {},
        "by_location": {}
    }

    for npc_id, npc_info in npcs.items():
        if npc_info.get("status") != "active":
            continue

        # Tier summary
        tier = npc_info.get("tier", 1)
        summary["by_tier"][tier] = summary["by_tier"].get(tier, 0) + 1

        # Race summary
        race = npc_info.get("race", "unknown")
        summary["by_race"][race] = summary["by_race"].get(race, 0) + 1

        # Faction summary
        faction = npc_info.get("faction", "none")
        summary["by_faction"][faction] = summary["by_faction"].get(faction, 0) + 1

        # Location summary
        location = npc_info.get("location", "unknown")
        summary["by_location"][location] = summary["by_location"].get(location, 0) + 1

    return {
        "success": True,
        "summary": summary
    }

# Example usage
if __name__ == "__main__":
    # Create a test NPC
    test_npc = create_npc(
        name="Test Character",
        sex="male",
        race="human",
        role="merchant",
        location="Daejon",
        faction="merchants_guild"
    )
    print("Created test NPC:", test_npc)

    # Get the NPC details
    npc_details = get_npc(test_npc["npc_id"])
    print("\nNPC details:", json.dumps(npc_details["npc"], indent=2))

    # Generate a random NPC
    random_npc = generate_random_npc(location="Daejon", faction="adventurers_guild")
    print("\nGenerated random NPC:", random_npc)

    # Get summary
    summary = get_npc_summary()
    print("\nNPC summary:", summary)
