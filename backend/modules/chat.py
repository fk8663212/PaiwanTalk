import json
from openai import AsyncOpenAI
from typing import List, Dict, Any
from .utils import extract_structured

async def process(client: AsyncOpenAI, model_name: str, messages: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Handle normal conversation.
    """
    system_prompt = (
        "You are a helpful assistant. Always respond with strict JSON "
        "using keys `reply` (final answer shown to the user) and "
        "`thinking` (brief reasoning). Do not include other text."
    )
    
    # Ensure system prompt is at the beginning
    full_messages = [{"role": "system", "content": system_prompt}]
    
    # Add history, ensuring format is correct
    for msg in messages:
        if msg["role"] == "assistant":
            try:
                # Try to parse if it's already JSON string
                json.loads(msg["content"])
                full_messages.append(msg)
            except json.JSONDecodeError:
                # Wrap plain text in JSON structure
                simulated_json = json.dumps({
                    "reply": msg["content"],
                    "thinking": "Context from previous conversation"
                }, ensure_ascii=False)
                full_messages.append({"role": "assistant", "content": simulated_json})
        else:
            full_messages.append(msg)

    try:
        completion = await client.chat.completions.create(
            model=model_name,
            messages=full_messages,
            temperature=0.7,
            timeout=30.0,
            max_tokens=1024,
            presence_penalty=0.6,
        )
        
        raw_content = completion.choices[0].message.content
        
        reply, thinking = extract_structured(raw_content)
        return {
            "reply": reply,
            "thinking": thinking
        }
            
    except Exception as e:
        return {
            "reply": "抱歉，對話系統暫時無法回應。",
            "thinking": str(e)
        }
