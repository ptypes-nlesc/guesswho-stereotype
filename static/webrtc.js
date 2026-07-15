// Multi-peer WebRTC mesh for GuessWho
// Voice joins automatically after mic check; use Mute to silence yourself.
// Uses perfect negotiation to avoid offer/answer glare between peers.

(function () {
  // Keep iceServers small: 5+ slows discovery and triggers browser warnings.
  const ICE_SERVERS = [
    { urls: "stun:stun.l.google.com:19302" },
    {
      urls: "turn:openrelay.metered.ca:80",
      username: "openrelayproject",
      credential: "openrelayproject",
    },
  ];

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

    let localStream = null;
    let peers = {};
    let remoteStreams = {};
    let peerAudioEls = {};
    let pendingCandidates = {};
    let makingOffer = {};
    let ignoreOffer = {};
    let signalChain = {};
    let audioUnlocked = false;
    let voiceActive = false;
    let isMuted = false;
    let audioUnlockBound = false;

    function bindSilentAudioUnlock() {
      if (audioUnlockBound) return;
      audioUnlockBound = true;
      document.addEventListener(
        "click",
        () => {
          if (!voiceActive || audioUnlocked) return;
          playAllRemoteAudio().then(() => updateStatus());
        },
        true
      );
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
      muteButtonEl.title = "";
      muteButtonEl.textContent = isMuted ? muteLabels.muted : muteLabels.active;
    }

    function getPeerAudioEl(peerId) {
      if (peerAudioEls[peerId]) return peerAudioEls[peerId];
      const audio = document.createElement("audio");
      audio.autoplay = true;
      audio.playsInline = true;
      audio.muted = false;
      audio.volume = 1;
      audio.dataset.peerId = peerId;
      audio.style.cssText = "position:fixed;width:0;height:0;opacity:0;pointer-events:none;";
      document.body.appendChild(audio);
      peerAudioEls[peerId] = audio;
      return audio;
    }

    async function playAllRemoteAudio() {
      const elements = Object.values(peerAudioEls);
      let allOk = true;
      for (const audio of elements) {
        if (!audio.srcObject) continue;
        audio.muted = false;
        try {
          await audio.play();
        } catch (err) {
          console.warn("[WebRTC] Audio play blocked:", err);
          allOk = false;
        }
      }
      if (allOk && elements.length > 0) {
        audioUnlocked = true;
      }
      return allOk;
    }

    function setMuted(muted) {
      isMuted = muted;
      if (localStream) {
        localStream.getAudioTracks().forEach((track) => {
          track.enabled = !muted;
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
      // Polite peer yields on glare (does not make the initial offer).
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
      if (pc.signalingState !== "stable") {
        console.log(`[WebRTC] Skip offer to ${peerId} (${reason}): state=${pc.signalingState}`);
        return;
      }

      addLocalTracksToPeer(pc);
      makingOffer[peerId] = true;
      try {
        await pc.setLocalDescription(await pc.createOffer());
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
      const audio = peerAudioEls[peerId];
      if (audio) {
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
      updateStatus();
    }

    function attachRemoteTrack(peerId, event) {
      const stream = event.streams[0] || new MediaStream([event.track]);
      remoteStreams[peerId] = stream;
      const audio = getPeerAudioEl(peerId);
      audio.srcObject = stream;
      console.log(`[WebRTC] Remote track from ${peerId}`);
      playAllRemoteAudio().then(() => updateStatus());
    }

    function createPeerConnection(peerId) {
      if (peers[peerId]) return peers[peerId];

      const pc = new RTCPeerConnection({ iceServers: ICE_SERVERS });

      pc.onicecandidate = (event) => {
        if (!event.candidate) return;
        socket.emit(
          "webrtc_signal",
          signalPayload({
            to_id: peerId,
            candidate: event.candidate,
          })
        );
      };

      pc.ontrack = (event) => attachRemoteTrack(peerId, event);

      pc.onconnectionstatechange = () => {
        const state = pc.connectionState || "idle";
        console.log(`${peerId} connection state: ${state}`);
        if (state === "failed" || state === "closed") {
          removePeer(peerId);
          return;
        }
        if (state === "disconnected") {
          setTimeout(() => {
            const current = peers[peerId];
            if (!current || current !== pc) return;
            const s = pc.connectionState || "idle";
            if (s === "disconnected" || s === "failed" || s === "closed") {
              removePeer(peerId);
            }
          }, 3000);
        }
        if (state === "connected") {
          playAllRemoteAudio().then(() => updateStatus());
        }
        updateStatus();
      };

      // Only the designated offerer responds to negotiationneeded.
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

      // Add local tracks once at creation so the first offer/answer includes audio.
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
      const peerIds = Object.keys(peers);
      if (peerIds.length === 0) {
        setStatus(
          isMuted
            ? "voice on (muted) — waiting for peers…"
            : "voice on — waiting for peers…"
        );
        return;
      }
      const states = Object.values(peers).map((pc) => pc.connectionState || "unknown");
      const connected = states.filter((s) => s === "connected").length;
      const failed = states.filter((s) => s === "failed").length;
      let text = `${connected}/${states.length} connected`;
      if (isMuted) text += " (muted)";
      if (failed > 0) text += ` (${failed} failed)`;
      setStatus(text);
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

      // Polite peer: rollback local offer on glare, then accept remote offer.
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
          // Already negotiating or connected — do not force a second offer.
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
          localStream = await navigator.mediaDevices.getUserMedia({
            audio: {
              echoCancellation: true,
              noiseSuppression: true,
              autoGainControl: true,
            },
          });
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
        // Peers are created from peers_list / new_peer_joined with tracks already attached.
        // Do not mass-renegotiate here — that caused mid/answer races.
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

      if (localStream) {
        localStream.getTracks().forEach((t) => t.stop());
        localStream = null;
      }

      audioUnlocked = false;
      voiceActive = false;
      isMuted = false;
      setStatus("voice off");
      updateMuteButton();
    }

    if (muteButtonEl) {
      muteButtonEl.addEventListener("click", async () => {
        if (!voiceActive) return;
        await playAllRemoteAudio();
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
