# PaiwanTalk - 排灣語 AI 學習助手

這是一個結合大型語言模型 (LLM) 與檢索增強生成 (RAG) 技術的排灣語學習助手。旨在提供準確的排灣語翻譯、對話練習與例句推薦。

## 功能特色

1.  **多模式對話系統**：
    *   **一般對話 (Normal Chat)**：與 AI 進行日常排灣語或中文對話，具備短期記憶功能。
    *   **排灣語翻譯 (Translation)**：專精於排灣語轉中文的翻譯功能。
        *   **RAG 字典增強**：整合「千字表」、「教材詞彙」與「華語筆畫字典」，在翻譯前先進行精確的詞彙檢索，減少 AI 幻覺。
        *   **自動語言辨識**：自動擷取輸入中的排灣語部分進行翻譯，過濾中文指令。
    *   **例句推薦 (Recommendation)**：根據關鍵字提供排灣語例句。

2.  **高可用性架構 (DualClient)**：
    *   優先使用地端 vLLM 模型 (AMD GPU 加速)。
    *   自動故障轉移 (Failover)：若地端模型無回應或輸出異常 (如重複符號)，自動切換至 OpenAI API (GPT-4o-mini) 以確保服務不中斷。

## 專案結構

```
PaiwanTalk/
├── backend/                # FastAPI 後端
│   ├── main.py             # 主程式入口 (Router)
│   ├── modules/            # 功能模組
│   │   ├── classifier.py   # 意圖分類
│   │   ├── translator.py   # 翻譯模組 (含 RAG 邏輯)
│   │   ├── chat.py         # 一般對話模組
│   │   ├── recommend.py    # 推薦模組
│   │   └── dual_client.py  # 雙客戶端封裝 (vLLM + OpenAI)
│   ├── data/               # 字典資料庫 (.json)
│   └── paiwan_translation_api_multi.py # 字典查詢核心
├── frontend/               # 網頁前端
│   ├── index.html
│   ├── script.js
│   └── style.css
└── requirements.txt        # Python 依賴
```

## 安裝與執行

### 1. 環境設定

請確保已安裝 Python 3.10+。

```bash
pip install -r requirements.txt
```

設定環境變數 (建議建立 `.env` 檔案或直接 export)：

```bash
export OPENAI_API_KEY="your_openai_api_key"
# 若有自建 vLLM Server，程式碼中已預設兩組 Host，可於 backend/modules/dual_client.py 中修改
```

### 2. 啟動後端

進入 `backend` 目錄並啟動 FastAPI 伺服器：

```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. 啟動前端

進入 `frontend` 目錄並啟動簡易網頁伺服器：

```bash
cd frontend
python3 -m http.server 8080
```

打開瀏覽器訪問 `http://localhost:8080` 即可使用。

## 技術細節

*   **Backend**: FastAPI
*   **AI Client**: AsyncOpenAI (相容 vLLM 與 OpenAI)
*   **RAG**: FuzzyWuzzy (模糊搜尋), Custom Dictionary Logic
*   **Frontend**: Vanilla JS + HTML5

---
Developed for AMD AI Agent Online Hackathon.
