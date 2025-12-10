import json
import re
from typing import Optional, List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import AsyncOpenAI
import os

# ========= vLLM 設定 =========
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://210.61.209.139:45014/v1/")
VLLM_API_KEY = os.getenv("VLLM_API_KEY", "dummy-key")  # 形式需要，但內容無所謂

client = AsyncOpenAI(
    base_url=VLLM_BASE_URL,
    api_key=VLLM_API_KEY,
)

app = FastAPI(title="Simple LLM Test API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[Message]


class ChatResponse(BaseModel):
    reply: str
    model: str
    thinking: Optional[str] = None


@app.get("/")
def root():
    return {"status": "ok", "msg": "LLM test running"}


@app.get("/models")
async def get_models():
    """
    回傳主辦方 vLLM 目前掛載的所有模型，方便你檢查真正的 model id。
    """
    models = await client.models.list()
    return models


async def get_default_model_name() -> str:
    """
    每次呼叫時都去 vLLM /models 拿第一個模型當預設。
    比賽環境不固定，用這招最保險。
    """
    models = await client.models.list()
    if not getattr(models, "data", None):
        raise RuntimeError("No models available from vLLM server.")
    return models.data[0].id


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    單純丟一段文字給 LLM，不做任何翻譯邏輯。
    自動從 /models 取得可用的 model id。
    """
    try:
        model_name = await get_default_model_name()
    except Exception as e:
        return ChatResponse(reply="無法取得模型列表", model="unknown", thinking=str(e))

    # 構建完整的對話歷史
    messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful assistant. Always respond with strict JSON "
                "using keys `reply` (final answer shown to the user) and "
                "`thinking` (brief reasoning). Do not include other text."
            ),
        }
    ]
    
    # 加入前端傳來的歷史訊息
    for msg in req.messages:
        if msg.role == "assistant":
            # 為了保持與 System Prompt 的一致性，將歷史紀錄中的 Assistant 回覆包裝回 JSON 格式
            # 這樣模型才不會因為看到歷史紀錄是純文字而感到困惑，進而崩壞
            try:
                # 嘗試解析，如果已經是 JSON 就不重複包裝 (預防萬一)
                json.loads(msg.content)
                messages.append({"role": msg.role, "content": msg.content})
            except json.JSONDecodeError:
                # 如果是純文字，就包裝成 JSON
                simulated_json = json.dumps({
                    "reply": msg.content,
                    "thinking": "Context from previous conversation"
                }, ensure_ascii=False)
                messages.append({"role": msg.role, "content": simulated_json})
        else:
            messages.append({"role": msg.role, "content": msg.content})

    print(f"DEBUG: Sending messages to LLM: {json.dumps(messages, ensure_ascii=False)}")

    max_retries = 3
    last_error = None
    raw_content = ""

    for attempt in range(max_retries):
        try:
            print(f"DEBUG: Attempt {attempt + 1}/{max_retries}")
            # 設定 timeout=30秒，避免卡死
            # 設定 max_tokens=1024，避免模型生成過長
            completion = await client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=0.7,
                timeout=30.0,
                max_tokens=1024,
                presence_penalty=0.6,
            )
            
            raw_content = completion.choices[0].message.content
            
            # 檢查是否為垃圾輸出 (連續驚嘆號)
            if "!!!!!!!!!!" in raw_content:
                print(f"WARNING: Detected garbage output (attempt {attempt+1}): {raw_content[:50]}...")
                continue # Retry
                
            # 如果成功且沒有垃圾，跳出迴圈
            break
            
        except Exception as e:
            print(f"ERROR: LLM call failed (attempt {attempt+1}): {e}")
            last_error = e
            if attempt == max_retries - 1:
                # 回傳錯誤給前端，而不是讓它掛著
                return ChatResponse(
                    reply="抱歉，AI 暫時無法回應 (Timeout or Error)。",
                    model=model_name,
                    thinking=str(e)
                )

    if not raw_content:
         return ChatResponse(
            reply="抱歉，AI 產生了無效的回應。",
            model=model_name,
            thinking="Empty response or garbage filtered out."
        )

    print(f"DEBUG: Raw LLM response: {raw_content}")

    def extract_structured(text: str) -> tuple[str, Optional[str]]:
        """Best-effort抽取 reply/thinking，避免模型偷跑一般文字."""
        clean_content = text.strip()

        # 去除 ```json ... ``` 或 ``` ... ``` 包裹
        if clean_content.startswith("```") and clean_content.endswith("```"):
            inner_lines = clean_content.split("\n")
            clean_content = "\n".join(inner_lines[1:-1]).strip()

        # 1) 直接嘗試 JSON
        def try_parse_json(candidate: str):
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return (
                    str(parsed.get("reply") or "").strip(),
                    str(parsed.get("thinking") or "").strip(),
                )
            return None

        try:
            result = try_parse_json(clean_content)
            if result:
                return result[0] or text, result[1] or None
        except Exception:
            pass

        # 2) 嘗試抓最後一段 {...} 再 parse
        if "{" in clean_content and "}" in clean_content:
            last_open = clean_content.rfind("{")
            last_close = clean_content.rfind("}")
            if last_close > last_open:
                maybe_json = clean_content[last_open : last_close + 1]
                try:
                    result = try_parse_json(maybe_json)
                    if result:
                        return result[0] or text, result[1] or None
                except Exception:
                    pass

        # 3) regex 撈出 reply/thinking 欄位
        reply_match = re.search(r'"reply"\\s*:\\s*"([^"]+)"', clean_content)
        thinking_match = re.search(r'"thinking"\\s*:\\s*"([^"]+)"', clean_content)
        if reply_match:
            return reply_match.group(1), thinking_match.group(1) if thinking_match else None

        # 都失敗就原文
        return text, None

    reply_text, thinking_text = extract_structured(raw_content)
    return ChatResponse(reply=reply_text, model=model_name, thinking=thinking_text)
