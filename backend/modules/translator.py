import json
import re
import os
from typing import List, Dict, Any
from .utils import extract_structured
from paiwan_translation_api_multi import MultiSourceTranslator, SOURCE_FILES, SourceEnum

# Initialize translator globally for this module
# Assuming data directory is in the parent directory relative to this module or current working dir
# We need to be careful about paths. Since we run from backend/, data/ should be accessible.
translator_instance = None

def get_translator():
    global translator_instance
    if translator_instance is None:
        if not os.path.exists("data"):
             print("Warning: 'data' directory not found. Dictionary loading might fail.")
        translator_instance = MultiSourceTranslator(SOURCE_FILES)
        print("[TranslatorModule] Dictionary initialized.")
    return translator_instance

def split_tokens(paiwan: str) -> List[str]:
    """
    切分排灣語句子為單字
    """
    raw_tokens = re.split(r"[\s,，、\.\?？!！]+", paiwan)
    return [t for t in raw_tokens if t.strip()]

def call_word_translate(token: str) -> dict:
    """
    直接呼叫 MultiSourceTranslator 進行查詢
    """
    translator = get_translator()
    if translator is None:
        return {"original_text": token, "translation": "(系統錯誤: 字典未載入)"}

    # 使用 'all' 模式查詢所有來源
    used_source, translations = translator.translate(token, SourceEnum.all)
    
    # 將結果列表轉為字串
    translation_str = ", ".join(translations) if translations else token
    
    return {
        "original_text": token,
        "translation": translation_str
    }

def build_mapping_list(tokens: List[str]) -> List[dict]:
    """
    對每個 token 進行翻譯並建立對照表
    """
    mapping_list = []
    for tok in tokens:
        parsed = call_word_translate(tok)
        mapping_list.append({
            "token": parsed.get("original_text", tok),
            "translation": parsed.get("translation", "")
        })
    return mapping_list

def format_mapping_text(mapping_list: list[dict]) -> str:
    lines = []
    for e in mapping_list:
        lines.append(f"- 排灣語：{e['token']} → 中文：{e['translation']}")
    return "\n".join(lines)

async def process(client: Any, model_name: str, messages: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Handle translation from Paiwan language to Traditional Chinese using RAG (Dictionary Lookup).
    """
    # 1. Extract the latest user message (the text to translate)
    user_input = ""
    for msg in reversed(messages):
        if msg["role"] == "user":
            user_input = msg["content"]
            break
    
    if not user_input:
        return {"reply": "沒有收到需要翻譯的文字。", "thinking": "No user input found."}

    # 1.5 Extract Paiwan text from user input
    paiwan_text = user_input
    # Simple heuristic: if input contains Chinese, ask LLM to extract Paiwan.
    if re.search(r'[\u4e00-\u9fff]', user_input):
        extraction_sys_prompt = (
            "你是一個語言辨識專家。使用者的輸入可能包含中文指令和排灣語句子。\n"
            "請擷取輸入中的「排灣語」部分。\n"
            "範例：\n"
            "輸入：幫我翻譯 ti amentu aicu\n"
            "輸出：ti amentu aicu\n\n"
            "輸入：kikai 是什麼意思\n"
            "輸出：kikai\n\n"
            "請只輸出排灣語的部分，不要包含其他文字。"
        )
        try:
            ext_resp = await client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": extraction_sys_prompt},
                    {"role": "user", "content": user_input}
                ],
                temperature=0.1,
                max_tokens=256
            )
            extracted = ext_resp.choices[0].message.content.strip()
            extracted = extracted.strip('"').strip("'")
            if extracted:
                paiwan_text = extracted
        except Exception as e:
            print(f"[Translator] Extraction failed: {e}")
            paiwan_text = user_input

    # 2. Tokenize and Lookup Dictionary
    tokens = split_tokens(paiwan_text)
    mapping_list = build_mapping_list(tokens)
    formatted_text = format_mapping_text(mapping_list)

    # 3. Build Prompt with Dictionary Context
    system_prompt = (
        "你是一個排灣語的翻譯專家，而排灣語屬於VSO（動詞–主語–受語）語序。\n"
        "以下有一個排灣語片段的「詞彙對照」列表，請你根據每個「排灣語詞 → 對應中文」的 mapping，組成一個完整且最通順的中文句子。\n"
        "如果你覺得改變詞語順序、又或是刪除排列能更通暢，那你可以改變，目標就是將他組成正常對話的句子。\n\n"
        "詞彙對照：\n"
        f"{formatted_text}\n\n"
        "排灣族的文法補充:\n"
        "排灣族存在複合詞 複合詞為具有意義的兩個詞素緊密結合成一個新詞。兩個詞組合成為新詞,中間會有一個標記,可能是a或是na,標記上我們會叫他[虛]。\n\n"
        "請總是回傳嚴格的 JSON 格式，包含 `reply` (最終完整譯文) 和 `thinking` (翻譯過程與文法分析)。"
    )
    
    # We construct a new message list for the LLM, focusing on this specific translation task
    # We don't necessarily need the full chat history here, as we are doing a specific RAG task
    llm_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"原文: {paiwan_text}"}
    ]

    try:
        # Use the dual client passed in
        completion = await client.chat.completions.create(
            model=model_name,
            messages=llm_messages,
            temperature=0.7, # Slightly higher temp for fluent sentence construction
            timeout=30.0,
            max_tokens=1024,
        )
        
        raw_content = completion.choices[0].message.content
        
        reply, thinking = extract_structured(raw_content)
        
        # If thinking is empty, we can fill it with the dictionary mapping for transparency
        if not thinking:
            thinking = f"查詞結果:\n{formatted_text}"
            
        return {
            "reply": reply,
            "thinking": thinking
        }
            
    except Exception as e:
        return {
            "reply": "抱歉，翻譯系統暫時無法回應。",
            "thinking": str(e)
        }
