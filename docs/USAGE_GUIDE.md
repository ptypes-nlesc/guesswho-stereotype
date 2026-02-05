### For Moderators

#### Initial Setup
1. After logging in, you'll see the dashboard with two options:
   - **Controlled Entry Mode** (recommended) - Click "Open Control Panel"
   - **Quick Game Mode** - For instant testing with pre-generated URLs

2. In the **Control Panel** (`/moderator/control`):
   - You'll see the **Static Join URL** at the top
   - Copy this URL: `http://localhost:5000/join`
   - Share this URL with your participants in advance (email, chat, etc.)

#### Running a Session

**Step 1: Open Entry**
- Click the "🔓 Open Entry" button
- Status changes to OPEN
- Participants can now join

**Step 2: Wait for Participants**
- Monitor the waiting count: "X/2 participants waiting"
- When 2 participants join, status automatically changes to READY
- Entry is automatically closed

**Step 3: Start the Game**
- Review the participant IDs displayed
- Click "▶️ Start Game"
- Participants are automatically redirected to their roles (Player 1 or Player 2)
- You can now open the "Moderator Observer View" to watch the game

**Step 4: End the Game**
- When gameplay concludes, click "⏹️ End Game"
- Status changes to ENDED

**Step 5: Reset for Next Session**
- Click "🔄 Reset Session"
- Status returns to CLOSED
- You can now open entry again for the next pair of participants

### For Participants

#### Joining a Game

1. **Before the session:**
   - Receive the join URL from the moderator: `http://localhost:5000/join`
   - Open the URL in your browser
   - You'll see "Entry is currently closed"

2. **When entry opens:**
   - The page automatically updates to show "Entry is open!"
   - Click the "Join Game" button
   - You'll see "You're in the waiting room! X/2 participants"

3. **When game starts:**
   - The page shows "Waiting for moderator to start the game..."
   - When moderator clicks "Start Game", you're automatically redirected
   - You'll be assigned either Player 1 (secret card holder) or Player 2 (guesser)

4. **During gameplay:**
   - Play as normal using your assigned role view
   - No need to refresh or navigate

#### What if I close my browser?

The system stores your participant ID in localStorage, so:
- If you return to `/join` while in a game, you'll be redirected back to your game view
- If the session has ended, you'll need to join a new session
