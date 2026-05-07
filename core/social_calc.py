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
from game_config import game_config
from helper_functions import (
    init_npc_state,
    load_racial_bias,
    calc_situational_mods,
    update_npc_state,
    weighted_roll,
    get_relationship_level,
    get_relationship_data,
    get_behavior_band,
    get_character_field,
    get_mood_band,
    get_mood_label,
    get_mood_score,
)

# Constants from rules
DENSITY_MULTIPLIERS = {
    "Hamlet": 0.2,
    "Village": 0.5,
    "Town": 1.0,
    "Large City": 1.5,
    "Capital": 2.5,
    "Trade Hub": 0.75,
}
SOCIAL_MOOD_MARGIN_MULTIPLIER = game_config.float("mechanics.social_mood_margin_multiplier", 0.5, min_value=0.0)

def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))

def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

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
    current_category = get_relationship_data(current_trust).get("category", "neutral")

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

    # Trust category modifiers - harder to change well-established relationships.
    if current_category == "hostile":
        personality_mod *= 0.5  # Very hard to improve
    elif current_category == "close_bond":
        personality_mod *= 0.6  # Hard to damage strong bonds
    elif current_category == "friendly":
        personality_mod *= 0.8

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
    old_mood_score = _coerce_float(state.get("mood", state.get("mood_score", 0)), 0)
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

    # Trust is already applied by GameEngine before this mechanical resolver.
    relationship_dc_mod = 0

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
    mood_delta = _clamp(margin * SOCIAL_MOOD_MARGIN_MULTIPLIER, -10, 10)
    new_mood_score = _clamp(old_mood_score + mood_delta, -30, 30)
    old_mood = get_mood_label(old_mood_score)
    new_mood = get_mood_label(new_mood_score)
    mood_band = get_mood_band(new_mood_score)
    behavior = new_mood

    # Determine if this was a significant relationship change
    relationship_changed = old_relationship != new_relationship

    # Update NPC state
    interaction_timestamp = datetime.now().isoformat()
    update_fields = {
        "trust": new_trust,
        "mood": new_mood_score,
        "last_interaction": interaction_timestamp,
    }

    # Add to interaction history
    interaction_record = {
        "timestamp": interaction_timestamp,
        "type": interaction_type,
        "old_trust": old_trust,
        "new_trust": new_trust,
        "old_relationship": old_relationship,
        "new_relationship": new_relationship,
        "old_mood_score": old_mood_score,
        "new_mood_score": new_mood_score,
        "old_mood": old_mood,
        "new_mood": new_mood,
        "mood_delta": mood_delta,
        "margin": margin,
        "location": location_density,
        "gift_value": gift_value if interaction_type == "gift" else 0
    }

    npc_data = _load_npc_data()
    if npc_id in npc_data["npcs"]:
        npc_entry = npc_data["npcs"][npc_id]
        if isinstance(npc_entry, dict):
            identity = npc_entry.setdefault("identity", {})
            if isinstance(identity, dict):
                identity.update(update_fields)
                history = identity.get("interaction_history", [])
                identity["interaction_history"] = (history if isinstance(history, list) else []) + [interaction_record]
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
        "relationship_description": get_relationship_data(new_trust).get("description", ""),
        "trust_category": get_relationship_data(new_trust).get("category", "neutral"),
        "old_mood_score": old_mood_score,
        "new_mood_score": new_mood_score,
        "mood_delta": mood_delta,
        "old_mood": old_mood,
        "new_mood": new_mood,
        "mood": new_mood_score,
        "mood_label": new_mood,
        "mood_description": mood_band.get("description", ""),
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
    history = get_character_field(npc, "interaction_history", [])

    # Summarize relationship progression
    relationship_changes = []
    current_trust = get_character_field(npc, "trust", 0)
    current_relationship = get_relationship_level(current_trust)

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
        "current_trust": current_trust,
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
    trust = get_character_field(npc, "trust", 0)
    mood_score = get_mood_score(npc, 0)
    relationship = get_relationship_level(trust)
    personality = npc.get("personality", {})

    # Get relationship details
    relationship_data = get_relationship_data(trust)

    # Calculate affinity components
    bias_dict = load_racial_bias()
    player_race = _get_player_race()
    racial_bias = bias_dict.get(str(get_character_field(npc, "race", "human")).lower(), -20)
    situational_mods = calc_situational_mods(npc_id)

    affinity = racial_bias + trust + situational_mods
    behavior = get_behavior_band(affinity)

    # Determine relationship trends
    history = get_character_field(npc, "interaction_history", [])
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
        "npc_name": get_character_field(npc, "name", "Unknown"),
        "current_relationship": relationship,
        "relationship_description": relationship_data["description"],
        "current_trust": trust,
        "current_mood": mood_score,
        "current_mood_label": get_mood_label(mood_score),
        "trust_range": relationship_data["trust"],
        "racial_bias": racial_bias,
        "situational_mods": situational_mods,
        "affinity": affinity,
        "behavior": behavior,
        "relationship_trend": trend,
        "interactions_count": len(history),
        "last_interaction": get_character_field(npc, "last_interaction", "Never"),
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
    summary_counts = {"close_bonds": 0, "friends": 0, "neutral": 0, "hostile": 0}

    for npc_id, npc in npc_data["npcs"].items():
        if npc.get("status") == "active":
            trust = get_character_field(npc, "trust", 0)
            mood_score = get_mood_score(npc, 0)
            relationship = get_relationship_level(trust)
            relationship_data = get_relationship_data(trust)
            category = relationship_data.get("category", "neutral")
            if category == "close_bond":
                summary_counts["close_bonds"] += 1
            elif category == "friendly":
                summary_counts["friends"] += 1
            elif category == "hostile":
                summary_counts["hostile"] += 1
            else:
                summary_counts["neutral"] += 1

            relationships.append({
                "npc_id": npc_id,
                "name": get_character_field(npc, "name", "Unknown"),
                "role": get_character_field(npc, "role", "Unknown"),
                "location": get_character_field(npc, "location", "Unknown"),
                "relationship": relationship,
                "trust": trust,
                "mood": mood_score,
                "mood_label": get_mood_label(mood_score),
                "relationship_description": relationship_data["description"],
                "last_interaction": get_character_field(npc, "last_interaction", "Never")
            })

    # Sort by trust level (highest first)
    relationships.sort(key=lambda x: x["trust"], reverse=True)

    return {
        "success": True,
        "relationships": relationships,
        "count": len(relationships),
        "summary": summary_counts
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
