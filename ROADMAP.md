# Project Roadmap – Guess Who Stereotype

This roadmap outlines the current development milestones and future goals for the *Guess Who Stereotype* web application.  
The focus is on improving interactivity, data collection, and research usability.

---

## ✅ Phase 1 – Core Functionality (MVP)

- [x] Flask backend with `/create_game` endpoint  
- [x] Player and Moderator interfaces  
- [x] Socket.IO real-time communication  
- [x] Unique `game_id` per session  
- [x] SQLite logging of all in-game events  
- [x] Basic UI for character cards and interactions  

---

## 🧪 Phase 2 – Usability & Data Quality

- [x] Improve card layout and responsive design  
- [x] Add index page with login for moderator
- [x] Add moderator dashboard  
- [ ] Enable export of game data as `.csv` or `.json`  

---

## 🚧 Phase 3 – Audio Capture & Voice Communication
### Data capture

- [ ] Record participant audio locally in the browser using the MediaRecorder API
- [ ] Upload one .webm audio file per participant per game to the server
- [ ] Store audio metadata (game_id, role, start/end timestamps)
- [ ] Align audio timelines with logged game events (questions, answers, eliminations)

### Real-time voice communication

- [ ] Integrate WebRTC to enable low-latency voice communication between participants
- [ ] Use existing Socket.IO infrastructure for WebRTC signaling (offer/answer, ICE candidates)
- [ ] Support direct peer-to-peer audio streams (no server-side mixing)                                
- [ ] Configure STUN (and optional TURN) servers to support NAT traversal
- [ ] Maintain MediaRecorder-based audio capture in parallel for analysis (WebRTC does not replace recording)
---

## 🚀 Phase 4 – Deployment & Collaboration

- [ ] Authentication for moderator dashboard  
- [ ] Deployment to a web server (HTTPS + SSL)  
- [ ] Documentation for researchers and developers  
- [ ] Add test suite (pytest + Playwright for UI)  

---

### 🗓️ Last Updated
December 2025
