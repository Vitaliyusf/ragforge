"""Configuration management service."""
import os
import json
from typing import Dict, Any, Optional
from pathlib import Path

from app.core.logging_config import ServiceLogger
from app.core.config import Settings, get_settings
from app.core.constants import VALID_IMPLEMENTATIONS
from app.core.errors import ValidationException, ServiceException


class ConfigService:
    """Service for configuration management."""
    
    def __init__(
        self,
        logger: ServiceLogger,
        config: Optional[Settings] = None
    ):
        """
        Initialize config service.
        
        Args:
            logger: Service logger
            config: Application settings (uses global if not provided)
        """
        self.logger = logger
        self.config = config or get_settings()
        self.config_file = Path(os.getenv("CONFIG_FILE", "/app/config.json"))
    
    def get_config(self) -> Dict[str, Any]:
        """
        Get current configuration.
        
        Returns:
            Dictionary with configuration values
        """
        return {
            "llm_implementation": self.config.llm_implementation,
            "device": self.config.device,
            "max_concurrent_requests": self.config.max_concurrent_requests,
            "ollama_url": self.config.ollama_url,
            "llm_timeout": self.config.llm_timeout,
            "summary_timeout": self.config.summary_timeout,
            "metadata_timeout": self.config.metadata_timeout,
            "models": {
                "summary": self.config.summary_model,
                "metadata": self.config.metadata_model,
                "rag_chat": self.config.rag_chat_model,
                "default": self.config.default_model
            },
            "generation_params": {
                "hf_max_length": self.config.hf_max_length,
                "hf_temperature": self.config.hf_temperature,
                "hf_top_p": self.config.hf_top_p,
                "hf_do_sample": self.config.hf_do_sample
            },
            "vllm": {
                "base_url": self.config.vllm_base_url,
                "max_tokens": self.config.vllm_max_tokens,
                "temperature": self.config.vllm_temperature,
                "top_p": self.config.vllm_top_p,
                "top_k": self.config.vllm_top_k
            },
            "timeouts": {
                "llm": self.config.llm_timeout,
                "summary": self.config.summary_timeout,
                "metadata": self.config.metadata_timeout
            }
        }
    
    def update_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update configuration values.
        
        Note: Since Settings is a Pydantic BaseSettings, direct modification
        is limited. This method updates the config file and environment variables
        for persistence, but runtime changes may require service restart.
        
        Args:
            updates: Dictionary with configuration updates
            
        Returns:
            Dictionary with updated fields
        """
        updated_fields = []
        old_values = {}
        config_data = {}
        
        # Load existing config file if it exists
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    config_data = json.load(f)
            except Exception as e:
                self.logger.log(
                    "service:config",
                    "Failed to load config file",
                    {"error": str(e)},
                    hypothesis_id="W"
                )
        
        # Update implementation if provided
        if "llm_implementation" in updates:
            new_impl = updates["llm_implementation"]
            if new_impl not in VALID_IMPLEMENTATIONS:
                raise ValidationException(f"Invalid implementation: {new_impl}")
            old_values["llm_implementation"] = self.config.llm_implementation
            config_data["llm_implementation"] = new_impl
            os.environ["LLM_IMPLEMENTATION"] = new_impl
            updated_fields.append("llm_implementation")
        
        # Update device
        if "device" in updates:
            old_values["device"] = self.config.device
            config_data["device"] = updates["device"]
            os.environ["DEVICE"] = updates["device"]
            updated_fields.append("device")
        
        # Update max concurrent requests
        if "max_concurrent_requests" in updates:
            old_values["max_concurrent_requests"] = self.config.max_concurrent_requests
            config_data["max_concurrent_requests"] = int(updates["max_concurrent_requests"])
            os.environ["MAX_CONCURRENT_REQUESTS"] = str(updates["max_concurrent_requests"])
            updated_fields.append("max_concurrent_requests")
        
        # Update model configs
        if "models" in updates:
            models = updates["models"]
            if "summary" in models:
                old_values["summary_model"] = self.config.summary_model
                config_data["summary_model"] = models["summary"]
                os.environ["SUMMARY_MODEL"] = models["summary"]
                updated_fields.append("models.summary")
            if "metadata" in models:
                old_values["metadata_model"] = self.config.metadata_model
                config_data["metadata_model"] = models["metadata"]
                os.environ["METADATA_MODEL"] = models["metadata"]
                updated_fields.append("models.metadata")
            if "rag_chat" in models:
                old_values["rag_chat_model"] = self.config.rag_chat_model
                config_data["rag_chat_model"] = models["rag_chat"]
                os.environ["RAG_CHAT_MODEL"] = models["rag_chat"]
                updated_fields.append("models.rag_chat")
            if "default" in models:
                old_values["default_model"] = self.config.default_model
                config_data["default_model"] = models["default"]
                os.environ["DEFAULT_MODEL"] = models["default"]
                updated_fields.append("models.default")
        
        # Handle timeout updates
        if "llm_timeout" in updates:
            old_values["llm_timeout"] = self.config.llm_timeout
            config_data["llm_timeout"] = float(updates["llm_timeout"])
            os.environ["LLM_TIMEOUT"] = str(updates["llm_timeout"])
            updated_fields.append("llm_timeout")
        
        if "summary_timeout" in updates:
            old_values["summary_timeout"] = self.config.summary_timeout
            config_data["summary_timeout"] = float(updates["summary_timeout"])
            os.environ["SUMMARY_TIMEOUT"] = str(updates["summary_timeout"])
            updated_fields.append("summary_timeout")
        
        if "metadata_timeout" in updates:
            old_values["metadata_timeout"] = self.config.metadata_timeout
            config_data["metadata_timeout"] = float(updates["metadata_timeout"])
            os.environ["METADATA_TIMEOUT"] = str(updates["metadata_timeout"])
            updated_fields.append("metadata_timeout")
        
        # Save to file
        if updated_fields:
            self._save_config(config_data)
            self.logger.log(
                "service:config",
                "Configuration updated",
                {
                    "updated_fields": updated_fields,
                    "old_values": old_values
                }
            )
        
        return {
            "status": "updated",
            "updated_fields": updated_fields,
            "message": f"Updated {len(updated_fields)} configuration fields"
        }
    
    def get_generation_params(self) -> Dict[str, Any]:
        """
        Get generation parameters for different implementations.
        
        Returns:
            Dictionary with generation parameters
        """
        return {
            "huggingface": {
                "max_length": self.config.hf_max_length,
                "temperature": self.config.hf_temperature,
                "top_p": self.config.hf_top_p,
                "do_sample": self.config.hf_do_sample
            },
            "vllm": {
                "max_tokens": self.config.vllm_max_tokens,
                "temperature": self.config.vllm_temperature,
                "top_p": self.config.vllm_top_p,
                "top_k": self.config.vllm_top_k
            }
        }
    
    def get_model_configs(self) -> Dict[str, str]:
        """
        Get model configurations.
        
        Returns:
            Dictionary with model names
        """
        return {
            "summary_model": self.config.summary_model,
            "metadata_model": self.config.metadata_model,
            "rag_chat_model": self.config.rag_chat_model,
            "default_model": self.config.default_model
        }
    
    def update_model_configs(self, model_configs: Dict[str, str]) -> Dict[str, Any]:
        """
        Update model configurations.
        
        Args:
            model_configs: Dictionary with model name updates
            
        Returns:
            Dictionary with updated models
        """
        updated = []
        config_data = {}
        
        # Load existing config file if it exists
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    config_data = json.load(f)
            except Exception:
                pass
        
        if "summary_model" in model_configs:
            config_data["summary_model"] = model_configs["summary_model"]
            os.environ["SUMMARY_MODEL"] = model_configs["summary_model"]
            updated.append("summary_model")
        
        if "metadata_model" in model_configs:
            config_data["metadata_model"] = model_configs["metadata_model"]
            os.environ["METADATA_MODEL"] = model_configs["metadata_model"]
            updated.append("metadata_model")
        
        if "rag_chat_model" in model_configs:
            config_data["rag_chat_model"] = model_configs["rag_chat_model"]
            os.environ["RAG_CHAT_MODEL"] = model_configs["rag_chat_model"]
            updated.append("rag_chat_model")
        
        if "default_model" in model_configs:
            config_data["default_model"] = model_configs["default_model"]
            os.environ["DEFAULT_MODEL"] = model_configs["default_model"]
            updated.append("default_model")
        
        if updated:
            self._save_config(config_data)
            self.logger.log(
                "service:config",
                "Model configurations updated",
                {"updated_models": updated}
            )
        
        return {
            "status": "updated",
            "updated_models": updated
        }
    
    def _save_config(self, config_data: Dict[str, Any]) -> None:
        """
        Save configuration to file.
        
        Args:
            config_data: Configuration data to save
        """
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, 'w') as f:
                json.dump(config_data, f, indent=2)
            
            self.logger.log(
                "service:config",
                "Configuration saved to file",
                {"config_file": str(self.config_file), "full_config_state": config_data}
            )
        except Exception as e:
            error_msg = f"Failed to save config: {str(e)}"
            self.logger.log(
                "service:config",
                "Failed to save config",
                {"error": str(e), "config_file": str(self.config_file)},
                hypothesis_id="E"
            )
            raise ServiceException(error_msg, original_exception=e)
