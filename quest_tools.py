# quest_tools.py
import json
import os
import random
import shutil
import glob
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from path_config import path_config
from helper_functions import roll_generic_check

# Quest categories
QUEST_CATEGORIES = {
    "event": "Event/Obstacle",
    "assignment": "NPC Assignment"
}

# Quest types
QUEST_TYPES = {
    "event": [
        "random_encounter",
        "monster_attack",
        "natural_hazard",
        "mystery_investigation",
        "survival_challenge"
    ],
    "assignment": [
        "fetch_quest",
        "hunt_quest",
        "delivery_quest",
        "escort_quest",
        "research_quest",
        "crafting_quest"
    ]
}

# Difficulty levels
DIFFICULTY_LEVELS = {
    "trivial": 15,
    "easy": 25,
    "moderate": 50,
    "challenging": 75,
    "epic": 100
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

def _load_game_state():
    """Load game state from file."""
    try:
        with open(path_config.game_state_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Could not load game state: {e}")
        return {"player": {}, "quests": {}, "npcs": {}}

def generate_random_encounter_quest(location: str = "wilderness") -> Dict:
    """
    Generate a random encounter quest (event category).

    Args:
        location: Location where the encounter occurs

    Returns:
        Dictionary with quest details
    """
    # Determine encounter type based on location
    encounter_types = {
        "wilderness": ["bandit_ambush", "wild_animal_attack", "lost_traveler", "abandoned_camp"],
        "forest": ["monster_encounter", "herb_gathering", "hunting_opportunity", "ancient_ruins"],
        "dungeon": ["monster_nest", "trapped_room", "puzzle_chamber", "hidden_treasure"],
        "city": ["street_brawl", "pickpocket_attempt", "mysterious_stranger", "urban_legend"],
        "road": ["bandit_ambush", "merchant_caravan", "broken_wagon", "roadside_shrine"]
    }

    encounter_type = random.choice(encounter_types.get(location, encounter_types["wilderness"]))

    # Generate quest details
    quest_id = f"quest_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    difficulty = random.choice(["trivial", "easy", "moderate", "challenging"])

    # Base quest template
    quest = {
        "quest_id": quest_id,
        "category": "event",
        "type": "random_encounter",
        "title": "",
        "description": "",
        "location": location,
        "difficulty": difficulty,
        "difficulty_dc": DIFFICULTY_LEVELS[difficulty],
        "objectives": [],
        "completion_conditions": [],
        "rewards": {
            "items": "scavenging_only",
            "gold": 0,
            "reputation": 0
        },
        "status": "active",
        "acceptance_date": datetime.now().isoformat(),
        "completion_date": None,
        "failed": False,
        "hidden": False
    }

    # Customize based on encounter type
    if encounter_type == "bandit_ambush":
        quest["title"] = "Bandit Ambush"
        quest["description"] = f"You are ambushed by bandits while traveling through {location}. Defend yourself or find a way to escape."
        quest["objectives"] = ["Survive the bandit ambush"]
        quest["completion_conditions"] = ["bandits_defeated_or_escaped"]
        quest["rewards"]["description"] = "Practice combat skills and potentially scavenge items from defeated bandits."

    elif encounter_type == "wild_animal_attack":
        animal = random.choice(["wolves", "bears", "wild boars", "giant snakes"])
        quest["title"] = f"Wild {animal} Attack"
        quest["description"] = f"A pack of {animal} attacks you in the {location}. Defend yourself or find a way to calm them."
        quest["objectives"] = [f"Survive the {animal} attack"]
        quest["completion_conditions"] = [f"{animal}_defeated_or_calmed"]
        quest["rewards"]["description"] = "Practice combat/survival skills and potentially scavenge animal parts."

    elif encounter_type == "monster_encounter":
        monster = random.choice(["goblins", "orcs", "trolls", "giant spiders"])
        quest["title"] = f"Monster Encounter: {monster}"
        quest["description"] = f"You encounter a group of {monster} in the {location}. They look hostile!"
        quest["objectives"] = [f"Deal with the {monster} threat"]
        quest["completion_conditions"] = [f"{monster}_defeated_or_avoided"]
        quest["rewards"]["description"] = "Practice combat skills and potentially scavenge monster remains."

    elif encounter_type == "natural_hazard":
        hazard = random.choice(["flash flood", "rockslide", "forest fire", "quick sand"])
        quest["title"] = f"Natural Hazard: {hazard}"
        quest["description"] = f"You encounter a dangerous {hazard} in the {location}. Find a way to survive!"
        quest["objectives"] = [f"Survive the {hazard}"]
        quest["completion_conditions"] = [f"{hazard}_survived"]
        quest["rewards"]["description"] = "Practice survival skills and potentially find items in the aftermath."

    elif encounter_type == "lost_traveler":
        quest["title"] = "Lost Traveler"
        quest["description"] = f"You come across a lost traveler in the {location}. They seem injured and disoriented."
        quest["objectives"] = ["Help the lost traveler or continue on your way"]
        quest["completion_conditions"] = ["traveler_helped_or_left"]
        quest["rewards"]["description"] = "Potential reputation gain if helped, plus information or goodwill from the encounter."

    elif encounter_type == "mysterious_stranger":
        quest["title"] = "Mysterious Stranger"
        quest["description"] = f"A mysterious figure approaches you in the {location}. They have an unusual request or information."
        quest["objectives"] = ["Listen to the stranger's story and decide how to respond"]
        quest["completion_conditions"] = ["stranger_interaction_completed"]
        quest["rewards"]["description"] = "Potential information gain or social consequences."

    return quest

def generate_npc_assignment_quest(npc_id: str, quest_type: str = None) -> Dict:
    """
    Generate an NPC assignment quest.

    Args:
        npc_id: ID of the NPC giving the quest
        quest_type: Specific type of assignment quest

    Returns:
        Dictionary with quest details
    """
    game_state = _load_game_state()
    npc = game_state["npcs"].get(npc_id, {})

    if not npc:
        return {"success": False, "message": "NPC not found"}

    # Determine quest type if not specified
    if not quest_type:
        quest_type = random.choice(QUEST_TYPES["assignment"])

    # Generate quest ID
    quest_id = f"quest_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # Base quest template
    quest = {
        "quest_id": quest_id,
        "category": "assignment",
        "type": quest_type,
        "title": "",
        "description": "",
        "giver": npc_id,
        "giver_name": npc.get("name", "Unknown"),
        "location": npc.get("location", "unknown"),
        "difficulty": "moderate",
        "difficulty_dc": 50,
        "objectives": [],
        "completion_conditions": [],
        "rewards": {
            "items": [],
            "gold": 0,
            "reputation": 0
        },
        "status": "active",
        "acceptance_date": datetime.now().isoformat(),
        "completion_date": None,
        "failed": False,
        "hidden": False
    }

    # Customize based on quest type
    if quest_type == "fetch_quest":
        item_type = random.choice(["herbs", "minerals", "animal parts", "ancient artifacts"])
        item_name = f"rare {item_type}"
        quest["title"] = f"Fetch Quest: {item_name}"
        quest["description"] = f"{npc.get('name', 'The NPC')} needs {item_name} for {random.choice(['a potion', 'a ritual', 'their research', 'a customer'])}. Retrieve {random.randint(3, 8)} samples."
        quest["objectives"] = [f"Find and collect {item_name}"]
        quest["completion_conditions"] = [f"{item_name}_collected"]
        quest["rewards"]["gold"] = random.randint(50, 200)
        quest["rewards"]["reputation"] = random.randint(1, 5)
        quest["rewards"]["description"] = f"Receive payment and reputation gain from {npc.get('name', 'the NPC')}."

    elif quest_type == "hunt_quest":
        target = random.choice(["wolves", "bandits", "monsters", "rare creatures"])
        quest["title"] = f"Hunt Quest: {target}"
        quest["description"] = f"{npc.get('name', 'The NPC')} offers a bounty for {target} that have been causing trouble. Eliminate {random.randint(2, 6)} of them."
        quest["objectives"] = [f"Hunt down {target}", f"Bring proof of elimination"]
        quest["completion_conditions"] = [f"{target}_eliminated", "proof_returned"]
        quest["rewards"]["gold"] = random.randint(100, 500)
        quest["rewards"]["reputation"] = random.randint(3, 10)
        quest["rewards"]["items"].append("hunter's_token")
        quest["rewards"]["description"] = f"Receive bounty payment, reputation gain, and a hunter's token from {npc.get('name', 'the NPC')}."

    elif quest_type == "delivery_quest":
        destination = random.choice(["nearby town", "distant city", "hidden village", "mountain fortress"])
        item = random.choice(["package", "letter", "artifact", "supplies"])
        quest["title"] = f"Delivery Quest: {item} to {destination}"
        quest["description"] = f"{npc.get('name', 'The NPC')} needs you to deliver a {item} to {destination}. It's {random.choice(['urgent', 'valuable', 'secret', 'fragile'])}."
        quest["objectives"] = [f"Take the {item}", f"Deliver to {destination}", "Return with confirmation"]
        quest["completion_conditions"] = [f"{item}_delivered", "confirmation_received"]
        quest["rewards"]["gold"] = random.randint(200, 800)
        quest["rewards"]["reputation"] = random.randint(5, 15)
        quest["rewards"]["description"] = f"Receive payment and reputation gain from {npc.get('name', 'the NPC')} for successful delivery."

    elif quest_type == "escort_quest":
        person = random.choice(["merchant", "noble", "scholar", "pilgrim"])
        destination = random.choice(["nearby town", "sacred site", "academy", "capital city"])
        quest["title"] = f"Escort Quest: {person} to {destination}"
        quest["description"] = f"A {person} named {random.choice(['Eldrin', 'Lyra', 'Thalion', 'Mirabel'])} needs safe passage to {destination}. Protect them from dangers along the way."
        quest["objectives"] = [f"Meet the {person}", f"Escort safely to {destination}", "Deal with any threats"]
        quest["completion_conditions"] = [f"{person}_arrived_safely", "threats_handled"]
        quest["rewards"]["gold"] = random.randint(300, 1200)
        quest["rewards"]["reputation"] = random.randint(10, 20)
        quest["rewards"]["items"].append(f"{person}_favor")
        quest["rewards"]["description"] = f"Receive payment, reputation gain, and a favor from the {person}."

    elif quest_type == "research_quest":
        subject = random.choice(["ancient ruins", "magical phenomenon", "rare creature", "lost civilization"])
        quest["title"] = f"Research Quest: {subject}"
        quest["description"] = f"{npc.get('name', 'The NPC')}, a {random.choice(['scholar', 'mage', 'historian'])}, needs information about {subject}. Gather data and report back."
        quest["objectives"] = [f"Investigate {subject}", "Collect information", "Report findings"]
        quest["completion_conditions"] = [f"{subject}_researched", "findings_reported"]
        quest["rewards"]["gold"] = random.randint(150, 600)
        quest["rewards"]["reputation"] = random.randint(5, 15)
        quest["rewards"]["items"].append("scholar's_gratitude")
        quest["rewards"]["description"] = f"Receive payment, reputation gain, and scholarly recognition."

    elif quest_type == "crafting_quest":
        item_type = random.choice(["weapon", "armor", "potion", "enchanted item"])
        material = random.choice(["mythril", "dragon scales", "rare herbs", "ancient runes"])
        quest["title"] = f"Crafting Quest: {item_type} with {material}"
        quest["description"] = f"{npc.get('name', 'The NPC')} wants a {item_type} made from {material}. Craft it and deliver it to them."
        quest["objectives"] = [f"Gather {material}", f"Craft the {item_type}", "Deliver finished item"]
        quest["completion_conditions"] = [f"{material}_gathered", f"{item_type}_crafted", "item_delivered"]
        quest["rewards"]["gold"] = random.randint(500, 2000)
        quest["rewards"]["reputation"] = random.randint(15, 25)
        quest["rewards"]["items"].append("master_crafter's_mark")
        quest["rewards"]["description"] = f"Receive payment, reputation gain, and recognition as a master crafter."

    # Adjust difficulty based on quest details
    if "dangerous" in quest["description"].lower() or "eliminate" in quest["description"].lower():
        quest["difficulty"] = random.choice(["challenging", "epic"])
        quest["difficulty_dc"] = DIFFICULTY_LEVELS[quest["difficulty"]]

    return quest

def add_quest_to_journal(quest_data: Dict) -> Dict:
    """
    Add a quest to the player's journal.

    Args:
        quest_data: Dictionary containing quest details

    Returns:
        Dictionary with success status and quest ID
    """
    game_state = _load_game_state()

    # Initialize quest journal if it doesn't exist
    if "quests" not in game_state:
        game_state["quests"] = {}

    # Generate quest ID if not provided
    if "quest_id" not in quest_data:
        quest_data["quest_id"] = f"quest_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    quest_id = quest_data["quest_id"]

    # Check if quest already exists
    if quest_id in game_state["quests"]:
        return {
            "success": False,
            "message": f"Quest {quest_id} already exists in journal",
            "quest_id": quest_id
        }

    # Add quest to journal
    game_state["quests"][quest_id] = quest_data

    # Save game state
    _backup_and_save(game_state)

    return {
        "success": True,
        "message": f"Quest '{quest_data.get('title', 'Untitled')}' added to journal",
        "quest_id": quest_id
    }

def update_quest_progress(quest_id: str, objective_completed: str = None, status: str = None) -> Dict:
    """
    Update the progress of a quest.

    Args:
        quest_id: ID of the quest to update
        objective_completed: Objective that was completed
        status: New status (active, completed, failed)

    Returns:
        Dictionary with success status and updated quest details
    """
    game_state = _load_game_state()

    if "quests" not in game_state or quest_id not in game_state["quests"]:
        return {
            "success": False,
            "message": f"Quest {quest_id} not found in journal"
        }

    quest = game_state["quests"][quest_id]

    # Update objective progress if provided
    if objective_completed and "objectives" in quest:
        if objective_completed not in quest.get("completed_objectives", []):
            quest.setdefault("completed_objectives", []).append(objective_completed)

    # Update status if provided
    if status:
        quest["status"] = status
        if status == "completed":
            quest["completion_date"] = datetime.now().isoformat()
        elif status == "failed":
            quest["failed"] = True

    # Check if all objectives are completed
    if "objectives" in quest and "completed_objectives" in quest:
        all_objectives = set(quest["objectives"])
        completed_objectives = set(quest["completed_objectives"])

        if len(completed_objectives) >= len(all_objectives):
            quest["status"] = "completed"
            quest["completion_date"] = datetime.now().isoformat()

    # Save game state
    _backup_and_save(game_state)

    return {
        "success": True,
        "message": f"Quest {quest_id} updated",
        "quest": quest
    }

def complete_quest(quest_id: str) -> Dict:
    """
    Mark a quest as completed and distribute rewards.

    Args:
        quest_id: ID of the quest to complete

    Returns:
        Dictionary with success status and reward details
    """
    game_state = _load_game_state()

    if "quests" not in game_state or quest_id not in game_state["quests"]:
        return {
            "success": False,
            "message": f"Quest {quest_id} not found in journal"
        }

    quest = game_state["quests"][quest_id]

    if quest["status"] == "completed":
        return {
            "success": False,
            "message": f"Quest {quest_id} is already completed"
        }

    # Mark quest as completed
    quest["status"] = "completed"
    quest["completion_date"] = datetime.now().isoformat()

    # Distribute rewards
    rewards_distributed = {}

    # Item rewards
    if quest["rewards"].get("items"):
        if quest["rewards"]["items"] == "scavenging_only":
            rewards_distributed["items"] = "Items obtained through scavenging during quest"
        else:
            inventory = game_state["player"].setdefault("inventory", {})
            for item in quest["rewards"]["items"]:
                item_id = f"reward_{item}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                inventory[item_id] = {
                    "archetype": item,
                    "tags": ["quest_reward"],
                    "description": f"Reward from quest: {quest.get('title', 'Untitled')}",
                    "location": None,
                    "qty": 1
                }
                rewards_distributed.setdefault("items", []).append(item)

    # Gold rewards
    if quest["rewards"].get("gold", 0) > 0:
        player = game_state.setdefault("player", {})
        current_gold = player.get("gold", 0)
        player["gold"] = current_gold + quest["rewards"]["gold"]
        rewards_distributed["gold"] = quest["rewards"]["gold"]

    # Reputation rewards
    if quest["rewards"].get("reputation", 0) > 0:
        player = game_state.setdefault("player", {})
        identity = player.setdefault("identity", {})
        current_rep = identity.get("reputation", 0)
        identity["reputation"] = current_rep + quest["rewards"]["reputation"]
        rewards_distributed["reputation"] = quest["rewards"]["reputation"]

    # Save game state
    _backup_and_save(game_state)

    return {
        "success": True,
        "message": f"Quest {quest_id} completed successfully",
        "quest_title": quest.get("title", "Untitled"),
        "rewards_distributed": rewards_distributed,
        "completion_date": quest["completion_date"]
    }

def fail_quest(quest_id: str) -> Dict:
    """
    Mark a quest as failed.

    Args:
        quest_id: ID of the quest to fail

    Returns:
        Dictionary with success status
    """
    game_state = _load_game_state()

    if "quests" not in game_state or quest_id not in game_state["quests"]:
        return {
            "success": False,
            "message": f"Quest {quest_id} not found in journal"
        }

    quest = game_state["quests"][quest_id]

    if quest["status"] == "completed":
        return {
            "success": False,
            "message": f"Quest {quest_id} is already completed and cannot be failed"
        }

    if quest["status"] == "failed":
        return {
            "success": False,
            "message": f"Quest {quest_id} is already marked as failed"
        }

    # Mark quest as failed
    quest["status"] = "failed"
    quest["failed"] = True
    quest["completion_date"] = datetime.now().isoformat()

    # Apply any penalties for failing
    penalties = {}

    # Reputation penalty for assignment quests
    if quest["category"] == "assignment":
        player = game_state.setdefault("player", {})
        identity = player.setdefault("identity", {})
        current_rep = identity.get("reputation", 0)
        rep_penalty = max(1, quest["difficulty_dc"] // 20)
        identity["reputation"] = max(0, current_rep - rep_penalty)
        penalties["reputation"] = -rep_penalty

    # Save game state
    _backup_and_save(game_state)

    return {
        "success": True,
        "message": f"Quest {quest_id} marked as failed",
        "quest_title": quest.get("title", "Untitled"),
        "penalties_applied": penalties
    }

def get_active_quests() -> Dict:
    """
    Get a list of all active quests.

    Returns:
        Dictionary with list of active quests
    """
    game_state = _load_game_state()

    if "quests" not in game_state:
        return {
            "success": True,
            "active_quests": [],
            "count": 0
        }

    active_quests = []
    for quest_id, quest_data in game_state["quests"].items():
        if quest_data.get("status") == "active" and not quest_data.get("hidden", False):
            active_quests.append({
                "quest_id": quest_id,
                "title": quest_data.get("title", "Untitled"),
                "category": quest_data.get("category", "unknown"),
                "type": quest_data.get("type", "unknown"),
                "location": quest_data.get("location", "unknown"),
                "difficulty": quest_data.get("difficulty", "moderate"),
                "objectives": quest_data.get("objectives", []),
                "completed_objectives": quest_data.get("completed_objectives", []),
                "acceptance_date": quest_data.get("acceptance_date", "unknown")
            })

    return {
        "success": True,
        "active_quests": active_quests,
        "count": len(active_quests)
    }

def get_completed_quests() -> Dict:
    """
    Get a list of all completed quests.

    Returns:
        Dictionary with list of completed quests
    """
    game_state = _load_game_state()

    if "quests" not in game_state:
        return {
            "success": True,
            "completed_quests": [],
            "count": 0
        }

    completed_quests = []
    for quest_id, quest_data in game_state["quests"].items():
        if quest_data.get("status") == "completed":
            completed_quests.append({
                "quest_id": quest_id,
                "title": quest_data.get("title", "Untitled"),
                "category": quest_data.get("category", "unknown"),
                "type": quest_data.get("type", "unknown"),
                "completion_date": quest_data.get("completion_date", "unknown"),
                "rewards": quest_data.get("rewards", {})
            })

    return {
        "success": True,
        "completed_quests": completed_quests,
        "count": len(completed_quests)
    }

def get_quest_details(quest_id: str) -> Dict:
    """
    Get detailed information about a specific quest.

    Args:
        quest_id: ID of the quest

    Returns:
        Dictionary with quest details
    """
    game_state = _load_game_state()

    if "quests" not in game_state or quest_id not in game_state["quests"]:
        return {
            "success": False,
            "message": f"Quest {quest_id} not found"
        }

    quest_data = game_state["quests"][quest_id]

    # Calculate progress
    total_objectives = len(quest_data.get("objectives", []))
    completed_objectives = len(quest_data.get("completed_objectives", []))
    progress = (completed_objectives / total_objectives * 100) if total_objectives > 0 else 0

    return {
        "success": True,
        "quest": {
            "quest_id": quest_id,
            "title": quest_data.get("title", "Untitled"),
            "category": quest_data.get("category", "unknown"),
            "type": quest_data.get("type", "unknown"),
            "description": quest_data.get("description", "No description"),
            "location": quest_data.get("location", "unknown"),
            "difficulty": quest_data.get("difficulty", "moderate"),
            "difficulty_dc": quest_data.get("difficulty_dc", 50),
            "status": quest_data.get("status", "unknown"),
            "acceptance_date": quest_data.get("acceptance_date", "unknown"),
            "completion_date": quest_data.get("completion_date", None),
            "failed": quest_data.get("failed", False),
            "objectives": quest_data.get("objectives", []),
            "completed_objectives": quest_data.get("completed_objectives", []),
            "progress_percentage": round(progress, 1),
            "rewards": quest_data.get("rewards", {}),
            "giver": quest_data.get("giver", None),
            "giver_name": quest_data.get("giver_name", None),
            "hidden": quest_data.get("hidden", False)
        }
    }

def abandon_quest(quest_id: str) -> Dict:
    """
    Abandon an active quest.

    Args:
        quest_id: ID of the quest to abandon

    Returns:
        Dictionary with success status
    """
    game_state = _load_game_state()

    if "quests" not in game_state or quest_id not in game_state["quests"]:
        return {
            "success": False,
            "message": f"Quest {quest_id} not found in journal"
        }

    quest = game_state["quests"][quest_id]

    if quest["status"] != "active":
        return {
            "success": False,
            "message": f"Quest {quest_id} is not active and cannot be abandoned"
        }

    # Mark quest as abandoned
    quest["status"] = "abandoned"
    quest["abandoned_date"] = datetime.now().isoformat()

    # Apply reputation penalty for assignment quests
    penalties = {}

    if quest["category"] == "assignment":
        player = game_state.setdefault("player", {})
        identity = player.setdefault("identity", {})
        current_rep = identity.get("reputation", 0)
        rep_penalty = max(1, quest["difficulty_dc"] // 30)
        identity["reputation"] = max(0, current_rep - rep_penalty)
        penalties["reputation"] = -rep_penalty

    # Save game state
    _backup_and_save(game_state)

    return {
        "success": True,
        "message": f"Quest {quest_id} abandoned",
        "quest_title": quest.get("title", "Untitled"),
        "penalties_applied": penalties
    }

def generate_quest_summary() -> Dict:
    """
    Generate a summary of all quests.

    Returns:
        Dictionary with quest summary statistics
    """
    game_state = _load_game_state()

    if "quests" not in game_state:
        return {
            "success": True,
            "total_quests": 0,
            "active_quests": 0,
            "completed_quests": 0,
            "failed_quests": 0,
            "abandoned_quests": 0,
            "by_category": {},
            "by_difficulty": {}
        }

    stats = {
        "total_quests": 0,
        "active_quests": 0,
        "completed_quests": 0,
        "failed_quests": 0,
        "abandoned_quests": 0,
        "by_category": {},
        "by_difficulty": {}
    }

    for quest_id, quest_data in game_state["quests"].items():
        stats["total_quests"] += 1

        status = quest_data.get("status", "unknown")
        if status == "active":
            stats["active_quests"] += 1
        elif status == "completed":
            stats["completed_quests"] += 1
        elif status == "failed":
            stats["failed_quests"] += 1
        elif status == "abandoned":
            stats["abandoned_quests"] += 1

        # Category stats
        category = quest_data.get("category", "unknown")
        stats["by_category"][category] = stats["by_category"].get(category, 0) + 1

        # Difficulty stats
        difficulty = quest_data.get("difficulty", "unknown")
        stats["by_difficulty"][difficulty] = stats["by_difficulty"].get(difficulty, 0) + 1

    return {
        "success": True,
        **stats
    }

# Example usage
if __name__ == "__main__":
    # Generate and add a random encounter quest
    encounter_quest = generate_random_encounter_quest("forest")
    print("Generated random encounter quest:")
    print(json.dumps(encounter_quest, indent=2))

    add_result = add_quest_to_journal(encounter_quest)
    print(f"\nAdded to journal: {add_result}")

    # Generate and add an NPC assignment quest
    assignment_quest = generate_npc_assignment_quest("npc_kraelra", "hunt_quest")
    print("\nGenerated NPC assignment quest:")
    print(json.dumps(assignment_quest, indent=2))

    add_result2 = add_quest_to_journal(assignment_quest)
    print(f"\nAdded to journal: {add_result2}")

    # Get active quests
    active_quests = get_active_quests()
    print(f"\nActive quests: {active_quests}")

    # Get quest details
    if active_quests["count"] > 0:
        first_quest_id = active_quests["active_quests"][0]["quest_id"]
        details = get_quest_details(first_quest_id)
        print(f"\nDetails for first quest:")
        print(json.dumps(details, indent=2))
