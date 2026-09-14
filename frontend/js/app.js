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
let conversationHistory = [];

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

if (clearChatBtn) {
  clearChatBtn.addEventListener('click', () => {
    if (confirm('Clear chat conversation?')) {
      conversationHistory = [];
      chatMessages.innerHTML = '';
      if (welcomeCard) welcomeCard.style.display = 'block';
    }
  });
}

const syncGmailBtn = document.getElementById('syncGmailBtn');
const syncGmailIcon = document.getElementById('syncGmailIcon');

if (syncGmailBtn) {
  syncGmailBtn.addEventListener('click', async () => {
    const token = getStoredToken();
    if (!token) {
      openAuthModal();
      return;
    }

    syncGmailIcon.classList.add('animate-spin', 'text-indigo-400');
    try {
      const res = await fetch('/gmail/sync', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Device-Token': token
        }
      });
      if (!res.ok) {
        const errText = await res.text();
        alert(`⚠️ Sync failed (HTTP ${res.status}): ${errText.slice(0, 150)}`);
        return;
      }
      const data = await res.json();
      if (data.success) {
        alert(`📬 Gmail Sync: ${data.message}`);
      } else {
        alert(`⚠️ ${data.message}`);
      }
    } catch (err) {
      alert(`❌ Sync error: ${err.message}`);
    } finally {
      syncGmailIcon.classList.remove('animate-spin', 'text-indigo-400');
    }
  });
}

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
      <!-- Explainability / Knowledge Graph Section -->
      <div class="explainability-container hidden mb-3">
        <details class="explainability-box p-3 text-xs md:text-sm rounded-xl bg-slate-900/90 border border-emerald-500/30 shadow-inner" open>
          <summary class="flex items-center gap-2 font-medium text-emerald-400 cursor-pointer select-none">
            <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            <span class="explainability-badge text-emerald-300 font-semibold">⚡ Version 2.0 (Knowledge Graph)</span>
            <span class="explainability-summary text-slate-400 text-[11px] ml-auto">Graph & Context Evidence</span>
          </summary>
          <div class="explainability-content mt-2.5 pt-2.5 border-t border-slate-800/80 text-slate-300 font-sans space-y-2"></div>
        </details>
      </div>

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
    explainabilityContainer: wrapper.querySelector('.explainability-container'),
    explainabilityBox: wrapper.querySelector('.explainability-box'),
    explainabilityBadge: wrapper.querySelector('.explainability-badge'),
    explainabilityContent: wrapper.querySelector('.explainability-content'),
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

  const historyPayload = conversationHistory.slice(-12);
  conversationHistory.push({ role: 'user', content: text });

  try {
    const response = await fetch('/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Device-Token': token
      },
      body: JSON.stringify({
        message: text,
        stream: true,
        history: historyPayload
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

          // 0. Explainability & Knowledge Graph Evidence
          if (payload.type === 'explainability' && payload.data) {
            const exp = payload.data;
            node.explainabilityContainer.classList.remove('hidden');

            const isV2 = exp.version === 'v2';
            node.explainabilityBadge.textContent = isV2 ? '⚡ Version 2.0 (Knowledge Graph Active)' : '🔍 Version 1.0 (Pure Vector RAG)';
            node.explainabilityBadge.className = isV2 ? 'text-emerald-300 font-semibold' : 'text-blue-300 font-semibold';

            let html = `
              <div class="flex flex-wrap gap-2 items-center mb-2 pb-2 border-b border-slate-800 text-[11px]">
                <span class="px-2 py-0.5 rounded bg-slate-800 text-slate-300">Model: <strong>${escapeHtml(exp.model || '')}</strong></span>
                <span class="px-2 py-0.5 rounded bg-slate-800 text-slate-300">Intent: <strong>${escapeHtml(exp.intent || '')}</strong></span>
                <span class="px-2 py-0.5 rounded ${isV2 ? 'bg-emerald-950/80 text-emerald-300 border border-emerald-800/40' : 'bg-blue-950/80 text-blue-300 border border-blue-800/40'}">
                  ${isV2 ? 'Bitemporal Knowledge Graph Engine' : 'Vector RAG Mode'}
                </span>
              </div>
            `;

            if (exp.matched_entities && exp.matched_entities.length > 0) {
              html += `
                <div class="mb-2">
                  <div class="text-slate-400 font-medium mb-1">👤 Identified Entities:</div>
                  <div class="flex flex-wrap gap-1.5">
                    ${exp.matched_entities.map(e => `<span class="px-2 py-0.5 rounded bg-indigo-950/70 border border-indigo-800/50 text-indigo-300 font-mono text-[11px]">${escapeHtml(e)}</span>`).join('')}
                  </div>
                </div>
              `;
            }

            if (exp.relational_path && exp.relational_path.length > 0) {
              html += `
                <div class="mb-2 p-2.5 rounded-lg bg-emerald-950/30 border border-emerald-800/40">
                  <div class="text-emerald-400 font-semibold mb-1 flex items-center gap-1.5">
                    <span>🔗 Verified Relational Graph Traversal (Ground Truth):</span>
                  </div>
                  <div class="font-mono text-emerald-200 text-xs space-y-1">
                    ${exp.relational_path.map(p => `<div>• ${escapeHtml(p)}</div>`).join('')}
                  </div>
                </div>
              `;
            }

            if (exp.graph_facts && exp.graph_facts.length > 0) {
              html += `
                <div class="mb-2 p-2.5 rounded-lg bg-slate-800/60 border border-slate-700/50">
                  <div class="text-slate-300 font-semibold mb-1">📋 Active Knowledge Graph Facts:</div>
                  <div class="space-y-1 font-mono text-xs text-slate-200">
                    ${exp.graph_facts.map(f => `<div>• <strong>${escapeHtml(f.subject)}</strong> —[${escapeHtml(f.predicate)}]➔ <strong>${escapeHtml(f.object)}</strong> <span class="text-slate-400 text-[10px]">(since ${escapeHtml(f.valid_from || 'active')})</span></div>`).join('')}
                  </div>
                </div>
              `;
            } else if (isV2 && (!exp.matched_entities || exp.matched_entities.length === 0)) {
              html += `
                <div class="text-slate-400 italic text-xs mb-1">
                  ℹ️ General query — no specific entity matched in Knowledge Graph.
                </div>
              `;
            }

            if (exp.system_prompt_preview) {
              html += `
                <details class="mt-2 text-[11px]">
                  <summary class="text-slate-400 hover:text-slate-200 cursor-pointer select-none">View Exact Context Injected into Model</summary>
                  <pre class="mt-1.5 p-2 rounded bg-slate-950/80 border border-slate-800 text-slate-400 font-mono text-[10px] whitespace-pre-wrap overflow-x-auto max-h-48 overflow-y-auto">${escapeHtml(exp.system_prompt_preview)}</pre>
                </details>
              `;
            }

            node.explainabilityContent.innerHTML = html;
            scrollToBottom();
          }

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

            if (answerAccumulator) {
              conversationHistory.push({ role: 'assistant', content: answerAccumulator });
              if (conversationHistory.length > 20) conversationHistory = conversationHistory.slice(-20);
            }

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

// Communication link handler (tel:, sms:, wa.me)
chatMessages.addEventListener('click', (e) => {
  const link = e.target.closest('a');
  if (!link) return;

  const href = link.getAttribute('href') || '';
  if (href.startsWith('tel:')) {
    if (navigator.vibrate) navigator.vibrate(30);
  } else if (href.startsWith('https://wa.me') || href.startsWith('http')) {
    link.setAttribute('target', '_blank');
    link.setAttribute('rel', 'noopener noreferrer');
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
