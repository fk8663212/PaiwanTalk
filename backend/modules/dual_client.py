import os
import json
from openai import AsyncOpenAI
from typing import Any, List, Optional

class DualClient:
    def __init__(self, vllm_base_urls: List[str], vllm_api_key: str):
        # Primary Clients (vLLM List)
        self.vllm_clients = []
        for url in vllm_base_urls:
            if url:
                self.vllm_clients.append(AsyncOpenAI(
                    base_url=url,
                    api_key=vllm_api_key,
                ))
        
        # Secondary Client (Official OpenAI)
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.openai_client = None
        if self.openai_api_key:
            self.openai_client = AsyncOpenAI(
                api_key=self.openai_api_key
            )
            print("DEBUG: OpenAI Fallback Client Initialized.")
        else:
            print("WARNING: OPENAI_API_KEY not found. Fallback will not work.")

        # Mocking the structure to match AsyncOpenAI: client.chat.completions.create
        self.chat = self.Chat(self)
        self.models = self.Models(self)

    class Models:
        def __init__(self, parent):
            self.parent = parent

        async def list(self):
            # Try vLLM clients in order
            for i, client in enumerate(self.parent.vllm_clients):
                try:
                    return await client.models.list()
                except Exception as e:
                    print(f"WARNING: vLLM client {i+1} models.list failed: {e}")
            
            # If all vLLM failed, try OpenAI
            if self.parent.openai_client:
                # Return OpenAI models or a dummy list to keep code running
                return await self.parent.openai_client.models.list()
            raise RuntimeError("All vLLM clients and OpenAI fallback failed.")

    class Chat:
        def __init__(self, parent):
            self.parent = parent
            self.completions = self.Completions(parent)

        class Completions:
            def __init__(self, parent):
                self.parent = parent

            async def create(self, *args, **kwargs):
                # 1. Try vLLM clients in order
                for i, client in enumerate(self.parent.vllm_clients):
                    try:
                        print(f"DEBUG: Attempting vLLM client {i+1}...")
                        # Ensure we use the model name provided, or fallback logic might need to change it
                        # Note: Different vLLM servers might have different model names. 
                        # Ideally we should query the model list for each client, but for now we assume the model name passed is valid or ignored by the server if it only hosts one.
                        
                        # If switching between vLLM servers, we might need to re-fetch the model name if they differ.
                        # But usually in this hackathon context, we just want to hit the endpoint.
                        
                        response = await client.chat.completions.create(*args, **kwargs)
                        
                        # Check for garbage output
                        content = response.choices[0].message.content
                        if "!!!!!!!!!!" in content:
                            raise ValueError("Detected garbage output (exclamation marks).")
                        
                        return response
                    
                    except Exception as e:
                        print(f"ERROR: vLLM client {i+1} failed or returned garbage: {e}")
                        continue # Try next vLLM client

                # 2. Try OpenAI if available
                if self.parent.openai_client:
                    print("DEBUG: Switching to OpenAI Fallback...")
                    
                    # Remove vLLM-specific params if any (usually they are compatible)
                    # But we MUST change the model name to an OpenAI one
                    # We'll use gpt-4o-mini as a cost-effective fallback, or gpt-3.5-turbo
                    fallback_model = "gpt-4o-mini" 
                    
                    kwargs['model'] = fallback_model
                    
                    # Remove params that might not be supported or needed
                    # e.g. if vLLM uses specific extra_body params
                    
                    return await self.parent.openai_client.chat.completions.create(*args, **kwargs)
                
                # If no fallback, re-raise
                raise RuntimeError("All vLLM clients and OpenAI fallback failed.")
