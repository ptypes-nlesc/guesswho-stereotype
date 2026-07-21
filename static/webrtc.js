// Multi-peer WebRTC mesh for GuessWho
// Voice joins automatically after mic check; use Mute to silence yourself.
// Uses perfect negotiation to avoid offer/answer glare between peers.
//
// Single-browser multi-tab self-test often fails to "hear yourself" even when
// connected (autoplay policy + echo cancellation). Prefer two devices, or
// open pages with ?voice_debug=1 to loosen mic processing and log levels.

(function () {
  // Keep iceServers under 5 URLs (browser warning). Include TURN/TCP for
  // restricted networks (VMs, campus firewalls) where host/srflx ICE fails.
  const TURN_USER = "openrelayproject";
  const TURN_PASS = "openrelayproject";
  const ICE_SERVERS = [
    { urls: "stun:stun.l.google.com:19302" },
    {
      urls: [
        "turn:openrelay.metered.ca:80",
        "turn:openrelay.metered.ca:443",
        "turn:openrelay.metered.ca:443?transport=tcp",
      ],
      username: TURN_USER,
      credential: TURN_PASS,
    },
  ];

  function voiceDebugEnabled() {
    try {
      return new URLSearchParams(window.location.search).has("voice_debug");
    } catch (_) {
      return false;
    }
  }

  function setupVoice(opts) {
    const socket = opts.socket;
    const gameId = opts.gameId;
    const role = opts.role;
    const muteButtonEl = opts.muteButtonEl || opts.buttonEl;
    const statusEl = opts.statusEl;
    const socketReady = opts.socketReady || Promise.resolve();
    const autoJoin = opts.autoJoin !== false;
    const muteLabels = Object.assign(
      { active: "Mute", muted: "Unmute", pending: "Mute" },
      opts.muteLabels || {}
    );
    const debug = voiceDebugEnabled();

    const participantStorageKey = `participant_id_${gameId}_${role}`;
    let participantId = localStorage.getItem(participantStorageKey);
    if (!participantId) {
      participantId = crypto.randomUUID();
      localStorage.setItem(participantStorageKey, participantId);
    }
    window.participantId = participantId;
    console.log(`[WebRTC] Participant ID (${role}): ${participantId}`);
    const includeParticipantId = role !== "moderator";

    const storageKey = `gw_client_id_${role || "unknown"}`;
    let clientId = null;
    try {
      clientId = localStorage.getItem(storageKey);
    } catch (_) {}
    if (!clientId) {
      clientId = `${role || "unknown"}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      try {
        localStorage.setItem(storageKey, clientId);
      } catch (_) {}
    }
    console.log(`[WebRTC] Stable client_id: ${clientId}`);
    if (debug) console.log("[WebRTC] voice_debug=1 — AEC off, inbound stats logging on");

    let localStream = null;
    let peers = {};
    let remoteStreams = {};
    let peerAudioEls = {};
    let pendingCandidates = {};
    let makingOffer = {};
    let ignoreOffer = {};
    let signalChain = {};
    let statsTimers = {};
    let iceRestartAttempts = {};
    let lastIceFailure = null;
    let audioUnlocked = false;
    let audioBlocked = false;
    let voiceActive = false;
    let isMuted = false;
    let audioUnlockBound = false;
    let audioCtx = null;

    function bindSilentAudioUnlock() {
      if (audioUnlockBound) return;
      audioUnlockBound = true;
      const unlock = () => {
        if (!voiceActive) return;
        resumeAudioContext();
        playAllRemoteAudio().then(() => updateStatus());
      };
      document.addEventListener("click", unlock, true);
      document.addEventListener("keydown", unlock, true);
      document.addEventListener("touchstart", unlock, true);
    }

    function resumeAudioContext() {
      try {
        const Ctx = window.AudioContext || window.webkitAudioContext;
        if (!Ctx) return;
        if (!audioCtx) audioCtx = new Ctx();
        if (audioCtx.state === "suspended") {
          audioCtx.resume().catch(() => {});
        }
      } catch (_) {}
    }

    function setStatus(text) {
      if (statusEl) statusEl.textContent = text;
    }

    function updateMuteButton() {
      if (!muteButtonEl) return;
      if (!voiceActive) {
        muteButtonEl.textContent = muteLabels.pending;
        muteButtonEl.disabled = true;
        muteButtonEl.title = "Voice is connecting…";
        return;
      }
      muteButtonEl.disabled = false;
      muteButtonEl.title = audioBlocked
        ? "Click to enable speaker output"
        : "";
      muteButtonEl.textContent = isMuted ? muteLabels.muted : muteLabels.active;
    }

    function getPeerAudioEl(peerId) {
      if (peerAudioEls[peerId]) return peerAudioEls[peerId];
      const audio = document.createElement("audio");
      audio.autoplay = true;
      audio.playsInline = true;
      // Required for WebKit; keep element in the document tree.
      audio.setAttribute("playsinline", "");
      audio.setAttribute("autoplay", "");
      audio.controls = false;
      audio.muted = false;
      audio.volume = 1.0;
      audio.dataset.peerId = peerId;
      // Not display:none — some browsers refuse to play fully hidden media.
      audio.style.cssText =
        "position:fixed;left:0;bottom:0;width:1px;height:1px;opacity:0.01;z-index:-1;";
      document.body.appendChild(audio);
      peerAudioEls[peerId] = audio;
      return audio;
    }

    async function playOne(audio, peerId) {
      if (!audio || !audio.srcObject) return false;
      audio.muted = false;
      audio.volume = 1.0;
      try {
        await audio.play();
        if (debug) {
          console.log(`[WebRTC] play() ok for ${peerId || audio.dataset.peerId}`, {
            paused: audio.paused,
            muted: audio.muted,
            volume: audio.volume,
            readyState: audio.readyState,
          });
        }
        return true;
      } catch (err) {
        console.warn(
          `[WebRTC] Audio play blocked for ${peerId || audio.dataset.peerId}:`,
          err
        );
        return false;
      }
    }

    async function playAllRemoteAudio() {
      resumeAudioContext();
      const entries = Object.entries(peerAudioEls);
      if (entries.length === 0) {
        audioBlocked = false;
        return true;
      }
      let allOk = true;
      for (const [peerId, audio] of entries) {
        if (!audio.srcObject) continue;
        const ok = await playOne(audio, peerId);
        if (!ok) allOk = false;
      }
      audioUnlocked = allOk;
      audioBlocked = !allOk;
      return allOk;
    }

    function setMuted(muted) {
      isMuted = muted;
      if (localStream) {
        localStream.getAudioTracks().forEach((track) => {
          track.enabled = !muted;
        });
      }
      if (debug) {
        console.log(`[WebRTC] local mic ${muted ? "MUTED" : "LIVE"}`, {
          tracks: (localStream && localStream.getAudioTracks().map((t) => ({
            id: t.id,
            enabled: t.enabled,
            muted: t.muted,
            readyState: t.readyState,
          }))) || [],
        });
      }
      updateMuteButton();
    }

    function signalPayload(extra) {
      return {
        game_id: gameId,
        from_id: clientId,
        role,
        ...(includeParticipantId ? { participant_id: participantId } : {}),
        ...extra,
      };
    }

    /** Deterministic offerer: lower client_id always makes the offer (impolite). */
    function shouldBeOfferer(localId, remoteId) {
      return localId < remoteId;
    }

    function isPolite(remoteId) {
      return !shouldBeOfferer(clientId, remoteId);
    }

    function enqueueSignal(peerId, task) {
      const prev = signalChain[peerId] || Promise.resolve();
      const next = prev.then(task, task);
      signalChain[peerId] = next.catch(() => {});
      return next;
    }

    function addLocalTracksToPeer(pc) {
      if (!localStream) return false;
      let added = false;
      const senders = pc.getSenders();
      localStream.getTracks().forEach((track) => {
        const alreadySending = senders.some(
          (sender) => sender.track && sender.track.id === track.id
        );
        if (!alreadySending) {
          pc.addTrack(track, localStream);
          added = true;
        }
      });
      return added;
    }

    async function sendOffer(peerId, reason) {
      const pc = peers[peerId];
      if (!pc || !localStream) return;
      const iceRestart = reason === "ice-restart";
      if (!iceRestart && pc.signalingState !== "stable") {
        console.log(`[WebRTC] Skip offer to ${peerId} (${reason}): state=${pc.signalingState}`);
        return;
      }

      addLocalTracksToPeer(pc);
      makingOffer[peerId] = true;
      try {
        const offer = await pc.createOffer(iceRestart ? { iceRestart: true } : undefined);
        await pc.setLocalDescription(offer);
        console.log(`[WebRTC] Sending OFFER (${reason}) from ${clientId} to ${peerId}`);
        socket.emit(
          "webrtc_signal",
          signalPayload({
            to_id: peerId,
            description: pc.localDescription,
          })
        );
      } finally {
        makingOffer[peerId] = false;
      }
    }

    async function logIceDiagnostics(peerId, pc) {
      console.warn(`[WebRTC] ICE diagnostics for ${peerId}`, {
        connectionState: pc.connectionState,
        iceConnectionState: pc.iceConnectionState,
        iceGatheringState: pc.iceGatheringState,
        signalingState: pc.signalingState,
      });
      try {
        const report = await pc.getStats();
        report.forEach((r) => {
          if (r.type === "local-candidate" || r.type === "remote-candidate") {
            console.warn(`[WebRTC] ${r.type}`, {
              peer: peerId,
              candidateType: r.candidateType,
              protocol: r.protocol,
              address: r.address || r.ip,
              port: r.port,
              url: r.url,
            });
          }
          if (r.type === "candidate-pair") {
            console.warn(`[WebRTC] candidate-pair`, {
              peer: peerId,
              state: r.state,
              nominated: r.nominated,
              local: r.localCandidateId,
              remote: r.remoteCandidateId,
            });
          }
        });
      } catch (err) {
        console.warn(`[WebRTC] getStats failed for ${peerId}`, err);
      }
    }

    function stopStats(peerId) {
      if (statsTimers[peerId]) {
        clearInterval(statsTimers[peerId]);
        delete statsTimers[peerId];
      }
    }

    function startStats(peerId, pc) {
      if (!debug) return;
      stopStats(peerId);
      let ticks = 0;
      statsTimers[peerId] = setInterval(async () => {
        ticks += 1;
        if (ticks > 30 || !peers[peerId]) {
          stopStats(peerId);
          return;
        }
        try {
          const report = await pc.getStats();
          report.forEach((r) => {
            if (r.type === "inbound-rtp" && (r.kind === "audio" || r.mediaType === "audio")) {
              console.log(`[WebRTC] inbound ${peerId}`, {
                packetsReceived: r.packetsReceived,
                bytesReceived: r.bytesReceived,
                audioLevel: r.audioLevel,
                jitter: r.jitter,
              });
            }
            if (r.type === "outbound-rtp" && (r.kind === "audio" || r.mediaType === "audio")) {
              console.log(`[WebRTC] outbound → peer ${peerId}`, {
                packetsSent: r.packetsSent,
                bytesSent: r.bytesSent,
              });
            }
          });
        } catch (_) {}
      }, 2000);
    }

    function removePeer(peerId) {
      const pc = peers[peerId];
      if (pc) {
        try {
          pc.onicecandidate = null;
          pc.ontrack = null;
          pc.onconnectionstatechange = null;
          pc.onnegotiationneeded = null;
          pc.close();
        } catch (_) {}
      }
      stopStats(peerId);
      const audio = peerAudioEls[peerId];
      if (audio) {
        try {
          audio.pause();
        } catch (_) {}
        audio.srcObject = null;
        audio.remove();
        delete peerAudioEls[peerId];
      }
      delete remoteStreams[peerId];
      delete peers[peerId];
      delete pendingCandidates[peerId];
      delete makingOffer[peerId];
      delete ignoreOffer[peerId];
      delete signalChain[peerId];
      delete iceRestartAttempts[peerId];
      updateStatus();
    }

    function attachRemoteTrack(peerId, event) {
      const track = event.track;
      if (!track) return;

      let stream = remoteStreams[peerId];
      if (!stream) {
        stream = event.streams && event.streams[0]
          ? event.streams[0]
          : new MediaStream();
        remoteStreams[peerId] = stream;
      }
      if (!stream.getTracks().some((t) => t.id === track.id)) {
        // Prefer the stream from the event when present; else attach manually.
        if (!(event.streams && event.streams[0])) {
          stream.addTrack(track);
        } else {
          stream = event.streams[0];
          remoteStreams[peerId] = stream;
        }
      }

      const audio = getPeerAudioEl(peerId);
      if (audio.srcObject !== stream) {
        audio.srcObject = stream;
      }

      console.log(`[WebRTC] Remote track from ${peerId}`, {
        id: track.id,
        kind: track.kind,
        muted: track.muted,
        enabled: track.enabled,
        readyState: track.readyState,
      });

      const tryPlay = () => {
        playAllRemoteAudio().then(() => updateStatus());
      };

      track.onunmute = () => {
        console.log(`[WebRTC] Remote track unmuted from ${peerId}`);
        tryPlay();
      };
      track.onmute = () => {
        console.log(`[WebRTC] Remote track muted from ${peerId}`);
      };
      track.onended = () => {
        console.log(`[WebRTC] Remote track ended from ${peerId}`);
      };

      // Tracks often start muted until first RTP packet.
      if (!track.muted) tryPlay();
      else {
        // Still attempt play; unmute handler will retry.
        tryPlay();
      }
    }

    function createPeerConnection(peerId) {
      if (peers[peerId]) return peers[peerId];

      const pc = new RTCPeerConnection({ iceServers: ICE_SERVERS });

      pc.onicecandidate = (event) => {
        if (!event.candidate) {
          console.log(`[WebRTC] ICE gathering complete for ${peerId}`);
          return;
        }
        const c = event.candidate;
        // host/srflx/relay — if you never see "relay", TURN is not working.
        console.log(`[WebRTC] local ICE → ${peerId}`, {
          type: c.type,
          protocol: c.protocol,
          address: c.address,
          port: c.port,
          candidate: c.candidate,
        });
        socket.emit(
          "webrtc_signal",
          signalPayload({
            to_id: peerId,
            candidate: event.candidate,
          })
        );
      };

      pc.onicecandidateerror = (event) => {
        console.warn(`[WebRTC] ICE candidate error for ${peerId}`, {
          url: event.url,
          errorCode: event.errorCode,
          errorText: event.errorText,
          hostCandidate: event.hostCandidate,
        });
      };

      pc.oniceconnectionstatechange = () => {
        console.log(`${peerId} iceConnectionState: ${pc.iceConnectionState}`);
      };

      pc.ontrack = (event) => attachRemoteTrack(peerId, event);

      pc.onconnectionstatechange = () => {
        const state = pc.connectionState || "idle";
        console.log(`${peerId} connection state: ${state}`);
        if (state === "failed") {
          logIceDiagnostics(peerId, pc);
          // One ICE restart before giving up (helps flaky NAT / TURN).
          if (!iceRestartAttempts[peerId] && shouldBeOfferer(clientId, peerId)) {
            iceRestartAttempts[peerId] = 1;
            lastIceFailure = "ICE failed — retrying…";
            updateStatus();
            enqueueSignal(peerId, async () => {
              try {
                await sendOffer(peerId, "ice-restart");
              } catch (err) {
                console.error(`[WebRTC] ICE restart failed for ${peerId}:`, err);
                lastIceFailure =
                  "ICE failed (firewall/NAT). Need working TURN relay.";
                removePeer(peerId);
              }
            });
            return;
          }
          lastIceFailure =
            "ICE failed (firewall/NAT). Need working TURN relay.";
          removePeer(peerId);
          return;
        }
        if (state === "closed") {
          removePeer(peerId);
          return;
        }
        if (state === "disconnected") {
          setTimeout(() => {
            const current = peers[peerId];
            if (!current || current !== pc) return;
            const s = pc.connectionState || "idle";
            if (s === "disconnected" || s === "failed" || s === "closed") {
              lastIceFailure =
                "ICE disconnected. Check network / TURN.";
              removePeer(peerId);
            }
          }, 3000);
        }
        if (state === "connected") {
          lastIceFailure = null;
          iceRestartAttempts[peerId] = 0;
          startStats(peerId, pc);
          playAllRemoteAudio().then(() => updateStatus());
        }
        updateStatus();
      };

      pc.onnegotiationneeded = () => {
        enqueueSignal(peerId, async () => {
          if (!shouldBeOfferer(clientId, peerId)) return;
          if (!localStream || !peers[peerId]) return;
          try {
            await sendOffer(peerId, "negotiationneeded");
          } catch (err) {
            console.error(`[WebRTC] negotiationneeded failed for ${peerId}:`, err);
          }
        });
      };

      addLocalTracksToPeer(pc);
      peers[peerId] = pc;
      if (!pendingCandidates[peerId]) pendingCandidates[peerId] = [];
      return pc;
    }

    function updateStatus() {
      if (!voiceActive) {
        setStatus("connecting voice…");
        return;
      }
      if (audioBlocked) {
        setStatus("🔊 click page to enable sound");
        updateMuteButton();
        return;
      }
      const peerIds = Object.keys(peers);
      if (peerIds.length === 0) {
        if (lastIceFailure) {
          setStatus(lastIceFailure);
        } else {
          setStatus(
            isMuted
              ? "voice on (muted) — waiting for peers…"
              : "voice on — waiting for peers…"
          );
        }
        updateMuteButton();
        return;
      }
      const states = Object.values(peers).map((pc) => pc.connectionState || "unknown");
      const connected = states.filter((s) => s === "connected").length;
      const failed = states.filter((s) => s === "failed").length;
      let text = `${connected}/${states.length} connected`;
      if (isMuted) text += " (muted)";
      if (failed > 0) text += ` (${failed} failed)`;
      setStatus(text);
      updateMuteButton();
    }

    async function flushPendingCandidates(peerId, pc) {
      const queued = pendingCandidates[peerId] || [];
      pendingCandidates[peerId] = [];
      for (const cand of queued) {
        try {
          await pc.addIceCandidate(new RTCIceCandidate(cand));
        } catch (e) {
          if (!ignoreOffer[peerId]) {
            console.warn(`Failed to add queued ICE candidate from ${peerId}:`, e);
          }
        }
      }
    }

    async function handleRemoteDescription(peerId, description) {
      const pc = createPeerConnection(peerId);
      const polite = isPolite(peerId);

      const offerCollision =
        description.type === "offer" &&
        (makingOffer[peerId] || pc.signalingState !== "stable");

      ignoreOffer[peerId] = !polite && offerCollision;
      if (ignoreOffer[peerId]) {
        console.log(`[WebRTC] Ignoring colliding offer from ${peerId} (we are impolite)`);
        return;
      }

      if (offerCollision && polite) {
        console.log(`[WebRTC] Glare with ${peerId}: rolling back local offer`);
        await Promise.all([
          pc.setLocalDescription({ type: "rollback" }),
          pc.setRemoteDescription(new RTCSessionDescription(description)),
        ]);
      } else {
        await pc.setRemoteDescription(new RTCSessionDescription(description));
      }

      await flushPendingCandidates(peerId, pc);

      if (description.type === "offer") {
        addLocalTracksToPeer(pc);
        if (pc.signalingState !== "have-remote-offer") {
          console.warn(
            `[WebRTC] Unexpected state after remote offer from ${peerId}: ${pc.signalingState}`
          );
          return;
        }
        await pc.setLocalDescription(await pc.createAnswer());
        socket.emit(
          "webrtc_signal",
          signalPayload({
            to_id: peerId,
            description: pc.localDescription,
          })
        );
      }
    }

    async function handleIncomingSignal(payload) {
      const fromId = payload.from_id;
      if (!fromId || fromId === clientId) return;

      const description = payload.description;
      const candidate = payload.candidate;

      await enqueueSignal(fromId, async () => {
        if (description) {
          try {
            await handleRemoteDescription(fromId, description);
          } catch (err) {
            console.error(`Error handling remote description from ${fromId}:`, err);
          }
          return;
        }

        if (!candidate) return;

        const pc = createPeerConnection(fromId);
        try {
          if (pc.remoteDescription && pc.remoteDescription.type) {
            await pc.addIceCandidate(new RTCIceCandidate(candidate));
          } else {
            if (!pendingCandidates[fromId]) pendingCandidates[fromId] = [];
            pendingCandidates[fromId].push(candidate);
          }
        } catch (err) {
          if (!ignoreOffer[fromId]) {
            console.error(`Failed to process ICE candidate from ${fromId}:`, err);
          }
        }
      });
    }

    async function connectToPeer(peerId, reason) {
      if (!localStream || !peerId || peerId === clientId) return;

      await enqueueSignal(peerId, async () => {
        const existing = peers[peerId];
        if (existing) {
          return;
        }
        createPeerConnection(peerId);
        if (shouldBeOfferer(clientId, peerId)) {
          try {
            await sendOffer(peerId, reason);
          } catch (err) {
            console.error(`[WebRTC] Initial offer failed for ${peerId}:`, err);
          }
        }
        updateStatus();
      });
    }

    async function startVoice() {
      try {
        if (window.MicCheck && !MicCheck.isMicReady()) {
          setStatus("microphone check required");
          updateMuteButton();
          return;
        }

        if (!localStream) {
          // Same-machine multi-tab loopback is often silenced by AEC.
          // ?voice_debug=1 disables processing so self-test can hear packets.
          const audioConstraints = debug
            ? {
                echoCancellation: false,
                noiseSuppression: false,
                autoGainControl: false,
              }
            : {
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
              };
          localStream = await navigator.mediaDevices.getUserMedia({
            audio: audioConstraints,
          });
          if (debug) {
            console.log(
              "[WebRTC] local tracks",
              localStream.getAudioTracks().map((t) => ({
                label: t.label,
                settings: t.getSettings && t.getSettings(),
              }))
            );
          }
        }

        await socketReady;

        const ack = await new Promise((resolve) => {
          socket.emit(
            "voice_join",
            {
              game_id: gameId,
              role,
              client_id: clientId,
              ...(includeParticipantId ? { participant_id: participantId } : {}),
            },
            resolve
          );
        });

        if (!ack || ack.status === "error") {
          setStatus(ack?.message || "voice join failed");
          voiceActive = false;
          updateMuteButton();
          return;
        }

        voiceActive = true;
        bindSilentAudioUnlock();
        setMuted(false);
        updateStatus();
      } catch (err) {
        console.error("Voice start failed:", err);
        voiceActive = false;
        setStatus("microphone blocked");
        updateMuteButton();
      }
    }

    function stopVoice() {
      socket.emit("voice_leave", {
        game_id: gameId,
        client_id: clientId,
        role,
      });

      Object.keys(peers).forEach((peerId) => removePeer(peerId));
      peers = {};
      peerAudioEls = {};
      remoteStreams = {};
      pendingCandidates = {};
      makingOffer = {};
      ignoreOffer = {};
      signalChain = {};
      iceRestartAttempts = {};
      lastIceFailure = null;

      if (localStream) {
        localStream.getTracks().forEach((t) => t.stop());
        localStream = null;
      }

      audioUnlocked = false;
      audioBlocked = false;
      voiceActive = false;
      isMuted = false;
      setStatus("voice off");
      updateMuteButton();
    }

    if (muteButtonEl) {
      muteButtonEl.addEventListener("click", async () => {
        if (!voiceActive) return;
        // Mute click is a user gesture — always try to unlock speakers first.
        await playAllRemoteAudio();
        // If audio was blocked, first click only enables speakers.
        if (audioBlocked) {
          updateStatus();
          return;
        }
        setMuted(!isMuted);
        updateStatus();
      });
    }

    socket.on("peers_list", async (data) => {
      for (const peer of data.peers || []) {
        if (peer.client_id === clientId) continue;
        await connectToPeer(peer.client_id, "peers-list");
      }
    });

    socket.on("new_peer_joined", async (data) => {
      if (!data || data.client_id === clientId) return;
      await connectToPeer(data.client_id, "new-peer");
    });

    socket.on("peer_left_voice", (data) => {
      if (!data || data.client_id === clientId) return;
      removePeer(data.client_id);
    });

    socket.on("webrtc_signal", handleIncomingSignal);

    socket.on("game_ended", (data) => {
      if (!data || data.game_id !== gameId) return;
      stopVoice();
    });

    socket.on("connect", () => {
      if (voiceActive || localStream) {
        startVoice().catch((err) => console.error("Voice rejoin failed:", err));
      }
    });

    window.addEventListener("beforeunload", () => {
      if (!voiceActive) return;
      socket.emit("voice_leave", {
        game_id: gameId,
        client_id: clientId,
        role,
      });
    });

    updateMuteButton();
    setStatus("connecting voice…");

    if (autoJoin) {
      startVoice().catch((err) => console.error("Auto voice join failed:", err));
    }

    return { startVoice, stopVoice, setMuted, toggleMute: () => setMuted(!isMuted) };
  }

  window.setupVoice = setupVoice;
})();
