# game_engine_complete.py
import sys
import json
import copy
import os
import re
import logging
from typing import Dict, Any, Literal, List, Optional, Tuple
from datetime import datetime
from pathlib import Path
try:
    import requests
except ImportError:
    requests = None
import threading
import time
import signal
from path_config import path_config
from game_config import game_config
# Import all your tools
from combat_tools import CombatTools
from combat_manager import CombatManager
from map_tools import get_current_map, execute_map_command
from inventory_tools import add_item_to_inventory
from social_calc import resolve_social_interaction
from crafting import craft_item, study_spell, create_spell, add_found_or_purchased_item
from helper_functions import calculate_scaled_hp_mp_max, roll_generic_check
from quest_tools import add_quest_to_journal, update_quest_progress, complete_quest, get_active_quests
from npc_manager import get_npc, update_npc, get_npcs_by_location
try:
    from web_interface import WebInterface
except ImportError:
    WebInterface = None
from character_creation import CharacterCreator
from api_integration import APIManager
from enhanced_social_calc import EnhancedSocialCalculator
from ai_opening_scene import (
    get_opening_campaign_summary,
    get_opening_scene_facts,
    get_opening_scene_source,
    get_opening_scene_status,
    get_opening_scene_text,
    get_opening_scene_title,
    get_opening_world_state,
)
# Configuration
GAME_STATE_PATH = path_config.game_state_path
STORY_BIBLE_PATH = path_config.story_bible_path
CHARACTER_TEMPLATES_PATH = path_config.references_dir / "character_templates.json"
API_ENDPOINT = "https://api.mistral.ai/v1/chat/completions"  # Mistral 3 Large endpoint
logger = logging.getLogger("GameEngine")
# Conversation management settings
MAX_CONVERSATION_HISTORY = game_config.int("conversation.max_history", 4, min_value=1)
SUMMARY_UPDATE_INTERVAL = game_config.int("conversation.summary_update_interval", 3, min_value=1)
SUMMARY_FILE_NAME = "dm_summary.md"
STORY_FILE_NAME = "story_transcript.md"
DM_PROMPT_DEBUG_FILE_NAME = "last_dm_prompt_debug.md"
DM_PROMPT_DEBUG_JSON_FILE_NAME = "last_dm_prompt_debug.json"
DM_RESPONSE_DEBUG_JSON_FILE_NAME = "last_api_response_dm_narration.json"
NPC_GENDER_MODIFIERS = {
    "male": {"Str": 2, "Vit": 1, "Will": -1},
    "female": {"Str": -1, "Ins": 1, "Will": 1},
}
NPC_FACT_MAX_COUNT = game_config.int("npc_memory.max_fact_count", 8, min_value=1)
NPC_FACT_MAX_CHARS = game_config.int("npc_memory.max_fact_chars", 180, min_value=40)
PROMPT_COMPACT_TEXT_CHARS = game_config.int("prompt_context.compact_text_chars", 1200, min_value=80)
PROMPT_COMPACT_LIST_ITEMS = game_config.int("prompt_context.compact_list_items", 8, min_value=1)
PROMPT_COMPACT_LIST_CHARS = game_config.int("prompt_context.compact_list_chars", 220, min_value=40)
PROMPT_RECENT_EXCHANGE_LIMIT = game_config.int("prompt_context.recent_exchange_limit", 4, min_value=1)
PROMPT_RECENT_PLAYER_CHARS = game_config.int("prompt_context.recent_player_chars", 420, min_value=40)
PROMPT_RECENT_DM_CHARS = game_config.int("prompt_context.recent_dm_chars", 700, min_value=80)
PROMPT_OPENING_SCENE_CHARS = game_config.int("prompt_context.opening_scene_chars", 1800, min_value=120)
PROMPT_STORY_BIBLE_CHARS = game_config.int("prompt_context.story_bible_excerpt_chars", 900, min_value=120)
PROMPT_RUNTIME_STORY_BIBLE_CHARS = game_config.int("prompt_context.runtime_story_bible_excerpt_chars", 700, min_value=120)
PROMPT_SCENE_CONTEXT_CHARS = game_config.int("prompt_context.scene_context_chars", 900, min_value=120)
PROMPT_SCENE_BRIEF_CHARS = game_config.int("prompt_context.scene_brief_chars", 700, min_value=120)
PROMPT_BRIEF_TOKEN_BUDGET = game_config.int("prompt_context.brief_token_budget", 900, min_value=120)
PROMPT_DM_RECENT_EXCHANGE_LIMIT = game_config.int("prompt_context.dm_recent_exchange_limit", 2, min_value=1)
PROMPT_DM_RECENT_PLAYER_CHARS = game_config.int("prompt_context.dm_recent_player_chars", 220, min_value=40)
PROMPT_DM_RECENT_DM_CHARS = game_config.int("prompt_context.dm_recent_dm_chars", 320, min_value=80)
PROMPT_DM_SUMMARY_CHARS = game_config.int("prompt_context.dm_summary_chars", 600, min_value=80)
MODEL_DM_TEMPERATURE = game_config.float("model_calls.dm_temperature", 0.75, min_value=0.0, max_value=2.0)
MODEL_DM_MAX_TOKENS = game_config.int("model_calls.dm_max_tokens", 1200, min_value=1)
MODEL_TURN_CONTEXT_TEMPERATURE = game_config.float("model_calls.turn_context_temperature", 0.1, min_value=0.0, max_value=2.0)
MODEL_TURN_CONTEXT_MAX_TOKENS = game_config.int("model_calls.turn_context_max_tokens", 700, min_value=1)
MODEL_DC_EVALUATION_TEMPERATURE = game_config.float("model_calls.dc_evaluation_temperature", 0.1, min_value=0.0, max_value=2.0)
MODEL_DC_EVALUATION_MAX_TOKENS = game_config.int("model_calls.dc_evaluation_max_tokens", 800, min_value=1)
MODEL_SOCIAL_DETECTION_TEMPERATURE = game_config.float("model_calls.social_detection_temperature", 0.1, min_value=0.0, max_value=2.0)
MODEL_SKILL_DETECTION_TEMPERATURE = game_config.float("model_calls.skill_detection_temperature", 0.1, min_value=0.0, max_value=2.0)
MODEL_NARRATIVE_BRIEF_TEMPERATURE = game_config.float("model_calls.narrative_brief_temperature", 0.15, min_value=0.0, max_value=2.0)
MODEL_NARRATIVE_BRIEF_MAX_TOKENS = game_config.int("model_calls.narrative_brief_max_tokens", 500, min_value=1)
MODEL_NPC_REVIEW_TEMPERATURE = game_config.float("model_calls.npc_review_temperature", 0.45, min_value=0.0, max_value=2.0)
MODEL_NPC_REVIEW_MAX_TOKENS = game_config.int("model_calls.npc_review_max_tokens", 900, min_value=1)
MODEL_TURN_SUMMARY_TEMPERATURE = game_config.float("model_calls.turn_summary_temperature", 0.2, min_value=0.0, max_value=2.0)
MODEL_TURN_SUMMARY_MAX_TOKENS = game_config.int("model_calls.turn_summary_max_tokens", 250, min_value=1)
DM_NARRATIVE_MIN_PARAGRAPHS = game_config.int("dm_narration.min_paragraphs", 2, min_value=1)
DM_NARRATIVE_MAX_PARAGRAPHS = game_config.int("dm_narration.max_paragraphs", 3, min_value=DM_NARRATIVE_MIN_PARAGRAPHS)
DM_NARRATIVE_RESPONSE_HOOKS = game_config.int("dm_narration.response_hook_count", 1, min_value=1)
DM_PROSE_HEAT = game_config.int("dm_narration.prose_heat", 1, min_value=0, max_value=5)
API_DM_TIMEOUT_SECONDS = game_config.float("api.dm_timeout_seconds", 40, min_value=1)
WEB_DEFAULT_PORT = game_config.int("web.default_port", 5000, min_value=1, max_value=65535)
WEB_ENGINE_STARTUP_WAIT_SECONDS = game_config.float("web.engine_startup_wait_seconds", 3, min_value=0.0)
KNOWLEDGE_PRIORITY_RULES = [
    "Story Bible is canonical truth.",
    "Saved game_state facts are secondary and must not override the Story Bible.",
    "Recent summary, transcript, generated briefs, and model inference are continuity aids only after the first two.",
    "When sources conflict, follow the highest-priority source and avoid inventing a reconciliation.",
]
NPC_FACT_REPLACE_CATEGORIES = {
    "status",
    "location",
    "injuries",
    "treatment",
    "restraints",
    "mark",
    "behavior",
    "relationship",
    "identity",
}
class ConversationManager:
    """Manages conversation history and summary for efficient API calls."""
    
    def __init__(self, load_transcript: bool = True):
        self.history = []  # List of (player_input, dm_response) tuples
        self.summary = "Game has just begun."
        self.interactions_since_summary = 0
        self.story_bible = self._load_story_bible()
        self.summary_file_path = path_config.logs_dir / SUMMARY_FILE_NAME
        self.story_file_path = path_config.logs_dir / STORY_FILE_NAME
        if load_transcript:
            self.rehydrate_from_story_transcript()
        loaded_summary = self._load_summary_file()
        if loaded_summary:
            self.summary = loaded_summary
    
    def _load_story_bible(self) -> str:
        """Load the story bible for context."""
        try:
            with open(STORY_BIBLE_PATH, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return "Story bible not found."
    def _load_summary_file(self) -> str:
        """Load the persistent one-line turn summary file."""
        try:
            if self.summary_file_path.exists():
                return self.summary_file_path.read_text(encoding="utf-8").strip()
        except Exception as e:
            logger.error(f"Failed to load summary file: {e}")
        return ""
    def _parse_story_transcript(self, transcript_text: str) -> List[Tuple[str, str]]:
        """Extract player/DM pairs from the markdown story transcript."""
        exchanges = []
        turn_pattern = re.compile(r"^##[ \t]+Turn[^\n]*\n(?P<body>.*?)(?=^##[ \t]+|\Z)", re.MULTILINE | re.DOTALL)
        for match in turn_pattern.finditer(transcript_text or ""):
            section = None
            player_lines = []
            dm_lines = []
            for line in match.group("body").splitlines():
                label = line.strip()
                if label == "Player:":
                    section = "player"
                    continue
                if label == "DM:":
                    section = "dm"
                    continue
                if label == "Command:":
                    break
                if section == "player":
                    player_lines.append(line)
                elif section == "dm":
                    dm_lines.append(line)
            player_input = "\n".join(player_lines).strip()
            dm_response = "\n".join(dm_lines).strip()
            if player_input and dm_response:
                exchanges.append((player_input, dm_response))
        return exchanges[-MAX_CONVERSATION_HISTORY:]
    def _load_story_transcript_history(self) -> List[Tuple[str, str]]:
        """Load recent player/DM exchanges from the persistent transcript."""
        try:
            if self.story_file_path.exists():
                transcript_text = self.story_file_path.read_text(encoding="utf-8")
                return self._parse_story_transcript(transcript_text)
        except Exception as e:
            logger.error(f"Failed to load story transcript history: {e}")
        return []
    def rehydrate_from_story_transcript(self) -> int:
        """Replace in-memory history with recent exchanges from the transcript."""
        self.history = self._load_story_transcript_history()
        self.interactions_since_summary = 0
        return len(self.history)
    def get_summary_file_text(self) -> str:
        """Return the latest summary-file text for model context."""
        return self._load_summary_file() or self.summary
    def append_summary_line(self, summary: str):
        """Append one concise turn summary to the persistent summary file."""
        clean_summary = " ".join(str(summary or "").split()).strip()
        if not clean_summary:
            clean_summary = "Turn completed with no notable state change."
        if len(clean_summary) > 220:
            clean_summary = clean_summary[:217].rstrip() + "..."
        try:
            path_config.logs_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().isoformat(timespec="seconds")
            with open(self.summary_file_path, "a", encoding="utf-8") as f:
                f.write(f"- {timestamp}: {clean_summary}\n")
            self.summary = self._load_summary_file() or clean_summary
        except Exception as e:
            logger.error(f"Failed to append summary line: {e}")
    def append_story_exchange(self, player_input: str, dm_response: str, command: Optional[Dict[str, Any]] = None):
        """Append the full player/DM exchange to the persistent story transcript."""
        try:
            path_config.logs_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().isoformat(timespec="seconds")
            with open(self.story_file_path, "a", encoding="utf-8") as f:
                f.write(f"\n## Turn {timestamp}\n\n")
                f.write(f"Player:\n{player_input.strip()}\n\n")
                f.write(f"DM:\n{dm_response.strip()}\n")
                if command is not None:
                    f.write("\nCommand:\n")
                    f.write("```json\n")
                    f.write(json.dumps(command, indent=2))
                    f.write("\n```\n")
        except Exception as e:
            logger.error(f"Failed to append story exchange: {e}")
    def seed_opening_scene(self, title: str, scene_text: str,
                           scene_facts: Optional[List[str]] = None,
                           source: str = ""):
        """Initialize the story transcript with the opening scene."""
        try:
            path_config.logs_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().isoformat(timespec="seconds")
            clean_title = str(title or "Opening Scene").strip()
            clean_scene = str(scene_text or "").strip()
            with open(self.story_file_path, "w", encoding="utf-8") as f:
                f.write("# Story Transcript\n\n")
                f.write(f"## Opening Scene: {clean_title} ({timestamp})\n\n")
                if source:
                    f.write(f"Source: {source}\n\n")
                f.write(f"DM:\n{clean_scene}\n")
                if scene_facts:
                    f.write("\nScene Facts:\n")
                    f.write("```json\n")
                    f.write(json.dumps(scene_facts, indent=2, ensure_ascii=False))
                    f.write("\n```\n")
            if clean_scene:
                self.add_interaction(f"[Opening Scene: {clean_title}]", clean_scene)
        except Exception as e:
            logger.error(f"Failed to seed opening scene transcript: {e}")
    def get_recent_exchanges(self, limit: int = MAX_CONVERSATION_HISTORY) -> List[Dict[str, str]]:
        """Return recent player/DM exchanges as structured data."""
        return [
            {"player": player_input, "dm": dm_response}
            for player_input, dm_response in self.history[-limit:]
        ]
    def get_last_exchange(self) -> Dict[str, str]:
        """Return the most recent player/DM exchange from restored history."""
        if not self.history:
            return {"player": "", "dm": ""}
        player_input, dm_response = self.history[-1]
        return {"player": player_input, "dm": dm_response}
    
    def _calculate_social_difficulty(self, player_input: str, target_npc: str) -> int:
        """Determine appropriate difficulty class for interaction"""
        base_difficulty = 50  # Neutral
        # Adjust based on interaction type
        interaction_adjustments = {
            "appeal": 0,
            "demand": 15,
            "gift": -10,
            "threat": 20,
            "flattery": -5
        }
        # Detect interaction type from player input if not specified
        interaction_type = "appeal"  # default
        for word in ["demand", "order", "command"]:
            if word in player_input.lower():
                interaction_type = "demand"
                break
        for word in ["gift", "give", "offer"]:
            if word in player_input.lower():
                interaction_type = "gift"
                break
        difficulty = base_difficulty + interaction_adjustments.get(interaction_type, 0)
        # Adjust based on NPC relationship
        npc_data = self.social_calculator._load_npc_data(target_npc)
        if npc_data:
            relationship = npc_data.get("relationship", "neutral")
            relationship_mods = {
                "mortal enemy": 25,
                "enemy": 15,
                "adversary": 10,
                "rival": 5,
                "neutral": 0,
                "acquaintance": -5,
                "friend": -10,
                "close friend": -15,
                "lover": -20,
                "soulmate": -25
            }
            difficulty += relationship_mods.get(relationship, 0)
        return max(10, min(90, difficulty))  # Clamp to reasonable range
    def _log_social_interaction(self, npc_id: str, player_action: str, result: Dict):
        """Log social interaction to game history"""
        try:
            log_entry = {
                "timestamp": result["metadata"]["timestamp"],
                "player_action": player_action,
                "target_npc": npc_id,
                "interaction_type": result["metadata"]["interaction_type"],
                "success": result["social_result"]["success"],
                "trust_change": result["social_result"]["trust_change"],
                "old_relationship": result["social_result"].get("old_relationship", ""),
                "new_relationship": result["social_result"]["new_relationship"],
                "consequences": result["social_result"]["consequences"],
                "narrative_summary": result["narrative"][:100] + "..."  # Truncated
            }
            # Add to conversation history
            self.conversation_manager.add_interaction(player_action, result["narrative"])
            # Save to social interaction log
            log_path = path_config.logs_dir / "social_interactions.json"
            logs = []
            if log_path.exists():
                with open(log_path, "r", encoding="utf-8") as f:
                    logs = json.load(f)
            logs.append(log_entry)
            # Keep only last 100 entries
            if len(logs) > 100:
                logs = logs[-100:]
            with open(log_path, "w", encoding="utf-8") as f:
                json.dump(logs, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to log social interaction: {str(e)}")
        
    def add_interaction(self, player_input: str, dm_response: str):
        """Add a new interaction to the conversation history."""
        self.history.append((player_input, dm_response))
        self.interactions_since_summary += 1
        
        # Keep only the most recent interactions
        if len(self.history) > MAX_CONVERSATION_HISTORY:
            self.history = self.history[-MAX_CONVERSATION_HISTORY:]
        
        # Persistent one-line summaries are appended after each completed turn.
    
    def _update_summary(self):
        """Update the conversation summary based on recent interactions."""
        if not self.history:
            return
        
        # Simple summary generation
        recent_events = []
        for player_input, dm_response in self.history[-SUMMARY_UPDATE_INTERVAL:]:
            recent_events.append(f"Player: {player_input[:50]}... DM: {dm_response[:50]}...")
        
        self.summary = f"Recent events: {', '.join(recent_events)}"
    
    def get_conversation_context(self) -> str:
        """Get the formatted conversation context for the API."""
        context = f"""STORY BIBLE:
{self.story_bible}
SUMMARY FILE:
{self.get_summary_file_text()}
RECENT INTERACTIONS:
"""
        
        for i, (player_input, dm_response) in enumerate(self.history[-MAX_CONVERSATION_HISTORY:], 1):
            context += f"\nInteraction {i}:\nPlayer: {player_input}\nDM: {dm_response}\n"
        
        return context
class GameEngine:
    def __init__(self, start_web: bool = True, open_browser: bool = True,
                 host: str = "127.0.0.1", port: int = WEB_DEFAULT_PORT):
        print("🎮 Initializing Game Engine...")
        
        # Initialize all systems
        self.combat = CombatTools()
        self.combat_manager = CombatManager(self)
        self.conversation_manager = ConversationManager()
        self.character_creator = CharacterCreator()
        # Initialize API manager and enhanced social calculator
        self.api_manager = APIManager()
        self.social_calculator = EnhancedSocialCalculator(self.api_manager)
        # Check if game state exists
        self.game_state_exists = os.path.exists(GAME_STATE_PATH)
        
        if self.game_state_exists:
            self._load_game_state()
            print("📁 Loaded existing game state")
        else:
            self.game_state = {"player": {}, "npcs": {}, "quests": {}, "world": {}}
            print("📝 No existing game found - new game will be created")
        
        # Set up signal handler for clean shutdown
        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGINT, self._handle_shutdown)
            signal.signal(signal.SIGTERM, self._handle_shutdown)
        
        # Start web interface
        self.web_interface = None
        self.web_thread = None
        self.host = host
        self.port = port
        if not start_web:
            print("✅ Game engine initialized without web interface")
            return
        if WebInterface is None:
            raise RuntimeError("Flask is not installed. Run pip install -r requirements.txt before launching the web UI.")
        self.web_interface = WebInterface(host=host, port=port, open_browser=open_browser)
        self.web_interface.set_game_engine(self)
        
        print("🌐 Starting web interface...")
        self.web_thread = threading.Thread(target=self._start_web_interface, daemon=True)
        self.web_thread.start()
        
        # Wait for web interface to start
        time.sleep(WEB_ENGINE_STARTUP_WAIT_SECONDS)
        
        print("✅ Game engine fully initialized!")
        print("🌐 Web interface should have opened automatically in your browser")
        print(f"   If not, open: http://{host}:{port}")
        print("\n🎮 Ready to play! Press Ctrl+C to exit cleanly.")
    
    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signals for clean exit."""
        print("\n🛑 Shutting down game engine...")
        
        # Stop web interface properly
        if hasattr(self, 'web_interface'):
            try:
                print("   Stopping web server...")
                self.web_interface.stop_server()
            except Exception as e:
                print(f"   Error stopping web server: {e}")
        
        # Give threads time to clean up
        time.sleep(1.5)
        
        print("✅ Game engine stopped cleanly")
        
        # Force exit to prevent hanging
        os._exit(0)   # This is the key for reliable shutdown on Windows
    def _start_web_interface(self):
        """Start the web interface."""
        self.web_interface.run()
    def _clean_known_facts(self):
        """Prevent known_facts from nesting or exploding."""
        player = self.game_state.get("player")
        if isinstance(player, dict):
            identity = self._npc_identity(player)
            identity.pop("guided_creation", None)
            identity["known_facts"] = self._sanitize_known_facts_value(
                identity.get("known_facts", []),
                allow_character_creation=True,
            )
        npcs = self.game_state.setdefault("npcs", {})
        if isinstance(npcs, dict):
            for npc in (npc for npc in npcs.values() if isinstance(npc, dict)):
                identity = self._npc_identity(npc)
                identity.pop("guided_creation", None)
                identity["known_facts"] = self._sanitize_known_facts_value(identity.get("known_facts", []))
    def _load_game_state(self):
        """Load the game state from file."""
        try:
            with open(GAME_STATE_PATH, "r", encoding="utf-8") as f:
                self.game_state = json.load(f)
            self._clean_known_facts()
            self._normalize_npc_records()
            self._reset_stale_combat_state()
            self._save_game_state()
        except FileNotFoundError:
            print(f"Warning: Game state file not found at {GAME_STATE_PATH}")
            self.game_state = {"player": {}, "npcs": {}, "quests": {}, "world": {}}
        except json.JSONDecodeError as e:
            print(f"Error loading game state: {e}")
            self.game_state = {"player": {}, "npcs": {}, "quests": {}, "world": {}}
    
    def _save_game_state(self):
        """Save the game state to file."""
        try:
            self._clean_known_facts()
            self._normalize_npc_records()
            with open(GAME_STATE_PATH, "w", encoding="utf-8") as f:
                json.dump(self.game_state, f, indent=2)
        except Exception as e:
            print(f"Error saving game state: {e}")
    def _normalize_key_text(self, value: Any) -> str:
        """Normalize NPC identifiers and display names for matching."""
        return re.sub(r"\s+", " ", str(value or "").strip()).lower()
    def _make_npc_id_from_name(self, name: str) -> str:
        """Build a stable canonical NPC id from a learned display name."""
        slug = re.sub(r"[^a-z0-9]+", "_", str(name or "").strip().lower()).strip("_")
        return f"npc_{slug or 'unknown'}"

    def _is_generic_npc_reference(self, value: Any) -> bool:
        """Return true for race/species/role labels that should not be canonical NPC ids."""
        normalized = self._normalize_key_text(value).replace("-", " ").replace("_", " ")
        if normalized.startswith("npc "):
            normalized = normalized[4:]
        generic_tokens = {
            "human", "elf", "dwarf", "beastfolk", "beastkin", "nekko", "nekkko",
            "catfolk", "demon", "woman", "man", "girl", "boy", "person", "npc",
            "unknown", "unnamed", "unknown npc", "unnamed npc", "unknown woman",
            "unknown man", "nekko woman", "nekko man", "beastfolk woman",
            "beastfolk man", "unknown nekko woman", "unnamed nekko woman",
            "unknown beastfolk woman", "unnamed beastfolk woman",
        }
        return normalized in generic_tokens

    def _allocate_placeholder_npc_id(self, reference: Any, updates: Optional[Dict[str, Any]] = None) -> str:
        """Allocate a stable unnamed NPC id for generic references like npc_nekko."""
        inferred = self._infer_race_gender_from_reference(reference, json.dumps(updates or {}, ensure_ascii=False))
        race = inferred.get("race") or "unknown"
        gender = inferred.get("gender")
        role = {"female": "woman", "male": "man"}.get(gender, "npc")
        base = f"unnamed_{race}_{role}"
        base = re.sub(r"[^a-z0-9_]+", "_", base.lower()).strip("_")
        npcs = self.game_state.setdefault("npcs", {})
        if base not in npcs:
            return base
        counter = 2
        while f"{base}_{counter}" in npcs:
            counter += 1
        return f"{base}_{counter}"

    def _ensure_npc_for_interaction(self, reference: Any, player_input: str = "",
                                    updates: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Create a template-shaped live NPC when a player first interacts with an unnamed target."""
        if not reference:
            return None
        resolved = self._resolve_npc_reference(str(reference))
        if resolved:
            return resolved
        learned_name = (updates or {}).get("name")
        if learned_name and self._is_learned_npc_name(learned_name, str(reference)):
            npc_id = self._make_npc_id_from_name(str(learned_name))
        elif self._is_generic_npc_reference(reference):
            npc_id = self._allocate_placeholder_npc_id(reference, updates)
        else:
            npc_id = self._make_npc_id_from_name(str(reference)) if not str(reference).startswith(("npc_", "unnamed_")) else str(reference)

        inferred = self._infer_race_gender_from_reference(reference, learned_name or "", player_input, json.dumps(updates or {}, ensure_ascii=False))
        source = {
            "npc_id": npc_id,
            "aliases": [str(reference)],
        }
        if learned_name:
            source["name"] = learned_name
        if inferred.get("race"):
            source["race"] = inferred["race"]
        if inferred.get("gender"):
            source["gender"] = inferred["gender"]

        npc = self._make_template_npc(npc_id, source)
        if player_input:
            self._append_npc_known_fact(npc, f"First interacted with during player action: {self._compact_text(player_input, 180)}")
        self.game_state.setdefault("npcs", {})[npc_id] = npc
        self.game_state.setdefault("npc_aliases", {})[str(reference)] = npc_id
        self._normalize_npc_records()
        return self._resolve_npc_reference(learned_name or str(reference)) or npc_id
    def _is_learned_npc_name(self, name: Any, current_key: str = "") -> bool:
        """Return true when a placeholder NPC has a real learned name."""
        normalized = self._normalize_key_text(name)
        if not normalized:
            return False
        placeholder_names = {
            "unknown",
            "unnamed",
            "unknown npc",
            "unnamed npc",
            "unknown beastfolk woman",
            "unnamed beastfolk woman",
            "unknown nekko woman",
            "unnamed nekko woman",
        }
        if normalized in placeholder_names or normalized.startswith("unknown "):
            return False
        key_as_name = self._normalize_key_text(str(current_key).replace("_", " "))
        return normalized != key_as_name
    def _load_character_template(self) -> Dict[str, Any]:
        """Load the canonical character/NPC template from references."""
        try:
            template_path = path_config.references_dir / "character_templates.json"
            with open(template_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            return self._blank_character_template(loaded if isinstance(loaded, dict) else {})
        except Exception as e:
            logger.error(f"Failed to load character template: {e}")
            return self._blank_character_template({})

    def _blank_character_template(self, template: Dict[str, Any]) -> Dict[str, Any]:
        """Return a template shape with player-specific saved values cleared."""
        identity_source = template.get("identity") if isinstance(template.get("identity"), dict) else {}
        identity = {
            "name": "",
            "gender": "",
            "race": "",
            "background": "",
            "class_theme": "",
            "reputation": 0,
            "title": "",
            "age": 0,
            "relationships": {},
            "known_facts": [],
        }
        for key, value in identity_source.items():
            if key not in identity and key != "guided_creation":
                identity[key] = [] if isinstance(value, list) else {} if isinstance(value, dict) else ""

        stats_source = template.get("stats") if isinstance(template.get("stats"), dict) else {}
        stats = {stat: 0 for stat in (stats_source.keys() or ["Str", "Agi", "Vit", "Ins", "Will", "Crea"])}
        skills_source = template.get("skills") if isinstance(template.get("skills"), dict) else {}
        skills = {skill: 0.0 for skill in skills_source}
        derived_source = template.get("derived") if isinstance(template.get("derived"), dict) else {}
        derived = {field: 0 for field in (derived_source.keys() or ["HP", "HP_max", "MP", "MP_max", "AC"])}

        return {
            "identity": identity,
            "stats": stats,
            "skills": skills,
            "derived": derived,
            "inventory": {},
            "equipment": {},
            "gold": 0,
        }
    def _template_identity_fields(self) -> set:
        return set((self._load_character_template().get("identity") or {}).keys())
    def _npc_identity(self, npc: Dict[str, Any]) -> Dict[str, Any]:
        """Return the canonical mutable identity object for an NPC record."""
        identity = npc.setdefault("identity", {})
        return identity if isinstance(identity, dict) else {}
    def _get_npc_field(self, npc: Dict[str, Any], field: str, default: Any = None) -> Any:
        """Read NPC data from the template shape with legacy fallback."""
        identity = npc.get("identity") if isinstance(npc.get("identity"), dict) else {}
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
        return npc.get(field, default)

    def _sanitize_known_fact_text(self, fact: Any, allow_character_creation: bool = False) -> str:
        """Return one safe narrative fact, or an empty string if it is technical/nested."""
        if not isinstance(fact, (str, int, float, bool)):
            return ""
        clean = " ".join(str(fact).split()).strip()
        if not clean:
            return ""
        lowered = clean.lower()
        bad_phrases = [
            "known_facts",
            "identity:",
            "stats:",
            "skills:",
            "derived:",
            "inventory:",
            "equipment:",
            "gold:",
            "{",
            "}",
            "[",
            "]",
            "':",
            '":',
            "0.0",
        ]
        if any(phrase in lowered for phrase in bad_phrases):
            return ""
        npc_bad_prefixes = (
            "former occupation:",
            "former hobbies:",
            "emergency response:",
            "wilderness survival:",
            "personal strengths:",
            "personal weaknesses:",
            "personal flaw:",
            "narration from this interaction:",
            "player action during this interaction:",
            "created_at:",
            "updated_at:",
            "deviation_range:",
            "role:",
            "faction:",
        )
        if not allow_character_creation and lowered.startswith(npc_bad_prefixes):
            return ""
        prose_markers = (
            "seems to",
            "as if",
            " like a ",
            " like an ",
            " like the ",
            "hush of",
            "holds its breath",
            "swallows",
            "the silence",
        )
        if not allow_character_creation and any(marker in lowered for marker in prose_markers):
            return ""
        if not allow_character_creation and self._fact_uses_player_subject(lowered):
            return ""
        if not allow_character_creation and not self._looks_like_state_fact(clean):
            return ""
        return clean[:NPC_FACT_MAX_CHARS].rstrip()

    def _fact_uses_player_subject(self, lowered_fact: str) -> bool:
        """Detect player-action narration that should not become NPC memory."""
        padded = f" {lowered_fact} "
        return (
            lowered_fact.startswith(("you ", "your ", "player "))
            or any(token in padded for token in [" you ", " your ", " yourself ", " player "])
        )

    def _looks_like_state_fact(self, fact: str) -> bool:
        """Accept generic NPC state facts; reject unlabeled prose beats."""
        lowered = self._normalize_key_text(fact)
        if not lowered:
            return False
        prefix = lowered.split(":", 1)[0].strip() if ":" in lowered else ""
        if prefix in {
            "name", "identity", "relationship", "trust", "mood", "status", "condition",
            "conditions", "position", "location", "injury", "injuries", "wound", "wounds",
            "bleeding", "fracture", "restraints", "chain", "chains", "mark", "brand",
            "tattoo", "behavior", "goal", "need", "fear", "knowledge", "memory",
        }:
            return True
        if lowered.startswith(("is ", "has ", "was ", "needs ", "wants ", "fears ", "knows ", "believes ")):
            return True
        state_verbs = {
            "is", "are", "was", "were", "has", "have", "had", "remains", "remain",
            "knows", "believes", "wants", "needs", "fears", "trusts", "distrusts",
            "revealed", "implied", "acknowledges", "acknowledged", "accepts", "accepted",
            "refuses", "refused", "recognizes", "recognized", "questions", "challenges",
            "tests", "hides", "hiding",
        }
        words = re.findall(r"[a-zA-Z']+", lowered)
        if not words:
            return False
        if words[0] in {"he", "she", "they", "it"} and len(words) > 1 and words[1] in state_verbs:
            return True
        if len(words) > 1 and words[1] in state_verbs:
            return True
        if len(words) > 2 and words[2] in state_verbs:
            return True
        return False

    def _known_fact_category(self, fact: str) -> str:
        """Classify an NPC fact so stale state can be replaced instead of repeated."""
        lowered = self._normalize_key_text(fact)
        prefix = lowered.split(":", 1)[0].strip() if ":" in lowered else ""
        prefix_categories = {
            "name": "identity",
            "identity": "identity",
            "relationship": "relationship",
            "trust": "relationship",
            "mood": "status",
            "status": "status",
            "condition": "status",
            "conditions": "status",
            "position": "location",
            "location": "location",
            "injury": "injuries",
            "injuries": "injuries",
            "wound": "injuries",
            "wounds": "injuries",
            "bleeding": "injuries",
            "fracture": "injuries",
            "chain": "restraints",
            "chains": "restraints",
            "restraints": "restraints",
            "brand": "mark",
            "tattoo": "mark",
            "mark": "mark",
            "behavior": "behavior",
            "goal": "behavior",
            "need": "behavior",
            "fear": "behavior",
            "knowledge": "note",
            "memory": "note",
        }
        if prefix in prefix_categories:
            return prefix_categories[prefix]
        if any(token in lowered for token in ["bandage", "rebandage", "cleaned", "treated", "stabilized"]):
            return "treatment"
        if any(token in lowered for token in ["chain", "shackle", "bound", "binding", "restraint"]):
            return "restraints"
        if any(token in lowered for token in ["tattoo", "brand", "mark on"]):
            return "mark"
        if any(token in lowered for token in ["wound", "gash", "bruise", "cut", "blood", "bleed", "laceration", "fracture", "injur"]):
            return "injuries"
        if any(token in lowered for token in ["unconscious", "breathing", "stable", "stir", "weak", "pained"]):
            return "status"
        if any(token in lowered for token in ["react", "flinch", "defensive", "claw", "tail", "ears", "twitch"]):
            return "behavior"
        if any(token in lowered for token in ["hidden", "concealed", "forest", "undergrowth", "hollow", "oak", "brush"]):
            return "location"
        if any(token in lowered for token in ["trust", "relationship", "friend", "hostile", "afraid", "hopeful"]):
            return "relationship"
        return "note"

    def _merge_known_fact(self, facts: List[str], fact: str, seen_notes: Optional[set] = None) -> List[str]:
        """Merge one clean fact, replacing stale state facts in the same category."""
        category = self._known_fact_category(fact)
        if category in NPC_FACT_REPLACE_CATEGORIES:
            facts = [
                existing
                for existing in facts
                if self._known_fact_category(existing) != category
            ]
            facts.append(fact)
            return facts[-NPC_FACT_MAX_COUNT:]
        if seen_notes is not None:
            note_key = self._normalize_key_text(fact)
            if note_key in seen_notes:
                return facts
            seen_notes.add(note_key)
        elif fact in facts:
            return facts
        facts.append(fact)
        return facts[-NPC_FACT_MAX_COUNT:]

    def _sanitize_known_facts_value(self, facts: Any, allow_character_creation: bool = False) -> List[str]:
        """Normalize known_facts to a small flat list of strings only."""
        if isinstance(facts, list):
            raw_facts = facts
        elif isinstance(facts, (str, int, float, bool)):
            raw_facts = [facts]
        elif isinstance(facts, dict):
            # Do not walk nested known_facts structures; rescue only direct simple fact text.
            raw_facts = [
                facts.get(key)
                for key in ("fact", "note", "description", "summary")
                if isinstance(facts.get(key), (str, int, float, bool))
            ]
        else:
            raw_facts = []

        cleaned: List[str] = []
        seen_notes = set()
        for fact in raw_facts:
            clean = self._sanitize_known_fact_text(fact, allow_character_creation=allow_character_creation)
            if not clean:
                continue
            cleaned = self._merge_known_fact(cleaned, clean, seen_notes)
        return cleaned[-NPC_FACT_MAX_COUNT:]

    def _append_npc_known_fact(self, npc: Dict[str, Any], fact: Any):
        """Only add clean, readable narrative facts."""
        identity = self._npc_identity(npc)
        known_facts = self._sanitize_known_facts_value(identity.get("known_facts", []))
        clean = self._sanitize_known_fact_text(fact)
        if clean and len(clean) > 12:
            known_facts = self._merge_known_fact(known_facts, clean)
        identity["known_facts"] = known_facts[-NPC_FACT_MAX_COUNT:]

    def _normalize_npc_gender(self, gender: Any) -> str:
        normalized = self._normalize_key_text(gender)
        if normalized in {"female", "woman", "girl", "lady", "she", "her"}:
            return "female"
        if normalized in {"male", "man", "boy", "gentleman", "he", "him"}:
            return "male"
        return normalized if normalized in NPC_GENDER_MODIFIERS else ""

    def _infer_race_gender_from_reference(self, *values: Any) -> Dict[str, str]:
        text = self._normalize_key_text(" ".join(str(value or "") for value in values))
        race = ""
        race_aliases = {
            "nekko": "nekko",
            "nekkko": "nekko",
            "catfolk": "nekko",
            "feline beastfolk": "nekko",
            "beastfolk": "beastfolk",
            "beastkin": "beastfolk",
            "demon": "demon",
            "elf": "elf",
            "dwarf": "dwarf",
            "human": "human",
        }
        for candidate, race_key in race_aliases.items():
            if candidate in text:
                race = race_key
                break
        gender = ""
        if any(word in text for word in ("woman", "female", "girl", "lady", "she", "her")):
            gender = "female"
        elif any(word in text for word in ("man", "male", "boy", "gentleman", " he ", " him ")):
            gender = "male"
        return {"race": race, "gender": gender}

    def _load_base_stat_table(self) -> Dict[str, Any]:
        try:
            with open(path_config.base_stats_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            return loaded if isinstance(loaded, dict) else {}
        except Exception as e:
            logger.error(f"Failed to load base stats for NPC creation: {e}")
            return {}

    def _base_stats_race_key(self, race: Any) -> str:
        normalized = self._normalize_key_text(race).replace(" ", "_").replace("-", "_")
        aliases = {
            "beastkin": "beastfolk",
            "beast_kin": "beastfolk",
            "true_beastkin": "beastfolk",
            "catfolk": "nekko",
            "nekkko": "nekko",
        }
        return aliases.get(normalized, normalized or "human")

    def _npc_baseline_stats(self, race: Any, gender: Any = "") -> Dict[str, int]:
        """Build NPC stats from base_stats.json averages plus character-creation gender mods."""
        base_table = self._load_base_stat_table()
        race_key = self._base_stats_race_key(race or "human")
        race_stats = base_table.get(race_key) or base_table.get("human") or {}
        stats: Dict[str, int] = {}
        max_stats: Dict[str, int] = {}
        for stat in ("Str", "Agi", "Vit", "Ins", "Will", "Crea"):
            values = race_stats.get(stat, [8, 10, 12])
            if isinstance(values, list) and len(values) >= 3:
                stats[stat] = int(values[1])
                max_stats[stat] = int(values[2])
            else:
                stats[stat] = int(values if isinstance(values, (int, float)) else 10)
                max_stats[stat] = max(20, stats[stat])
        for stat, modifier in NPC_GENDER_MODIFIERS.get(self._normalize_npc_gender(gender), {}).items():
            stats[stat] = max(1, min(max_stats.get(stat, 99), stats.get(stat, 10) + modifier))
        return stats

    def _npc_derived_from_stats(self, stats: Dict[str, int]) -> Dict[str, int]:
        maxima = calculate_scaled_hp_mp_max(stats)
        return {
            "HP": maxima["HP_max"],
            "HP_max": maxima["HP_max"],
            "MP": maxima["MP_max"],
            "MP_max": maxima["MP_max"],
            "AC": 10 + stats.get("Agi", 10) // 2,
            "Initiative": stats.get("Agi", 10) + stats.get("Ins", 10) // 2,
            "Carry_Capacity": stats.get("Str", 10) * 10,
        }

    def _initialize_npc_baseline_stats(self, npc: Dict[str, Any], force: bool = False):
        identity = self._npc_identity(npc)
        race = self._racial_profile_key(identity.get("race") or npc.get("race") or "human")
        gender = self._normalize_npc_gender(identity.get("gender") or npc.get("gender") or "")
        existing_stats = npc.get("stats") if isinstance(npc.get("stats"), dict) else {}
        has_stats = any(float(value or 0) > 0 for value in existing_stats.values())
        if force or not has_stats:
            npc["stats"] = self._npc_baseline_stats(race, gender)
        npc["derived"] = self._npc_derived_from_stats(npc.get("stats", {}))

    def _looks_like_player_creation_artifact(self, source: Dict[str, Any]) -> bool:
        """Detect NPC records polluted by player character creation output."""
        if not isinstance(source, dict):
            return False
        identity = source.get("identity") if isinstance(source.get("identity"), dict) else source
        facts = identity.get("known_facts", []) if isinstance(identity, dict) else []
        fact_text = " ".join(str(fact) for fact in facts if isinstance(fact, (str, int, float, bool))).lower()
        background = self._normalize_key_text(identity.get("background", "") if isinstance(identity, dict) else "")
        class_theme = self._normalize_key_text(identity.get("class_theme", "") if isinstance(identity, dict) else "")
        return (
            isinstance(identity, dict)
            and (
                "guided_creation" in identity
                or fact_text.startswith("former occupation:")
                or "former occupation:" in fact_text
                or "before elyndor" in background
                or class_theme == "isekai adventurer"
            )
        )
            
    def _normalize_relationships_value(self, relationships: Any) -> Dict[str, Any]:
        """Normalize relationship data so history uses template vocabulary."""
        if not isinstance(relationships, dict):
            return {}
        normalized = copy.deepcopy(relationships)
        for relationship in normalized.values():
            if not isinstance(relationship, dict):
                continue
            history = relationship.get("interaction_history", [])
            if not isinstance(history, list):
                relationship["interaction_history"] = []
                continue
            for event in history:
                if isinstance(event, dict) and "emotional_response" in event:
                    event.setdefault("mood", event.pop("emotional_response"))
        return normalized

    def _set_npc_field(self, npc: Dict[str, Any], field: str, value: Any):
        """Safely write NPC data - protect known_facts from technical garbage."""
        identity = self._npc_identity(npc)
        template_fields = self._template_identity_fields()

        if field in {"npc_id", "aliases", "updated_at", "experience"}:
            return

        if field in {"background", "class_theme", "guided_creation"}:
            return

        if field == "trust_level":
            field = "trust"
        if field == "emotional_response":
            field = "mood"
        if field == "trust":
            try:
                identity["trust"] = round(float(value), 2)
            except (TypeError, ValueError):
                identity["trust"] = value
            return
        if field == "mood":
            identity["mood"] = str(value)
            return

        if field in {"facts", "known_fact"}:
            field = "known_facts"

        if field == "known_facts":
            for fact in self._sanitize_known_facts_value(value):
                self._append_npc_known_fact(npc, fact)
            return

        # === RELATIONSHIPS ===
        if field == "relationship":
            relationships = identity.setdefault("relationships", {})
            player_rel = relationships.setdefault("player", {})
            if isinstance(player_rel, dict):
                player_rel["relationship"] = str(value)
            return

        if field == "interaction_history":
            relationships = identity.setdefault("relationships", {})
            player_rel = relationships.setdefault("player", {})
            if isinstance(player_rel, dict):
                player_rel["interaction_history"] = value if isinstance(value, list) else []
            return

        # === BIG TECHNICAL OBJECTS - DO NOT DUMP INTO known_facts ===
        if field in {"stats", "skills", "derived", "inventory", "equipment", "gold", "personality", "voice_profile"}:
            if isinstance(value, (dict, list)):
                npc[field] = value
            return

        # === CURRENT NPC STATE ===
        if field in {"status", "injuries", "wounds", "conditions", "physical_state",
                     "location", "bleeding", "fracture", "chain", "slave_mark", "tattoo"}:
            fact_text = self._sanitize_known_fact_text(f"{field}: {value}")
            if fact_text:
                identity[field] = fact_text.split(":", 1)[1].strip()
                self._append_npc_known_fact(npc, fact_text)
            return

        if field == "notes":
            clean_value = self._sanitize_known_fact_text(value)
            if clean_value and self._known_fact_category(clean_value) != "note":
                self._append_npc_known_fact(npc, clean_value)
            return

        if field == "gender":
            identity["gender"] = self._normalize_npc_gender(value) or str(value)
            self._initialize_npc_baseline_stats(npc, force=True)
            return

        if field == "race":
            identity["race"] = self._base_stats_race_key(value)
            self._initialize_npc_baseline_stats(npc, force=True)
            return

        # === TEMPLATE IDENTITY FIELDS ===
        if field in template_fields:
            identity[field] = value
            return

        # Unknown scalar fields are ignored. Durable memory should arrive through
        # recognized state fields or explicit known_facts, not template metadata.

    def _make_template_npc(self, npc_id: str, source: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Instantiate a canonical NPC record from references/character_templates.json."""
        template = copy.deepcopy(self._load_character_template())
        if not isinstance(template.get("identity"), dict):
            template["identity"] = {}
        source = source or {}
        source_is_polluted = self._looks_like_player_creation_artifact(source)
        aliases = set(source.get("aliases", [])) if isinstance(source.get("aliases"), list) else set()
        for alias in [npc_id, source.get("npc_id"), source.get("name"), source.get("display_name")]:
            if alias:
                aliases.add(str(alias))
        source_identity = source.get("identity") if isinstance(source.get("identity"), dict) else {}
        for field, value in source_identity.items():
            if source_is_polluted and field in {
                "age", "background", "class_theme", "guided_creation", "known_facts",
                "relationships",
            }:
                continue
            if value not in ("", None, [], {}):
                self._set_npc_field(template, field, value)
        for field, value in source.items():
            if source_is_polluted and field in {
                "stats", "skills", "derived", "gold", "background", "class_theme",
                "guided_creation", "known_facts",
            }:
                continue
            if field != "identity" and value not in ("", None, [], {}):
                self._set_npc_field(template, field, value)
        identity = self._npc_identity(template)
        if not identity.get("name") and not npc_id.startswith(("npc_", "unnamed_")):
            identity["name"] = npc_id
        if not identity.get("name") and npc_id.startswith("unnamed_beastfolk"):
            identity["name"] = "Unknown Beastfolk Woman"
        if not identity.get("name") and npc_id.startswith(("unnamed_nekko", "unnamed_nekkko")):
            identity["name"] = "Unknown Nekko Woman"
        inferred = self._infer_race_gender_from_reference(
            npc_id,
            source.get("npc_id"),
            source.get("name"),
            " ".join(sorted(aliases)),
        )
        if inferred.get("race") and not identity.get("race"):
            identity["race"] = inferred["race"]
        if inferred.get("gender") and not identity.get("gender"):
            identity["gender"] = inferred["gender"]
        if not identity.get("race") and (
            "nekko" in npc_id
            or "nekkko" in npc_id
        ):
            identity["race"] = "nekko"
        if not identity.get("race") and "beastfolk" in npc_id:
            identity["race"] = "beastfolk"
        identity.setdefault("relationships", {})
        identity.setdefault("known_facts", [])
        self._initialize_npc_baseline_stats(template)
        if aliases:
            alias_map = self.game_state.setdefault("npc_aliases", {})
            canonical_key = self._make_npc_id_from_name(identity.get("name", "")) if self._is_learned_npc_name(identity.get("name"), npc_id) else npc_id
            for alias in aliases:
                alias_map[alias] = canonical_key
        return template
    def _merge_npc_records(self, canonical_key: str, canonical: Dict[str, Any],
                           duplicate_key: str, duplicate: Dict[str, Any]) -> Dict[str, Any]:
        """Merge two NPC records into a single canonical template-shaped record."""
        merged = self._make_template_npc(canonical_key, canonical)
        for source in (duplicate,):
            source_identity = source.get("identity") if isinstance(source.get("identity"), dict) else {}
            for field, value in source_identity.items():
                if value not in ("", None, [], {}):
                    self._set_npc_field(merged, field, value)
            for field, value in source.items():
                if field != "identity" and value not in ("", None, [], {}):
                    self._set_npc_field(merged, field, value)
        identity = self._npc_identity(merged)
        inferred = self._infer_race_gender_from_reference(
            canonical_key,
            duplicate_key,
            json.dumps(canonical, ensure_ascii=False),
            json.dumps(duplicate, ensure_ascii=False),
        )
        if inferred.get("race") and not identity.get("race"):
            identity["race"] = inferred["race"]
        if inferred.get("gender") and not identity.get("gender"):
            identity["gender"] = inferred["gender"]
        self._initialize_npc_baseline_stats(merged, force=bool(inferred.get("race") or inferred.get("gender")))
        alias_map = self.game_state.setdefault("npc_aliases", {})
        for alias in [canonical_key, duplicate_key, self._get_npc_field(canonical, "name"), self._get_npc_field(duplicate, "name")]:
            if alias:
                alias_map[str(alias)] = canonical_key
        return merged
    def _normalize_npc_records(self):
        """Keep every live NPC as a stable instance of character_templates.json."""
        npcs = self.game_state.setdefault("npcs", {})
        if not isinstance(npcs, dict):
            self.game_state["npcs"] = {}
            return
        player = self.game_state.get("player", {})
        player_name = ""
        player_key = ""
        if isinstance(player, dict):
            player.pop("level", None)
            player.pop("experience", None)
            player_identity = player.get("identity") if isinstance(player.get("identity"), dict) else {}
            player_name = self._normalize_key_text(player_identity.get("name") or player.get("name"))
            if player_name:
                player_key = self._make_npc_id_from_name(player_name)
        self.game_state.setdefault("npc_aliases", {})
        normalized: Dict[str, Dict[str, Any]] = {}
        for npc_key, npc in list(npcs.items()):
            if not isinstance(npc, dict):
                continue
            name = self._get_npc_field(npc, "name", "")
            if not name and not npc_key.startswith(("npc_", "unnamed_")):
                name = npc_key
            if player_name and (
                self._normalize_key_text(name) == player_name
                or self._normalize_key_text(npc_key) == self._normalize_key_text(player_key)
            ):
                continue
            if name and (self._is_learned_npc_name(name, npc_key) or not npc_key.startswith(("npc_", "unnamed_"))):
                canonical_key = self._make_npc_id_from_name(name)
            else:
                canonical_key = npc_key
            templated = self._make_template_npc(canonical_key, npc)
            identity = self._npc_identity(templated)
            if name:
                identity["name"] = name
            if canonical_key in normalized:
                normalized[canonical_key] = self._merge_npc_records(canonical_key, normalized[canonical_key], npc_key, templated)
            else:
                normalized[canonical_key] = templated
            for alias in [npc_key, self._get_npc_field(npc, "name"), npc.get("npc_id"), npc.get("display_name")]:
                if alias:
                    self.game_state["npc_aliases"][str(alias)] = canonical_key
        self.game_state["npcs"] = normalized
        self.game_state["npc_aliases"] = {
            alias: canonical
            for alias, canonical in self.game_state.get("npc_aliases", {}).items()
            if canonical in normalized
        }
    def _resolve_npc_reference(self, target: str, known_npcs: Optional[List[Dict[str, Any]]] = None) -> Optional[str]:
        """Resolve an NPC id, display name, or alias to the canonical save key."""
        if not target:
            return None
        target_norm = self._normalize_key_text(target)
        npcs = self.game_state.get("npcs", {})
        alias_map = self.game_state.get("npc_aliases", {})
        for alias, canonical in alias_map.items():
            if target_norm == self._normalize_key_text(alias) and canonical in npcs:
                return canonical
        for npc_key, npc in npcs.items():
            if target_norm == self._normalize_key_text(npc_key):
                return npc_key
            if isinstance(npc, dict):
                names = [
                    self._get_npc_field(npc, "name"),
                    self._get_npc_field(npc, "title"),
                    npc_key,
                ]
                if any(target_norm == self._normalize_key_text(name) for name in names):
                    return npc_key
        for npc in known_npcs or []:
            npc_id = npc.get("npc_id", "")
            name = npc.get("name", "")
            if target_norm in {self._normalize_key_text(npc_id), self._normalize_key_text(name)}:
                return npc_id
        return None
    def _reset_stale_combat_state(self):
        """Drop combat state that predates the active save file."""
        try:
            game_start = self.game_state.get("game", {}).get("start_date")
            combat_updated = self.combat.state.get("last_updated")
            if not (self.combat.state.get("active") and game_start and combat_updated):
                return
            if datetime.fromisoformat(combat_updated) < datetime.fromisoformat(game_start):
                self.combat.end_combat()
        except Exception as e:
            logger.error(f"Failed to check stale combat state: {e}")
    def _write_dm_prompt_debug(self, player_input: str, prompt: str,
                               social_check: Optional[Dict[str, Any]] = None,
                               social_result: Optional[Dict[str, Any]] = None,
                               npc_review: Optional[Dict[str, Any]] = None,
                               skill_check: Optional[Dict[str, Any]] = None,
                               skill_result: Optional[Dict[str, Any]] = None,
                               turn_context: Optional[Dict[str, Any]] = None,
                               narrative_brief: Optional[Dict[str, Any]] = None):
        """Overwrite the final DM prompt debug files for the latest turn."""
        try:
            path_config.logs_dir.mkdir(parents=True, exist_ok=True)
            debug_payload = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "source": "game_engine",
                "prompt_type": "dm_narration",
                "player_input": player_input,
                "social_check": social_check or {"needs_social_check": False},
                "social_result": social_result or {},
                "skill_check": skill_check or {"needs_skill_check": False},
                "skill_result": skill_result or {},
                "turn_context": turn_context or {},
                "narrative_brief": narrative_brief or {},
                "npc_review": npc_review or {"npc_actions": []},
                "known_npcs_snapshot": self.game_state.get("npcs", {}),
                "full_prompt": prompt,
            }
            json_debug_path = path_config.logs_dir / DM_PROMPT_DEBUG_JSON_FILE_NAME
            json_debug_path.write_text(
                json.dumps(debug_payload, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            markdown = (
                "# Last DM Prompt Debug\n\n"
                f"- Timestamp: {debug_payload['timestamp']}\n"
                f"- Prompt type: {debug_payload['prompt_type']}\n"
                f"- Player input: {player_input}\n\n"
                "## Social Check\n"
                "```json\n"
                f"{json.dumps(debug_payload['social_check'], indent=2, ensure_ascii=False)}\n"
                "```\n\n"
                "## Social Result\n"
                "```json\n"
                f"{json.dumps(debug_payload['social_result'], indent=2, ensure_ascii=False)}\n"
                "```\n\n"
                "## NPC Review\n"
                "```json\n"
                f"{json.dumps(debug_payload['npc_review'], indent=2, ensure_ascii=False)}\n"
                "```\n\n"
                "## Turn Context\n"
                "```json\n"
                f"{json.dumps(debug_payload['turn_context'], indent=2, ensure_ascii=False)}\n"
                "```\n\n"
                "## Narrative Brief\n"
                "```json\n"
                f"{json.dumps(debug_payload['narrative_brief'], indent=2, ensure_ascii=False)}\n"
                "```\n\n"
                "## Skill Check\n"
                "```json\n"
                f"{json.dumps(debug_payload['skill_check'], indent=2, ensure_ascii=False)}\n"
                "```\n\n"
                "## Skill Result\n"
                "```json\n"
                f"{json.dumps(debug_payload['skill_result'], indent=2, ensure_ascii=False)}\n"
                "```\n\n"
                "## Known NPCs Snapshot\n"
                "```json\n"
                f"{json.dumps(debug_payload['known_npcs_snapshot'], indent=2, ensure_ascii=False)}\n"
                "```\n\n"
                "## Full Prompt\n"
                "```text\n"
                f"{prompt}\n"
                "```\n"
            )
            (path_config.logs_dir / DM_PROMPT_DEBUG_FILE_NAME).write_text(markdown, encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to write DM prompt debug file: {e}")
    def _call_mistral_api(self, prompt: str) -> str:
        """Call the Mistral API with the improved novel-style prompt."""
        api_key = self.api_manager.api_key
        dm_style_rules = self._dm_prose_style_rules()

        # === IMPROVED DM PROMPT ===
        system_content = f"""You are an expert Dungeon Master narrating a dark fantasy TTRPG in a novel-like style.

Core Rules:
- Never speak or act for the player. Incorporate exactly what they said and did into the narrative.
- Fix the player's grammar and spelling when weaving their actions/words into the story.
- Write in third-person limited, focusing on what the player experiences.
- Responses should be {DM_NARRATIVE_MIN_PARAGRAPHS} to {DM_NARRATIVE_MAX_PARAGRAPHS} well-flowing narrative paragraphs before the JSON command block.
- Do not summarize or repeat the scene setting unless something meaningful has changed.

Structure:
1. First paragraph: Retell the player's most recent action or spoken words in narrative form before showing outcomes.
2. Middle paragraph: Show only the immediate result: NPC reaction, body language, short dialogue, and direct consequences.
3. Optional final paragraph: Add one extra immediate consequence only if needed, then stop at the first clear player response opportunity.
4. Include at most {DM_NARRATIVE_RESPONSE_HOOKS} clear response hook. A hook can be a direct question, request, accusation, choice point, or quoted line that naturally invites the player to answer.
5. Once the response hook appears, do not continue with a second question, warning, scene beat, or new complication. Never write "What do you do next?"

Style Guidelines:
{dm_style_rules}

Remember: These responses will be stitched together into a continuous story. Prioritize flow and readability above all."""

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": prompt},
        ]

        input_tokens = self.api_manager._estimate_token_count(messages)

        if not api_key:
            fallback = self._fallback_dm_response()
            self._write_dm_response_debug(fallback, {"source": "fallback", "reason": "missing api key"}, input_tokens)
            self.api_manager.record_token_usage("dm_narration", input_tokens, self.api_manager._estimate_token_count(fallback), True, source="fallback")
            return fallback

        if requests is None:
            fallback = self._fallback_dm_response("requests is not installed")
            self._write_dm_response_debug(fallback, {"source": "fallback", "reason": "requests is not installed"}, input_tokens)
            self.api_manager.record_token_usage("dm_narration", input_tokens, self.api_manager._estimate_token_count(fallback), False, source="fallback")
            return fallback

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": self.api_manager.dm_model,
            "messages": messages,
            "temperature": MODEL_DM_TEMPERATURE,
            "max_tokens": MODEL_DM_MAX_TOKENS
        }

        try:
            self.api_manager.delay_before_call()
            response = requests.post(API_ENDPOINT, headers=headers, json=data, timeout=API_DM_TIMEOUT_SECONDS)
            response.raise_for_status()

            result = response.json()
            content = result["choices"][0]["message"]["content"].strip()

            self._write_dm_response_debug(content, result, input_tokens)
            self.api_manager.record_token_usage(
                "dm_narration", input_tokens, 
                self.api_manager._estimate_token_count(content), True, source="game_engine"
            )
            return content

        except Exception as e:
            error_msg = f"[API ERROR] {type(e).__name__}: {str(e)}"
            print(error_msg)
            fallback = self._fallback_dm_response(error_msg)
            self._write_dm_response_debug(fallback, {"source": "fallback", "reason": error_msg}, input_tokens)
            self.api_manager.record_token_usage("dm_narration", input_tokens, self.api_manager._estimate_token_count(fallback), False, source="game_engine")
            return fallback
            
    def _write_dm_response_debug(self, content: str, raw_response: Optional[Dict[str, Any]] = None,
                                 input_tokens: Optional[int] = None):
        """Persist the latest raw DM response so post-call failures are diagnosable."""
        try:
            path_config.logs_dir.mkdir(parents=True, exist_ok=True)
            payload = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "prompt_type": "dm_narration",
                "model": self.api_manager.dm_model,
                "input_tokens_estimate": input_tokens,
                "content": content,
                "raw_response": raw_response or {},
            }
            (path_config.logs_dir / DM_RESPONSE_DEBUG_JSON_FILE_NAME).write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except Exception as e:
            logger.error(f"Failed to write DM response debug file: {e}")
    def _fallback_dm_response(self, reason: str = "") -> str:
        """Return a playable no-op DM response when the API is unavailable."""
        detail = f" ({reason})" if reason else ""
        command = {
            "action": "narrative",
            "command": {
                "message": f"Fallback DM response used{detail}. No mechanical state change was applied."
            }
        }
        return (
            "The world pauses around your action, and the moment is recorded. "
            "No deeper mechanical change is applied while the live DM API is unavailable.\n"
            f"```json\n{json.dumps(command)}\n```"
        )
    
    def _compact_text(self, value: Any, max_chars: int = PROMPT_COMPACT_TEXT_CHARS) -> str:
        """Collapse whitespace and cap text for prompt budget control."""
        compact = " ".join(str(value or "").split())
        if len(compact) <= max_chars:
            return compact
        return compact[:max_chars - 3].rstrip() + "..."
    def _compact_list_text(self, values: Any, max_items: int = PROMPT_COMPACT_LIST_ITEMS,
                           max_chars: int = PROMPT_COMPACT_LIST_CHARS) -> List[str]:
        """Return a bounded list of compact strings."""
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, list):
            return []
        compacted = []
        for value in values[-max_items:]:
            text = self._compact_text(value, max_chars)
            if text:
                compacted.append(text)
        return compacted
    def _compact_recent_exchanges(self, limit: int = PROMPT_RECENT_EXCHANGE_LIMIT,
                                  max_player_chars: int = PROMPT_RECENT_PLAYER_CHARS,
                                  max_dm_chars: int = PROMPT_RECENT_DM_CHARS) -> List[Dict[str, str]]:
        """Return recent exchanges with bounded text for prompt use."""
        return [
            {
                "player": self._compact_text(exchange.get("player", ""), max_player_chars),
                "dm": self._compact_text(exchange.get("dm", ""), max_dm_chars),
            }
            for exchange in self.conversation_manager.get_recent_exchanges(limit)
        ]
    def _compact_player_for_prompt(self) -> Dict[str, Any]:
        """Keep only player fields the models need for turn reasoning."""
        player = self.game_state.get("player", {})
        identity = player.get("identity") if isinstance(player.get("identity"), dict) else {}
        stats = player.get("stats") if isinstance(player.get("stats"), dict) else {}
        skills = player.get("skills") if isinstance(player.get("skills"), dict) else {}
        derived = player.get("derived") if isinstance(player.get("derived"), dict) else {}
        nonzero_skills = {
            name: round(float(value), 3)
            for name, value in skills.items()
            if isinstance(value, (int, float)) and abs(float(value)) > 0.0001
        }
        return {
            "identity": {
                "name": identity.get("name") or player.get("name", ""),
                "race": identity.get("race") or player.get("race", ""),
                "gender": identity.get("gender", ""),
                "class_theme": identity.get("class_theme", ""),
                "reputation": identity.get("reputation", 0),
            },
            "stats": {key: round(float(value), 3) for key, value in stats.items() if isinstance(value, (int, float))},
            "trained_skills": nonzero_skills,
            "derived": {
                "HP": derived.get("HP"),
                "HP_max": derived.get("HP_max"),
                "MP": derived.get("MP"),
                "MP_max": derived.get("MP_max"),
                "AC": derived.get("AC"),
            },
        }
    def _compact_player_possessions_for_prompt(self) -> Dict[str, Any]:
        """Return explicit possessions so narration does not invent supplies."""
        player = self.game_state.get("player", {})
        inventory = player.get("inventory") if isinstance(player.get("inventory"), dict) else {}
        equipment = player.get("equipment") if isinstance(player.get("equipment"), dict) else {}
        return {
            "inventory": inventory,
            "equipment": equipment,
            "gold": player.get("gold", 0) if isinstance(player, dict) else 0,
            "constraints": [
                "Do not invent carried items, tools, containers, weapons, food, water, or medical supplies.",
                "If inventory and equipment are empty, the player has no recorded carried gear.",
                "Worn clothing may be torn or damaged only when the player explicitly uses it that way.",
            ],
        }
    def _compact_racial_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        """Trim racial reference data without dropping descriptive utility."""
        compact = {
            "name": self._compact_text(profile.get("name", ""), 60),
            "description": self._compact_text(profile.get("description", ""), 240),
            "appearance": self._compact_text(profile.get("appearance", ""), 220),
            "culture": self._compact_text(profile.get("culture", ""), 180),
            "current_status": self._compact_text(profile.get("current_status", ""), 180),
        }
        relations = profile.get("relations")
        if isinstance(relations, dict):
            compact["relations"] = {
                str(key): self._compact_text(value, 90)
                for key, value in list(relations.items())[:4]
            }
        subraces = profile.get("subraces")
        if isinstance(subraces, dict):
            compact["subraces"] = {
                key: {
                    "name": self._compact_text(value.get("name", key), 60),
                    "description": self._compact_text(value.get("description", ""), 160),
                    "appearance": self._compact_text(value.get("appearance", ""), 160),
                    "current_status": self._compact_text(value.get("current_status", ""), 120),
                }
                for key, value in list(subraces.items())[:4]
                if isinstance(value, dict)
            }
        return {key: value for key, value in compact.items() if value not in ("", {}, [])}
    def _compact_dc_evaluation_for_prompt(self, evaluation: Any) -> Dict[str, Any]:
        """Keep only DC facts models must obey; omit raw model chatter."""
        if not isinstance(evaluation, dict):
            return {}
        def compact_modifiers(modifiers: Any) -> List[Dict[str, Any]]:
            if not isinstance(modifiers, list):
                return []
            compacted = []
            for modifier in modifiers[:3]:
                if not isinstance(modifier, dict):
                    continue
                compacted.append({
                    "fact": self._compact_text(modifier.get("fact", ""), 160),
                    "category": self._compact_text(modifier.get("category", ""), 60),
                    "scope": self._compact_text(modifier.get("scope", ""), 80),
                    "effect": modifier.get("effect", ""),
                    "modifier": modifier.get("modifier", 0),
                    "reason": self._compact_text(modifier.get("reason", ""), 120),
                })
            return compacted
        return {
            "base_dc": evaluation.get("base_dc"),
            "final_dc": evaluation.get("final_dc"),
            "positive_modifiers": compact_modifiers(evaluation.get("applied_positive_modifiers")),
            "negative_modifiers": compact_modifiers(evaluation.get("applied_negative_modifiers")),
            "notes": self._compact_text(evaluation.get("notes", ""), 180),
        }
    def _compact_skill_check_for_prompt(self, skill_check: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Compact a detected skill check for downstream prompts."""
        if not isinstance(skill_check, dict) or not skill_check.get("needs_skill_check"):
            return {"needs_skill_check": False}
        return {
            "needs_skill_check": True,
            "skill": skill_check.get("skill", ""),
            "stats_used": skill_check.get("stats_used", []),
            "difficulty_class": skill_check.get("difficulty_class", 0),
            "reason": self._compact_text(skill_check.get("reason", ""), 160),
            "stakes": self._compact_text(skill_check.get("stakes", ""), 160),
            "dc_evaluation": self._compact_dc_evaluation_for_prompt(skill_check.get("dc_evaluation", {})),
        }
    def _compact_skill_result_for_prompt(self, skill_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Compact a resolved skill roll for downstream prompts."""
        if not isinstance(skill_result, dict) or not skill_result:
            return {}
        return {
            "skill": skill_result.get("skill"),
            "success": skill_result.get("success"),
            "roll": skill_result.get("roll"),
            "difficulty_class": skill_result.get("difficulty_class"),
            "margin": skill_result.get("margin"),
            "total_bonus": skill_result.get("total_bonus"),
            "growth_added": skill_result.get("growth_added", {}),
        }
    def _compact_social_check_for_prompt(self, social_check: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Compact a social check decision."""
        if not isinstance(social_check, dict) or not social_check.get("needs_social_check"):
            return {"needs_social_check": False}
        return {
            "needs_social_check": True,
            "target_npc": social_check.get("target_npc"),
            "interaction_type": social_check.get("interaction_type"),
            "reason": self._compact_text(social_check.get("reason", ""), 160),
        }
    def _compact_social_result_for_prompt(self, social_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Compact resolved social mechanics and NPC reaction."""
        if not isinstance(social_result, dict) or not social_result:
            return {}
        result = social_result.get("social_result") if isinstance(social_result.get("social_result"), dict) else {}
        reaction = social_result.get("npc_reaction") if isinstance(social_result.get("npc_reaction"), dict) else {}
        return {
            "success": result.get("success"),
            "roll": result.get("roll"),
            "difficulty_class": result.get("difficulty_class") or result.get("dc"),
            "trust_change": result.get("trust_change"),
            "relationship": result.get("new_relationship"),
            "mood": result.get("emotional_response") or result.get("mood"),
            "reaction": {
                "dialogue": self._compact_text(reaction.get("dialogue", ""), 180),
                "body_language": self._compact_text(reaction.get("body_language", ""), 120),
            },
        }
    def _compact_turn_context_for_prompt(self, turn_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Compact the context-model output for downstream prompts."""
        if not isinstance(turn_context, dict):
            return {}
        return {
            "involved_npcs": turn_context.get("involved_npcs", []),
            "relevant_races": turn_context.get("relevant_races", []),
            "likely_intent": self._compact_text(turn_context.get("likely_intent", ""), 220),
            "mechanical_risks": self._compact_list_text(turn_context.get("mechanical_risks", []), 5, 160),
            "continuity_constraints": self._compact_list_text(turn_context.get("continuity_constraints", []), 5, 160),
            "forbidden_assumptions": self._compact_list_text(turn_context.get("forbidden_assumptions", []), 5, 160),
            "scene_focus": self._compact_text(turn_context.get("scene_focus", ""), 240),
            "relevant_lore_keys": turn_context.get("relevant_lore_keys", []),
        }
    def _compact_npc_review_for_prompt(self, npc_review: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Compact NPC review output for DM and summary prompts."""
        if not isinstance(npc_review, dict):
            return {"npc_actions": []}
        actions = []
        for action in npc_review.get("npc_actions", [])[:5] if isinstance(npc_review.get("npc_actions"), list) else []:
            if not isinstance(action, dict):
                continue
            actions.append({
                "npc_id": action.get("npc_id"),
                "name": action.get("name"),
                "action": self._compact_text(action.get("action", ""), 180),
                "dialogue": self._compact_text(action.get("dialogue", ""), 180),
                "body_language": self._compact_text(action.get("body_language", ""), 120),
                "constraints": action.get("constraints", {}),
            })
        return {"npc_actions": actions, "notes": self._compact_text(npc_review.get("notes", ""), 180)}
    def _load_racial_profiles(self) -> Dict[str, Any]:
        """Load racial profile reference data for prompt context."""
        try:
            if path_config.racial_profiles_path.exists():
                with open(path_config.racial_profiles_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                return loaded if isinstance(loaded, dict) else {}
        except Exception as e:
            logger.error(f"Failed to load racial profiles: {e}")
        return {}
    def _racial_profile_key(self, race: Any) -> str:
        """Map game-facing race/subrace names to racial_profiles.json keys."""
        normalized = self._normalize_key_text(race).replace(" ", "_").replace("-", "_")
        aliases = {
            "beastfolk": "beastkin",
            "beast_kin": "beastkin",
            "true_beastfolk": "beastkin",
            "true_beastkin": "beastkin",
            "nekko": "nekko",
            "nekkko": "nekko",
            "nekko_beastfolk": "nekko",
            "nekkko_beastfolk": "nekko",
            "nekko_beastkin": "nekko",
            "nekkko_beastkin": "nekko",
            "feline_beastfolk": "nekko",
            "feline_beastkin": "nekko",
            "catfolk": "nekko",
            "low_caste_demon": "demon",
            "high_caste_demon": "demon",
        }
        return aliases.get(normalized, normalized)
    def _racial_appearance_constraints(self, turn_context: Optional[Dict[str, Any]] = None) -> List[str]:
        """Flatten selected racial appearance facts into hard narration constraints."""
        constraints = []
        for profile in self._select_racial_profiles(turn_context).values():
            name = profile.get("name", "")
            appearance = profile.get("appearance", "")
            if name and appearance:
                constraints.append(f"{name}: {appearance}")
                if self._normalize_key_text(name) == "nekko":
                    constraints.append(
                        "Nekko use the Nekko racial profile; describe smooth skin with animal ears, tail, claws, and eyes, not full-body fur unless an individual NPC record says otherwise."
                    )
            subraces = profile.get("subraces", {})
            if isinstance(subraces, dict):
                for subrace in subraces.values():
                    if not isinstance(subrace, dict):
                        continue
                    sub_name = subrace.get("name", "")
                    sub_appearance = subrace.get("appearance", "")
                    if sub_name and sub_appearance:
                        constraints.append(f"{sub_name}: {sub_appearance}")
                    if self._normalize_key_text(sub_name) == "nekko":
                        constraints.append(
                            "Nekko use the Nekko subrace appearance, not True Beastkin traits; do not describe fur unless an individual NPC record says so."
                        )
        return constraints[:8]
    def _collect_relevant_races(self, turn_context: Optional[Dict[str, Any]] = None) -> List[str]:
        """Return racial profile keys likely relevant to the current prompt."""
        races = []
        player = self.game_state.get("player", {})
        if isinstance(player, dict):
            identity = player.get("identity") if isinstance(player.get("identity"), dict) else {}
            races.extend([identity.get("race"), identity.get("sub-race"), player.get("race"), player.get("sub-race")])
        npcs = self.game_state.get("npcs", {})
        involved_npcs = []
        if isinstance(turn_context, dict):
            involved_npcs = [str(npc_id) for npc_id in turn_context.get("involved_npcs", []) or []]
        npc_items = (
            [(npc_id, npcs.get(npc_id)) for npc_id in involved_npcs if isinstance(npcs, dict)]
            if involved_npcs else list(npcs.items() if isinstance(npcs, dict) else [])
        )
        for _, npc in npc_items:
            if isinstance(npc, dict):
                races.extend([self._get_npc_field(npc, "race"), self._get_npc_field(npc, "sub-race")])
        if isinstance(turn_context, dict):
            races.extend(turn_context.get("relevant_races", []) or [])
            races.extend(turn_context.get("relevant_lore_keys", []) or [])
        profile_keys = []
        for race in races:
            key = self._racial_profile_key(race)
            if key and key not in profile_keys:
                profile_keys.append(key)
        return profile_keys
    def _select_racial_profiles(self, turn_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Select compact racial profiles relevant to this turn."""
        profiles = self._load_racial_profiles()
        selected = {}
        for key in self._collect_relevant_races(turn_context):
            profile = profiles.get(key)
            if not isinstance(profile, dict):
                continue
            selected[key] = self._compact_racial_profile({**profile, "name": profile.get("name", key)})
        return selected
    def _story_bible_excerpt(self, player_input: str,
                             turn_context: Optional[Dict[str, Any]] = None,
                             max_chars: int = PROMPT_STORY_BIBLE_CHARS) -> str:
        """Select a compact story bible excerpt relevant to this turn."""
        bible = self.conversation_manager.story_bible or ""
        if len(bible) <= max_chars:
            return bible
        keywords = set(re.findall(r"[a-zA-Z]{4,}", player_input.lower()))
        if isinstance(turn_context, dict):
            for value in (turn_context.get("relevant_races", []) or []) + (turn_context.get("relevant_lore_keys", []) or []):
                keywords.add(str(value).lower())
            for value in turn_context.get("involved_npcs", []) or []:
                keywords.add(str(value).lower())
        for value in ["elyndor", "demon", "caravan", "rift"]:
            keywords.add(value)
        paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", bible) if paragraph.strip()]
        scored = []
        for paragraph in paragraphs:
            lower = paragraph.lower()
            score = sum(1 for keyword in keywords if keyword and keyword in lower)
            if score:
                scored.append((score, paragraph))
        scored.sort(key=lambda item: item[0], reverse=True)
        excerpt_parts = []
        length = 0
        for _, paragraph in scored[:6]:
            if length + len(paragraph) + 2 > max_chars:
                break
            excerpt_parts.append(paragraph)
            length += len(paragraph) + 2
        if not excerpt_parts:
            return self._compact_text(bible, max_chars)
        return "\n\n".join(excerpt_parts)
    def _knowledge_priority_context(self) -> Dict[str, Any]:
        """Return the source-priority contract shared by story-facing prompts."""
        return {
            "highest_to_lowest": KNOWLEDGE_PRIORITY_RULES,
            "saved_game_state_examples": [
                "scenario.current_scene",
                "scenario.scene_facts",
                "world.facts",
                "NPC identity/known_facts",
                "player identity/inventory/equipment",
            ],
        }
    def _format_knowledge_priority_for_prompt(self) -> str:
        """Format source priority for the final DM prompt."""
        return "\n".join(
            f"{index}. {rule}"
            for index, rule in enumerate(KNOWLEDGE_PRIORITY_RULES, start=1)
        )
    def _dm_prose_style_rules(self) -> str:
        """Return prose intensity and repetition guardrails for DM narration."""
        heat_profiles = {
            0: ("plain referee", "Use spare, practical sentences with almost no imagery."),
            1: ("grounded", "Use clean narrative prose with at most one concrete sensory detail."),
            2: ("restrained novel", "Use vivid but economical prose; let action and dialogue carry the scene."),
            3: ("atmospheric", "Use richer atmosphere when it sharpens tension, but keep it tied to action."),
            4: ("lyrical", "Use expressive description, but avoid slowing the turn or obscuring consequences."),
            5: ("ornate", "Use high fantasy flourish while still obeying pacing and clarity limits."),
        }
        label, guidance = heat_profiles.get(DM_PROSE_HEAT, heat_profiles[1])
        return "\n".join([
            f"PROSE HEAT: {DM_PROSE_HEAT}/5 ({label})",
            f"- {guidance}",
            "- Do not re-describe the environment unless it changed or the player directly interacts with it.",
            "- Use at most one environmental or sensory sentence per response unless the environment is the obstacle.",
            "- Prefer concrete action, NPC behavior, dialogue, and consequences over atmosphere.",
            "- Avoid ornate similes, repeated motifs, and stock dramatic phrasing.",
            "- Do not reuse distinctive images from recent DM responses unless continuity requires it.",
        ])
    def _get_scene_context(self) -> str:
        """Return the active scene that the DM must treat as current reality."""
        scenario = self.game_state.get("scenario", {})
        opening_scene = scenario.get("opening_scene", {})
        current_scene = scenario.get("current_scene") or opening_scene.get("text")
        if current_scene:
            return current_scene
        return ""
    def _opening_scene_context(self) -> Dict[str, Any]:
        """Return the opening-scene seed for prompt continuity."""
        scenario = self.game_state.get("scenario", {})
        opening_scene = scenario.get("opening_scene", {})
        if not isinstance(opening_scene, dict):
            return {}
        text = self._compact_text(opening_scene.get("text", ""), PROMPT_OPENING_SCENE_CHARS)
        if not text:
            return {}
        return {
            "title": self._compact_text(opening_scene.get("title", "Opening Scene"), 120),
            "text": text,
            "status": opening_scene.get("status", ""),
            "source": scenario.get("current_scene_source", ""),
        }
    def _get_known_npcs_for_prompt(self) -> List[Dict[str, Any]]:
        """Return only NPCs active in the save state, never the reference library."""
        known = {}
        player = self.game_state.get("player", {})
        player_identity = player.get("identity") if isinstance(player, dict) and isinstance(player.get("identity"), dict) else {}
        player_name = self._normalize_key_text(player_identity.get("name") or (player.get("name") if isinstance(player, dict) else ""))
        player_key = self._make_npc_id_from_name(player_name) if player_name else ""
        for npc_id, npc in self.game_state.get("npcs", {}).items():
            if isinstance(npc, dict):
                npc_name = self._get_npc_field(npc, "name", npc_id)
                if player_name and (
                    self._normalize_key_text(npc_name) == player_name
                    or self._normalize_key_text(npc_id) == self._normalize_key_text(player_key)
                ):
                    continue
                known[npc_id] = {
                    "npc_id": npc_id,
                    "name": npc_name,
                    "race": self._get_npc_field(npc, "race", ""),
                    "role": self._get_npc_field(npc, "title", ""),
                    "relationship": self._get_npc_field(npc, "relationship", "neutral"),
                    "mood": self._get_npc_field(npc, "mood", "neutral"),
                }
        return list(known.values())
    def _player_known_facts_for_dc(self) -> List[str]:
        """Return player facts relevant to DC adjudication without full player stats."""
        player = self.game_state.get("player", {})
        identity = player.get("identity") if isinstance(player, dict) and isinstance(player.get("identity"), dict) else {}
        facts = []
        facts.extend(identity.get("known_facts", []) if isinstance(identity.get("known_facts"), list) else [])
        inventory = player.get("inventory") if isinstance(player, dict) and isinstance(player.get("inventory"), dict) else {}
        equipment = player.get("equipment") if isinstance(player, dict) and isinstance(player.get("equipment"), dict) else {}
        if inventory:
            facts.append(f"Recorded inventory: {json.dumps(inventory, ensure_ascii=False)}")
        else:
            facts.append("Recorded inventory: empty; no carried tools, containers, supplies, food, or water are available unless explicitly added.")
        if equipment:
            facts.append(f"Recorded equipment: {json.dumps(equipment, ensure_ascii=False)}")
        else:
            facts.append("Recorded equipment: empty.")
        return self._compact_list_text(facts, 12, 260)
    def _relevant_npc_known_facts_for_dc(self, player_input: str, skill_detection: Dict[str, Any],
                                         context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Return facts for NPCs that are both in game_state and named in this DC packet."""
        npcs = self.game_state.get("npcs", {})
        if not isinstance(npcs, dict):
            return []
        turn_context = context.get("turn_context", {}) if isinstance(context.get("turn_context"), dict) else {}
        involved = {str(npc_id) for npc_id in turn_context.get("involved_npcs", []) or []}
        info_text = self._normalize_key_text(" ".join([
            str(player_input or ""),
            str(skill_detection.get("reason", "")),
            str(skill_detection.get("stakes", "")),
            " ".join(str(fact) for fact in context.get("scene_facts", []) or []),
            " ".join(str(fact) for fact in context.get("world_facts", []) or []),
            " ".join(involved),
        ]))
        relevant = []
        for npc_id, npc in npcs.items():
            if not isinstance(npc, dict):
                continue
            name = self._get_npc_field(npc, "name", "")
            aliases = npc.get("aliases", []) if isinstance(npc.get("aliases"), list) else []
            identifiers = [npc_id, name, self._get_npc_field(npc, "title", "")]
            identifiers.extend(aliases)
            mentioned = str(npc_id) in involved or any(
                ident and self._normalize_key_text(ident) in info_text
                for ident in identifiers
            )
            if not mentioned:
                continue
            facts = self._get_npc_field(npc, "known_facts", [])
            relevant.append({
                "npc_id": npc_id,
                "name": name,
                "race": self._get_npc_field(npc, "race", ""),
                "relationship": self._get_npc_field(npc, "relationship", "neutral"),
                "mood": self._get_npc_field(npc, "mood", "neutral"),
                "known_facts": self._compact_list_text(facts, 8, 220),
            })
        return relevant[:5]
    def _build_dc_evaluation_context(self, player_input: str, skill_detection: Dict[str, Any],
                                     context: Dict[str, Any], suggested_base: int) -> Dict[str, Any]:
        """Build the intentionally narrow fact packet for DC adjudication."""
        return {
            "knowledge_priority": self._knowledge_priority_context(),
            "story_bible_excerpt": context.get("story_bible_excerpt", ""),
            "player_input": player_input,
            "proposed_check": {
                "skill": skill_detection.get("skill", ""),
                "stats_used": skill_detection.get("stats_used", []),
                "base_dc": suggested_base,
                "task_goal": self._compact_text(skill_detection.get("reason", ""), 220),
                "stakes": self._compact_text(skill_detection.get("stakes", ""), 220),
            },
            "scene_facts": context.get("scene_facts", []),
            "player_known_facts": self._player_known_facts_for_dc(),
            "relevant_npc_known_facts": self._relevant_npc_known_facts_for_dc(player_input, skill_detection, context),
        }
    def _resolve_detected_npc_id(self, target: str, known_npcs: List[Dict[str, Any]]) -> Optional[str]:
        """Map detector target text to a known NPC id."""
        return self._resolve_npc_reference(target, known_npcs)
    def _build_turn_evaluation_context(self, player_input: str) -> Dict[str, Any]:
        """Context used by pre-DM evaluation prompts."""
        return {
            "knowledge_priority": self._knowledge_priority_context(),
            "player_input": player_input,
            "summary_file": self._compact_text(self.conversation_manager.get_summary_file_text(), PROMPT_COMPACT_TEXT_CHARS),
            "last_4_exchanges": self._compact_recent_exchanges(PROMPT_RECENT_EXCHANGE_LIMIT),
            "opening_scene": self._opening_scene_context(),
            "current_scene": self._compact_text(self._get_scene_context(), PROMPT_SCENE_CONTEXT_CHARS),
            "scene_facts": self._compact_list_text(self.game_state.get("scenario", {}).get("scene_facts", []), 12, 220),
            "world_facts": self._compact_list_text(self.game_state.get("world", {}).get("facts", []), 8, 220),
            "known_npcs": self._get_known_npcs_for_prompt(),
            "location": self.game_state.get("world", {}).get("location", {}),
            "player": self._compact_player_for_prompt(),
            "player_possessions": self._compact_player_possessions_for_prompt(),
            "story_bible_excerpt": self._story_bible_excerpt(player_input, max_chars=PROMPT_STORY_BIBLE_CHARS),
            "racial_profiles": self._select_racial_profiles(),
        }
    def _build_shared_story_context(self, player_input: str,
                                    turn_context: Optional[Dict[str, Any]] = None,
                                    narrative_brief: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Story continuity packet shared by DM and NPC-facing prompts."""
        scene_facts = self._compact_list_text(
            self.game_state.get("scenario", {}).get("scene_facts", []),
            12,
            220,
        )
        world_facts = self._compact_list_text(
            self.game_state.get("world", {}).get("facts", []),
            8,
            220,
        )
        return {
            "knowledge_priority": self._knowledge_priority_context(),
            "campaign_summary": self._compact_text(self.conversation_manager.get_summary_file_text(), PROMPT_COMPACT_TEXT_CHARS),
            "recent_exchanges": self._compact_recent_exchanges(PROMPT_RECENT_EXCHANGE_LIMIT),
            "opening_scene": self._opening_scene_context(),
            "current_scene": self._compact_text(self._get_scene_context(), PROMPT_SCENE_CONTEXT_CHARS),
            "scene_brief": self._compact_text((narrative_brief or {}).get("scene_brief", ""), PROMPT_SCENE_BRIEF_CHARS),
            "scene_facts": scene_facts,
            "world_facts": world_facts,
            "known_npcs": self._get_known_npcs_for_prompt(),
            "location": self.game_state.get("world", {}).get("location", {}),
            "player": self._compact_player_for_prompt(),
            "player_possessions": self._compact_player_possessions_for_prompt(),
            "turn_context": self._compact_turn_context_for_prompt(turn_context),
            "relevant_lore": self._select_dm_lore_profiles(player_input, turn_context, scene_facts),
            "story_bible_excerpt": self._story_bible_excerpt(player_input, turn_context, max_chars=PROMPT_STORY_BIBLE_CHARS),
        }
    def _evaluate_turn_context(self, player_input: str) -> Dict[str, Any]:
        """Use the context model to decide what context matters this turn."""
        context = self._build_turn_evaluation_context(player_input)
        evaluation = self.api_manager.call_api(
            "turn_context_evaluation",
            context,
            temperature=MODEL_TURN_CONTEXT_TEMPERATURE,
            max_tokens=MODEL_TURN_CONTEXT_MAX_TOKENS,
        )
        if not isinstance(evaluation, dict):
            evaluation = {}
        known_npcs = context.get("known_npcs", [])
        evaluation.setdefault("involved_npcs", [])
        evaluation.setdefault("relevant_races", self._collect_relevant_races(evaluation))
        evaluation.setdefault("mechanical_risks", [])
        evaluation.setdefault("continuity_constraints", [])
        evaluation.setdefault("forbidden_assumptions", [])
        evaluation.setdefault("scene_focus", self._compact_text(context.get("current_scene", ""), 700))
        evaluation.setdefault("relevant_lore_keys", evaluation.get("relevant_races", []))
        resolved_npcs = []
        for npc_ref in evaluation.get("involved_npcs", []) or []:
            resolved = self._resolve_npc_reference(str(npc_ref), known_npcs)
            if resolved and resolved not in resolved_npcs:
                resolved_npcs.append(resolved)
        evaluation["involved_npcs"] = resolved_npcs
        evaluation["relevant_races"] = self._collect_relevant_races(evaluation)
        return evaluation
    def _coerce_dc_int(self, value: Any, default: int = 50) -> int:
        """Coerce a DC-like value to a clamped whole number."""
        try:
            return int(round(float(value)))
        except (TypeError, ValueError):
            return default
    def _validate_dc_modifier(self, modifier: Any, skill: str = "") -> Optional[Dict[str, Any]]:
        """Normalize one model-proposed DC modifier."""
        if not isinstance(modifier, dict):
            return None
        fact = self._compact_text(modifier.get("fact", ""), 240)
        if not fact:
            return None
        value = self._coerce_dc_int(modifier.get("modifier", 0), 0)
        value = max(-20, min(20, value))
        relevance = self._coerce_dc_int(modifier.get("relevance", 0), 0)
        relevance = max(0, min(100, relevance))
        effect = self._normalize_key_text(modifier.get("effect", ""))
        if effect in {"helps", "easier", "benefit", "advantage"}:
            value = -abs(value)
        elif effect in {"hurts", "harder", "penalty", "disadvantage"}:
            value = abs(value)
        elif effect in {"neutral", "irrelevant", "none"}:
            value = 0
        value = self._remove_character_ability_dc_modifier(fact, modifier.get("reason", ""), value)
        return {
            "fact": fact,
            "category": self._compact_text(modifier.get("category", ""), 60),
            "scope": self._compact_text(modifier.get("scope", ""), 80),
            "effect": effect or ("helps" if value < 0 else "hurts" if value > 0 else "neutral"),
            "modifier": value,
            "relevance": relevance,
            "reason": self._compact_text(modifier.get("reason", ""), 220),
        }
    def _normalize_dc_modifier_magnitude(self, fact: str, reason: Any, value: int, skill: str = "") -> int:
        """Normalize obvious major/minor factor magnitudes."""
        if value == 0:
            return 0
        skill = str(skill or "").lower()
        fact_text = str(fact or "").lower()
        text = f"{fact} {reason}".lower()
        sign = -1 if value < 0 else 1
        magnitude = abs(value)
        cover_context = (
            re.search(r"\bcover\b", text) is not None
            or any(term in text for term in [
                "concealed", "concealment", "forest cover", "under cover",
                "cover and concealment", "better concealment", "foliage", "underbrush"
            ])
        )
        if skill == "stealth":
            if any(term in text for term in ["hundred yards", "100 yards", "one hundred yards"]):
                return -max(magnitude, 10)
            if any(term in fact_text for term in ["distracted", "focused elsewhere", "focused on another target", "not actively searching"]):
                return -max(magnitude, 10)
            if any(term in fact_text for term in ["actively searching", "on alert", "watching the route", "attention fixed"]):
                if "not actively searching" not in text:
                    return max(magnitude, 10)
            if any(term in fact_text for term in ["player is moving carefully", "controlled movement", "carefully and gently", "gently to avoid"]):
                return -max(magnitude, 2)
            if any(term in fact_text for term in ["chain", "rattle", "metal restraints"]):
                return max(magnitude, 6)
            if any(term in fact_text for term in ["visible mark", "glowing mark", "glowing", "draw attention"]):
                return max(magnitude, 2)
            if any(term in fact_text for term in ["wounded", "unconscious", "moving another body", "moving a wounded"]):
                return max(magnitude, 8)
            if cover_context:
                return -max(magnitude, 5)
        elif skill == "medicine":
            if any(term in fact_text for term in ["unconscious", "eliminating resistance", "removes patient cooperation"]):
                return -min(max(magnitude, 1), 2)
            if cover_context or any(term in text for term in ["stable environment", "reducing risk of interruption"]):
                return -min(max(magnitude, 1), 3)
            if any(term in fact_text for term in ["chains", "restraints", "restrained"]):
                return -min(max(magnitude, 1), 2)
            if any(term in fact_text for term in ["improvised", "lack of proper tools", "no proper tools"]):
                return min(max(magnitude, 2), 6)
            if any(term in text for term in ["remain unaware", "remains unaware", "distracted enemies reduce", "reduce the risk of interruption", "reduces the risk of interruption"]):
                return -min(max(magnitude, 1), 3)
            if any(term in text for term in ["nearby danger", "threat of discovery", "persistent threat", "circling overhead", "time pressure", "mental burden"]):
                return min(max(magnitude, 2), 6)
            if "actively engaged" in text:
                return -min(max(magnitude, 1), 3)
            if any(term in fact_text for term in ["bleeding", "deep wound", "severe wound", "infection"]):
                return min(max(magnitude, 2), 8)
        return sign * magnitude
    def _correct_dc_modifier_sign(self, fact: str, reason: Any, value: int, skill: str = "") -> int:
        """Correct obvious sign inversions from model output."""
        if value == 0:
            return 0
        skill = str(skill or "").lower()
        text = f"{fact} {reason}".lower()
        explicitly_easier = any(term in text for term in [
            "distracted enemies are easier",
            "distracted",
            "not actively searching",
            "better concealment",
            "cover improves",
            "improves stealth",
            "reduces noise",
            "reduces exposure",
            "reduces the risk",
            "controlled movement reduces",
            "careful approach",
            "shorter distances reduce",
            "hundred yards",
            "100 yards",
            "far away",
            "eliminating resistance",
            "removes patient cooperation",
            "stable environment",
            "reducing distractions",
            "reducing risk of interruption",
        ])
        explicitly_harder = any(term in text for term in [
            "inherently noisy",
            "adds significant burden",
            "adds burden",
            "making silent movement harder",
            "chains can produce noise",
            "requiring careful handling to avoid rattling",
            "increasing the risk",
            "could draw attention",
            "winged demon",
            "circling overhead",
            "flying observer",
            "aerial detection",
            "on alert",
            "actively searching",
            "watching the route",
            "time pressure",
            "mental burden",
            "lack of proper tools",
            "improvised",
            "increased bleeding",
            "infection",
        ])
        if skill == "medicine" and any(term in text for term in ["unconscious", "eliminating resistance", "removes patient cooperation"]):
            explicitly_harder = False
            explicitly_easier = True
        if skill == "medicine" and any(term in text for term in ["nearby danger", "time pressure", "mental burden", "threat of discovery", "circling overhead"]):
            explicitly_harder = True
            explicitly_easier = False
        if skill == "medicine" and (
            re.search(r"\bcover\b", text) is not None
            or any(term in text for term in ["concealed", "concealment", "stable environment", "reducing distractions"])
        ):
            explicitly_harder = False
            explicitly_easier = True
        if "not actively searching" in text:
            explicitly_harder = explicitly_harder and not any(term in text for term in ["distracted", "not actively searching"])
        if any(term in text for term in ["controlled movement reduces", "moving carefully", "carefully and gently", "avoid agitating"]):
            explicitly_harder = False
            explicitly_easier = True
        if explicitly_harder and not explicitly_easier and value < 0:
            return abs(value)
        if explicitly_easier and not explicitly_harder and value > 0:
            return -abs(value)
        return value
    def _remove_character_ability_dc_modifier(self, fact: str, reason: Any, value: int) -> int:
        """Do not let DC double-count character ability that the roll already handles."""
        text = f"{fact} {reason}".lower()
        ability_terms = [
            "no invested points", "lack of skill investment", "skill investment",
            "limited formal training", "low skill", "high skill",
            "stat", "attribute", "bonus"
        ]
        if any(term in text for term in ability_terms):
            return 0
        return value
    def _rank_dc_modifiers(self, modifiers: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Apply top three positive and top three negative DC modifiers."""
        positives = [mod for mod in modifiers if mod.get("modifier", 0) > 0]
        negatives = [mod for mod in modifiers if mod.get("modifier", 0) < 0]
        zeros = [mod for mod in modifiers if mod.get("modifier", 0) == 0]
        def sort_key(modifier: Dict[str, Any]):
            return (abs(int(modifier.get("modifier", 0))), int(modifier.get("relevance", 0)))
        positives = sorted(positives, key=sort_key, reverse=True)
        negatives = sorted(negatives, key=sort_key, reverse=True)
        applied = positives[:3] + negatives[:3]
        considered = positives[3:] + negatives[3:] + zeros
        return positives[:3], negatives[:3], considered
    def _evaluate_dc(self, player_input: str, skill_detection: Dict[str, Any],
                     context: Dict[str, Any]) -> Dict[str, Any]:
        """Use a general fact-modifier DC evaluator and validate the result in Python."""
        suggested_base = self._coerce_dc_int(skill_detection.get("difficulty_class", 50), 50)
        dc_context = self._build_dc_evaluation_context(player_input, skill_detection, context, suggested_base)
        raw_evaluation = self.api_manager.call_api(
            "dc_evaluation",
            dc_context,
            temperature=MODEL_DC_EVALUATION_TEMPERATURE,
            max_tokens=MODEL_DC_EVALUATION_MAX_TOKENS,
        )
        if not isinstance(raw_evaluation, dict):
            raw_evaluation = {}
        base_dc = self._coerce_dc_int(raw_evaluation.get("base_dc", suggested_base), suggested_base)
        base_dc = max(1, min(100, base_dc))
        candidate_modifiers = raw_evaluation.get("candidate_modifiers", [])
        if not isinstance(candidate_modifiers, list):
            candidate_modifiers = []
        validated_modifiers = []
        seen_facts = set()
        skill_name = str(skill_detection.get("skill", "")).lower()
        for modifier in candidate_modifiers:
            normalized = self._validate_dc_modifier(modifier, skill_name)
            if not normalized:
                continue
            fact_key = self._normalize_key_text(normalized["fact"])
            if fact_key in seen_facts:
                continue
            seen_facts.add(fact_key)
            validated_modifiers.append(normalized)
        applied_positive, applied_negative, considered_not_applied = self._rank_dc_modifiers(validated_modifiers)
        final_dc = base_dc + sum(mod["modifier"] for mod in applied_positive + applied_negative)
        final_dc = max(1, min(100, final_dc))
        return {
            "source": "dc_evaluation",
            "base_dc": base_dc,
            "final_dc": final_dc,
            "applied_positive_modifiers": applied_positive,
            "applied_negative_modifiers": applied_negative,
            "considered_not_applied": considered_not_applied,
            "raw_evaluation": raw_evaluation,
            "notes": raw_evaluation.get("notes", ""),
        }
    def _detect_social_check(self, player_input: str,
                             turn_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Ask the model whether the action needs a social check, with fallback."""
        context = self._build_turn_evaluation_context(player_input)
        if turn_context:
            context["turn_context"] = self._compact_turn_context_for_prompt(turn_context)
            context["racial_profiles"] = self._select_racial_profiles(turn_context)
            context["story_bible_excerpt"] = self._story_bible_excerpt(
                player_input,
                turn_context,
                max_chars=PROMPT_RUNTIME_STORY_BIBLE_CHARS,
            )
        inferred = self.api_manager._infer_social_check(context)
        social_words = [
            "talk", "speak", "say", "ask", "tell", "convince", "persuade",
            "intimidate", "threaten", "bargain", "negotiate", "lie", "deceive",
            "gift", "offer", "plead", "apologize", "flatter", "demand",
            "whisper", "promise", "request", "beg", "comfort", "reassure",
            "help", "trust", "calm", "explain", "warn", "thank"
        ]
        if not inferred.get("needs_social_check") and not any(word in player_input.lower() for word in social_words):
            return {
                "needs_social_check": False,
                "target_npc": None,
                "interaction_type": inferred.get("interaction_type", "appeal"),
                "reason": inferred.get("reason", "No social check needed"),
                "raw_detection": {"source": "local_prefilter", **inferred},
            }
        detection = self.api_manager.call_api(
            "social_check_detection",
            context,
            temperature=MODEL_SOCIAL_DETECTION_TEMPERATURE,
        )
        known_npcs = context["known_npcs"]
        target = detection.get("target_npc") or detection.get("npc_id") or ""
        resolved_target = self._resolve_detected_npc_id(target, known_npcs)
        needs_check = bool(detection.get("needs_social_check", False)) and bool(resolved_target)
        if not needs_check:
            inferred_target = inferred.get("target_npc") or inferred.get("npc_id") or ""
            inferred_resolved = self._resolve_detected_npc_id(inferred_target, known_npcs)
            if inferred.get("needs_social_check") and inferred_resolved:
                detection = inferred
                resolved_target = inferred_resolved
                needs_check = True
        return {
            "needs_social_check": needs_check,
            "target_npc": resolved_target,
            "interaction_type": detection.get("interaction_type", "appeal"),
            "reason": detection.get("reason", "No social check needed" if not needs_check else ""),
            "raw_detection": detection,
        }
    def _detect_skill_check(self, player_input: str,
                            turn_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Ask whether the action needs a non-social mechanical skill check."""
        context = self._build_turn_evaluation_context(player_input)
        if turn_context:
            context["turn_context"] = self._compact_turn_context_for_prompt(turn_context)
            context["racial_profiles"] = self._select_racial_profiles(turn_context)
            context["story_bible_excerpt"] = self._story_bible_excerpt(
                player_input,
                turn_context,
                max_chars=PROMPT_RUNTIME_STORY_BIBLE_CHARS,
            )
        detection = self.api_manager.call_api(
            "skill_check_detection",
            context,
            temperature=MODEL_SKILL_DETECTION_TEMPERATURE,
        )
        needs_check = bool(detection.get("needs_skill_check", False))
        inferred_detection = self.api_manager._infer_skill_check(context)
        if not needs_check and (detection.get("parse_error") or inferred_detection.get("needs_skill_check")):
            detection = inferred_detection
            needs_check = bool(detection.get("needs_skill_check", False))
        stats_used = detection.get("stats_used") or []
        if isinstance(stats_used, str):
            stats_used = [stats_used]
        stats_used = [str(stat).strip().title() for stat in stats_used if str(stat).strip()][:3]
        if needs_check and not stats_used:
            detection = self.api_manager._infer_skill_check(context)
            needs_check = bool(detection.get("needs_skill_check", False))
            stats_used = detection.get("stats_used") or []
            if isinstance(stats_used, str):
                stats_used = [stats_used]
            stats_used = [str(stat).strip().title() for stat in stats_used if str(stat).strip()][:3]
        dc = detection.get("difficulty_class", 50 if needs_check else 0)
        try:
            dc = int(float(dc))
        except (TypeError, ValueError):
            dc = 50 if needs_check else 0
        dc_evaluation = {}
        if needs_check:
            dc = self._calibrate_skill_dc(player_input, detection, context, dc)
            provisional_detection = {
                "needs_skill_check": needs_check and bool(stats_used),
                "skill": str(detection.get("skill", "")).strip().lower(),
                "stats_used": stats_used,
                "difficulty_class": max(1, min(100, dc)),
                "reason": detection.get("reason", ""),
                "stakes": detection.get("stakes", ""),
            }
            dc_evaluation = self._evaluate_dc(player_input, provisional_detection, context)
            dc = dc_evaluation.get("final_dc", dc)
        return {
            "needs_skill_check": needs_check and bool(stats_used),
            "skill": str(detection.get("skill", "")).strip().lower(),
            "stats_used": stats_used,
            "difficulty_class": max(1, min(100, dc)) if needs_check else 0,
            "reason": detection.get("reason", "No skill check needed" if not needs_check else ""),
            "stakes": detection.get("stakes", ""),
            "dc_evaluation": dc_evaluation,
            "raw_detection": detection,
        }
    def _calibrate_skill_dc(self, player_input: str, detection: Dict[str, Any],
                            context: Dict[str, Any], model_dc: int) -> int:
        """Keep the detector's base DC sane before fact-modifier evaluation."""
        inferred = self.api_manager._infer_skill_check(context)
        inferred_dc = int(inferred.get("difficulty_class") or model_dc)
        if model_dc == 50 and detection.get("parse_error"):
            return inferred_dc
        if model_dc == 50 and inferred.get("needs_skill_check") and inferred_dc != 50:
            return inferred_dc
        return max(1, min(100, int(model_dc)))
    def _resolve_skill_check(self, skill_check: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Run a detected skill check through the generic roll function."""
        if not skill_check.get("needs_skill_check"):
            return None
        result = roll_generic_check(
            entity_id="player",
            stats_used=skill_check["stats_used"],
            skill_used=skill_check.get("skill"),
            difficulty_class=skill_check["difficulty_class"],
        )
        self._load_game_state()
        skill_used = result.get("check_details", {}).get("skill_used") or skill_check.get("skill")
        player = self.game_state.get("player", {})
        post_growth_state = {
            "stats": {
                stat: player.get("stats", {}).get(stat)
                for stat in result.get("check_details", {}).get("stats_used", [])
            },
            "skill": skill_used,
            "skill_value": player.get("skills", {}).get(skill_used) if skill_used else None,
            "derived": {
                key: player.get("derived", {}).get(key)
                for key in ["HP", "HP_max", "MP", "MP_max"]
            },
        }
        return {
            "source": "roll_generic_check",
            "skill": skill_check.get("skill"),
            "stats_used": skill_check.get("stats_used", []),
            "difficulty_class": skill_check.get("difficulty_class"),
            "dc_evaluation": skill_check.get("dc_evaluation", {}),
            "reason": skill_check.get("reason", ""),
            "stakes": skill_check.get("stakes", ""),
            "success": result.get("success", False),
            "margin": result.get("margin", 0),
            "roll": result.get("roll", 0),
            "total_bonus": result.get("total_bonus", 0),
            "growth_added": result.get("growth_added", {}),
            "post_growth_state": post_growth_state,
            "check_details": result.get("check_details", {}),
        }
    def _brief_active_npcs(self, turn_context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Return only recurring save-state NPCs involved in this turn."""
        known = self._get_known_npcs_for_prompt()
        involved = set()
        if isinstance(turn_context, dict):
            involved = {str(npc_id) for npc_id in turn_context.get("involved_npcs", []) or []}
        if involved:
            return [npc for npc in known if str(npc.get("npc_id")) in involved]
        return []
    def _compact_lore_entries(self, lore: Any, max_entries: int = 3) -> List[Dict[str, Any]]:
        """Keep racial/lore brief entries small enough for the large model prompt."""
        compact_lore = []
        if isinstance(lore, dict):
            iterable = lore.values()
        elif isinstance(lore, list):
            iterable = lore
        else:
            iterable = []
        for entry in iterable:
            if not isinstance(entry, dict):
                continue
            compact_entry = {
                "name": self._compact_text(entry.get("name") or entry.get("race") or entry.get("topic"), 80),
                "description": self._compact_text(entry.get("description") or entry.get("details"), 260),
            }
            appearance = entry.get("appearance")
            culture = entry.get("culture") or entry.get("current_status")
            relations = entry.get("relations")
            if appearance:
                compact_entry["appearance"] = self._compact_text(appearance, 180)
            if culture:
                compact_entry["culture"] = self._compact_text(culture, 220)
            if isinstance(relations, dict):
                compact_entry["relations"] = {
                    str(key): self._compact_text(value, 120)
                    for key, value in list(relations.items())[:4]
                }
            compact_lore.append(compact_entry)
            if len(compact_lore) >= max_entries:
                break
        return compact_lore
    def _trusted_mechanical_constraints(self, social_check: Dict[str, Any],
                                        social_result: Optional[Dict[str, Any]],
                                        skill_check: Dict[str, Any],
                                        skill_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Build concise must-obey mechanics from deterministic game results."""
        constraints = {
            "social": {
                "needs_check": bool((social_check or {}).get("needs_social_check")),
                "target_npc": (social_check or {}).get("target_npc"),
                "interaction_type": (social_check or {}).get("interaction_type"),
                "result": {},
            },
            "skill": {
                "needs_check": bool((skill_check or {}).get("needs_skill_check")),
                "skill": (skill_check or {}).get("skill"),
                "stats_used": (skill_check or {}).get("stats_used", []),
                "difficulty_class": (skill_check or {}).get("difficulty_class", 0),
                "dc_evaluation": self._compact_dc_evaluation_for_prompt((skill_check or {}).get("dc_evaluation", {})),
                "reason": self._compact_text((skill_check or {}).get("reason", ""), 180),
                "stakes": self._compact_text((skill_check or {}).get("stakes", ""), 180),
                "result": {},
            },
        }
        social_mechanics = (social_result or {}).get("social_result", {})
        if isinstance(social_mechanics, dict):
            constraints["social"]["result"] = {
                "success": social_mechanics.get("success"),
                "roll": social_mechanics.get("roll"),
                "dc": social_mechanics.get("difficulty_class") or social_mechanics.get("dc"),
                "trust_change": social_mechanics.get("trust_change"),
                "relationship": social_mechanics.get("new_relationship"),
                "mood": social_mechanics.get("emotional_response") or social_mechanics.get("mood"),
            }
        if isinstance(skill_result, dict):
            constraints["skill"]["result"] = {
                "success": skill_result.get("success"),
                "roll": skill_result.get("roll"),
                "margin": skill_result.get("margin"),
                "total_bonus": skill_result.get("total_bonus"),
                "growth_added": skill_result.get("growth_added", {}),
            }
        return constraints
    def _fallback_narrative_brief(self, turn_context: Dict[str, Any],
                                  social_check: Dict[str, Any],
                                  social_result: Optional[Dict[str, Any]],
                                  skill_check: Dict[str, Any],
                                  skill_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Build a compact trusted brief without relying on model prose."""
        return {
            "scene_brief": self._compact_text(self._get_scene_context(), PROMPT_SCENE_BRIEF_CHARS),
            "relevant_lore": self._compact_lore_entries(self._select_racial_profiles(turn_context), max_entries=3),
            "active_npcs": self._brief_active_npcs(turn_context),
            "mechanical_constraints": self._trusted_mechanical_constraints(
                social_check, social_result, skill_check, skill_result
            ),
            "continuity_constraints": [
                self._compact_text(item, 180)
                for item in (turn_context.get("continuity_constraints", []) or [])[:4]
            ],
            "forbidden_assumptions": [
                self._compact_text(item, 180)
                for item in (turn_context.get("forbidden_assumptions", []) or [])[:4]
            ],
        }
    def _sanitize_narrative_brief(self, brief: Any,
                                  turn_context: Dict[str, Any],
                                  social_check: Dict[str, Any],
                                  social_result: Optional[Dict[str, Any]],
                                  skill_check: Dict[str, Any],
                                  skill_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Reject malformed/oversized model briefs and return a compact trusted brief."""
        fallback = self._fallback_narrative_brief(
            turn_context, social_check, social_result, skill_check, skill_result
        )
        if not isinstance(brief, dict):
            return fallback
        raw_narrative = str(brief.get("narrative", "") or "")
        if raw_narrative.strip().startswith(("```", "{")) or len(raw_narrative) > 300:
            return fallback
        if brief.get("parse_error") or brief.get("fallback_after_parse_error"):
            return fallback
        known_ids = {npc.get("npc_id") for npc in self._brief_active_npcs(turn_context)}
        model_active_npcs = [
            npc for npc in brief.get("active_npcs", [])
            if isinstance(npc, dict) and npc.get("npc_id") in known_ids
        ] if isinstance(brief.get("active_npcs"), list) else []
        sanitized = {
            "scene_brief": self._compact_text(
                brief.get("scene_brief") or fallback["scene_brief"],
                PROMPT_SCENE_BRIEF_CHARS,
            ),
            "relevant_lore": self._compact_lore_entries(brief.get("relevant_lore") or fallback["relevant_lore"], max_entries=3),
            "active_npcs": model_active_npcs or fallback["active_npcs"],
            "mechanical_constraints": fallback["mechanical_constraints"],
            "continuity_constraints": [
                self._compact_text(item, 180)
                for item in (brief.get("continuity_constraints") or fallback["continuity_constraints"])[:4]
            ] if isinstance(brief.get("continuity_constraints") or fallback["continuity_constraints"], list) else fallback["continuity_constraints"],
            "forbidden_assumptions": [
                self._compact_text(item, 180)
                for item in (brief.get("forbidden_assumptions") or fallback["forbidden_assumptions"])[:4]
            ] if isinstance(brief.get("forbidden_assumptions") or fallback["forbidden_assumptions"], list) else fallback["forbidden_assumptions"],
        }
        while self.api_manager._estimate_token_count(sanitized) > PROMPT_BRIEF_TOKEN_BUDGET:
            if len(sanitized["relevant_lore"]) > 1:
                sanitized["relevant_lore"] = sanitized["relevant_lore"][:1]
            elif len(sanitized["scene_brief"]) > 360:
                sanitized["scene_brief"] = self._compact_text(sanitized["scene_brief"], 360)
            else:
                break
        return sanitized
    def _build_narrative_brief(self, player_input: str,
                               turn_context: Dict[str, Any],
                               social_check: Dict[str, Any],
                               social_result: Optional[Dict[str, Any]],
                               skill_check: Dict[str, Any],
                               skill_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Use the context model to curate a compact brief for large-model narration."""
        context = self._build_turn_evaluation_context(player_input)
        context.update({
            "turn_context": self._compact_turn_context_for_prompt(turn_context),
            "racial_profiles": self._select_racial_profiles(turn_context),
            "story_bible_excerpt": self._story_bible_excerpt(player_input, turn_context, max_chars=PROMPT_STORY_BIBLE_CHARS),
            "social_check": self._compact_social_check_for_prompt(social_check),
            "social_result": self._compact_social_result_for_prompt(social_result),
            "skill_check": self._compact_skill_check_for_prompt(skill_check),
            "skill_result": self._compact_skill_result_for_prompt(skill_result),
        })
        brief = self.api_manager.call_api(
            "narrative_brief",
            context,
            temperature=MODEL_NARRATIVE_BRIEF_TEMPERATURE,
            max_tokens=MODEL_NARRATIVE_BRIEF_MAX_TOKENS,
        )
        return self._sanitize_narrative_brief(
            brief,
            turn_context,
            social_check,
            social_result,
            skill_check,
            skill_result,
        )
    def _review_npc_actions(self, player_input: str, social_check: Dict[str, Any],
                            social_result: Optional[Dict[str, Any]], 
                            turn_context: Optional[Dict[str, Any]] = None,
                            narrative_brief: Optional[Dict[str, Any]] = None,
                            skill_check: Optional[Dict[str, Any]] = None,
                            skill_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Review NPC actions separately from final DM narration."""
        active_npcs = []
        if isinstance(narrative_brief, dict) and isinstance(narrative_brief.get("active_npcs"), list):
            active_npcs = [npc for npc in narrative_brief["active_npcs"] if isinstance(npc, dict) and npc.get("npc_id")]
        if not active_npcs and not (social_check or {}).get("needs_social_check"):
            return {
                "npc_actions": [],
                "notes": "Skipped NPC review: no recurring active NPCs or social target for this turn.",
            }
        context = self._build_turn_evaluation_context(player_input)
        context.update({
            "turn_context": self._compact_turn_context_for_prompt(turn_context),
            "narrative_brief": narrative_brief or {},
            "story_context": self._build_shared_story_context(player_input, turn_context, narrative_brief),
            "racial_profiles": self._select_racial_profiles(turn_context),
            "story_bible_excerpt": self._story_bible_excerpt(player_input, turn_context, max_chars=PROMPT_RUNTIME_STORY_BIBLE_CHARS),
            "social_check": self._compact_social_check_for_prompt(social_check),
            "social_result": self._compact_social_result_for_prompt(social_result),
            "skill_check": self._compact_skill_check_for_prompt(skill_check),
            "skill_result": self._compact_skill_result_for_prompt(skill_result),
        })
        review = self.api_manager.call_api(
            "npc_action_review",
            context,
            temperature=MODEL_NPC_REVIEW_TEMPERATURE,
            max_tokens=MODEL_NPC_REVIEW_MAX_TOKENS,
        )
        npc_actions = review.get("npc_actions", [])
        if not isinstance(npc_actions, list):
            npc_actions = []
        return {
            "npc_actions": npc_actions,
            "notes": review.get("notes", ""),
        }
    def _summarize_turn(self, player_input: str, narrative: str, command: Dict[str, Any],
                        mechanical_result: Dict[str, Any], social_check: Dict[str, Any],
                        social_result: Optional[Dict[str, Any]],
                        npc_review: Dict[str, Any],
                        skill_check: Optional[Dict[str, Any]] = None,
                        skill_result: Optional[Dict[str, Any]] = None,
                        turn_context: Optional[Dict[str, Any]] = None,
                        narrative_brief: Optional[Dict[str, Any]] = None) -> str:
        """Generate and persist a one-line summary after the DM response."""
        context = {
            "player_input": player_input,
            "dm_narrative": self._compact_text(narrative, 900),
            "command": command,
            "mechanical_result": {
                "success": mechanical_result.get("success") if isinstance(mechanical_result, dict) else None,
                "message": self._compact_text((mechanical_result or {}).get("message", ""), 180) if isinstance(mechanical_result, dict) else "",
            },
            "social_check": self._compact_social_check_for_prompt(social_check),
            "social_result": self._compact_social_result_for_prompt(social_result),
            "npc_review": self._compact_npc_review_for_prompt(npc_review),
            "skill_check": self._compact_skill_check_for_prompt(skill_check),
            "skill_result": self._compact_skill_result_for_prompt(skill_result),
            "scene_result": self._compact_text((narrative_brief or {}).get("scene_brief", ""), 220),
        }
        summary_response = self.api_manager.call_api(
            "turn_summary",
            context,
            temperature=MODEL_TURN_SUMMARY_TEMPERATURE,
            max_tokens=MODEL_TURN_SUMMARY_MAX_TOKENS,
        )
        summary = summary_response.get("summary") or summary_response.get("narrative") or ""
        self.conversation_manager.append_summary_line(summary)
        return " ".join(summary.split()).strip()
    def _format_precomputed_context(self, social_check: Optional[Dict[str, Any]],
                                    social_result: Optional[Dict[str, Any]],
                                    npc_review: Optional[Dict[str, Any]],
                                    skill_check: Optional[Dict[str, Any]] = None,
                                    skill_result: Optional[Dict[str, Any]] = None,
                                    turn_context: Optional[Dict[str, Any]] = None,
                                    narrative_brief: Optional[Dict[str, Any]] = None) -> str:
        """Format only final pre-DM constraints, not agent reasoning."""
        constraints: Dict[str, Any] = {}
        if isinstance(skill_result, dict) and skill_result:
            success = bool(skill_result.get("success"))
            margin = skill_result.get("margin")
            constraints["skill_result"] = {
                "source": skill_result.get("source"),
                "skill": skill_result.get("skill") or (skill_check or {}).get("skill"),
                "difficulty_class": (skill_check or {}).get("difficulty_class") or skill_result.get("difficulty_class"),
                "result": "success" if success else "failure",
                "margin": round(float(margin), 2) if isinstance(margin, (int, float)) else margin,
                "narration_constraint": (
                    "Narrate the declared action as succeeding; keep the margin in mind for degree."
                    if success else
                    "Narrate the declared action as failing; keep the margin in mind for degree."
                ),
            }
        compact_social = self._compact_social_result_for_prompt(social_result)
        if compact_social:
            constraints["social_result"] = {
                key: value
                for key, value in compact_social.items()
                if value not in (None, "", {}, [])
            }
        compact_review = self._compact_npc_review_for_prompt(npc_review)
        if compact_review.get("npc_actions"):
            constraints["npc_actions"] = compact_review["npc_actions"]
        if compact_review.get("notes"):
            constraints["npc_notes"] = compact_review["notes"]
        compact_turn = self._compact_turn_context_for_prompt(turn_context)
        continuity = compact_turn.get("continuity_constraints") or []
        forbidden = compact_turn.get("forbidden_assumptions") or []
        if continuity:
            constraints["continuity_constraints"] = continuity
        if forbidden:
            constraints["forbidden_assumptions"] = forbidden
        return json.dumps(constraints, indent=2)
    def _select_dm_lore_profiles(self, player_input: str,
                                 turn_context: Optional[Dict[str, Any]],
                                 scene_facts: List[str]) -> Dict[str, Any]:
        """Select only lore profiles directly referenced by this turn."""
        profiles = self._load_racial_profiles()
        selected: Dict[str, Any] = {}
        text = self._normalize_key_text(" ".join([player_input, " ".join(scene_facts)]))
        requested = []
        direct_requested = []
        if isinstance(turn_context, dict):
            requested.extend(turn_context.get("relevant_races", []) or [])
            requested.extend(turn_context.get("relevant_lore_keys", []) or [])
        for race in requested:
            key = self._racial_profile_key(race)
            profile = profiles.get(key)
            if not isinstance(profile, dict):
                continue
            profile_name = self._normalize_key_text(profile.get("name", key))
            profile_plural = self._normalize_key_text(profile.get("plural", ""))
            if key in text or profile_name in text or (profile_plural and profile_plural in text):
                direct_requested.append(key)
        for key, profile in profiles.items():
            profile_name = self._normalize_key_text(profile.get("name", key)) if isinstance(profile, dict) else key
            profile_plural = self._normalize_key_text(profile.get("plural", "")) if isinstance(profile, dict) else ""
            if key in text or profile_name in text or (profile_plural and profile_plural in text):
                direct_requested.append(key)
        for race in direct_requested:
            key = self._racial_profile_key(race)
            if key in profiles and key not in selected:
                selected[key] = self._compact_racial_profile({**profiles[key], "name": profiles[key].get("name", key)})
            if len(selected) >= 3:
                break
        return selected
    def _format_player_possessions_for_dm(self) -> str:
        """Return a terse possession constraint for the DM."""
        possessions = self._compact_player_possessions_for_prompt()
        inventory = possessions.get("inventory", {})
        equipment = possessions.get("equipment", {})
        return json.dumps({
            "inventory": inventory,
            "equipment": equipment,
            "gold": possessions.get("gold", 0),
            "rule": "Only narrate carried gear listed here. Do not invent tools, supplies, weapons, food, water, containers, or medical gear. Worn clothing may be damaged only if the player explicitly uses it that way."
        }, indent=2)
    def _build_dm_context(self, player_input: str, social_check: Optional[Dict[str, Any]] = None,
                          social_result: Optional[Dict[str, Any]] = None,
                          npc_review: Optional[Dict[str, Any]] = None,
                          skill_check: Optional[Dict[str, Any]] = None,
                          skill_result: Optional[Dict[str, Any]] = None,
                          turn_context: Optional[Dict[str, Any]] = None,
                          narrative_brief: Optional[Dict[str, Any]] = None) -> str:
        """Build the context for the DM prompt."""
        combat_active = self.combat.state.get("active", False)
        combat_status = 'ACTIVE' if combat_active else 'inactive'
        player_hp = self.game_state.get('player', {}).get('derived', {}).get('HP', '?')
        player_mp = self.game_state.get('player', {}).get('derived', {}).get('MP', '?')
        location = self.game_state.get('world', {}).get('location', {}).get('settlement', 'unknown')
        scene_facts = self._compact_list_text(self.game_state.get("scenario", {}).get("scene_facts", []), 10, 220)
        world_facts = self._compact_list_text(self.game_state.get("world", {}).get("facts", []), 8, 220)
        scene_brief = self._compact_text(
            (narrative_brief or {}).get("scene_brief") or self._get_scene_context(),
            PROMPT_SCENE_CONTEXT_CHARS,
        )
        precomputed_context = self._format_precomputed_context(
            social_check,
            social_result,
            npc_review,
            skill_check,
            skill_result,
            turn_context,
            narrative_brief,
        )
        known_npcs = self._get_known_npcs_for_prompt()
        lore_profiles = self._select_dm_lore_profiles(player_input, turn_context, scene_facts)
        recent_exchanges = self._compact_recent_exchanges(
            PROMPT_DM_RECENT_EXCHANGE_LIMIT,
            max_player_chars=PROMPT_DM_RECENT_PLAYER_CHARS,
            max_dm_chars=PROMPT_DM_RECENT_DM_CHARS,
        )
        summary = self._compact_text(self.conversation_manager.get_summary_file_text(), PROMPT_DM_SUMMARY_CHARS)
        opening_scene = self._opening_scene_context()
        story_bible_excerpt = self._story_bible_excerpt(
            player_input,
            turn_context,
            max_chars=PROMPT_STORY_BIBLE_CHARS,
        )
        player_input_json = json.dumps(player_input)
        sections = []
        sections.append(f"KNOWLEDGE PRIORITY:\n{self._format_knowledge_priority_for_prompt()}")
        if story_bible_excerpt:
            sections.append(f"CANONICAL STORY BIBLE EXCERPT:\n{story_bible_excerpt}")
        if opening_scene:
            sections.append(
                "OPENING SCENE / CAMPAIGN SEED:\n"
                f"{opening_scene.get('title', 'Opening Scene')}\n\n"
                f"{opening_scene.get('text', '')}"
            )
        sections.append(f"SCENE BRIEF:\n{scene_brief or 'No current scene is available.'}")
        if scene_facts:
            sections.append(f"DURABLE SCENE FACTS:\n{json.dumps(scene_facts, indent=2)}")
        if world_facts:
            sections.append(f"DURABLE WORLD FACTS:\n{json.dumps(world_facts, indent=2)}")
        if lore_profiles:
            sections.append(
                "RELEVANT LORE:\n"
                "Use as appearance/culture defaults only. Individual NPC state overrides lore.\n"
                f"{json.dumps(lore_profiles, indent=2)}"
            )
        sections.append(f"PLAYER POSSESSIONS:\n{self._format_player_possessions_for_dm()}")
        situation = [f"Combat: {combat_status}", f"Location: {location}"]
        if combat_active:
            situation.extend([f"Player HP: {player_hp}", f"Player MP: {player_mp}"])
        sections.append("CURRENT SITUATION:\n- " + "\n- ".join(situation))
        if known_npcs:
            sections.append(
                "KNOWN RECURRING NPCS:\n"
                "Use these npc_id values exactly when emitting npc_update commands.\n"
                f"{json.dumps(known_npcs, indent=2)}"
            )
        if summary:
            sections.append(f"CAMPAIGN SUMMARY:\n{summary}")
        if recent_exchanges:
            sections.append(f"RECENT EXCHANGES:\n{json.dumps(recent_exchanges, indent=2)}")
        if precomputed_context != "{}":
            sections.append(
                "PRE-DM CONSTRAINTS:\n"
                "Treat these as hard outcome constraints; do not explain mechanics.\n"
                f"{precomputed_context}"
            )
        context = "\n\n".join(sections) + f"""
PLAYER ACTION: {player_input_json}
PLAYER AGENCY RULES:
- Resolve only what the player explicitly attempts.
- Do not invent player movement, speech, thoughts, feelings, attacks, pickups, searches, rests, departures, returns, or next objectives.
- Plans, intentions, and conditions are context only unless the player explicitly acts on them now.
- If the action reaches a natural stopping point, stop there and leave the next choice unresolved.
- You may narrate time passing, NPC/enemy actions, environmental changes, and observed consequences.
DM NARRATIVE SHAPE:
- Write {DM_NARRATIVE_MIN_PARAGRAPHS} to {DM_NARRATIVE_MAX_PARAGRAPHS} narrative paragraphs before the JSON block.
- Paragraph 1 must restate PLAYER ACTION in polished narrative form, including the player's spoken words or intent when present.
- Paragraph 2, and paragraph 3 only if needed, should show immediate results of that action.
- Present at most {DM_NARRATIVE_RESPONSE_HOOKS} clear player response opportunity, then stop the narrative immediately.
- A response opportunity may be NPC dialogue, a direct question, an accusation, a request, a visible choice point, or a pause that clearly invites the player to respond.
- Do not stack response hooks. After an NPC gives the player something to answer, do not add a second question, warning, threat, new objective, or extra scene beat.
DM STYLE:
{self._dm_prose_style_rules()}
NPC MEMORY RULES:
- npc_update.known_facts must be concise current facts, not full narration.
- Keep each NPC fact under one short sentence and avoid "you/your" phrasing.
- Prefer current status, location, injuries, restraints, special marks, behavior, identity, or relationship changes.
RESPOND WITH:
1. Narrative description of what happens.
2. At the very end, exactly one JSON command block with mechanical actions and durable state updates.
Use a single command for one change, or multi for several:
```json
{{
  "action": "multi",
  "commands": [
    {{"action": "scene_update", "command": {{"current_scene": "What is physically true now.", "facts": ["Durable scene fact."]}}}},
    {{"action": "npc_update", "command": {{"npc_id": "existing_or_new_npc_id", "updates": {{"mood": "afraid", "status": "freed", "known_facts": ["Durable NPC fact."]}}}}}},
    {{"action": "note_fact", "command": {{"fact": "A durable world or story fact the game must remember."}}}}
  ]
}}
```
Available command actions: narrative, scene_update, location_update, npc_update, note_fact, inventory, quest, spell_create, spell_study, spell_cast, combat_start, combat_action, combat_end, skill_check.
If your narrative names, describes, injures, moves, or changes an NPC, include an npc_update for that NPC in the JSON. If a name is revealed, include that newly revealed name in updates.name. Do not use race-only ids like npc_nekko as permanent NPC ids; use an existing npc_id, a descriptive unnamed id, or the named id once learned.
Do not emit social_interaction for the current player action. Use skill_check only for additional checks that were not already precomputed.
ONLY output the narrative + one JSON block. No extra text."""
        
        return context
    def _command_payload(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Return the nested command payload when present."""
        payload = command.get("command", {})
        return payload if isinstance(payload, dict) else {}
    def _apply_scene_update(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Persist current-scene text and durable scene facts."""
        payload = self._command_payload(command)
        scenario = self.game_state.setdefault("scenario", {})
        current_scene = payload.get("current_scene") or payload.get("scene") or payload.get("description")
        if current_scene:
            scenario["current_scene"] = str(current_scene)
        facts = payload.get("facts") or payload.get("scene_facts") or []
        if isinstance(facts, str):
            facts = [facts]
        if facts:
            existing = scenario.setdefault("scene_facts", [])
            for fact in facts:
                clean_fact = " ".join(str(fact).split()).strip()
                if clean_fact and clean_fact not in existing:
                    existing.append(clean_fact)
        return {
            "success": True,
            "message": "Scene updated",
            "current_scene": scenario.get("current_scene", ""),
            "facts_added": len(facts) if isinstance(facts, list) else 0
        }
    def _apply_location_update(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Persist the player's current location."""
        payload = self._command_payload(command)
        location = payload.get("location", payload)
        if not isinstance(location, dict):
            return {"success": False, "message": "location_update requires a location object"}
        self.game_state.setdefault("world", {}).setdefault("location", {}).update(location)
        return {"success": True, "message": "Location updated", "location": self.game_state["world"]["location"]}
    def _apply_note_fact(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Persist a durable world or story fact."""
        payload = self._command_payload(command)
        fact = payload.get("fact") or payload.get("note")
        if not fact:
            return {"success": False, "message": "note_fact requires fact"}
        clean_fact = " ".join(str(fact).split()).strip()
        facts = self.game_state.setdefault("world", {}).setdefault("facts", [])
        if clean_fact not in facts:
            facts.append(clean_fact)
        return {"success": True, "message": "Fact noted", "fact": clean_fact}
    def _apply_npc_update(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Persist NPC updates in the active save state."""
        payload = self._command_payload(command)
        npc_id = payload.get("npc_id") or payload.get("target_npc")
        updates = payload.get("updates", {})
        if not npc_id or not isinstance(updates, dict):
            return {"success": False, "message": "npc_update requires npc_id and updates"}
        player = self.game_state.get("player", {})
        player_identity = player.get("identity") if isinstance(player, dict) and isinstance(player.get("identity"), dict) else {}
        player_name = self._normalize_key_text(player_identity.get("name") or (player.get("name") if isinstance(player, dict) else ""))
        updated_name = self._normalize_key_text(updates.get("name", ""))
        if player_name and (
            self._normalize_key_text(npc_id) == self._normalize_key_text(self._make_npc_id_from_name(player_name))
            or self._normalize_key_text(npc_id) == player_name
            or updated_name == player_name
        ):
            return {"success": False, "message": "Refusing to create or update the player as an NPC"}
        npcs = self.game_state.setdefault("npcs", {})
        original_npc_ref = npc_id
        npc_id = (
            self._resolve_npc_reference(npc_id)
            or self._ensure_npc_for_interaction(npc_id, updates=updates)
            or npc_id
        )
        npcs = self.game_state.setdefault("npcs", {})
        if npc_id not in npcs:
            npc_lookup = get_npc(npc_id)
            inferred = self._infer_race_gender_from_reference(original_npc_ref, json.dumps(updates, ensure_ascii=False))
            source = npc_lookup.get("npc", {"npc_id": npc_id}) if npc_lookup.get("success") else {"npc_id": npc_id}
            aliases = source.get("aliases") if isinstance(source.get("aliases"), list) else []
            aliases.append(str(original_npc_ref))
            source["aliases"] = aliases
            if inferred.get("race"):
                source.setdefault("race", inferred["race"])
            if inferred.get("gender"):
                source.setdefault("gender", inferred["gender"])
            npcs[npc_id] = self._make_template_npc(npc_id, source)
        for field, value in updates.items():
            self._set_npc_field(npcs[npc_id], field, value)
        if any(field in updates for field in ("race", "gender")):
            self._initialize_npc_baseline_stats(npcs[npc_id], force=True)
        if "name" in updates:
            self._normalize_npc_records()
            npc_id = self._resolve_npc_reference(updates["name"]) or npc_id
            self.game_state.setdefault("npc_aliases", {})[str(original_npc_ref)] = npc_id
        else:
            self._normalize_npc_records()
        return {"success": True, "message": f"Updated NPC {npc_id}", "updated_fields": list(updates.keys())}
    def _reload_game_state_after_external_update(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Refresh self.game_state after tools that mutate the save file directly."""
        if result.get("success"):
            self._load_game_state()
        return result
    def _execute_command(self, command: Dict) -> Dict:
        """Execute one or more commands from the DM response."""
        if not isinstance(command, dict):
            return {"success": False, "message": "Command must be a JSON object", "results": []}
        commands = command.get("commands")
        if command.get("action", "").lower() in {"multi", "state_update"}:
            commands = command.get("commands", [])
        if commands is not None:
            if not isinstance(commands, list):
                return {"success": False, "message": "commands must be a list", "results": []}
            results = [self._execute_single_command(item) for item in commands]
            return {
                "success": all(result.get("success", False) for result in results),
                "message": f"Executed {len(results)} command(s)",
                "results": results
            }
        return self._execute_single_command(command)

    def _iter_command_entries(self, command: Any) -> List[Dict[str, Any]]:
        """Flatten a DM command or multi-command into individual command objects."""
        if not isinstance(command, dict):
            return []
        if command.get("commands") is not None or command.get("action", "").lower() in {"multi", "state_update"}:
            entries = []
            for item in command.get("commands", []) if isinstance(command.get("commands"), list) else []:
                entries.extend(self._iter_command_entries(item))
            return entries
        return [command]

    def _npc_refs_from_completed_turn(self, command: Dict[str, Any],
                                      social_check: Optional[Dict[str, Any]],
                                      social_result: Optional[Dict[str, Any]],
                                      npc_review: Optional[Dict[str, Any]]) -> List[str]:
        refs: List[str] = []
        for item in self._iter_command_entries(command):
            action = item.get("action", "").lower()
            payload = self._command_payload(item)
            if action in {"npc_update", "npc_state", "social_interaction"}:
                refs.extend([
                    payload.get("npc_id"),
                    payload.get("target_npc"),
                    payload.get("updates", {}).get("name") if isinstance(payload.get("updates"), dict) else None,
                ])
        if isinstance(social_check, dict):
            refs.extend([social_check.get("target_npc"), social_check.get("npc_id")])
        if isinstance(social_result, dict):
            refs.append(social_result.get("npc_id"))
            reaction = social_result.get("npc_reaction") if isinstance(social_result.get("npc_reaction"), dict) else {}
            refs.append(reaction.get("npc_id"))
        if isinstance(npc_review, dict):
            for action in npc_review.get("npc_actions", []) if isinstance(npc_review.get("npc_actions"), list) else []:
                if isinstance(action, dict):
                    refs.extend([action.get("npc_id"), action.get("name")])
        return [str(ref) for ref in refs if ref]

    def _reconcile_npcs_after_narration(self, player_input: str, narrative: str,
                                        command: Dict[str, Any],
                                        social_check: Optional[Dict[str, Any]] = None,
                                        social_result: Optional[Dict[str, Any]] = None,
                                        npc_review: Optional[Dict[str, Any]] = None):
        """Normalize NPC records after command updates without mining DM prose."""
        self._normalize_npc_records()

    def _execute_single_command(self, command: Dict) -> Dict:
        """Execute a single validated command from the DM response."""
        if not isinstance(command, dict):
            return {"success": False, "message": "Command entry must be an object"}
        action = command.get("action", "").lower()
        if action in {"", "none", "noop", "narrative", "error"}:
            return {
                "success": action != "error",
                "message": command.get("message") or command.get("command", {}).get("message", "No mechanical action requested")
            }
        if action == "scene_update":
            return self._apply_scene_update(command)
        if action == "location_update":
            return self._apply_location_update(command)
        if action == "note_fact":
            return self._apply_note_fact(command)
        if action in {"npc_update", "npc_state"}:
            return self._apply_npc_update(command)
        if action == "skill_check":
            payload = self._command_payload(command)
            stats_used = payload.get("stats_used") or []
            if isinstance(stats_used, str):
                stats_used = [stats_used]
            try:
                difficulty_class = int(float(payload.get("difficulty_class", 50)))
            except (TypeError, ValueError):
                difficulty_class = 50
            result = roll_generic_check(
                entity_id=payload.get("entity_id", "player"),
                stats_used=[str(stat).strip().title() for stat in stats_used if str(stat).strip()][:3],
                skill_used=payload.get("skill"),
                situational_bonus=float(payload.get("situational_bonus", 0) or 0),
                difficulty_class=max(10, min(100, difficulty_class)),
            )
            self._load_game_state()
            return result
        if action == "combat_start":
            return self.combat.start_combat(self._command_payload(command).get("participants", []))
        if action == "combat_end":
            return self.combat.end_combat()
        if action == "spell_create":
            spell_command = self._command_payload(command)
            return self._reload_game_state_after_external_update(create_spell(**spell_command))
        if action in {"spell_study", "spell_research", "spell_learn"}:
            spell_command = self._command_payload(command)
            return self._reload_game_state_after_external_update(study_spell(spell_command.get("spell_key")))
        if action == "spell_cast":
            spell_command = self._command_payload(command)
            return self.combat.execute_combat_command({
                "action": "spell",
                "caster": spell_command.get("caster", "player"),
                "spell_key": spell_command.get("spell_key"),
                "target": spell_command.get("target"),
                "target_pos": spell_command.get("target_pos"),
                "charge_percent": spell_command.get("charge_percent", 100.0),
            })
        if action in {"combat_action", "combat"}:
            return self.combat.execute_combat_command(command["command"])
        elif action == "social_interaction":
            social_command = command.get("command", {})
            target_npc = social_command.get("target_npc") or social_command.get("npc_id")
            if not target_npc:
                return {"success": False, "message": "Social interaction missing target_npc/npc_id"}
            target_npc = self._resolve_npc_reference(target_npc) or target_npc
            return self.process_social_interaction(
                player_input=social_command.get("player_input") or social_command.get("player_action") or "",
                target_npc=target_npc,
                interaction_type=social_command.get("interaction_type", "appeal")
            )
        elif action == "inventory":
            inventory_command = command.get("command", {})
            inventory_action = inventory_command.get("action", "").lower()
            if inventory_action == "add":
                self._save_game_state()
                return self._reload_game_state_after_external_update(add_item_to_inventory(
                    item_data=inventory_command.get("item_data", {}),
                    entity_id=inventory_command.get("entity_id", "player"),
                    quantity=inventory_command.get("quantity", 1),
                    condition=inventory_command.get("condition", "pristine")
                ))
            return {"success": True, "message": "Inventory action acknowledged"}
        elif action == "quest":
            quest_command = command.get("command", {})
            if quest_command.get("action") == "add":
                self._save_game_state()
                return self._reload_game_state_after_external_update(add_quest_to_journal(quest_command.get("quest_data")))
            elif quest_command.get("action") == "update":
                self._save_game_state()
                return self._reload_game_state_after_external_update(update_quest_progress(quest_command.get("quest_id"), quest_command.get("objective")))
            elif quest_command.get("action") == "complete":
                self._save_game_state()
                return self._reload_game_state_after_external_update(complete_quest(quest_command.get("quest_id")))
        elif action == "npc":
            npc_command = command.get("command", {})
            if npc_command.get("action") == "get":
                return get_npc(npc_command.get("npc_id"))
            elif npc_command.get("action") == "update":
                return self._apply_npc_update({
                    "action": "npc_update",
                    "command": {
                        "npc_id": npc_command.get("npc_id"),
                        "updates": npc_command.get("updates", {})
                    }
                })
        else:
            return {"success": False, "message": f"Unknown action: {action}"}
    def process_player_action(self, player_input: str) -> Dict:
        """Process a player action and return the result."""
        self._load_game_state()  # Refresh game state
        # 1. Build the full turn pipeline: small context, Python mechanics, large NPC/DM narration.
        turn_context = self._evaluate_turn_context(player_input)
        social_check = self._detect_social_check(player_input, turn_context)
        social_result = None
        if social_check.get("needs_social_check"):
            social_target = self._ensure_npc_for_interaction(
                social_check.get("target_npc"),
                player_input=player_input,
            )
            if social_target:
                social_check["target_npc"] = social_target
            social_result = self.process_social_interaction(
                player_input=player_input,
                target_npc=social_check["target_npc"],
                interaction_type=social_check.get("interaction_type", "appeal"),
                turn_context=turn_context,
            )
        skill_check = self._detect_skill_check(player_input, turn_context)
        skill_result = self._resolve_skill_check(skill_check)
        narrative_brief = self._build_narrative_brief(
            player_input,
            turn_context,
            social_check,
            social_result,
            skill_check,
            skill_result,
        )
        npc_review = self._review_npc_actions(
            player_input,
            social_check,
            social_result,
            turn_context,
            narrative_brief,
            skill_check,
            skill_result,
        )
        prompt = self._build_dm_context(
            player_input,
            social_check,
            social_result,
            npc_review,
            skill_check,
            skill_result,
            turn_context,
            narrative_brief,
        )
        self._write_dm_prompt_debug(
            player_input,
            prompt,
            social_check,
            social_result,
            npc_review,
            skill_check,
            skill_result,
            turn_context,
            narrative_brief,
        )
        
        # 2. Call the Mistral API
        llm_text = self._call_mistral_api(prompt)
        # 3. Extract the JSON command
        import re
        narrative = re.split(r'```(?:json)?', llm_text, maxsplit=1)[0].strip()
        if not narrative:
            narrative = "The moment resolves, but the DM response did not include narrative text."
        json_match = re.search(r'```(?:json)?\s*(.+?)\s*```', llm_text, re.DOTALL)
        if json_match:
            try:
                command = json.loads(json_match.group(1))
            except json.JSONDecodeError as e:
                command = {"action": "error", "message": f"Invalid JSON command: {e}"}
        else:
            command = {"action": "error", "message": "No JSON command found"}
        # 4. Execute the command
        try:
            result = self._execute_command(command)
        except Exception as e:
            logger.exception("Failed to execute DM command")
            result = {
                "success": False,
                "message": f"Command execution failed after DM response: {type(e).__name__}: {e}"
            }
        self._reconcile_npcs_after_narration(
            player_input=player_input,
            narrative=narrative,
            command=command,
            social_check=social_check,
            social_result=social_result,
            npc_review=npc_review,
        )
        # 5. Update conversation history
        self.conversation_manager.add_interaction(player_input, narrative)
        self.conversation_manager.append_story_exchange(player_input, narrative, command)
        try:
            turn_summary = self._summarize_turn(
                player_input=player_input,
                narrative=narrative,
                command=command,
                mechanical_result=result,
                social_check=social_check,
                social_result=social_result,
                npc_review=npc_review,
                skill_check=skill_check,
                skill_result=skill_result,
                turn_context=turn_context,
                narrative_brief=narrative_brief,
            )
        except Exception as e:
            logger.exception("Failed to summarize completed turn")
            turn_summary = f"Summary failed after turn completion: {type(e).__name__}: {e}"
        # 6. Save game state
        try:
            self._save_game_state()
        except Exception as e:
            logger.exception("Failed to save game state after completed turn")
            result = {
                "success": False,
                "message": f"{result.get('message', '')} Save failed: {type(e).__name__}: {e}".strip()
            }
        # 7. Return the result
        return {
            "narrative": narrative,
            "command_executed": command,
            "mechanical_result": result,
            "social_check": social_check,
            "social_result": social_result,
            "npc_review": npc_review,
            "turn_context": turn_context,
            "narrative_brief": narrative_brief,
            "skill_check": skill_check,
            "skill_result": skill_result,
            "turn_summary": turn_summary,
            "token_usage": self.api_manager.get_token_usage(),
            "updated_combat_state": self.combat.state if self.combat.state.get("active") else None,
            "map": get_current_map(self.combat.state) if self.combat.state.get("active") else None
        }
    def get_game_start_options(self) -> Dict:
        """Get available game start options - ALWAYS shows new game option first."""
        return {
            "has_existing_game": self.game_state_exists,
            "message": "Welcome to Isekai RPG! What would you like to do?",
            "options": [
                {
                    "id": "new_game",
                    "title": "🆕 Start New Game",
                    "description": "Create a new character and begin a fresh adventure",
                    "available": True,
                    "priority": 1,
                    "recommended": True
                },
                {
                    "id": "continue",
                    "title": "📁 Continue Existing Game",
                    "description": "Load your previous game and continue where you left off",
                    "available": self.game_state_exists,
                    "priority": 2
                }
            ]
        }
    def start_new_game(self, character_data: Dict) -> Dict:
        """Start a new game with the given character."""
        character_name = (
            character_data.get("name")
            or character_data.get("character", {}).get("identity", {}).get("name")
            or "Unknown"
        )
        print("🎮 Starting new game with character:", character_name)
        
        # Create character using the character creator
        if isinstance(character_data.get("character"), dict):
            creation_result = {
                "success": True,
                "character": character_data["character"],
                "message": "Character supplied by guided creation."
            }
        else:
            creation_result = self.character_creator.create_character(
                name=character_data["name"],
                gender=character_data["gender"],
                race=character_data["race"],
                background=character_data["background"],
                class_theme=character_data["class_theme"],
                stat_allocations=character_data["stat_allocations"],
                skill_bonuses=character_data.get("skill_bonuses"),
                known_facts=character_data.get("known_facts"),
                age=character_data.get("age"),
        )
        if not creation_result["success"]:
            return {
                "success": False,
                "error": creation_result["error"],
                "field": creation_result.get("field", "unknown")
            }
        # Initialize new game state
        opening_scene = get_opening_scene_text()
        opening_scene_facts = get_opening_scene_facts()
        opening_world = get_opening_world_state()
        starting_location = opening_world.get("location") if isinstance(opening_world.get("location"), dict) else {}
        starting_time = opening_world.get("time") if isinstance(opening_world.get("time"), dict) else {}
        self.game_state = {
            "schema_version": 1,
            "player": creation_result["character"],
            "npcs": {},
            "quests": {},
            "scenario": {
                "opening_scene": {
                    "title": get_opening_scene_title(),
                    "text": opening_scene,
                    "status": get_opening_scene_status(),
                    "created_at": datetime.now().isoformat()
                },
                "current_scene": opening_scene,
                "current_scene_source": get_opening_scene_source(),
                "scene_facts": opening_scene_facts
            },
            "world": {
                "location": {
                    "settlement": "Caravan Road Ambush",
                    "region": "Forested River Road",
                    "coordinates": [0, 0]
                } | starting_location,
                "time": {
                    "day": 1,
                    "hour": 8,
                    "season": "spring"
                } | starting_time
            },
            "game": {
                "start_date": datetime.now().isoformat(),
                "playtime": 0,
                "difficulty": "normal"
            }
        }
        # Save the new game state
        self._save_game_state()
        self.combat.end_combat()
        self.game_state_exists = True
        
        # Reset conversation history
        self.conversation_manager = ConversationManager(load_transcript=False)
        self.conversation_manager.summary = get_opening_campaign_summary()
        try:
            path_config.logs_dir.mkdir(parents=True, exist_ok=True)
            self.conversation_manager.summary_file_path.write_text(
                self.conversation_manager.summary + "\n",
                encoding="utf-8",
            )
            self.conversation_manager.seed_opening_scene(
                get_opening_scene_title(),
                opening_scene,
                opening_scene_facts,
                get_opening_scene_source(),
            )
        except Exception as e:
            logger.error(f"Failed to reset conversation files for new game: {e}")
        location = self.game_state.get("world", {}).get("location", {})
        starting_location = ", ".join(
            str(location.get(key))
            for key in ("settlement", "region")
            if location.get(key)
        )
        print("✅ New game started successfully!")
        return {
            "success": True,
            "message": "New game started successfully! Welcome to your adventure.",
            "character": creation_result["character"],
            "starting_location": starting_location,
            "opening_scene": opening_scene
        }
    def continue_existing_game(self) -> Dict:
        """Continue an existing game."""
        if not self.game_state_exists:
            return {
                "success": False,
                "error": "No existing game found to continue"
            }
        self._load_game_state()
        self.conversation_manager.rehydrate_from_story_transcript()
        print("📁 Continuing existing game")
        return {
            "success": True,
            "message": f"Welcome back! Continuing your adventure from {self.game_state['world']['location']['settlement']}.",
            "game_state": self.game_state,
            "resume_context": self.get_resume_context()
        }
    def get_character_creation_info(self) -> Dict:
        """Get information needed for character creation."""
        return {
            "available_races": self.character_creator.get_available_races(),
            "stat_allocation_rules": self.character_creator.get_stat_allocation_rules(),
            "race_info": {race: self.character_creator.get_race_info(race) 
                          for race in self.character_creator.get_available_races()},
            "suggested_backgrounds": self.character_creator.backgrounds
        }
    def get_base_stats_for_character(self, race: str, gender: str) -> Optional[Dict]:
        """Get base stats for a race/gender combination."""
        return self.character_creator.get_base_stats_for_race_gender(race, gender)
    def get_suggested_backgrounds(self, race: str) -> List[str]:
        """Get suggested backgrounds for a race."""
        return self.character_creator.get_suggested_backgrounds(race)
    def _calculate_social_difficulty(self, player_input: str, target_npc: str) -> int:
        """Determine an interaction DC from phrasing and current NPC relationship."""
        difficulty = 50
        lowered = player_input.lower()
        npc_data = self.social_calculator._load_npc_data(target_npc) or {}
        known_text = " ".join(str(fact) for fact in self._get_npc_field(npc_data, "known_facts", []) or [])
        interaction_context = " ".join([
            str(self._get_npc_field(npc_data, "mood", "")),
            known_text,
        ]).lower()
        if any(word in lowered for word in ["thank", "reassure", "comfort", "apologize", "it's okay", "safe"]):
            difficulty = 25
        if any(word in lowered for word in ["ask", "tell", "please", "help", "travel together", "come with me"]):
            difficulty = min(difficulty, 35)
        if any(word in lowered for word in ["let me travel", "join me", "recruit", "together with you"]):
            difficulty = 45
        if any(word in lowered for word in ["demand", "order", "command", "threaten"]):
            difficulty = max(difficulty, 65)
        if any(word in lowered for word in ["gift", "offer", "help", "please"]):
            difficulty -= 10
        if any(word in interaction_context for word in ["freed", "chains_removed", "grateful", "cautiously relieved"]):
            difficulty -= 10
        if any(word in interaction_context for word in ["distrust", "hostile", "threat", "dagger"]):
            difficulty += 5
        relationship = self._get_npc_field(npc_data, "relationship", "neutral")
        difficulty += {
            "mortal enemy": 25,
            "enemy": 15,
            "adversary": 10,
            "rival": 5,
            "neutral": 0,
            "acquaintance": -5,
            "friend": -10,
            "close friend": -15,
            "lover": -20,
            "soulmate": -25,
        }.get(relationship, 0)
        return int(max(10, min(100, difficulty)))
    def _log_social_interaction(self, npc_id: str, player_action: str, result: Dict):
        """Append a compact social interaction audit log."""
        try:
            log_path = path_config.logs_dir / "social_interactions.json"
            logs = []
            if log_path.exists():
                with open(log_path, "r", encoding="utf-8") as f:
                    logs = json.load(f)
            logs.append({
                "timestamp": datetime.now().isoformat(),
                "npc_id": npc_id,
                "player_action": player_action,
                "success": result.get("social_result", {}).get("success", False),
                "trust_change": result.get("social_result", {}).get("trust_change", 0),
                "relationship": result.get("social_result", {}).get("new_relationship", "neutral"),
            })
            with open(log_path, "w", encoding="utf-8") as f:
                json.dump(logs[-100:], f, indent=2)
        except Exception as e:
            logger.error(f"Failed to log social interaction: {e}")
    def get_game_state(self) -> Dict:
        """Get the current game state."""
        return self.game_state
    def get_resume_context(self) -> Dict[str, Any]:
        """Return non-persistent UI context for resuming an interrupted game."""
        last_exchange = self.conversation_manager.get_last_exchange()
        last_dm = str(last_exchange.get("dm") or "").strip()
        last_player = str(last_exchange.get("player") or "").strip()
        return {
            "has_last_turn": bool(last_dm),
            "last_player_input": last_player,
            "last_dm_narrative": last_dm,
            "source": STORY_FILE_NAME if last_dm else "",
        }
    def get_token_usage(self) -> Dict:
        """Get current session token usage."""
        return self.api_manager.get_token_usage()
    def process_social_interaction(self, player_input: str, target_npc: str,
                              interaction_type: str = "appeal",
                              turn_context: Optional[Dict[str, Any]] = None,
                              narrative_brief: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Process a social interaction with enhanced system"""
        try:
            # Determine difficulty based on context
            target_npc = self._resolve_npc_reference(target_npc) or target_npc
            difficulty = self._calculate_social_difficulty(player_input, target_npc)
            story_context = self._build_shared_story_context(player_input, turn_context, narrative_brief)
            # Use enhanced social calculator
            result = self.social_calculator.resolve_social_interaction(
                target_npc,
                interaction_type,
                player_input,
                difficulty,
                story_context=story_context,
            )
            # Log the interaction
            self._log_social_interaction(target_npc, player_input, result)
            return result
        except Exception as e:
            logger.error(f"Social interaction processing failed: {str(e)}")
            return {
                "narrative": "An error occurred processing the social interaction.",
                "social_result": {"success": False, "trust_change": 0},
                "npc_reaction": {"dialogue": "..."}
            }
    def get_combat_state(self) -> Dict:
        """Get the current combat state."""
        return self.combat.state
    def get_combat_map(self) -> Dict:
        """Get the current combat map."""
        return get_current_map(self.combat.state) if self.combat.state.get("active") else {"map_grid": "No active map", "legend": "No legend"}
    def get_npcs(self) -> List[Dict]:
        """Get all NPCs."""
        return list(self.game_state.get("npcs", {}).values())
    def get_quests(self) -> List[Dict]:
        """Get all quests."""
        quests = self.game_state.get("quests", {})
        if isinstance(quests, dict):
            flattened = []
            for value in quests.values():
                if isinstance(value, list):
                    flattened.extend(value)
                elif isinstance(value, dict):
                    flattened.append(value)
            return flattened
        if isinstance(quests, list):
            return quests
        return []
# Main entry point
if __name__ == "__main__":
    print("🚀 Starting Isekai RPG Game Engine...")
    engine = GameEngine()
    # Keep the main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        # This should be handled by the signal handler, but just in case
        print("\n🛑 Shutting down...")
        sys.exit(0)
