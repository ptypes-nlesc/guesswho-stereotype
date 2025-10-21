# Project Roadmap – Guess Who Stereotype

This roadmap outlines the current development milestones and future goals for the *Guess Who Stereotype* web application.  
The focus is on improving interactivity, data collection, and research usability.

---

## ✅ Phase 1 – Core Functionality (MVP)
**Goal:** Enable playable, data-logged prototype.

- [x] Flask backend with `/create_game` endpoint  
- [x] Player and Moderator interfaces  
- [x] Socket.IO real-time communication  
- [x] Unique `game_id` per session  
- [x] SQLite logging of all in-game events  
- [x] Basic UI for character cards and interactions  

---

## 🧪 Phase 2 – Usability & Data Quality
**Goal:** Improve user experience and ensure robust data capture.

- [ ] Improve card layout and responsive design  
- [ ] Add moderator note-taking panel  
- [ ] Include timestamps and sequence tracking in logs  
- [ ] Enable export of game data as `.csv` or `.json`  
- [ ] Add visual feedback for card eliminations  

---

## 🚧 Phase 3 – Audio Integration
**Goal:** Record and synchronize spoken dialogue with in-game actions.

- [ ] Integrate WebRTC for real-time voice chat  
- [ ] Use MediaRecorder API for local audio capture  
- [ ] Upload `.webm` files to server per participant  
- [ ] Sync audio timeline with elimination log  

---

## 🚀 Phase 4 – Deployment & Collaboration
**Goal:** Prepare the application for real studies and collaborative use.

- [ ] Authentication for moderator dashboard  
- [ ] Multi-session game management  
- [ ] Deployment to a web server (HTTPS + SSL)  
- [ ] Documentation for researchers and developers  
- [ ] Add test suite (pytest + Playwright for UI)  

---

### 🗓️ Last Updated
October 2025
