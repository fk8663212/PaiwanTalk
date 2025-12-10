// 指向 n8n「Production URL」，不用按 listen 就能收；若要改回本機可設為 http://localhost:8000/chat
//const backendUrl = "https://a38ea8040ab2.ngrok-free.app/webhook/paiwan-chat";
const backendUrl = "http://localhost:8000/chat";

const messagesEl = document.getElementById("messages");
const inputEl = document.getElementById("user-input");
const sendBtn = document.getElementById("send-btn");
const chips = document.querySelectorAll(".chip");

function closeThinkingModal() {
  const existing = document.querySelector(".thinking-modal-overlay");
  if (existing) existing.remove();
}

function openThinkingModal(thinkingText) {
  closeThinkingModal();

  const overlay = document.createElement("div");
  overlay.className = "thinking-modal-overlay";

  const modal = document.createElement("div");
  modal.className = "thinking-modal";

  const header = document.createElement("div");
  header.className = "thinking-modal-header";
  header.textContent = "思考過程";

  const closeBtn = document.createElement("button");
  closeBtn.className = "thinking-close";
  closeBtn.textContent = "×";
  closeBtn.addEventListener("click", closeThinkingModal);
  header.appendChild(closeBtn);

  const body = document.createElement("pre");
  body.className = "thinking-body";
  body.textContent = thinkingText;

  modal.appendChild(header);
  modal.appendChild(body);
  overlay.appendChild(modal);

  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) {
      closeThinkingModal();
    }
  });

  document.addEventListener(
    "keydown",
    (e) => {
      if (e.key === "Escape") closeThinkingModal();
    },
    { once: true }
  );

  document.body.appendChild(overlay);
}

function appendMessage({ text, type, thinking }) {
  const div = document.createElement("div");
  div.className = `message ${type}`;

  const chatPanel = messagesEl.closest(".chat-panel");
  chatPanel?.classList.remove("empty");

  if (thinking) {
    const badge = document.createElement("button");
    badge.className = "thinking-tag";
    badge.textContent = "已思考 ▸";
    badge.addEventListener("click", () => openThinkingModal(thinking));
    div.appendChild(badge);
  }

  const textBlock = document.createElement("div");
  textBlock.className = "message-text";
  textBlock.textContent = text;
  div.appendChild(textBlock);

  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return div;
}

async function sendMessage() {
  const text = inputEl.value.trim();
  if (!text) return;

  // Enter chat mode layout
  document.querySelector('.page').classList.add('chat-mode');

  appendMessage({ text, type: "user" });
  inputEl.value = "";
  inputEl.focus();

  const thinkingBubble = appendMessage({ text: "思考中...", type: "bot" });

  try {
    const resp = await fetch(backendUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ message: text }),
    });

    if (!resp.ok) {
      thinkingBubble.textContent = `錯誤：${resp.status}`;
      return;
    }

    const data = await resp.json();
    const finalText = data.reply || "(空回覆)";
    const botMsg = appendMessage({
      text: finalText,
      type: "bot",
      thinking: data.thinking,
    });
    messagesEl.replaceChild(botMsg, thinkingBubble);
  } catch (err) {
    thinkingBubble.textContent = "呼叫後端失敗，請稍後再試。";
    console.error(err);
  }
}

sendBtn.addEventListener("click", sendMessage);

inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

chips.forEach((chip) => {
  chip.addEventListener("click", () => {
    const prompt = chip.dataset.prompt || chip.textContent;
    inputEl.value = prompt;
    sendMessage();
  });
});
