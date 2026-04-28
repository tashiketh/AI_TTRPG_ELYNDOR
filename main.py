#!/usr/bin/env python3
"""
Main entry point for the Isekai RPG
Handles game startup, new game creation, and continuing existing games
"""

import sys
import os
from pathlib import Path

# Add the project and core directories to Python path.
PROJECT_ROOT = Path(__file__).resolve().parent
CORE_DIR = PROJECT_ROOT / "core"
for import_path in (CORE_DIR, PROJECT_ROOT):
    import_path_str = str(import_path)
    if import_path_str not in sys.path:
        sys.path.insert(0, import_path_str)

from game_engine import GameEngine
from path_config import path_config

def show_main_menu():
    """Show the main menu with game options"""
    print("""
╔════════════════════════════════════════════════════════════╗
║              🌟 ISEKAI RPG - MAIN MENU 🌟                ║
╚════════════════════════════════════════════════════════════╝

Welcome to the Isekai RPG - A world of magic, adventure, and destiny!
""")

def check_game_status() -> bool:
    """Check if an existing game save exists"""
    return path_config.game_state_path.exists()

def main():
    """Main entry point"""
    print("🚀 Starting Isekai RPG...")
    
    # Check if game exists
    has_existing_game = check_game_status()
    
    if has_existing_game:
        print("📁 Existing game detected!")
        print("🎮 Starting game engine...")
        
        # Start the game engine normally
        engine = GameEngine()
        
        # Keep the main thread alive
        try:
            while True:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 Shutting down...")
            sys.exit(0)
    else:
        print("📝 No existing game found.")
        print("🎭 Starting character creation...")
        
        # Run the new game creator
        import subprocess
        try:
            result = subprocess.run([
                sys.executable, str(CORE_DIR / "new_game_creator.py")
            ], check=True, capture_output=False, text=True)
            
            if result.returncode == 0:
                print("\n🎮 Game created successfully! Starting game engine...")
                # Now start the game engine
                engine = GameEngine()
                
                # Keep the main thread alive
                try:
                    while True:
                        import time
                        time.sleep(1)
                except KeyboardInterrupt:
                    print("\n🛑 Shutting down...")
                    sys.exit(0)
            else:
                print(f"\n❌ Game creation failed with code {result.returncode}")
                sys.exit(1)
                
        except subprocess.CalledProcessError as e:
            print(f"\n❌ Error running character creator: {str(e)}")
            sys.exit(1)
        except FileNotFoundError:
            print(f"\n❌ {CORE_DIR / 'new_game_creator.py'} not found. Please run it manually first.")
            sys.exit(1)

if __name__ == "__main__":
    main()
