import json
import re
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
import os

# ========= vLLM 設定 =========
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://210.61.209.139:45014/v1/")
VLLM_API_KEY = os.getenv("VLLM_API_KEY", "dummy-key")  # 形式需要，但內容無所謂

client = OpenAI(
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


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    model: str
    thinking: Optional[str] = None


@app.get("/")
def root():
    return {"status": "ok", "msg": "LLM test running"}


@app.get("/models")
def get_models():
    """
    回傳主辦方 vLLM 目前掛載的所有模型，方便你檢查真正的 model id。
    """
    models = client.models.list()
    return models


def get_default_model_name() -> str:
    """
    每次呼叫時都去 vLLM /models 拿第一個模型當預設。
    比賽環境不固定，用這招最保險。
    """
    models = client.models.list()
    if not getattr(models, "data", None):
        raise RuntimeError("No models available from vLLM server.")
    return models.data[0].id


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    單純丟一段文字給 LLM，不做任何翻譯邏輯。
    自動從 /models 取得可用的 model id。
    """
    model_name = get_default_model_name()

    completion = client.chat.completions.create(
        model=model_name,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant. Always respond with strict JSON "
                    "using keys `reply` (final answer shown to the user) and "
                    "`thinking` (brief reasoning). Do not include other text."
                ),
            },
            {"role": "user", "content": req.message},
        ],
        temperature=0.7,
    )

    raw_content = completion.choices[0].message.content

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
