import json
import os
import re
from typing import Dict, List, Tuple, Optional
from enum import Enum
from collections import defaultdict

from fuzzywuzzy import fuzz
from fastapi import FastAPI, HTTPException, Response, Query, Path
from pydantic import BaseModel

# ========= 基本設定 =========
# 你可以改這裡來指定實體檔案位置
DATA_DIR = os.environ.get("PAIWAN_DATA_DIR", "data")

SOURCE_FILES = {
    "qianzi": os.path.join(DATA_DIR, "千字表(東排灣語).json"),
    "jiaocai": os.path.join(DATA_DIR, "教材_paiwan_words.json"),
    "bihua":  os.path.join(DATA_DIR, "華語筆畫字典.json"),
}

# 合併時的優先級（數字愈大優先）
SOURCE_WEIGHTS = {
    "jiaocai": 1.0,
    "qianzi": 0.9,
    "bihua":  0.7,
}

# 模糊匹配門檻與保護條件
FUZZ_THRESHOLD = 85
MAX_LEN_GAP = 3           # 與查詢詞的長度差距限制（防暴衝誤配）
MAX_CANDIDATES_PER_SRC = 8  # 每個來源最多保留的模糊候選

# ========= 資料模型 =========
class TranslateRequest(BaseModel):
    text: str

class TranslateResponse(BaseModel):
    original_text: str
    translation: str
    success: bool
    source: str

class SourceEnum(str, Enum):
    qianzi = "qianzi"
    jiaocai = "jiaocai"
    bihua = "bihua"
    all = "all"

# ========= 工具 =========
def normalize_token(s: str) -> str:
    # 基本歸一化（小寫、去除空白/常見分隔）
    s = s.strip().lower()
    s = re.sub(r"[ \t\r\n·、，,；;．.]", "", s)
    return s

# ========= 多來源翻譯器 =========
class MultiSourceTranslator:
    def __init__(self, sources: Dict[str, str]):
        """
        sources: {source_name: file_path}
        """
        self.sources = sources
        self.dicts: Dict[str, Dict[str, List[str]]] = {}          # 每個來源的 {paiwan: [chinese,...]}
        self.norm_keys: Dict[str, Dict[str, str]] = {}            # 每個來源的 {normalized_paiwan: original_paiwan}
        self.load_all()

    def load_one(self, src_name: str, file_path: str) -> Tuple[Dict[str, List[str]], Dict[str, str]]:
        mapping: Dict[str, List[str]] = defaultdict(list)
        norm_map: Dict[str, str] = {}

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            raise RuntimeError(f"載入來源 {src_name} 失敗：{file_path} ({e})")

        # 支援兩種形態：[{paiwan, chinese}, ...] 或 [{paiwan, chinese:[...]}, ...]
        for row in data:
            pw = (row.get("paiwan") or "").strip()
            zh = row.get("chinese")
            if not pw or zh is None:
                continue

            # 統一成 list
            zh_list = zh if isinstance(zh, list) else [zh]

            # 過濾無效項
            cleaned = [z.strip() for z in zh_list
                       if isinstance(z, str) and z.strip() and z.strip() not in ("[虛]", "[虛")]
            if not cleaned:
                continue

            if pw not in mapping:
                mapping[pw] = []

            # 去重、保持插入順序
            seen = set(mapping[pw])
            for z in cleaned:
                if z not in seen:
                    mapping[pw].append(z)
                    seen.add(z)

        # 準備 normalized 鍵
        for k in mapping.keys():
            nk = normalize_token(k)
            # 若不同原字詞歸一化後碰撞，只保留第一個
            norm_map.setdefault(nk, k)

        return mapping, norm_map

    def load_all(self):
        for name, path in self.sources.items():
            m, norm = self.load_one(name, path)
            self.dicts[name] = m
            self.norm_keys[name] = norm

    def _exact_lookup(self, src: str, text: str) -> Optional[List[str]]:
        """
        先精確（含 normalized 精確）
        """
        d = self.dicts[src]
        if text in d:
            return d[text]

        # normalized 精確
        nk = normalize_token(text)
        orig = self.norm_keys[src].get(nk)
        if orig and orig in d:
            return d[orig]
        return None

    def _fuzzy_candidates(self, src: str, text: str) -> List[Tuple[int, str, List[str]]]:
        """
        回傳 [(score, word, translations), ...]，已過濾/排序/截斷
        """
        d = self.dicts[src]
        text_norm = normalize_token(text)
        out = []

        for word, translations in d.items():
            word_norm = normalize_token(word)

            # 先做長度保護，避免長/短詞誤配
            if abs(len(text_norm) - len(word_norm)) > MAX_LEN_GAP:
                continue

            # partial_ratio 對黏連、分詞差異較穩定
            score = fuzz.partial_ratio(text_norm, word_norm)
            if score >= FUZZ_THRESHOLD:
                out.append((score, word, translations))

        # 高分在前，取前若干個
        out.sort(key=lambda x: x[0], reverse=True)
        return out[:MAX_CANDIDATES_PER_SRC]

    def translate_from_source(self, src: str, text: str) -> List[str]:
        # 精確命中直接回傳
        exact = self._exact_lookup(src, text)
        if exact:
            return exact

        # 模糊命中（合併同分候選的翻譯，並去重）
        cands = self._fuzzy_candidates(src, text)
        if not cands:
            return []

        best = cands[0][0]
        merged: List[str] = []
        seen = set()
        for score, _w, zs in cands:
            if score < best:  # 只合併同最高分群
                break
            for z in zs:
                if z not in seen:
                    merged.append(z)
                    seen.add(z)
        return merged

    def translate(self, text: str, source: SourceEnum) -> Tuple[str, List[str]]:
        """
        回傳 (used_source, translations)
        """
        if source != SourceEnum.all:
            translations = self.translate_from_source(source.value, text)
            print( f"Translate from {source.value}: {text} -> {translations}" )
            return (source.value, translations)

        # all：依權重逐一嘗試，先看是否「任一來源精確命中」
        # 再做加權合併（避免低品質來源蓋過高品質）
        exact_pool: Dict[str, List[str]] = {}
        for src in SOURCE_WEIGHTS:
            exact = self._exact_lookup(src, text)
            if exact:
                exact_pool[src] = exact

        if exact_pool:
            # 有精確命中的話，依權重排序後合併（高權重在前）
            merged: List[str] = []
            seen = set()
            for src in sorted(exact_pool.keys(), key=lambda s: SOURCE_WEIGHTS[s], reverse=True):
                for z in exact_pool[src]:
                    if z not in seen:
                        merged.append(z)
                        seen.add(z)
            print( f"Translate from all(精確): {text} -> {merged}" )
            return ("all(exact)", merged)

        # 沒有精確命中 → 模糊命中加權合併（只合併各來源最高分群）
        bucket = []
        for src in SOURCE_WEIGHTS:
            zs = self.translate_from_source(src, text)
            if zs:
                bucket.append((src, zs))

        if not bucket:
            print( f"Translate from all(none): {text} -> []" )
            return ("all", [])

        # 依權重把結果拼起來，避免低權重來源蓋掉高權重
        merged: List[str] = []
        seen = set()
        for src, zs in sorted(bucket, key=lambda x: SOURCE_WEIGHTS[x[0]], reverse=True):
            for z in zs:
                if z not in seen:
                    merged.append(z)
                    seen.add(z)
        print( f"Translate from all(fuzzy): {text} -> {merged}" )
        return ("all(fuzzy)", merged)

# ========= FastAPI =========
app = FastAPI(title="排灣語多來源翻譯 API", description="排灣語與中文翻譯（多資料來源）")

translator: Optional[MultiSourceTranslator] = None

@app.on_event("startup")
async def startup_event():
    global translator
    # 檔案存在檢查（避免啟動後才出錯）
    for name, path in SOURCE_FILES.items():
        if not os.path.exists(path):
            # 提示但不阻止啟動，讓 /sources 可以展示狀態
            print(f"[警告] 來源 {name} 檔案不存在：{path}")
    translator = MultiSourceTranslator(SOURCE_FILES)
    print("[OK] 已載入多來源字典：", ", ".join(translator.sources.keys()))

@app.get("/sources")
async def list_sources():
    return {
        "sources": list(SOURCE_FILES.keys()) + ["all"],
        "weights": SOURCE_WEIGHTS,
        "data_dir": DATA_DIR
    }

@app.post("/translate/{source}", response_model=TranslateResponse)
async def translate_by_path(
    source: SourceEnum = Path(..., description="qianzi | jiaocai | bihua | all"),
    request: TranslateRequest = None,
    response: Response = None
):
    if response is not None:
        response.headers["Connection"] = "close"
    if not request or not request.text.strip():
        raise HTTPException(status_code=400, detail="輸入文字不能為空")
    used, translations = translator.translate(request.text, source)
    success = len(translations) > 0
    return TranslateResponse(
        original_text=request.text,
        translation=", ".join(translations) if success else request.text,
        success=success,
        source=used
    )

@app.post("/translate", response_model=TranslateResponse)
async def translate_default(
    request: TranslateRequest,
    response: Response,
    source: SourceEnum = Query(SourceEnum.all, description="qianzi | jiaocai | bihua | all")
):
    response.headers["Connection"] = "close"
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="輸入文字不能為空")
    used, translations = translator.translate(request.text, source)
    success = len(translations) > 0
    return TranslateResponse(
        original_text=request.text,
        translation=", ".join(translations) if success else request.text,
        success=success,
        source=used
    )

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "paiwan_multi_sources", "endpoints": ["/translate/{source}", "/translate", "/sources"]}
