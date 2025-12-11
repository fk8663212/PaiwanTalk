# PaiwanTalk - 排灣語 AI 學習助手

這是一個結合大型語言模型 (LLM) 與檢索增強生成 (RAG) 技術的排灣語學習助手。旨在提供準確的排灣語翻譯、對話練習、例句推薦以及即時資訊查詢功能。

## 功能特色

1.  **智慧意圖判斷 (Intent Classification)**：
    *   系統會根據使用者輸入的對話歷史，自動判斷意圖並路由至對應模組（翻譯、推薦、搜尋或一般閒聊）。

2.  **多模式功能模組**：
    *   **排灣語翻譯 (Translation)**：
        *   **RAG 字典增強**：整合「千字表」、「教材詞彙」與「華語筆畫字典」，在翻譯前先進行精確的詞彙檢索，減少 AI 幻覺。
        *   **智慧擷取**：自動從混合輸入中擷取排灣語部分進行翻譯，過濾中文指令。
    *   **例句推薦 (Recommendation)**：
        *   基於 Excel 資料庫 (`formosan_pairs_paiwan.xlsx`) 隨機推薦排灣語例句，幫助使用者學習。
    *   **即時搜尋 (Search)**：
        *   整合 **DuckDuckGo** 搜尋引擎，針對時事、天氣或特定知識（如「五年祭」）進行網路檢索。
        *   **在地化優化**：強制針對台灣地區進行搜尋，並由 LLM 整理成繁體中文摘要。
    *   **一般對話 (Chat)**：
        *   具備短期記憶的日常對話功能。

3.  **高可用性架構 (DualClient / Triple Redundancy)**：
    *   **多層次備援**：依序嘗試主辦方提供的兩組 vLLM Host (AMD GPU 加速)。
    *   **自動故障轉移 (Failover)**：若 vLLM 無回應、超時 (Timeout) 或輸出亂碼 (如重複驚嘆號)，自動切換至 OpenAI API (GPT-4o-mini) 以確保服務不中斷。
    *   **穩健性設計**：包含 JSON 輸出修復機制 (`extract_structured`)，確保前端顯示正常。

## 專案結構

```
PaiwanTalk/
├── backend/                    # FastAPI 後端
│   ├── main.py                 # 主程式入口 (Router & FastAPI App)
│   ├── modules/                # 功能模組
│   │   ├── classifier.py       # 意圖分類 (Chat, Translation, Recommendation, Search)
│   │   ├── translator.py       # 翻譯模組 (含 RAG 與擷取邏輯)
│   │   ├── recommender.py      # 推薦模組 (Excel 隨機選句)
│   │   ├── search_test.py      # 搜尋模組 (DuckDuckGo + LLM 摘要)
│   │   ├── chat.py             # 一般對話模組
│   │   ├── dual_client.py      # 多重備援客戶端 (vLLM list -> OpenAI)
│   │   └── utils.py            # 工具函式 (JSON 修復等)
│   ├── data/                   # 資料庫
│   │   ├── unique_data.json
│   │   ├── formosan_pairs_paiwan.xlsx  # 推薦句庫
│   │   └── ... (其他字典檔)
│   └── paiwan_translation_api_multi.py # 字典查詢核心邏輯
├── frontend/                   # 網頁前端
│   ├── index.html
│   ├── script.js
│   └── style.css
└── requirements.txt            # Python 依賴
```

## 安裝與執行

### 1. 環境設定

建議使用虛擬環境 (Virtual Environment) 以避免套件衝突。

```bash
# 建立虛擬環境 (若尚未建立)
python3 -m venv ~/paiwantalk-venv

# 啟動虛擬環境
source ~/paiwantalk-venv/bin/activate

# 安裝依賴套件
pip install -r requirements.txt
```

### 2. 設定環境變數

專案使用 `.env` 檔案管理設定。請在 `backend/` 目錄下確認或建立 `.env`：

```env
OPENAI_API_KEY="your_openai_api_key"
VLLM_BASE_URL="http://host1:port/v1/"
VLLM_BASE_URL_2="http://host2:port/v1/"
VLLM_API_KEY="dummy-key"
```

### 3. 啟動後端伺服器

進入 `backend` 目錄並啟動 FastAPI：

```bash
cd backend
# 使用虛擬環境中的 uvicorn
~/paiwantalk-venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

伺服器將在 `http://0.0.0.0:8000` 啟動。

### 4. 啟動前端

您可以直接開啟 `frontend/index.html`，或使用簡易 HTTP Server：

```bash
cd frontend
python3 -m http.server 8080
```

打開瀏覽器訪問 `http://localhost:8080` 即可使用。

## 技術細節

*   **Backend Framework**: FastAPI
*   **LLM Integration**: AsyncOpenAI SDK (Compatible with vLLM & OpenAI)
*   **Search**: DuckDuckGo Search (ddgs)
*   **Data Processing**: Pandas, OpenPyXL (Excel handling), FuzzyWuzzy (String matching)
*   **Frontend**: Vanilla JavaScript, HTML5, CSS3

---
Developed for AMD AI Agent Online Hackathon.
