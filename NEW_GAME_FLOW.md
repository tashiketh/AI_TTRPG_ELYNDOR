# New Game Creation Flow

## 🎮 How to Start a New Game

### Option 1: Automatic Flow (Recommended)
Simply run:
```bash
python main.py
```

The system will:
1. Check if `logs/game_state.json` exists
2. If no game exists → automatically launch the character creator
3. After character creation → start the game engine
4. Next time you run → it will continue your existing game

### Option 2: Manual Character Creation
Run the character creator directly:
```bash
python new_game_creator.py
```

Then start the game:
```bash
python game_engine.py
```

### Option 3: Quick Test
Test just the character creation without starting the game:
```bash
python character_creation_sequence.py
```

## 📝 New Game Creation Process

1. **Welcome Screen** - Shows the isekai opening narrative
2. **Character Basics** - Enter name, gender, and race
3. **Backstory** - Describe your previous life (affects stats)
4. **Character Preview** - Review your stats and attributes
5. **Confirmation** - Confirm and start your adventure
6. **Game Initialization** - Game engine starts with your character

## 🎭 Character Creation Features

### Name
- Enter any name you want
- Default: "Aburi" (from the story)

### Gender Options
- Male
- Female  
- Other

### Race Options
- **Human** - Versatile and adaptable
- **Elf** - Graceful with magical affinity
- **Dwarf** - Sturdy and resilient
- **Beastfolk** - Agile and instinctive
- **Demon** - Powerful but feared

### Backstory Tips
Your backstory affects your starting stats (6 bonus points):
- **Strength**: "strong", "athlete", "warrior", "labor", "build", "fight"
- **Agility**: "fast", "agile", "dancer", "runner", "acrobat", "thief"
- **Vitality**: "tough", "endurance", "survival", "health", "stamina"
- **Insight**: "smart", "studied", "research", "scholar", "intelligent"
- **Will**: "determined", "willpower", "focus", "discipline", "mental"
- **Creativity**: "creative", "artist", "music", "imagine", "invent"

### Example Backstories
- "I was a professional athlete who trained daily and competed in marathons" → +Str, +Vit, +Agi
- "I was a software engineer who enjoyed chess and strategy games" → +Ins, +Will, +Crea
- "I was a musician who performed nightly and practiced yoga" → +Crea, +Agi, +Will

## 📁 Game Save Location

Your game progress is saved to:
```
logs/game_state.json
```

This file contains:
- Player character data
- NPC relationships and states
- Quest progress
- Inventory items
- World location and state

## 🔄 Continuing Your Game

Once you've created a game, simply run:
```bash
python main.py
```

The system will detect your saved game and continue automatically!

## ⚠️ Troubleshooting

**Issue**: Game doesn't start after character creation
**Solution**: Make sure `logs/game_state.json` was created

**Issue**: Want to start over
**Solution**: Delete `logs/game_state.json` and run `python main.py` again

**Issue**: Character stats seem wrong
**Solution**: Check your backstory for relevant keywords or try a different description

## 🎉 Enjoy Your Adventure!

The game now properly handles:
- ✅ New game creation with interactive character setup
- ✅ Continuing existing games automatically
- ✅ Backstory-based stat allocation (6 bonus points)
- ✅ Proper game state saving and loading
- ✅ Graceful handling of missing game files
