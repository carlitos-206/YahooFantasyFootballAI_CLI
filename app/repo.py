from sqlmodel import SQLModel, Field, Session, create_engine
from typing import Optional
from datetime import datetime

class Player(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    position: str
    team: Optional[str] = None
    status: Optional[str] = None  # Q / O / IR / etc.
    last_updated: datetime

class Projection(SQLModel, table=True):
    key: str = Field(primary_key=True)        # player_id|week
    player_id: str
    week: int
    proj_points: float
    floor: float
    ceiling: float
    last_updated: datetime

class Setting(SQLModel, table=True):
    k: str = Field(primary_key=True)
    v: str

class Repo:
    def __init__(self, db_path: str):
        self.engine = create_engine(f"sqlite:///{db_path}", echo=False)
        SQLModel.metadata.create_all(self.engine)

    def session(self):
        return Session(self.engine)
