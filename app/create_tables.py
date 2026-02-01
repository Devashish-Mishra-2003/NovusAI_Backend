# app/create_tables.py

import os
import sys
# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import Base, engine
from app.models.auth import Company, User
from app.models.chat import ChatHistory

print("Creating database tables...")
Base.metadata.create_all(bind=engine)
print("Tables created successfully: companies, users, chat_history")
print("Database file: ./novusai.db")