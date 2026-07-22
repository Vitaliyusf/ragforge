"""Factory for creating database repositories."""
from app.db.interfaces import IChatRepository, IMessageRepository
from app.db.implementations.sqlite import SQLiteChatRepository, SQLiteMessageRepository
from app.db.implementations.mongodb import MongoDBChatRepository, MongoDBMessageRepository
from app.config import MemoryConfig


class DatabaseFactory:
    """Factory for creating database repository instances."""
    
    @staticmethod
    def create_chat_repository(config: MemoryConfig) -> IChatRepository:
        """Create a chat repository instance."""
        db_type = config.db_type.lower()
        
        if db_type == "sqlite":
            return SQLiteChatRepository(config)
        elif db_type == "mongodb":
            return MongoDBChatRepository(config)
        else:
            raise ValueError(f"Unknown database type: {db_type}")
    
    @staticmethod
    def create_message_repository(config: MemoryConfig) -> IMessageRepository:
        """Create a message repository instance."""
        db_type = config.db_type.lower()
        
        if db_type == "sqlite":
            return SQLiteMessageRepository(config)
        elif db_type == "mongodb":
            return MongoDBMessageRepository(config)
        else:
            raise ValueError(f"Unknown database type: {db_type}")
