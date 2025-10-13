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

// --- Socket.IO client setup (will silently fail if socket.io library not loaded)
try {
  const socket = io();

  // Append an event to any transcript containers
  function appendTranscriptEntry(obj) {
    const containers = document.querySelectorAll('.transcript');
    containers.forEach(c => {
      const el = document.createElement('div');
      el.className = 'transcript-entry';
      el.textContent = `[${obj.role}] ${obj.action}` + (obj.question ? `: ${obj.question}` : '') + (obj.answer ? `: ${obj.answer}` : '') + (obj.note ? `: ${obj.note}` : '') + (obj.card ? `: card ${obj.card}` : '');
      c.appendChild(el);
      c.scrollTop = c.scrollHeight;
    });
  }

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
} catch (e) {
  // socket.io script not present; ignore
}
