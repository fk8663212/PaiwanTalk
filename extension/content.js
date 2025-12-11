// 內容腳本：在頁面上監聽文字選取，顯示一個小方塊觸發翻譯

const PT_API_BASE = "http://localhost:8000";
const PT_BUBBLE_ID = "paiwantalk-translate-bubble";

let ptBubble = null;
let ptCurrentText = "";

function createBubble() {
  if (ptBubble) return ptBubble;
  const div = document.createElement("div");
  div.id = PT_BUBBLE_ID;
  div.textContent = "PT";
  div.style.position = "absolute";
  div.style.zIndex = "2147483647";
  div.style.padding = "4px 6px";
  div.style.fontSize = "12px";
  div.style.fontFamily = "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
  div.style.background = "#1f2933";
  div.style.color = "#fff";
  div.style.borderRadius = "4px";
  div.style.boxShadow = "0 2px 6px rgba(0,0,0,0.3)";
  div.style.cursor = "pointer";
  div.style.display = "none";

  div.addEventListener("click", onBubbleClick);

  document.documentElement.appendChild(div);
  ptBubble = div;
  return div;
}

function hideBubble() {
  if (ptBubble) {
    ptBubble.style.display = "none";
  }
  ptCurrentText = "";
}

function showBubbleNearSelection(text) {
  if (!text.trim()) {
    hideBubble();
    return;
  }

  const selection = window.getSelection();
  if (!selection || selection.rangeCount === 0) {
    hideBubble();
    return;
  }

  const range = selection.getRangeAt(0);
  const rect = range.getBoundingClientRect();
  if (!rect || (rect.x === 0 && rect.y === 0 && rect.width === 0 && rect.height === 0)) {
    hideBubble();
    return;
  }

  const bubble = createBubble();
  ptCurrentText = text;

  const top = window.scrollY + rect.top - 28; // 在選取上方一點點
  const left = window.scrollX + rect.left;

  bubble.style.top = `${Math.max(top, window.scrollY + 4)}px`;
  bubble.style.left = `${Math.max(left, window.scrollX + 4)}px`;
  bubble.textContent = "PT";
  bubble.title = "使用 PaiwanTalk 翻譯";
  bubble.style.display = "block";
}

async function onBubbleClick(event) {
  event.stopPropagation();
  event.preventDefault();

  const text = (ptCurrentText || "").trim();
  if (!text) {
    hideBubble();
    return;
  }

  const bubble = createBubble();
  bubble.textContent = "翻譯中...";

  try {
    // 從 storage 取得目前選擇的模型模式
    const modelMode = await new Promise((resolve) => {
      if (!chrome || !chrome.storage || !chrome.storage.sync) {
        resolve("default");
        return;
      }
      try {
        chrome.storage.sync.get({ model_mode: "default" }, (res) => {
          if (chrome.runtime && chrome.runtime.lastError) {
            console.warn("讀取 model_mode 失敗，改用 default:", chrome.runtime.lastError);
            resolve("default");
            return;
          }
          const value = res && res.model_mode ? res.model_mode : "default";
          resolve(value);
        });
      } catch (e) {
        console.warn("chrome.storage.sync.get 拋出例外，改用 default:", e);
        resolve("default");
      }
    });

    const res = await fetch(`${PT_API_BASE}/api/translate_simple`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, direction: "paiwan2zh", model_mode: modelMode }),
    });
    const data = await res.json();
    const translation = data.translation || "(沒有取得翻譯結果)";

    bubble.textContent = translation;
    bubble.style.whiteSpace = "pre-wrap";
    bubble.style.maxWidth = "260px";
  } catch (err) {
    console.error("PaiwanTalk 翻譯失敗", err);
    const bubble = createBubble();
    bubble.textContent = "翻譯失敗";
  }
}

// 監聽滑鼠放開事件，檢查有沒有文字被選取
window.addEventListener("mouseup", (e) => {
  // 若是點在我們自己的泡泡上，就不要重新判斷選取狀態，避免立刻把泡泡隱藏
  if (ptBubble && e.target === ptBubble) {
    return;
  }

  setTimeout(() => {
    const sel = window.getSelection();
    if (!sel) {
      hideBubble();
      return;
    }
    const text = sel.toString();
    if (!text.trim()) {
      hideBubble();
      return;
    }
    showBubbleNearSelection(text);
  }, 10);
});

// 如果使用者點擊頁面其他地方，且沒有選取文字，就隱藏小方塊
window.addEventListener("mousedown", (e) => {
  if (ptBubble && e.target === ptBubble) return;
  const sel = window.getSelection();
  if (!sel || !sel.toString().trim()) {
    hideBubble();
  }
});

window.addEventListener("scroll", () => {
  // 捲動時簡單地隱藏，避免位置錯亂
  hideBubble();
});
