from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime

from app.db import Base


class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True)

    conversation_id = Column(String, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)

    conditions = Column(JSON, nullable=True)
    active_drugs = Column(JSON, nullable=True)
    intent = Column(String, nullable=True)
    mode = Column(String, nullable=True)

    visualizations_json = Column(Text, nullable=True)

    timestamp = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")
