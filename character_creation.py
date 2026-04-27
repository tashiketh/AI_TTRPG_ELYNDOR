# character_creation.py
import json
import os
import csv
from typing import Dict, Any, List, Optional
from pathlib import Path
import re
from path_config import path_config
from helper_functions import calculate_scaled_hp_mp_max

# Configuration
RACE_DATA_PATH = "references/races.json"
BACKGROUNDS_PATH = "references/backgrounds.json"
GAME_STATE_PATH = str(path_config.game_state_path)

# Default race data (if files don't exist)
DEFAULT_RACE_DATA = {
    "human": {
        "base_stats": {"Str": 12, "Agi": 10, "Vit": 10, "Ins": 12, "Will": 10, "Crea": 12},
        "max_stats": {"Str": 20, "Agi": 20, "Vit": 20, "Ins": 20, "Will": 20, "Crea": 20},
        "gender_modifiers": {
            "male": {"Str": 2, "Vit": 1, "Will": -1},
            "female": {"Str": -1, "Ins": 1, "Will": 1}
        },
        "description": "Versatile and adaptable",
        "allowed_genders": ["male", "female"],
        "common_backgrounds": ["farmer", "merchant", "soldier", "scholar", "artisan"]
    },
    "elf": {
        "base_stats": {"Str": 7, "Agi": 11, "Vit": 8, "Ins": 13, "Will": 10, "Crea": 12},
        "max_stats": {"Str": 18, "Agi": 22, "Vit": 18, "Ins": 22, "Will": 20, "Crea": 22},
        "gender_modifiers": {
            "male": {"Str": 2, "Vit": 1, "Will": -1},
            "female": {"Str": -1, "Ins": 1, "Will": 1}
        },
        "description": "Graceful and magical",
        "allowed_genders": ["male", "female"],
        "common_backgrounds": ["forest guide", "mage", "diplomat", "artist", "ranger"]
    },
    "dwarf": {
        "base_stats": {"Str": 14, "Agi": 8, "Vit": 12, "Ins": 11, "Will": 10, "Crea": 11},
        "max_stats": {"Str": 22, "Agi": 18, "Vit": 24, "Ins": 20, "Will": 22, "Crea": 18},
        "gender_modifiers": {
            "male": {"Str": 2, "Vit": 1, "Will": -1},
            "female": {"Str": -1, "Ins": 1, "Will": 1}
        },
        "description": "Sturdy and resilient",
        "allowed_genders": ["male", "female"],
        "common_backgrounds": ["miner", "blacksmith", "engineer", "warrior", "brewer"]
    },
    "beastfolk": {
        "base_stats": {"Str": 14, "Agi": 15, "Vit": 14, "Ins": 12, "Will": 8, "Crea": 8},
        "max_stats": {"Str": 18, "Agi": 19, "Vit": 20, "Ins": 19, "Will": 18, "Crea": 17},
        "gender_modifiers": {
            "male": {"Str": 2, "Vit": 1, "Will": -1},
            "female": {"Str": -1, "Ins": 1, "Will": 1}
        },
        "description": "Agile and instinctive",
        "allowed_genders": ["male", "female"],
        "common_backgrounds": ["hunter", "scout", "wanderer", "survivor", "guard"]
    },
    "nekko": {
        "base_stats": {"Str": 9, "Agi": 15, "Vit": 13, "Ins": 9, "Will": 9, "Crea": 13},
        "max_stats": {"Str": 16, "Agi": 22, "Vit": 20, "Ins": 18, "Will": 19, "Crea": 18},
        "gender_modifiers": {
            "male": {"Str": 2, "Vit": 1, "Will": -1},
            "female": {"Str": -1, "Ins": 1, "Will": 1}
        },
        "description": "Agile, smooth-skinned, and socially vulnerable",
        "allowed_genders": ["male", "female"],
        "common_backgrounds": ["scout", "slave", "laborer", "guide", "outcast"]
    },
    "demon": {
        "base_stats": {"Str": 12, "Agi": 12, "Vit": 14, "Ins": 14, "Will": 13, "Crea": 14},
        "max_stats": {"Str": 16, "Agi": 20, "Vit": 18, "Ins": 19, "Will": 17, "Crea": 18},
        "gender_modifiers": {
            "male": {"Str": 2, "Vit": 1, "Will": -1},
            "female": {"Str": -1, "Ins": 1, "Will": 1}
        },
        "description": "Powerful but feared",
        "allowed_genders": ["male", "female"],
        "common_backgrounds": ["outcast", "mage", "warrior", "exile", "scholar"]
    }
}

# Default backgrounds
DEFAULT_BACKGROUNDS = [
    "noble", "commoner", "scholar", "warrior", "merchant", "artisan",
    "outcast", "wanderer", "hunter", "farmer", "priest", "thief",
    "adventurer", "sage", "healer", "bard", "soldier", "sailor"
]

GUIDED_CREATION_QUESTIONS = [
    {
        "id": "occupation",
        "prompt": "What did you do for a living before Elyndor?"
    },
    {
        "id": "hobbies",
        "prompt": "What hobbies, sports, crafts, or regular activities shaped you?"
    },
    {
        "id": "emergency_response",
        "prompt": "Are you good in an emergency? What usually happens when pressure hits?"
    },
    {
        "id": "wilderness_survival",
        "prompt": "How could you survive in a wilderness with little help?"
    },
    {
        "id": "strengths",
        "prompt": "What were you unusually good at?"
    },
    {
        "id": "weaknesses",
        "prompt": "What were you bad at, inexperienced with, or physically/mentally weak in?"
    },
    {
        "id": "personal_flaw",
        "prompt": "What personal habit, belief, or flaw followed you into Elyndor?"
    }
]

GUIDED_QUESTION_LABELS = {
    "occupation": "Former occupation",
    "hobbies": "Former hobbies",
    "emergency_response": "Emergency response",
    "wilderness_survival": "Wilderness survival",
    "strengths": "Personal strengths",
    "weaknesses": "Personal weaknesses",
    "personal_flaw": "Personal flaw"
}

STAT_KEYWORDS = {
    "Str": [
        "labor", "construction", "warehouse", "farmer", "mechanic", "soldier", "marine",
        "fighter", "boxing", "wrestling", "weight", "lifting", "strong", "strength",
        "physical job", "manual", "carpenter", "blacksmith", "army",
    ],
    "Agi": [
        "runner", "running", "dance", "dancer", "martial arts", "gymnast", "climb",
        "climbing", "parkour", "quick", "reflex", "agile", "athlete", "sports",
        "basketball", "soccer", "tennis", "raquetball"
    ],
    "Vit": [
        "endurance", "stamina", "hiking", "camping", "survival", "military",
        "firefighter", "paramedic", "nurse", "tough", "resilient", "marathon",
        "backpacking", "outdoors"
    ],
    "Ins": [
        "engineer", "programmer", "software", "doctor", "nurse", "medic", "teacher",
        "research", "researcher", "student", "scholar", "scientist", "analyst",
        "detective", "strategy", "chess", "reading", "studied", "smart"
    ],
    "Will": [
        "emergency", "calm", "pressure", "discipline", "disciplined", "military",
        "air force", "army", "police", "firefighter", "paramedic", "nurse", "determined",
        "stubborn", "focused", "meditation", "trauma", "crisis"
    ],
    "Crea": [
        "artist", "art", "music", "musician", "writer", "writing", "design",
        "designer", "invent", "inventor", "creative", "craft", "crafting",
        "woodworking", "cooking", "improvise", "improvisation", "engineering", "author"
    ]
}

LOW_STAT_KEYWORDS = {
    "Str": [
        "desk job", "office", "sedentary", "weak", "never exercise", "no exercise",
        "out of shape", "physically weak", "not physical", "not very strong",
        "not strong"
    ],
    "Agi": [
        "clumsy", "slow", "poor reflex", "bad reflex", "uncoordinated",
        "bad coordination"
    ],
    "Vit": [
        "sickly", "low stamina", "poor endurance", "tire easily", "frail",
        "bad health"
    ],
    "Ins": [
        "bad at studying", "poor memory", "not academic", "impulsive",
        "bad with details"
    ],
    "Will": [
        "panic", "panics", "freeze", "freezes", "anxious", "coward",
        "gives up", "low confidence"
    ],
    "Crea": [
        "not creative", "unimaginative", "rigid", "literal", "no hobbies",
        "all physical", "only physical"
    ]
}

SKILL_KEYWORDS = {
    "melee weapons": ["sword", "knife", "stick fighting", "martial arts", "soldier", "combat", "weapon"],
    "unarmed combat": ["boxing", "wrestling", "martial arts", "brawl", "fighting", "self defense"],
    "ranged weapons": ["shooting", "rifle", "gun", "archery", "bow", "marksmanship", "hunting"],
    "shields": ["shield", "riot", "defensive line"],
    "spellcasting": ["magic", "fantasy", "imagination", "visualization", "meditation", "creative focus"],
    "athletics": ["athlete", "sports", "running", "climbing", "lifting", "swimming", "gym"],
    "survival": ["camping", "camped", "hiking", "hiked", "bushcraft", "wilderness", "foraging", "hunting", "fishing", "survival", "fire", "water", "set camp", "avoid getting lost"],
    "stealth": ["sneak", "stealth", "hide", "hunting", "quiet", "scout", "stalking"],
    "investigation": ["detective", "research", "analysis", "analyst", "details", "troubleshoot", "investigate"],
    "communication": ["sales", "teacher", "manager", "leadership", "negotiation", "customer service", "counseling"],
    "tactics": ["strategy", "chess", "military", "games", "planning", "leadership", "tactics"],
    "smithing": ["metal", "mechanic", "machinist", "welding", "blacksmith", "engineering", "tools"],
    "woodworking": ["woodworking", "carpentry", "carpenter", "whittling", "furniture"],
    "leatherworking": ["leather", "sewing", "tailor", "costume", "repair clothes"],
    "alchemy": ["chemistry", "pharmacy", "lab", "cooking", "cooked", "herbalism", "medicine"],
    "enchanting": ["electronics", "engineering", "programming", "runes", "magic items", "crafting"],
    "medicine": ["doctor", "nurse", "medic", "emt", "paramedic", "first aid", "air force", "army", "medical"],
    "animal handling": ["animals", "veterinary", "vet", "horses", "farm", "pets", "dog training"],
    "slight of hand": ["sleight", "lockpick", "magic tricks", "pickpocket", "fine motor", "juggling"],
    "research": ["research", "library", "study", "scholar", "academic", "reading", "programmer", "engineer"]
}

class CharacterCreator:
    def __init__(self):
        self.race_data = self._load_race_data()
        self.backgrounds = self._load_backgrounds()
        self.world_canon = self._load_world_canon()
        self.skill_definitions = self._load_skill_definitions()
    
    def _load_race_data(self) -> Dict:
        """Load race data from file or use defaults."""
        try:
            with open(RACE_DATA_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return DEFAULT_RACE_DATA
    
    def _load_backgrounds(self) -> List[str]:
        """Load available backgrounds from file or use defaults."""
        try:
            with open(BACKGROUNDS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return DEFAULT_BACKGROUNDS
    
    def _load_world_canon(self) -> Dict:
        """Load world canon rules for character creation."""
        # This would be loaded from a file in a real implementation
        return {
            "forbidden_race_gender_combinations": [],
            "forbidden_backgrounds": [],
            "required_background_elements": []
        }

    def _load_skill_definitions(self) -> Dict[str, List[str]]:
        """Load skills and their stat sources from references/skills.csv."""
        skills: Dict[str, List[str]] = {}
        try:
            with open(path_config.skills_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    name = row.get("skill_name", "").strip().lower()
                    stats = [
                        stat.strip().title()
                        for stat in row.get("stats_used", "").replace('"', "").split(",")
                        if stat.strip()
                    ]
                    if name and stats:
                        skills[name] = stats
        except Exception as e:
            print(f"Warning: Failed to load skills.csv: {e}")

        return skills or {
            "melee weapons": ["Str", "Agi"],
            "ranged weapons": ["Str", "Agi"],
            "spellcasting": ["Crea", "Will"],
            "survival": ["Ins", "Vit"],
            "communication": ["Crea", "Ins"],
            "smithing": ["Crea", "Str"],
        }
    
    def validate_name(self, name: str) -> Optional[str]:
        """Validate character name."""
        if not name or len(name) < 2:
            return "Name must be at least 2 characters long."
        
        if not re.match(r'^[a-zA-Z\-\'\s]+$', name):
            return "Name contains invalid characters. Only letters, spaces, hyphens, and apostrophes are allowed."
        
        return None
    
    def validate_gender(self, race: str, gender: str) -> Optional[str]:
        """Validate gender choice for selected race."""
        if race not in self.race_data:
            return f"Unknown race: {race}"
        
        allowed_genders = self.race_data[race].get("allowed_genders", [])
        if gender not in allowed_genders:
            return f"Gender '{gender}' is not allowed for {race} race. Allowed: {', '.join(allowed_genders)}"
        
        # Check world canon restrictions
        forbidden_combo = f"{race}_{gender}"
        if forbidden_combo in self.world_canon.get("forbidden_race_gender_combinations", []):
            return f"The combination of {race} and {gender} gender violates world canon."
        
        return None
    
    def validate_race(self, race: str) -> Optional[str]:
        """Validate race choice."""
        if race not in self.race_data:
            available_races = list(self.race_data.keys())
            return f"Invalid race. Available races: {', '.join(available_races)}"
        
        return None
    
    def validate_background(self, race: str, background: str) -> Optional[str]:
        """Validate background choice."""
        # Check if background is forbidden for this race
        forbidden_key = f"{race}_{background}"
        if forbidden_key in self.world_canon.get("forbidden_backgrounds", []):
            return f"The background '{background}' is not allowed for {race} race."
        
        # Check required elements for certain backgrounds
        required_elements = self.world_canon.get("required_background_elements", {})
        if background in required_elements:
            missing = [elem for elem in required_elements[background] if elem not in background.lower()]
            if missing:
                return f"Background '{background}' must include: {', '.join(missing)}"
        
        return None
    
    def validate_class_theme(self, class_theme: str) -> Optional[str]:
        """Validate class theme."""
        if not class_theme or len(class_theme) < 5:
            return "Class theme must be at least 5 characters long and descriptive."
        
        if len(class_theme) > 100:
            return "Class theme is too long. Please keep it under 100 characters."
        
        return None
    
    def calculate_base_stats(self, race: str, gender: str) -> Dict[str, int]:
        """Calculate base stats for character."""
        race_data = self.race_data[race]
        base_stats = race_data["base_stats"].copy()
        
        # Apply gender modifiers
        gender_mods = race_data["gender_modifiers"].get(gender, {})
        for stat, mod in gender_mods.items():
            base_stats[stat] = min(base_stats[stat] + mod, race_data["max_stats"][stat])
        
        return base_stats
    
    def validate_stat_allocation(self, base_stats: Dict[str, int],
                                  race: str, allocations: Dict[str, int]) -> Optional[str]:
        """Validate guided stat adjustments."""
        race_data = self.race_data[race]
        max_stats = race_data["max_stats"]

        total_points = sum(allocations.values())
        if total_points < 0 or total_points > 4:
            return f"Guided stat adjustments must total between +0 and +4. Current total: {total_points}."

        for stat, points in allocations.items():
            if stat not in base_stats:
                return f"Invalid stat: {stat}"

            if points < -2 or points > 2:
                return f"Guided stat adjustment for {stat} must be between -2 and +2."

            new_value = base_stats[stat] + points
            if new_value > max_stats[stat]:
                return f"{stat} cannot exceed racial maximum of {max_stats[stat]} (would be {new_value})."
            if new_value < 1:
                return f"{stat} cannot be reduced below 1."
        
        return None

    def validate_age(self, age: Optional[int]) -> Optional[str]:
        """Validate player-provided age."""
        if age is None:
            return None
        try:
            numeric_age = int(age)
        except (TypeError, ValueError):
            return "Age must be a whole number."
        if numeric_age < 1 or numeric_age > 120:
            return "Age must be between 1 and 120."
        return None

    def _normalize_age(self, age: Optional[int]) -> int:
        """Return a saved age, defaulting legacy callers to 18."""
        return 18 if age is None else int(age)

    def _phrase_score(self, text: str, keywords: List[str]) -> int:
        """Count rough keyword/phrase matches in freeform guided answers."""
        lowered = text.lower()
        return sum(1 for keyword in keywords if keyword in lowered)

    def _normalize_stat_adjustments(self, scores: Dict[str, int]) -> Dict[str, int]:
        """Convert raw stat scores into bounded -2..+2 adjustments totaling +0..+4."""
        adjustments = {stat: max(-2, min(2, score)) for stat, score in scores.items()}

        while sum(adjustments.values()) > 4:
            positives = [stat for stat, value in adjustments.items() if value > 0]
            if not positives:
                break
            stat = max(positives, key=lambda key: (adjustments[key], key))
            adjustments[stat] -= 1

        while sum(adjustments.values()) < 0:
            negatives = [stat for stat, value in adjustments.items() if value < 0]
            if negatives:
                stat = min(negatives, key=lambda key: (adjustments[key], key))
                adjustments[stat] += 1
            else:
                break

        return adjustments

    def _normalize_skill_bonuses(self, scores: Dict[str, int]) -> Dict[str, float]:
        """Convert skill evidence into max-10 starting skill bonuses, max +2 each."""
        allowed = set(self.skill_definitions)
        ranked = sorted(
            (
                (skill, min(2, max(0, score)))
                for skill, score in scores.items()
                if skill in allowed and score > 0
            ),
            key=lambda item: (item[1], item[0]),
            reverse=True
        )

        bonuses: Dict[str, float] = {}
        remaining = 10
        for skill, score in ranked:
            if remaining <= 0:
                break
            value = min(score, remaining)
            bonuses[skill] = float(value)
            remaining -= value
        return bonuses

    def _answer_known_facts(self, guided_answers: Dict[str, str]) -> List[str]:
        """Store each guided answer as a durable known fact for later AI context."""
        facts = []
        for question in GUIDED_CREATION_QUESTIONS:
            answer = " ".join(str(guided_answers.get(question["id"], "")).split()).strip()
            if answer:
                facts.append(f"{GUIDED_QUESTION_LABELS[question['id']]}: {answer}")
        return facts

    def _summarize_guided_background(self, name: str, gender: str,
                                     guided_answers: Dict[str, str]) -> str:
        """Create a compact one-sentence background from guided answers."""
        occupation = self._third_person_fragment(guided_answers.get("occupation", ""))
        hobbies = self._third_person_fragment(guided_answers.get("hobbies", ""))
        emergency = self._third_person_fragment(guided_answers.get("emergency_response", ""))
        weakness = self._third_person_fragment(guided_answers.get("weaknesses", ""))

        pronoun = "They"
        if gender == "male":
            pronoun = "He"
        elif gender == "female":
            pronoun = "She"

        pieces = []
        if occupation:
            if occupation.lower().startswith(("worked ", "served ", "studied ")):
                pieces.append(occupation)
            else:
                article = self._article_for(occupation)
                pieces.append(f"worked as {article + ' ' if article else ''}{occupation}")
        if hobbies:
            pieces.append(f"was shaped by {hobbies}")
        if emergency:
            pieces.append(f"responded to pressure by {emergency}")
        if weakness:
            pieces.append(f"struggled with {weakness}")
        if not pieces:
            pieces.append("lived an ordinary life with no single defining specialty")
        return f"{pronoun} " + ", ".join(pieces[:4]).rstrip(".") + " before being pulled into Elyndor."

    def _clean_answer(self, answer: Any, max_chars: int = 140) -> str:
        clean = " ".join(str(answer or "").split()).strip()
        if len(clean) > max_chars:
            clean = clean[:max_chars - 3].rstrip() + "..."
        return clean

    def _third_person_fragment(self, answer: Any) -> str:
        """Turn a short first-person answer into a background-friendly fragment."""
        clean = self._clean_answer(answer)
        replacements = [
            (r"^i was an? ", ""),
            (r"^i worked as an? ", ""),
            (r"^i worked in ", "worked in "),
            (r"^i am an? ", ""),
            (r"^i am ", ""),
            (r"^i can ", "could "),
            (r"^i stay ", "stayed "),
            (r"^i ", ""),
            (r"\bi panic\b", "panicked"),
            (r"\bi keep\b", "kept"),
            (r"\bi take\b", "took"),
            (r"\bmy\b", "their"),
            (r"\bme\b", "them"),
            (r"\bi\b", "they"),
        ]
        lowered = clean
        for pattern, replacement in replacements:
            lowered = re.sub(pattern, replacement, lowered, flags=re.IGNORECASE)
        return lowered.strip(" .")

    def _article_for(self, text: str) -> str:
        text = text.strip().lower()
        if not text:
            return ""
        if text.startswith(("a ", "an ", "the ")):
            return ""
        return "an" if text[0] in "aeiou" else "a"

    def interpret_guided_answers(self, guided_answers: Dict[str, str]) -> Dict[str, Any]:
        """Interpret guided freeform answers into bounded stats, skills, and facts."""
        combined = "\n".join(str(value or "") for value in guided_answers.values())
        stat_scores = {stat: 0 for stat in ["Str", "Agi", "Vit", "Ins", "Will", "Crea"]}
        skill_scores = {skill: 0 for skill in self.skill_definitions}

        for stat, keywords in STAT_KEYWORDS.items():
            stat_scores[stat] += min(3, self._phrase_score(combined, keywords))
        for stat, keywords in LOW_STAT_KEYWORDS.items():
            stat_scores[stat] -= min(2, self._phrase_score(combined, keywords))

        weakness_text = str(guided_answers.get("weaknesses", "")).lower()
        for stat, keywords in STAT_KEYWORDS.items():
            if self._phrase_score(weakness_text, keywords):
                stat_scores[stat] -= 1
        for stat, keywords in LOW_STAT_KEYWORDS.items():
            if self._phrase_score(weakness_text, keywords):
                stat_scores[stat] -= 1

        for skill, keywords in SKILL_KEYWORDS.items():
            if skill not in skill_scores:
                continue
            score = self._phrase_score(combined, keywords)
            if score:
                skill_scores[skill] += min(3, score)

        return {
            "stat_adjustments": self._normalize_stat_adjustments(stat_scores),
            "skill_bonuses": self._normalize_skill_bonuses(skill_scores),
            "known_facts": self._answer_known_facts(guided_answers),
            "raw_stat_scores": stat_scores,
            "raw_skill_scores": skill_scores,
        }
    
    def create_character(self, name: str, gender: str, race: str,
                         background: str, class_theme: str,
                         stat_allocations: Dict[str, int],
                         skill_bonuses: Optional[Dict[str, float]] = None,
                         known_facts: Optional[List[str]] = None,
                         age: Optional[int] = None) -> Dict[str, Any]:
        """Create a new character with validated inputs."""
        # Validate all inputs
        name_error = self.validate_name(name)
        if name_error:
            return {"success": False, "error": name_error, "field": "name"}

        age_error = self.validate_age(age)
        if age_error:
            return {"success": False, "error": age_error, "field": "age"}
        
        race_error = self.validate_race(race)
        if race_error:
            return {"success": False, "error": race_error, "field": "race"}
        
        gender_error = self.validate_gender(race, gender)
        if gender_error:
            return {"success": False, "error": gender_error, "field": "gender"}
        
        background_error = self.validate_background(race, background)
        if background_error:
            return {"success": False, "error": background_error, "field": "background"}
        
        class_theme_error = self.validate_class_theme(class_theme)
        if class_theme_error:
            return {"success": False, "error": class_theme_error, "field": "class_theme"}
        
        # Calculate base stats and validate allocations
        base_stats = self.calculate_base_stats(race, gender)
        allocation_error = self.validate_stat_allocation(base_stats, race, stat_allocations)
        if allocation_error:
            return {"success": False, "error": allocation_error, "field": "stat_allocations"}
        
        # Calculate final stats
        final_stats = base_stats.copy()
        for stat, points in stat_allocations.items():
            final_stats[stat] += points

        skills = self._calculate_initial_skills(final_stats, background)
        for skill, value in (skill_bonuses or {}).items():
            skill_name = str(skill).strip().lower()
            if skill_name in skills:
                skills[skill_name] = min(2.0, max(0.0, float(value)))
        
        # Create character data
        character = {
            "identity": {
                "name": name,
                "gender": gender,
                "race": race,
                "background": background,
                "class_theme": class_theme,
                "reputation": 0,
                "title": "",
                "age": self._normalize_age(age),
                "known_facts": known_facts or []
            },
            "stats": final_stats,
            "skills": skills,
            "derived": self._calculate_derived_attributes(final_stats),
            "inventory": {},
            "equipment": {},
            "gold": 50
        }
        
        return {
            "success": True,
            "character": character,
            "message": "Character created successfully!"
        }

    def create_character_from_guided_answers(self, name: str, gender: str, race: str,
                                             guided_answers: Dict[str, str],
                                             class_theme: str = "Isekai Adventurer",
                                             age: Optional[int] = None) -> Dict[str, Any]:
        """Create a character from guided life-history answers."""
        interpretation = self.interpret_guided_answers(guided_answers)
        background = self._summarize_guided_background(name, gender, guided_answers)
        result = self.create_character(
            name=name,
            gender=gender,
            race=race,
            background=background,
            class_theme=class_theme,
            stat_allocations=interpretation["stat_adjustments"],
            skill_bonuses=interpretation["skill_bonuses"],
            known_facts=interpretation["known_facts"],
            age=age,
        )
        if result.get("success"):
            result["guided_creation"] = interpretation
            result["character"]["identity"]["guided_creation"] = {
                "stat_adjustments": interpretation["stat_adjustments"],
                "skill_bonuses": interpretation["skill_bonuses"],
            }
        return result
    
    def _calculate_initial_skills(self, stats: Dict[str, int], background: str) -> Dict[str, float]:
        """Initialize all references/skills.csv skills at zero."""
        return {skill_name: 0.0 for skill_name in self.skill_definitions}
    
    def _calculate_derived_attributes(self, stats: Dict[str, int]) -> Dict[str, float]:
        """Calculate derived attributes from base stats."""
        maxima = calculate_scaled_hp_mp_max(stats)
        max_hp = maxima["HP_max"]
        max_mp = maxima["MP_max"]
        return {
            "HP": max_hp,
            "HP_max": max_hp,
            "MP": max_mp,
            "MP_max": max_mp,
            "AC": 10 + stats["Agi"] // 2,
            "Initiative": stats["Agi"] + stats["Ins"] // 2,
            "Carry_Capacity": stats["Str"] * 10
        }
    
    def get_available_races(self) -> List[str]:
        """Get list of available races."""
        return list(self.race_data.keys())
    
    def get_race_info(self, race: str) -> Optional[Dict]:
        """Get detailed information about a race."""
        return self.race_data.get(race)
    
    def get_suggested_backgrounds(self, race: str) -> List[str]:
        """Get backgrounds commonly associated with a race."""
        race_info = self.race_data.get(race, {})
        common_backgrounds = race_info.get("common_backgrounds", [])
        
        # Combine with general backgrounds
        all_backgrounds = list(set(common_backgrounds + self.backgrounds))
        
        # Sort by relevance (common ones first)
        return sorted(all_backgrounds, key=lambda x: 0 if x in common_backgrounds else 1)
    
    def get_base_stats_for_race_gender(self, race: str, gender: str) -> Optional[Dict[str, int]]:
        """Get base stats for a race/gender combination."""
        if race not in self.race_data:
            return None
        
        return self.calculate_base_stats(race, gender)
    
    def get_stat_allocation_rules(self) -> Dict:
        """Get rules for stat allocation."""
        return {
            "total_points": 6,
            "max_per_stat": 3,
            "requires_justification": "Each increase beyond +1 must be narratively justified"
        }

# Example usage and testing
if __name__ == "__main__":
    creator = CharacterCreator()
    
    print("=== Character Creation System ===")
    print(f"Available races: {', '.join(creator.get_available_races())}")
    
    # Example character creation
    example_char = creator.create_character(
        name="Eldrin",
        gender="male", 
        race="elf",
        background="Forest guide and amateur mage",
        class_theme="Arcane Ranger - blending nature magic with woodland survival",
        stat_allocations={"Str": 0, "Agi": 1, "Vit": 0, "Ins": 1, "Will": 0, "Crea": 2},
        skill_bonuses={"survival": 2, "spellcasting": 1, "research": 1},
        known_facts=["Former occupation: Forest guide and amateur mage."],
        age=24
    )
    
    if example_char["success"]:
        print("\n=== Created Character ===")
        print(json.dumps(example_char["character"], indent=2))
    else:
        print(f"\nCharacter creation failed: {example_char['error']}")
