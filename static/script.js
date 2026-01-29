// submitQuestion and sendAnswer removed: UI no longer exposes direct question/answer controls

function eliminateCard(id) {
  document.getElementById('card' + id).classList.add('eliminated');
  fetch('/eliminate_card', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ card_id: id }),
  });
}
// submitNote removed: moderator no longer saves notes via the UI

// --- Chat helpers
function sendChat(role) {
  const input = document.getElementById('chat-input');
  if (!input) return;
  const text = input.value.trim();
  if (!text) return;
  const payload = { game_id: 'default', role: role, text: text, participant_id: window.participantId };
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

// --- Socket.IO client setup
// Only open a socket when this page is the top-level window (not inside an iframe).
// Moderator is a top-level page and will therefore open a socket and can both observe and send chat.
// Player pages may be embedded in the moderator as iframes; when embedded we avoid opening an extra socket
// to reduce duplicate connections and noise.
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

// If this page is top-level (not inside an iframe), initialize socket.io and join the game room.
if (window.top === window.self) {
  try {
    window.socket = io();
    socket.emit('join', { game_id: 'default', participant_id: window.participantId });

    // Fetch recent transcript for this game and display it
    fetch('/transcript?game_id=default&limit=200')
      .then(r => r.json())
      .then(arr => {
        arr.forEach(entry => appendTranscriptEntry(entry));
      })
      .catch(err => console.error('transcript fetch failed', err));

    socket.on('connect', () => appendTranscriptEntry({role: 'system', action: 'connected', text: 'socket connected'}));
    socket.on('connect_error', (err) => appendTranscriptEntry({role: 'system', action: 'connect_error', text: String(err)}));

    // question/answer/note socket events removed (UI no longer uses them)
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
    console.error('Socket initialization failed', e);
  }
} else {
  // Embedded in an iframe: don't open a socket, but load a one-time transcript snapshot so the iframe shows history.
  fetch('/transcript?game_id=default&limit=200')
    .then(r => r.json())
    .then(arr => {
      arr.forEach(entry => appendTranscriptEntry(entry));
    })
    .catch(err => console.error('transcript fetch failed', err));
}
