import os
import re

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI

from paiwan_translation_api_multi import (
    MultiSourceTranslator,
    SOURCE_FILES,
    SourceEnum,
)

# ========== vLLM 設定 ==========
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://210.61.209.139:45014/v1/")
VLLM_API_KEY = os.getenv("VLLM_API_KEY", "dummy-key")  # 形式需要，但內容無所謂

llm_client = OpenAI(
    base_url=VLLM_BASE_URL,
    api_key=VLLM_API_KEY,
)

# ========== 排灣語翻譯器 ==========
translator = MultiSourceTranslator(SOURCE_FILES)

app = FastAPI(title="Hackathon Paiwan AI Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    dict_source: str | None = None
    dict_candidates: list[str] | None = None
    mode: str = "chat"  # "chat" or "paiwan_translate"


# --------- Debug / 健康檢查 ---------

@app.get("/")
def root():
    return {"status": "ok", "service": "hackathon_paiwan_agent"}


@app.get("/models")
def get_models():
    """
    回傳目前 vLLM 掛載的模型列表，方便確認真正的 model id。
    """
    return llm_client.models.list()


def get_default_model_name() -> str:
    """
    從 vLLM /models 拿第一個可用模型當預設。
    （比賽環境不固定，用這招最安全）
    """
    models = llm_client.models.list()
    if not getattr(models, "data", None):
        raise RuntimeError("No models available from vLLM server.")
    return models.data[0].id


# --------- 簡單的「翻譯請求偵測」 ---------

TRANSLATE_PATTERNS = [
    # 幫我翻譯這個句子 na tarivaksun , sinsi ?
    r"幫我?翻譯(一下|看看|這(句|個句子)?|)?[:：\s]*(.+)",
    # 這句排灣語是什麼意思：na tarivaksun , sinsi ?
    r"這句排灣語是什麼意思[:：\s]*(.+)",
]


def detect_translate_intent(text: str) -> str | None:
    """如果是翻譯請求，回傳抽出的排灣語句子；否則回傳 None"""
    for pattern in TRANSLATE_PATTERNS:
        m = re.search(pattern, text)
        if m:
            # 最後一個群組當作排灣語內容
            paiwan = m.group(m.lastindex).strip()
            return paiwan
    return None


# --------- LLM 呼叫封裝 ---------

def call_llm(messages, temperature: float = 0.7) -> str:
    model_name = get_default_model_name()
    completion = llm_client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=temperature,
    )
    return completion.choices[0].message.content


# --------- API ---------


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    # 1. 先判斷是不是翻譯請求
    paiwan_text = detect_translate_intent(req.message)

    if paiwan_text:
        # ===== 排灣語翻譯模式 =====
        used_source, candidates = translator.translate(paiwan_text, SourceEnum.all)

        if not candidates:
            # 字典找不到 → 直接請 LLM 硬翻一次
            reply = call_llm(
                [
                    {
                        "role": "system",
                        "content": "你是一個排灣語翻譯助理，請盡力將使用者提供的句子翻成自然的中文。",
                    },
                    {
                        "role": "user",
                        "content": f"請將這句排灣語翻成中文：{paiwan_text}",
                    },
                ],
                temperature=0.3,
            )
            return ChatResponse(
                reply=reply,
                dict_source=None,
                dict_candidates=[],
                mode="paiwan_translate",
            )

        # 字典有候選 → 當 RAG 使用
        system_prompt = (
            "你是一個排灣語翻譯助理。\n"
            "我會給你一個排灣語原句，和根據字典查到的中文詞彙候選。\n"
            "請你根據這些候選，推論出最自然、最通順的中文翻譯句子。\n"
            "僅輸出翻譯結果本身，不需要多餘的解釋。"
        )
        user_content = (
            f"排灣語原句：{paiwan_text}\n"
            f"字典候選：{', '.join(candidates)}\n"
            "請選擇最合適的詞義，組成一個自然的中文句子。"
        )

        translation = call_llm(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
        )

        reply_text = (
            f"原文（排灣語）：{paiwan_text}\n"
            f"中文翻譯：{translation}"
        )

        return ChatResponse(
            reply=reply_text,
            dict_source=used_source,
            dict_candidates=candidates,
            mode="paiwan_translate",
        )

    # ===== 一般聊天模式 =====
    reply = call_llm(
        [
            {
                "role": "system",
                "content": "你是一個友善的助理。如果使用者沒有特別提到排灣語，就當作一般聊天助理回答。",
            },
            {"role": "user", "content": req.message},
        ]
    )

    return ChatResponse(
        reply=reply,
        dict_source=None,
        dict_candidates=[],
        mode="chat",
    )
