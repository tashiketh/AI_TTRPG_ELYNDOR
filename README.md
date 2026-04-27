# Isekai RPG

Local AI-driven TTRPG prototype with a Flask web UI and Mistral-powered DM responses.

## Setup

Use the bundled Python runtime available in Codex Desktop, or any Python 3.12 install:

```powershell
& 'C:\Users\joeal\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pip install -r requirements.txt
```

Set `MISTRAL_API_KEY` to enable live DM responses. Without it, the game uses a safe fallback response and does not call the network.

```powershell
$env:MISTRAL_API_KEY = 'your-key-here'
```

## Run

```powershell
& 'C:\Users\joeal\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' main.py
```

The web UI opens at `http://127.0.0.1:5000`.

## Test

```powershell
& 'C:\Users\joeal\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -q
```
