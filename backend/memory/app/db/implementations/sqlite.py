"""SQLite database implementation."""
import sqlite3
import os
from typing import List, Dict, Any
from datetime import datetime

from app.db.interfaces import IChatRepository, IMessageRepository
from app.config import MemoryConfig


class SQLiteChatRepository(IChatRepository):
    """SQLite implementation of chat repository."""
    
    def __init__(self, config: MemoryConfig):
        """Initialize SQLite chat repository."""
        self.config = config
        self._ensure_db_initialized()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        return sqlite3.connect(self.config.db_file)
    
    def _ensure_db_initialized(self) -> None:
        """Ensure database and tables are initialized."""
        db_dir = os.path.dirname(self.config.db_file)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Create chats table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chats (
                id TEXT PRIMARY KEY,
                title TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        ''')
        
        # Create messages table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                chat_id TEXT,
                sender TEXT,
                message TEXT,
                timestamp TEXT,
                FOREIGN KEY (chat_id) REFERENCES chats(id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def create(self, chat_id: str, title: str) -> bool:
        """Create a new chat."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            cursor.execute(
                "INSERT INTO chats (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (chat_id, title, now, now)
            )
            conn.commit()
            conn.close()
            return True
        except Exception:
            return False
    
    def get_all(self) -> List[Dict[str, Any]]:
        """Get all chats."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, title, created_at, updated_at FROM chats ORDER BY updated_at DESC")
            chats = []
            for row in cursor.fetchall():
                chats.append({
                    "id": row[0],
                    "title": row[1],
                    "created_at": row[2],
                    "updated_at": row[3]
                })
            conn.close()
            return chats
        except Exception:
            return []
    
    def delete(self, chat_id: str) -> bool:
        """Delete a chat."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
            conn.commit()
            conn.close()
            return True
        except Exception:
            return False
    
    def update_timestamp(self, chat_id: str, timestamp: str) -> bool:
        """Update chat's updated_at timestamp."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE chats SET updated_at = ? WHERE id = ?",
                (timestamp, chat_id)
            )
            conn.commit()
            conn.close()
            return True
        except Exception:
            return False


class SQLiteMessageRepository(IMessageRepository):
    """SQLite implementation of message repository."""
    
    def __init__(self, config: MemoryConfig):
        """Initialize SQLite message repository."""
        self.config = config
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        return sqlite3.connect(self.config.db_file)
    
    def create(self, message_id: str, chat_id: str, sender: str, message: str, timestamp: str) -> bool:
        """Create a new message."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO messages (id, chat_id, sender, message, timestamp) VALUES (?, ?, ?, ?, ?)",
                (message_id, chat_id, sender, message, timestamp)
            )
            conn.commit()
            conn.close()
            return True
        except Exception:
            return False
    
    def get_by_chat_id(self, chat_id: str) -> List[Dict[str, Any]]:
        """Get all messages for a chat."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, sender, message, timestamp FROM messages WHERE chat_id = ? ORDER BY timestamp ASC",
                (chat_id,)
            )
            messages = []
            for row in cursor.fetchall():
                messages.append({
                    "id": row[0],
                    "sender": row[1],
                    "message": row[2],
                    "timestamp": row[3]
                })
            conn.close()
            return messages
        except Exception:
            return []
    
    def delete_by_chat_id(self, chat_id: str) -> bool:
        """Delete all messages for a chat."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
            conn.commit()
            conn.close()
            return True
        except Exception:
            return False
