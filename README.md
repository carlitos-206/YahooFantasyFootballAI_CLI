# FantasyFootballAI

A command-line Fantasy Football assistant powered by the Yahoo Fantasy Sports API.  
This tool connects to your Yahoo league, fetches live data, and provides commands to view players, manage lineups, and eventually make AI-driven trade and roster suggestions.

---

## Features
- ✅ Connects to your Yahoo Fantasy Football league using OAuth2  
- ✅ CLI commands to interact with your league (standings, players, rosters, etc.)  
- ✅ Background scheduler to poll Yahoo for updates  
- 🚧 AI-driven lineup optimization and trade suggestions (coming soon)

---

## Installation

```bash

git clone https://github.com/yourusername/FantasyFootballAI.git

cd FantasyFootballAI

python -m venv venv

source venv/bin/activate   # Mac/Linux

venv\Scripts\activate      # Windows

pip install -r requirements.txt 

```

## Setup
#### Create a Yahoo application at Yahoo Developer Network

#### Permissions: Fantasy Sports

#### Download your app credentials

#### Save credentials to data/yahoo_oauth.json (First run will guide you through login and token storage.)

## Run the CLI:

```bash
Copy code
python -m app.cli run
```
Commands
```bash
Copy code
# Fetch league standings
python -m app.cli standings
```

## List available players (filter by position)
```python -m app.cli players --pos QB```

## View your roster
```python -m app.cli roster```

## Start scheduler (fetches updates every 5 minutes)
```python -m app.cli scheduler --poll 5```

Project Structure
```
.
├── app/
│   ├── __init__.py
│   ├── brains
│   │   ├── __init__.py
│   │   ├── draft.py
│   │   └── rules.py
│   ├── cli.py
│   ├── config.py
│   ├── features.py
│   ├── formatting.py
│   ├── repo.py
│   ├── scheduler.py
│   ├── ui.py
│   ├── views.py
│   └── yahoo_client.py
├── data/
│   ├── cache.sqlite
│   └── yahoo_oauth.json
├── README.md
└── requirements.txt

```
Roadmap
 AI-based lineup optimizer (real-time NFL events)

 Trade and waiver suggestions

 Web dashboard (optional)

## License
### MIT