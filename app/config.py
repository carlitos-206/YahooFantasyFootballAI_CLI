import os
from dataclasses import dataclass
from dotenv import load_dotenv
load_dotenv()

@dataclass
class Settings:
    league_id: str
    db_path: str
    poll_interval_min: int

def load_settings():
    return Settings(
        league_id=os.getenv("YAHOO_LEAGUE_ID",""),
        db_path=os.getenv("DB_PATH","./data/cache.sqlite"),
        poll_interval_min=int(os.getenv("POLL_INTERVAL_MIN","5")),
    )
