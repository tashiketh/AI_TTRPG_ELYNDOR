# enhanced_social_calc_fixed.py
import json
import random
from typing import Dict, Any, List, Optional
from pathlib import Path
from path_config import path_config
from api_integration import APIManager
from social_calc import resolve_social_interaction as resolve_social_mechanics
import logging
import os

logger = logging.getLogger("EnhancedSocialCalc")

class EnhancedSocialCalculator:
    def __init__(self, api_manager: APIManager):
        self.api = api_manager
        self.npc_data_cache = {}

    def _identity(self, npc_data: Dict[str, Any]) -> Dict[str, Any]:
        identity = npc_data.get("identity") if isinstance(npc_data, dict) else {}
        return identity if isinstance(identity, dict) else npc_data

    def _get_npc_field(self, npc_data: Dict[str, Any], field: str, default: Any = None) -> Any:
        identity = self._identity(npc_data)
        if field in identity:
            return identity.get(field, default)
        if field == "relationship":
            player_rel = identity.get("relationships", {}).get("player", {})
            if isinstance(player_rel, dict):
                return player_rel.get("relationship", default)
        if field == "interaction_history":
            player_rel = identity.get("relationships", {}).get("player", {})
            if isinstance(player_rel, dict):
                return player_rel.get("interaction_history", default)
        return npc_data.get(field, default)

    def _set_npc_field(self, npc_data: Dict[str, Any], field: str, value: Any):
        identity = npc_data.setdefault("identity", {})
        if field == "relationship":
            player_rel = identity.setdefault("relationships", {}).setdefault("player", {})
            if isinstance(player_rel, dict):
                player_rel["relationship"] = value
            return
        if field == "interaction_history":
            player_rel = identity.setdefault("relationships", {}).setdefault("player", {})
            if isinstance(player_rel, dict):
                player_rel["interaction_history"] = value
            return
        if field == "last_interaction":
            player_rel = identity.setdefault("relationships", {}).setdefault("player", {})
            if isinstance(player_rel, dict):
                player_rel["last_interaction"] = value
            return
        if field == "emotional_response":
            field = "mood"
        if field == "trust_level":
            field = "trust"
        identity[field] = value

    def resolve_social_interaction(self, npc_id: str, interaction_type: str,
                                 player_action: str, difficulty_class: int = 50,
                                 story_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Enhanced social interaction resolution with API integration"""
        # Load NPC data
        npc_data = self._load_npc_data(npc_id)
        if not npc_data:
            return self._generate_error_response(f"NPC {npc_id} not found")

        # Prepare context for API
        api_context = self._prepare_social_context(
            npc_data, interaction_type, player_action, difficulty_class
        )

        social_result = self._resolve_mechanical_social_result(
            npc_id=npc_id,
            interaction_type=interaction_type,
            difficulty_class=difficulty_class,
            npc_data=npc_data,
        )

        # Generate narrative
        narrative_context = self._prepare_narrative_context(npc_data, social_result, player_action, story_context)
        narrative = self.api.call_api("narrative_generation", narrative_context)

        # Generate NPC dialogue
        dialogue_context = self._prepare_dialogue_context(npc_data, social_result, story_context)
        dialogue = self.api.call_api("dialogue_generation", dialogue_context)

        # Combine results
        final_response = self._combine_responses(npc_id, npc_data, social_result, narrative, dialogue)
        final_response.setdefault("metadata", {})
        final_response["metadata"]["interaction_type"] = interaction_type
        final_response["metadata"]["player_action"] = player_action

        # Update NPC state
        self._update_npc_state(npc_id, final_response)

        return final_response

    def _map_interaction_type(self, interaction_type: str) -> str:
        """Map model-facing interaction labels to social_calc's mechanical labels."""
        normalized = str(interaction_type or "appeal").strip().lower()
        return {
            "comfort": "appeal",
            "reassure": "appeal",
            "reassurance": "appeal",
            "recruitment": "favor",
            "persuasion": "appeal",
            "bargaining": "appeal",
            "deception": "appeal",
            "interrogation": "appeal",
            "demand": "offence",
            "threat": "offence",
            "intimidation": "offence",
            "flattery": "appeal",
        }.get(normalized, normalized if normalized in {"appeal", "offence", "neutral", "gift", "betrayal", "favor"} else "appeal")

    def _resolve_mechanical_social_result(self, npc_id: str, interaction_type: str,
                                          difficulty_class: int,
                                          npc_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Use social_calc.py for deterministic social DC/roll/trust mechanics."""
        self._ensure_npc_in_game_state(npc_id, npc_data or {})
        mechanical_type = self._map_interaction_type(interaction_type)
        result = resolve_social_mechanics(
            npc_id=npc_id,
            interaction_type=mechanical_type,
            difficulty_class=difficulty_class,
            location_density="Town",
        )
        if "message" in result and "success" in result and "adjusted_dc" not in result:
            return {
                "success": False,
                "trust_change": 0,
                "relationship_changed": False,
                "old_relationship": "neutral",
                "new_relationship": "neutral",
                "emotional_response": "uncertain",
                "consequences": [result["message"]],
                "margin": 0,
                "difficulty_class": difficulty_class,
                "adjusted_dc": difficulty_class,
                "mechanical_interaction_type": mechanical_type,
                "source": "social_calc",
            }
        return {
            "success": result.get("success", False),
            "trust_change": result.get("trust_change", 0),
            "relationship_changed": result.get("relationship_changed", False),
            "old_relationship": result.get("old_relationship", "neutral"),
            "new_relationship": result.get("new_relationship", "neutral"),
            "emotional_response": result.get("behavior", "neutral"),
            "consequences": [f"Behavior band: {result.get('behavior', 'unknown')}"],
            "margin": result.get("margin", 0),
            "roll": result.get("roll"),
            "initial_roll": result.get("initial_roll"),
            "difficulty_class": difficulty_class,
            "adjusted_dc": result.get("adjusted_dc", difficulty_class),
            "dc_adjustment": result.get("dc_adjustment", 0),
            "old_trust": result.get("old_trust"),
            "new_trust": result.get("new_trust"),
            "mechanical_interaction_type": mechanical_type,
            "source": "social_calc",
        }

    def _ensure_npc_in_game_state(self, npc_id: str, npc_data: Dict[str, Any]):
        """Ensure social_calc can read reference NPCs from the active save."""
        try:
            if not path_config.game_state_path.exists():
                return
            with open(path_config.game_state_path, "r", encoding="utf-8") as f:
                game_state = json.load(f)
            npcs = game_state.setdefault("npcs", {})
            if npc_id not in npcs:
                npcs[npc_id] = dict(npc_data) if npc_data else {"npc_id": npc_id}
                npcs[npc_id]["npc_id"] = npc_id
                with open(path_config.game_state_path, "w", encoding="utf-8") as f:
                    json.dump(game_state, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to ensure NPC in game state for social_calc: {e}")

    def _load_npc_data(self, npc_id: str) -> Optional[Dict[str, Any]]:
        """Load NPC data from cache or file"""
        if npc_id in self.npc_data_cache:
            return self.npc_data_cache[npc_id]

        try:
            # Try to load from game state first
            game_state_path = path_config.game_state_path
            if game_state_path.exists():
                with open(game_state_path, "r", encoding="utf-8") as f:
                    game_state = json.load(f)
                if "npcs" in game_state and npc_id in game_state["npcs"]:
                    self.npc_data_cache[npc_id] = game_state["npcs"][npc_id]
                    return game_state["npcs"][npc_id]

            # Fallback to NPC data file
            npc_file = path_config.references_dir / "npcs.json"
            if npc_file.exists():
                with open(npc_file, "r", encoding="utf-8") as f:
                    npc_data = json.load(f)
                if npc_id in npc_data.get("npcs", {}):
                    self.npc_data_cache[npc_id] = npc_data["npcs"][npc_id]
                    return npc_data["npcs"][npc_id]

            return None
        except Exception as e:
            logger.error(f"Failed to load NPC data for {npc_id}: {str(e)}")
            return None

    def _prepare_social_context(self, npc_data: Dict, interaction_type: str,
                              player_action: str, difficulty_class: int) -> Dict[str, Any]:
        """Prepare optimized context for social resolution API call"""
        # Get current game state
        game_state = self._load_game_state()
        npc_id = npc_data.get("npc_id", "unknown_npc")
        npc_name = self._get_npc_field(npc_data, "name", npc_id)
        npc_race = self._get_npc_field(npc_data, "race", "unknown")
        trust = self._coerce_number(self._get_npc_field(npc_data, "trust", 0), 0)

        # Safely extract active quest titles
        active_quest_titles = []
        quests_data = game_state.get("quests", {})
        if isinstance(quests_data, dict):
            for quest_list in quests_data.values():
                if isinstance(quest_list, list):
                    for quest in quest_list:
                        if isinstance(quest, dict):
                            active_quest_titles.append(quest.get("title", "Unknown"))

        return {
            "player_action": player_action,
            "interaction_type": interaction_type,
            "difficulty_class": difficulty_class,
            "npc_profile": {
                "name": npc_name,
                "race": npc_race,
                "personality": self._get_npc_field(npc_data, "personality", {}),
                "relationship_with_player": self._get_npc_field(npc_data, "relationship", "neutral"),
                "current_mood": self._get_npc_field(npc_data, "mood", "neutral"),
                "trust": trust,
                "deviation_range": self._get_npc_field(npc_data, "deviation_range", 10)
            },
            "game_state": {
                "location": game_state.get("world", {}).get("location", {}).get("settlement", "unknown"),
                "player_reputation": game_state.get("player", {}).get("identity", {}).get("reputation", 0),
                "active_quests": active_quest_titles
            },
            "interaction_history": self._get_recent_interactions(npc_data, limit=3),
            "racial_bias": self._get_racial_bias(npc_race),
            "situational_modifiers": self._calculate_situational_mods(npc_data)
        }

    def _prepare_narrative_context(self, npc_data: Dict, social_result: Dict,
                                  player_action: str,
                                  story_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Prepare context for narrative generation"""
        npc_id = npc_data.get("npc_id", "unknown_npc")
        npc_name = self._get_npc_field(npc_data, "name", npc_id)
        npc_race = self._get_npc_field(npc_data, "race", "unknown")
        return {
            "social_result": social_result,
            "npc_name": npc_name,
            "npc_race": npc_race,
            "npc_personality": self._get_npc_field(npc_data, "personality", {}),
            "current_relationship": social_result.get("new_relationship",
                                                     self._get_npc_field(npc_data, "relationship", "neutral")),
            "trust_change": social_result.get("trust_change", 0),
            "emotional_response": social_result.get("emotional_response", "neutral"),
            "player_action": player_action,
            "story_context": story_context or {},
            "location": self._get_current_location(),
            "time_of_day": self._get_current_time()
        }

    def _prepare_dialogue_context(self, npc_data: Dict, social_result: Dict,
                                  story_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Prepare context for NPC dialogue generation"""
        return {
            "npc_voice_profile": self._get_npc_field(npc_data, "voice_profile", {}),
            "current_mood": social_result.get("emotional_response", self._get_npc_field(npc_data, "mood", "neutral")),
            "relationship": social_result.get("new_relationship", self._get_npc_field(npc_data, "relationship", "neutral")),
            "interaction_success": social_result.get("success", False),
            "trust": social_result.get("new_trust", self._get_npc_field(npc_data, "trust", 0)),
            "player_action": social_result.get("player_action", ""),
            "consequences": social_result.get("consequences", []),
            "story_context": story_context or {},
            "forbidden_phrases": self._get_npc_field(npc_data, "voice_profile", {}).get("forbidden", [])
        }

    def _combine_responses(self, npc_id: str, npc_data: Dict, social_result: Dict,
                           narrative: Dict, dialogue: Dict) -> Dict[str, Any]:
        """Combine all API responses into final structure"""
        return {
            "narrative": narrative.get("narrative", "The NPC responds to your request."),
            "social_result": {
                "success": social_result.get("success", False),
                "trust_change": social_result.get("trust_change", 0),
                "relationship_change": social_result.get("relationship_changed", False),
                "new_relationship": social_result.get("new_relationship", "neutral"),
                "emotional_response": social_result.get("emotional_response", "neutral"),
                "consequences": social_result.get("consequences", []),
                "margin": social_result.get("margin", 0),
                "roll": social_result.get("roll"),
                "initial_roll": social_result.get("initial_roll"),
                "difficulty_class": social_result.get("difficulty_class"),
                "adjusted_dc": social_result.get("adjusted_dc"),
                "dc_adjustment": social_result.get("dc_adjustment", 0),
                "old_trust": social_result.get("old_trust"),
                "new_trust": social_result.get("new_trust"),
                "source": social_result.get("source", "social_calc")
            },
            "npc_reaction": {
                "dialogue": dialogue.get("dialogue", "I'll consider that."),
                "body_language": dialogue.get("body_language", "neutral"),
                "mood": social_result.get("emotional_response", "neutral")
            },
            "game_effects": self._determine_game_effects(social_result),
            "metadata": {
                "npc_id": npc_id,
                "interaction_type": social_result.get("interaction_type", ""),
                "timestamp": self._get_current_timestamp()
            }
        }

    def _update_npc_state(self, npc_id: str, interaction_result: Dict):
        """Update NPC state based on interaction outcome"""
        try:
            game_state_path = path_config.game_state_path
            if not game_state_path.exists():
                return

            with open(game_state_path, "r", encoding="utf-8") as f:
                game_state = json.load(f)

            if npc_id in game_state["npcs"]:
                npc_data = game_state["npcs"][npc_id]

                # Update trust
                current_trust = self._coerce_number(self._get_npc_field(npc_data, "trust", 0), 0)
                trust_change = interaction_result["social_result"]["trust_change"]
                self._set_npc_field(npc_data, "trust", round(current_trust + trust_change, 2))

                # Update relationship if changed
                if interaction_result["social_result"]["relationship_change"]:
                    self._set_npc_field(npc_data, "relationship", interaction_result["social_result"]["new_relationship"])

                # Update mood based on emotional response
                self._set_npc_field(npc_data, "mood", interaction_result["npc_reaction"]["mood"])

                # Add to interaction history
                interaction_history = self._get_npc_field(npc_data, "interaction_history", [])
                if not isinstance(interaction_history, list):
                    interaction_history = []

                interaction_history.append({
                    "timestamp": interaction_result["metadata"]["timestamp"],
                    "type": interaction_result["metadata"]["interaction_type"],
                    "player_action": interaction_result["metadata"].get("player_action", ""),
                    "old_trust": current_trust,
                    "new_trust": self._get_npc_field(npc_data, "trust", 0),
                    "old_relationship": interaction_result["social_result"].get("old_relationship", ""),
                    "new_relationship": self._get_npc_field(npc_data, "relationship", interaction_result["social_result"].get("new_relationship", "neutral")),
                    "mood": interaction_result["social_result"]["emotional_response"]
                })
                self._set_npc_field(npc_data, "interaction_history", interaction_history)

                # Save updated game state
                with open(game_state_path, "w", encoding="utf-8") as f:
                    json.dump(game_state, f, indent=4)

                # Update cache
                self.npc_data_cache[npc_id] = npc_data

        except Exception as e:
            logger.error(f"Failed to update NPC state for {npc_id}: {str(e)}")

    def _coerce_number(self, value: Any, default: float = 0) -> float:
        """Convert loosely stored numeric fields without breaking sparse NPC records."""
        try:
            if isinstance(value, str):
                value = value.strip()
                if not value:
                    return default
            return float(value)
        except (TypeError, ValueError):
            return default

    def _get_recent_interactions(self, npc_data: Dict, limit: int = 3) -> List[Dict]:
        """Get recent interaction history"""
        history = npc_data.get("interaction_history", [])
        return history[-limit:] if history else []

    def _load_game_state(self) -> Dict:
        """Load current game state"""
        try:
            if path_config.game_state_path.exists():
                with open(path_config.game_state_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            return {"player": {}, "npcs": {}, "quests": {}, "world": {}}
        except Exception as e:
            logger.error(f"Failed to load game state: {str(e)}")
            return {"player": {}, "npcs": {}, "quests": {}, "world": {}}

    def _get_racial_bias(self, npc_race: str) -> int:
        """Get racial bias modifier"""
        try:
            player_race = self._load_game_state().get("player", {}).get("identity", {}).get("race", "human")
            bias_data = self._load_racial_bias_data()
            return bias_data.get(npc_race.lower(), {}).get(player_race.lower(), -20)
        except Exception:
            return -20

    def _load_racial_bias_data(self) -> Dict:
        """Load racial bias data from CSV"""
        try:
            bias_path = path_config.racial_bias_path
            bias_data = {}

            with open(bias_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                if len(lines) > 1:  # Has header + data
                    races = lines[0].strip().split(",")[1:]  # Skip player_race column
                    for line in lines[1:]:
                        parts = line.strip().split(",")
                        if len(parts) > 1:
                            actor_race = parts[0]
                            bias_data[actor_race.lower()] = {}
                            for i, race in enumerate(races):
                                try:
                                    bias_data[actor_race.lower()][race.lower()] = int(parts[i+1])
                                except ValueError:
                                    bias_data[actor_race.lower()][race.lower()] = -20
            return bias_data
        except Exception as e:
            logger.warning(f"Failed to load racial bias data: {str(e)}")
            return {
                "human": {"human": 0, "elf": -5, "dwarf": 5, "beastfolk": -10, "demon": -30},
                "elf": {"human": -5, "elf": 0, "dwarf": -15, "beastfolk": 0, "demon": -20},
                "dwarf": {"human": 5, "elf": -15, "dwarf": 0, "beastfolk": -25, "demon": -35},
                "beastfolk": {"human": -15, "elf": 0, "dwarf": -25, "beastfolk": 10, "demon": -30},
                "demon": {"human": -25, "elf": -20, "dwarf": -35, "beastfolk": -35, "demon": 10}
            }

    def _calculate_situational_mods(self, npc_data: Dict) -> int:
        """Calculate situational modifiers"""
        try:
            game_state = self._load_game_state()
            player_rep = game_state.get("player", {}).get("identity", {}).get("reputation", 0)

            # Reputation modifier
            rep_mod = min(10, max(-10, player_rep // 2))

            # Location modifier
            location = game_state.get("world", {}).get("location", {}).get("settlement", "town")
            location_mod = {"camp": -5, "town": 0, "city": 5, "capital": 10}.get(location.lower(), 0)

            # Quest-related modifier
            quest_mod = 0
            active_quests = game_state.get("quests", {})
            for quest in active_quests.values():
                if quest.get("giver") == npc_data.get("npc_id") and quest.get("status") == "active":
                    quest_mod += 5  # NPC more favorable if they gave you a quest

            return rep_mod + location_mod + quest_mod
        except Exception:
            return 0

    def _determine_game_effects(self, social_result: Dict) -> Dict[str, Any]:
        """Determine mechanical game effects from social outcome"""
        effects = {
            "reputation_change": 0,
            "cooperation_modifier": 0,
            "quest_progress": None
        }

        if social_result.get("success", False):
            effects["reputation_change"] = min(2, max(0, social_result["trust_change"] // 2))
            effects["cooperation_modifier"] = min(15, max(0, social_result["trust_change"] * 5))

            # Check for quest-related consequences
            if "quest_acceptance" in social_result.get("consequences", []):
                effects["quest_progress"] = "new_quest_available"
        else:
            trust_change = social_result["trust_change"]
            if trust_change < -2:
                effects["reputation_change"] = max(-2, trust_change // 3)
                effects["cooperation_modifier"] = max(-10, trust_change * 3)

                if trust_change < -5:
                    effects["quest_progress"] = "quest_failed"

        return effects

    def _get_current_location(self) -> str:
        """Get current location description"""
        try:
            game_state = self._load_game_state()
            location = game_state.get("world", {}).get("location", {})
            settlement = location.get("settlement", "unknown settlement")
            region = location.get("region", "unknown region")
            return f"{settlement}, {region}"
        except Exception:
            return "a nondescript location"

    def _get_current_time(self) -> str:
        """Get current time description"""
        try:
            game_state = self._load_game_state()
            time_data = game_state.get("world", {}).get("time", {})
            hour = time_data.get("hour", 12)

            if 5 <= hour < 12:
                return "morning"
            elif 12 <= hour < 17:
                return "afternoon"
            elif 17 <= hour < 21:
                return "evening"
            else:
                return "night"
        except Exception:
            return "some time of day"

    def _get_current_timestamp(self) -> str:
        """Get formatted timestamp"""
        from datetime import datetime
        return datetime.now().isoformat()

    def _generate_error_response(self, error_message: str) -> Dict[str, Any]:
        """Generate error response"""
        return {
            "narrative": f"Error: {error_message}",
            "social_result": {
                "success": False,
                "trust_change": 0,
                "relationship_change": False,
                "new_relationship": "neutral",
                "emotional_response": "error",
                "consequences": ["interaction_failed"]
            },
            "npc_reaction": {
                "dialogue": "An error occurred.",
                "body_language": "confused",
                "mood": "neutral"
            },
            "game_effects": {},
            "metadata": {
                "error": error_message
            }
        }
