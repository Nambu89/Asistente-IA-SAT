from pydantic import BaseModel
from typing import Optional

class Message(BaseModel):
    role: str
    content: str
    timestamp: Optional[str] = None 