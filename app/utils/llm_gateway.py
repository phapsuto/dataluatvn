import os
import time
import json
import logging
from typing import AsyncGenerator, Dict, Any, List
import litellm

# Configure litellm behavior
litellm.telemetry = False  # Disable telemetry
litellm.drop_params = True  # Drop unsupported parameters automatically

# Create logs directory if not exists
os.makedirs("logs", exist_ok=True)

# Set up specific logger for LLM usage
llm_logger = logging.getLogger("llm_usage")
llm_logger.setLevel(logging.INFO)

# Avoid adding duplicate handlers if reloaded
if not llm_logger.handlers:
    file_handler = logging.FileHandler("logs/llm_usage.log", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
    llm_logger.addHandler(file_handler)

class LLMGateway:
    # Class level state to hold the currently selected provider
    _active_provider = "fpt"
    
    # Providers configuration
    PROVIDERS = {
        "fpt": {
            "model": "custom_openai/gemma-4-31B-it",
            "api_base": "https://mkp-api.fptcloud.com/v1",
            "api_key": os.environ.get("FPT_CLOUD_API_KEY") or "",
        },
        "ollama": {
            "model": "ollama/llama3.2",
            "api_base": os.environ.get("OLLAMA_API_BASE") or "http://localhost:11434",
        },
    }
    
    # Default fallback path
    FALLBACK_CHAIN = ["fpt", "ollama"]

    @classmethod
    def get_status(cls) -> Dict[str, Any]:
        """Returns the current state and available models."""
        available = []
        for p, config in cls.PROVIDERS.items():
            if p == "ollama":
                available.append(p)
            elif config.get("api_key"):
                available.append(p)
                
        return {
            "active_provider": cls._active_provider,
            "model": cls.PROVIDERS[cls._active_provider]["model"],
            "fallback_chain": cls.FALLBACK_CHAIN,
            "available_providers": available
        }

    @classmethod
    def switch_provider(cls, provider: str) -> Dict[str, Any]:
        """Switches the active LLM provider at runtime."""
        if provider not in cls.PROVIDERS:
            raise ValueError(f"Provider '{provider}' không hợp lệ. Danh sách hỗ trợ: {list(cls.PROVIDERS.keys())}")
        cls._active_provider = provider
        return {
            "status": "success", 
            "active_provider": provider, 
            "model": cls.PROVIDERS[provider]["model"]
        }

    @classmethod
    async def call_stream(
        cls, 
        messages: List[Dict[str, str]], 
        system_prompt: str, 
        temperature: float = 0.1,
        custom_model: str = None
    ) -> AsyncGenerator[str, None]:
        """
        Asynchronously streams completion tokens from the active LLM provider,
        automatically falling back to alternative providers if failures occur.
        """
        # Package the system prompt along with conversation history
        payload_messages = [{"role": "system", "content": system_prompt}] + messages
        
        # Build the exact order of providers to try (active first, then fallback path)
        providers_to_try = [cls._active_provider]
        for fb in cls.FALLBACK_CHAIN:
            if fb not in providers_to_try:
                providers_to_try.append(fb)
                
        last_error = None
        for provider in providers_to_try:
            config = cls.PROVIDERS[provider]
            
            # Skip provider if API key is required but missing (unless it is Ollama)
            if provider != "ollama" and not config.get("api_key"):
                continue
                
            model = custom_model if (custom_model and provider == "fpt") else config["model"]
            api_key = config.get("api_key")
            api_base = config.get("api_base")
            
            start_time = time.time()
            token_count = 0
            
            try:
                kwargs = {
                    "model": model,
                    "messages": payload_messages,
                    "temperature": temperature,
                    "stream": True
                }
                if api_key:
                    kwargs["api_key"] = api_key
                if api_base:
                    kwargs["api_base"] = api_base
                    
                # Call litellm streaming completion
                response = await litellm.acompletion(**kwargs)
                
                async for chunk in response:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta and delta.content:
                        token_count += 1
                        yield delta.content
                        
                # Log success usage
                latency = time.time() - start_time
                log_data = {
                    "provider": provider,
                    "model": model,
                    "latency": f"{latency:.3f}s",
                    "tokens_estimated": token_count,
                    "status": "success"
                }
                llm_logger.info(json.dumps(log_data, ensure_ascii=False))
                return  # Exit successfully if completion completes
                
            except Exception as e:
                latency = time.time() - start_time
                log_data = {
                    "provider": provider,
                    "model": model,
                    "latency": f"{latency:.3f}s",
                    "status": "failed",
                    "error": str(e)
                }
                llm_logger.info(json.dumps(log_data, ensure_ascii=False))
                last_error = e
                print(f"⚠️ Provider '{provider}' failed with error: {e}. Trying fallback...")
                
        # Raise exception if all fallback options failed
        raise last_error or RuntimeError("Tất cả các LLM Providers đều gặp lỗi và không thể hoàn thành yêu cầu.")
