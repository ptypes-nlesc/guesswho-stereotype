# Project Roadmap – Xposed

This roadmap outlines the current development milestones and future goals for the *Xposed* web application.  

---

## Phase 1 – Core Functionality (MVP)

- [x] Flask backend with `/create_game` endpoint  
- [x] Player and Moderator interfaces  
- [x] Socket.IO real-time communication  
- [x] Unique `game_id` per session  
- [x] SQLite logging of all in-game events  
- [x] Basic UI for character cards and interactions  

---

## Phase 2 – First Game Playable

- [ ] Add win condition & final guess UI 
- [x] Improve card layout and responsive design  
- [x] Add index page with login for moderator
- [x] Add moderator dashboard  
- [ ] Pre-generate game IDs in advance for participant distribution 
- [ ] Enable export of game data as `.csv` or `.json` 

---

## Phase 3 – Live Audio & Moderator-Controlled Recording 

### Live Voice Communication
- [ ] Add audio_events table to SQLite schema
- [ ] Integrate WebRTC for 3-way peer-to-peer audio 
- [ ] Use Socket.IO for WebRTC signaling 

### Moderator Recording Control
- [ ] Add "Start/Stop Recording" buttons to moderator dashboard 
- [ ] Broadcast `recording_start` / `recording_stop` socket events to all players 

### Audio Capture & Storage
- [ ] Implement MediaRecorder API on all player pages 
- [ ] Auto-start capture when receiving `recording_start` event
- [ ] Auto-stop capture when receiving `recording_stop` event
- [ ] Save `.wav` files to `data/audio/{game_id}/{role}_{timestamp}.wav` 
- [ ] Store recording metadata in database with synchronized timestamps

---

## Phase 4 – Production Deployment & Security

- [ ] Enable HTTPS with SSL certificates 
- [ ] Set up reverse proxy (nginx) for production hosting
- [ ] Require MODERATOR_PASSWORD environment variable (no hardcoded default)
- [ ] Add comprehensive input validation & error handling
- [ ] Implement disconnect recovery & reconnection logic
- [ ] Documentation for researchers and deployment instructions

---

## Phase 5 – Future Features

- [ ] Automatic speech-to-text transcription (Whisper API)
- [ ] Researcher analytics dashboard
- [ ] Export analysis-ready datasets (events + audio + transcripts)
- [ ] Add test suite (pytest + Playwright for UI)
- [ ] Support multiple concurrent moderators

---

### 🗓️ Last Updated
January 15, 2026




