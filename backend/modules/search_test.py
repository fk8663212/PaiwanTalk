import os
import re
import asyncio
import requests
from bs4 import BeautifulSoup
from ddgs import DDGS
from openai import AsyncOpenAI
from typing import List, Dict, Any


# 設定爬取內容長度限制 (避免超過 Context Window)
MAX_CHARS_PER_PAGE = 3000


def _simplify_query(raw: str, fallback: str) -> str:
    """將 LLM 產生的關鍵字字串簡化成較短、較乾淨的搜尋 query。

    - 移除多餘空白與常見贅詞（如「是什麼」、「如何」、「請問」等）。
    - 只保留前幾個關鍵詞，避免 query 過長、過雜。
    """

    s = re.sub(r"\s+", " ", raw).strip()
    if not s:
        return fallback

    # 依標點與空白切詞
    tokens = re.split(r"[,\u3001;，。！？\?、\s]+", s)
    stopwords = {
        "是什麼", "是甚麼", "為什麼", "為何", "如何", "怎麼", "怎樣",
        "請問", "幫我", "介紹", "說明", "分析", "解釋", "的", "一下",
    }

    filtered: List[str] = []
    for t in tokens:
        t = t.strip()
        if not t or t in stopwords:
            continue
        filtered.append(t)
        if len(filtered) >= 5:
            break

    if not filtered:
        return fallback

    return " ".join(filtered)

# =========================================

async def get_llm_decision_and_query(client: AsyncOpenAI, model_name: str, messages: List[Dict[str, str]]):
    """（目前未在主流程使用）

    第一階段：LLM 判斷是否需要搜索。
    如果需要，回傳搜索字串；如果不需要，回傳直接答案。
    為了簡化解析，我們要求 LLM 使用特定前綴。
    """
    system_prompt = """
    You are a smart decision-making assistant.
    Determine if the user's request requires real-time information or external data (web search).

    Rules:
    1. If web search is needed (e.g., current events, weather, specific stats), output ONLY the best search keywords.Answer in Traditional Chinese.
    2. If no search is needed (e.g., general knowledge, coding, translation, chat), output ONLY the number "0".

    Do not provide any explanations or extra text.
    """
    # 不直接修改原 messages，建立新的 decision_messages
    decision_messages: List[Dict[str, str]] = [
        {"role": "system", "content": system_prompt}
    ] + list(messages)

    response = await client.chat.completions.create(
        model=model_name,
        messages=decision_messages,
        max_tokens=100,
        temperature=0.0,
    )
    
    content = response.choices[0].message.content.strip()

    # 判斷邏輯
    if content == "0":
        return False, None
    else:
        # 如果不是 0，代表內容就是搜尋關鍵字
        return True, content


async def extract_search_query(client: AsyncOpenAI, model_name: str, question: str) -> str:
    """讓 LLM 幫忙把使用者問題轉成適合搜尋的關鍵字。

    規則：
    - 不要直接回答問題，只輸出關鍵字（5-20 個字之內）。
    - 可以用繁體中文或中英混合，但以繁體中文為主。
    - 不要加前後解釋文字，只輸出關鍵字本身。
    """

    system_prompt = """
    You are a search query generator for a chatbot about Taiwan Indigenous Peoples (especially the Paiwan people).
    Given a user's question (likely in Traditional Chinese),
    generate a concise set of search keywords suitable for DuckDuckGo web search.

    Requirements:
    - Use Traditional Chinese when appropriate.
    - Focus on the core topic and related entities (people, places, organizations, languages, rituals).
    - If the question may relate to Taiwan Indigenous culture or rituals (e.g. 包含「五年祭」、「祭典」、「祭儀」、「部落」、「原住民」、「排灣」等詞),
      then include relevant terms such as「排灣族」、「台灣原住民」、「祭儀」、「傳統文化」 in the keywords.
    - Length: roughly 5 to 20 characters/words.
    - Do NOT answer the question.
    - Output ONLY the search keywords, with no extra explanation.
    """

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]

    try:
        response = await client.chat.completions.create(
            model=model_name,
            messages=messages,
            max_tokens=64,
            temperature=0.2,
        )
        query_raw = (response.choices[0].message.content or "").strip()
        if not query_raw:
            return question

        # 將 LLM 產生的關鍵字進一步簡化，避免 query 過長或太雜
        query = _simplify_query(query_raw, fallback=question)
        return query
    except Exception as e:
        # 發生錯誤時退回直接用原始問題搜尋，避免整體流程失敗
        print(f"⚠️ extract_search_query 失敗，改用原始問題：{e}")
        return question

async def get_web_summary(client: AsyncOpenAI, model_name: str, messages: List[Dict[str, str]], query: str, max_results: int = 3) -> Dict[str, Any]:
    """整合函式：執行 搜尋 -> 爬取 -> 濃縮 的完整流程。

    回傳：{"summary": str, "sources": List[{"title": str, "url": str}]}
    """
    print(f"🔍 [搜尋] 正在 DuckDuckGo 查詢: {query} ...")
    
    # --- 1. 執行搜尋 (使用 to_thread 避免卡住) ---
    def run_search():
        results = []
        with DDGS() as ddgs:
            # 這裡的 ddgs.text 是同步的，所以包在函式裡跑
            # region 設為台灣繁體，讓結果更偏向在地與華文內容
            search_gen = ddgs.text(query, max_results=max_results, region="tw-tzh")
            if search_gen:
                for r in search_gen:
                    results.append(r)
        return results

    # 在背景執行搜尋
    search_results = await asyncio.to_thread(run_search)

    if not search_results:
        return {"summary": "搜尋無結果。", "sources": []}

    # --- 2. 執行爬取 (依序爬取前 N 筆) ---
    aggregated_content = ""
    used_sources: List[Dict[str, str]] = []
    
    for idx, res in enumerate(search_results):
        url = res['href']
        title = res['title']
        print(f"📄 [爬取] 正在讀取第 {idx+1} 筆: {title}")

        # 定義單一爬取動作 (同步程式碼)
        def fetch_one():
            try:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
                resp = requests.get(url, headers=headers, timeout=5)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, 'html.parser')
                for tag in soup(["script", "style", "nav", "footer", "iframe"]):
                    tag.extract()
                return soup.get_text(separator=' ', strip=True)[:MAX_CHARS_PER_PAGE]
            except Exception as e:
                print(f"⚠️ 無法讀取 {url}: {e}")
                return ""

        # 在背景執行爬取
        content = await asyncio.to_thread(fetch_one)
        
        if content:
            aggregated_content += f"\n=== 來源 {idx+1}: {title} ({url}) ===\n{content}\n"
            used_sources.append({"title": title, "url": url})

    if not aggregated_content:
        print("⚠️ 無法從任何搜尋結果中提取有效文字。")
        return {"summary": "無法從搜尋結果中提取有效文字。", "sources": []}

    # --- 3. 執行濃縮 (LLM) ---
    print("🧠 [濃縮] 正在整理資訊...")
    
    # 修改重點：Prompt 改為英文，並強制要求輸出繁體中文
    system_prompt = (
        "You are a professional researcher. "
        "Read the provided raw web data and extract the 3-5 most relevant key points "
        "based on the user's question. Ignore ads and irrelevant noise. "
        "IMPORTANT: You must output the final summary in Traditional Chinese (繁體中文)."
    )

    user_prompt = f"""
    User Question: {query}

    --- Web Collected Data ---
    {aggregated_content}
    """

    # 使用 await 非同步呼叫 OpenAI
    response = await client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )

    summary = response.choices[0].message.content
    return {"summary": summary, "sources": used_sources}


async def process(client: AsyncOpenAI, model_name: str, messages: List[Dict[str, str]]) -> Dict[str, Any]:
    """整合入口：用於主系統 router 的搜尋模組。

    步驟：
    1. 從對話歷史中抓出最新一則 user 問句。
    2. 若問題跟原住民族／排灣族相關，強化搜尋關鍵字。
    3. 以（可能加權後的）問句作為 query 呼叫 get_web_summary。
    4. 回傳符合主系統格式的 {"reply", "thinking"}。
    """

    # 1. 抓最新一則 user 問句作為搜尋關鍵字
    user_question = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_question = str(msg.get("content", "")).strip()
            if user_question:
                break

    if not user_question:
        return {
            "reply": "沒有找到可以用來搜尋的使用者問題。",
            "thinking": "Search module: no user question detected.",
        }

    # 2. 根據關鍵字判斷是否為原住民族／排灣族相關查詢，若是則加強關鍵字
    indigenous_keywords = [
        "排灣", "排灣族", "paiwan", "原住民", "原民", "族語", "母語", "南島語",
        "阿美族", "泰雅族", "布農族", "魯凱族", "卑南族", "鄒族", "賽夏族",
        "五年祭", "五年祭典", "五年大祭",
    ]

    is_indigenous_question = any(k.lower() in user_question.lower() for k in indigenous_keywords)

    # 2.5 只從使用者問題本身抓關鍵詞，不再讓 LLM 產生 query
    # 優先抓出在 indigenous_keywords 裡出現的詞，例如「五年祭」、「排灣族」
    base_query = user_question
    lower_q = user_question.lower()
    matched_keywords: List[str] = []
    for kw in indigenous_keywords:
        if kw.lower() in lower_q and kw not in matched_keywords:
            matched_keywords.append(kw)

    if matched_keywords:
        # 例如「你能介紹一下五年祭嗎？」 -> "五年祭"
        base_query = " ".join(matched_keywords)

    # 3. 呼叫 web 搜尋與摘要（不再額外附加長串關鍵字）
    web_result = await get_web_summary(client, model_name, messages, base_query)
    summary = web_result.get("summary", "")
    sources = web_result.get("sources", [])

    # 4. 依照現有 UI 格式回傳，並把實際使用到的來源網站列在 thinking 裡
    thinking_lines = [
        f"已針對「{user_question}」透過 DuckDuckGo 進行網路搜尋並整理重點。"
        + ("（已針對原住民族／排灣族相關主題加強關鍵字。)" if is_indigenous_question else ""),
    ]

    if sources:
        thinking_lines.append("使用的主要資料來源：")
        for src in sources:
            title = src.get("title") or "(無標題)"
            url = src.get("url") or "(無網址)"
            thinking_lines.append(f"- {title} ({url})")

    thinking = "\n".join(thinking_lines)

    return {
        "reply": summary,
        "thinking": thinking,
    }