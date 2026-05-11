# game_engine_complete.py
import sys
import json
import copy
import os
import re
import random
import logging
import difflib
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
from inventory_tools import (
    add_currency_to_wallet,
    add_item_to_inventory,
    currency_snapshot,
    normalize_inventory_collection,
    normalize_player_currency,
)
from social_calc import resolve_social_interaction
from crafting import craft_item, study_spell, create_spell, add_found_or_purchased_item
from helper_functions import (
    calculate_scaled_hp_mp_max,
    roll_generic_check,
    load_trust_reference,
    get_relationship_level,
    get_relationship_data,
    get_mood_band,
    get_mood_label,
    get_mood_score,
)
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
DEFAULT_UNEVALUATED_DC = game_config.int("mechanics.default_unevaluated_dc", 45, min_value=1, max_value=100)
NPC_MOOD_DECAY_PER_HOUR = game_config.float("mechanics.mood_decay_per_hour", 1.0, min_value=0.0)
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
PROMPT_TRANSCRIPT_RETRIEVAL_MAX_SNIPPETS = game_config.int("prompt_context.transcript_retrieval_max_snippets", 3, min_value=0)
PROMPT_TRANSCRIPT_RETRIEVAL_MAX_CHARS = game_config.int("prompt_context.transcript_retrieval_max_chars", 260, min_value=80)
PROMPT_TRANSCRIPT_RETRIEVAL_MAX_TURNS = game_config.int("prompt_context.transcript_retrieval_max_turns", 80, min_value=1)
PROMPT_TRANSCRIPT_RETRIEVAL_TERM_LIMIT = game_config.int("prompt_context.transcript_retrieval_term_limit", 12, min_value=1)
TURN_MEMORY_UPDATE_MAX_FACTS = game_config.int("npc_memory.turn_memory_update_max_facts", 6, min_value=1)
SCENE_FACT_MAX_PER_SCOPE = game_config.int("scene_memory.max_facts_per_scope", 12, min_value=1)
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
MODEL_TURN_SUMMARY_MAX_TOKENS = game_config.int("model_calls.turn_summary_max_tokens", 650, min_value=1)
MODEL_OOC_QUESTION_TEMPERATURE = game_config.float("model_calls.ooc_question_temperature", 0.2, min_value=0.0, max_value=2.0)
MODEL_OOC_QUESTION_MAX_TOKENS = game_config.int("model_calls.ooc_question_max_tokens", 500, min_value=1)
DM_NARRATIVE_MIN_PARAGRAPHS = game_config.int("dm_narration.min_paragraphs", 2, min_value=1)
DM_NARRATIVE_MAX_PARAGRAPHS = game_config.int("dm_narration.max_paragraphs", 3, min_value=DM_NARRATIVE_MIN_PARAGRAPHS)
DM_NARRATIVE_RESPONSE_HOOKS = game_config.int("dm_narration.response_hook_count", 1, min_value=1)
DM_PROSE_HEAT = game_config.int("dm_narration.prose_heat", 1, min_value=0, max_value=5)
TIME_DEFAULT_TURN_MINUTES = game_config.int("time.default_turn_minutes", 1, min_value=0)
TIME_MAX_DM_ADVANCE_MINUTES = game_config.int("time.max_dm_advance_minutes", 1440, min_value=1)
API_DM_TIMEOUT_SECONDS = game_config.float("api.dm_timeout_seconds", 40, min_value=1)
WEB_DEFAULT_PORT = game_config.int("web.default_port", 5000, min_value=1, max_value=65535)
WEB_ENGINE_STARTUP_WAIT_SECONDS = game_config.float("web.engine_startup_wait_seconds", 3, min_value=0.0)
KNOWLEDGE_PRIORITY_RULES = [
    "Story Bible is canonical truth.",
    "Saved game_state facts are secondary and must not override the Story Bible.",
    "Recent summary, transcript, generated briefs, and model inference are continuity aids only after the first two.",
    "When sources conflict, follow the highest-priority source and avoid inventing a reconciliation.",
]
PLAYER_RELATIONSHIP_TYPE_EXAMPLES = [
    "stranger",
    "rescuer",
    "rescued",
    "traveling companion",
    "former traveling companion",
    "friend",
    "close friend",
    "lover",
    "former lover",
    "wife",
    "former wife",
    "husband",
    "former husband",
    "spouse",
    "former spouse",
    "servant",
    "slave",
    "master",
    "employer",
    "employee",
    "mentor",
    "student",
    "rival",
    "enemy",
    "dependent",
    "protector",
    "ward",
    "family",
]
STORY_BIBLE_TOPIC_TRIGGERS = {
    "slavery": [
        "slave",
        "slavery",
        "slaver",
        "enslaved",
        "owner",
        "master",
        "property",
        "command",
        "order",
        "tattoo",
        "slave mark",
        "red tattoo",
        "blue tattoo",
        "neck mark",
        "binding spell",
        "chain",
        "chains",
        "escape",
        "escaped",
        "fugitive",
    ],
    "general_considerations": [
        "settlement",
        "settlements",
        "village",
        "hamlet",
        "town",
        "city",
        "travel",
        "road",
        "distance",
        "market",
        "bargain",
        "bargaining",
        "protection",
    ],
    "general_considerations.settlements": [
        "settlement",
        "settlements",
        "village",
        "hamlet",
        "town",
        "city",
        "travel",
        "road",
        "distance",
    ],
}
NPC_FACT_REPLACE_CATEGORIES = {
    "status",
    "location",
    "injuries",
    "treatment",
    "restraints",
    "mark",
    "behavior",
    "relationship",
    "party",
    "identity",
}
NPC_PROFILE_RANDOM = random.SystemRandom()
NPC_NAME_POOLS = {
    "nekko": {
        "female": ["Airi", "Mireya", "Sena", "Kaori", "Nyara", "Tavira", "Rikka", "Meira"],
        "male": ["Taro", "Kiren", "Naru", "Riven", "Sato", "Maeko", "Joren", "Tavi"],
        "": ["Ari", "Niko", "Rin", "Kavi", "Sera", "Mako", "Tarin", "Nyx"],
    },
    "beastfolk": {
        "female": ["Arva", "Mara", "Tessa", "Veyra", "Kessa", "Runa", "Sable", "Ivara"],
        "male": ["Bren", "Kellan", "Tor", "Varric", "Dain", "Hale", "Rusk", "Orin"],
        "": ["Ash", "Bryn", "Ren", "Vale", "Kerr", "Senn", "Tarn", "Rook"],
    },
    "elf": {
        "female": ["Caelyra", "Mirel", "Vaena", "Saelin", "Ilyra", "Thalia", "Evara", "Nimel"],
        "male": ["Cael", "Vaeron", "Theren", "Ilan", "Saeris", "Erynd", "Maelor", "Lior"],
        "": ["Ael", "Vael", "Sae", "Lior", "Eryn", "Miren", "Thael", "Caer"],
    },
    "dwarf": {
        "female": ["Branna", "Dagna", "Kelda", "Maren", "Torra", "Hilda", "Ragna", "Ysold"],
        "male": ["Borin", "Dain", "Korr", "Thane", "Rurik", "Hald", "Orrek", "Torvik"],
        "": ["Korrin", "Dagna", "Marn", "Rurik", "Thane", "Kelda", "Borin", "Torra"],
    },
    "human": {
        "female": ["Mara", "Elian", "Tessa", "Rowen", "Anya", "Kara", "Selene", "Vera"],
        "male": ["Darian", "Rowan", "Garrick", "Tomas", "Renald", "Cassian", "Oren", "Jarik"],
        "": ["Rowan", "Ren", "Tarin", "Vale", "Maren", "Cass", "Oren", "Sable"],
    },
    "unknown": {
        "female": ["Mira", "Veya", "Sera", "Anri", "Talia", "Kira", "Rhea", "Nara"],
        "male": ["Ren", "Tomas", "Oren", "Kellan", "Darin", "Joss", "Tavik", "Merrin"],
        "": ["Ren", "Mira", "Vale", "Sera", "Oren", "Tarin", "Nara", "Kavi"],
    },
}
NPC_CORE_TRAITS = [
    "guarded", "pragmatic", "curious", "proud", "cautious", "defiant",
    "patient", "sardonic", "earnest", "watchful", "reserved", "stubborn",
]
NPC_SOCIAL_TRAITS = [
    "measures trust slowly", "answers directly when pressed", "deflects with dry remarks",
    "tests intentions before yielding", "notices small inconsistencies",
    "protects vulnerable people first", "keeps emotion under tight control",
    "pushes for practical next steps",
]
NPC_ATTITUDES = [
    "wary", "controlled", "sharp-eyed", "tired but alert", "quietly intense",
    "skeptical", "formal under stress", "blunt", "careful", "restless",
]
NPC_WORK_ETHICS = [
    "survival-focused", "methodical", "dutiful", "resourceful", "opportunistic",
    "disciplined", "relentless", "cautious", "independent",
]
NPC_SPEECH_STYLES = [
    "clipped", "low and guarded", "plainspoken", "dry", "formal", "measured",
    "soft but firm", "blunt", "careful", "watchful",
]
NPC_SPEECH_QUIRKS = [
    "answers in short clauses",
    "asks pointed follow-up questions",
    "uses conditional promises",
    "keeps threats understated",
    "names risks before feelings",
    "pauses before accepting help",
    "uses practical comparisons",
    "avoids unnecessary gratitude",
    "speaks around fear rather than naming it",
    "turns uncertainty into a test",
]
NPC_VOICE_FORBIDDEN = [
    "DM-style scene narration",
    "omniscient exposition",
    "instant unconditional trust",
    "modern slang",
    "long speeches",
    "flowery monologues",
]
OOC_NOTE_PATTERN = re.compile(
    r"^\s*[\(\[\{]?\s*"
    r"(?P<label>"
    r"ooc(?:\s+note)?|"
    r"out\s+of\s+character|"
    r"note\s+to\s+(?:the\s+)?dm|"
    r"dm\s+note|"
    r"question\s+(?:for|to)\s+(?:the\s+)?dm|"
    r"clarification\s*(?:for\s+(?:the\s+)?dm)?|"
    r"meta\s+question"
    r")"
    r"\s*(?::|-)\s*"
    r"(?P<question>.+?)"
    r"\s*[\)\]\}]?\s*$",
    re.IGNORECASE | re.DOTALL,
)
DM_OVERRIDE_PATTERN = re.compile(
    r"^\s*[\(\[\{]?\s*"
    r"dm\s+override"
    r"\s*(?::|-)\s*"
    r"(?P<body>.+?)"
    r"\s*[\)\]\}]?\s*$",
    re.IGNORECASE | re.DOTALL,
)
DM_OVERRIDE_BODY_PATTERN = re.compile(
    r"^\s*"
    r"(?P<scope>scene|world|npc(?:\s+[^:]+)?)"
    r"\s*(?::|-)\s*"
    r"(?P<fact>.+?)"
    r"\s*$",
    re.IGNORECASE | re.DOTALL,
)
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
            story_bible_path = path_config.story_bible_path
            text = story_bible_path.read_text(encoding="utf-8")
            if story_bible_path.suffix.lower() == ".json" or text.lstrip().startswith("{"):
                loaded = json.loads(text)
                return self._flatten_story_bible_reference(loaded)
            return text
        except FileNotFoundError:
            return "Story bible not found."
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse story bible JSON: {e}")
            return "Story bible not found."

    def _flatten_story_bible_reference(self, value: Any) -> str:
        """Convert structured story-bible JSON into searchable canonical text."""
        lines: List[str] = []

        def label(path: List[str]) -> str:
            return " / ".join(str(part).replace("_", " ").title() for part in path)

        def walk(node: Any, path: List[str]):
            if isinstance(node, dict):
                for key, child in node.items():
                    walk(child, path + [str(key)])
                return
            if isinstance(node, list):
                if all(not isinstance(item, (dict, list)) for item in node):
                    clean_items = [str(item).strip() for item in node if str(item).strip()]
                    if clean_items:
                        lines.append(f"{label(path)}: {', '.join(clean_items)}")
                    return
                for index, child in enumerate(node, start=1):
                    walk(child, path + [str(index)])
                return
            text = str(node).strip()
            if text:
                lines.append(f"{label(path)}: {text}")

        walk(value, [])
        return "\n".join(lines)
    def _load_summary_file(self) -> str:
        """Load the persistent one-line turn summary file."""
        try:
            if self.summary_file_path.exists():
                return self.summary_file_path.read_text(encoding="utf-8").strip()
        except Exception as e:
            logger.error(f"Failed to load summary file: {e}")
        return ""
    def _parse_story_transcript_entries(self, transcript_text: str, limit: Optional[int] = None) -> List[Dict[str, str]]:
        """Extract structured turn entries from the markdown story transcript."""
        entries: List[Dict[str, str]] = []
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
                header = match.group(0).splitlines()[0].strip()
                turn = re.sub(r"^##[ \t]+Turn[ \t]*", "", header).strip()
                entries.append({
                    "turn": turn,
                    "player": player_input,
                    "dm": dm_response,
                })
        if limit is not None:
            normalized_limit = max(0, int(limit))
            return entries[-normalized_limit:] if normalized_limit else []
        return entries
    def _parse_story_transcript(self, transcript_text: str) -> List[Tuple[str, str]]:
        """Extract recent player/DM pairs from the markdown story transcript."""
        entries = self._parse_story_transcript_entries(transcript_text, limit=MAX_CONVERSATION_HISTORY)
        return [(entry["player"], entry["dm"]) for entry in entries]
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
    def get_transcript_entries(self, limit: int = PROMPT_TRANSCRIPT_RETRIEVAL_MAX_TURNS) -> List[Dict[str, str]]:
        """Return structured transcript entries for local continuity retrieval."""
        try:
            if self.story_file_path.exists():
                transcript_text = self.story_file_path.read_text(encoding="utf-8")
                return self._parse_story_transcript_entries(transcript_text, limit=limit)
        except Exception as e:
            logger.error(f"Failed to load story transcript entries: {e}")
        return []
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
        """Legacy shim; GameEngine owns reference-based social DC selection."""
        return DEFAULT_UNEVALUATED_DC
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
        self._skill_dc_reference_cache = None
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
    def _normalize_inventories(self):
        """Keep saved inventories display-ready and combat-ready."""
        player = self.game_state.get("player")
        if isinstance(player, dict):
            normalize_player_currency(player)
            player["inventory"] = normalize_inventory_collection(player.get("inventory", {}))
        npcs = self.game_state.get("npcs", {})
        if isinstance(npcs, dict):
            for npc in npcs.values():
                if isinstance(npc, dict) and isinstance(npc.get("inventory"), dict):
                    npc["inventory"] = normalize_inventory_collection(npc.get("inventory", {}))
    def _scene_fact_key(self, value: Any, fallback: str = "scene_fact") -> str:
        """Return a stable, boring key for a scene fact."""
        raw_text = str(value or "").strip().lower()
        if raw_text and re.fullmatch(r"[a-z0-9_]{1,80}", raw_text):
            return raw_text
        text = self._normalize_key_text(value)
        if not text:
            return fallback
        words = [
            word
            for word in re.findall(r"[a-z0-9]+", text)
            if word not in {
                "the", "a", "an", "and", "or", "of", "to", "in", "on", "at", "is", "are",
                "was", "were", "has", "have", "had", "with", "from", "for", "by", "player",
                "current", "now", "still", "nearby", "left", "gone", "remain", "remains",
                "present", "active", "inactive", "no", "not",
            }
        ]
        key = "_".join(words[:7]).strip("_")
        return key[:80] or fallback
    def _clean_scene_fact_text(self, fact: Any) -> str:
        """Normalize a scene fact without letting nested structures into state."""
        if not isinstance(fact, (str, int, float, bool)):
            return ""
        return " ".join(str(fact).split()).strip()
    def _iter_scene_fact_entries(self, facts: Any, default_scope: str = "local") -> List[Tuple[str, str, str]]:
        """Flatten legacy and keyed scene fact shapes into scope/key/text triples."""
        entries: List[Tuple[str, str, str]] = []
        scope_default = default_scope if default_scope in {"local", "carryover"} else "local"
        if isinstance(facts, (str, int, float, bool)):
            text = self._clean_scene_fact_text(facts)
            if text:
                entries.append((scope_default, self._scene_fact_key(text), text))
            return entries
        if isinstance(facts, list):
            for item in facts:
                entries.extend(self._iter_scene_fact_entries(item, scope_default))
            return entries
        if not isinstance(facts, dict):
            return entries
        for scope in ("local", "carryover"):
            if scope in facts:
                entries.extend(self._iter_scene_fact_entries(facts.get(scope), scope))
        if any(scope in facts for scope in ("local", "carryover")):
            return entries
        if any(key in facts for key in ("key", "text", "fact", "value")):
            text = self._clean_scene_fact_text(facts.get("text") or facts.get("fact") or facts.get("value"))
            if text:
                scope = str(facts.get("scope") or scope_default).lower()
                scope = scope if scope in {"local", "carryover"} else scope_default
                key = self._scene_fact_key(facts.get("key") or facts.get("category") or text)
                entries.append((scope, key, text))
            return entries
        for key, value in facts.items():
            text = self._clean_scene_fact_text(value)
            if text:
                entries.append((scope_default, self._scene_fact_key(key or text), text))
        return entries
    def _upsert_scene_fact(self, memory: Dict[str, Dict[str, str]], scope: str, key: str, text: str):
        """Insert or replace one keyed scene fact, avoiding duplicate keys across scopes."""
        target_scope = scope if scope in {"local", "carryover"} else "local"
        fact_key = self._scene_fact_key(key or text)
        clean_text = self._clean_scene_fact_text(text)
        if not clean_text:
            return
        for existing_scope in ("local", "carryover"):
            if existing_scope != target_scope:
                memory.setdefault(existing_scope, {}).pop(fact_key, None)
        scoped = memory.setdefault(target_scope, {})
        scoped[fact_key] = clean_text
        while len(scoped) > SCENE_FACT_MAX_PER_SCOPE:
            scoped.pop(next(iter(scoped)))
    def _remove_scene_fact(self, memory: Dict[str, Dict[str, str]], fact_ref: Any) -> int:
        """Remove scene facts by key, dict reference, or exact text."""
        refs = self._iter_scene_fact_entries(fact_ref)
        candidates: List[Tuple[Optional[str], str, str]] = []
        raw_key = ""
        if refs:
            for scope, key, text in refs:
                candidates.append((scope, key, text))
        elif isinstance(fact_ref, (str, int, float, bool)):
            text = self._clean_scene_fact_text(fact_ref)
            raw_key = re.sub(r"[^a-z0-9_]+", "_", str(fact_ref).strip().lower()).strip("_")
            candidates.append((None, self._scene_fact_key(text), text))
        removed = 0
        for scope, key, text in candidates:
            scopes = [scope] if scope in {"local", "carryover"} else ["local", "carryover"]
            normalized_text = self._normalize_key_text(text)
            keys = {candidate for candidate in (key, raw_key) if candidate}
            for target_scope in scopes:
                scoped = memory.setdefault(target_scope, {})
                removed_key = False
                for candidate_key in keys:
                    if candidate_key in scoped:
                        del scoped[candidate_key]
                        removed += 1
                        removed_key = True
                if removed_key:
                    continue
                for existing_key, existing_text in list(scoped.items()):
                    if normalized_text and self._normalize_key_text(existing_text) == normalized_text:
                        del scoped[existing_key]
                        removed += 1
        return removed
    def _normalize_scene_facts(self) -> Dict[str, Dict[str, str]]:
        """Migrate scenario.scene_facts to scoped keyed current facts."""
        scenario = self.game_state.setdefault("scenario", {})
        existing = scenario.get("scene_facts", {})
        memory = {"local": {}, "carryover": {}}
        for scope, key, text in self._iter_scene_fact_entries(existing):
            self._upsert_scene_fact(memory, scope, key, text)
        scenario["scene_facts"] = memory
        return memory
    def _load_game_state(self):
        """Load the game state from file."""
        try:
            with open(GAME_STATE_PATH, "r", encoding="utf-8") as f:
                self.game_state = json.load(f)
            self._clean_known_facts()
            self._normalize_inventories()
            self._normalize_scene_facts()
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
            self._normalize_inventories()
            self._normalize_scene_facts()
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

    def _is_stable_npc_key(self, npc_key: Any) -> bool:
        """Return true for save keys that should not be renamed during normalization."""
        return str(npc_key or "").startswith(("npc_", "unnamed_"))

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
        if self._is_generic_npc_reference(reference):
            npc_id = self._allocate_placeholder_npc_id(reference, updates)
        elif str(reference).startswith(("npc_", "unnamed_")):
            npc_id = str(reference)
        elif learned_name and self._is_learned_npc_name(learned_name, str(reference)):
            npc_id = self._make_npc_id_from_name(str(learned_name))
        else:
            npc_id = self._make_npc_id_from_name(str(reference))

        inferred = self._infer_race_gender_from_reference(reference, learned_name or "", player_input, json.dumps(updates or {}, ensure_ascii=False))
        source = {
            "npc_id": npc_id,
            "aliases": [str(reference)],
        }
        if learned_name:
            source["known_name"] = learned_name
            source["display_name"] = learned_name
        if inferred.get("race"):
            source["race"] = inferred["race"]
        if inferred.get("gender"):
            source["gender"] = inferred["gender"]
        for field in (
            "role", "title", "status", "location", "injuries", "wounds",
            "conditions", "known_facts",
        ):
            if isinstance(updates, dict) and updates.get(field) not in ("", None, [], {}):
                source[field] = updates[field]

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
        if normalized.startswith("unnamed "):
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
            "display_name": "",
            "known_name": "unknown",
            "aliases": [],
            "gender": "",
            "race": "",
            "background": "",
            "class_theme": "",
            "reputation": 0,
            "title": "",
            "age": 0,
            "relationship_with_player": {
                "type": "stranger",
                "public_label": "Stranger",
                "notes": "",
            },
            "relationships": {},
            "known_facts": [],
        }
        for key, value in identity_source.items():
            if key not in identity and key != "guided_creation":
                if isinstance(value, list):
                    identity[key] = []
                elif isinstance(value, dict):
                    identity[key] = {}
                elif isinstance(value, bool):
                    identity[key] = value
                elif isinstance(value, (int, float)):
                    identity[key] = value
                else:
                    identity[key] = value if value is not None else ""

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
            "currency": {"copper": 0},
        }
    def _template_identity_fields(self) -> set:
        return set((self._load_character_template().get("identity") or {}).keys())
    def _npc_identity(self, npc: Dict[str, Any]) -> Dict[str, Any]:
        """Return the canonical mutable identity object for an NPC record."""
        identity = npc.setdefault("identity", {})
        return identity if isinstance(identity, dict) else {}

    def _unknown_npc_display_name(self, npc_id: str, identity: Dict[str, Any]) -> str:
        """Build a player-facing placeholder name without inventing a proper name."""
        race = self._normalize_key_text(identity.get("race", ""))
        if not race:
            inferred = self._infer_race_gender_from_reference(npc_id)
            race = self._normalize_key_text(inferred.get("race", ""))
        if race == "nekkko":
            race = "nekko"
        gender = self._normalize_npc_gender(identity.get("gender", ""))
        if not gender:
            gender = self._infer_race_gender_from_reference(npc_id).get("gender", "")
        role = {"female": "Woman", "male": "Man"}.get(gender, "NPC")
        race_label = race.title() if race and race != "unknown" else ""
        if race_label and role != "NPC":
            return f"Unknown {race_label} {role}"
        if race_label:
            return f"Unknown {race_label} NPC"
        return "Unknown NPC"

    def _npc_public_reference_label(self, npc_id: str, npc: Dict[str, Any]) -> str:
        """Return a player-safe label for an NPC whose true name is not known."""
        known_name = self._get_npc_field(npc, "known_name", "unknown")
        if self._is_learned_npc_name(known_name, npc_id):
            return self._compact_text(known_name, 80)
        identity = self._npc_identity(npc)
        placeholder = self._unknown_npc_display_name(npc_id, identity)
        return self._compact_text(placeholder, 80)

    def _npc_public_text(self, npc_id: str, npc: Dict[str, Any], value: Any,
                         max_chars: int) -> str:
        """Return NPC text with hidden true names replaced by the public label."""
        text = self._compact_text(value, max_chars)
        if not text:
            return ""
        known_name = self._get_npc_field(npc, "known_name", "unknown")
        if self._is_learned_npc_name(known_name, npc_id):
            return text
        display_name = self._get_npc_field(npc, "display_name", "")
        reference_label = self._npc_public_reference_label(npc_id, npc)
        if display_name and reference_label:
            pattern = rf"(?<!\w){re.escape(str(display_name))}(?!\w)"
            text = re.sub(pattern, reference_label, text, flags=re.IGNORECASE)
        return text

    def _npc_public_facts(self, npc_id: str, npc: Dict[str, Any],
                          facts: Any, max_items: int, max_chars: int) -> List[str]:
        """Return public NPC facts without hidden true-name leaks."""
        return [
            fact for fact in (
                self._npc_public_text(npc_id, npc, item, max_chars)
                for item in self._compact_list_text(facts, max_items, max_chars)
            )
            if fact
        ]

    def _generate_npc_display_name(self, npc_id: str, identity: Dict[str, Any],
                                   source: Optional[Dict[str, Any]] = None) -> str:
        """Generate a private true name without seeding from scene text."""
        source = source or {}
        race = self._base_stats_race_key(identity.get("race") or source.get("race") or "unknown")
        gender = self._normalize_npc_gender(identity.get("gender") or source.get("gender") or "")
        pool = NPC_NAME_POOLS.get(race) or NPC_NAME_POOLS.get("unknown", {})
        names = pool.get(gender) or pool.get("") or NPC_NAME_POOLS["unknown"][""]
        existing = {
            self._normalize_key_text(self._get_npc_field(other, "display_name", ""))
            for key, other in self.game_state.get("npcs", {}).items()
            if key != npc_id and isinstance(other, dict)
        }
        for _ in range(max(4, len(names) * 2)):
            candidate = self._profile_choice(names, "Ren")
            if self._normalize_key_text(candidate) not in existing:
                return candidate
        return f"{self._profile_choice(names, 'Ren')} {NPC_PROFILE_RANDOM.randint(2, 99)}"

    def _generate_npc_age(self, npc_id: str, identity: Dict[str, Any],
                          source: Optional[Dict[str, Any]] = None) -> int:
        """Generate an adult age for a newly discovered NPC."""
        source = source or {}
        for value in (identity.get("age"), source.get("age")):
            try:
                age = int(float(value))
                if age > 0:
                    return age
            except (TypeError, ValueError):
                pass
        context = self._normalize_key_text(" ".join([
            npc_id,
            identity.get("title", ""),
            source.get("role", ""),
            source.get("title", ""),
        ]))
        if "elder" in context:
            return NPC_PROFILE_RANDOM.randint(55, 82)
        if "girl" in context or "boy" in context or "young" in context:
            return NPC_PROFILE_RANDOM.randint(18, 24)
        return NPC_PROFILE_RANDOM.randint(19, 46)

    def _merge_npc_aliases(self, npc: Dict[str, Any], aliases: Any):
        """Persist aliases on the NPC record for reference resolution."""
        if aliases is None:
            return
        if isinstance(aliases, (str, int, float, bool)):
            aliases = [aliases]
        if not isinstance(aliases, list):
            return
        identity = self._npc_identity(npc)
        existing = identity.get("aliases", [])
        if isinstance(existing, (str, int, float, bool)):
            existing = [existing]
        if not isinstance(existing, list):
            existing = []
        seen = {self._normalize_key_text(alias) for alias in existing if alias}
        clean_aliases = [str(alias).strip() for alias in existing if str(alias).strip()]
        for alias in aliases:
            alias_text = str(alias or "").strip()
            alias_key = self._normalize_key_text(alias_text)
            if alias_text and alias_key not in seen:
                clean_aliases.append(alias_text)
                seen.add(alias_key)
        identity["aliases"] = clean_aliases
        npc["aliases"] = clean_aliases

    def _set_npc_known_name(self, npc: Dict[str, Any], value: Any):
        """Reveal or preserve the player-known name without changing the save key."""
        identity = self._npc_identity(npc)
        clean = self._compact_text(value, 80)
        if not clean:
            return
        if self._is_learned_npc_name(clean):
            identity["known_name"] = clean
            identity["display_name"] = clean
            self._merge_npc_aliases(npc, [identity.get("display_name"), clean])
            identity.pop("name", None)
            identity.pop("name_status", None)
            return
        identity["known_name"] = "unknown"
        identity.pop("name", None)
        identity.pop("name_status", None)

    def _set_npc_display_name(self, npc: Dict[str, Any], value: Any):
        """Set the private true/display name without revealing it to the player."""
        identity = self._npc_identity(npc)
        clean = self._compact_text(value, 80)
        if not clean or not self._is_learned_npc_name(clean):
            return
        identity["display_name"] = clean
        identity.pop("name", None)
        identity.pop("name_status", None)
        self._merge_npc_aliases(npc, [clean])

    def _ensure_npc_name_fields(self, npc_id: str, npc: Dict[str, Any],
                                source: Optional[Dict[str, Any]] = None):
        """Normalize display_name/known_name while keeping the NPC key stable."""
        identity = self._npc_identity(npc)
        source = source or {}
        identity_source = source.get("identity") if isinstance(source.get("identity"), dict) else {}
        legacy_name = identity.pop("name", None)
        legacy_status = identity.pop("name_status", None)
        current_known = identity.get("known_name")
        current_display = identity.get("display_name")
        source_known = (
            identity_source.get("known_name")
            or source.get("known_name")
        )
        if source_known and not self._is_learned_npc_name(source_known, npc_id):
            source_known = ""
        source_private_display = identity_source.get("display_name") or source.get("display_name")
        source_revealed_name = identity_source.get("name") or source.get("name") or legacy_name
        candidate_known = (
            current_known
            if self._is_learned_npc_name(current_known, npc_id)
            else source_known
        )
        if candidate_known and self._normalize_key_text(candidate_known) == "unknown":
            candidate_known = ""
        identity["known_name"] = "unknown"
        if candidate_known and self._is_learned_npc_name(candidate_known, npc_id):
            self._set_npc_known_name(npc, candidate_known)
        elif source_revealed_name and self._is_learned_npc_name(source_revealed_name, npc_id):
            if legacy_status == "unknown":
                self._set_npc_display_name(npc, source_revealed_name)
            else:
                self._set_npc_known_name(npc, source_revealed_name)
        elif source_private_display and self._is_learned_npc_name(source_private_display, npc_id):
            self._set_npc_display_name(npc, source_private_display)
        elif current_display and self._is_learned_npc_name(current_display, npc_id):
            self._set_npc_display_name(npc, current_display)
        else:
            self._set_npc_display_name(
                npc,
                self._generate_npc_display_name(npc_id, identity, source),
            )
        if not identity.get("display_name"):
            self._set_npc_display_name(
                npc,
                self._generate_npc_display_name(npc_id, identity, source),
            )
        if not self._is_learned_npc_name(identity.get("known_name"), npc_id):
            identity["known_name"] = "unknown"
        identity.pop("name", None)
        identity.pop("name_status", None)
        self._merge_npc_aliases(npc, [npc_id, source.get("npc_id"), self._npc_public_reference_label(npc_id, npc)])

    def _npc_alias_values(self, npc_id: str, npc: Dict[str, Any]) -> List[str]:
        """Return all reference strings that should resolve to this NPC."""
        identity = self._npc_identity(npc)
        aliases = []
        for value in [
            npc_id,
            npc.get("npc_id") if isinstance(npc, dict) else "",
            npc.get("display_name") if isinstance(npc, dict) else "",
            self._get_npc_field(npc, "name", ""),
            self._get_npc_field(npc, "display_name", ""),
            self._get_npc_field(npc, "known_name", ""),
            self._get_npc_field(npc, "title", ""),
        ]:
            if value and self._normalize_key_text(value) != "unknown":
                aliases.append(str(value))
        for container in (identity.get("aliases", []), npc.get("aliases", [])):
            if isinstance(container, (str, int, float, bool)):
                container = [container]
            if isinstance(container, list):
                aliases.extend(str(alias) for alias in container if alias)
        deduped = []
        seen = set()
        for alias in aliases:
            key = self._normalize_key_text(alias)
            if key and key not in seen:
                deduped.append(alias)
                seen.add(key)
        return deduped

    def _get_npc_field(self, npc: Dict[str, Any], field: str, default: Any = None) -> Any:
        """Read NPC data from the template shape with legacy fallback."""
        identity = npc.get("identity") if isinstance(npc.get("identity"), dict) else {}
        relationships = identity.get("relationships", {}) if isinstance(identity.get("relationships"), dict) else {}
        player_rel = relationships.get("player", {}) if isinstance(relationships, dict) else {}
        if field == "name":
            return identity.get("display_name") or identity.get("name") or npc.get("display_name") or npc.get("name", default)
        if field == "display_name":
            return identity.get("display_name") or identity.get("name") or npc.get("display_name", default)
        if field == "known_name":
            return identity.get("known_name") or ("unknown" if identity else default)
        if field == "trust" and "trust" not in identity and isinstance(player_rel, dict) and "trust" in player_rel:
            return player_rel.get("trust", default)
        if field == "relationship":
            return get_relationship_level(self._get_npc_field(npc, "trust", 0))
        if field == "trust_label":
            return get_relationship_level(self._get_npc_field(npc, "trust", 0))
        if field == "relationship_with_player":
            return self._npc_relationship_with_player(npc)
        if field in {"relationship_type_with_player", "relationship_role_with_player"}:
            return self._npc_relationship_with_player(npc).get("type", default)
        if field in {"relationship_label_with_player", "player_relationship"}:
            return self._npc_relationship_with_player_label(npc)
        if field in {"party", "party_member"}:
            for container in (identity, npc):
                for party_field in ("party", "party_member"):
                    if party_field in container:
                        return self._coerce_bool(container.get(party_field), False)
            return default
        if field in {"mood", "mood_score"}:
            return get_mood_score(npc, default)
        if field == "mood_label":
            return get_mood_label(get_mood_score(npc, 0))
        if field in {"interaction_history", "last_interaction"}:
            return identity.get(field, npc.get(field, default))
        if field in identity:
            return identity.get(field, default)
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
            "tattoo", "behavior", "goal", "need", "fear", "party", "knowledge", "memory",
        }:
            return True
        if lowered.startswith(("is ", "has ", "was ", "needs ", "wants ", "fears ", "knows ", "believes ")):
            return True
        state_verbs = {
            "is", "are", "was", "were", "has", "have", "had", "remains", "remain",
            "knows", "believes", "wants", "needs", "fears", "trusts", "distrusts",
            "revealed", "implied", "acknowledges", "acknowledged", "accepts", "accepted",
            "refuses", "refused", "recognizes", "recognized", "questions", "challenges",
            "tests", "hides", "hiding", "said", "says", "told", "mentioned", "mentions",
            "warned", "warns", "called", "calls",
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
            "party": "party",
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
            unknown_subjects = self._unknown_knowledge_subjects(clean)
            if unknown_subjects and self._known_facts_have_positive_subject(known_facts, unknown_subjects):
                return
            positive_subjects = self._positive_memory_subjects(clean)
            if positive_subjects:
                known_facts = [
                    existing for existing in known_facts
                    if not self._unknown_knowledge_subjects(existing, positive_subjects)
                ]
            known_facts = self._merge_known_fact(known_facts, clean)
        identity["known_facts"] = known_facts[-NPC_FACT_MAX_COUNT:]

    def _unknown_knowledge_subjects(self, fact: Any, restrict_to: Optional[set] = None) -> set:
        """Return proper-noun subjects in claims that an NPC lacks knowledge of them."""
        text = str(fact or "")
        subjects = set()
        patterns = [
            r"\b(?:no knowledge of|never heard of|not heard of|does not know|doesn't know)\s+([A-Z][A-Za-z'’-]{2,})",
            r"\b([A-Z][A-Za-z'’-]{2,})\s+(?:is|remains)\s+unknown\b",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                subjects.add(match.group(1).lower())
        if restrict_to is not None:
            subjects &= {str(item).lower() for item in restrict_to}
        return subjects

    def _positive_memory_subjects(self, fact: Any) -> set:
        """Return proper-noun subjects from high-signal memory facts."""
        text = str(fact or "")
        if self._unknown_knowledge_subjects(text):
            return set()
        if not any(token in text.lower() for token in ("said", "mentioned", "knows", "revealed", "warned", "called", "there is", "there's")):
            return set()
        subjects = {
            match.group(0).lower()
            for match in re.finditer(r"\b[A-Z][A-Za-z'’-]{2,}\b", text)
        }
        npc_names = {
            self._normalize_key_text(self._get_npc_field(npc, "known_name", ""))
            for npc in self.game_state.get("npcs", {}).values()
            if isinstance(npc, dict)
        }
        return {subject for subject in subjects if subject not in npc_names and subject not in {"the"}}

    def _known_facts_have_positive_subject(self, known_facts: List[str], subjects: set) -> bool:
        lowered_subjects = {str(subject).lower() for subject in subjects}
        for fact in known_facts:
            if self._unknown_knowledge_subjects(fact, lowered_subjects):
                continue
            positive_subjects = self._positive_memory_subjects(fact)
            if positive_subjects & lowered_subjects:
                return True
            lowered_fact = str(fact or "").lower()
            if any(subject in lowered_fact for subject in lowered_subjects) and any(
                token in lowered_fact for token in ("said", "mentioned", "revealed", "called", "there is", "there's")
            ):
                return True
        return False

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

    def _profile_choice(self, values: List[str], fallback: str = "") -> str:
        """Choose one profile phrase without relying on model output."""
        return NPC_PROFILE_RANDOM.choice(values) if values else fallback

    def _profile_sample(self, values: List[str], count: int) -> List[str]:
        """Sample a compact unique list for NPC profile fields."""
        if not values:
            return []
        count = max(0, min(count, len(values)))
        return NPC_PROFILE_RANDOM.sample(values, count)

    def _npc_profile_context_text(self, npc_id: str, identity: Dict[str, Any],
                                  source: Optional[Dict[str, Any]] = None) -> str:
        """Collect short context cues for first-pass NPC profile generation."""
        source = source or {}
        pieces = [
            npc_id,
            identity.get("display_name", ""),
            identity.get("known_name", ""),
            identity.get("race", ""),
            identity.get("gender", ""),
            identity.get("title", ""),
            identity.get("background", ""),
        ]
        facts = identity.get("known_facts", [])
        if isinstance(facts, list):
            pieces.extend(str(fact) for fact in facts[:6])
        for key in ("npc_id", "name", "display_name", "race", "gender", "role", "title", "status", "location"):
            pieces.append(source.get(key, ""))
        return self._normalize_key_text(" ".join(str(piece) for piece in pieces if piece))

    def _npc_role_label(self, npc_id: str, identity: Dict[str, Any],
                        source: Optional[Dict[str, Any]] = None) -> str:
        """Infer a simple role label for generated NPC identity text."""
        source = source or {}
        explicit = identity.get("title") or source.get("role") or source.get("title")
        if explicit:
            return self._compact_text(explicit, 60)
        text = self._npc_profile_context_text(npc_id, identity, source)
        if any(token in text for token in ["slave", "enslaved", "chain", "shackle", "bound", "mark"]):
            return "fugitive captive"
        if any(token in text for token in ["guard", "soldier", "patrol", "warrior"]):
            return "armed survivor"
        if any(token in text for token in ["merchant", "caravan", "wagon", "trader"]):
            return "caravan survivor"
        if any(token in text for token in ["healer", "doctor", "medic", "medicine"]):
            return "field healer"
        race = identity.get("race") or "unknown"
        return f"{race} survivor" if race else "local survivor"

    def _npc_profile_motivation(self, context_text: str) -> str:
        if any(token in context_text for token in ["slave", "enslaved", "chain", "shackle", "bound", "mark"]):
            return "freedom without recapture"
        if any(token in context_text for token in ["wound", "bleed", "injur", "pain", "stable"]):
            return "survival and enough safety to recover"
        if any(token in context_text for token in ["guard", "soldier", "patrol", "warrior"]):
            return "control of the immediate threat"
        return self._profile_choice([
            "survival", "protecting what remains", "finding leverage",
            "getting reliable information", "staying free of obligations",
        ], "survival")

    def _npc_profile_fear(self, context_text: str) -> str:
        if any(token in context_text for token in ["slave", "enslaved", "chain", "shackle", "bound", "mark"]):
            return "being owned again"
        if "demon" in context_text:
            return "being found by demons"
        if any(token in context_text for token in ["betray", "distrust", "trust"]):
            return "misplaced trust"
        return self._profile_choice(["betrayal", "helplessness", "public humiliation", "losing control"], "betrayal")

    def _generate_npc_character_profile(self, npc_id: str, npc: Dict[str, Any],
                                        source: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create a persistent non-API profile for a newly discovered NPC."""
        identity = self._npc_identity(npc)
        source = source or {}
        name = identity.get("display_name") or source.get("display_name") or source.get("name")
        if not name:
            name = self._generate_npc_display_name(npc_id, identity, source)
            identity["display_name"] = name
        race = identity.get("race") or source.get("race") or "unknown"
        gender = identity.get("gender") or source.get("gender") or ""
        age = self._generate_npc_age(npc_id, identity, source)
        context_text = self._npc_profile_context_text(npc_id, identity, source)
        role = self._npc_role_label(npc_id, identity, source)

        core_pool = list(NPC_CORE_TRAITS)
        social_pool = list(NPC_SOCIAL_TRAITS)
        attitude_pool = list(NPC_ATTITUDES)
        if any(token in context_text for token in ["slave", "enslaved", "chain", "shackle", "bound", "mark"]):
            core_pool.extend(["defiant", "guarded", "watchful", "stubborn"])
            social_pool.extend(["tests kindness for hidden costs", "treats help as a bargain until proven otherwise"])
            attitude_pool.extend(["braced for betrayal", "coldly alert", "defensive"])
        if "nekko" in context_text:
            core_pool.extend(["watchful", "quick-reacting", "proud"])
            social_pool.extend(["tracks tone and body language closely", "masks fear with sharp questions"])
            attitude_pool.extend(["feline-still", "coiled", "sharp-eared"])

        personality = {
            "core_trait": self._profile_choice(core_pool, "guarded"),
            "social_trait": self._profile_choice(social_pool, "measures trust slowly"),
            "work_ethic": self._profile_choice(NPC_WORK_ETHICS, "survival-focused"),
            "attitude": self._profile_choice(attitude_pool, "wary"),
            "likes": self._profile_sample([
                "plain bargains", "kept promises", "practical competence",
                "quiet exits", "useful information", "being asked before touched",
            ], 2),
            "dislikes": self._profile_sample([
                "ownership language", "careless noise", "pity", "boasting",
                "unearned familiarity", "being cornered", "vague promises",
            ], 2),
            "fears": self._npc_profile_fear(context_text),
            "motivations": self._npc_profile_motivation(context_text),
            "boundaries": [
                "does not grant trust quickly",
                "reacts badly to being handled without consent",
            ],
        }
        speech_style = self._profile_choice(NPC_SPEECH_STYLES, "guarded")
        quirks = self._profile_sample(NPC_SPEECH_QUIRKS, 3)
        example_dialogue = [
            f'"Say what you mean, {name if name and not name.lower().startswith("unknown") else "stranger"}."',
            '"Help has a price. Name it before I owe you."',
            '"I heard that. Keep your voice down."',
        ]
        if "slave" in context_text or "chain" in context_text or "mark" in context_text:
            example_dialogue = [
                '"Do not touch the mark."',
                '"Chains make promises cheap. Prove yours another way."',
                '"Quiet. If they hear us, we both lose."',
            ]
        voice_profile = {
            "core_personality": (
                f"{name} is a {personality['core_trait']} {role} who "
                f"{personality['social_trait']} and remains {personality['attitude']}."
            ),
            "speech_style": speech_style,
            "register": self._profile_choice(["plain", "rough", "controlled", "formal", "dry"], "plain"),
            "pace": self._profile_choice(["short bursts", "measured", "slow under stress", "quick and clipped"], "measured"),
            "sentence_length": self._profile_choice(["short", "short-to-medium", "varied but concise"], "short"),
            "quirks": quirks,
            "example_dialogue": example_dialogue,
            "forbidden": list(NPC_VOICE_FORBIDDEN),
        }
        role_phrase = role if self._normalize_key_text(role).startswith(self._normalize_key_text(race)) else f"{race} {role}"
        background = (
            f"{name} is a {role_phrase}, shaped by {personality['motivations']} "
            f"and wary of {personality['fears']}."
        )
        class_theme = f"{role.title()} - {personality['core_trait']} / {speech_style}"
        return {
            "background": self._compact_text(background, 220),
            "class_theme": self._compact_text(class_theme, 100),
            "personality": personality,
            "voice_profile": voice_profile,
            "deviation_range": NPC_PROFILE_RANDOM.choice([5, 7, 10, 12]),
            "trust": -5 if personality["core_trait"] in {"guarded", "cautious", "defiant", "reserved"} else 0,
            "role": role,
            "gender": gender,
            "age": age,
        }

    def _has_distinct_npc_profile(self, npc: Dict[str, Any]) -> bool:
        """Return true when an NPC already has usable personality and voice data."""
        personality = npc.get("personality") if isinstance(npc.get("personality"), dict) else {}
        voice = npc.get("voice_profile") if isinstance(npc.get("voice_profile"), dict) else {}
        return bool(
            personality.get("core_trait")
            and personality.get("social_trait")
            and voice.get("core_personality")
            and voice.get("speech_style")
        )

    def _ensure_npc_character_profile(self, npc_id: str, npc: Dict[str, Any],
                                      source: Optional[Dict[str, Any]] = None):
        """Ensure a live NPC has persistent background, personality, and voice."""
        if not isinstance(npc, dict):
            return
        identity = self._npc_identity(npc)
        profile = self._generate_npc_character_profile(npc_id, npc, source or {})
        if not identity.get("background"):
            identity["background"] = profile["background"]
        if not identity.get("class_theme"):
            identity["class_theme"] = profile["class_theme"]
        if not identity.get("title"):
            identity["title"] = profile["role"]
        try:
            existing_age = int(float(identity.get("age") or 0))
        except (TypeError, ValueError):
            existing_age = 0
        if existing_age <= 0:
            identity["age"] = profile["age"]
        if not self._has_distinct_npc_profile(npc):
            npc["personality"] = profile["personality"]
            npc["voice_profile"] = profile["voice_profile"]
        personality = npc.get("personality") if isinstance(npc.get("personality"), dict) else profile["personality"]
        voice_profile = npc.setdefault("voice_profile", {})
        if isinstance(voice_profile, dict):
            display_name = self._get_npc_field(npc, "display_name", "") or npc_id.replace("_", " ").title()
            role = identity.get("title") or profile["role"]
            voice_profile["core_personality"] = (
                f"{display_name} is a {personality.get('core_trait', 'guarded')} {role} who "
                f"{personality.get('social_trait', 'measures trust slowly')} and remains "
                f"{personality.get('attitude', 'wary')}."
            )
            voice_profile.setdefault("forbidden", list(NPC_VOICE_FORBIDDEN))
            background_text = self._normalize_key_text(identity.get("background", ""))
            if (
                self._is_learned_npc_name(display_name, npc_id)
                and background_text.startswith("unknown")
            ):
                identity["background"] = self._compact_text(
                    f"{display_name} is a {identity.get('race') or 'unknown'} {role}, "
                    f"shaped by {personality.get('motivations', 'survival')} "
                    f"and wary of {personality.get('fears', 'betrayal')}.",
                    220,
                )
        npc.setdefault("deviation_range", profile["deviation_range"])
        self._migrate_player_relationship_fields(npc)
        identity.setdefault("trust", profile["trust"])
        identity.setdefault("relationships", {})
        self._migrate_player_relationship_fields(npc)

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

    def _migrate_player_relationship_fields(self, npc: Dict[str, Any]):
        """Keep player trust/mood on identity while preserving inter-NPC relationships."""
        identity = self._npc_identity(npc)
        def migrate_mood_fields():
            if "mood_score" in identity and not isinstance(identity.get("mood"), (int, float)):
                identity["mood"] = identity.pop("mood_score")
            if isinstance(identity.get("mood"), str):
                mood_text = identity["mood"].strip()
                try:
                    identity["mood"] = round(float(mood_text), 2)
                except ValueError:
                    match = re.search(r"\((-?\d+(?:\.\d+)?)", mood_text)
                    if match:
                        try:
                            identity["mood"] = round(float(match.group(1)), 2)
                        except ValueError:
                            identity.pop("mood", None)
                    else:
                        identity.pop("mood", None)
            identity.pop("mood_score", None)
        relationships = identity.get("relationships")
        if not isinstance(relationships, dict):
            identity["relationships"] = {}
            migrate_mood_fields()
            return
        player_rel = relationships.get("player")
        if not isinstance(player_rel, dict):
            migrate_mood_fields()
            return
        if "trust" not in identity and "trust" in player_rel:
            try:
                identity["trust"] = round(float(player_rel.get("trust")), 2)
            except (TypeError, ValueError):
                identity["trust"] = player_rel.get("trust")
        for field in ("interaction_history", "last_interaction"):
            if field in player_rel and field not in identity:
                identity[field] = player_rel.get(field)
            player_rel.pop(field, None)
        relationship_role = (
            player_rel.get("relationship_with_player")
            or player_rel.get("relationship_type")
            or player_rel.get("relationship_role")
            or player_rel.get("role")
        )
        legacy_relationship = player_rel.get("relationship")
        if not relationship_role and legacy_relationship:
            trust_labels = {
                str(band.get("label", "")).strip().lower()
                for band in load_trust_reference().get("trust_scale", [])
                if isinstance(band, dict)
            }
            legacy_key = str(legacy_relationship).strip().lower()
            if legacy_key and legacy_key not in trust_labels:
                relationship_role = legacy_relationship
        if relationship_role and "relationship_with_player" not in identity:
            identity["relationship_with_player"] = self._normalize_relationship_with_player(relationship_role)
        for field in ("relationship_with_player", "relationship_type", "relationship_role", "role"):
            player_rel.pop(field, None)
        player_rel.pop("trust", None)
        player_rel.pop("relationship", None)
        if not player_rel:
            relationships.pop("player", None)
        migrate_mood_fields()

    def _relationship_label_from_type(self, relationship_type: Any) -> str:
        clean = self._compact_text(relationship_type, 80).replace("_", " ").replace("-", " ")
        clean = " ".join(clean.split()).strip()
        if not clean:
            return "Stranger"
        return " ".join(part.capitalize() for part in clean.split())

    def _normalize_relationship_with_player(self, value: Any) -> Dict[str, str]:
        if isinstance(value, dict):
            rel_type = (
                value.get("type")
                or value.get("relationship_type")
                or value.get("role")
                or value.get("category")
                or value.get("public_label")
                or value.get("label")
                or "stranger"
            )
            public_label = value.get("public_label") or value.get("label")
            notes = value.get("notes") or ""
        else:
            rel_type = value or "stranger"
            public_label = ""
            notes = ""
        rel_type = self._compact_text(rel_type, 80).replace("_", " ").strip().lower() or "stranger"
        public_label = self._compact_text(public_label, 80) or self._relationship_label_from_type(rel_type)
        return {
            "type": rel_type,
            "public_label": public_label,
            "notes": self._compact_text(notes, 160),
        }

    def _npc_relationship_with_player(self, npc: Dict[str, Any]) -> Dict[str, str]:
        identity = self._npc_identity(npc)
        relationship = identity.get("relationship_with_player")
        return self._normalize_relationship_with_player(relationship)

    def _npc_relationship_with_player_label(self, npc: Dict[str, Any]) -> str:
        relationship = self._npc_relationship_with_player(npc)
        return relationship.get("public_label") or self._relationship_label_from_type(relationship.get("type", "stranger"))

    def _set_npc_field(self, npc: Dict[str, Any], field: str, value: Any):
        """Safely write NPC data - protect known_facts from technical garbage."""
        identity = self._npc_identity(npc)
        template_fields = self._template_identity_fields()

        if field in {"npc_id", "updated_at", "experience"}:
            return

        if field == "aliases":
            self._merge_npc_aliases(npc, value)
            return

        if field in {"background", "class_theme", "guided_creation"}:
            return

        if field == "display_name":
            self._set_npc_display_name(npc, value)
            return

        if field in {"name", "known_name"}:
            self._set_npc_known_name(npc, value)
            return

        if field == "name_status":
            return

        if field == "role":
            if value not in ("", None):
                identity["title"] = self._compact_text(value, 80)
            return

        if field in {"party", "party_member", "is_party_member"}:
            is_party = self._coerce_bool(value, False)
            identity["party"] = is_party
            identity["party_member"] = is_party
            npc["party"] = is_party
            return

        if field == "party_role":
            if value not in ("", None):
                identity["party_role"] = self._compact_text(value, 80)
            return

        if field in {"relationship_with_player", "player_relationship"}:
            identity["relationship_with_player"] = self._normalize_relationship_with_player(value)
            return

        if field in {"relationship_type_with_player", "relationship_role_with_player"}:
            current = self._npc_relationship_with_player(npc)
            current["type"] = value
            current["public_label"] = ""
            identity["relationship_with_player"] = self._normalize_relationship_with_player(current)
            return

        if field == "deviation_range":
            try:
                npc["deviation_range"] = max(1, min(20, int(float(value))))
            except (TypeError, ValueError):
                pass
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
            try:
                identity["mood"] = round(float(value), 2)
            except (TypeError, ValueError):
                pass
            return
        if field == "mood_score":
            try:
                identity["mood"] = round(float(value), 2)
            except (TypeError, ValueError):
                pass
            return

        if field in {"facts", "known_fact"}:
            field = "known_facts"

        if field == "known_facts":
            for fact in self._sanitize_known_facts_value(value):
                self._append_npc_known_fact(npc, fact)
            return

        # === RELATIONSHIPS ===
        if field == "relationship":
            return

        if field == "interaction_history":
            identity["interaction_history"] = value if isinstance(value, list) else []
            return

        # === BIG TECHNICAL OBJECTS - DO NOT DUMP INTO known_facts ===
        if field in {"stats", "skills", "derived", "inventory", "equipment", "currency", "gold", "personality", "voice_profile"}:
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
            if field == "relationships":
                self._migrate_player_relationship_fields(npc)
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
        source_identity = source.get("identity") if isinstance(source.get("identity"), dict) else {}
        identity_aliases = source_identity.get("aliases", []) if isinstance(source_identity.get("aliases"), list) else []
        aliases.update(str(alias) for alias in identity_aliases if alias)
        for alias in [
            npc_id,
            source.get("npc_id"),
            source.get("name"),
            source.get("display_name"),
            source.get("known_name"),
            source_identity.get("name"),
            source_identity.get("display_name"),
            source_identity.get("known_name"),
        ]:
            if alias:
                aliases.add(str(alias))
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
                "stats", "skills", "derived", "currency", "gold", "background", "class_theme",
                "guided_creation", "known_facts",
            }:
                continue
            if field != "identity" and value not in ("", None, [], {}):
                self._set_npc_field(template, field, value)
        identity = self._npc_identity(template)
        if not source_is_polluted:
            for field, max_chars in (("background", 220), ("class_theme", 100)):
                preserved = source_identity.get(field) or source.get(field)
                if preserved not in ("", None, [], {}):
                    identity[field] = self._compact_text(preserved, max_chars)
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
        self._migrate_player_relationship_fields(template)
        identity["relationship_with_player"] = self._normalize_relationship_with_player(
            identity.get("relationship_with_player")
        )
        identity.setdefault("known_facts", [])
        self._merge_npc_aliases(template, list(aliases))
        self._ensure_npc_name_fields(npc_id, template, source)
        self._ensure_npc_character_profile(npc_id, template, source)
        self._initialize_npc_baseline_stats(template)
        if aliases:
            alias_map = self.game_state.setdefault("npc_aliases", {})
            for alias in self._npc_alias_values(npc_id, template):
                alias_map[alias] = npc_id
        return template
    def _merge_npc_records(self, canonical_key: str, canonical: Dict[str, Any],
                           duplicate_key: str, duplicate: Dict[str, Any]) -> Dict[str, Any]:
        """Merge two NPC records into a single canonical template-shaped record."""
        merged = self._make_template_npc(canonical_key, canonical)
        for source in (duplicate,):
            source_identity = source.get("identity") if isinstance(source.get("identity"), dict) else {}
            for field, value in source_identity.items():
                if value not in ("", None, [], {}):
                    if field == "trust":
                        current_trust = self._npc_identity(merged).get("trust")
                        try:
                            incoming_num = float(value)
                            current_num = float(current_trust)
                        except (TypeError, ValueError):
                            incoming_num = current_num = None
                        if (
                            incoming_num in {-5.0, 0.0}
                            and current_num is not None
                            and current_num not in {-5.0, 0.0}
                        ):
                            continue
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
        self._ensure_npc_name_fields(canonical_key, merged)
        alias_map = self.game_state.setdefault("npc_aliases", {})
        self._merge_npc_aliases(merged, [canonical_key, duplicate_key])
        for alias in self._npc_alias_values(canonical_key, merged):
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
        learned_name_index: Dict[str, str] = {}
        for npc_key, npc in list(npcs.items()):
            if not isinstance(npc, dict):
                continue
            name = self._get_npc_field(npc, "name", "")
            if not name and not self._is_stable_npc_key(npc_key):
                name = npc_key
            if player_name and (
                self._normalize_key_text(name) == player_name
                or self._normalize_key_text(npc_key) == self._normalize_key_text(player_key)
            ):
                continue
            canonical_key = str(npc_key) if self._is_stable_npc_key(npc_key) else self._make_npc_id_from_name(name or str(npc_key))
            source_npc = npc
            if not self._is_stable_npc_key(npc_key) and name:
                source_npc = copy.deepcopy(npc)
                source_npc.setdefault("name", name)
            templated = self._make_template_npc(canonical_key, source_npc)
            identity = self._npc_identity(templated)
            self._ensure_npc_name_fields(canonical_key, templated)
            learned_name = self._get_npc_field(templated, "known_name", "")
            learned_key = self._normalize_key_text(learned_name) if self._is_learned_npc_name(learned_name, canonical_key) else ""
            merge_key = canonical_key
            if learned_key and learned_key in learned_name_index and not self._is_stable_npc_key(npc_key):
                merge_key = learned_name_index[learned_key]
            if merge_key in normalized:
                canonical_key = merge_key
                normalized[canonical_key] = self._merge_npc_records(canonical_key, normalized[canonical_key], npc_key, templated)
            else:
                normalized[canonical_key] = templated
            if learned_key and learned_key not in learned_name_index:
                learned_name_index[learned_key] = canonical_key
            for alias in self._npc_alias_values(canonical_key, normalized[canonical_key]):
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
                    self._get_npc_field(npc, "display_name"),
                    self._get_npc_field(npc, "known_name"),
                    self._get_npc_field(npc, "title"),
                    npc_key,
                ]
                names.extend(self._npc_alias_values(npc_key, npc))
                if any(
                    target_norm == self._normalize_key_text(name)
                    for name in names
                    if name and self._normalize_key_text(name) != "unknown"
                ):
                    return npc_key
        for npc in known_npcs or []:
            npc_id = npc.get("npc_id", "")
            names = [
                npc_id,
                npc.get("name", ""),
                npc.get("display_name", ""),
                npc.get("known_name", ""),
                npc.get("reference_label", ""),
            ]
            if target_norm in {self._normalize_key_text(name) for name in names if name}:
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
- Address the player character as "you" in narration; do not use the character name or third-person pronouns for the player except in quoted dialogue or rare disambiguation.
- Treat precomputed NPC action dialogue as the authoritative NPC voice. Quote it exactly or omit it; do not replace it with alternate speech for the same NPC beat.
- Treat saved WORLD TIME as authoritative. Do not change time of day unless the prompt clock supports it or the JSON includes time_update.
- If narration advances time through waiting, travel, searching, crafting, resting, studying, or a named duration, include time_update with the elapsed minutes.
- If the narration gives the player any found, taken, received, purchased, or looted item, include a matching inventory add command in the final JSON.
- If the narration gives the player ordinary coins or money, include a matching currency command instead of an inventory item.
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

    def _extract_ooc_question(self, player_input: Any) -> str:
        """Return the OOC question text when the entire input is a DM note."""
        text = str(player_input or "").strip()
        if not text:
            return ""
        match = OOC_NOTE_PATTERN.match(text)
        if not match:
            return ""
        question = " ".join(match.group("question").split()).strip()
        return question

    def _extract_dm_override(self, player_input: Any) -> Optional[Dict[str, str]]:
        """Return a parsed direct DM override when the entire input uses override syntax."""
        text = str(player_input or "").strip()
        if not text:
            return None
        match = DM_OVERRIDE_PATTERN.match(text)
        if not match:
            return None
        body = " ".join(match.group("body").split()).strip()
        body_match = DM_OVERRIDE_BODY_PATTERN.match(body)
        if not body_match:
            return {"error": "Use (DM Override: scene: fact), (DM Override: world: fact), or (DM Override: npc Name: fact)."}
        scope = self._normalize_key_text(body_match.group("scope"))
        fact = self._clean_override_fact(body_match.group("fact"))
        if not fact:
            return {"error": "Override fact was empty or unsafe."}
        if scope.startswith("npc "):
            return {
                "scope": "npc",
                "target": scope[4:].strip(),
                "fact": fact,
            }
        return {
            "scope": scope,
            "target": "",
            "fact": fact,
        }

    def _clean_override_fact(self, fact: Any, max_chars: int = 220) -> str:
        """Normalize a direct override fact while rejecting nested/technical payloads."""
        if not isinstance(fact, (str, int, float, bool)):
            return ""
        clean = " ".join(str(fact).split()).strip()
        if not clean:
            return ""
        lowered = clean.lower()
        blocked = ("known_facts", "identity:", "stats:", "skills:", "derived:", "{", "}", "[", "]", '":', "':")
        if any(token in lowered for token in blocked):
            return ""
        return clean[:max_chars].rstrip()

    def _ooc_note_looks_like_override_request(self, question: str) -> bool:
        """Detect OOC preference notes that should teach override syntax instead of calling the API."""
        lowered = self._normalize_key_text(question)
        if not lowered:
            return False
        if any(lowered.startswith(prefix) for prefix in (
            "i want ",
            "i would like ",
            "please make ",
            "please have ",
            "can you make ",
            "can you have ",
            "can you establish ",
            "establish that ",
            "inject ",
            "override ",
        )):
            return True
        return " i want " in f" {lowered} " or " i would like " in f" {lowered} "

    def _scene_role_name(self, role: str) -> str:
        """Infer a named scene role such as 'healer' from current scene facts when obvious."""
        role_key = self._normalize_key_text(role)
        if not role_key:
            return ""
        context = " ".join([
            self._get_scene_context(),
            " ".join(self._compact_scene_facts_for_prompt(20, 220)),
        ])
        pattern = re.compile(rf"\b(?:local\s+)?{re.escape(role_key)}\s*,\s*([A-Z][a-zA-Z'\-]+)", re.IGNORECASE)
        match = pattern.search(context)
        if match:
            return f"{role_key.title()} {match.group(1)}"
        return ""

    def _scene_title_for_name(self, name: str) -> str:
        """Infer a role title for a named NPC from scene facts when obvious."""
        clean_name = str(name or "").strip()
        if not clean_name:
            return ""
        context = " ".join([
            self._get_scene_context(),
            " ".join(self._compact_scene_facts_for_prompt(20, 220)),
        ])
        pattern = re.compile(rf"\b(?:local\s+)?([a-z][a-z'\-]+)\s*,\s*{re.escape(clean_name)}\b", re.IGNORECASE)
        match = pattern.search(context)
        if not match:
            return ""
        role = self._normalize_key_text(match.group(1))
        if role in {"local", "current", "the", "a", "an"}:
            return ""
        return f"{role.title()} {clean_name[:1].upper() + clean_name[1:]}"

    def _known_name_corrected_text(self, text: str) -> str:
        """Lightly correct near-miss known NPC names in generated override suggestions."""
        known_names = [
            npc.get("known_name")
            for npc in self._get_known_npcs_for_prompt()
            if isinstance(npc, dict) and self._is_learned_npc_name(npc.get("known_name"), npc.get("npc_id", ""))
        ]
        canonical = {self._normalize_key_text(name): str(name) for name in known_names if name}
        if not canonical:
            return text
        name_keys = list(canonical.keys())

        def replace_word(match: re.Match) -> str:
            word = match.group(0)
            normalized = self._normalize_key_text(word)
            if normalized in canonical:
                return canonical[normalized]
            if len(normalized) < 4:
                return word
            candidates = [name for name in name_keys if name[:1] == normalized[:1]]
            close = difflib.get_close_matches(normalized, candidates, n=1, cutoff=0.4)
            return canonical[close[0]] if close else word

        return re.sub(r"\b[A-Za-z][A-Za-z'\-]*\b", replace_word, text)

    def _suggest_dm_override_phrase(self, question: str) -> str:
        """Convert an OOC preference note into an explicit override syntax hint."""
        text = " ".join(str(question or "").split()).strip()
        text = re.sub(
            r"\s*[.?!,;:]*\s*(?:can|could)\s+you\s+(?:do\s+that|make\s+that\s+happen|work\s+with\s+that)\??\s*$",
            "",
            text,
            flags=re.IGNORECASE,
        ).strip()
        text = re.sub(r"[?.!]+$", "", text).strip()
        fact = ""
        want_match = re.match(r"^(?:i\s+want|i\s+would\s+like)\s+(?P<subject>.+?)\s+to\s+(?P<action>.+)$", text, flags=re.IGNORECASE)
        command_match = re.match(r"^(?:please\s+make|please\s+have|can\s+you\s+make|can\s+you\s+have|can\s+you\s+establish)\s+(?P<subject>.+?)\s+to\s+(?P<action>.+)$", text, flags=re.IGNORECASE)
        match = want_match or command_match
        if match:
            subject = re.sub(r"^(?:the|a|an)\s+", "", match.group("subject").strip(), flags=re.IGNORECASE)
            titled_name = self._scene_title_for_name(subject)
            if titled_name:
                subject = titled_name
            else:
                role_name = self._scene_role_name(subject)
                subject = role_name or (subject[:1].upper() + subject[1:])
            action = match.group("action").strip()
            fact = f"{subject} will {action}."
        else:
            fact = text[:1].upper() + text[1:]
            if fact and fact[-1] not in ".!?":
                fact += "."
        fact = self._known_name_corrected_text(self._clean_override_fact(fact) or "Story detail goes here.")
        return f"OOC Note -- To inject a story detail use the following phrase: (DM Override: scene: {fact})"

    def _build_ooc_question_context(self, player_input: str, question: str) -> Dict[str, Any]:
        """Build a local-only context packet for OOC referee answers."""
        scene_facts = self._compact_scene_facts_for_prompt(
            PROMPT_COMPACT_LIST_ITEMS,
            PROMPT_COMPACT_LIST_CHARS,
        )
        return {
            "knowledge_priority": self._knowledge_priority_context(),
            "raw_player_input": player_input,
            "ooc_question": question,
            "campaign_summary": self._compact_text(
                self.conversation_manager.get_summary_file_text(),
                PROMPT_COMPACT_TEXT_CHARS,
            ),
            "recent_exchanges": self._compact_recent_exchanges(PROMPT_RECENT_EXCHANGE_LIMIT),
            "relevant_transcript_evidence": self._retrieve_relevant_transcript_evidence(question),
            "opening_scene": self._opening_scene_context(),
            "current_scene": self._compact_text(self._get_scene_context(), PROMPT_SCENE_CONTEXT_CHARS),
            "scene_facts": scene_facts,
            "world_facts": self._compact_list_text(
                self.game_state.get("world", {}).get("facts", []),
                PROMPT_COMPACT_LIST_ITEMS,
                PROMPT_COMPACT_LIST_CHARS,
            ),
            "world_time": self._world_time_context(),
            "known_npcs": self._get_known_npcs_for_prompt(),
            "location": self.game_state.get("world", {}).get("location", {}),
            "player": self._compact_player_for_prompt(),
            "player_possessions": self._compact_player_possessions_for_prompt(),
            "story_bible_excerpt": self._story_bible_excerpt(
                question,
                max_chars=PROMPT_RUNTIME_STORY_BIBLE_CHARS,
            ),
            "story_bible_lore": self._select_story_bible_lore(question, scene_facts=scene_facts, max_entries=6),
            "answer_rules": [
                "Answer out of character as the DM/referee.",
                "Do not advance the story, trigger rolls, speak as NPCs, or emit commands.",
                "Use only supplied context; say when the saved context does not establish an answer.",
            ],
        }

    def _normalize_ooc_answer(self, response: Any, context: Dict[str, Any]) -> str:
        """Convert a structured or narrative OOC response into a safe display string."""
        answer = ""
        if isinstance(response, dict):
            answer = response.get("answer") or response.get("narrative") or response.get("message") or ""
        else:
            answer = str(response or "")
        answer = str(answer or "").strip()
        if answer.startswith("```"):
            answer = re.sub(r"^```(?:json|text)?\s*", "", answer, flags=re.IGNORECASE).strip()
            answer = re.sub(r"\s*```$", "", answer).strip()
        if answer.startswith("{") and answer.endswith("}"):
            try:
                parsed = json.loads(answer)
                if isinstance(parsed, dict):
                    answer = str(parsed.get("answer") or parsed.get("narrative") or answer).strip()
            except json.JSONDecodeError:
                pass
        if not answer:
            scene = self._compact_text(context.get("current_scene", ""), PROMPT_COMPACT_LIST_CHARS)
            facts = context.get("scene_facts", []) if isinstance(context.get("scene_facts"), list) else []
            fact_text = "; ".join(str(fact) for fact in facts[:PROMPT_COMPACT_LIST_ITEMS])
            if fact_text:
                answer = f"Saved scene facts say: {fact_text}"
            elif scene:
                answer = f"Saved scene context says: {scene}"
            else:
                answer = "The saved context does not establish that yet."
        if not answer.lower().startswith("ooc note"):
            answer = f"OOC note - {answer}"
        return answer

    def _ooc_bypass_result(self, player_input: str, question: str, narrative: str,
                           command: Dict[str, Any], success: bool, message: str) -> Dict[str, Any]:
        """Return a standard OOC response shell that bypasses the story pipeline."""
        return {
            "narrative": narrative,
            "command_executed": command,
            "mechanical_result": {
                "success": success,
                "message": message,
            },
            "ooc": True,
            "ooc_question": question,
            "social_check": {
                "needs_social_check": False,
                "bypassed": True,
                "reason": "OOC DM note",
            },
            "social_result": None,
            "npc_review": {
                "npc_actions": [],
                "notes": "Bypassed for OOC DM note.",
            },
            "turn_context": None,
            "narrative_brief": None,
            "skill_check": {
                "needs_skill_check": False,
                "bypassed": True,
                "reason": "OOC DM note",
            },
            "skill_result": None,
            "turn_summary": "OOC note handled; story summary not updated.",
            "token_usage": self.api_manager.get_token_usage(),
            "updated_combat_state": self.combat.state if self.combat.state.get("active") else None,
            "map": get_current_map(self.combat.state) if self.combat.state.get("active") else None,
        }

    def _process_dm_override(self, player_input: str, override: Dict[str, str]) -> Dict[str, Any]:
        """Apply a direct player-authored DM override without running the story pipeline."""
        if override.get("error"):
            return self._ooc_bypass_result(
                player_input,
                override.get("error", ""),
                "(Override failed)",
                {"action": "dm_override", "command": {"error": override.get("error")}},
                False,
                override.get("error", "Override failed."),
            )
        scope = override.get("scope", "")
        fact = override.get("fact", "")
        target = override.get("target", "")
        result: Dict[str, Any]
        if scope == "scene":
            result = self._apply_scene_update({
                "action": "scene_update",
                "command": {"set_facts": {"local": {self._scene_fact_key(fact): fact}}},
            })
        elif scope == "world":
            result = self._apply_note_fact({
                "action": "note_fact",
                "command": {"fact": fact},
            })
        elif scope == "npc":
            if not target:
                result = {"success": False, "message": "NPC override requires a target name."}
            else:
                npc_id = (
                    self._resolve_npc_reference(target)
                    or self._ensure_npc_for_interaction(target, updates={"known_facts": [f"knowledge: {fact}"]})
                )
                if npc_id and npc_id in self.game_state.setdefault("npcs", {}):
                    self._append_npc_known_fact(self.game_state["npcs"][npc_id], f"knowledge: {fact}")
                    result = {"success": True, "message": "NPC override recorded.", "npc_id": npc_id, "fact": fact}
                else:
                    result = {"success": False, "message": f"Could not resolve NPC override target: {target}"}
        else:
            result = {"success": False, "message": f"Unknown override scope: {scope}"}

        success = bool(result.get("success"))
        if success:
            self._save_game_state()
        return self._ooc_bypass_result(
            player_input,
            fact,
            "(Override successful)" if success else "(Override failed)",
            {
                "action": "dm_override",
                "command": {
                    "scope": scope,
                    "target": target,
                    "fact": fact,
                },
            },
            success,
            result.get("message", "Override successful." if success else "Override failed."),
        )

    def _process_ooc_question(self, player_input: str, question: str) -> Dict[str, Any]:
        """Answer an OOC DM note without running the story-turn pipeline."""
        if self._ooc_note_looks_like_override_request(question):
            answer = self._suggest_dm_override_phrase(question)
            return self._ooc_bypass_result(
                player_input,
                question,
                answer,
                {
                    "action": "ooc_note",
                    "command": {"message": "Override syntax suggested; no game state change requested."},
                },
                True,
                "OOC override syntax suggested; mechanics, NPC review, narration commands, summary, and time advancement were bypassed.",
            )
        context = self._build_ooc_question_context(player_input, question)
        response = self.api_manager.call_api(
            "ooc_question",
            context,
            temperature=MODEL_OOC_QUESTION_TEMPERATURE,
            max_tokens=MODEL_OOC_QUESTION_MAX_TOKENS,
        )
        answer = self._normalize_ooc_answer(response, context)
        return self._ooc_bypass_result(
            player_input,
            question,
            answer,
            {
                "action": "ooc_note",
                "command": {"message": "Out-of-character question answered; no game state change requested."},
            },
            True,
            "OOC question answered; mechanics, NPC review, narration commands, summary, and time advancement were bypassed.",
        )
    
    def _compact_text(self, value: Any, max_chars: int = PROMPT_COMPACT_TEXT_CHARS) -> str:
        """Collapse whitespace and cap text for prompt budget control."""
        compact = " ".join(str(value or "").split())
        if len(compact) <= max_chars:
            return compact
        return compact[:max_chars - 3].rstrip() + "..."

    def _compact_text_preserve_ends(self, value: Any, max_chars: int = PROMPT_COMPACT_TEXT_CHARS) -> str:
        """Compact long text while preserving both setup and final outcome/dialogue."""
        compact = " ".join(str(value or "").split())
        if len(compact) <= max_chars:
            return compact
        if max_chars < 20:
            return self._compact_text(compact, max_chars)
        marker = " ... "
        head_chars = max(8, (max_chars - len(marker)) // 2)
        tail_chars = max(8, max_chars - len(marker) - head_chars)
        return f"{compact[:head_chars].rstrip()}{marker}{compact[-tail_chars:].lstrip()}"

    def _coerce_bool(self, value: Any, default: Any = False) -> Any:
        """Coerce common JSON/model truthy and falsey values without guessing on unknown text."""
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        normalized = self._normalize_key_text(value)
        if normalized in {"true", "yes", "y", "1", "on", "join", "joins", "joined", "member", "party", "with party", "in party"}:
            return True
        if normalized in {"false", "no", "n", "0", "off", "leave", "leaves", "left", "depart", "departs", "departed", "not member", "not in party"}:
            return False
        return default
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
    def _coerce_time_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default
    def _time_of_day_label(self, hour: int) -> str:
        hour = int(hour) % 24
        if 5 <= hour < 12:
            return "morning"
        if 12 <= hour < 17:
            return "afternoon"
        if 17 <= hour < 20:
            return "evening"
        return "night"
    def _world_time_context(self) -> Dict[str, Any]:
        """Return normalized saved world time for prompts and command handling."""
        time_data = self.game_state.get("world", {}).get("time", {})
        if not isinstance(time_data, dict):
            time_data = {}
        day = max(1, self._coerce_time_int(time_data.get("day"), 1))
        hour = self._coerce_time_int(time_data.get("hour"), 8) % 24
        minute = self._coerce_time_int(time_data.get("minute"), 0)
        hour = (hour + minute // 60) % 24
        minute = minute % 60
        return {
            "day": day,
            "hour": hour,
            "minute": minute,
            "season": str(time_data.get("season") or "spring"),
            "time_of_day": self._time_of_day_label(hour),
            "clock": f"Day {day}, {hour:02d}:{minute:02d}",
        }
    def _format_world_time_for_prompt(self) -> str:
        time_state = self._world_time_context()
        return (
            f"{time_state['clock']} ({time_state['time_of_day']}), "
            f"season: {time_state['season']}. This saved clock is authoritative."
        )
    def _world_location_context(self) -> Dict[str, Any]:
        """Return the saved player location without empty fields."""
        location = self.game_state.get("world", {}).get("location", {})
        if not isinstance(location, dict):
            return {}
        return {
            str(key): value
            for key, value in location.items()
            if value not in (None, "", [], {})
        }
    def _format_world_location_for_prompt(self) -> str:
        location = self._world_location_context()
        if not location:
            return "unknown. This saved location is authoritative when present."
        ordered_keys = (
            "settlement",
            "site",
            "area",
            "district",
            "building",
            "room",
            "region",
            "coordinates",
        )
        used = set()
        parts = []
        for key in ordered_keys:
            if key in location:
                parts.append(f"{key}: {location[key]}")
                used.add(key)
        for key, value in location.items():
            if key not in used:
                parts.append(f"{key}: {value}")
        return "; ".join(parts) + ". This saved location is authoritative."
    def _time_fact_conflicts_with_world_time(self, fact: str) -> bool:
        """Drop stale time-of-day facts from prompt packets when the saved clock disagrees."""
        text = self._normalize_key_text(fact)
        if not text:
            return False
        label = self._world_time_context().get("time_of_day", "")
        morning_conflicts = [
            "night", "nightfall", "dusk", "evening", "sunset", "moonlight",
            "fully dark", "growing darker", "approaching night",
        ]
        day_conflicts = [
            "night", "nightfall", "dusk", "sunset", "moonlight",
            "fully dark", "approaching night",
        ]
        night_conflicts = [
            "morning", "afternoon", "midday", "noon", "sunrise",
            "bright daylight", "full daylight",
        ]
        if label == "morning":
            return any(term in text for term in morning_conflicts)
        if label == "afternoon":
            return any(term in text for term in day_conflicts)
        if label == "night":
            return any(term in text for term in night_conflicts)
        return False
    def _compact_scene_fact_map_for_prompt(self, max_items: int, max_chars: int) -> Dict[str, Dict[str, str]]:
        """Return scoped keyed scene facts for prompt use."""
        memory = self._normalize_scene_facts()
        compacted = {"local": {}, "carryover": {}}
        max_items = max(1, int(max_items))
        local_items = list(memory.get("local", {}).items())
        carryover_items = list(memory.get("carryover", {}).items())
        carryover_limit = min(len(carryover_items), max(1, max_items // 3)) if carryover_items else 0
        local_limit = max_items - carryover_limit
        if local_items and local_limit <= 0:
            carryover_limit = 0
            local_limit = 1
        if not local_items:
            carryover_limit = max_items
        if not carryover_items:
            local_limit = max_items
        scope_limits = {"local": local_limit, "carryover": carryover_limit}
        for scope in ("local", "carryover"):
            limit = scope_limits.get(scope, 0)
            if limit <= 0:
                continue
            items = list(memory.get(scope, {}).items())[-limit:]
            for key, fact in items:
                text = self._compact_text(fact, max_chars)
                if text and not self._time_fact_conflicts_with_world_time(text):
                    compacted[scope][key] = text
        return {scope: facts for scope, facts in compacted.items() if facts}
    def _compact_scene_facts_for_prompt(self, max_items: int, max_chars: int) -> List[str]:
        fact_map = self._compact_scene_fact_map_for_prompt(max_items, max_chars)
        facts = []
        for scope in ("local", "carryover"):
            facts.extend(fact_map.get(scope, {}).values())
        return facts[:max_items]
    def _compact_recent_exchanges(self, limit: int = PROMPT_RECENT_EXCHANGE_LIMIT,
                                  max_player_chars: int = PROMPT_RECENT_PLAYER_CHARS,
                                  max_dm_chars: int = PROMPT_RECENT_DM_CHARS) -> List[Dict[str, str]]:
        """Return recent exchanges with bounded text for prompt use."""
        return [
            {
                "player": self._compact_text(exchange.get("player", ""), max_player_chars),
                "dm": self._compact_text_preserve_ends(exchange.get("dm", ""), max_dm_chars),
            }
            for exchange in self.conversation_manager.get_recent_exchanges(limit)
        ]

    def _transcript_retrieval_terms(self, player_input: str) -> List[Dict[str, Any]]:
        """Extract cheap local search terms from the player's latest input."""
        text = str(player_input or "")
        stopwords = {
            "about", "after", "again", "also", "been", "before", "being", "could", "does",
            "down", "from", "have", "into", "just", "know", "like", "look", "more", "note",
            "only", "over", "please", "should", "tell", "that", "their", "them", "then",
            "there", "they", "this", "what", "when", "where", "which", "while", "with",
            "would", "your", "you", "dm",
        }
        terms: List[Dict[str, Any]] = []
        seen = set()

        def add(term: str, weight: int, phrase: bool = False):
            clean = " ".join(str(term or "").split()).strip(".,!?;:()[]{}\"'")
            if len(clean) < 3:
                return
            key = clean.lower()
            if key in seen:
                return
            seen.add(key)
            terms.append({"term": clean, "weight": weight, "phrase": phrase})

        for quoted in re.findall(r"[\"“”]([^\"“”]{3,80})[\"“”]", text):
            add(quoted, 7, phrase=True)
        for proper in re.findall(r"\b[A-Z][A-Za-z'’-]{2,}\b", text):
            if proper.lower() not in stopwords:
                add(proper, 6)
        for word in re.findall(r"\b[a-zA-Z][a-zA-Z'’-]{3,}\b", text):
            lowered = word.lower()
            if lowered not in stopwords:
                add(lowered, 2)
            if len(terms) >= PROMPT_TRANSCRIPT_RETRIEVAL_TERM_LIMIT:
                break
        return terms[:PROMPT_TRANSCRIPT_RETRIEVAL_TERM_LIMIT]

    def _transcript_match_count(self, haystack: str, term: str, phrase: bool = False) -> int:
        """Count bounded case-insensitive transcript matches."""
        if not term:
            return 0
        if phrase or " " in term:
            return haystack.count(term.lower())
        pattern = re.compile(rf"\b{re.escape(term.lower())}\b")
        return len(pattern.findall(haystack))

    def _transcript_evidence_excerpt(self, entry: Dict[str, str], terms: List[Dict[str, Any]], max_chars: int) -> str:
        """Return a compact excerpt centered near the strongest matched term."""
        player = str(entry.get("player", "") or "")
        dm = str(entry.get("dm", "") or "")
        combined = f"Player: {player}\nDM: {dm}".strip()
        lowered = combined.lower()
        match_index = -1
        for term_info in sorted(terms, key=lambda item: item.get("weight", 0), reverse=True):
            needle = str(term_info.get("term", "")).lower()
            if not needle:
                continue
            match_index = lowered.find(needle)
            if match_index >= 0:
                break
        if match_index < 0 or len(combined) <= max_chars:
            return self._compact_text_preserve_ends(combined, max_chars)
        half = max(40, max_chars // 2)
        start = max(0, match_index - half)
        end = min(len(combined), start + max_chars)
        if end - start < max_chars:
            start = max(0, end - max_chars)
        excerpt = combined[start:end].strip()
        if start > 0:
            excerpt = "..." + excerpt
        if end < len(combined):
            excerpt = excerpt.rstrip() + "..."
        return excerpt

    def _retrieve_relevant_transcript_evidence(self, player_input: str,
                                               max_snippets: int = PROMPT_TRANSCRIPT_RETRIEVAL_MAX_SNIPPETS,
                                               max_chars: int = PROMPT_TRANSCRIPT_RETRIEVAL_MAX_CHARS) -> List[Dict[str, Any]]:
        """Local transcript search used as a low-cost continuity aid for prompts."""
        if max_snippets <= 0:
            return []
        terms = self._transcript_retrieval_terms(player_input)
        if not terms:
            return []
        entries = self.conversation_manager.get_transcript_entries(PROMPT_TRANSCRIPT_RETRIEVAL_MAX_TURNS)
        scored: List[Tuple[float, int, Dict[str, str], List[str]]] = []
        for index, entry in enumerate(entries):
            combined = f"{entry.get('player', '')}\n{entry.get('dm', '')}".lower()
            score = 0.0
            matched_terms: List[str] = []
            for term_info in terms:
                term = str(term_info.get("term", ""))
                count = self._transcript_match_count(combined, term, bool(term_info.get("phrase")))
                if count <= 0:
                    continue
                score += min(count, 3) * float(term_info.get("weight", 1))
                matched_terms.append(term)
            if score <= 0:
                continue
            recency_bonus = (index + 1) / max(1, len(entries)) * 0.5
            scored.append((score + recency_bonus, index, entry, matched_terms[:5]))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        evidence = []
        for score, _index, entry, matched_terms in scored[:max_snippets]:
            evidence.append({
                "turn": entry.get("turn", ""),
                "matched_terms": matched_terms,
                "excerpt": self._transcript_evidence_excerpt(entry, terms, max_chars),
            })
        return evidence

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
            "currency": currency_snapshot(player if isinstance(player, dict) else {}),
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
    def _roll_margin_band(self, success: Any, margin: Any) -> str:
        """Classify a resolved roll margin for narration pressure."""
        is_success = bool(success)
        try:
            numeric_margin = float(margin)
        except (TypeError, ValueError):
            return "success" if is_success else "failure"
        if is_success:
            if numeric_margin >= 20:
                return "exceptional_success"
            if numeric_margin >= 10:
                return "strong_success"
            if numeric_margin >= 5:
                return "clean_success"
            return "narrow_success"
        if numeric_margin <= -20:
            return "severe_failure"
        if numeric_margin <= -10:
            return "clear_failure"
        return "narrow_failure"
    def _roll_outcome_contract(self, roll_label: str, success: Any, margin: Any,
                               goal: Any = "", stakes: Any = "") -> Dict[str, Any]:
        """Build generic must-obey narration rules for any precomputed roll."""
        is_success = bool(success)
        band = self._roll_margin_band(is_success, margin)
        compact_goal = self._compact_text(goal, 180)
        compact_stakes = self._compact_text(stakes, 180)
        if is_success:
            required = (
                f"{roll_label} succeeds. Narrate the declared goal as achieved, "
                "with the margin controlling how clean or costly the success feels."
            )
            forbidden = [
                "Do not narrate the declared goal as failed.",
                "Do not add a new failure, loss, or blocked progress that contradicts the successful roll.",
            ]
            if band == "narrow_success":
                required += " Because the margin is narrow, success may be tense, noisy, slow, or costly, but it remains a success."
        else:
            required = (
                f"{roll_label} fails. Narrate a concrete setback, complication, cost, lost opportunity, "
                "or worsened position tied to the attempted goal."
            )
            forbidden = [
                "Do not narrate the declared goal as cleanly achieved.",
                "Do not describe the obstacle as avoided unless the failure creates an equal or worse complication.",
                "Do not soften the failure into 'it worked for now' without a concrete negative consequence.",
            ]
            if band == "narrow_failure":
                required += " Because the margin is narrow, the setback can be limited, partial, or delayed, but it must still matter."
        if compact_goal:
            required += f" Attempted goal: {compact_goal}"
        if compact_stakes:
            required += f" Stakes to honor: {compact_stakes}"
        return {
            "outcome_lock": "This roll is already resolved. Do not reroll, reverse, ignore, or soften it into the opposite outcome.",
            "margin_band": band,
            "required_narrative_effect": required,
            "forbidden_outcomes": forbidden,
        }
    def _compact_social_check_for_prompt(self, social_check: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Compact a social check decision."""
        if not isinstance(social_check, dict) or not social_check.get("needs_social_check"):
            return {"needs_social_check": False}
        return {
            "needs_social_check": True,
            "target_npc": social_check.get("target_npc"),
            "interaction_type": social_check.get("interaction_type"),
            "base_difficulty_class": social_check.get("base_difficulty_class"),
            "difficulty_class": social_check.get("difficulty_class"),
            "trust_modifier": social_check.get("trust_modifier"),
            "reason": self._compact_text(social_check.get("reason", ""), 160),
        }
    def _compact_social_result_for_prompt(self, social_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Compact resolved social mechanics and NPC reaction."""
        if not isinstance(social_result, dict) or not social_result:
            return {}
        result = social_result.get("social_result") if isinstance(social_result.get("social_result"), dict) else {}
        reaction = social_result.get("npc_reaction") if isinstance(social_result.get("npc_reaction"), dict) else {}
        compact = {
            "success": result.get("success"),
            "roll": result.get("roll"),
            "difficulty_class": result.get("difficulty_class") or result.get("dc"),
            "margin": result.get("margin"),
            "trust_change": result.get("trust_change"),
            "relationship": result.get("new_relationship"),
            "trust_category": result.get("trust_category"),
            "mood": result.get("new_mood_score") if result.get("new_mood_score") is not None else result.get("mood"),
            "mood_label": result.get("mood_label") or result.get("emotional_response"),
            "mood_delta": result.get("mood_delta"),
            "old_mood_score": result.get("old_mood_score"),
            "new_mood_score": result.get("new_mood_score"),
        }
        dialogue = self._compact_text(reaction.get("dialogue", ""), 180)
        body_language = self._compact_text(reaction.get("body_language", ""), 120)
        if dialogue or body_language:
            compact["reaction"] = {
                "dialogue": dialogue,
                "body_language": body_language,
            }
        return compact
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
            npc_id = action.get("npc_id")
            public_name = action.get("name")
            if npc_id and isinstance(self.game_state.get("npcs", {}), dict):
                npc = self.game_state.get("npcs", {}).get(str(npc_id))
                if isinstance(npc, dict):
                    public_name = self._npc_public_reference_label(str(npc_id), npc)
            actions.append({
                "npc_id": npc_id,
                "name": public_name,
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

    def _load_story_bible_json(self) -> Dict[str, Any]:
        """Load the structured story bible, when available."""
        paths = [
            path_config.story_bible_path,
            path_config.references_dir / "Story_bible.json",
            path_config.references_dir / "story_bible.json",
        ]
        seen = set()
        for path in paths:
            if not path or path in seen:
                continue
            seen.add(path)
            if path.suffix.lower() != ".json" or not path.exists():
                continue
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                return loaded if isinstance(loaded, dict) else {}
            except Exception as e:
                logger.error(f"Failed to load structured story bible: {e}")
        return {}

    def _story_bible_json_entries(self) -> List[Dict[str, str]]:
        """Flatten structured story-bible facts into individually selectable entries."""
        bible = self._load_story_bible_json()
        entries: List[Dict[str, str]] = []

        def walk(node: Any, path: List[str]):
            if isinstance(node, dict):
                for key, child in node.items():
                    walk(child, path + [str(key)])
                return
            if isinstance(node, list):
                if all(not isinstance(item, (dict, list)) for item in node):
                    text = ", ".join(str(item).strip() for item in node if str(item).strip())
                    if text and path:
                        entries.append({
                            "key": ".".join(path),
                            "text": self._compact_text(text, 320),
                        })
                    return
                for index, child in enumerate(node, start=1):
                    walk(child, path + [str(index)])
                return
            text = str(node).strip()
            if text and path:
                entries.append({
                    "key": ".".join(path),
                    "text": self._compact_text(text, 320),
                })

        walk(bible, [])
        return entries

    def _story_bible_relevance_text(self, player_input: str,
                                    turn_context: Optional[Dict[str, Any]],
                                    scene_facts: Optional[List[str]]) -> str:
        """Build the relevance text used for deterministic story-bible lore selection."""
        parts: List[str] = [
            player_input or "",
            self._get_scene_context() or "",
            " ".join(scene_facts or []),
            " ".join(self.game_state.get("world", {}).get("facts", []) if isinstance(self.game_state.get("world", {}).get("facts", []), list) else []),
        ]
        involved = set()
        if isinstance(turn_context, dict):
            for field in ("relevant_lore_keys", "relevant_races", "continuity_constraints", "forbidden_assumptions", "mechanical_risks"):
                value = turn_context.get(field, [])
                if isinstance(value, list):
                    parts.append(" ".join(str(item) for item in value))
                elif value:
                    parts.append(str(value))
            parts.append(str(turn_context.get("likely_intent", "")))
            parts.append(str(turn_context.get("scene_focus", "")))
            involved = {str(npc_id) for npc_id in turn_context.get("involved_npcs", []) or []}
        npcs = self.game_state.get("npcs", {})
        if isinstance(npcs, dict):
            npc_items = (
                [(npc_id, npcs.get(npc_id)) for npc_id in involved if npc_id in npcs]
                if involved else []
            )
            for npc_id, npc in npc_items:
                if not isinstance(npc, dict):
                    continue
                identity = self._npc_identity(npc)
                parts.extend([
                    npc_id,
                    str(identity.get("background", "")),
                    str(identity.get("class_theme", "")),
                    " ".join(str(fact) for fact in identity.get("known_facts", []) if isinstance(identity.get("known_facts", []), list)),
                ])
        return self._normalize_key_text(" ".join(str(part) for part in parts if part))

    def _triggered_story_bible_topics(self, relevance_text: str,
                                      turn_context: Optional[Dict[str, Any]]) -> List[str]:
        """Return structured story-bible topics that should be considered this turn."""
        triggered: List[str] = []
        requested = []
        if isinstance(turn_context, dict):
            requested.extend(turn_context.get("relevant_lore_keys", []) or [])
            requested.extend(turn_context.get("relevant_races", []) or [])
        requested_text = self._normalize_key_text(" ".join(str(item) for item in requested))
        for topic, triggers in STORY_BIBLE_TOPIC_TRIGGERS.items():
            topic_key = self._normalize_key_text(topic)
            if topic_key and topic_key in requested_text and topic not in triggered:
                triggered.append(topic)
                continue
            if any(self._normalize_key_text(trigger) in relevance_text for trigger in triggers):
                if topic not in triggered:
                    triggered.append(topic)
        if "slavery_legal_and_common" in requested_text and "slavery" not in triggered:
            triggered.append("slavery")
        return triggered

    def _select_story_bible_lore(self, player_input: str,
                                 turn_context: Optional[Dict[str, Any]] = None,
                                 scene_facts: Optional[List[str]] = None,
                                 max_entries: int = 8) -> List[Dict[str, str]]:
        """Select mandatory structured story-bible facts relevant to this turn."""
        entries = self._story_bible_json_entries()
        if not entries:
            return []
        relevance_text = self._story_bible_relevance_text(player_input, turn_context, scene_facts)
        topics = self._triggered_story_bible_topics(relevance_text, turn_context)
        keywords = {
            word for word in re.findall(r"[a-z0-9_]{4,}", relevance_text)
            if word not in {"that", "with", "from", "this", "have", "they", "their", "will", "known"}
        }
        scored: List[Tuple[int, Dict[str, str]]] = []
        price_relevant = any(word in relevance_text for word in ("price", "prices", "cost", "market", "value", "sale", "buy", "sell"))
        for entry in entries:
            key = str(entry.get("key", ""))
            key_norm = self._normalize_key_text(key.replace(".", " "))
            text_norm = self._normalize_key_text(entry.get("text", ""))
            combined = f"{key_norm} {text_norm}"
            combined_tokens = set(re.findall(r"[a-z0-9_]{3,}", combined))
            score = sum(
                1 for keyword in keywords
                if keyword in combined_tokens or (len(keyword) > 8 and keyword in combined)
            )
            for topic in topics:
                topic_norm = self._normalize_key_text(topic.replace(".", " "))
                if key == topic or key.startswith(f"{topic}.") or topic_norm in key_norm:
                    score += 12
            if key.startswith("slavery.types.red_tattoo") and any(word in relevance_text for word in ("red", "slave mark", "mark", "tattoo")):
                score += 5
            if key.startswith("slavery.types.blue_tattoo") and "blue" not in relevance_text:
                score -= 5
            if key.startswith("slavery.") and any(word in relevance_text for word in ("command", "order", "orders", "refuse", "refusing", "hurt", "pain", "obey")):
                if ".mechanics_" in key or key.endswith("command_trigger_clarification"):
                    score += 10
            if key.startswith("slavery.prices") and not price_relevant:
                score -= 10
            if key.startswith("general_considerations.virginity_awareness") and not any(
                word in relevance_text for word in ("virgin", "market", "bargain", "female", "protection")
            ):
                score -= 8
            if score > 0:
                scored.append((score, entry))
        scored.sort(key=lambda item: (-item[0], item[1].get("key", "")))
        selected = []
        seen = set()
        for _, entry in scored:
            key = entry.get("key", "")
            if key in seen:
                continue
            selected.append({
                "source": "references/Story_bible.json",
                "key": key,
                "text": entry.get("text", ""),
            })
            seen.add(key)
            if len(selected) >= max_entries:
                break
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
    def _get_known_npcs_for_prompt(self, private: bool = False) -> List[Dict[str, Any]]:
        """Return active save-state NPCs, with private identity only when requested."""
        known = {}
        player = self.game_state.get("player", {})
        player_identity = player.get("identity") if isinstance(player, dict) and isinstance(player.get("identity"), dict) else {}
        player_name = self._normalize_key_text(player_identity.get("name") or (player.get("name") if isinstance(player, dict) else ""))
        player_key = self._make_npc_id_from_name(player_name) if player_name else ""
        for npc_id, npc in self.game_state.get("npcs", {}).items():
            if isinstance(npc, dict):
                display_name = self._get_npc_field(npc, "display_name", npc_id)
                known_name = self._get_npc_field(npc, "known_name", "unknown")
                reference_label = self._npc_public_reference_label(npc_id, npc)
                relationship_with_player = self._npc_relationship_with_player(npc)
                if player_name and (
                    self._normalize_key_text(display_name) == player_name
                    or self._normalize_key_text(npc_id) == self._normalize_key_text(player_key)
                ):
                    continue
                entry = {
                    "npc_id": npc_id,
                    "known_name": known_name if self._is_learned_npc_name(known_name, npc_id) else "unknown",
                    "reference_label": reference_label,
                    "gender": self._get_npc_field(npc, "gender", ""),
                    "age": self._get_npc_field(npc, "age", 0),
                    "race": self._get_npc_field(npc, "race", ""),
                    "background": self._npc_public_text(npc_id, npc, self._get_npc_field(npc, "background", ""), 180),
                    "class_theme": self._npc_public_text(npc_id, npc, self._get_npc_field(npc, "class_theme", ""), 120),
                    "party": self._get_npc_field(npc, "party", False),
                    "relationship_with_player": relationship_with_player,
                    "player_relationship": relationship_with_player.get("public_label", "Stranger"),
                    "known_facts": self._npc_public_facts(npc_id, npc, self._get_npc_field(npc, "known_facts", []), 5, 140),
                }
                if private:
                    personality = self._get_npc_field(npc, "personality", {})
                    if not isinstance(personality, dict):
                        personality = {}
                    voice_profile = self._get_npc_field(npc, "voice_profile", {})
                    if not isinstance(voice_profile, dict):
                        voice_profile = {}
                    trust_value = self._get_npc_field(npc, "trust", 0)
                    trust_data = get_relationship_data(trust_value)
                    mood_score = self._get_npc_field(npc, "mood", 0)
                    mood_data = get_mood_band(mood_score)
                    entry.update({
                        "display_name": display_name,
                        "role": self._get_npc_field(npc, "title", ""),
                        "relationship": relationship_with_player.get("public_label", "Stranger"),
                        "relationship_with_player": relationship_with_player,
                        "trust": trust_value,
                        "trust_label": self._get_npc_field(npc, "trust_label", "neutral"),
                        "trust_category": trust_data.get("category", "neutral"),
                        "trust_description": self._compact_text(trust_data.get("description", ""), 120),
                        "mood": mood_score,
                        "mood_label": get_mood_label(mood_score),
                        "mood_description": self._compact_text(mood_data.get("description", ""), 120),
                        "background": self._compact_text(self._get_npc_field(npc, "background", ""), 180),
                        "class_theme": self._compact_text(self._get_npc_field(npc, "class_theme", ""), 120),
                        "known_facts": self._compact_list_text(self._get_npc_field(npc, "known_facts", []), 5, 140),
                    })
                    entry["personality"] = {
                        "core_trait": personality.get("core_trait", ""),
                        "social_trait": personality.get("social_trait", ""),
                        "attitude": personality.get("attitude", ""),
                        "motivations": personality.get("motivations", ""),
                        "fears": personality.get("fears", ""),
                        "boundaries": self._compact_list_text(personality.get("boundaries", []), 2, 100),
                    }
                    entry["voice_profile"] = {
                        "core_personality": self._compact_text(voice_profile.get("core_personality", ""), 180),
                        "speech_style": voice_profile.get("speech_style", ""),
                        "register": voice_profile.get("register", ""),
                        "pace": voice_profile.get("pace", ""),
                        "quirks": self._compact_list_text(voice_profile.get("quirks", []), 3, 100),
                        "example_dialogue": self._compact_list_text(voice_profile.get("example_dialogue", []), 3, 120),
                        "forbidden": self._compact_list_text(voice_profile.get("forbidden", []), 4, 80),
                    }
                known[npc_id] = entry
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
            name = self._npc_public_reference_label(npc_id, npc)
            aliases = npc.get("aliases", []) if isinstance(npc.get("aliases"), list) else []
            identifiers = [npc_id, name, self._get_npc_field(npc, "known_name", ""), self._get_npc_field(npc, "title", "")]
            identifiers.extend(aliases)
            mentioned = str(npc_id) in involved or any(
                ident and self._normalize_key_text(ident) in info_text
                for ident in identifiers
            )
            if not mentioned:
                continue
            facts = self._get_npc_field(npc, "known_facts", [])
            trust_value = self._get_npc_field(npc, "trust", 0)
            trust_data = get_relationship_data(trust_value)
            mood_score = self._get_npc_field(npc, "mood", 0)
            relationship_with_player = self._npc_relationship_with_player(npc)
            relevant.append({
                "npc_id": npc_id,
                "name": name,
                "race": self._get_npc_field(npc, "race", ""),
                "relationship_with_player": relationship_with_player,
                "player_relationship": relationship_with_player.get("public_label", "Stranger"),
                "trust_label": self._get_npc_field(npc, "trust_label", "neutral"),
                "trust": trust_value,
                "trust_category": trust_data.get("category", "neutral"),
                "mood": mood_score,
                "mood_label": get_mood_label(mood_score),
                "known_facts": self._compact_list_text(facts, 8, 220),
            })
        return relevant[:5]
    def _build_dc_evaluation_context(self, player_input: str, skill_detection: Dict[str, Any],
                                     context: Dict[str, Any], suggested_base: int) -> Dict[str, Any]:
        """Build the intentionally narrow fact packet for DC adjudication."""
        last_exchange = self.conversation_manager.get_last_exchange()
        return {
            "current_player_input": player_input,
            "last_interaction": {
                "player_input": self._compact_text(last_exchange.get("player", ""), PROMPT_RECENT_PLAYER_CHARS),
                "dm_narrative": self._compact_text(last_exchange.get("dm", ""), PROMPT_RECENT_DM_CHARS),
            },
            "proposed_check": {
                "skill": skill_detection.get("skill", ""),
                "stats_used": skill_detection.get("stats_used", []),
                "base_dc": suggested_base,
                "task_goal": self._compact_text(skill_detection.get("reason", ""), 220),
                "stakes": self._compact_text(skill_detection.get("stakes", ""), 220),
            },
            "skill_reference": self._skill_dc_full_entry(skill_detection.get("skill", "")),
            "known_facts": {
                "world_time": context.get("world_time") or self._world_time_context(),
                "scene": context.get("scene_facts", []),
                "world": context.get("world_facts", []),
                "player": self._player_known_facts_for_dc(),
                "npcs": self._relevant_npc_known_facts_for_dc(player_input, skill_detection, context),
            },
        }
    def _resolve_detected_npc_id(self, target: str, known_npcs: List[Dict[str, Any]]) -> Optional[str]:
        """Map detector target text to a known NPC id."""
        return self._resolve_npc_reference(target, known_npcs)

    def _resolve_social_candidate_npc(self, player_input: str, context: Dict[str, Any],
                                      turn_context: Optional[Dict[str, Any]] = None,
                                      inferred: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Resolve the single NPC most likely involved in this turn, before deciding social intent."""
        known_npcs = context.get("known_npcs", []) if isinstance(context.get("known_npcs"), list) else []
        candidates: List[str] = []

        def add_candidate(ref: Any):
            resolved = self._resolve_detected_npc_id(str(ref or ""), known_npcs)
            if resolved and resolved not in candidates:
                candidates.append(resolved)

        inferred = inferred or {}
        add_candidate(inferred.get("target_npc") or inferred.get("npc_id"))

        compact_turn_context = context.get("turn_context", {}) if isinstance(context.get("turn_context"), dict) else {}
        active_turn_context = turn_context if isinstance(turn_context, dict) else compact_turn_context
        involved_refs = active_turn_context.get("involved_npcs", [])
        if not isinstance(involved_refs, list):
            involved_refs = []
        for ref in involved_refs:
            add_candidate(ref)

        lowered_input = self._normalize_key_text(player_input)
        for npc in known_npcs:
            names = [
                npc.get("npc_id", ""),
                npc.get("known_name", ""),
                npc.get("reference_label", ""),
                npc.get("name", ""),
                npc.get("display_name", ""),
            ]
            for name in names:
                name_key = self._normalize_key_text(name)
                if name_key and name_key != "unknown" and name_key in lowered_input:
                    add_candidate(npc.get("npc_id", ""))

        return candidates[0] if len(candidates) == 1 else None
    def _npc_trust_value(self, npc_id: str) -> float:
        """Return the current player-facing trust value for an NPC."""
        npc = self.game_state.get("npcs", {}).get(npc_id, {})
        if not isinstance(npc, dict):
            return 0.0
        identity = npc.get("identity") if isinstance(npc.get("identity"), dict) else {}
        player_rel = identity.get("relationships", {}).get("player", {}) if isinstance(identity.get("relationships"), dict) else {}
        if "trust" in identity:
            trust_value = identity.get("trust")
        elif "trust" in npc:
            trust_value = npc.get("trust")
        elif isinstance(player_rel, dict):
            trust_value = player_rel.get("trust", 0)
        else:
            trust_value = 0
        try:
            return float(trust_value)
        except (TypeError, ValueError):
            return 0.0
    def _build_turn_evaluation_context(self, player_input: str) -> Dict[str, Any]:
        """Context used by pre-DM evaluation prompts."""
        scene_facts = self._compact_scene_facts_for_prompt(12, 220)
        return {
            "knowledge_priority": self._knowledge_priority_context(),
            "player_input": player_input,
            "summary_file": self._compact_text(self.conversation_manager.get_summary_file_text(), PROMPT_COMPACT_TEXT_CHARS),
            "last_4_exchanges": self._compact_recent_exchanges(PROMPT_RECENT_EXCHANGE_LIMIT),
            "relevant_transcript_evidence": self._retrieve_relevant_transcript_evidence(player_input),
            "opening_scene": self._opening_scene_context(),
            "current_scene": self._compact_text(self._get_scene_context(), PROMPT_SCENE_CONTEXT_CHARS),
            "world_time": self._world_time_context(),
            "scene_facts": scene_facts,
            "world_facts": self._compact_list_text(self.game_state.get("world", {}).get("facts", []), 8, 220),
            "known_npcs": self._get_known_npcs_for_prompt(),
            "location": self.game_state.get("world", {}).get("location", {}),
            "player": self._compact_player_for_prompt(),
            "player_possessions": self._compact_player_possessions_for_prompt(),
            "story_bible_excerpt": self._story_bible_excerpt(player_input, max_chars=PROMPT_STORY_BIBLE_CHARS),
            "story_bible_lore": self._select_story_bible_lore(player_input, scene_facts=scene_facts),
            "racial_profiles": self._select_racial_profiles(),
        }
    def _skill_dc_reference_for_prompt(self) -> List[Dict[str, Any]]:
        """Load the combined skill/DC reference for model-side skill adjudication."""
        if self._skill_dc_reference_cache is not None:
            return copy.deepcopy(self._skill_dc_reference_cache)
        try:
            with open(path_config.skill_dc_reference_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load skill/DC reference: {e}")
            self._skill_dc_reference_cache = []
            return []
        rows = loaded.get("skills", []) if isinstance(loaded, dict) else loaded
        if not isinstance(rows, list):
            rows = []
        reference: List[Dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            skill_name = self._normalize_key_text(row.get("skill_name", ""))
            if not skill_name:
                continue
            raw_stats = row.get("stats_used", [])
            if isinstance(raw_stats, str):
                raw_stats = raw_stats.replace('"', "").split(",")
            stats_used = [str(stat).strip().title() for stat in raw_stats if str(stat).strip()][:3]
            raw_examples = row.get("dc_examples", {})
            examples: Dict[str, str] = {}
            if isinstance(raw_examples, dict):
                sorted_examples = sorted(
                    raw_examples.items(),
                    key=lambda item: self._coerce_dc_int(item[0], 0),
                )
                examples = {
                    str(self._coerce_dc_int(dc, 0)): self._compact_text(text, PROMPT_COMPACT_LIST_CHARS)
                    for dc, text in sorted_examples
                    if self._coerce_dc_int(dc, 0) > 0
                }
            reference.append({
                "skill_name": skill_name,
                "skill_description": self._compact_text(row.get("skill_description", ""), PROMPT_COMPACT_LIST_CHARS),
                "stats_used": stats_used,
                "dc_examples": examples,
            })
        self._skill_dc_reference_cache = reference
        return copy.deepcopy(reference)
    def _skill_dc_reference_map(self) -> Dict[str, Dict[str, Any]]:
        """Return combined skill/DC reference entries keyed by normalized skill name."""
        return {entry["skill_name"]: entry for entry in self._skill_dc_reference_for_prompt()}
    def _social_dc_reference_for_prompt(self) -> Dict[str, Any]:
        """Return the social_check reference entry for model-side social DC adjudication."""
        reference = copy.deepcopy(self._skill_dc_reference_map().get("social_check", {}))
        reference["trust_reference"] = load_trust_reference()
        return reference
    def _skill_dc_full_entry(self, skill_name: Any) -> Dict[str, Any]:
        """Return the full skills_with_dc.json entry for the selected skill."""
        normalized = self._normalize_detected_skill_name(skill_name)
        try:
            with open(path_config.skill_dc_reference_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load full skill/DC entry: {e}")
            return copy.deepcopy(self._skill_dc_reference_map().get(normalized, {}))
        rows = loaded.get("skills", []) if isinstance(loaded, dict) else loaded
        if not isinstance(rows, list):
            return {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            if self._normalize_key_text(row.get("skill_name", "")) == normalized:
                return copy.deepcopy(row)
        return copy.deepcopy(self._skill_dc_reference_map().get(normalized, {}))
    def _normalize_detected_skill_name(self, skill_name: Any) -> str:
        """Normalize model skill output to the combined skill/DC reference key when possible."""
        normalized = self._normalize_key_text(skill_name)
        aliases = {
            "melee weapons": "melee weapons",
            "ranged weapons": "ranged weapons",
            "spellcasting": "spellcasting",
            "social": "communication",
            "crafting": "smithing",
            "survival": "survival",
            "slight of hand": "sleight of hand",
            "sleight of hand": "sleight of hand",
        }
        normalized = aliases.get(normalized, normalized)
        reference = self._skill_dc_reference_map()
        return normalized if normalized in reference else normalized
    def _skill_reference_stats(self, skill_name: str) -> List[str]:
        """Return authoritative stat sources for a selected skill."""
        entry = self._skill_dc_reference_map().get(self._normalize_detected_skill_name(skill_name), {})
        stats = entry.get("stats_used", []) if isinstance(entry, dict) else []
        return [str(stat).strip().title() for stat in stats if str(stat).strip()][:3]
    def _build_shared_story_context(self, player_input: str,
                                    turn_context: Optional[Dict[str, Any]] = None,
                                    narrative_brief: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Story continuity packet shared by DM and NPC-facing prompts."""
        scene_facts = self._compact_scene_facts_for_prompt(12, 220)
        world_facts = self._compact_list_text(
            self.game_state.get("world", {}).get("facts", []),
            8,
            220,
        )
        return {
            "knowledge_priority": self._knowledge_priority_context(),
            "campaign_summary": self._compact_text(self.conversation_manager.get_summary_file_text(), PROMPT_COMPACT_TEXT_CHARS),
            "recent_exchanges": self._compact_recent_exchanges(PROMPT_RECENT_EXCHANGE_LIMIT),
            "relevant_transcript_evidence": self._retrieve_relevant_transcript_evidence(player_input),
            "opening_scene": self._opening_scene_context(),
            "current_scene": self._compact_text(self._get_scene_context(), PROMPT_SCENE_CONTEXT_CHARS),
            "scene_brief": self._compact_text((narrative_brief or {}).get("scene_brief", ""), PROMPT_SCENE_BRIEF_CHARS),
            "world_time": self._world_time_context(),
            "scene_facts": scene_facts,
            "world_facts": world_facts,
            "known_npcs": self._get_known_npcs_for_prompt(),
            "location": self.game_state.get("world", {}).get("location", {}),
            "player": self._compact_player_for_prompt(),
            "player_possessions": self._compact_player_possessions_for_prompt(),
            "turn_context": self._compact_turn_context_for_prompt(turn_context),
            "relevant_lore": self._select_dm_lore_profiles(player_input, turn_context, scene_facts),
            "full_story_bible": self._load_story_bible_json(),
            "story_bible_lore": self._select_story_bible_lore(player_input, turn_context, scene_facts),
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
    def _coerce_dc_int(self, value: Any, default: int = DEFAULT_UNEVALUATED_DC) -> int:
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
        suggested_base = self._coerce_dc_int(
            skill_detection.get("difficulty_class", DEFAULT_UNEVALUATED_DC),
            DEFAULT_UNEVALUATED_DC,
        )
        dc_context = self._build_dc_evaluation_context(player_input, skill_detection, context, suggested_base)
        raw_evaluation = self.api_manager.call_api(
            "dc_evaluation",
            dc_context,
            temperature=MODEL_DC_EVALUATION_TEMPERATURE,
            max_tokens=MODEL_DC_EVALUATION_MAX_TOKENS,
        )
        if not isinstance(raw_evaluation, dict):
            raw_evaluation = {}
        base_dc = max(1, min(100, suggested_base))
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
        context["social_dc_reference"] = self._social_dc_reference_for_prompt()
        if turn_context:
            context["turn_context"] = self._compact_turn_context_for_prompt(turn_context)
            context["racial_profiles"] = self._select_racial_profiles(turn_context)
            context["story_bible_excerpt"] = self._story_bible_excerpt(
                player_input,
                turn_context,
                max_chars=PROMPT_RUNTIME_STORY_BIBLE_CHARS,
            )
        inferred = self.api_manager._infer_social_check(context)
        candidate_target = self._resolve_social_candidate_npc(
            player_input,
            context,
            turn_context=turn_context,
            inferred=inferred,
        )
        social_words = [
            "talk", "speak", "say", "ask", "tell", "convince", "persuade",
            "intimidate", "threaten", "bargain", "negotiate", "lie", "deceive",
            "gift", "offer", "plead", "apologize", "flatter", "demand",
            "whisper", "promise", "request", "beg", "comfort", "reassure",
            "help", "trust", "calm", "explain", "warn", "thank"
        ]
        if (
            not candidate_target
            and not inferred.get("needs_social_check")
            and not any(word in player_input.lower() for word in social_words)
        ):
            return {
                "needs_social_check": False,
                "target_npc": None,
                "candidate_target_npc": None,
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
        target = detection.get("target_npc") or detection.get("npc_id") or candidate_target or ""
        resolved_target = self._resolve_detected_npc_id(target, known_npcs)
        needs_check = bool(detection.get("needs_social_check", False)) and bool(resolved_target)
        if not needs_check:
            inferred_target = inferred.get("target_npc") or inferred.get("npc_id") or ""
            inferred_resolved = self._resolve_detected_npc_id(inferred_target, known_npcs)
            if inferred.get("needs_social_check") and inferred_resolved:
                detection = inferred
                resolved_target = inferred_resolved
                needs_check = True
        base_dc = 0
        trust = 0.0
        difficulty_class = 0
        if needs_check:
            base_dc = self._coerce_dc_int(
                detection.get("difficulty_class"),
                DEFAULT_UNEVALUATED_DC,
            )
            base_dc = max(1, min(100, base_dc))
            trust = self._npc_trust_value(resolved_target)
            difficulty_class = max(1, min(100, int(round(base_dc - trust))))
        return {
            "needs_social_check": needs_check,
            "target_npc": resolved_target,
            "candidate_target_npc": candidate_target,
            "interaction_type": detection.get("interaction_type", "appeal"),
            "base_difficulty_class": base_dc,
            "difficulty_class": difficulty_class,
            "trust_modifier": -trust if needs_check else 0,
            "reason": detection.get("reason", "No social check needed" if not needs_check else ""),
            "raw_detection": detection,
        }
    def _communication_skill_reroute(self, detection: Dict[str, Any], social_check: Optional[Dict[str, Any]],
                                     context: Dict[str, Any], turn_context: Optional[Dict[str, Any]],
                                     player_input: str) -> Optional[Dict[str, Any]]:
        """Convert NPC-facing communication skill detections into social checks."""
        social_check = social_check or {}
        target = (
            social_check.get("target_npc")
            or social_check.get("candidate_target_npc")
            or self._resolve_social_candidate_npc(
                player_input,
                context,
                turn_context=turn_context,
                inferred=social_check.get("raw_detection") if isinstance(social_check.get("raw_detection"), dict) else None,
            )
        )
        if not target:
            return None
        base_dc = self._coerce_dc_int(
            detection.get("difficulty_class"),
            social_check.get("base_difficulty_class") or DEFAULT_UNEVALUATED_DC,
        )
        base_dc = max(1, min(100, base_dc))
        trust = self._npc_trust_value(target)
        return {
            "needs_social_check": True,
            "target_npc": target,
            "candidate_target_npc": target,
            "interaction_type": social_check.get("interaction_type", "appeal"),
            "base_difficulty_class": base_dc,
            "difficulty_class": max(1, min(100, int(round(base_dc - trust)))),
            "trust_modifier": -trust,
            "reason": detection.get("reason") or "NPC-facing communication is handled by social_calc.",
            "raw_detection": {
                "source": "communication_skill_reroute",
                "original_skill_detection": detection,
                "prior_social_detection": social_check,
            },
        }
    def _communication_fallback_for_unresolved_social(self, player_input: str, context: Dict[str, Any],
                                                      social_check: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Use a normal communication roll when social intent has no valid tracked NPC target."""
        if not isinstance(social_check, dict):
            return None
        raw_detection = social_check.get("raw_detection")
        if not isinstance(raw_detection, dict) or not raw_detection.get("needs_social_check"):
            return None
        if social_check.get("target_npc") or social_check.get("candidate_target_npc"):
            return None
        unresolved_target = raw_detection.get("target_npc") or raw_detection.get("npc_id") or ""
        base_dc = self._coerce_dc_int(
            raw_detection.get("difficulty_class") or social_check.get("base_difficulty_class"),
            DEFAULT_UNEVALUATED_DC,
        )
        base_dc = max(1, min(100, base_dc))
        stats_used = self._skill_reference_stats("communication") or ["Crea", "Ins"]
        reason = (
            social_check.get("reason")
            or raw_detection.get("reason")
            or "Social pressure has no valid tracked NPC target, so it falls back to communication."
        )
        if unresolved_target:
            reason = f"{reason} Unresolved target: {self._compact_text(unresolved_target, 80)}."
        provisional_detection = {
            "needs_skill_check": True,
            "skill": "communication",
            "stats_used": stats_used,
            "difficulty_class": base_dc,
            "reason": reason,
            "stakes": "The addressed person or surrounding audience may accept, resist, escalate, or impose a cost.",
        }
        dc_evaluation = self._evaluate_dc(player_input, provisional_detection, context)
        dc = dc_evaluation.get("final_dc", base_dc)
        return {
            **provisional_detection,
            "difficulty_class": max(1, min(100, dc)),
            "dc_evaluation": dc_evaluation,
            "raw_detection": {
                "source": "unresolved_social_target_communication_fallback",
                "prior_social_detection": social_check,
            },
        }
    def _detect_skill_check(self, player_input: str,
                            turn_context: Optional[Dict[str, Any]] = None,
                            social_check: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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
        context["skill_dc_reference"] = self._skill_dc_reference_for_prompt()
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
        if not needs_check:
            fallback = self._communication_fallback_for_unresolved_social(player_input, context, social_check)
            if fallback:
                return fallback
        skill_name = self._normalize_detected_skill_name(detection.get("skill", ""))
        stats_used = detection.get("stats_used") or []
        if isinstance(stats_used, str):
            stats_used = [stats_used]
        stats_used = [str(stat).strip().title() for stat in stats_used if str(stat).strip()][:3]
        reference_stats = self._skill_reference_stats(skill_name)
        if needs_check and reference_stats:
            stats_used = reference_stats
        if needs_check and not stats_used:
            detection = self.api_manager._infer_skill_check(context)
            needs_check = bool(detection.get("needs_skill_check", False))
            skill_name = self._normalize_detected_skill_name(detection.get("skill", ""))
            stats_used = detection.get("stats_used") or []
            if isinstance(stats_used, str):
                stats_used = [stats_used]
            stats_used = [str(stat).strip().title() for stat in stats_used if str(stat).strip()][:3]
            reference_stats = self._skill_reference_stats(skill_name)
            if reference_stats:
                stats_used = reference_stats
        dc = detection.get("difficulty_class", DEFAULT_UNEVALUATED_DC if needs_check else 0)
        try:
            dc = int(float(dc))
        except (TypeError, ValueError):
            dc = DEFAULT_UNEVALUATED_DC if needs_check else 0
        if needs_check and skill_name == "communication":
            rerouted_social_check = self._communication_skill_reroute(
                detection,
                social_check,
                context,
                turn_context,
                player_input,
            )
            if rerouted_social_check:
                return {
                    "needs_skill_check": False,
                    "skill": skill_name,
                    "stats_used": stats_used,
                    "difficulty_class": 0,
                    "reason": "NPC-facing communication is routed to social_calc.",
                    "stakes": detection.get("stakes", ""),
                    "dc_evaluation": {},
                    "raw_detection": detection,
                    "reroute_to_social_check": rerouted_social_check,
                }
        dc_evaluation = {}
        if needs_check:
            dc = max(1, min(100, dc))
            provisional_detection = {
                "needs_skill_check": needs_check and bool(stats_used),
                "skill": skill_name,
                "stats_used": stats_used,
                "difficulty_class": max(1, min(100, dc)),
                "reason": detection.get("reason", ""),
                "stakes": detection.get("stakes", ""),
            }
            dc_evaluation = self._evaluate_dc(player_input, provisional_detection, context)
            dc = dc_evaluation.get("final_dc", dc)
        return {
            "needs_skill_check": needs_check and bool(stats_used),
            "skill": skill_name,
            "stats_used": stats_used,
            "difficulty_class": max(1, min(100, dc)) if needs_check else 0,
            "reason": detection.get("reason", "No skill check needed" if not needs_check else ""),
            "stakes": detection.get("stakes", ""),
            "dc_evaluation": dc_evaluation,
            "raw_detection": detection,
        }
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
                "margin": social_mechanics.get("margin"),
                "trust_change": social_mechanics.get("trust_change"),
                "relationship": social_mechanics.get("new_relationship"),
                "trust_category": social_mechanics.get("trust_category"),
                "mood": social_mechanics.get("new_mood_score") if social_mechanics.get("new_mood_score") is not None else social_mechanics.get("mood"),
                "mood_label": social_mechanics.get("mood_label") or social_mechanics.get("emotional_response"),
                "mood_delta": social_mechanics.get("mood_delta"),
                "new_mood_score": social_mechanics.get("new_mood_score"),
            }
            if social_mechanics.get("success") is not None:
                label = "Social roll"
                if (social_check or {}).get("interaction_type"):
                    label = f"{social_check.get('interaction_type')} social roll"
                constraints["social"]["outcome_contract"] = self._roll_outcome_contract(
                    label,
                    social_mechanics.get("success"),
                    social_mechanics.get("margin"),
                    goal=(social_check or {}).get("reason", ""),
                    stakes=(
                        "NPC attitude, trust, cooperation, or refusal must match the social result. "
                        "Do not narrate agreement, trust, or cooperation from a failed social roll."
                    ),
                )
        if isinstance(skill_result, dict):
            constraints["skill"]["result"] = {
                "success": skill_result.get("success"),
                "roll": skill_result.get("roll"),
                "margin": skill_result.get("margin"),
                "total_bonus": skill_result.get("total_bonus"),
                "growth_added": skill_result.get("growth_added", {}),
            }
            constraints["skill"]["outcome_contract"] = self._roll_outcome_contract(
                f"{(skill_check or {}).get('skill') or skill_result.get('skill') or 'Skill'} roll",
                skill_result.get("success"),
                skill_result.get("margin"),
                goal=(skill_check or {}).get("reason", ""),
                stakes=(skill_check or {}).get("stakes", ""),
            )
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
            "story_bible_lore": self._select_story_bible_lore(player_input, turn_context, context.get("scene_facts", [])),
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

    def _npc_social_context_for_prompt(self, active_profiles: List[Dict[str, Any]],
                                       social_check: Optional[Dict[str, Any]],
                                       social_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Build the short trust/mood sentence the NPC reviewer should honor."""
        if not isinstance(social_check, dict) or not social_check.get("needs_social_check"):
            return {}
        target_npc = str(social_check.get("target_npc") or "")
        if not target_npc:
            return {}
        profile = next(
            (npc for npc in active_profiles if isinstance(npc, dict) and str(npc.get("npc_id")) == target_npc),
            {},
        )
        mechanics = {}
        if isinstance(social_result, dict):
            mechanics = social_result.get("social_result") if isinstance(social_result.get("social_result"), dict) else social_result
        name = (
            profile.get("known_name")
            if profile.get("known_name") and profile.get("known_name") != "unknown"
            else profile.get("reference_label") or profile.get("display_name") or target_npc
        )
        relationship_with_player = profile.get("relationship_with_player") if isinstance(profile.get("relationship_with_player"), dict) else {}
        player_relationship = (
            relationship_with_player.get("public_label")
            or profile.get("player_relationship")
            or profile.get("relationship")
            or "Stranger"
        )
        trust_label = mechanics.get("new_relationship") or profile.get("trust_label") or "neutral"
        trust_category = mechanics.get("trust_category") or profile.get("trust_category") or get_relationship_data(profile.get("trust", 0)).get("category", "neutral")
        mood_score = (
            mechanics.get("new_mood_score")
            if mechanics.get("new_mood_score") is not None
            else mechanics.get("mood") if isinstance(mechanics.get("mood"), (int, float))
            else profile.get("mood", 0)
        )
        mood = mechanics.get("mood_label") or mechanics.get("emotional_response") or profile.get("mood_label") or get_mood_label(mood_score)
        margin = mechanics.get("margin")
        success = mechanics.get("success")
        if success is True:
            result_text = "succeeded"
        elif success is False:
            result_text = "failed"
        else:
            result_text = "was not rolled"
        interaction_description = self._compact_text(
            social_check.get("reason") or social_check.get("interaction_type") or "the social interaction",
            180,
        )
        sentence = (
            f"{name}, whose relationship to the player is {player_relationship}, feels {trust_category} toward the player ({trust_label}), and is feeling {mood}. "
            f"The interaction {interaction_description} {result_text}"
        )
        if margin is not None:
            sentence += f" by a margin of {round(float(margin), 2) if isinstance(margin, (int, float)) else margin}"
        sentence += "."
        return {
            "npc_id": target_npc,
            "name": name,
            "relationship_with_player": relationship_with_player or {"type": "stranger", "public_label": player_relationship, "notes": ""},
            "player_relationship": player_relationship,
            "trust_label": trust_label,
            "trust_category": trust_category,
            "mood": mood_score,
            "mood_label": mood,
            "mood_delta": mechanics.get("mood_delta"),
            "interaction_description": interaction_description,
            "success": success,
            "margin": margin,
            "instruction": sentence,
        }

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
        active_ids = {str(npc.get("npc_id")) for npc in active_npcs if npc.get("npc_id")}
        if (social_check or {}).get("target_npc"):
            active_ids.add(str((social_check or {}).get("target_npc")))
        known_profiles = self._get_known_npcs_for_prompt(private=True)
        active_profiles = [
            npc for npc in known_profiles
            if str(npc.get("npc_id")) in active_ids
        ]
        context = {
            "player_input": player_input,
            "narrative_brief": narrative_brief or {},
            "active_npc_profiles": active_profiles,
            "npc_social_context": self._npc_social_context_for_prompt(active_profiles, social_check, social_result),
            "story_context": self._build_shared_story_context(player_input, turn_context, narrative_brief),
            "social_check": self._compact_social_check_for_prompt(social_check),
            "social_result": self._compact_social_result_for_prompt(social_result),
            "skill_check": self._compact_skill_check_for_prompt(skill_check),
            "skill_result": self._compact_skill_result_for_prompt(skill_result),
        }
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

    def _memory_update_facts(self, value: Any, max_items: int = TURN_MEMORY_UPDATE_MAX_FACTS) -> List[str]:
        """Normalize model memory-update fact lists into short strings."""
        if isinstance(value, (str, int, float, bool)):
            values = [value]
        elif isinstance(value, list):
            values = value
        elif isinstance(value, dict):
            values = [
                value.get(key)
                for key in ("fact", "text", "summary", "value", "note")
                if value.get(key) is not None
            ]
        else:
            values = []
        facts = []
        seen = set()
        for value in values:
            text = self._compact_text(value, NPC_FACT_MAX_CHARS)
            if not text:
                continue
            key = self._normalize_key_text(text)
            if key in seen:
                continue
            seen.add(key)
            facts.append(text)
            if len(facts) >= max_items:
                break
        return facts

    def _apply_turn_memory_updates(self, memory_updates: Any) -> Dict[str, Any]:
        """Apply validated durable memory extracted by the turn summarizer."""
        result = {
            "npc_facts_added": 0,
            "scene_facts_added": 0,
            "world_facts_added": 0,
            "skipped": [],
        }
        if not isinstance(memory_updates, dict):
            self._last_turn_memory_result = result
            return result

        npc_updates = memory_updates.get("npc_facts") or memory_updates.get("npcs") or []
        if isinstance(npc_updates, dict):
            npc_updates = [
                {"npc_id": npc_id, "facts": facts}
                for npc_id, facts in npc_updates.items()
            ]
        if not isinstance(npc_updates, list):
            npc_updates = []
        for update in npc_updates[:TURN_MEMORY_UPDATE_MAX_FACTS]:
            if not isinstance(update, dict):
                continue
            npc_ref = (
                update.get("npc_id")
                or update.get("target_npc")
                or update.get("name")
                or update.get("known_name")
                or update.get("display_name")
            )
            npc_id = self._resolve_npc_reference(str(npc_ref or ""))
            if not npc_id or npc_id not in self.game_state.get("npcs", {}):
                if npc_ref:
                    result["skipped"].append(f"unknown_npc:{npc_ref}")
                continue
            facts = update.get("facts")
            if facts is None:
                facts = update.get("known_facts") or update.get("fact")
            npc = self.game_state["npcs"][npc_id]
            before = list(self._npc_identity(npc).get("known_facts", []))
            for fact in self._memory_update_facts(facts):
                clean = self._sanitize_known_fact_text(fact)
                self._append_npc_known_fact(npc, clean or f"memory: {fact}")
            after = list(self._npc_identity(npc).get("known_facts", []))
            result["npc_facts_added"] += len([fact for fact in after if fact not in before])

        scene_updates = memory_updates.get("scene_facts") or memory_updates.get("current_scene") or {}
        scene_entries = self._iter_scene_fact_entries(scene_updates)
        if scene_entries:
            memory = self._normalize_scene_facts()
            for scope, key, text in scene_entries[:TURN_MEMORY_UPDATE_MAX_FACTS]:
                before = copy.deepcopy(memory)
                self._upsert_scene_fact(memory, scope, key, text)
                if memory != before:
                    result["scene_facts_added"] += 1
            self.game_state.setdefault("scenario", {})["scene_facts"] = memory

        world_updates = memory_updates.get("world_facts") or memory_updates.get("facts") or []
        for fact in self._memory_update_facts(world_updates):
            before = list(self.game_state.setdefault("world", {}).setdefault("facts", []))
            self._apply_note_fact({"action": "note_fact", "command": {"fact": fact}})
            after = self.game_state.setdefault("world", {}).setdefault("facts", [])
            if after != before:
                result["world_facts_added"] += 1

        contradictions = memory_updates.get("contradictions")
        if isinstance(contradictions, list) and contradictions:
            result["contradictions"] = [
                self._compact_text(item, 180)
                for item in contradictions[:TURN_MEMORY_UPDATE_MAX_FACTS]
            ]
        self._last_turn_memory_result = result
        return result

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
            "relevant_transcript_evidence": self._retrieve_relevant_transcript_evidence(player_input),
        }
        summary_response = self.api_manager.call_api(
            "turn_summary",
            context,
            temperature=MODEL_TURN_SUMMARY_TEMPERATURE,
            max_tokens=MODEL_TURN_SUMMARY_MAX_TOKENS,
        )
        summary = summary_response.get("summary") or summary_response.get("narrative") or ""
        self._apply_turn_memory_updates(summary_response.get("memory_updates", {}))
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
            skill_label = skill_result.get("skill") or (skill_check or {}).get("skill") or "Skill"
            constraints["skill_result"] = {
                "source": skill_result.get("source"),
                "skill": skill_label,
                "difficulty_class": (skill_check or {}).get("difficulty_class") or skill_result.get("difficulty_class"),
                "result": "success" if success else "failure",
                "margin": round(float(margin), 2) if isinstance(margin, (int, float)) else margin,
                "outcome_contract": self._roll_outcome_contract(
                    f"{skill_label} roll",
                    success,
                    margin,
                    goal=(skill_check or {}).get("reason", ""),
                    stakes=(skill_check or {}).get("stakes", ""),
                ),
            }
        compact_social = self._compact_social_result_for_prompt(social_result)
        if compact_social:
            filtered_social = {
                key: value
                for key, value in compact_social.items()
                if value not in (None, "", {}, [])
            }
            social_success = compact_social.get("success")
            social_margin = compact_social.get("margin")
            social_label = "Social roll"
            if isinstance(social_check, dict) and social_check.get("interaction_type"):
                social_label = f"{social_check.get('interaction_type')} social roll"
            filtered_social["result"] = "success" if bool(social_success) else "failure"
            filtered_social["outcome_contract"] = self._roll_outcome_contract(
                social_label,
                social_success,
                social_margin,
                goal=(social_check or {}).get("reason", ""),
                stakes=(
                    "NPC attitude, trust, cooperation, or refusal must match the social result. "
                    "Do not narrate agreement, trust, or cooperation from a failed social roll."
                ),
            )
            constraints["social_result"] = filtered_social
        compact_review = self._compact_npc_review_for_prompt(npc_review)
        if compact_review.get("npc_actions"):
            constraints["npc_dialogue_policy"] = (
                "npc_actions.dialogue is the authoritative NPC voice handoff. "
                "Use provided dialogue exactly or omit it; do not replace it with alternate speech for the same NPC beat."
            )
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
            "currency": possessions.get("currency", {}),
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
        world_location = self._world_location_context()
        location = self._format_world_location_for_prompt()
        scene_fact_map = self._compact_scene_fact_map_for_prompt(10, 220)
        scene_facts = [
            fact
            for scope in ("local", "carryover")
            for fact in scene_fact_map.get(scope, {}).values()
        ]
        world_facts = self._compact_list_text(self.game_state.get("world", {}).get("facts", []), 8, 220)
        world_time = self._world_time_context()
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
        full_story_bible = self._load_story_bible_json()
        story_bible_lore = self._select_story_bible_lore(player_input, turn_context, scene_facts)
        recent_exchanges = self._compact_recent_exchanges(
            PROMPT_DM_RECENT_EXCHANGE_LIMIT,
            max_player_chars=PROMPT_DM_RECENT_PLAYER_CHARS,
            max_dm_chars=PROMPT_DM_RECENT_DM_CHARS,
        )
        transcript_evidence = self._retrieve_relevant_transcript_evidence(player_input)
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
        if full_story_bible:
            sections.append(
                "FULL CANONICAL STORY BIBLE:\n"
                f"{json.dumps(full_story_bible, indent=2)}"
            )
        if story_bible_excerpt:
            sections.append(f"CANONICAL STORY BIBLE EXCERPT:\n{story_bible_excerpt}")
        if story_bible_lore:
            sections.append(
                "CANONICAL RELEVANT STORY BIBLE:\n"
                "These structured facts are mandatory when relevant to the current NPC, scene, or player action.\n"
                f"{json.dumps(story_bible_lore, indent=2)}"
            )
        if opening_scene:
            sections.append(
                "OPENING SCENE / CAMPAIGN SEED:\n"
                f"{opening_scene.get('title', 'Opening Scene')}\n\n"
                f"{opening_scene.get('text', '')}"
            )
        sections.append(f"SCENE BRIEF:\n{scene_brief or 'No current scene is available.'}")
        sections.append(f"KEYED SCENE FACTS (current truth):\n{json.dumps(scene_fact_map, indent=2)}")
        if world_facts:
            sections.append(f"DURABLE WORLD FACTS:\n{json.dumps(world_facts, indent=2)}")
        if lore_profiles:
            sections.append(
                "RELEVANT LORE:\n"
                "Use as appearance/culture defaults only. Individual NPC state overrides lore.\n"
                f"{json.dumps(lore_profiles, indent=2)}"
            )
        sections.append(f"PLAYER POSSESSIONS:\n{self._format_player_possessions_for_dm()}")
        situation = [
            f"Combat: {combat_status}",
            f"Location: {location}",
            f"Time: {world_time['clock']} ({world_time['time_of_day']}), {world_time['season']}",
        ]
        if combat_active:
            situation.extend([f"Player HP: {player_hp}", f"Player MP: {player_mp}"])
        sections.append("CURRENT SITUATION:\n- " + "\n- ".join(situation))
        sections.append(
            "WORLD TIME:\n"
            f"{self._format_world_time_for_prompt()}\n"
            "Ignore summary, transcript, or scene facts that imply a conflicting time of day. "
            "Do not narrate dawn, dusk, evening, night, moonlight, sunrise, or sunset unless the saved clock supports it or you emit a time_update command."
        )
        sections.append(
            "WORLD LOCATION:\n"
            f"{json.dumps(world_location or {'status': 'unknown'}, indent=2)}\n"
            "This saved location is the authoritative physical place for the player. "
            "Ignore opening-scene, summary, transcript, or stale scene facts that imply a conflicting location unless the JSON includes location_update."
        )
        if known_npcs:
            sections.append(
                "KNOWN RECURRING NPCS:\n"
                "Use these npc_id values exactly when emitting npc_update, party_update, or relationship_update commands.\n"
                "known_name is player-facing; if it is unknown, refer to reference_label rather than inventing or using a hidden true name.\n"
                "relationship_with_player is the objective social role/bond, separate from trust and mood.\n"
                f"{json.dumps(known_npcs, indent=2)}"
            )
        if summary:
            sections.append(f"CAMPAIGN SUMMARY:\n{summary}")
        if recent_exchanges:
            sections.append(f"RECENT EXCHANGES:\n{json.dumps(recent_exchanges, indent=2)}")
        if transcript_evidence:
            sections.append(
                "RELEVANT TRANSCRIPT EVIDENCE:\n"
                "Continuity aid from earlier story_transcript turns. Use direct prior dialogue or observed facts here to avoid contradicting established events; do not treat it as stronger than Story Bible or explicit saved game_state facts.\n"
                f"{json.dumps(transcript_evidence, indent=2)}"
            )
        if precomputed_context != "{}":
            sections.append(
                "PRE-DM CONSTRAINTS:\n"
                "Treat these as hard outcome constraints; do not explain mechanics.\n"
                "Every listed roll is already resolved. The narrative must show the stated success or failure and may not narrate the opposite outcome.\n"
                "A failed roll must create a concrete setback, complication, cost, lost opportunity, or worsened position tied to that roll.\n"
                "If npc_actions include dialogue, that dialogue is the NPC actor's voice handoff: quote it exactly or omit it, but do not invent a different line for the same NPC beat.\n"
                f"{precomputed_context}"
            )
        context = "\n\n".join(sections) + f"""
PLAYER ACTION: {player_input_json}
PLAYER AGENCY RULES:
- Resolve only what the player explicitly attempts.
- Do not invent player movement, speech, thoughts, feelings, attacks, pickups, searches, rests, departures, returns, or next objectives.
- Plans, intentions, and conditions are context only unless the player explicitly acts on them now.
- If the action reaches a natural stopping point, stop there and leave the next choice unresolved.
- You may narrate brief time passing, NPC/enemy actions, environmental changes, and observed consequences.
- Do not change time of day in narration unless the saved WORLD TIME supports it or the JSON includes time_update.
DM NARRATIVE SHAPE:
- Write {DM_NARRATIVE_MIN_PARAGRAPHS} to {DM_NARRATIVE_MAX_PARAGRAPHS} narrative paragraphs before the JSON block.
- Address the player character as "you"; do not narrate the player in third person or use the character name except in quoted dialogue or rare disambiguation.
- Paragraph 1 must restate PLAYER ACTION in polished narrative form, including the player's spoken words or intent when present.
- Paragraph 2, and paragraph 3 only if needed, should show immediate results of that action.
- If PRE-DM CONSTRAINTS include npc_actions.dialogue, use that NPC line exactly or omit it; do not paraphrase it or create a competing line.
- Present at most {DM_NARRATIVE_RESPONSE_HOOKS} clear player response opportunity, then stop the narrative immediately.
- A response opportunity may be NPC dialogue, a direct question, an accusation, a request, a visible choice point, or a pause that clearly invites the player to respond.
- Do not stack response hooks. After an NPC gives the player something to answer, do not add a second question, warning, threat, new objective, or extra scene beat.
DM STYLE:
{self._dm_prose_style_rules()}
NPC MEMORY RULES:
- npc_update.known_facts must be concise current facts, not full narration.
- Do not emit npc_update fields for mood, mood_score, trust, trust_level, relationship, or emotional_response; Python mechanics own those values.
- Use relationship_update, not npc_update.relationship, when the objective relationship role with the player changes.
- Keep each NPC fact under one short sentence and avoid "you/your" phrasing.
- Prefer current status, location, injuries, restraints, special marks, behavior, identity, or relationship changes.
SCENE MEMORY RULES:
- scene_update facts are keyed current truth, not narration history.
- Use stable generic keys such as "active_threats", "companion_condition", or "weather"; replace changed facts by reusing the same key.
- Put facts about the immediate location in set_facts.local. Put facts that should follow the player after leaving in set_facts.carryover.
- If a fact becomes false, include its key or exact text in remove_facts.
- On a true scene transition, long travel, sleep, or leaving a location, set transition true or clear_local_facts true; preserve carryover facts that still apply.
LOCATION MEMORY RULES:
- WORLD LOCATION is the player's saved physical location; do not pull the player back to the opening forest or caravan unless the current action actually returns there.
- If the player enters, leaves, travels to, rents, sleeps in, searches, or otherwise establishes a new physical place, include location_update with the most specific known fields.
- Use concise fields such as settlement, region, area, building, room, site, or coordinates. Do not store full narration in location fields.
RESPOND WITH:
1. Narrative description of what happens.
2. At the very end, exactly one JSON command block with mechanical actions and durable state updates.
Use a single command for one change, or multi for several:
```json
{{
  "action": "multi",
  "commands": [
    {{"action": "scene_update", "command": {{"current_scene": "What is physically true now.", "set_facts": {{"local": {{"active_threats": "No active enemies are visible here."}}, "carryover": {{"companion_condition": "Layla remains wounded but stable."}}}}, "remove_facts": ["obsolete_fact_key"], "transition": false}}}},
    {{"action": "location_update", "command": {{"location": {{"settlement": "Veldros", "building": "Rusty Tankard", "room": "rented room"}}}}}},
    {{"action": "npc_update", "command": {{"npc_id": "existing_or_new_npc_id", "updates": {{"status": "freed", "known_facts": ["Durable NPC fact."]}}}}}},
    {{"action": "party_update", "command": {{"npc_id": "existing_npc_id", "action": "join", "reason": "The NPC is now traveling with the player."}}}},
    {{"action": "relationship_update", "command": {{"npc_id": "existing_npc_id", "type": "traveling companion", "public_label": "Traveling Companion", "reason": "The NPC has agreed to travel with the player."}}}},
    {{"action": "inventory", "command": {{"action": "add", "item_data": {{"archetype": "Iron Key", "tags": ["key"], "hp": 100, "max_hp": 100}}, "quantity": 1, "condition": "worn"}}}},
    {{"action": "currency", "command": {{"copper": 5, "reason": "ordinary coins found"}}}},
    {{"action": "note_fact", "command": {{"fact": "A durable world or story fact the game must remember."}}}},
    {{"action": "time_update", "command": {{"advance_minutes": 10, "reason": "Waiting, travel, searching, crafting, resting, or other meaningful time spent."}}}}
  ]
}}
```
Available command actions: narrative, scene_update, location_update, time_update, npc_update, party_update, relationship_update, note_fact, inventory, currency, quest, spell_create, spell_study, spell_cast, combat_start, combat_action, combat_end, skill_check.
If your narrative names, describes, injures, moves, or changes an NPC, include an npc_update for that NPC in the JSON. If a name is revealed to the player, include that newly revealed name in updates.name. Keep the npc_id stable: use an existing npc_id, or a descriptive unnamed id for a new unnamed NPC. Do not switch an existing unnamed npc_id to a name-based id after revelation.
If your narrative says an NPC joins, leaves, starts traveling with, is recruited by, is dismissed from, or parts from the player, include party_update for that NPC. Use action "join" or "leave"; do not write party membership through npc_update.
If the story changes an NPC's objective relationship role with the player, include relationship_update. Use type values such as {", ".join(PLAYER_RELATIONSHIP_TYPE_EXAMPLES)}. Do not include a status field; former relationships should be expressed as type values such as "former lover", "former wife", "former husband", or "former traveling companion".
If your narrative says the player finds, takes, receives, buys, loots, carries, or keeps an item, include an inventory add command for that item in the JSON.
Use currency for ordinary spendable coins or money: copper, silver, gold, and platinum should update the wallet, not inventory. Only use inventory for unusual physical coins such as foreign, cursed, marked, sealed, collectible, or counterfeit coins.
Use WORLD TIME as the current clock. If the player waits, travels, searches at length, rests, crafts, studies, or if narration implies minutes/hours passing or a new time of day, include time_update with advance_minutes. Do not use scene_update alone to imply clock movement.
Use WORLD LOCATION as the current physical location. If narration changes where the player is, include location_update; do not use scene_update alone to imply physical relocation.
Do not emit social_interaction for the current player action. Use skill_check only for additional checks that were not already precomputed.
ONLY output the narrative + one JSON block. No extra text."""
        
        return context
    def _command_payload(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Return the nested command payload when present."""
        payload = command.get("command", {})
        return payload if isinstance(payload, dict) else {}
    def _decay_npc_moods_for_elapsed_hours(self, hours_crossed: int) -> Dict[str, Any]:
        """Move short-term NPC mood scores toward neutral after clock-hour changes."""
        hours = max(0, int(hours_crossed))
        rate = max(0.0, float(NPC_MOOD_DECAY_PER_HOUR))
        summary = {
            "hours_crossed": hours,
            "rate": rate,
            "total_decay": round(hours * rate, 2),
            "updated_npcs": 0,
            "changes": [],
        }
        if hours <= 0 or rate <= 0:
            return summary
        decay = hours * rate
        npcs = self.game_state.get("npcs", {})
        if not isinstance(npcs, dict):
            return summary
        for npc_id, npc in npcs.items():
            if not isinstance(npc, dict):
                continue
            identity = npc.get("identity")
            if not isinstance(identity, dict):
                continue
            if "mood" not in identity and "mood_score" not in identity:
                continue
            old_mood = get_mood_score(npc, 0.0)
            if old_mood > 0:
                new_mood = max(0.0, old_mood - decay)
            elif old_mood < 0:
                new_mood = min(0.0, old_mood + decay)
            else:
                new_mood = 0.0
            new_mood = round(new_mood, 2)
            if new_mood != old_mood or not isinstance(identity.get("mood"), (int, float)):
                identity["mood"] = new_mood
                identity.pop("mood_score", None)
                summary["updated_npcs"] += 1
                summary["changes"].append({
                    "npc_id": str(npc_id),
                    "from": old_mood,
                    "to": new_mood,
                })
        return summary

    def _advance_world_time(self, advance_minutes: int, reason: str = "") -> Dict[str, Any]:
        """Advance the persistent world clock by a bounded number of minutes."""
        minutes = max(0, int(advance_minutes))
        if minutes <= 0:
            return {
                "success": True,
                "message": "No time advanced",
                "advanced_minutes": 0,
                "time": self._world_time_context(),
                "mood_decay": self._decay_npc_moods_for_elapsed_hours(0),
            }
        time_state = self._world_time_context()
        old_abs_hour = ((time_state["day"] - 1) * 24) + time_state["hour"]
        total = ((time_state["day"] - 1) * 1440) + (time_state["hour"] * 60) + time_state["minute"] + minutes
        new_day = (total // 1440) + 1
        minute_of_day = total % 1440
        new_hour = minute_of_day // 60
        new_minute = minute_of_day % 60
        new_abs_hour = ((new_day - 1) * 24) + new_hour
        mood_decay = self._decay_npc_moods_for_elapsed_hours(max(0, new_abs_hour - old_abs_hour))
        world_time = self.game_state.setdefault("world", {}).setdefault("time", {})
        world_time.update({
            "day": new_day,
            "hour": new_hour,
            "minute": new_minute,
            "season": time_state.get("season", "spring"),
        })
        game = self.game_state.setdefault("game", {})
        game["playtime"] = self._coerce_time_int(game.get("playtime"), 0) + minutes
        if reason:
            game["last_time_advance_reason"] = str(reason)[:160]
        return {
            "success": True,
            "message": f"Advanced world time by {minutes} minute(s)",
            "advanced_minutes": minutes,
            "time": self._world_time_context(),
            "mood_decay": mood_decay,
        }
    def _apply_time_update(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Persist deliberate DM-declared time passage."""
        payload = self._command_payload(command)
        minutes = (
            payload.get("advance_minutes")
            if payload.get("advance_minutes") is not None
            else payload.get("minutes")
        )
        hours = payload.get("advance_hours")
        if minutes is None and hours is not None:
            minutes = self._coerce_time_int(hours, 0) * 60
        if minutes is None:
            return {"success": False, "message": "time_update requires advance_minutes or advance_hours"}
        advance_minutes = self._coerce_time_int(minutes, 0)
        if advance_minutes < 0:
            return {"success": False, "message": "time_update cannot move time backward"}
        if advance_minutes > TIME_MAX_DM_ADVANCE_MINUTES:
            return {
                "success": False,
                "message": f"time_update advance exceeds configured maximum of {TIME_MAX_DM_ADVANCE_MINUTES} minutes",
            }
        return self._advance_world_time(advance_minutes, payload.get("reason", "DM time update"))

    def _time_quantity_from_text(self, value: Any) -> Optional[float]:
        """Parse a small written or numeric time quantity."""
        text = str(value or "").strip().lower()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            pass
        return {
            "a": 1,
            "an": 1,
            "one": 1,
            "two": 2,
            "three": 3,
            "four": 4,
            "five": 5,
            "six": 6,
            "seven": 7,
            "eight": 8,
            "nine": 9,
            "ten": 10,
            "eleven": 11,
            "twelve": 12,
            "couple": 2,
            "several": 3,
        }.get(text)

    def _infer_player_declared_time_advance(self, player_input: Any) -> Dict[str, Any]:
        """Infer explicit time passage declared by the player, independent of DM JSON."""
        text = re.sub(r"[-–—]", " ", str(player_input or "").lower())
        if not text.strip():
            return {"minutes": 0, "reason": ""}

        quantity = (
            r"(?:\d+(?:\.\d+)?|a|an|one|two|three|four|five|six|seven|eight|nine|ten|"
            r"eleven|twelve|couple|several)"
        )
        spans: List[Tuple[int, int]] = []
        minutes = 0

        def add_match(match: re.Match, amount: float):
            nonlocal minutes
            if any(not (match.end() <= start or match.start() >= end) for start, end in spans):
                return
            spans.append((match.start(), match.end()))
            minutes += max(1, int(round(amount)))

        for match in re.finditer(fr"\b({quantity})\s+days?\s+(?:and\s+)?({quantity})\s+hours?\b", text):
            days = self._time_quantity_from_text(match.group(1))
            hours = self._time_quantity_from_text(match.group(2))
            if days is not None and hours is not None:
                add_match(match, (days * 1440) + (hours * 60))

        for match in re.finditer(fr"\b({quantity})\s+hours?\s+(?:and\s+)?({quantity})\s+minutes?\b", text):
            hours = self._time_quantity_from_text(match.group(1))
            mins = self._time_quantity_from_text(match.group(2))
            if hours is not None and mins is not None:
                add_match(match, (hours * 60) + mins)

        for match in re.finditer(fr"\b({quantity})\s+and\s+a\s+half\s+hours?\b", text):
            hours = self._time_quantity_from_text(match.group(1))
            if hours is not None:
                add_match(match, (hours * 60) + 30)

        for match in re.finditer(r"\bhalf\s+(?:an?\s+)?hours?\b", text):
            add_match(match, 30)

        for match in re.finditer(r"\bquarter\s+(?:of\s+an?\s+|an?\s+)?hours?\b", text):
            add_match(match, 15)

        for match in re.finditer(r"\bhalf\s+(?:a\s+)?days?\b", text):
            add_match(match, 720)

        for match in re.finditer(fr"\b({quantity})\s+days?\b", text):
            days = self._time_quantity_from_text(match.group(1))
            if days is not None:
                add_match(match, days * 1440)

        for match in re.finditer(fr"\b({quantity})\s+hours?\b", text):
            hours = self._time_quantity_from_text(match.group(1))
            if hours is not None:
                add_match(match, hours * 60)

        for match in re.finditer(fr"\b({quantity})\s+(?:minutes?|mins?)\b", text):
            mins = self._time_quantity_from_text(match.group(1))
            if mins is not None:
                add_match(match, mins)

        for match in re.finditer(r"\b(?:slow\s+)?count\s+of\s+(\d+)\b", text):
            count = self._coerce_time_int(match.group(1), 0)
            if count > 0:
                add_match(match, (count + 59) // 60)

        if minutes <= 0:
            return {"minutes": 0, "reason": ""}
        return {
            "minutes": min(minutes, TIME_MAX_DM_ADVANCE_MINUTES),
            "reason": "player-declared time passage",
        }

    def _apply_missing_time_update_fallback(self, player_input: str, command: Any,
                                            result: Dict[str, Any]) -> Dict[str, Any]:
        """Advance saved time when the DM omits time_update."""
        if self._command_includes_time_update(command):
            return result
        inferred = self._infer_player_declared_time_advance(player_input)
        minutes = self._coerce_time_int(inferred.get("minutes"), 0)
        reason = inferred.get("reason") or "default per-turn passage"
        if minutes <= 0:
            minutes = TIME_DEFAULT_TURN_MINUTES
        if minutes <= 0:
            return result
        if not isinstance(result, dict):
            result = {"success": False, "message": "Command result was not a dictionary"}
        result["time_result"] = self._advance_world_time(minutes, reason)
        return result

    def _apply_scene_update(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Persist current-scene text and scoped current scene facts."""
        payload = self._command_payload(command)
        def command_flag(name: str) -> bool:
            value = payload.get(name)
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return value != 0
            return str(value or "").strip().lower() in {"true", "yes", "1", "on"}
        scenario = self.game_state.setdefault("scenario", {})
        current_scene = payload.get("current_scene") or payload.get("scene") or payload.get("description")
        if current_scene:
            scenario["current_scene"] = str(current_scene)
        location_update_result = None
        location = payload.get("location") or payload.get("world_location") or payload.get("current_location")
        if isinstance(location, dict):
            location_update_result = self._apply_location_update({
                "action": "location_update",
                "command": {"location": location},
            })
        memory = self._normalize_scene_facts()
        if command_flag("transition") or command_flag("clear_local_facts"):
            memory["local"] = {}
        if command_flag("clear_carryover_facts"):
            memory["carryover"] = {}

        removed = 0
        remove_facts = (
            payload.get("remove_facts")
            or payload.get("remove_scene_facts")
            or payload.get("stale_facts")
            or []
        )
        if isinstance(remove_facts, (str, int, float, bool, dict)):
            remove_facts = [remove_facts]
        for fact_ref in remove_facts if isinstance(remove_facts, list) else []:
            removed += self._remove_scene_fact(memory, fact_ref)

        added = 0
        fact_sets = [
            (payload.get("set_facts"), "local"),
            (payload.get("facts"), payload.get("fact_scope", "local")),
            (payload.get("scene_facts"), payload.get("fact_scope", "local")),
            (payload.get("local_facts"), "local"),
            (payload.get("carryover_facts"), "carryover"),
        ]
        for fact_values, default_scope in fact_sets:
            if fact_values in (None, "", [], {}):
                continue
            for scope, key, text in self._iter_scene_fact_entries(fact_values, str(default_scope or "local")):
                self._upsert_scene_fact(memory, scope, key, text)
                added += 1
        scenario["scene_facts"] = memory
        result = {
            "success": True,
            "message": "Scene updated",
            "current_scene": scenario.get("current_scene", ""),
            "facts_added": added,
            "facts_removed": removed,
            "local_fact_count": len(memory.get("local", {})),
            "carryover_fact_count": len(memory.get("carryover", {})),
        }
        if location_update_result:
            result["location_update"] = location_update_result
        return result
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
        mechanics_owned_fields = {
            "mood",
            "mood_score",
            "emotional_response",
            "trust",
            "trust_level",
            "relationship",
        }
        ignored_fields = [
            field for field in updates
            if str(field).strip().lower() in mechanics_owned_fields
        ]
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
            if str(field).strip().lower() in mechanics_owned_fields:
                continue
            self._set_npc_field(npcs[npc_id], field, value)
        if any(field in updates for field in ("race", "gender")):
            self._initialize_npc_baseline_stats(npcs[npc_id], force=True)
        self._ensure_npc_name_fields(npc_id, npcs[npc_id])
        self._normalize_npc_records()
        npc_id = self._resolve_npc_reference(str(original_npc_ref)) or npc_id
        alias_map = self.game_state.setdefault("npc_aliases", {})
        alias_map[str(original_npc_ref)] = npc_id
        for field in ("name", "known_name", "display_name"):
            if updates.get(field) not in ("", None, [], {}):
                alias_map[str(updates[field])] = npc_id
        updated_fields = [
            field for field in updates
            if str(field).strip().lower() not in mechanics_owned_fields
        ]
        message = f"Updated NPC {npc_id}"
        if ignored_fields:
            message += f"; ignored mechanics-owned fields: {', '.join(str(field) for field in ignored_fields)}"
        return {
            "success": True,
            "message": message,
            "updated_fields": updated_fields,
            "ignored_fields": ignored_fields,
        }
    def _parse_party_membership(self, payload: Dict[str, Any]) -> Optional[bool]:
        """Return requested party membership, or None when the command is ambiguous."""
        for field in ("party", "party_member", "is_party_member", "member", "in_party", "joined"):
            if field in payload:
                return self._coerce_bool(payload.get(field), False)
        action = self._normalize_key_text(
            payload.get("action")
            or payload.get("status")
            or payload.get("membership")
            or payload.get("state")
        )
        if action in {"join", "joins", "joined", "add", "added", "recruit", "recruited", "with party", "in party"}:
            return True
        if action in {"leave", "leaves", "left", "remove", "removed", "depart", "departed", "dismiss", "dismissed", "not in party"}:
            return False
        return None

    def _apply_party_update(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Set an NPC's party membership flag from a dedicated DM command."""
        payload = self._command_payload(command)
        npc_ref = (
            payload.get("npc_id")
            or payload.get("target_npc")
            or payload.get("name")
            or payload.get("known_name")
        )
        if not npc_ref:
            return {"success": False, "message": "party_update requires npc_id or target_npc"}
        is_party = self._parse_party_membership(payload)
        if is_party is None:
            return {"success": False, "message": "party_update requires join/leave action or party boolean"}

        updates = {}
        for name_field in ("name", "known_name", "display_name"):
            if payload.get(name_field) not in ("", None, [], {}):
                updates[name_field] = payload.get(name_field)
        npc_id = (
            self._resolve_npc_reference(str(npc_ref))
            or self._ensure_npc_for_interaction(str(npc_ref), updates=updates)
        )
        if not npc_id:
            return {"success": False, "message": f"Could not resolve NPC for party update: {npc_ref}"}
        npcs = self.game_state.setdefault("npcs", {})
        if npc_id not in npcs:
            npcs[npc_id] = self._make_template_npc(npc_id, {"npc_id": npc_id, "aliases": [str(npc_ref)]})

        npc = npcs[npc_id]
        self._set_npc_field(npc, "party", is_party)
        identity = self._npc_identity(npc)
        party_role = payload.get("party_role") or payload.get("role")
        if party_role not in ("", None, [], {}):
            identity["party_role"] = self._compact_text(party_role, 80)
        reason = self._compact_text(payload.get("reason", ""), 120)
        current_relationship = self._npc_relationship_with_player(npc)
        current_type = current_relationship.get("type", "stranger")
        if is_party:
            if current_type in {"", "stranger", "acquaintance"} or "companion" in current_type:
                self._set_npc_field(npc, "relationship_with_player", {
                    "type": "traveling companion",
                    "public_label": "Traveling Companion",
                    "notes": reason or "Traveling with the player.",
                })
        elif "companion" in current_type:
            self._set_npc_field(npc, "relationship_with_player", {
                "type": "former traveling companion",
                "public_label": "Former Traveling Companion",
                "notes": reason or "No longer traveling with the player.",
            })
        fact = payload.get("known_fact") or payload.get("fact")
        if fact in ("", None, [], {}):
            fact = f"party: {'active traveling companion' if is_party else 'not an active traveling companion'}"
        self._append_npc_known_fact(npc, fact)
        self._ensure_npc_name_fields(npc_id, npc)
        self._normalize_npc_records()
        resolved_id = self._resolve_npc_reference(str(npc_ref)) or npc_id
        return {
            "success": True,
            "message": f"{'Added' if is_party else 'Removed'} {resolved_id} {'to' if is_party else 'from'} the party",
            "npc_id": resolved_id,
            "party": is_party,
            "reason": reason,
            "relationship_with_player": self._npc_relationship_with_player(npc),
            "updated_fields": ["identity.party", "identity.party_member", "identity.relationship_with_player"],
        }

    def _apply_relationship_update(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Set an NPC's objective relationship role/bond with the player."""
        payload = self._command_payload(command)
        npc_ref = (
            payload.get("npc_id")
            or payload.get("target_npc")
            or payload.get("name")
            or payload.get("known_name")
        )
        if not npc_ref:
            return {"success": False, "message": "relationship_update requires npc_id or target_npc"}

        raw_relationship_value = payload.get("relationship_with_player")
        relationship_value = raw_relationship_value
        if not isinstance(relationship_value, dict):
            relationship_value = {
                "type": (
                    raw_relationship_value
                    or payload.get("type")
                    or payload.get("relationship_type")
                    or payload.get("relationship_role")
                    or payload.get("relationship")
                    or payload.get("role")
                ),
                "public_label": payload.get("public_label") or payload.get("label"),
                "notes": payload.get("notes") or payload.get("reason") or "",
            }
        requested_type = relationship_value.get("type") if isinstance(relationship_value, dict) else relationship_value
        if requested_type in ("", None, [], {}):
            return {"success": False, "message": "relationship_update requires a relationship type"}

        updates = {}
        for name_field in ("name", "known_name", "display_name"):
            if payload.get(name_field) not in ("", None, [], {}):
                updates[name_field] = payload.get(name_field)
        npc_id = (
            self._resolve_npc_reference(str(npc_ref))
            or self._ensure_npc_for_interaction(str(npc_ref), updates=updates)
        )
        if not npc_id:
            return {"success": False, "message": f"Could not resolve NPC for relationship update: {npc_ref}"}

        npcs = self.game_state.setdefault("npcs", {})
        if npc_id not in npcs:
            npcs[npc_id] = self._make_template_npc(npc_id, {"npc_id": npc_id, "aliases": [str(npc_ref)]})

        npc = npcs[npc_id]
        relationship = self._normalize_relationship_with_player(relationship_value)
        self._set_npc_field(npc, "relationship_with_player", relationship)
        fact = payload.get("known_fact") or payload.get("fact")
        if fact in ("", None, [], {}):
            fact = f"relationship: {relationship.get('public_label') or relationship.get('type')}"
        self._append_npc_known_fact(npc, fact)
        self._ensure_npc_name_fields(npc_id, npc)
        self._normalize_npc_records()
        resolved_id = self._resolve_npc_reference(str(npc_ref)) or npc_id
        return {
            "success": True,
            "message": f"Updated {resolved_id} relationship with player to {relationship['public_label']}",
            "npc_id": resolved_id,
            "relationship_with_player": relationship,
            "updated_fields": ["identity.relationship_with_player"],
        }
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

    def _command_includes_time_update(self, command: Any) -> bool:
        return any(
            str(entry.get("action", "")).lower() in {"time_update", "advance_time"}
            for entry in self._iter_command_entries(command)
            if isinstance(entry, dict)
        )

    def _npc_refs_from_completed_turn(self, command: Dict[str, Any],
                                      social_check: Optional[Dict[str, Any]],
                                      social_result: Optional[Dict[str, Any]],
                                      npc_review: Optional[Dict[str, Any]]) -> List[str]:
        refs: List[str] = []
        for item in self._iter_command_entries(command):
            action = item.get("action", "").lower()
            payload = self._command_payload(item)
            if action in {"npc_update", "npc_state", "social_interaction", "relationship_update", "player_relationship_update"}:
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
        if action in {"time_update", "advance_time"}:
            return self._apply_time_update(command)
        if action == "note_fact":
            return self._apply_note_fact(command)
        if action in {"npc_update", "npc_state"}:
            return self._apply_npc_update(command)
        if action in {"party_update", "party"}:
            return self._apply_party_update(command)
        if action in {"relationship_update", "player_relationship_update"}:
            return self._apply_relationship_update(command)
        if action == "skill_check":
            payload = self._command_payload(command)
            stats_used = payload.get("stats_used") or []
            if isinstance(stats_used, str):
                stats_used = [stats_used]
            try:
                difficulty_class = int(float(payload.get("difficulty_class", DEFAULT_UNEVALUATED_DC)))
            except (TypeError, ValueError):
                difficulty_class = DEFAULT_UNEVALUATED_DC
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
                interaction_type=social_command.get("interaction_type", "appeal"),
                difficulty_class=social_command.get("difficulty_class"),
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
        elif action == "currency":
            currency_command = command.get("command", {})
            if not isinstance(currency_command, dict):
                return {"success": False, "message": "currency command requires an object"}
            self._save_game_state()
            return self._reload_game_state_after_external_update(add_currency_to_wallet(
                copper=currency_command.get("copper", currency_command.get("cp", 0)),
                silver=currency_command.get("silver", currency_command.get("sp", 0)),
                gold=currency_command.get("gold", currency_command.get("gp", 0)),
                platinum=currency_command.get("platinum", currency_command.get("pp", 0)),
                entity_id=currency_command.get("entity_id", "player"),
            ))
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
        dm_override = self._extract_dm_override(player_input)
        if dm_override is not None:
            return self._process_dm_override(player_input, dm_override)
        ooc_question = self._extract_ooc_question(player_input)
        if ooc_question:
            return self._process_ooc_question(player_input, ooc_question)
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
                difficulty_class=social_check.get("difficulty_class"),
            )
        skill_check = self._detect_skill_check(player_input, turn_context, social_check=social_check)
        if skill_check.get("reroute_to_social_check") and not social_result:
            social_check = skill_check["reroute_to_social_check"]
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
                difficulty_class=social_check.get("difficulty_class"),
            )
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
        result = self._apply_missing_time_update_fallback(player_input, command, result)
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
                    "minute": 0,
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
    def _calculate_social_difficulty(self, player_input: str, target_npc: str,
                                     base_difficulty: Optional[int] = None) -> int:
        """Apply the simple trust modifier to a reference-selected social base DC."""
        base_dc = self._coerce_dc_int(base_difficulty, DEFAULT_UNEVALUATED_DC)
        trust = self._npc_trust_value(target_npc)
        return int(max(1, min(100, round(base_dc - trust))))
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
                              narrative_brief: Optional[Dict[str, Any]] = None,
                              difficulty_class: Optional[int] = None) -> Dict[str, Any]:
        """Process a social interaction with enhanced system"""
        try:
            target_npc = self._resolve_npc_reference(target_npc) or target_npc
            if difficulty_class is None:
                difficulty = self._calculate_social_difficulty(player_input, target_npc)
            else:
                difficulty = max(1, min(100, self._coerce_dc_int(difficulty_class, DEFAULT_UNEVALUATED_DC)))
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
    def _npc_api_record(self, npc_id: str, npc: Dict[str, Any]) -> Dict[str, Any]:
        """Return an NPC record with flat UI fields while preserving the raw save data."""
        record = copy.deepcopy(npc)
        known_name = self._get_npc_field(npc, "known_name", "unknown")
        public_name = (
            self._compact_text(known_name, 80)
            if self._is_learned_npc_name(known_name, npc_id)
            else self._npc_public_reference_label(npc_id, npc)
        )
        mood_score = self._get_npc_field(npc, "mood", 0)
        relationship_with_player = self._npc_relationship_with_player(npc)
        trust_label = self._get_npc_field(npc, "trust_label", "neutral")
        record.update({
            "npc_id": npc_id,
            "id": npc_id,
            "name": public_name,
            "display_name": self._get_npc_field(npc, "display_name", public_name),
            "known_name": known_name if self._is_learned_npc_name(known_name, npc_id) else "unknown",
            "gender": self._get_npc_field(npc, "gender", ""),
            "race": self._get_npc_field(npc, "race", ""),
            "role": self._get_npc_field(npc, "party_role", "") or self._get_npc_field(npc, "title", "") or "Companion",
            "relationship": relationship_with_player.get("public_label", "Stranger"),
            "relationship_with_player": relationship_with_player,
            "trust_label": trust_label,
            "trust": self._get_npc_field(npc, "trust", 0),
            "mood": mood_score,
            "mood_label": get_mood_label(mood_score),
            "location": self._get_npc_field(npc, "location", ""),
            "party": self._get_npc_field(npc, "party", False),
        })
        return record

    def get_npcs(self) -> List[Dict]:
        """Get all NPCs."""
        npcs = self.game_state.get("npcs", {})
        if not isinstance(npcs, dict):
            return []
        return [
            self._npc_api_record(npc_id, npc)
            for npc_id, npc in npcs.items()
            if isinstance(npc, dict)
        ]
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
