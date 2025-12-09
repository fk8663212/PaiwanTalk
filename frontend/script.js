const backendUrl = "http://localhost:8000/chat"; // 之後部署時改成你的後端 URL

const messagesEl = document.getElementById("messages");
const inputEl = document.getElementById("user-input");
const sendBtn = document.getElementById("send-btn");

function appendMessage(text, type) {
  const div = document.createElement("div");
  div.className = `message ${type}`;
  div.textContent = text;
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

async function sendMessage() {
  const text = inputEl.value.trim();
  if (!text) return;

  appendMessage(text, "user");
  inputEl.value = "";
  inputEl.focus();

  appendMessage("思考中...", "bot");
  const thinkingBubble = messagesEl.lastChild;

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
    thinkingBubble.textContent = data.reply || "(空回覆)";
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
