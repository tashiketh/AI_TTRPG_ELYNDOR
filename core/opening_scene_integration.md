# Opening Scene Integration Guide

## 🎭 Your Opening Scene (Ready to Use)

Here's your dramatic opening scene formatted for integration:

```python
def show_opening_scene():
    """Display the dramatic opening scene"""
    print("""
╔════════════════════════════════════════════════════════════╗
║              🔥 YOUR AWAKENING IN ELYNDOR 🔥                ║
╚════════════════════════════════════════════════════════════╝

You awaken with a violent jolt — not from sleep, but from being torn
through reality itself.

One moment you were in your world. The next, you're slammed into damp
earth and leaf litter, gasping for breath. Your heart hammers. The air
smells of smoke, blood, and something acrid — like ozone mixed with
sulfur.

You're on a gentle forested slope. Through the bushes and trees you
have cover, but only barely.

Thirty yards down the hill, a caravan is being massacred.

Three wagons are stopped on the dirt road. Screams echo as demonic
monstrosities — hunched, grey-skinned, creatures the size of large men
with jagged-toothed and 4 arms each rip into the travelers with claws
and crude weapons. Their laughter is guttural and wet. Bodies are being
torn apart with horrifying casualness.

Above it all, circling lazily in the sky, is a winged demon — taller,
more elegant, with leathery wings and burning red eyes. It watches the
slaughter like a conductor overseeing an orchestra.

You are hidden... for now.

A slight movement just an arm's length away draws your attention.
Half-hidden by the same bushes that hide you lies a bleeding woman —
the violence of the moment doesn't blind you to her feline ears and
a tail. She's unconscious, bleeding from a gash all over her body.
Her wrists are bound with heavy iron chains. A bright red tattoo
glows faintly on the side of her neck.

As you watch, she collapses into the dirt, not yet hidden from the
slaughter. You don't know if she saw you or not, but if any of the
demons glance up the hill, they will almost certainly see her and
if you're still there, they will find you too.

💀 THE CHOICE IS YOURS 💀
""")
```

## 🔧 Integration Options

### **Option 1: Add to New Game Creator (Recommended)**

**File**: `core/new_game_creator.py`
**Location**: After character creation, before starting the game

**Add this call in `create_and_start_new_game()` function:**
```python
# After character creation, before starting game engine
print("\n🎭 YOUR AWAKENING IN ELYNDOR")
show_opening_scene()

# Get player's first choice
print("\n⚔️ WHAT WILL YOU DO?")
print("1. Try to help the bleeding woman")
print("2. Stay hidden and observe the massacre")
print("3. Run deeper into the forest to escape")
print("4. Look for weapons or anything useful nearby")

choice = input("\nEnter your choice (1-4): ").strip()

# Store this choice to pass to the game engine
initial_choice = ""
if choice == "1":
    initial_choice = "help_woman"
elif choice == "2":
    initial_choice = "stay_hidden"
elif choice == "3":
    initial_choice = "flee_deeper"
elif choice == "4":
    initial_choice = "look_for_weapons"
else:
    initial_choice = "stay_hidden"  # Default

# Pass this to game engine
game_character_data["initial_choice"] = initial_choice
```

### **Option 2: Add to Game Engine Initialization**

**File**: `core/game_engine.py`
**Location**: In the `start_new_game` method

```python
def start_new_game(self, character_data: Dict) -> Dict:
    """Start a new game with the given character."""
    
    # Show opening scene if this is a truly new game
    if not self.game_state_exists:
        print("\n" + "="*60)
        print("🔥 YOUR AWAKENING IN ELYNDOR 🔥")
        print("="*60)
        print("""
        [Your opening scene text here]
        """)
        
        # Get player's first choice
        print("\n⚔️ WHAT WILL YOU DO?")
        # ... choice handling code ...
        
        # Set initial game state based on choice
        if initial_choice == "help_woman":
            self.game_state["opening_choice"] = "helped_woman"
            self.game_state["relationships"]["mystery_woman"] = "saved"
        # ... other choices ...
    
    # Continue with normal game setup
    # ... existing code ...
```

### **Option 3: Create a Separate Opening Scene Module**

**File**: `core/opening_scene.py` (new file)

```python
#!/usr/bin/env python3
"""
Opening scene module for Isekai RPG
Handles the dramatic introduction and first player choice
"""

def show_opening_scene():
    """Display the opening scene and get player's first choice"""
    print("""
    [Your complete opening scene text]
    """)
    
    print("\n⚔️ WHAT WILL YOU DO?")
    print("1. Try to help the bleeding woman")
    print("2. Stay hidden and observe the massacre")
    print("3. Run deeper into the forest to escape")
    print("4. Look for weapons or anything useful nearby")
    
    while True:
        choice = input("\nEnter your choice (1-4): ").strip()
        if choice in ["1", "2", "3", "4"]:
            break
        print("Please enter a number between 1 and 4.")
    
    # Map choice to game action
    choice_map = {
        "1": "help_woman",
        "2": "stay_hidden", 
        "3": "flee_deeper",
        "4": "look_for_weapons"
    }
    
    return choice_map[choice]

def get_opening_scene_consequences(choice: str) -> Dict:
    """Return game consequences of opening scene choice"""
    consequences = {
        "help_woman": {
            "description": "You rush to the woman's side, trying to stop her bleeding...",
            "relationships": {"mystery_woman": "saved"},
            "starting_items": ["bloodstained_cloth"],
            "initial_location": "forest_slope",
            "stealth": -1,  # More likely to be noticed
            "compassion": +1
        },
        "stay_hidden": {
            "description": "You remain perfectly still, watching the horror unfold...",
            "relationships": {},
            "starting_items": [],
            "initial_location": "forest_slope",
            "stealth": +1,
            "trauma": +1
        },
        "flee_deeper": {
            "description": "You turn and run deeper into the forest...",
            "relationships": {"mystery_woman": "abandoned"},
            "starting_items": [],
            "initial_location": "deep_forest",
            "stealth": +1,
            "cowardice": +1
        },
        "look_for_weapons": {
            "description": "You quickly scan the area for anything useful...",
            "relationships": {"mystery_woman": "ignored"},
            "starting_items": ["rusty_dagger"],
            "initial_location": "forest_slope",
            "pragmatism": +1
        }
    }
    
    return consequences[choice]
```

## 🎯 Recommended Implementation

### **Step 1: Create the opening scene function**
Add the `show_opening_scene()` function to `core/new_game_creator.py`

### **Step 2: Modify the game creation flow**
In `create_and_start_new_game()`, add:
```python
# After character creation, show opening scene
show_opening_scene()

# Get player's first choice
initial_choice = get_player_choice()  # Implement this simple function

# Pass choice to game engine
game_character_data["opening_choice"] = initial_choice
```

### **Step 3: Modify Game Engine to handle opening choice**
In `core/game_engine.py`, modify `start_new_game()` to:
```python
def start_new_game(self, character_data: Dict) -> Dict:
    # ... existing code ...
    
    # Apply opening scene consequences
    if "opening_choice" in character_data:
        self.apply_opening_consequences(character_data["opening_choice"])
    
    # ... rest of existing code ...
```

### **Step 4: Add consequence handling**
Add this method to `GameEngine` class:
```python
def apply_opening_consequences(self, choice: str):
    """Apply consequences of opening scene choice"""
    consequences = {
        "help_woman": {
            "narrative": "You rush to the woman's side...",
            "relationships": {"mystery_woman": {"status": "saved", "trust": 2}},
            "inventory": ["bloodstained_cloth"],
            "stats": {"stealth": -1, "compassion": 1}
        },
        # ... other choices ...
    }
    
    # Apply consequences to game state
    if choice in consequences:
        conseq = consequences[choice]
        
        # Update relationships
        if "relationships" in conseq:
            for npc, rel_data in conseq["relationships"].items():
                if npc not in self.game_state["npcs"]:
                    self.game_state["npcs"][npc] = {}
                self.game_state["npcs"][npc].update(rel_data)
        
        # Add items
        if "inventory" in conseq:
            for item in conseq["inventory"]:
                if "inventory" not in self.game_state["player"]:
                    self.game_state["player"]["inventory"] = []
                self.game_state["player"]["inventory"].append(item)
        
        # Update stats
        if "stats" in conseq:
            for stat, value in conseq["stats"].items():
                if "stats" not in self.game_state["player"]:
                    self.game_state["player"]["stats"] = {}
                self.game_state["player"]["stats"][stat] = value
```

## 💡 Benefits of This Approach

1. **Immediate Engagement**: Players start with action, not exposition
2. **Meaningful Choices**: First decision impacts relationships and gameplay
3. **World Building**: Establishes the tone (dark, urgent, dangerous)
4. **Character Definition**: Shows who your character is through action
5. **Gameplay Impact**: Choices have real consequences

## 🎮 Example First Choices & Consequences

| Choice | Immediate Effect | Long-term Consequences |
|--------|------------------|-----------------------|
| **Help woman** | Gain her trust, find clues | Potential ally, but higher risk of demon detection |
| **Stay hidden** | Remain undetected | Miss potential ally, witness important events |
| **Flee deeper** | Escape immediate danger | Miss critical information, harder to find way back |
| **Look for weapons** | Find useful items | May attract demon attention, moral ambiguity |

This creates a powerful, cinematic opening that immediately draws players into your world!
