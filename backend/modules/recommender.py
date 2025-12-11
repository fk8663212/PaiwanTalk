import json
import os
import random
import pandas as pd
from typing import List, Dict, Any
from .utils import extract_structured

# Global cache for the dataframe
_SENTENCE_DF = None

def load_sentences():
    global _SENTENCE_DF
    if _SENTENCE_DF is None:
        try:
            # Assuming running from backend/
            file_path = os.path.join("data", "formosan_pairs_paiwan.xlsx")
            if os.path.exists(file_path):
                _SENTENCE_DF = pd.read_excel(file_path)
                print(f"[Recommender] Loaded {_SENTENCE_DF.shape[0]} sentences.")
            else:
                print(f"[Recommender] Warning: {file_path} not found.")
        except Exception as e:
            print(f"[Recommender] Error loading sentences: {e}")

def get_random_sentence():
    load_sentences()
    if _SENTENCE_DF is not None and not _SENTENCE_DF.empty:
        row = _SENTENCE_DF.sample(1).iloc[0]
        return row['Ab'], row['Ch']
    return None, None

async def process(client: Any, model_name: str, messages: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Handle recommendation of example sentences.
    """
    # 1. Try to get a random sentence from the database
    paiwan_sent, chinese_sent = get_random_sentence()
    
    if paiwan_sent and chinese_sent:
        reply_text = (
            "這裡有一個排灣語例句供您參考：\n\n"
            f"**{paiwan_sent}**\n"
            f"中文：{chinese_sent}"
        )
        
        return {
            "reply": reply_text,
            "thinking": "已從資料庫隨機挑選例句 (formosan_pairs_paiwan.xlsx)"
        }
    else:
        # Fallback to LLM generation if file not found or empty
        system_prompt = (
            "You are a Paiwan language teacher. "
            "Your task is to provide example sentences (例句) in Paiwan with Traditional Chinese translations. "
            "Based on the user's topic or request, generate 3-5 useful sentences. "
            "Always respond with strict JSON using keys `reply` (the formatted list of sentences) and "
            "`thinking` (why you chose these examples). "
            "Format the reply nicely."
        )
        
        full_messages = [{"role": "system", "content": system_prompt}]
        for msg in messages:
             if msg["role"] == "user":
                 full_messages.append(msg)

        try:
            completion = await client.chat.completions.create(
                model=model_name,
                messages=full_messages,
                temperature=0.7,
                timeout=20.0,
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
