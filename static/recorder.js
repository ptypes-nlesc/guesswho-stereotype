// Session audio capture: each browser records its local microphone only.
// Starts/stops on Socket.IO recording_start / recording_stop, then uploads
// the stem to POST /audio/upload (option 1: soft gate + notifications).

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

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
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
   * @param {function(object): void} [opts.onComplete] - after stop (before/after upload)
   * @param {boolean} [opts.autoUpload=true]
   * @param {number} [opts.uploadRetries=3]
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
    const autoUpload = opts.autoUpload !== false;
    const uploadRetries = typeof opts.uploadRetries === "number" ? opts.uploadRetries : 3;

    let mediaRecorder = null;
    let recStream = null;
    let chunks = [];
    let active = false;
    let session = null; // metadata for current/last take
    let lastResult = null;
    let pendingWork = Promise.resolve();
    let uploadInFlight = null;
    // After role swap this page is about to navigate; ignore round-2 recording_start
    // so we do not block on a new take or keep chatting under the old role.
    let suppressNewTakes = false;

    function setIndicator(text, mode) {
      if (!statusEl) return;
      statusEl.textContent = text;
      // mode: recording | uploading | ok | error | muted
      let color = "#555";
      let weight = "normal";
      if (mode === "recording") {
        color = "#b71c1c";
        weight = "600";
      } else if (mode === "uploading") {
        color = "#e65100";
        weight = "600";
      } else if (mode === "ok") {
        color = "#2e7d32";
        weight = "600";
      } else if (mode === "error") {
        color = "#c62828";
        weight = "600";
      }
      statusEl.style.color = color;
      statusEl.style.fontWeight = weight;
    }

    function resetIndicator() {
      setIndicator("", "muted");
    }

    function isRecording() {
      return active && mediaRecorder && mediaRecorder.state === "recording";
    }

    function getLastResult() {
      return lastResult;
    }

    function isBusy() {
      return isRecording() || !!uploadInFlight;
    }

    /**
     * Call before leaving the page (role swap). Stops accepting new takes and
     * finalizes the current stem if still recording.
     */
    function prepareForNavigation() {
      suppressNewTakes = true;
      console.log("[Recording] prepareForNavigation — ignoring further starts");
      if (isRecording()) {
        stopFromEvent({ game_id: gameId, reason: "prepare_for_navigation" }).catch(
          (err) => console.warn("[Recording] stop on navigate failed", err)
        );
      }
    }

    /**
     * Wait until in-flight stop + upload work finishes.
     * Does NOT wait for "not recording" — after role swap the server may start
     * round 2 while this old page is still open; waiting for that would block
     * navigation (and chat would keep using the old role).
     */
    async function waitForIdle(timeoutMs) {
      const limit = typeof timeoutMs === "number" ? timeoutMs : 60000;
      const start = Date.now();
      try {
        await pendingWork;
      } catch (_) {
        /* individual steps log their own errors */
      }
      while (uploadInFlight && Date.now() - start < limit) {
        try {
          await uploadInFlight;
        } catch (_) {}
        try {
          await pendingWork;
        } catch (_) {}
        await sleep(50);
      }
      // One more drain in case stop just queued upload after pendingWork resolved.
      try {
        await pendingWork;
      } catch (_) {}
      if (uploadInFlight) {
        try {
          await uploadInFlight;
        } catch (_) {}
      }
      return {
        ok: !uploadInFlight,
        recording: isRecording(),
        uploading: !!uploadInFlight,
      };
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

    async function uploadResult(result, attemptBase) {
      if (!result || !result.blob) {
        return { ok: false, reason: "no_blob" };
      }
      if (
        result.client_recorder_start_ts == null ||
        result.client_recorder_stop_ts == null ||
        result.client_received_ts == null
      ) {
        setIndicator("upload blocked (missing timestamps)", "error");
        return { ok: false, reason: "missing_timestamps" };
      }

      const attempts = uploadRetries;
      let lastErr = null;

      for (let i = 0; i < attempts; i++) {
        if (i > 0) {
          await sleep(400 * Math.pow(2, i - 1));
        }
        setIndicator(
          i === 0 ? "↑ uploading…" : `↑ upload retry ${i + 1}/${attempts}…`,
          "uploading"
        );
        try {
          const form = new FormData();
          const ext = (result.mimeType || "").includes("ogg")
            ? "ogg"
            : (result.mimeType || "").includes("mp4")
              ? "m4a"
              : "webm";
          const filename = [
            result.recording_id || "rec",
            role,
            participantId || "moderator",
          ].join("_") + "." + ext;

          form.append(
            "file",
            result.blob,
            filename
          );
          form.append("game_id", result.game_id || gameId);
          form.append("recording_id", result.recording_id || "");
          form.append("role", role);
          if (participantId) {
            form.append("participant_id", participantId);
          }
          form.append("client_received_ts", String(result.client_received_ts));
          form.append(
            "client_recorder_start_ts",
            String(result.client_recorder_start_ts)
          );
          form.append(
            "client_recorder_stop_ts",
            String(result.client_recorder_stop_ts)
          );
          if (result.server_ts) {
            form.append("server_ts", result.server_ts);
          }
          if (result.server_stop_ts) {
            form.append("server_stop_ts", result.server_stop_ts);
          }
          if (result.mimeType) {
            form.append("mime_type", result.mimeType);
          }

          // Do NOT set keepalive: browsers cap keepalive bodies at ~64KB;
          // research stems are often 0.5–several MB and would fail silently.
          // Navigation is delayed via waitForIdle() instead.
          const res = await fetch("/audio/upload", {
            method: "POST",
            body: form,
            credentials: "same-origin",
          });
          let data = null;
          try {
            data = await res.json();
          } catch (_) {
            data = null;
          }
          if (!res.ok || !data || data.status !== "ok") {
            const msg =
              (data && data.message) || `HTTP ${res.status}`;
            throw new Error(msg);
          }

          lastResult = {
            ...result,
            uploaded: true,
            audio_path: data.audio_path,
            audio_event_id: data.audio_event_id,
            upload_byte_size: data.byte_size,
          };
          window.__lastRecording = lastResult;
          setIndicator("✓ uploaded", "ok");
          console.log("[Recording] uploaded", {
            recording_id: result.recording_id,
            audio_path: data.audio_path,
            byte_size: data.byte_size,
            attempt: (attemptBase || 0) + i + 1,
          });
          return { ok: true, data, result: lastResult };
        } catch (err) {
          lastErr = err;
          console.warn("[Recording] upload attempt failed", {
            attempt: i + 1,
            size: result.size || (result.blob && result.blob.size),
            recording_id: result.recording_id,
            error: err && err.message ? err.message : err,
          });
        }
      }

      const errText = lastErr && lastErr.message ? lastErr.message : "unknown error";
      setIndicator("⚠ upload failed — use downloadLast()", "error");
      console.error("[Recording] upload failed after retries", lastErr);
      if (lastResult) {
        lastResult.uploaded = false;
        lastResult.upload_error = String(errText);
      }
      return { ok: false, reason: "upload_failed", error: lastErr };
    }

    async function runUpload(result) {
      if (!autoUpload) {
        return { ok: false, reason: "auto_upload_disabled" };
      }
      uploadInFlight = uploadResult(result);
      try {
        return await uploadInFlight;
      } finally {
        uploadInFlight = null;
      }
    }

    async function startFromEvent(data) {
      const clientReceivedTs = Date.now();

      if (!data || data.game_id !== gameId) {
        console.log("[Recording] ignore start for other game", data && data.game_id);
        return { ok: false, reason: "wrong_game" };
      }

      if (suppressNewTakes) {
        console.log(
          "[Recording] ignore start — page is navigating away (role swap)"
        );
        return { ok: false, reason: "navigating_away" };
      }

      if (isRecording()) {
        console.warn("[Recording] already active; ignoring duplicate start");
        return { ok: false, reason: "already_recording" };
      }

      if (typeof MediaRecorder === "undefined") {
        console.error("[Recording] MediaRecorder not supported in this browser");
        setIndicator("recording unsupported", "error");
        return { ok: false, reason: "unsupported" };
      }

      let local = typeof getLocalStream === "function" ? getLocalStream() : null;
      if (!local || !local.getAudioTracks().length) {
        try {
          local = await ensureLocalStream();
        } catch (err) {
          console.error("[Recording] could not get microphone stream", err);
          setIndicator("mic required for recording", "error");
          return { ok: false, reason: "no_mic" };
        }
      }
      if (!local || !local.getAudioTracks().length) {
        console.error("[Recording] no local audio tracks");
        setIndicator("mic required for recording", "error");
        return { ok: false, reason: "no_mic" };
      }

      recStream = cloneAudioStream(local);
      if (!recStream) {
        setIndicator("mic required for recording", "error");
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
        setIndicator("recorder error", "error");
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
        setIndicator("⏺ recording…", "recording");
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
        setIndicator("recorder error", "error");
        return { ok: false, reason: "start_failed" };
      }
    }

    function stopFromEvent(data) {
      const stopPromise = new Promise((resolve) => {
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
            uploaded: false,
          };
          session = null;

          setIndicator("recording saved (local)", "muted");
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
          setIndicator("recorder error", "error");
          resolve({ ok: false, reason: "stop_failed" });
        }
      });

      const chain = stopPromise.then(async (stopRes) => {
        if (stopRes && stopRes.ok && stopRes.result && autoUpload) {
          const uploadRes = await runUpload(stopRes.result);
          return { ...stopRes, upload: uploadRes };
        }
        return stopRes;
      });
      pendingWork = pendingWork.then(
        () => chain,
        () => chain
      );
      return chain;
    }

    /**
     * After role swap / reload, pages miss live socket events. If the server
     * still has recording_active, start MediaRecorder for the current take.
     */
    async function resumeIfActive(maxAttempts) {
      if (suppressNewTakes) {
        return { ok: false, reason: "navigating_away" };
      }
      const attempts = maxAttempts || 8;
      for (let i = 0; i < attempts; i++) {
        if (suppressNewTakes) {
          return { ok: false, reason: "navigating_away" };
        }
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
        await sleep(400);
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
      // Role swap: stop current take if needed and ignore round-2 start on this page.
      socket.on("roles_swapped", (data) => {
        if (data && data.game_id && data.game_id !== gameId) return;
        prepareForNavigation();
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
      uploadResult,
      waitForIdle,
      prepareForNavigation,
      isRecording,
      isBusy,
      getLastResult,
      downloadLast,
      resetIndicator,
    };
  }

  window.createSessionRecorder = createSessionRecorder;
})();
