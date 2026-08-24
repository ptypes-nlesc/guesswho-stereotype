# User guide

## Moderators

1. Open `/dashboard` and log in with the staff password.
2. **Open Entry** — session state becomes `OPEN`.
3. **Generate Tokens** — download the CSV and send one join link per participant.
4. Wait until both participants are in the waiting room (`READY`).
5. **Start Game** — `IN_PROGRESS`. Player 1 sees the secret card; player 2 sees the grid.
6. **Start recording** before talk begins. Leave it running through both rounds.
7. Observe from **Moderator View** (`/moderator`): chat, voice, secret card, eliminations.
8. **Swap Roles** for round 2. Round 1 audio is finalized and uploaded; round 2 starts a new take. Pages redirect on their own.
9. **Stop recording**, then **End Game** (`ENDED`).
10. **Reset Session** (`CLOSED`) before the next pair.

Staff login is session-based. The moderator is not a participant. Moderator chat is stored with `role = moderator`.

If a stem fails to upload, the player UI offers a local download; the dashboard checklist shows which stems arrived.

## Participants

1. Open the invitation link from the moderator.
2. If the token is valid and unused, you enter the waiting room.
3. When the game starts you are sent to your role:
   - **Player 1** — secret card only
   - **Player 2** — 12-card grid; eliminate cards that no longer match
4. Allow the microphone when the browser asks. Use chat and voice as instructed.
5. After a role swap the page reloads with the other role.

Closing the tab does not drop your identity. If the session is still active, reopen `/player1` or `/player2`. After end or reset you need a new invitation.

## Session states

| State | Meaning |
|------|---------|
| `CLOSED` | No entry |
| `OPEN` | Tokens may be redeemed |
| `READY` | Two players waiting for start |
| `IN_PROGRESS` | Live play |
| `ENDED` | Finished |

## What is stored

| Data | Table / location |
|------|------------------|
| Secret card per round | `rounds.chosen_card_id` |
| Round timing | `rounds.started_at`, `rounds.ended_at` |
| Session events | `events` |
| Chat | `chat` |
| Eliminations | `eliminated_cards` |
| Join tokens | `access_tokens` |
| Audio stem metadata | `audio_events` |
| Audio files | `{AUDIO_STORAGE_DIR}/{game_id}/` |
