#!/usr/bin/env python3
"""
New Game Creator - Interactive character creation interface
Handles the complete new game setup flow
"""

import sys
import os
import json
from pathlib import Path
from typing import Dict, Any, Optional

# Add the current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

from character_creation_sequence import create_character_from_guided_answers, prompt_for_age
from character_creation import GUIDED_CREATION_QUESTIONS
from ai_opening_scene import get_opening_scene_text, get_character_creation_text
from game_engine import GameEngine

def show_welcome_screen():
    """Display the welcome screen and game introduction"""
    print("""
╔════════════════════════════════════════════════════════════╗
║     🌟 ISEKAI RPG - NEW ADVENTURE CREATOR 🌟              ║
╚════════════════════════════════════════════════════════════╝

""")
    print(get_character_creation_text())

def get_character_basics() -> Dict[str, Any]:
    """Get basic character information from user"""
    print("\n📋 CHARACTER CREATION")
    print("=" * 50)
    
    # Name
    name = input("Enter your character's name: ").strip()
    if not name:
        name = "Aburi"  # Default name from the story
        print(f"Using default name: {name}")

    age = prompt_for_age()
    
    # Gender
    print("\nSelect gender:")
    print("1. Male")
    print("2. Female")
    gender_choice = input("Enter choice (1-2): ").strip()
    gender_map = {"1": "male", "2": "female"}
    gender = gender_map.get(gender_choice, "male")
    print(f"Gender: {gender}")
    
    # Race
    print("\nSelect race:")
    print("1. Human - default")
    print("2. Elf - Graceful and rare")
    print("3. Dwarf - Sturdy stubborn")
    print("4. Beastfolk - Hard mode")
    print("5. Nekko - Sleek and agile")
    print("6. Demon - Evil Destroyer")
    race_choice = input("Enter choice (1-6): ").strip()
    race_map = {"1": "human", "2": "elf", "3": "dwarf", "4": "beastfolk", "5": "nekko", "6": "demon"}
    race = race_map.get(race_choice, "human")
    print(f"Race: {race}")
    
    return {"name": name, "age": age, "gender": gender, "race": race}

def get_guided_answers() -> Dict[str, str]:
    """Get guided previous-life answers from user."""
    print("\n📝 YOUR PREVIOUS LIFE")
    print("=" * 50)
    print("Answer these naturally. The system will create bounded stat adjustments,")
    print("starting skill bonuses, a one-sentence background, and known facts.")

    answers: Dict[str, str] = {}
    for question in GUIDED_CREATION_QUESTIONS:
        answer = input(f"\n{question['prompt']}\n> ").strip()
        answers[question["id"]] = answer

    if not any(answers.values()):
        answers["occupation"] = "I was living a normal life with no particular distinguishing features."
        print("Using default previous life: ordinary, with no single defining specialty.")
    return answers

def confirm_character(character_data: Dict[str, Any]) -> bool:
    """Display character summary and get confirmation"""
    print("\n🎭 YOUR CHARACTER")
    print("=" * 50)
    print(f"Name: {character_data['identity']['name']}")
    print(f"Gender: {character_data['identity']['gender']}")
    print(f"Race: {character_data['identity']['race']}")
    print(f"Age: {character_data['identity']['age']}")
    
    print(f"\n📊 STATS:")
    for stat, value in character_data['stats'].items():
        print(f"  {stat}: {value:.1f}")
    
    print(f"\n💪 DERIVED ATTRIBUTES:")
    for attr, value in character_data['derived'].items():
        if isinstance(value, float):
            print(f"  {attr}: {value:.1f}")
        else:
            print(f"  {attr}: {value}")

    starting_skills = {
        skill: value
        for skill, value in character_data.get("skills", {}).items()
        if isinstance(value, (int, float)) and value > 0
    }
    if starting_skills:
        print("\n🛠 STARTING SKILLS:")
        for skill, value in sorted(starting_skills.items()):
            print(f"  {skill}: +{value:g}")

    known_facts = character_data.get("identity", {}).get("known_facts", [])
    if known_facts:
        print("\n🧠 KNOWN FACTS:")
        for fact in known_facts:
            print(f"  - {fact}")
    
    print("\n✅ Character creation complete!")
    
    while True:
        confirm = input("\nDo you want to start your adventure with this character? (y/n): ").strip().lower()
        if confirm in ['y', 'yes']:
            return True
        elif confirm in ['n', 'no']:
            return False
        else:
            print("Please enter 'y' or 'n'")

def create_and_start_new_game():
    """Complete new game creation and start the game"""
    try:
        # Show welcome and get character info
        show_welcome_screen()
        basics = get_character_basics()
        guided_answers = get_guided_answers()
        
        # Create character
        print("\n🎲 CREATING YOUR CHARACTER...")
        character = create_character_from_guided_answers(
            name=basics["name"],
            gender=basics["gender"],
            race=basics["race"],
            guided_answers=guided_answers,
            age=basics["age"],
        )
        
        # Confirm character
        if not confirm_character(character):
            print("\n❌ Character creation cancelled.")
            return False
        
        # Initialize game engine and start new game
        print("\n🚀 STARTING YOUR ADVENTURE...")
        engine = GameEngine(start_web=False)
        
        # Start the game
        result = engine.start_new_game({"character": character})
        
        if result.get("success"):
            print(f"\n🎉 Game started successfully!")
            print(f"Welcome to Elyndor, {character['identity']['name']}!")
            print(f"Your adventure begins in {result.get('location', 'a mysterious land')}...")
            return True
        else:
            print(f"\n❌ Failed to start game: {result.get('error', 'Unknown error')}")
            return False
            
    except Exception as e:
        print(f"\n❌ Error during game creation: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main entry point"""
    print("🌟 ISEKAI RPG - NEW GAME CREATOR 🌟")
    print("=" * 50)
    
    success = create_and_start_new_game()
    
    if success:
        print("\n🎮 Game is now running! You can continue your adventure.")
        print("Next time you run the game, it will detect your saved progress.")
    else:
        print("\n💔 Game creation failed. Please try again.")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
