// 背景 service worker：處理右鍵選單，並觸發 popup 進行翻譯

// 建立右鍵菜單
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "paiwantalk-translate",
    title: "使用 PaiwanTalk 翻譯選取文字",
    contexts: ["selection"],
  });
});

// 右鍵選單點擊事件
chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId !== "paiwantalk-translate") return;
  const text = info.selectionText || "";
  if (!text.trim()) return;

  // 先嘗試打開 popup（必須在使用者操作的同步呼叫堆疊中執行）
  if (chrome.action && chrome.action.openPopup) {
    chrome.action.openPopup().catch((err) => {
      console.error("無法開啟 popup", err);
    });
  }

  // 再非同步地把選取文字與自動翻譯旗標存到 storage，讓 popup 讀取
  if (chrome.storage && chrome.storage.sync) {
    chrome.storage.sync.set({ pending_text: text, pending_translate: true }, () => {
      if (chrome.runtime.lastError) {
        console.error("設定 pending_text 失敗", chrome.runtime.lastError);
      }
    });
  }
});
