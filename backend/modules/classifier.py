import json
from openai import AsyncOpenAI
from typing import List, Dict

async def classify_intent(client: AsyncOpenAI, model_name: str, messages: List[Dict[str, str]]) -> str:
    """
    Classify the user's intent based on the full conversation history.
    Categories:
    - 'translation': User wants to translate text to Paiwan.
    - 'recommendation': User wants example sentences or learning materials.
    - 'chat': Normal conversation or unclear intent.
    - 'search': User asks for up-to-date factual information that likely requires web search
                (e.g. current events, today's weather, latest statistics, rankings, etc.).
    """
    
    system_prompt = (
        "You are an intelligent intent classifier for a Paiwan language learning assistant. "
        "Analyze the conversation history, especially the latest user message, to determine the user's current intent.\n\n"
        "Categories:\n"
        "1. 'translation': \n"
        "   - The user inputs text that looks like Paiwan language (Latin alphabet, often containing 'j', 'q', 'v', 'z', 'ng', 'tj', 'dj', 'lj').\n"
        "   - The user explicitly asks to translate Paiwan text to Chinese.\n"
        "   - Example: 'tjaquvuquvulj', 'nanguaq', 'ti sun a kemeljang'.\n"
        "2. 'recommendation': \n"
        "   - The user asks for example sentences, learning materials, or random sentences.\n"
        "   - Keywords: '例句', '推薦', '句子', '教我一句', '隨機'.\n"
        "3. 'chat': \n"
        "   - General conversation in Chinese or English.\n"
        "   - Greetings like '你好', '早安'.\n"
        "   - Questions about the bot.\n"
        "   - If the user inputs Chinese text (even if they ask to translate it to Paiwan, we classify as chat because we only support Paiwan->Chinese translation).\n\n"
        "4. 'search': \n"
        "   - The user asks about current news, today's weather, recent statistics, rankings, prices, or any information that clearly depends on up-to-date web data.\n"
        "   - Example: '今天台北的天氣如何？', '今年金馬獎最佳影片是誰？', '目前美元對台幣匯率多少？','介紹一下五年祭'.\n\n"
        "Return a JSON object with a single key 'intent'. Value must be one of: 'translation', 'recommendation', 'chat', 'search'.\n"
        "Example: {\"intent\": \"translation\"}"
    )

    # Prepare messages for the classifier, keeping the system prompt separate
    classifier_messages = [{"role": "system", "content": system_prompt}]
    
    # Add recent history (e.g., last 5 messages) to provide context without consuming too many tokens
    # We filter out system messages from the original history to avoid confusing the classifier
    recent_messages = messages[-5:] if len(messages) > 5 else messages
    for msg in recent_messages:
        if msg["role"] != "system":
             # Ensure content is string
             classifier_messages.append({"role": msg["role"], "content": str(msg["content"])})

    print(f"DEBUG: Classifier messages: {json.dumps(classifier_messages, ensure_ascii=False)}")

    try:
        completion = await client.chat.completions.create(
            model=model_name,
            messages=classifier_messages,
            temperature=0.1,
            max_tokens=50,
            # response_format={"type": "json_object"} # Removing this to avoid potential 400 errors
        )
        
        content = completion.choices[0].message.content
        
        # Try to parse JSON
        try:
            result = json.loads(content)
            return result.get("intent", "chat")
        except json.JSONDecodeError:
            # Fallback: check for keywords in the raw content
            if "search" in content:
                return "search"
            if "translation" in content:
                return "translation"
            elif "recommendation" in content:
                return "recommendation"
            return "chat"
            
    except Exception as e:
        print(f"Classifier Error: {e}")
        return "chat"
