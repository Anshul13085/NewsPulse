from pydantic import BaseModel
from typing import List

class User(BaseModel):
    email: str
    watchlist: List[str] = []  # e.g. ["Bitcoin", "Adani", "SpaceX"]