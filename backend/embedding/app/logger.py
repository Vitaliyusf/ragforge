"""Logging utilities for the embedding service."""
import json
import os
import time
from typing import Dict, Any, Optional


class ServiceLogger:
    """Structured logging for the embedding service."""
    
    def __init__(self, service_name: str = "embedding", log_dir: Optional[str] = None):
        """Initialize the logger."""
        self.service_name = service_name
        
        if log_dir is None:
            current_file = os.path.abspath(__file__)
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
            log_dir = os.getenv("LOG_DIR", os.path.join(project_root, "logs"))
        
        os.makedirs(log_dir, exist_ok=True)
        self.log_path = os.path.join(log_dir, f"{service_name}_service.log")
    
    def log(
        self, 
        location: str, 
        message: str, 
        data: Optional[Dict[str, Any]] = None, 
        hypothesis_id: str = "A"
    ) -> None:
        """Write a log entry."""
        try:
            log_entry = {
                "service": self.service_name,
                "location": location,
                "message": message,
                "data": data or {},
                "hypothesisId": hypothesis_id,
                "timestamp": int(time.time() * 1000)
            }
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception:
            pass
