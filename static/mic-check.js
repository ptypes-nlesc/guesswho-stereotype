// Microphone permission check (Teams-style pre-join, no voice mesh).
// Used on waiting room and moderator dashboard before game voice starts.

(function () {
  const MIC_READY_KEY = "gw_mic_ready";

  function isMicReady() {
    try {
      return localStorage.getItem(MIC_READY_KEY) === "1";
    } catch (_) {
      return false;
    }
  }

  function setMicReady(ready) {
    try {
      if (ready) {
        localStorage.setItem(MIC_READY_KEY, "1");
      } else {
        localStorage.removeItem(MIC_READY_KEY);
      }
    } catch (_) {
      // ignore localStorage errors
    }
  }

  function setStatus(statusEl, text, color) {
    if (!statusEl) return;
    statusEl.textContent = text;
    statusEl.style.color = color || "#555";
  }

  function stopStream(stream) {
    if (!stream) return;
    stream.getTracks().forEach((track) => {
      try {
        track.stop();
      } catch (_) {}
    });
  }

  async function runMicCheck(opts) {
    const buttonEl = opts.buttonEl;
    const statusEl = opts.statusEl;
    const levelEl = opts.levelEl;
    const messages = Object.assign(
      {
        idle: "Not checked yet",
        checking: "Requesting microphone access…",
        speak: "Speak now — the bar should move",
        ok: "Microphone ready",
        blocked: "Microphone blocked. Allow access in browser settings.",
        error: "Microphone check failed. Try again.",
      },
      opts.messages || {}
    );

    if (buttonEl) buttonEl.disabled = true;
    setStatus(statusEl, messages.checking, "#555");

    let stream = null;
    let audioContext = null;
    let rafId = null;

    function cleanup() {
      if (rafId) cancelAnimationFrame(rafId);
      if (audioContext) {
        try {
          audioContext.close();
        } catch (_) {}
      }
      stopStream(stream);
      stream = null;
      if (levelEl) levelEl.style.width = "0%";
    }

    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      setStatus(statusEl, messages.speak, "#1565c0");

      audioContext = new (window.AudioContext || window.webkitAudioContext)();
      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);

      const data = new Uint8Array(analyser.frequencyBinCount);
      let heardInput = false;
      const startedAt = Date.now();

      await new Promise((resolve) => {
        const tick = () => {
          analyser.getByteFrequencyData(data);
          let sum = 0;
          for (let i = 0; i < data.length; i++) sum += data[i];
          const level = sum / data.length;
          if (levelEl) {
            const pct = Math.min(100, Math.round((level / 80) * 100));
            levelEl.style.width = pct + "%";
          }
          if (level > 8) heardInput = true;

          if (Date.now() - startedAt >= 2500) {
            resolve();
            return;
          }
          rafId = requestAnimationFrame(tick);
        };
        rafId = requestAnimationFrame(tick);
      });

      cleanup();
      setMicReady(true);
      setStatus(
        statusEl,
        heardInput ? messages.ok : messages.ok,
        "#2e7d32"
      );
      if (buttonEl) {
        buttonEl.textContent = opts.successLabel || buttonEl.textContent;
        buttonEl.disabled = false;
      }
      return { ok: true, heardInput };
    } catch (err) {
      cleanup();
      setMicReady(false);
      const blocked =
        err && (err.name === "NotAllowedError" || err.name === "PermissionDeniedError");
      setStatus(statusEl, blocked ? messages.blocked : messages.error, "#c62828");
      if (buttonEl) buttonEl.disabled = false;
      return { ok: false, error: err };
    }
  }

  function bindMicCheckButton(opts) {
    if (!opts || !opts.buttonEl) return;
    if (opts.buttonEl.dataset.micCheckBound !== "1") {
      opts.buttonEl.dataset.micCheckBound = "1";
      opts.buttonEl.addEventListener("click", () => runMicCheck(opts));
    }
    if (opts.statusEl && isMicReady()) {
      setStatus(
        opts.statusEl,
        (opts.messages && opts.messages.ok) || "Microphone ready",
        "#2e7d32"
      );
    }
  }

  window.MicCheck = {
    isMicReady,
    setMicReady,
    runMicCheck,
    bindMicCheckButton,
  };
})();