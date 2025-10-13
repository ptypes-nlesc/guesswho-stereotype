function submitQuestion() {
  const q = document.getElementById('question').value;
  fetch('/submit_question', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question: q }),
  });
}

function sendAnswer(ans) {
  fetch('/submit_answer', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ answer: ans }),
  });
}

function eliminateCard(id) {
  document.getElementById('card' + id).classList.add('eliminated');
  fetch('/eliminate_card', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ card_id: id }),
  });
}
function submitNote() {
  const note = document.getElementById('note').value;
  fetch('/submit_note', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ note: note }),
  }).then(() => {
    document.getElementById('note').value = '';
  });
}

// --- Chat helpers
function sendChat(role) {
  const input = document.getElementById('chat-input');
  if (!input) return;
  const text = input.value.trim();
  if (!text) return;
  const payload = { game_id: 'default', role: role, text: text };
  // Prefer socket if available
  try {
    if (typeof socket !== 'undefined' && socket.connected) {
      socket.emit('chat', payload);
    } else {
      // fallback HTTP POST
      fetch('/submit_chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
    }
  } catch (e) {
    // ignore
  }
  input.value = '';
}

// --- Socket.IO client setup (will silently fail if socket.io library not loaded)
try {
  // make socket global for other functions to use
  window.socket = io();

  // join default game room
  socket.emit('join', { game_id: 'default' });

  // Fetch recent transcript for this game and display it
  fetch('/transcript?game_id=default&limit=200')
    .then(r => r.json())
    .then(arr => {
      arr.forEach(entry => appendTranscriptEntry(entry));
    })
    .catch(err => console.error('transcript fetch failed', err));

  // Append an event to any transcript containers
  function appendTranscriptEntry(obj) {
    const containers = document.querySelectorAll('.transcript');
    containers.forEach(c => {
      const el = document.createElement('div');
      el.className = 'transcript-entry';
      // Prefer text/message, fallback to note/question/answer
      const text = obj.text || obj.message || obj.note || obj.question || obj.answer || '';
      el.textContent = `[${obj.role}] ${obj.action}` + (obj.card ? `: card ${obj.card}` : '') + (text ? `: ${text}` : '');
      c.appendChild(el);
      c.scrollTop = c.scrollHeight;
    });
  }

  socket.on('connect', () => appendTranscriptEntry({role: 'system', action: 'connected', text: 'socket connected'}));
  socket.on('connect_error', (err) => appendTranscriptEntry({role: 'system', action: 'connect_error', text: String(err)}));

  socket.on('question', (data) => appendTranscriptEntry(data));
  socket.on('answer', (data) => appendTranscriptEntry(data));
  socket.on('note', (data) => appendTranscriptEntry(data));
  socket.on('eliminate', (data) => {
    appendTranscriptEntry(data);
    // apply elimination visually if present
    if (data.card) {
      const el = document.getElementById('card' + data.card);
      if (el) el.classList.add('eliminated');
    }
  });
  socket.on('chat', (data) => { console.log('socket chat received', data); appendTranscriptEntry(data); });
} catch (e) {
  // socket.io script not present; ignore
}
