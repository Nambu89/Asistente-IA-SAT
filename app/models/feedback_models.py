from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class Feedback(BaseModel):
    message_id: str
    session_id: str
    rating: int  # 1 (pulgar abajo) o 5 (pulgar arriba)
    comment: Optional[str] = None
    model: Optional[str] = None
    question: Optional[str] = None
    answer: Optional[str] = None
    created_at: datetime = datetime.now()