// Multi-peer WebRTC mesh for GuessWho
// Allows 3+ participants to join a voice room and hear each other.

(function () {
  function setupVoice(opts) {
    const socket = opts.socket;
    const gameId = opts.gameId;
    const role = opts.role;
    const buttonEl = opts.buttonEl;
    const statusEl = opts.statusEl;
    const remoteAudioEl = opts.remoteAudioEl;

    // Generate or reuse a stable client ID for this browser
    const storageKey = `gw_client_id_${role || "unknown"}`;
    let clientId = null;
    try {
      clientId = localStorage.getItem(storageKey);
    } catch (_) {
      // ignore localStorage errors
    }
    if (!clientId) {
      clientId = `${role || "unknown"}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      try {
        localStorage.setItem(storageKey, clientId);
      } catch (_) {
        // ignore localStorage errors
      }
    }

    let localStream = null;
    let peers = {}; // {peer_id: RTCPeerConnection}
    let remoteStreams = {}; // {peer_id: MediaStream}
    let pendingCandidates = {}; // {peer_id: RTCIceCandidate[]}
    const remoteStream = new MediaStream(); // Combined remote audio

    if (remoteAudioEl) {
      remoteAudioEl.autoplay = true;
      remoteAudioEl.playsInline = true;
      remoteAudioEl.srcObject = remoteStream;
    }

    function setStatus(text) {
      if (statusEl) statusEl.textContent = text;
    }

    function setButton(joined) {
      if (buttonEl) buttonEl.textContent = joined ? "Leave voice" : "Join voice";
    }

    function removePeer(peerId) {
      const pc = peers[peerId];
      if (pc) {
        try { pc.close(); } catch (_) {}
      }
      const stream = remoteStreams[peerId];
      if (stream) {
        stream.getTracks().forEach((t) => {
          try { remoteStream.removeTrack(t); } catch (_) {}
        });
      }
      delete peers[peerId];
      delete remoteStreams[peerId];
      updateStatus();
    }

    function createPeerConnection(peerId) {
      const pc = new RTCPeerConnection({
        iceServers: [
          { urls: "stun:stun.l.google.com:19302" },
          { urls: "stun:stun1.l.google.com:19302" }
        ]
      });

      pc.onicecandidate = (event) => {
        if (event.candidate) {
          socket.emit("webrtc_signal", {
            game_id: gameId,
            from_id: clientId,
            to_id: peerId,
            role,
            candidate: event.candidate
          });
        }
      };

      pc.ontrack = (event) => {
        console.log(`ontrack from ${peerId}:`, event.streams);
        event.streams.forEach((stream) => {
          // Store remote stream and add its audio tracks to combined output
          remoteStreams[peerId] = stream;
          stream.getTracks().forEach((track) => {
            remoteStream.addTrack(track);
          });
        });
        if (remoteAudioEl) {
          remoteAudioEl.play().catch(() => {});
        }
      };

      pc.onconnectionstatechange = () => {
        const state = pc.connectionState || "idle";
        console.log(`${peerId} connection state: ${state}`);
        if (state === "failed" || state === "closed") {
          removePeer(peerId);
          return;
        }
        if (state === "disconnected") {
          // Give it a short grace period to recover before removing
          setTimeout(() => {
            const current = pc.connectionState || "idle";
            if (current === "disconnected" || current === "failed" || current === "closed") {
              removePeer(peerId);
            }
          }, 3000);
        }
        updateStatus();
      };

      // Add local stream tracks to this peer connection
      if (localStream) {
        localStream.getTracks().forEach((track) => {
          pc.addTrack(track, localStream);
        });
      }

      peers[peerId] = pc;
      if (!pendingCandidates[peerId]) pendingCandidates[peerId] = [];
      return pc;
    }

    function updateStatus() {
      if (Object.keys(peers).length === 0) {
        setStatus("idle");
        return;
      }
      const states = Object.values(peers).map((pc) => pc.connectionState || "unknown");
      const connected = states.filter((s) => s === "connected").length;
      setStatus(`${connected}/${states.length} connected`);
    }

    function shouldBeOfferer(localId, remoteId) {
      // Deterministic rule: only the peer with lexicographically lower ID sends offer
      // This prevents offer glare and ensures symmetric, predictable signaling
      return localId < remoteId;
    }

    async function handleRemoteDescription(peerId, description) {
      let pc = peers[peerId];
      if (!pc) {
        pc = createPeerConnection(peerId);
      }

      try {
        await pc.setRemoteDescription(new RTCSessionDescription(description));
        // Drain any ICE candidates received before remoteDescription was set
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
          const answer = await pc.createAnswer();
          await pc.setLocalDescription(answer);
          socket.emit("webrtc_signal", {
            game_id: gameId,
            from_id: clientId,
            to_id: peerId,
            role,
            description: pc.localDescription
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
            // Queue the candidate until remoteDescription is set
            if (!pendingCandidates[fromId]) pendingCandidates[fromId] = [];
            pendingCandidates[fromId].push(candidate);
          }
        } catch (err) {
          console.error(`Failed to process ICE candidate from ${fromId}:`, err);
        }
      }
    }

    async function startVoice() {
      try {
        if (!localStream) {
          localStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        }

        // Notify server we're joining voice
        socket.emit("voice_join", {
          game_id: gameId,
          role,
          client_id: clientId
        });

        setButton(true);
        setStatus("waiting for peers...");
      } catch (err) {
        console.error("Voice start failed:", err);
        setStatus("microphone blocked");
      }
    }

    function stopVoice() {
      // Close all peer connections
      Object.values(peers).forEach((pc) => {
        pc.close();
      });
      peers = {};

      // Stop local stream
      if (localStream) {
        localStream.getTracks().forEach((t) => t.stop());
        localStream = null;
      }

      // Clear remote streams
      remoteStream.getTracks().forEach((t) => remoteStream.removeTrack(t));
      Object.keys(remoteStreams).forEach((id) => {
        delete remoteStreams[id];
      });

      setStatus("idle");
      setButton(false);
    }

    if (buttonEl) {
      buttonEl.addEventListener("click", () => {
        if (Object.keys(peers).length > 0 || localStream) {
          stopVoice();
        } else {
          startVoice();
        }
      });
    }

    // Socket event: receive list of existing peers
    socket.on("peers_list", async (data) => {
      const peersList = data.peers || [];
      console.log("Received peers list:", peersList);
      for (const peer of peersList) {
        if (peer.client_id === clientId) continue; // ignore self if present
        if (!peers[peer.client_id]) {
          const pc = createPeerConnection(peer.client_id);
          // Only send offer if we should be the offerer (lower client_id)
          if (shouldBeOfferer(clientId, peer.client_id)) {
            const offer = await pc.createOffer();
            await pc.setLocalDescription(offer);
            socket.emit("webrtc_signal", {
              game_id: gameId,
              from_id: clientId,
              to_id: peer.client_id,
              role,
              description: pc.localDescription
            });
          }
        }
      }
      updateStatus();
    });

    // Socket event: receive WebRTC signal from peer
    socket.on("webrtc_signal", handleIncomingSignal);

    setStatus("idle");
    setButton(false);

    return { startVoice, stopVoice };
  }

  window.setupVoice = setupVoice;
})();
