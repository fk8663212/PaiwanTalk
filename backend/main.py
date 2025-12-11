import json
from typing import Optional, List
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import AsyncOpenAI
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Import our new modules
from modules import classifier, chat, translator, recommender
from modules.dual_client import DualClient

# ========= vLLM 設定 =========
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://210.61.209.139:45014/v1/")
VLLM_BASE_URL_2 = os.getenv("VLLM_BASE_URL_2", "http://210.61.209.139:45005/v1/")
VLLM_API_KEY = os.getenv("VLLM_API_KEY", "dummy-key")

# Initialize DualClient instead of standard AsyncOpenAI
# 預設：同時啟用 vLLM + OpenAI（必要時自動切換）
client_default = DualClient(
    vllm_base_urls=[VLLM_BASE_URL, VLLM_BASE_URL_2],
    vllm_api_key=VLLM_API_KEY,
)

# 僅使用主辦方提供的 vLLM，不啟用 OpenAI fallback
client_vllm_only = DualClient(
    vllm_base_urls=[VLLM_BASE_URL, VLLM_BASE_URL_2],
    vllm_api_key=VLLM_API_KEY,
)
client_vllm_only.openai_client = None

# 僅使用自己的 OpenAI API，不呼叫 vLLM
client_openai_only = DualClient(
    vllm_base_urls=[],
    vllm_api_key=VLLM_API_KEY,
)

app = FastAPI(title="PaiwanTalk AI Router")

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
    # model_mode: "default"（預設：先 vLLM、失敗再 OpenAI）
    #             "vllm_only"（只用主辦 vLLM）
    #             "openai_only"（只用自己的 OPENAI_API_KEY）
    model_mode: Optional[str] = "default"

class ChatResponse(BaseModel):
    reply: str
    model: str
    thinking: Optional[str] = None
    intent: Optional[str] = None # Added intent to response for debugging/UI

@app.get("/")
def root():
    return {"status": "ok", "msg": "PaiwanTalk AI Router Running"}

@app.get("/models")
async def get_models():
    models = await client_default.models.list()
    return models

async def get_default_model_name(active_client: DualClient) -> str:
    models = await active_client.models.list()
    if not getattr(models, "data", None):
        raise RuntimeError("No models available from vLLM server.")
    return models.data[0].id

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    """
    Main entry point.
    1. Identifies intent.
    2. Routes to specific module.
    """
    # 根據前端傳入的 model_mode 選擇實際要用的 client / 模型
    mode = (req.model_mode or "default").lower()

    if mode == "openai_only":
        active_client = client_openai_only
        # 僅用自己的 OpenAI：模型名稱固定為 gpt-4o-mini
        model_name = "gpt-4o-mini"
    else:
        # default 或 vllm_only 都需要跟 vLLM 查可用模型
        active_client = client_default if mode == "default" else client_vllm_only
        try:
            model_name = await get_default_model_name(active_client)
        except Exception as e:
            return ChatResponse(reply="無法取得模型列表", model="unknown", thinking=str(e))

    # Convert Pydantic models to dicts for modules
    messages_list = [{"role": m.role, "content": m.content} for m in req.messages]

    # 1. Classify Intent (using full history)
    intent = await classifier.classify_intent(active_client, model_name, messages_list)
    print(f"DEBUG: Detected Intent: {intent}")

    # 2. Route to Module
    response_data = {}
    
    if intent == "translation":
        response_data = await translator.process(active_client, model_name, messages_list)
    elif intent == "recommendation":
        response_data = await recommender.process(active_client, model_name, messages_list)
    else:
        # Default to chat
        response_data = await chat.process(active_client, model_name, messages_list)

    return ChatResponse(
        reply=response_data.get("reply", ""),
        model=model_name,
        thinking=response_data.get("thinking", ""),
        intent=intent
    )
