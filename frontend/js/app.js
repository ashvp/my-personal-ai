// Personal AI Assistant - Core Client Application

// Elements
const chatMessages = document.getElementById('chatMessages');
const messageForm = document.getElementById('messageForm');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const stopBtn = document.getElementById('stopBtn');
const authModal = document.getElementById('authModal');
const tokenInput = document.getElementById('tokenInput');
const saveTokenBtn = document.getElementById('saveTokenBtn');
const authStatusBadge = document.getElementById('authStatusBadge');
const tokenSettingsBtn = document.getElementById('tokenSettingsBtn');
const clearChatBtn = document.getElementById('clearChatBtn');
const welcomeCard = document.getElementById('welcomeCard');

// State
let currentAbortController = null;
let isGenerating = false;

// 1. Authentication & Token Handling
function getStoredToken() {
  return localStorage.getItem('assistant_device_token') || '';
}

function setStoredToken(token) {
  if (token) {
    localStorage.setItem('assistant_device_token', token.trim());
    updateAuthUI(true);
  } else {
    localStorage.removeItem('assistant_device_token');
    updateAuthUI(false);
  }
}

function updateAuthUI(isAuthenticated) {
  if (isAuthenticated) {
    authStatusBadge.className = 'flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-950/80 text-emerald-400 border border-emerald-800/50';
    authStatusBadge.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span> Paired';
  } else {
    authStatusBadge.className = 'flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-950/80 text-amber-400 border border-amber-800/50 cursor-pointer';
    authStatusBadge.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-amber-400"></span> Not Paired';
  }
}

function checkInitialAuth() {
  // Check if token was provided in URL query string (e.g. from QR scan)
  const urlParams = new URLSearchParams(window.location.search);
  const tokenFromUrl = urlParams.get('token');
  if (tokenFromUrl) {
    setStoredToken(tokenFromUrl);
    // Clean up URL without reloading
    window.history.replaceState({}, document.title, window.location.pathname);
  }

  const token = getStoredToken();
  if (!token) {
    openAuthModal();
  } else {
    updateAuthUI(true);
  }
}

function openAuthModal() {
  tokenInput.value = getStoredToken();
  authModal.classList.remove('hidden');
}

function closeAuthModal() {
  authModal.classList.add('hidden');
}

saveTokenBtn.addEventListener('click', () => {
  const token = tokenInput.value.trim();
  if (token) {
    setStoredToken(token);
    closeAuthModal();
  } else {
    alert('Please enter a valid device token.');
  }
});

tokenSettingsBtn.addEventListener('click', openAuthModal);
authStatusBadge.addEventListener('click', openAuthModal);

// 2. Chat UI Helpers
function autoResizeInput() {
  messageInput.style.height = 'auto';
  messageInput.style.height = Math.min(messageInput.scrollHeight, 160) + 'px';
}

messageInput.addEventListener('input', autoResizeInput);

// Handle Enter to send (Shift+Enter for newline)
messageInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    if (!isGenerating && messageInput.value.trim()) {
      messageForm.dispatchEvent(new Event('submit'));
    }
  }
});

function scrollToBottom() {
  window.scrollTo({
    top: document.body.scrollHeight,
    behavior: 'smooth'
  });
}

function appendUserMessage(text) {
  if (welcomeCard) welcomeCard.style.display = 'none';

  const wrapper = document.createElement('div');
  wrapper.className = 'flex justify-end mb-6';
  wrapper.innerHTML = `
    <div class="max-w-[85%] md:max-w-[70%] bg-indigo-600/90 text-white rounded-2xl rounded-tr-sm px-4 py-3 shadow-lg shadow-indigo-950/20 text-sm md:text-base whitespace-pre-wrap leading-relaxed">
      ${escapeHtml(text)}
    </div>
  `;
  chatMessages.appendChild(wrapper);
  scrollToBottom();
}

function createAssistantMessageNode() {
  if (welcomeCard) welcomeCard.style.display = 'none';

  const wrapper = document.createElement('div');
  wrapper.className = 'flex gap-3 mb-6 items-start';

  wrapper.innerHTML = `
    <div class="w-8 h-8 rounded-full bg-gradient-to-tr from-indigo-500 to-purple-600 flex items-center justify-center shrink-0 shadow-md shadow-indigo-900/30 text-white text-xs font-bold">
      Q
    </div>
    <div class="flex-1 overflow-hidden">
      <!-- Thinking Section (Collapsed by default once answered) -->
      <div class="thinking-container hidden mb-3">
        <details class="thinking-box thinking-active p-3 text-xs md:text-sm" open>
          <summary class="flex items-center gap-2 font-medium text-indigo-300">
            <svg class="w-4 h-4 animate-spin thinking-spinner text-indigo-400" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <circle cx="12" cy="12" r="10" stroke-width="3" stroke-dasharray="32" stroke-linecap="round"/>
            </svg>
            <span class="thinking-title">Thinking process</span>
            <span class="thinking-timer text-indigo-400/70 text-[11px] ml-auto">0s</span>
          </summary>
          <div class="thinking-content mt-2.5 pt-2.5 border-t border-indigo-900/40 text-slate-300 font-mono text-xs whitespace-pre-wrap leading-relaxed max-h-60 overflow-y-auto"></div>
        </details>
      </div>

      <!-- Answer Section -->
      <div class="markdown-body text-sm md:text-base text-slate-100 min-h-[1.5rem] typing-cursor"></div>

      <!-- Message Footer -->
      <div class="flex items-center gap-3 mt-2 text-[11px] text-slate-500 font-medium">
        <span class="footer-meta"></span>
        <button class="copy-btn hover:text-slate-300 transition-colors hidden flex items-center gap-1">
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
          </svg>
          <span>Copy</span>
        </button>
      </div>
    </div>
  `;

  chatMessages.appendChild(wrapper);
  scrollToBottom();

  return {
    wrapper,
    thinkingContainer: wrapper.querySelector('.thinking-container'),
    thinkingDetails: wrapper.querySelector('.thinking-box'),
    thinkingSpinner: wrapper.querySelector('.thinking-spinner'),
    thinkingTitle: wrapper.querySelector('.thinking-title'),
    thinkingTimer: wrapper.querySelector('.thinking-timer'),
    thinkingContent: wrapper.querySelector('.thinking-content'),
    answerBody: wrapper.querySelector('.markdown-body'),
    footerMeta: wrapper.querySelector('.footer-meta'),
    copyBtn: wrapper.querySelector('.copy-btn')
  };
}

// 3. Streaming Chat Request Handler
messageForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const text = messageInput.value.trim();
  if (!text || isGenerating) return;

  const token = getStoredToken();
  if (!token) {
    openAuthModal();
    return;
  }

  // Reset input
  messageInput.value = '';
  autoResizeInput();

  // Show user bubble
  appendUserMessage(text);

  // Prepare UI for generation
  isGenerating = true;
  sendBtn.classList.add('hidden');
  stopBtn.classList.remove('hidden');

  currentAbortController = new AbortController();

  const node = createAssistantMessageNode();
  let thinkingAccumulator = '';
  let answerAccumulator = '';
  const startTime = Date.now();

  const timerInterval = setInterval(() => {
    const elapsedSec = ((Date.now() - startTime) / 1000).toFixed(1);
    node.thinkingTimer.textContent = `${elapsedSec}s`;
  }, 200);

  try {
    const response = await fetch('/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Device-Token': token
      },
      body: JSON.stringify({
        message: text,
        stream: true
      }),
      signal: currentAbortController.signal
    });

    if (response.status === 401) {
      clearInterval(timerInterval);
      node.answerBody.classList.remove('typing-cursor');
      node.answerBody.innerHTML = '<span class="text-rose-400">❌ Unauthorized device. Please check your device token.</span>';
      openAuthModal();
      return;
    }

    if (!response.ok) {
      clearInterval(timerInterval);
      const errText = await response.text();
      node.answerBody.classList.remove('typing-cursor');
      node.answerBody.innerHTML = `<span class="text-rose-400">❌ Error: ${escapeHtml(errText)}</span>`;
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split('\n\n');
      buffer = events.pop(); // Keep partial trailing line in buffer

      for (const event of events) {
        const line = event.trim();
        if (!line.startsWith('data:')) continue;

        const jsonStr = line.replace(/^data:\s*/, '');
        if (!jsonStr) continue;

        try {
          const payload = JSON.parse(jsonStr);

          // 1. Thinking Token
          if (payload.type === 'thinking' && payload.token) {
            node.thinkingContainer.classList.remove('hidden');
            thinkingAccumulator += payload.token;
            node.thinkingContent.textContent = thinkingAccumulator;
            scrollToBottom();
          }

          // 2. Answer Token
          if (payload.type === 'answer' && payload.token) {
            // Once answer starts, collapse the thinking box
            if (!node.thinkingContainer.classList.contains('hidden') && node.thinkingDetails.hasAttribute('open')) {
              node.thinkingDetails.removeAttribute('open');
              node.thinkingDetails.classList.remove('thinking-active');
              node.thinkingSpinner.classList.add('hidden');
              node.thinkingTitle.textContent = `Thought process (${((Date.now() - startTime) / 1000).toFixed(1)}s)`;
            }

            answerAccumulator += payload.token;
            node.answerBody.innerHTML = marked.parse(answerAccumulator);
            scrollToBottom();
          }

          // 3. Finished Generation
          if (payload.done) {
            clearInterval(timerInterval);
            node.answerBody.classList.remove('typing-cursor');
            node.thinkingSpinner.classList.add('hidden');
            node.thinkingDetails.classList.remove('thinking-active');

            const totalSec = payload.total_duration_seconds || ((Date.now() - startTime) / 1000).toFixed(1);
            node.footerMeta.textContent = `${totalSec}s • ${payload.model || 'qwen'}`;

            // Setup copy button
            node.copyBtn.classList.remove('hidden');
            node.copyBtn.addEventListener('click', () => {
              navigator.clipboard.writeText(answerAccumulator);
              node.copyBtn.innerHTML = `
                <svg class="w-3.5 h-3.5 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="20 6 9 17 4 12"></polyline>
                </svg>
                <span class="text-emerald-400">Copied!</span>
              `;
              setTimeout(() => {
                node.copyBtn.innerHTML = `
                  <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                  </svg>
                  <span>Copy</span>
                `;
              }, 2000);
            });
          }
        } catch (parseErr) {
          console.warn('Could not parse SSE payload:', parseErr);
        }
      }
    }
  } catch (err) {
    clearInterval(timerInterval);
    node.answerBody.classList.remove('typing-cursor');
    if (err.name === 'AbortError') {
      node.footerMeta.textContent += ' (Stopped)';
    } else {
      node.answerBody.innerHTML += `<div class="text-rose-400 text-xs mt-2">Network error: ${escapeHtml(err.message)}</div>`;
    }
  } finally {
    clearInterval(timerInterval);
    isGenerating = false;
    currentAbortController = null;
    sendBtn.classList.remove('hidden');
    stopBtn.classList.add('hidden');
    messageInput.focus();
  }
});

// Stop generation
stopBtn.addEventListener('click', () => {
  if (currentAbortController) {
    currentAbortController.abort();
  }
});

// Clear chat
clearChatBtn.addEventListener('click', () => {
  chatMessages.innerHTML = '';
  if (welcomeCard) {
    chatMessages.appendChild(welcomeCard);
    welcomeCard.style.display = 'block';
  }
});

// Prompt suggestions click handler
window.fillPrompt = function(promptText) {
  messageInput.value = promptText;
  autoResizeInput();
  messageForm.dispatchEvent(new Event('submit'));
};

function escapeHtml(str) {
  return str.replace(/[&<>'"]/g, 
    tag => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      "'": '&#39;',
      '"': '&quot;'
    }[tag] || tag)
  );
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
  checkInitialAuth();
  autoResizeInput();
});
