# social_calc.py

import json
import os
import random
import math
import shutil
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from datetime import datetime
from path_config import path_config
from helper_functions import init_npc_state, load_racial_bias, calc_situational_mods, update_npc_state, weighted_roll

# Constants from rules
DENSITY_MULTIPLIERS = {
    "Hamlet": 0.2,
    "Village": 0.5,
    "Town": 1.0,
    "Large City": 1.5,
    "Capital": 2.5,
    "Trade Hub": 0.75,
}

# Relationship levels with trust ranges
RELATIONSHIP_LEVELS = {
    "mortal enemy": {"trust": (-100, -60), "description": "Will actively seek to harm or destroy"},
    "enemy": {"trust": (-59, -40), "description": "Hostile, will oppose at every opportunity"},
    "adversary": {"trust": (-39, -20), "description": "Distrustful, competitive, may sabotage"},
    "rival": {"trust": (-19, -10), "description": "Competitive but not openly hostile"},
    "neutral": {"trust": (-9, 9), "description": "Indifferent, no strong feelings"},
    "acquaintance": {"trust": (10, 20), "description": "Friendly but superficial"},
    "friend": {"trust": (21, 40), "description": "Genuine friendship, will help when convenient"},
    "close friend": {"trust": (41, 60), "description": "Strong bond, will make sacrifices"},
    "lover": {"trust": (61, 80), "description": "Romantic attachment, deep emotional connection"},
    "soulmate": {"trust": (81, 100), "description": "Unbreakable bond, will risk everything"}
}

# Behavior bands based on affinity (trust + bias + situational)
BEHAVIOR_BANDS = [
    (-float('inf'), -20, "hostile"),
    (-19, -5, "cold / obstructive"),
    (-4, 4, "neutral / transactional"),
    (5, 19, "helpful / cooperative"),
    (20, float('inf'), "protective / risk-taking")
]

def get_relationship_level(trust: float) -> str:
    """Get relationship level based on trust score."""
    for level, data in RELATIONSHIP_LEVELS.items():
        if data["trust"][0] <= trust <= data["trust"][1]:
            return level
    return "neutral"

def get_behavior_band(affinity: float) -> str:
    """Get behavior band based on affinity score."""
    for low, high, label in BEHAVIOR_BANDS:
        if low <= affinity <= high:
            return label
    return "unknown"

def calculate_relationship_change(
    current_trust: float,
    interaction_type: str,
    margin: float,
    personality_traits: Dict
) -> float:
    """
    Calculate relationship change based on interaction type, margin, and personality.

    Args:
        current_trust: Current trust level
        interaction_type: Type of interaction (appeal, offence, neutral, gift, etc.)
        margin: Margin of success/failure
        personality_traits: NPC's personality traits

    Returns:
        Trust change amount
    """
    # Get current relationship level
    current_relationship = get_relationship_level(current_trust)

    # Base trust change based on interaction type
    if interaction_type == "appeal":
        base_change = margin * 0.4 if margin > 0 else margin * 0.2
    elif interaction_type == "offence":
        base_change = -abs(margin) * 0.4 if margin > 0 else -abs(margin) * 0.2
    elif interaction_type == "gift":
        base_change = margin * 0.5
    elif interaction_type == "betrayal":
        base_change = -abs(margin) * 1.0
    elif interaction_type == "favor":
        base_change = margin * 0.6
    else:  # neutral
        base_change = margin * 0.1

    # Personality modifiers
    personality_mod = 1.0

    # Core trait modifiers
    core_trait = personality_traits.get("core_trait", "pragmatic")
    if core_trait in ["idealistic", "optimistic"]:
        personality_mod *= 1.2  # More forgiving, quicker to trust
    elif core_trait in ["cynical", "pragmatic"]:
        personality_mod *= 0.8  # Slower to trust

    # Social trait modifiers
    social_trait = personality_traits.get("social_trait", "friendly")
    if social_trait in ["friendly", "loyal"]:
        personality_mod *= 1.1
    elif social_trait in ["manipulative", "selfish"]:
        personality_mod *= 0.7

    # Relationship level modifiers - harder to change well-established relationships
    if current_relationship in ["mortal enemy", "enemy"]:
        personality_mod *= 0.5  # Very hard to improve
    elif current_relationship in ["soulmate", "lover"]:
        personality_mod *= 0.6  # Hard to damage strong bonds
    elif current_relationship in ["close friend", "friend"]:
        personality_mod *= 0.8
    elif current_relationship in ["adversary", "rival"]:
        personality_mod *= 1.2  # Easier to change competitive relationships

    # Apply modifiers
    final_change = base_change * personality_mod

    return final_change

def resolve_social_interaction(
        npc_id: str,
        interaction_type: str,  # "appeal", "offence", "neutral", "gift", "betrayal", "favor"
        difficulty_class: int = 50,  # Agent-provided baseline difficulty (higher = harder)
        location_density: str = "Town",
        gift_value: int = 0  # Value of gift if interaction_type is "gift"
) -> dict:
    """
    Resolve a social interaction with d100 roll.
    Higher difficulty_class = harder task.

    Args:
        npc_id: ID or name of NPC
        interaction_type: Type of interaction
        difficulty_class: Base difficulty (50 = average)
        location_density: Location type for density modifier
        gift_value: Value of gift for gift interactions

    Returns:
        Dictionary with interaction results
    """
    # Load NPC state
    state = init_npc_state(npc_id)
    if not state:
        return {
            "success": False,
            "message": f"NPC {npc_id} not found or invalid"
        }

    old_trust = state["trust"]
    deviation_range = state["deviation_range"]
    personality = state.get("personality", {})
    npc_race = state.get("npc_race", "Human")

    # Load racial bias
    bias_dict = load_racial_bias()
    bias = bias_dict.get(npc_race.lower(), -20)
    bias_adjust = DENSITY_MULTIPLIERS.get(location_density, 1.0)
    adjusted_bias = bias * bias_adjust

    # Situational modifiers
    situational_mods = calc_situational_mods(npc_id)

    # Adjust DC based on current relationship
    current_relationship = get_relationship_level(old_trust)
    relationship_dc_mod = 0

    if current_relationship in ["mortal enemy", "enemy"]:
        relationship_dc_mod = 20  # Much harder to interact positively
    elif current_relationship in ["adversary", "rival"]:
        relationship_dc_mod = 10  # Harder to interact
    elif current_relationship in ["close friend", "lover", "soulmate"]:
        relationship_dc_mod = -10  # Easier to interact
    elif current_relationship in ["friend", "acquaintance"]:
        relationship_dc_mod = -5  # Slightly easier

    adjusted_dc = max(10, min(100, difficulty_class + relationship_dc_mod))

    # Gift interaction special handling
    if interaction_type == "gift":
        # DC adjustment based on gift value and NPC personality
        gift_dc_reduction = min(30, gift_value / 20)  # 20 value = 1 DC reduction, max 30
        core_trait = personality.get("core_trait", "pragmatic")

        if core_trait in ["idealistic", "optimistic"]:
            gift_dc_reduction *= 1.5  # More impressed by gifts
        elif core_trait in ["cynical", "pragmatic"]:
            gift_dc_reduction *= 0.7  # Less impressed

        adjusted_dc = max(10, adjusted_dc - gift_dc_reduction)

    # Roll
    initial_roll = weighted_roll()
    roll = initial_roll + old_trust
    roll += random.uniform(-deviation_range, deviation_range)
    roll += situational_mods

    margin = roll - adjusted_dc
    success_flag = margin >= 0

    # Calculate trust change based on interaction type and personality
    trust_change = calculate_relationship_change(old_trust, interaction_type, margin, personality)

    # Apply soft scaling for trust changes
    denominator = 15 + (abs(old_trust) ** 1.6) / 5
    scale_factor = 1 / denominator
    starter_bonus = min(max(-.15*old_trust+2, 1), 4) * scale_factor
    dc_modifier = adjusted_dc / 100
    scaled_delta = trust_change * starter_bonus * dc_modifier

    # Update trust (no hard clamp, but track relationship changes)
    new_trust = old_trust + scaled_delta

    # Calculate new relationship level
    old_relationship = get_relationship_level(old_trust)
    new_relationship = get_relationship_level(new_trust)

    # Affinity calculations
    affinity_before = adjusted_bias + old_trust + situational_mods
    affinity_after = adjusted_bias + new_trust + situational_mods
    behavior = get_behavior_band(affinity_after)

    # Determine if this was a significant relationship change
    relationship_changed = old_relationship != new_relationship

    # Update NPC state
    update_fields = {
        "trust": new_trust,
        "relationship": new_relationship,
        "last_interaction": datetime.now().isoformat()
    }

    # Add to interaction history
    interaction_record = {
        "timestamp": datetime.now().isoformat(),
        "type": interaction_type,
        "old_trust": old_trust,
        "new_trust": new_trust,
        "old_relationship": old_relationship,
        "new_relationship": new_relationship,
        "margin": margin,
        "location": location_density,
        "gift_value": gift_value if interaction_type == "gift" else 0
    }

    npc_data = _load_npc_data()
    if npc_id in npc_data["npcs"]:
        npc_data["npcs"][npc_id]["interaction_history"] = npc_data["npcs"][npc_id].get("interaction_history", []) + [interaction_record]
        npc_data["npcs"][npc_id].update(update_fields)
        _save_npc_data(npc_data)

    # Return comprehensive results
    return {
        "success": success_flag,
        "margin": margin,
        "scaled_delta": scaled_delta,
        "old_trust": old_trust,
        "new_trust": new_trust,
        "trust_change": scaled_delta,
        "old_relationship": old_relationship,
        "new_relationship": new_relationship,
        "relationship_changed": relationship_changed,
        "relationship_description": RELATIONSHIP_LEVELS[new_relationship]["description"],
        "affinity_before": affinity_before,
        "affinity_after": affinity_after,
        "behavior": behavior,
        "adjusted_dc": adjusted_dc,
        "dc_adjustment": relationship_dc_mod,
        "initial_roll": initial_roll,
        "roll": roll,
        "interaction_record": interaction_record
    }

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
    """Reference NPC data is read-only; runtime social state is not persisted here."""
    return None

def get_relationship_history(npc_id: str) -> Dict:
    """
    Get the relationship history with an NPC.

    Args:
        npc_id: ID of the NPC

    Returns:
        Dictionary with relationship history
    """
    npc_data = _load_npc_data()
    if npc_id not in npc_data["npcs"]:
        return {
            "success": False,
            "message": f"NPC {npc_id} not found"
        }

    npc = npc_data["npcs"][npc_id]
    history = npc.get("interaction_history", [])

    # Summarize relationship progression
    relationship_changes = []
    current_relationship = npc.get("relationship", "neutral")

    for i, interaction in enumerate(history):
        if interaction.get("old_relationship") != interaction.get("new_relationship"):
            relationship_changes.append({
                "index": i,
                "timestamp": interaction["timestamp"],
                "from": interaction["old_relationship"],
                "to": interaction["new_relationship"],
                "type": interaction["type"],
                "trust_change": interaction["new_trust"] - interaction["old_trust"]
            })

    return {
        "success": True,
        "npc_id": npc_id,
        "current_relationship": current_relationship,
        "current_trust": npc.get("trust", 0),
        "relationship_history": relationship_changes,
        "full_interaction_history": history,
        "relationship_progression": len(relationship_changes)
    }

def get_npc_relationship_status(npc_id: str) -> Dict:
    """
    Get current relationship status with an NPC.

    Args:
        npc_id: ID of the NPC

    Returns:
        Dictionary with current relationship status
    """
    npc_data = _load_npc_data()
    if npc_id not in npc_data["npcs"]:
        return {
            "success": False,
            "message": f"NPC {npc_id} not found"
        }

    npc = npc_data["npcs"][npc_id]
    trust = npc.get("trust", 0)
    relationship = npc.get("relationship", "neutral")
    personality = npc.get("personality", {})

    # Get relationship details
    relationship_data = RELATIONSHIP_LEVELS.get(relationship, RELATIONSHIP_LEVELS["neutral"])

    # Calculate affinity components
    bias_dict = load_racial_bias()
    player_race = _get_player_race()
    racial_bias = bias_dict.get(npc.get("race", "human").lower(), -20)
    situational_mods = calc_situational_mods(npc_id)

    affinity = racial_bias + trust + situational_mods
    behavior = get_behavior_band(affinity)

    # Determine relationship trends
    history = npc.get("interaction_history", [])
    if len(history) >= 5:
        recent_trust_changes = [h["new_trust"] - h["old_trust"] for h in history[-5:]]
        avg_change = sum(recent_trust_changes) / len(recent_trust_changes)

        if avg_change > 1:
            trend = "improving_rapidly"
        elif avg_change > 0.2:
            trend = "improving"
        elif avg_change < -1:
            trend = "worsening_rapidly"
        elif avg_change < -0.2:
            trend = "worsening"
        else:
            trend = "stable"
    else:
        trend = "insufficient_data"

    return {
        "success": True,
        "npc_id": npc_id,
        "npc_name": npc.get("name", "Unknown"),
        "current_relationship": relationship,
        "relationship_description": relationship_data["description"],
        "current_trust": trust,
        "trust_range": relationship_data["trust"],
        "racial_bias": racial_bias,
        "situational_mods": situational_mods,
        "affinity": affinity,
        "behavior": behavior,
        "relationship_trend": trend,
        "interactions_count": len(history),
        "last_interaction": npc.get("last_interaction", "Never"),
        "personality_summary": {
            "core_trait": personality.get("core_trait", "unknown"),
            "social_trait": personality.get("social_trait", "unknown"),
            "likes": personality.get("likes", []),
            "dislikes": personality.get("dislikes", [])
        }
    }

def _get_player_race() -> str:
    """Get player's race from game state."""
    try:
        with open(path_config.game_state_path, "r", encoding="utf-8") as f:
            game_state = json.load(f)
        return game_state.get("player", {}).get("identity", {}).get("race", "Human")
    except Exception as e:
        print(f"Warning: Could not get player race: {e}")
        return "Human"

def get_all_relationships() -> Dict:
    """
    Get summary of all NPC relationships.

    Returns:
        Dictionary with all relationship summaries
    """
    npc_data = _load_npc_data()
    relationships = []

    for npc_id, npc in npc_data["npcs"].items():
        if npc.get("status") == "active":
            trust = npc.get("trust", 0)
            relationship = npc.get("relationship", "neutral")
            relationship_data = RELATIONSHIP_LEVELS.get(relationship, RELATIONSHIP_LEVELS["neutral"])

            relationships.append({
                "npc_id": npc_id,
                "name": npc.get("name", "Unknown"),
                "role": npc.get("role", "Unknown"),
                "location": npc.get("location", "Unknown"),
                "relationship": relationship,
                "trust": trust,
                "relationship_description": relationship_data["description"],
                "last_interaction": npc.get("last_interaction", "Never")
            })

    # Sort by trust level (highest first)
    relationships.sort(key=lambda x: x["trust"], reverse=True)

    return {
        "success": True,
        "relationships": relationships,
        "count": len(relationships),
        "summary": {
            "close_bonds": sum(1 for r in relationships if r["relationship"] in ["close friend", "lover", "soulmate"]),
            "friends": sum(1 for r in relationships if r["relationship"] in ["friend", "acquaintance"]),
            "neutral": sum(1 for r in relationships if r["relationship"] == "neutral"),
            "hostile": sum(1 for r in relationships if r["relationship"] in ["mortal enemy", "enemy", "adversary", "rival"])
        }
    }

# Example usage
if __name__ == "__main__":
    # Test different interaction types
    print("=== Testing Social Interactions ===")

    # Appeal interaction
    result = resolve_social_interaction(
        npc_id="npc_kraelra",
        interaction_type="appeal",
        difficulty_class=25,
        location_density="Town"
    )
    print("\nAppeal Interaction:")
    print(f"Success: {result['success']}, Margin: {result['margin']}")
    print(f"Trust: {result['old_trust']:.1f} → {result['new_trust']:.1f}")
    print(f"Relationship: {result['old_relationship']} → {result['new_relationship']}")
    print(f"Behavior: {result['behavior']}")

    # Gift interaction
    result = resolve_social_interaction(
        npc_id="npc_kraelra",
        interaction_type="gift",
        difficulty_class=30,
        location_density="Town",
        gift_value=100  # Valuable gift
    )
    print("\nGift Interaction (value 100):")
    print(f"Success: {result['success']}, Margin: {result['margin']}")
    print(f"Trust: {result['old_trust']:.1f} → {result['new_trust']:.1f}")
    print(f"Relationship: {result['old_relationship']} → {result['new_relationship']}")

    # Get relationship status
    status = get_npc_relationship_status("npc_kraelra")
    print("\nRelationship Status:")
    print(f"Current Relationship: {status['current_relationship']} ({status['relationship_description']})")
    print(f"Trust: {status['current_trust']:.1f} (Range: {status['trust_range']})")
    print(f"Behavior: {status['behavior']}, Trend: {status['relationship_trend']}")

    # Get all relationships
    all_rels = get_all_relationships()
    print(f"\nAll Relationships ({all_rels['count']} total):")
    for rel in all_rels["relationships"]:
        print(f"  {rel['name']}: {rel['relationship']} (Trust: {rel['trust']:.1f})")
