# Isekai RPG

**A local, AI-powered tabletop role-playing game** built with Python and Flask.  
Experience dynamic storytelling powered by Mistral AI while playing through a full-featured TTRPG system.

> **Note:** This project is currently in active development. The world is temporarily called **Elyndor** until a more fitting name is chosen.

---

## ✨ Features

- **Full TTRPG Systems** — Character creation, combat, social encounters, crafting, quests, inventory, and exploration
- **AI-Powered Dungeon Master** — Uses Mistral AI to generate dynamic responses, scenes, NPC dialogue, and story branches in real time
- **Web-Based Interface** — Clean browser-based UI that runs locally
- **Local-First** — Everything runs on your machine. Your stories and data stay private
- **Modular & Extensible** — Well-organized codebase designed for easy expansion
- **Persistant Memory** — JSON logs provide robust and enduring memory

---

## 🚀 Quick Start

### Requirements
- Python 3.12+
- Mistral API key (free tier available) — *optional but recommended*

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/tashiketh/AI_TTRPG_ELYNDOR.git
   cd AI_TTRPG_ELYNDOR
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. (Optional) Set your Mistral API key:
   ```bash
   # Windows (PowerShell)
   $env:MISTRAL_API_KEY = "your-api-key-here"

   # macOS / Linux
   export MISTRAL_API_KEY="your-api-key-here"
   ```

4. Run the game:
   ```bash
   python main.py
   ```

5. Open your browser and go to:  
   **http://127.0.0.1:5000**

---

## 🎮 How to Play

- Create a character through the guided creation flow
- Begin your adventure with an AI-generated opening scene
- Interact using natural language
- The AI DM responds dynamically to your actions in combat, dialogue, exploration, and more

---

## 📁 Project Structure

```
AI_TTRPG_ELYNDOR/
├── core/                  # Python game systems, AI integration, and design docs
├── references/            # Game data, prompts, NPCs, items, skills, and templates
├── templates/             # Flask HTML templates
├── static/                # CSS, JavaScript, and image assets
├── logs/                  # Local save data, transcripts, and debug logs
├── tests/                 # Test and verification scripts
├── main.py                # Application entry point
├── requirements.txt
└── README.md
```

---

## 🛠️ Tech Stack

- **Backend**: Python + Flask
- **AI**: Mistral API (any LLM model can be used)
- **Frontend**: HTML, CSS, JavaScript
- **Structure**: Modular Python packages

---

## 🗺️ Current Status & Roadmap

**Current State**: Functional early prototype with working character creation, combat, AI DM, and core loops.

**Planned Improvements**:
- Testing and feedback from users
- Enhanced UI/UX and visual elements
- Better AI reasoning
- Quest development
- Expanded systems (magic, factions, etc.)

---

## 🤝 Contributing

Contributions and feedback are greatly desired!  
Feel free to open issues for bugs, feature requests, or ideas.

---

## 📜 License

This project is licensed under the **MIT License** (see `LICENSE` file).

---

## 🙏 Credits

Built with Python, Flask, every available AI model and endless trial and error!  
Inspired by Angel Sword Studios and RFAB.AI.

---

**Ready to play?** Clone the repo and run `python main.py` — feedback is very appreciated!
