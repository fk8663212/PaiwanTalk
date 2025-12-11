const API_BASE = "http://localhost:8000";

const inputEl = document.getElementById("input");
const resultEl = document.getElementById("result");
const thinkingEl = document.getElementById("thinking");
const btn = document.getElementById("translateBtn");
const modelModeEl = document.getElementById("modelMode");

// 初始化：從 storage 載入上次選擇的模型與待翻譯文字
if (chrome && chrome.storage && chrome.storage.sync) {
  chrome.storage.sync.get(
    { model_mode: "default", pending_text: "", pending_translate: false },
    (res) => {
      if (modelModeEl) {
        const savedMode = res && res.model_mode ? res.model_mode : "default";
        modelModeEl.value = savedMode;
      }

      const pendingText = (res && res.pending_text) || "";
      const shouldAutoTranslate = !!(res && res.pending_translate);

      if (pendingText && inputEl) {
        inputEl.value = pendingText;
      }

      if (pendingText && shouldAutoTranslate) {
        // 清掉旗標避免下次重複自動翻譯
        chrome.storage.sync.set({ pending_translate: false });
        doTranslate(pendingText);
      }
    }
  );

  // 當使用者變更選項時，立即寫回 storage
  if (modelModeEl) {
    modelModeEl.addEventListener("change", () => {
      const value = modelModeEl.value || "default";
      chrome.storage.sync.set({ model_mode: value });
    });
  }
}

async function doTranslate(text) {
  const t = (text || "").trim();
  if (!t) {
    resultEl.textContent = "請先輸入要翻譯的文字。";
    thinkingEl.textContent = "";
    return;
  }

  resultEl.textContent = "翻譯中...";
  thinkingEl.textContent = "";

  try {
    const modelMode = (modelModeEl && modelModeEl.value) || "default";
    const res = await fetch(`${API_BASE}/api/translate_simple`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: t, direction: "paiwan2zh", model_mode: modelMode }),
    });
    const data = await res.json();
    resultEl.textContent = data.translation || "(沒有取得翻譯結果)";
    thinkingEl.textContent = data.thinking || "";
  } catch (err) {
    console.error(err);
    resultEl.textContent = "呼叫後端翻譯 API 失敗。";
    thinkingEl.textContent = String(err);
  }
}

btn.addEventListener("click", () => {
  doTranslate(inputEl.value);
});
