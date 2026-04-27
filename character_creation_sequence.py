#!/usr/bin/env python3
"""
Character creation sequence for the Isekai RPG
Handles the full character creation flow from basic info to final character
"""
import sys
import os
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add the current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))
from character_creation import CharacterCreator, GUIDED_CREATION_QUESTIONS
from api_integration import APIManager

def get_opening_narrative() -> str:
    """Return the opening narrative for character creation"""
    return """

You were going about your normal life, following your daily routine, when suddenly...
A blinding light engulfs you. The world around you distorts and twists. Sounds become muffled,
then disappear entirely. You feel weightless, as if floating in an endless void.

You are in between worlds, and soon your old life will be but a distant memory.

Before you stands a new path, a new destiny. But first, you must remember who you were...
"""

def create_character_from_backstory(name: str, gender: str, race: str,
                                    backstory: str, age: Optional[int] = None) -> Dict[str, Any]:
    """
    Backward-compatible wrapper that treats an old freeform backstory as guided input.
    """
    return create_character_from_guided_answers(
        name=name,
        gender=gender,
        race=race,
        guided_answers={
            "occupation": backstory,
            "hobbies": "",
            "emergency_response": "",
            "wilderness_survival": "",
            "strengths": "",
            "weaknesses": "",
            "personal_flaw": "",
        },
        age=age,
    )

def create_character_from_guided_answers(name: str, gender: str, race: str,
                                         guided_answers: Dict[str, str],
                                         age: Optional[int] = None) -> Dict[str, Any]:
    """Create a character from guided creation answers."""
    print(f"\n📜 Creating character: {name}")
    print(f"Gender: {gender}, Race: {race}")

    creator = CharacterCreator()
    result = creator.create_character_from_guided_answers(
        name=name,
        gender=gender,
        race=race,
        guided_answers=guided_answers,
        class_theme="Isekai Adventurer",
        age=age,
    )
    if result["success"]:
        print(f"✅ Character created successfully!")
        guided = result.get("guided_creation", {})
        print(f"Stat adjustments: {guided.get('stat_adjustments', {})}")
        print(f"Skill bonuses: {guided.get('skill_bonuses', {})}")
        print(f"Final stats: {result['character']['stats']}")
        return result["character"]
    else:
        print(f"❌ Character creation failed: {result['error']}")
        fallback_result = CharacterCreator().create_character(
            name=name,
            gender=gender,
            race=race,
            background="They lived an ordinary life before being pulled into Elyndor.",
            class_theme="Isekai Adventurer",
            stat_allocations={"Str": 0, "Agi": 0, "Vit": 0, "Ins": 0, "Will": 0, "Crea": 0},
            age=age,
        )
        return fallback_result["character"]

def prompt_for_age(default: int = 18) -> int:
    """Prompt for a player age and keep asking until it is valid."""
    while True:
        raw = input(f"Enter your character's age [{default}]: ").strip()
        if not raw:
            return default
        try:
            age = int(raw)
        except ValueError:
            print("Please enter age as a whole number.")
            continue
        if 1 <= age <= 120:
            return age
        print("Please enter an age between 1 and 120.")

def collect_guided_answers() -> Dict[str, str]:
    """Ask guided life-history questions."""
    print("\n📝 Step 3: Your Previous Life")
    print("-" * 40)
    print("Answer in a sentence or two. These answers become known facts the game can reference later.")
    answers: Dict[str, str] = {}
    for question in GUIDED_CREATION_QUESTIONS:
        answer = input(f"\n{question['prompt']}\n> ").strip()
        answers[question["id"]] = answer
    return answers

def run_character_creation_sequence():
    """Run the complete character creation sequence"""
    print("🎭 Isekai Character Creation")
    print("=" * 50)
    # Step 1: Get basic information
    print("\n📋 Step 1: Basic Information")
    print("-" * 40)
    name = input("Enter your character's name: ").strip()
    if not name:
        name = "Stranger"  # Default name
        print(f"Using default name: {name}")
    age = prompt_for_age()
    print("Select gender:")
    print("1. Male")
    print("2. Female")
    gender_choice = input("Enter choice (1-2): ").strip()
    gender_map = {"1": "male", "2": "female"}
    gender = gender_map.get(gender_choice, "male")
    print(f"Gender: {gender}")
    print("\nSelect race:")
    print("1. Human - the default of this world")
    print("2. Elf - Rare and graceful but weak")
    print("3. Dwarf - Strong and stubborn")
    print("4. Beastfolk - Beastial and wild, a difficult path")
    print("5. Nekko - Sleek and agile (WARNING - the hardest path!)")
    print("6. Demon - Evil destroyer")
    race_choice = input("Enter choice (1-6): ").strip()
    race_map = {"1": "human", "2": "elf", "3": "dwarf", "4": "beastfolk", "5": "nekko", "6": "demon"}
    race = race_map.get(race_choice, "human")
    print(f"Race: {race}")
    # Step 2: Show opening narrative
    print("\n📜 Step 2: The Isekai Moment")
    print("-" * 40)
    print(get_opening_narrative())
    guided_answers = collect_guided_answers()
    # Step 4: Create character
    print("\n🎲 Step 4: Character Creation")
    print("-" * 40)
    character = create_character_from_guided_answers(name, gender, race, guided_answers, age=age)
    # Step 5: Show results
    print("\n🎉 Character Created!")
    print("=" * 50)
    print(f"Name: {character['identity']['name']}")
    print(f"Gender: {character['identity']['gender']}")
    print(f"Race: {character['identity']['race']}")
    print(f"Age: {character['identity']['age']}")
    print(f"\nStats:")
    for stat, value in character['stats'].items():
        print(f"  {stat}: {value:.1f}")
    print(f"\nDerived Attributes:")
    for attr, value in character['derived'].items():
        if isinstance(value, float):
            print(f"  {attr}: {value:.1f}")
        else:
            print(f"  {attr}: {value}")
    print("\nKnown Facts:")
    for fact in character.get("identity", {}).get("known_facts", []):
        print(f"  - {fact}")
    return character
if __name__ == "__main__":
    try:
        character = run_character_creation_sequence()
        print(f"\n🎮 Ready to begin your adventure, {character['identity']['name']}!")
    except Exception as e:
        print(f"\n❌ Character creation failed: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
