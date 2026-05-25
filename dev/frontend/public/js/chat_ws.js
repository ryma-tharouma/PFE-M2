// WebSocket client for streaming chat with typing indicator
// Usage: include this script on your chat page and ensure the following elements exist:
// - #chat-area (container where messages will be appended)
// - #chat-input (textarea or input for the message)
// - #chat-send (button to send)
// - #typing-indicator (element to show typing)

(function () {
  const WS_URL = (window.location.protocol === 'https:' ? 'wss://' : 'ws://') + window.location.host + '/ws/chat';

  let socket = null;
  let assistantMessageEl = null;

  function showTyping(status) {
    const el = document.getElementById('typing-indicator');
    if (!el) return;
    el.style.display = status ? 'block' : 'none';
  }

  function appendUserMessage(text) {
    const area = document.getElementById('chat-area');
    if (!area) return;
    const div = document.createElement('div');
    div.className = 'message user-message';
    div.textContent = text;
    area.appendChild(div);
    area.scrollTop = area.scrollHeight;
  }

  function createAssistantMessage() {
    const area = document.getElementById('chat-area');
    if (!area) return null;
    const div = document.createElement('div');
    div.className = 'message assistant-message';
    const span = document.createElement('span');
    span.className = 'assistant-text';
    div.appendChild(span);
    area.appendChild(div);
    area.scrollTop = area.scrollHeight;
    return span;
  }

  function connectAndSend(payload) {
    // Close existing socket if any
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.close();
    }

    socket = new WebSocket(WS_URL);

    socket.addEventListener('open', () => {
      // send initial payload
      socket.send(JSON.stringify(payload));
    });

    socket.addEventListener('message', (ev) => {
      try {
        const data = JSON.parse(ev.data);
        handleServerMessage(data);
      } catch (e) {
        console.error('Invalid WS message', e, ev.data);
      }
    });

    socket.addEventListener('close', (ev) => {
      showTyping(false);
    });

    socket.addEventListener('error', (ev) => {
      console.error('WebSocket error', ev);
      showTyping(false);
    });
  }

  function handleServerMessage(msg) {
    const t = msg.type;
    if (t === 'typing') {
      showTyping(msg.status === true);
    } else if (t === 'token') {
      if (!assistantMessageEl) assistantMessageEl = createAssistantMessage();
      // Append token text (may include trailing space/newline)
      assistantMessageEl.textContent += msg.text;
      assistantMessageEl.parentElement.scrollIntoView({ behavior: 'smooth', block: 'end' });
    } else if (t === 'chunk') {
      // backward compatibility: whole chunk
      if (!assistantMessageEl) assistantMessageEl = createAssistantMessage();
      assistantMessageEl.textContent += msg.text;
      assistantMessageEl.parentElement.scrollIntoView({ behavior: 'smooth', block: 'end' });
    } else if (t === 'done') {
      showTyping(false);
      // Optionally display sources
      if (msg.sources && msg.sources.length) {
        const area = document.getElementById('chat-area');
        const div = document.createElement('div');
        div.className = 'message sources-message';
        div.textContent = 'Sources: ' + JSON.stringify(msg.sources);
        area.appendChild(div);
      }
      assistantMessageEl = null;
    } else if (t === 'error') {
      showTyping(false);
      const area = document.getElementById('chat-area');
      const div = document.createElement('div');
      div.className = 'message error-message';
      div.textContent = 'Error: ' + msg.error;
      area.appendChild(div);
      assistantMessageEl = null;
    }
  }

  function sendMessage() {
    const input = document.getElementById('chat-input');
    if (!input) return;
    const text = input.value.trim();
    if (!text) return;

    // Reset UI state for assistant message
    assistantMessageEl = null;

    appendUserMessage(text);

    const payload = {
      user_id: window.LARAVEL_USER_ID || 'anonymous',
      message: text,
      collection: window.DEFAULT_COLLECTION || 'manuel_parc_auto',
      max_turns: 1
    };

    connectAndSend(payload);

    input.value = '';
  }

  // Wire UI
  document.addEventListener('DOMContentLoaded', () => {
    const btn = document.getElementById('chat-send');
    const input = document.getElementById('chat-input');
    if (btn) btn.addEventListener('click', sendMessage);
    if (input) input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });

    // Hide typing indicator initially
    showTyping(false);
  });

})();

