from fastapi import FastAPI
from pydantic import BaseModel
import re
import json
import os
from typing import List, Dict

# 引入同目錄下的字典工具
from paiwan_translation_api_multi import MultiSourceTranslator, SOURCE_FILES, SourceEnum

app = FastAPI()

# 全域變數：翻譯器實例
translator = None

@app.on_event("startup")
async def startup_event():
    global translator
    # 初始化翻譯器
    # 注意：這裡假設執行目錄下有 data 資料夾，或 SOURCE_FILES 路徑正確
    if not os.path.exists("data"):
        print("Warning: 'data' directory not found in current path. Dictionary loading might fail.")
    
    translator = MultiSourceTranslator(SOURCE_FILES)
    print("[TranslationAPI] Translator initialized.")

# ---------- 資料模型 -----------

class ChatRequest(BaseModel):
    chatInput: str  # 跟 n8n 的欄位名稱一樣

class ChatResponse(BaseModel):
    paiwanText: str
    formattedText: str
    finalAnswer: str


# ---------- 小工具函式 -----------

def split_tokens(paiwan: str) -> List[str]:
    """
    切分排灣語句子為單字
    """
    # 保留原本的 split 邏輯，但過濾掉空字串
    raw_tokens = re.split(r"[\s,，、\.\?？!！]+", paiwan)
    return [t for t in raw_tokens if t.strip()]


def call_word_translate(token: str) -> dict:
    """
    直接呼叫 MultiSourceTranslator 進行查詢
    """
    if translator is None:
        return {"original_text": token, "translation": "(系統錯誤: 字典未載入)"}

    # 使用 'all' 模式查詢所有來源
    used_source, translations = translator.translate(token, SourceEnum.all)
    
    # 將結果列表轉為字串
    translation_str = ", ".join(translations) if translations else "無查詢結果"
    
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
    """
    等同於 Code1 產生 formattedText
    """
    lines = []
    for e in mapping_list:
        lines.append(f"- 排灣語：{e['token']} → 中文：{e['translation']}")
    return "\n".join(lines)


def build_llm_prompt(paiwan_text: str, formatted_text: str) -> str:
    """
    簡化後的 Prompt，移除 <thinking> 指令以避免模型崩潰。
    """
    return f"""
你是一個排灣語的翻譯專家，而排灣語屬於VSO（動詞–主語–受語）語序。
以下有一個排灣語片段的「詞彙對照」列表，請你根據每個「排灣語詞 → 對應中文」的 mapping，組成一個完整且最通順的中文句子。
如果你覺得改變詞語順序、又或是刪除排列能更通暢，那你可以改變，目標就是將他組成正常對話的句子。

詞彙對照：
{formatted_text}

原文: {paiwan_text}

請用繁體中文直接輸出最終完整譯文，並將答案以<ans>開始，以</ans>結束。

排灣族的文法補充:
排灣族存在複合詞 複合詞為具有意義的兩個詞素緊密結合成一個新詞。兩個詞組合成為新詞,中間會有一個標記,可能是a或是na,標記上我們會叫他[虛]。
""".strip()


async def call_llm(prompt: str) -> str:
    """
    呼叫 LLM 進行句子重組
    改用 AsyncOpenAI + Stream 模式，提高穩定性。
    """
    import os
    import time
    from openai import AsyncOpenAI

    # 檢查 VLLM (Hackathon 環境)
    vllm_base_url = os.getenv("VLLM_BASE_URL", "http://210.61.209.139:45014/v1/")
    vllm_api_key = os.getenv("VLLM_API_KEY", "dummy-key")
    
    print(f"[LLM] Connecting to {vllm_base_url} (Async)...")

    try:
        client = AsyncOpenAI(base_url=vllm_base_url, api_key=vllm_api_key)
        
        # 動態取得模型名稱
        print("[LLM] Fetching model list...")
        start_time = time.time()
        models = await client.models.list()
        if not models.data:
            print("[LLM] Error: No models found.")
            return "<ans>VLLM 錯誤: 無可用模型</ans>"
        model_name = models.data[0].id
        print(f"[LLM] Using model: {model_name} (took {time.time() - start_time:.2f}s)")
        
        print("[LLM] Sending completion request (Stream mode)...")
        start_time = time.time()
        
        response = await client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1024,
            stream=True  # 開啟串流模式
        )
        
        collected_content = []
        async for chunk in response:
            content = chunk.choices[0].delta.content
            if content:
                collected_content.append(content)
                # 簡單的防呆：如果發現連續驚嘆號，可以提早斷開 (選擇性實作，這裡先不加)
        
        full_content = "".join(collected_content)
        print(f"[LLM] Response received (took {time.time() - start_time:.2f}s)")
        print(f"[LLM] Raw output length: {len(full_content)}")
        print(f"[LLM] Raw output preview: {full_content[:200]}...")
        
        return full_content

    except Exception as e:
        print(f"[LLM] Call Error: {e}")

    # 如果失敗，回傳一個模擬結果
    print("Warning: No working LLM found. Using mock response.")
    return f"""
<ans>
(LLM 連線失敗或發生錯誤)
錯誤訊息: {e if 'e' in locals() else 'Unknown'}
</ans>
"""


def extract_final_answer(raw: str) -> str:
    """
    從 LLM 的輸出裡抓 <ans>...</ans> 內容
    若抓不到，嘗試移除 <thinking>...</thinking> 後回傳剩餘內容。
    """
    import re
    # 1. 嘗試抓取 <ans> 標籤內的內容
    m = re.search(r"<ans>(.*?)</ans>", raw, flags=re.S)
    if m:
        return m.group(1).strip()
    
    # 2. 若沒有 <ans>，則嘗試移除 <thinking> 區塊，回傳剩下的部分
    # 這樣可以避免把思考過程當成答案回傳給使用者
    clean = re.sub(r"<thinking>.*?</thinking>", "", raw, flags=re.S).strip()
    
    # 如果移除後變空了（代表只有思考過程），那就只好回傳原本的（至少有東西）
    if not clean:
        return raw.strip()
        
    return clean


# ---------- 主 API：等同整條 n8n Flow ----------

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    paiwan_text = req.chatInput

    # 1. 切 token
    tokens = split_tokens(paiwan_text)

    # 2. 每個 token 丟 /translate (直接呼叫函式)
    mapping_list = build_mapping_list(tokens)

    # 3. 建出 formattedText
    formatted_text = format_mapping_text(mapping_list)

    # 4. 組 prompt
    prompt = build_llm_prompt(paiwan_text, formatted_text)

    # 5. 呼叫 LLM
    raw_llm_output = await call_llm(prompt)

    # 6. 抽出 <ans> 中的結果
    final_answer = extract_final_answer(raw_llm_output)

    return ChatResponse(
        paiwanText=paiwan_text,
        formattedText=formatted_text,
        finalAnswer=final_answer,
    )
