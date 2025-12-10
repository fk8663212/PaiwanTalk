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
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": req.message},
        ],
        temperature=0.7,
    )

    reply = completion.choices[0].message.content
    return ChatResponse(reply=reply, model=model_name)
