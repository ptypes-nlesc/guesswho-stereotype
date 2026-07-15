// Multi-peer WebRTC mesh for GuessWho
// Voice joins automatically after mic check; use Mute to silence yourself.

(function () {
  const ICE_SERVERS = [
    { urls: "stun:stun.l.google.com:19302" },
    { urls: "stun:stun1.l.google.com:19302" },
    { urls: "stun:stun.cloudflare.com:3478" },
    {
      urls: [
        "turn:openrelay.metered.ca:80",
        "turn:openrelay.metered.ca:443",
        "turn:openrelay.metered.ca:443?transport=tcp",
      ],
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

    function addLocalTracksToPeer(pc) {
      if (!localStream) return false;
      let added = false;
      const senders = pc.getSenders();
      localStream.getTracks().forEach((track) => {
        const alreadySending = senders.some((sender) => sender.track && sender.track.id === track.id);
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
      addLocalTracksToPeer(pc);
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      console.log(`[WebRTC] Sending OFFER (${reason}) from ${clientId} to ${peerId}`);
      socket.emit("webrtc_signal", {
        game_id: gameId,
        from_id: clientId,
        to_id: peerId,
        role,
        ...(includeParticipantId ? { participant_id: participantId } : {}),
        description: pc.localDescription,
      });
    }

    async function renegotiateOutboundPeers(reason) {
      if (!localStream) return;
      for (const peerId of Object.keys(peers)) {
        if (shouldBeOfferer(clientId, peerId)) {
          try {
            await sendOffer(peerId, reason);
          } catch (err) {
            console.error(`[WebRTC] Renegotiation failed for ${peerId}:`, err);
          }
        }
      }
    }

    function removePeer(peerId) {
      const pc = peers[peerId];
      if (pc) {
        try { pc.close(); } catch (_) {}
      }
      const audio = peerAudioEls[peerId];
      if (audio) {
        audio.srcObject = null;
        audio.remove();
        delete peerAudioEls[peerId];
      }
      delete remoteStreams[peerId];
      delete peers[peerId];
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
      const pc = new RTCPeerConnection({ iceServers: ICE_SERVERS });

      pc.onicecandidate = (event) => {
        if (event.candidate) {
          socket.emit("webrtc_signal", {
            game_id: gameId,
            from_id: clientId,
            to_id: peerId,
            role,
            ...(includeParticipantId ? { participant_id: participantId } : {}),
            candidate: event.candidate,
          });
        }
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
            const current = pc.connectionState || "idle";
            if (current === "disconnected" || current === "failed" || current === "closed") {
              removePeer(peerId);
            }
          }, 3000);
        }
        if (state === "connected") {
          playAllRemoteAudio().then(() => updateStatus());
        }
        updateStatus();
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
      const peerIds = Object.keys(peers);
      if (peerIds.length === 0) {
        setStatus(isMuted ? "voice on (muted) — waiting for peers…" : "voice on — waiting for peers…");
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

    function shouldBeOfferer(localId, remoteId) {
      return localId < remoteId;
    }

    async function handleRemoteDescription(peerId, description) {
      let pc = peers[peerId];
      if (!pc) {
        pc = createPeerConnection(peerId);
      }

      try {
        await pc.setRemoteDescription(new RTCSessionDescription(description));
        if (pendingCandidates[peerId] && pendingCandidates[peerId].length) {
          for (const cand of pendingCandidates[peerId]) {
            try {
              await pc.addIceCandidate(new RTCIceCandidate(cand));
            } catch (e) {
              console.warn(`Failed to add queued ICE candidate from ${peerId}:`, e);
            }
          }
          pendingCandidates[peerId] = [];
        }
        if (description.type === "offer") {
          addLocalTracksToPeer(pc);
          const answer = await pc.createAnswer();
          await pc.setLocalDescription(answer);
          socket.emit("webrtc_signal", {
            game_id: gameId,
            from_id: clientId,
            to_id: peerId,
            role,
            ...(includeParticipantId ? { participant_id: participantId } : {}),
            description: pc.localDescription,
          });
        }
      } catch (err) {
        console.error(`Error handling remote description from ${peerId}:`, err);
      }
    }

    async function handleIncomingSignal(payload) {
      const fromId = payload.from_id;
      const description = payload.description;
      const candidate = payload.candidate;

      if (description) {
        await handleRemoteDescription(fromId, description);
      } else if (candidate) {
        let pc = peers[fromId];
        if (!pc) {
          pc = createPeerConnection(fromId);
        }
        try {
          if (pc.remoteDescription) {
            await pc.addIceCandidate(new RTCIceCandidate(candidate));
          } else {
            if (!pendingCandidates[fromId]) pendingCandidates[fromId] = [];
            pendingCandidates[fromId].push(candidate);
          }
        } catch (err) {
          console.error(`Failed to process ICE candidate from ${fromId}:`, err);
        }
      }
    }

    async function connectToPeer(peerId, reason) {
      if (!localStream || peers[peerId]) return;
      createPeerConnection(peerId);
      if (shouldBeOfferer(clientId, peerId)) {
        await sendOffer(peerId, reason);
      }
      updateStatus();
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
        await renegotiateOutboundPeers("after-voice-join");
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