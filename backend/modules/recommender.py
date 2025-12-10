import json
from openai import AsyncOpenAI
from typing import List, Dict, Any
from .utils import extract_structured

async def process(client: AsyncOpenAI, model_name: str, messages: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Handle recommendation of example sentences.
    """
    system_prompt = (
        "You are a Paiwan language teacher. "
        "Your task is to provide example sentences (例句) in Paiwan with Traditional Chinese translations. "
        "Based on the user's topic or request, generate 3-5 useful sentences. "
        "Always respond with strict JSON using keys `reply` (the formatted list of sentences) and "
        "`thinking` (why you chose these examples). "
        "Format the reply nicely."
    )
    
    full_messages = [{"role": "system", "content": system_prompt}]
    
    # Add history
    for msg in messages:
         if msg["role"] == "user":
             full_messages.append(msg)

    try:
        completion = await client.chat.completions.create(
            model=model_name,
            messages=full_messages,
            temperature=0.7,
            timeout=30.0,
            max_tokens=1024,
        )
        
        raw_content = completion.choices[0].message.content
        
        reply, thinking = extract_structured(raw_content)
        return {
            "reply": reply,
            "thinking": thinking
        }
            
    except Exception as e:
        return {
            "reply": "抱歉，推薦系統暫時無法回應。",
            "thinking": str(e)
        }
