# api_integration.py
import json
import time
import hashlib
import re
from datetime import datetime
from typing import Dict, Any, Optional, List
try:
    import requests
except ImportError:
    requests = None
from pathlib import Path
from path_config import path_config
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("APIIntegration")

TOKEN_USAGE_FILE_NAME = "token_usage.json"
DEBUG_PROMPT_FILE_NAME = "last_api_prompt_debug.json"
DEBUG_PROMPT_BY_TYPE_TEMPLATE = "last_api_prompt_{prompt_type}.json"
DEBUG_RESPONSE_BY_TYPE_TEMPLATE = "last_api_response_{prompt_type}.json"
DEFAULT_API_CALL_DELAY_SECONDS = 1.2
DEFAULT_CONTEXT_MODEL = "mistral-small-latest"
DEFAULT_NPC_MODEL = "mistral-large-latest"
DEFAULT_DM_MODEL = "mistral-large-latest"
DEFAULT_SUMMARY_MODEL = "mistral-small-latest"
DEFAULT_MISTRAL_MODEL = DEFAULT_CONTEXT_MODEL

class APIManager:
    def __init__(self, api_key: str = "", base_url: str = "https://api.mistral.ai/v1",
                 call_delay_seconds: Optional[float] = None, model: Optional[str] = None):
        """Initialize API manager with configuration"""
        self.api_key = api_key or os.getenv("MISTRAL_API_KEY", "")
        if not self.api_key:
            logger.warning("No Mistral API key provided - will use fallback logic")
        
        self.base_url = base_url
        self.context_model = os.getenv("MISTRAL_CONTEXT_MODEL", model or DEFAULT_CONTEXT_MODEL)
        self.npc_model = os.getenv("MISTRAL_NPC_MODEL", DEFAULT_NPC_MODEL)
        self.dm_model = os.getenv("MISTRAL_DM_MODEL", DEFAULT_DM_MODEL)
        self.summary_model = os.getenv("MISTRAL_SUMMARY_MODEL", DEFAULT_SUMMARY_MODEL)
        self.model = model or os.getenv("MISTRAL_MODEL", self.context_model)
        self.call_history = []
        self.response_cache = {}
        self.max_cache_size = 50
        self.cache_hits = 0
        self.call_delay_seconds = self._resolve_call_delay(call_delay_seconds)
        self.session_id = datetime.now().strftime("%Y%m%dT%H%M%S")
        self.token_usage_path = path_config.logs_dir / TOKEN_USAGE_FILE_NAME
        self.session_token_usage = {
            "session_id": self.session_id,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_tokens": 0,
            "calls": []
        }

        # Load system prompts
        self.system_prompts = self._load_system_prompts()

    def _resolve_call_delay(self, call_delay_seconds: Optional[float]) -> float:
        """Resolve the live API throttle delay."""
        if call_delay_seconds is not None:
            return max(0.0, float(call_delay_seconds))
        try:
            return max(0.0, float(os.getenv("API_CALL_DELAY_SECONDS", DEFAULT_API_CALL_DELAY_SECONDS)))
        except ValueError:
            return DEFAULT_API_CALL_DELAY_SECONDS

    def delay_before_call(self):
        """Pause before a live API request to avoid rapid-fire model calls."""
        if self.call_delay_seconds > 0:
            time.sleep(self.call_delay_seconds)

    def _load_system_prompts(self) -> Dict[str, str]:
        """Load pre-defined system prompts from file"""
        try:
            prompts_path = path_config.references_dir / "api_prompts.json"
            if prompts_path.exists():
                with open(prompts_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load system prompts: {e}")
        
        return self._get_default_prompts()

    def _get_default_prompts(self) -> Dict[str, str]:
        """Return default system prompts if file loading fails"""
        return {
            "narrative_generation": """Return only JSON: {"narrative":"2-4 concise dark-fantasy sentences"}.""",

            "dialogue_generation": """You are an NPC in a dark fantasy world.
            Respond with personality-appropriate dialogue that matches the NPC's voice style.
            Keep responses concise (1-3 sentences) and in character.""",

            "social_check_detection": """Return only JSON with this shape:
{"needs_social_check":false,"target_npc":"","interaction_type":"appeal","reason":"short reason"}

Set needs_social_check true whenever the player tries to influence, comfort, persuade, deceive, threaten, bargain with, question, recruit, calm, or request something from a specific NPC.
Do not include markdown or prose.""",
            

            "npc_action_review": """You review each NPC's immediate action separately from DM narration.
            Return JSON with npc_actions, where each action has npc_id, name, action, dialogue, body_language, and constraints.""",

            "turn_context_evaluation": """Return only JSON with this shape:
{"involved_npcs":[],"relevant_races":[],"likely_intent":"","mechanical_risks":[],"continuity_constraints":[],"forbidden_assumptions":[],"scene_focus":"","relevant_lore_keys":[]}

Select only context that matters for this turn. Do not narrate.""",

            "narrative_brief": """Return only JSON with this shape:
{"scene_brief":"","relevant_lore":[],"active_npcs":[],"mechanical_constraints":{},"continuity_constraints":[],"forbidden_assumptions":[]}

Build a compact brief for the NPC narrator and DM. Include only facts that affect this turn.
active_npcs must only include recurring NPCs from known_npcs; never include the player, mobs, enemies, victims, or reference-library characters.""",

            "skill_check_detection": """Return only JSON with this shape:
{"needs_skill_check":false,"skill":"","stats_used":[],"difficulty_class":0,"reason":"short reason","stakes":""}

Use a skill check whenever success is uncertain and failure matters: stealth, searching, tracking, medicine, survival, crafting, athletics, investigation, magic, tools, or perception.
Pick varied DCs: 15 trivial, 25 very easy, 35 easy, 45 moderate-low, 55 moderate-high, 65 difficult, 80 very hard, 95 extreme.
Do not default to 50. Use 50 only if the situation is truly average.
Do not include markdown or prose.""",

            "dc_evaluation": """Return only strict JSON with this shape:
{"base_dc":50,"candidate_modifiers":[{"fact":"","category":"","scope":"","effect":"helps","modifier":0,"relevance":0,"reason":""}],"notes":""}

Use only the compact referee packet provided. effect "helps" must use a negative modifier, effect "hurts" must use a positive modifier, and effect "neutral" must use 0. Never use a plus sign in JSON numbers; write 2, not +2. Most facts should be 0, 1, 2, -1, or -2. Use 5+ only for significant factors, 10+ for major factors, and 20 only for overwhelming factors. Do not compute the final DC; Python will apply only the top 3 positive and top 3 negative modifiers.""",

            "turn_summary": """Summarize this completed RPG turn in one concise line.
            Return JSON with summary only."""
        }

    def _generate_context_hash(self, prompt_type: str, context: dict) -> str:
        """Generate consistent hash for caching"""
        context_str = json.dumps({"prompt_type": prompt_type, "context": context}, sort_keys=True)
        return hashlib.md5(context_str.encode()).hexdigest()

    def _log_api_call(self, endpoint: str, input_tokens: int, output_tokens: int,
                     response_time: float, success: bool):
        """Track API call metrics"""
        self.call_history.append({
            "timestamp": time.time(),
            "endpoint": endpoint,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "response_time": response_time,
            "success": success
        })

        # Keep only last 100 calls
        if len(self.call_history) > 100:
            self.call_history.pop(0)

    def record_token_usage(self, prompt_type: str, input_tokens: int, output_tokens: int,
                           success: bool, source: str = "api_manager"):
        """Record per-session token usage and persist it for visibility."""
        input_tokens = int(max(0, round(input_tokens)))
        output_tokens = int(max(0, round(output_tokens)))
        event = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "prompt_type": prompt_type,
            "source": source,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "success": success
        }
        self.session_token_usage["calls"].append(event)
        self.session_token_usage["total_input_tokens"] += input_tokens
        self.session_token_usage["total_output_tokens"] += output_tokens
        self.session_token_usage["total_tokens"] += input_tokens + output_tokens
        self._persist_token_usage()

    def _persist_token_usage(self):
        """Write the current session token counter to disk."""
        try:
            path_config.logs_dir.mkdir(parents=True, exist_ok=True)
            data = {"sessions": {}}
            if self.token_usage_path.exists():
                with open(self.token_usage_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        data = loaded
            sessions = data.setdefault("sessions", {})
            sessions[self.session_id] = self.session_token_usage
            data["current_session_id"] = self.session_id
            with open(self.token_usage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to persist token usage: {e}")

    def get_token_usage(self) -> Dict[str, Any]:
        """Return the running token counter for this session."""
        return self.session_token_usage.copy()

    def _optimize_context(self, context: dict, max_tokens: int = 1000) -> dict:
        """Compress context to fit token budget"""
        optimized = context.copy()

        # Limit interaction history to last 3 entries
        if "interaction_history" in optimized and len(optimized["interaction_history"]) > 3:
            optimized["interaction_history"] = optimized["interaction_history"][-3:]

        # Simplify NPC profile if needed
        if "npc_profile" in optimized:
            optimized["npc_profile"] = {
                "name": optimized["npc_profile"].get("name", ""),
                "personality": optimized["npc_profile"].get("personality", {}),
                "relationship": optimized["npc_profile"].get("relationship_with_player", "neutral"),
                "mood": optimized["npc_profile"].get("current_mood", "neutral"),
                "voice_style": optimized["npc_profile"].get("voice_style", "normal")
            }

        return optimized

    def _safe_prompt_type_filename(self, prompt_type: str) -> str:
        """Return a filesystem-safe prompt type for debug files."""
        safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(prompt_type or "unknown")).strip("_")
        return safe or "unknown"

    def write_prompt_debug(self, prompt_type: str, payload: Dict[str, Any],
                           context: Dict[str, Any], source: str = "api_manager"):
        """Overwrite prompt debug files with the exact payload about to be used."""
        try:
            path_config.logs_dir.mkdir(parents=True, exist_ok=True)
            safe_prompt_type = self._safe_prompt_type_filename(prompt_type)
            debug_data = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "source": source,
                "prompt_type": prompt_type,
                "api_key_present": bool(self.api_key),
                "requests_available": requests is not None,
                "model": payload.get("model"),
                "temperature": payload.get("temperature"),
                "max_tokens": payload.get("max_tokens"),
                "messages": payload.get("messages", []),
                "optimized_context": context,
            }
            debug_text = json.dumps(debug_data, indent=2, ensure_ascii=False)
            (path_config.logs_dir / DEBUG_PROMPT_FILE_NAME).write_text(debug_text, encoding="utf-8")
            (path_config.logs_dir / DEBUG_PROMPT_BY_TYPE_TEMPLATE.format(
                prompt_type=safe_prompt_type
            )).write_text(debug_text, encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to write prompt debug file: {e}")

    def write_response_debug(self, prompt_type: str, raw_response: Any,
                             parsed_response: Optional[Dict[str, Any]] = None,
                             error: str = "", model: Optional[str] = None):
        """Overwrite the latest raw response debug file for a prompt type."""
        try:
            path_config.logs_dir.mkdir(parents=True, exist_ok=True)
            safe_prompt_type = self._safe_prompt_type_filename(prompt_type)
            debug_data = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "prompt_type": prompt_type,
                "model": model or self.model,
                "error": error,
                "raw_response": raw_response,
                "parsed_response": parsed_response or {},
            }
            (path_config.logs_dir / DEBUG_RESPONSE_BY_TYPE_TEMPLATE.format(
                prompt_type=safe_prompt_type
            )).write_text(json.dumps(debug_data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to write response debug file: {e}")

    def _model_for_prompt_type(self, prompt_type: str) -> str:
        """Choose the model role for a structured prompt."""
        if prompt_type == "npc_action_review":
            return self.npc_model
        if prompt_type == "turn_summary":
            return self.summary_model
        if prompt_type in {"turn_context_evaluation", "narrative_brief", "social_check_detection", "skill_check_detection", "dc_evaluation"}:
            return self.context_model
        return self.model

    def call_api(self, prompt_type: str, context: dict, temperature: float = 0.7,
                 model: Optional[str] = None, max_tokens: int = 500) -> Dict[str, Any]:
        """Make optimized API call with caching and error handling"""
        optimized_context = self._optimize_context(context)
        selected_model = model or self._model_for_prompt_type(prompt_type)
        payload = {
            "model": selected_model,
            "messages": [
                {"role": "system", "content": self.system_prompts.get(prompt_type, "")},
                {"role": "user", "content": json.dumps(optimized_context)}
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        input_tokens = self._estimate_token_count(payload["messages"])

        self.write_prompt_debug(prompt_type, payload, optimized_context)

        # If no API key, use fallback immediately
        if not self.api_key:
            logger.info("No API key - using fallback response")
            fallback = self._generate_fallback_response(prompt_type, context)
            output_tokens = self._estimate_token_count(fallback)
            self._log_api_call(prompt_type, input_tokens, output_tokens, 0, True)
            self.record_token_usage(prompt_type, input_tokens, output_tokens, True, source="fallback")
            return fallback
        if requests is None:
            logger.warning("requests is not installed - using fallback response")
            fallback = self._generate_fallback_response(prompt_type, context)
            output_tokens = self._estimate_token_count(fallback)
            self._log_api_call(prompt_type, input_tokens, output_tokens, 0, False)
            self.record_token_usage(prompt_type, input_tokens, output_tokens, False, source="fallback")
            return fallback
        
        # Generate context hash for caching
        context_hash = self._generate_context_hash(f"{prompt_type}:{selected_model}", context)

        # Check cache first
        if context_hash in self.response_cache:
            logger.info("Using cached API response")
            self.cache_hits += 1
            return self.response_cache[context_hash]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        try:
            start_time = time.time()
            self.delay_before_call()

            # Make API call
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )

            response.raise_for_status()
            result = response.json()

            # Calculate metrics
            response_time = time.time() - start_time
            output_tokens = self._estimate_token_count(result["choices"][0]["message"]["content"])

            # Log the call
            self._log_api_call(prompt_type, input_tokens, output_tokens, response_time, True)
            self.record_token_usage(prompt_type, input_tokens, output_tokens, True)

            # Parse and cache response
            parsed_response = self._parse_api_response(result, prompt_type)
            if parsed_response.get("parse_error") and prompt_type in {
                "social_check_detection",
                "skill_check_detection",
                "npc_action_review",
                "turn_summary",
                "turn_context_evaluation",
                "narrative_brief",
                "dc_evaluation",
            }:
                fallback = self._generate_fallback_response(prompt_type, context)
                fallback["parse_error"] = parsed_response["parse_error"]
                fallback["fallback_after_parse_error"] = True
                parsed_response = fallback
            self.write_response_debug(prompt_type, result, parsed_response, model=selected_model)
            self.response_cache[context_hash] = parsed_response

            # Maintain cache size
            if len(self.response_cache) > self.max_cache_size:
                oldest_hash = next(iter(self.response_cache))
                del self.response_cache[oldest_hash]

            return parsed_response

        except Exception as e:
            logger.error(f"API call failed: {str(e)}")
            self._log_api_call(prompt_type, input_tokens, 0, 0, False)
            self.record_token_usage(prompt_type, input_tokens, 0, False)

            # Return fallback response
            return self._generate_fallback_response(prompt_type, context)

    def _parse_api_response(self, raw_response: dict, prompt_type: str = "") -> Dict[str, Any]:
        """Robust parser that handles messy Mistral outputs."""
        try:
            message_content = raw_response["choices"][0]["message"]["content"]

            # Convert anything (list, dict, str) to string safely
            if isinstance(message_content, list):
                message_content = " ".join(str(item) for item in message_content)
            elif isinstance(message_content, dict):
                message_content = json.dumps(message_content)
            else:
                message_content = str(message_content)

            content = message_content.strip()
            if not content:
                raise ValueError("Empty model response content")

            # 1. Try fenced JSON (most common good case)
            import re
            fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL | re.IGNORECASE)
            if fenced:
                json_str = fenced.group(1).strip()
                if not json_str:
                    raise ValueError("Empty fenced JSON response")
                return self._loads_json_lenient(json_str)

            # 2. Try raw JSON object
            if content.startswith("{") and content.endswith("}"):
                return self._loads_json_lenient(content)

            # 3. Extract first JSON object from text
            json_object = self._extract_first_json_object(content)
            if json_object:
                return self._loads_json_lenient(json_object)

            # 4. Last resort - treat as narrative
            return {"narrative": content}

        except Exception as e:
            logger.error(f"Failed to parse API response: {str(e)}")
            fallback = self._generate_fallback_response(prompt_type, {}) if prompt_type else {}
            if fallback:
                fallback["parse_error"] = str(e)
                self.write_response_debug(prompt_type, raw_response, fallback, str(e))
                return fallback
            return {
                "narrative": "The world continues around you...",
                "error": "Failed to parse model response",
                "raw_snippet": str(raw_response.get("choices", [{}])[0].get("message", {}).get("content", ""))[:200]
            }

    def _loads_json_lenient(self, json_text: str) -> Dict[str, Any]:
        """Load JSON while tolerating common model mistakes like +2 numbers."""
        try:
            return json.loads(json_text)
        except json.JSONDecodeError:
            cleaned = re.sub(r'(:\s*)\+(\d+(?:\.\d+)?)', r'\1\2', json_text)
            return json.loads(cleaned)

    def _extract_first_json_object(self, text: str) -> str:
        """Extract the first balanced JSON object from arbitrary text."""
        start = text.find("{")
        if start == -1:
            return ""

        depth = 0
        in_string = False
        escape = False
        for idx in range(start, len(text)):
            char = text[idx]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start:idx + 1]
        return ""

    def _word_present(self, text: str, words: List[str]) -> bool:
        """Return true if any word or phrase appears in normalized text."""
        return any(word in text for word in words)

    def _estimate_contextual_dc(self, player_action: str, context: dict,
                                base: int, task_kind: str = "") -> int:
        """Estimate a varied DC from action and scene context."""
        text = " ".join([
            player_action,
            str(context.get("current_scene", "")),
            " ".join(str(fact) for fact in context.get("scene_facts", [])[-8:]),
        ]).lower()
        dc = base

        if self._word_present(text, ["proper tools", "file", "kit", "bench", "careful", "slowly", "take my time"]):
            dc -= 10
        if task_kind == "stealth" and self._word_present(text, [
            "distracted", "fighting", "attacking the wagons", "attacking wagons",
            "focused on the wagons", "focused on the caravan", "busy", "occupied",
            "carnage", "massacre", "chaos"
        ]):
            dc -= 15
        if task_kind == "stealth" and self._word_present(text, [
            "a hundred yards", "one hundred yards", "100 yards", "hundred yards",
            "far down the road", "down the road"
        ]):
            dc -= 15
        if task_kind == "stealth" and self._word_present(text, [
            "cover", "foliage", "forest", "underbrush", "bush", "trees",
            "treeline", "hidden", "out of sight"
        ]):
            dc -= 10
        if task_kind == "stealth" and self._word_present(text, [
            "not yet noticed", "not noticed", "haven't noticed", "have not noticed",
            "unaware", "unseen"
        ]):
            dc -= 10
        if task_kind == "stealth" and self._word_present(text, [
            "drag", "dragging", "carry", "carrying", "move the girl",
            "move her", "move someone", "unconscious", "chains", "chain"
        ]):
            dc += 10
        if self._word_present(text, ["obvious", "known", "likely place", "under the driver", "under the drivers"]):
            dc -= 5
        if self._word_present(text, ["improvised", "crude", "no tools", "bare hands"]):
            dc += 10
        if self._word_present(text, ["demon", "enemy", "patrol", "danger", "under pressure", "bleeding", "wounded"]):
            dc += 10
        if self._word_present(text, ["alert", "watched", "guarded", "hostile", "pursuit"]):
            dc += 10
        if self._word_present(text, ["dark", "night", "rain", "smoke", "panic", "hurry"]):
            dc += 5
        if task_kind == "stealth" and self._word_present(text, [
            "already alerted", "alerted", "actively searching", "searching for",
            "eyes locking", "attention fixed", "scanning the slope", "watching the treeline"
        ]):
            dc += 10
        if task_kind == "search" and self._word_present(player_action, ["search", "look", "check"]):
            dc -= 5
        if task_kind == "medicine" and self._word_present(player_action, ["stabilize", "compression", "bandage"]):
            dc -= 5

        if task_kind == "stealth":
            danger_nearby = self._word_present(text, ["demon", "enemy", "monster", "hostile", "danger"])
            moving_burden = self._word_present(text, [
                "drag", "dragging", "carry", "carrying", "move the girl",
                "move her", "move someone", "ease the girl", "girl",
                "wounded woman", "unconscious", "chains", "chain"
            ])
            if danger_nearby and moving_burden:
                dc = max(dc, 35)
            elif danger_nearby:
                dc = max(dc, 25)

        return max(10, min(100, int(round(dc / 5) * 5)))

    def _infer_skill_check(self, context: dict) -> Dict[str, Any]:
        """Rule-based skill detector used when the model is unavailable or invalid."""
        player_action = context.get("player_input", "").lower()

        stealth_intent = self._word_present(player_action, [
            "sneak", "hide", "quiet", "quietly", "silent", "avoid notice",
            "avoid detection", "don't see me", "dont see me", "out of sight",
            "unseen", "undetected", "creep", "under the cover", "under cover"
        ])
        if stealth_intent:
            dc = self._estimate_contextual_dc(player_action, context, 45, "stealth")
            return {
                "needs_skill_check": True,
                "skill": "stealth",
                "stats_used": ["Agi", "Ins"],
                "difficulty_class": dc,
                "reason": "The action depends on avoiding notice.",
                "stakes": "Success avoids attention; failure may create noise or reveal position."
            }

        if self._word_present(player_action, ["file", "rivet", "chain", "manacle", "forge", "smith"]):
            dc = self._estimate_contextual_dc(player_action, context, 45, "smithing")
            return {
                "needs_skill_check": True,
                "skill": "smithing",
                "stats_used": ["Crea", "Str"],
                "difficulty_class": dc,
                "reason": "Metal hardware work requires a smithing/tool check.",
                "stakes": "Success weakens or removes the hardware cleanly; failure costs time, noise, or damages tools."
            }
        if self._word_present(player_action, ["search", "look for", "check under", "inspect", "find", "scavenge"]):
            if self._word_present(player_action, ["demons search", "monsters search", "enemies search", "they search"]):
                return {
                    "needs_skill_check": False,
                    "skill": "",
                    "stats_used": [],
                    "difficulty_class": 0,
                    "reason": "The searching actor is not the player.",
                    "stakes": ""
                }
            dc = self._estimate_contextual_dc(player_action, context, 45, "search")
            return {
                "needs_skill_check": True,
                "skill": "investigation",
                "stats_used": ["Ins"],
                "difficulty_class": dc,
                "reason": "Searching a dangerous or cluttered area has uncertain results.",
                "stakes": "Success finds useful items or clues; failure misses them, costs time, or increases exposure."
            }
        if self._word_present(player_action, ["bandage", "wound", "bleeding", "medicine", "heal", "stabilize", "clean the wound"]):
            dc = self._estimate_contextual_dc(player_action, context, 50, "medicine")
            return {
                "needs_skill_check": True,
                "skill": "medicine",
                "stats_used": ["Ins", "Agi", "Will"],
                "difficulty_class": dc,
                "reason": "Treating wounds under field conditions requires a medicine check.",
                "stakes": "Success stabilizes the patient; failure worsens bleeding, infection risk, or noise."
            }
        if self._word_present(player_action, ["track", "tracks", "trail", "follow signs"]):
            dc = self._estimate_contextual_dc(player_action, context, 45, "survival")
            return {
                "needs_skill_check": True,
                "skill": "survival",
                "stats_used": ["Ins", "Agi"],
                "difficulty_class": dc,
                "reason": "Following signs through wilderness requires survival.",
                "stakes": "Success follows the trail; failure loses time or follows a false lead."
            }

        return {
            "needs_skill_check": False,
            "skill": "",
            "stats_used": [],
            "difficulty_class": 0,
            "reason": "No non-social mechanical uncertainty detected.",
            "stakes": ""
        }

    def _infer_social_check(self, context: dict) -> Dict[str, Any]:
        """Rule-based social detector used when the model is unavailable or too conservative."""
        player_action = context.get("player_input", "").lower()
        known_npcs = context.get("known_npcs", []) or []
        social_words = [
            "talk", "speak", "say", "ask", "tell", "convince", "persuade",
            "intimidate", "threaten", "bargain", "negotiate", "lie", "deceive",
            "gift", "offer", "plead", "apologize", "flatter", "demand",
            "whisper", "promise", "request", "beg", "comfort", "reassure",
            "help", "trust", "calm", "explain", "warn", "thank"
        ]

        target = ""
        for npc in known_npcs:
            name = str(npc.get("name", "")).lower()
            npc_id = str(npc.get("npc_id", "")).lower()
            if name and name in player_action:
                target = npc.get("npc_id", npc.get("name", ""))
                break
            if npc_id and npc_id in player_action:
                target = npc.get("npc_id", "")
                break

        if not target and any(pronoun in player_action for pronoun in ["her", "him", "them"]):
            scene_text = " ".join([
                str(context.get("current_scene", "")),
                str(context.get("summary_file", "")),
                " ".join(str(fact) for fact in context.get("scene_facts", [])[-10:]),
            ]).lower()
            active_matches = []
            for npc in known_npcs:
                name = str(npc.get("name", "")).lower()
                npc_id = str(npc.get("npc_id", "")).lower()
                if (name and name in scene_text) or (npc_id and npc_id in scene_text):
                    active_matches.append(npc)
            if len(active_matches) == 1:
                target = active_matches[0].get("npc_id", active_matches[0].get("name", ""))

        needs_check = bool(target) and any(word in player_action for word in social_words)
        interaction_type = "appeal"
        if self._word_present(player_action, ["threaten", "intimidate", "warn"]):
            interaction_type = "threat"
        elif self._word_present(player_action, ["demand", "order", "command"]):
            interaction_type = "demand"
        elif self._word_present(player_action, ["gift", "offer"]):
            interaction_type = "gift"
        elif self._word_present(player_action, ["flatter", "compliment", "praise"]):
            interaction_type = "flattery"
        elif self._word_present(player_action, ["comfort", "reassure", "calm", "apologize", "thank"]):
            interaction_type = "comfort"
        elif self._word_present(player_action, ["lie", "deceive", "trick"]):
            interaction_type = "deception"

        return {
            "needs_social_check": needs_check,
            "target_npc": target,
            "interaction_type": interaction_type,
            "reason": "Detected social influence toward a known NPC." if needs_check else "No known NPC social target detected."
        }

    def _generate_fallback_response(self, prompt_type: str, context: dict) -> Dict[str, Any]:
        """Generate rule-based response when API fails"""
        logger.warning(f"Using fallback response for {prompt_type}")

        if prompt_type == "narrative_generation":
            # Generic narrative
            npc_name = context.get("npc_name", "The NPC")
            return {
                "narrative": f"{npc_name} responds to your request with a measured tone, considering your words carefully before answering."
            }

        elif prompt_type == "dialogue_generation":
            # Generic dialogue
            return {
                "dialogue": "I'll consider your request.",
                "body_language": "thoughtful"
            }

        elif prompt_type == "social_check_detection":
            return self._infer_social_check(context)

        elif prompt_type == "npc_action_review":
            social_result = context.get("social_result", {})
            social_check = context.get("social_check", {})
            target_npc = social_check.get("target_npc", "")
            npc_actions = []
            if target_npc and social_result:
                reaction = social_result.get("npc_reaction", {})
                npc_actions.append({
                    "npc_id": target_npc,
                    "name": target_npc,
                    "action": "responds to the player's social approach",
                    "dialogue": reaction.get("dialogue", "I'll consider that."),
                    "body_language": reaction.get("body_language", "thoughtful"),
                    "constraints": {
                        "success": social_result.get("social_result", {}).get("success", False),
                        "emotional_response": social_result.get("social_result", {}).get("emotional_response", "neutral"),
                        "trust_change": social_result.get("social_result", {}).get("trust_change", 0)
                    }
                })
            return {"npc_actions": npc_actions, "notes": "Fallback NPC review"}

        elif prompt_type == "skill_check_detection":
            return self._infer_skill_check(context)

        elif prompt_type == "dc_evaluation":
            skill_check = context.get("skill_check", {}) or {}
            base_dc = skill_check.get("difficulty_class") or context.get("suggested_base_dc") or 50
            try:
                base_dc = int(float(base_dc))
            except (TypeError, ValueError):
                base_dc = 50
            return {
                "base_dc": max(1, min(100, base_dc)),
                "candidate_modifiers": [],
                "notes": "Fallback DC evaluation used the detected base DC without additional fact modifiers."
            }

        elif prompt_type == "turn_context_evaluation":
            known_npcs = context.get("known_npcs", []) or []
            action_text = str(context.get("player_input", "")).lower()
            involved_npcs = []
            for npc in known_npcs:
                name = str(npc.get("name", "")).lower()
                npc_id = str(npc.get("npc_id", "")).lower()
                if (name and name in action_text) or (npc_id and npc_id in action_text):
                    involved_npcs.append(npc.get("npc_id") or npc.get("name"))
            if not involved_npcs and len(known_npcs) == 1 and any(word in action_text for word in ["her", "him", "them"]):
                involved_npcs.append(known_npcs[0].get("npc_id") or known_npcs[0].get("name"))

            relevant_races = []
            player = context.get("player", {}) or {}
            player_identity = player.get("identity") if isinstance(player.get("identity"), dict) else {}
            player_race = player_identity.get("race") or player.get("race")
            if player_race:
                relevant_races.append(str(player_race).lower())
            for npc in known_npcs:
                race = npc.get("race")
                if race:
                    relevant_races.append(str(race).lower())

            return {
                "involved_npcs": [npc for npc in involved_npcs if npc],
                "relevant_races": sorted(set(relevant_races)),
                "likely_intent": context.get("player_input", ""),
                "mechanical_risks": [],
                "continuity_constraints": ["Preserve current scene facts and any known NPC state."],
                "forbidden_assumptions": ["Do not choose movement, speech, or decisions for the player."],
                "scene_focus": str(context.get("current_scene", ""))[:700],
                "relevant_lore_keys": sorted(set(relevant_races)),
            }

        elif prompt_type == "narrative_brief":
            turn_context = context.get("turn_context", {}) or {}
            racial_profiles = context.get("racial_profiles", {}) or {}
            relevant_lore = []
            race_aliases = {
                "beastfolk": "beastkin",
                "beast_kin": "beastkin",
                "nekko": "beastkin",
                "low_caste_demon": "demon",
                "high_caste_demon": "demon",
            }
            for race in turn_context.get("relevant_races", []):
                race_key = str(race).lower().replace(" ", "_").replace("-", "_")
                profile = racial_profiles.get(race_key) or racial_profiles.get(race_aliases.get(race_key, race_key))
                if isinstance(profile, dict):
                    relevant_lore.append({
                        "race": race,
                        "description": profile.get("description", ""),
                        "appearance": profile.get("appearance", ""),
                        "culture": profile.get("culture", ""),
                        "current_status": profile.get("current_status", ""),
                        "relations": profile.get("relations", {}),
                    })
            return {
                "scene_brief": str(context.get("current_scene", ""))[:900],
                "relevant_lore": relevant_lore,
                "active_npcs": [
                    npc for npc in context.get("known_npcs", [])
                    if isinstance(npc, dict) and npc.get("npc_id")
                ],
                "mechanical_constraints": {
                    "social_check": context.get("social_check", {}),
                    "social_result": context.get("social_result", {}),
                    "skill_check": context.get("skill_check", {}),
                    "skill_result": context.get("skill_result", {}),
                },
                "continuity_constraints": turn_context.get("continuity_constraints", []),
                "forbidden_assumptions": turn_context.get("forbidden_assumptions", []),
            }

        elif prompt_type == "turn_summary":
            player_action = " ".join(str(context.get("player_input", "")).split())
            narrative = " ".join(str(context.get("dm_narrative", "")).split())
            if narrative:
                summary = f"Player: {player_action[:70]} | DM: {narrative[:110]}"
            else:
                summary = f"Player acted: {player_action[:160]}"
            return {"summary": summary}

        return {"narrative": "Fallback response generated."}

    def _estimate_token_count(self, text: Any) -> int:
        """Estimate token count for cost tracking"""
        if isinstance(text, (dict, list)):
            text = json.dumps(text)
        return len(str(text).split()) * 1.3  # Approximate tokens

    def get_api_stats(self) -> Dict[str, Any]:
        """Return API usage statistics"""
        if not self.call_history:
            return {"calls": 0, "avg_tokens": 0, "success_rate": 0, "cache_hit_rate": 0}

        total_input = sum(call["input_tokens"] for call in self.call_history)
        total_output = sum(call["output_tokens"] for call in self.call_history)
        success_calls = sum(1 for call in self.call_history if call["success"])

        return {
            "total_calls": len(self.call_history),
            "avg_input_tokens": total_input / len(self.call_history),
            "avg_output_tokens": total_output / len(self.call_history),
            "avg_total_tokens": (total_input + total_output) / len(self.call_history),
            "success_rate": success_calls / len(self.call_history),
            "cache_size": len(self.response_cache),
            "cache_hit_rate": self._calculate_cache_hit_rate(),
            "session_tokens": self.get_token_usage()
        }

    def _calculate_cache_hit_rate(self) -> float:
        """Calculate cache effectiveness"""
        total = len(self.call_history) + self.cache_hits
        if total == 0:
            return 0.0
        return self.cache_hits / total
