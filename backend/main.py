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
client = DualClient(
    vllm_base_urls=[VLLM_BASE_URL, VLLM_BASE_URL_2],
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
    models = await client.models.list()
    return models

async def get_default_model_name() -> str:
    models = await client.models.list()
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
    try:
        model_name = await get_default_model_name()
    except Exception as e:
        return ChatResponse(reply="無法取得模型列表", model="unknown", thinking=str(e))

    # Convert Pydantic models to dicts for modules
    messages_list = [{"role": m.role, "content": m.content} for m in req.messages]

    # 1. Classify Intent (using full history)
    intent = await classifier.classify_intent(client, model_name, messages_list)
    print(f"DEBUG: Detected Intent: {intent}")

    # 2. Route to Module
    response_data = {}
    
    if intent == "translation":
        response_data = await translator.process(client, model_name, messages_list)
    elif intent == "recommendation":
        response_data = await recommender.process(client, model_name, messages_list)
    else:
        # Default to chat
        response_data = await chat.process(client, model_name, messages_list)

    return ChatResponse(
        reply=response_data.get("reply", ""),
        model=model_name,
        thinking=response_data.get("thinking", ""),
        intent=intent
    )
