// Session audio capture: each browser records its local microphone only.
// Starts/stops on Socket.IO recording_start / recording_stop (no upload yet).
//
// Holds the last blob + sync timestamps for a later feature/audio-upload branch.

(function () {
  function pickMimeType() {
    const candidates = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/ogg;codecs=opus",
      "audio/mp4",
    ];
    if (typeof MediaRecorder === "undefined") return "";
    for (const type of candidates) {
      if (MediaRecorder.isTypeSupported(type)) return type;
    }
    return "";
  }

  /**
   * Clone local audio tracks so mute (track.enabled=false on the voice stream)
   * does not silence the research recording, and so stopping the recorder does
   * not tear down WebRTC tracks.
   */
  function cloneAudioStream(source) {
    if (!source) return null;
    const clones = source.getAudioTracks().map((track) => {
      const c = track.clone();
      c.enabled = true;
      return c;
    });
    if (!clones.length) return null;
    return new MediaStream(clones);
  }

  function stopStreamTracks(stream) {
    if (!stream) return;
    stream.getTracks().forEach((t) => {
      try {
        t.stop();
      } catch (_) {}
    });
  }

  /**
   * @param {object} opts
   * @param {object} opts.socket - Socket.IO client
   * @param {string} opts.gameId
   * @param {string} opts.role
   * @param {string} [opts.participantId]
   * @param {function(): MediaStream|null} [opts.getLocalStream]
   * @param {function(): Promise<MediaStream|null>} [opts.ensureLocalStream]
   * @param {HTMLElement|null} [opts.statusEl] - recording indicator
   * @param {function(object): void} [opts.onComplete] - after stop with payload
   */
  function createSessionRecorder(opts) {
    const socket = opts.socket;
    const gameId = opts.gameId;
    const role = opts.role || "unknown";
    const participantId = opts.participantId || null;
    const getLocalStream = opts.getLocalStream || (() => null);
    const ensureLocalStream =
      opts.ensureLocalStream ||
      (async () => (typeof getLocalStream === "function" ? getLocalStream() : null));
    const statusEl = opts.statusEl || null;
    const onComplete = opts.onComplete || null;

    let mediaRecorder = null;
    let recStream = null;
    let chunks = [];
    let active = false;
    let session = null; // metadata for current/last take
    let lastResult = null;

    function setIndicator(text, isRecording) {
      if (!statusEl) return;
      statusEl.textContent = text;
      statusEl.style.color = isRecording ? "#b71c1c" : "#555";
      statusEl.style.fontWeight = isRecording ? "600" : "normal";
    }

    function resetIndicator() {
      setIndicator("", false);
    }

    function isRecording() {
      return active && mediaRecorder && mediaRecorder.state === "recording";
    }

    function getLastResult() {
      return lastResult;
    }

    /** Debug helper: download last take as a file in the browser. */
    function downloadLast() {
      if (!lastResult || !lastResult.blob) {
        console.warn("[Recording] Nothing to download");
        return false;
      }
      const ext = (lastResult.mimeType || "").includes("mp4")
        ? "mp4"
        : (lastResult.mimeType || "").includes("ogg")
          ? "ogg"
          : "webm";
      const name = [
        lastResult.recording_id || "rec",
        role,
        participantId || "anon",
      ].join("_") + "." + ext;
      const url = URL.createObjectURL(lastResult.blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
      return true;
    }

    async function startFromEvent(data) {
      const clientReceivedTs = Date.now();

      if (!data || data.game_id !== gameId) {
        console.log("[Recording] ignore start for other game", data && data.game_id);
        return { ok: false, reason: "wrong_game" };
      }

      if (isRecording()) {
        console.warn("[Recording] already active; ignoring duplicate start");
        return { ok: false, reason: "already_recording" };
      }

      if (typeof MediaRecorder === "undefined") {
        console.error("[Recording] MediaRecorder not supported in this browser");
        setIndicator("recording unsupported", false);
        return { ok: false, reason: "unsupported" };
      }

      let local = typeof getLocalStream === "function" ? getLocalStream() : null;
      if (!local || !local.getAudioTracks().length) {
        try {
          local = await ensureLocalStream();
        } catch (err) {
          console.error("[Recording] could not get microphone stream", err);
          setIndicator("mic required for recording", false);
          return { ok: false, reason: "no_mic" };
        }
      }
      if (!local || !local.getAudioTracks().length) {
        console.error("[Recording] no local audio tracks");
        setIndicator("mic required for recording", false);
        return { ok: false, reason: "no_mic" };
      }

      recStream = cloneAudioStream(local);
      if (!recStream) {
        setIndicator("mic required for recording", false);
        return { ok: false, reason: "no_mic" };
      }

      const mimeType = pickMimeType();
      chunks = [];
      try {
        mediaRecorder = mimeType
          ? new MediaRecorder(recStream, { mimeType })
          : new MediaRecorder(recStream);
      } catch (err) {
        console.error("[Recording] MediaRecorder construct failed", err);
        stopStreamTracks(recStream);
        recStream = null;
        setIndicator("recorder error", false);
        return { ok: false, reason: "construct_failed" };
      }

      session = {
        game_id: gameId,
        role,
        participant_id: participantId,
        recording_id: data.recording_id,
        server_ts: data.server_ts,
        client_received_ts: clientReceivedTs,
        client_recorder_start_ts: null,
        client_recorder_stop_ts: null,
        mimeType: mediaRecorder.mimeType || mimeType || "",
      };

      mediaRecorder.ondataavailable = (ev) => {
        if (ev.data && ev.data.size > 0) chunks.push(ev.data);
      };

      mediaRecorder.onerror = (ev) => {
        console.error("[Recording] MediaRecorder error", ev.error || ev);
      };

      try {
        // timeslice keeps data flowing; also helps some browsers flush chunks
        mediaRecorder.start(1000);
        session.client_recorder_start_ts = Date.now();
        active = true;
        setIndicator("⏺ recording…", true);
        console.log("[Recording] started", {
          recording_id: session.recording_id,
          mimeType: session.mimeType,
          server_ts: session.server_ts,
          client_received_ts: session.client_received_ts,
          client_recorder_start_ts: session.client_recorder_start_ts,
        });
        return { ok: true, session };
      } catch (err) {
        console.error("[Recording] start() failed", err);
        stopStreamTracks(recStream);
        recStream = null;
        mediaRecorder = null;
        session = null;
        active = false;
        setIndicator("recorder error", false);
        return { ok: false, reason: "start_failed" };
      }
    }

    function stopFromEvent(data) {
      return new Promise((resolve) => {
        if (data && data.game_id && data.game_id !== gameId) {
          resolve({ ok: false, reason: "wrong_game" });
          return;
        }

        if (!mediaRecorder || !active) {
          console.log("[Recording] stop ignored (not recording)");
          resolve({ ok: false, reason: "not_recording" });
          return;
        }

        const mr = mediaRecorder;
        const stopTs = Date.now();

        mr.onstop = () => {
          const mime =
            (session && session.mimeType) || mr.mimeType || "audio/webm";
          const blob = new Blob(chunks, { type: mime });
          stopStreamTracks(recStream);
          recStream = null;
          chunks = [];
          mediaRecorder = null;
          active = false;

          if (session) {
            session.client_recorder_stop_ts = stopTs;
            if (data && data.server_ts) {
              session.server_stop_ts = data.server_ts;
            }
          }

          lastResult = {
            ...(session || {}),
            blob,
            size: blob.size,
            mimeType: mime,
          };
          session = null;

          setIndicator("recording saved (local)", false);
          console.log("[Recording] stopped", {
            recording_id: lastResult.recording_id,
            size: lastResult.size,
            mimeType: lastResult.mimeType,
            client_recorder_start_ts: lastResult.client_recorder_start_ts,
            client_recorder_stop_ts: lastResult.client_recorder_stop_ts,
            server_ts: lastResult.server_ts,
          });

          if (typeof onComplete === "function") {
            try {
              onComplete(lastResult);
            } catch (err) {
              console.error("[Recording] onComplete error", err);
            }
          }

          // Expose for manual debug / next upload branch
          window.__lastRecording = lastResult;
          resolve({ ok: true, result: lastResult });
        };

        try {
          if (mr.state === "recording" || mr.state === "paused") {
            mr.stop();
          } else {
            mr.onstop();
          }
        } catch (err) {
          console.error("[Recording] stop() failed", err);
          stopStreamTracks(recStream);
          recStream = null;
          mediaRecorder = null;
          active = false;
          session = null;
          setIndicator("recorder error", false);
          resolve({ ok: false, reason: "stop_failed" });
        }
      });
    }

    /**
     * After role swap / reload, pages miss live socket events. If the server
     * still has recording_active, start MediaRecorder for the current take.
     */
    async function resumeIfActive(maxAttempts) {
      const attempts = maxAttempts || 8;
      for (let i = 0; i < attempts; i++) {
        if (isRecording()) {
          return { ok: true, reason: "already_recording" };
        }
        try {
          const res = await fetch(
            `/game/status?game_id=${encodeURIComponent(gameId)}`,
            { credentials: "same-origin", cache: "no-store" }
          );
          if (!res.ok) {
            throw new Error(`status HTTP ${res.status}`);
          }
          const data = await res.json();
          if (data.recording_active && data.recording_id) {
            console.log("[Recording] resuming active take after load", {
              recording_id: data.recording_id,
              round_number: data.round_number,
              attempt: i + 1,
            });
            const result = await startFromEvent({
              game_id: gameId,
              recording_id: data.recording_id,
              server_ts:
                data.recording_server_ts || new Date().toISOString(),
              reason: "resume_after_load",
            });
            if (result && result.ok) return result;
          } else if (i === 0) {
            // Not active yet — may still be starting after role swap; retry.
          } else if (!data.recording_active) {
            return { ok: false, reason: "not_active" };
          }
        } catch (err) {
          console.warn("[Recording] resumeIfActive poll failed", err);
        }
        await new Promise((r) => setTimeout(r, 400));
      }
      return { ok: false, reason: "give_up" };
    }

    if (socket) {
      socket.on("recording_start", (data) => {
        startFromEvent(data).catch((err) =>
          console.error("[Recording] start handler failed", err)
        );
      });
      socket.on("recording_stop", (data) => {
        stopFromEvent(data).catch((err) =>
          console.error("[Recording] stop handler failed", err)
        );
      });
      socket.on("game_ended", (data) => {
        if (data && data.game_id && data.game_id !== gameId) return;
        if (isRecording()) {
          stopFromEvent(data || { game_id: gameId }).catch(() => {});
        }
      });
      // Prefer a clean stop before navigation on role swap (server also emits stop).
      socket.on("roles_swapped", (data) => {
        if (data && data.game_id && data.game_id !== gameId) return;
        if (isRecording()) {
          stopFromEvent(data).catch(() => {});
        }
      });
    }

    window.addEventListener("beforeunload", () => {
      if (mediaRecorder && active) {
        try {
          mediaRecorder.stop();
        } catch (_) {}
        stopStreamTracks(recStream);
      }
    });

    // Late join / post–role-swap pages reattach to an active take.
    resumeIfActive().catch((err) =>
      console.warn("[Recording] resumeIfActive failed", err)
    );

    return {
      startFromEvent,
      stopFromEvent,
      resumeIfActive,
      isRecording,
      getLastResult,
      downloadLast,
      resetIndicator,
    };
  }

  window.createSessionRecorder = createSessionRecorder;
})();
