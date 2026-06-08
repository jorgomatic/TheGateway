# TheGateWayKeeperBot

Gateway screening bot for Telegram. Users join The GateWay! group, submit 3 files, and the admin receives them via DM with Approve/Deny buttons.

## Setup

### 1. Add bot to The GateWay! group
- Add @TheGateWayKeeperBot to the group
- Make it an **admin** with these permissions:
  - ✅ Delete messages
  - ✅ Ban users (optional, for future use)
  - ✅ Invite users via link

### 2. Enable the bot to receive member join events
In BotFather: `/setprivacy` → select your bot → `Disable`
This allows the bot to see all messages in the group.

Also in BotFather run `/setjoingroups` and make sure it's enabled.

### 3. Deploy to Railway
1. Push this folder to a GitHub repo
2. Create new Railway project → Deploy from GitHub
3. Set environment variable:
   - `BOT_TOKEN` = your bot token (or it's hardcoded already)
4. Railway will auto-detect the Procfile and run `python bot.py`

## Admin Commands (send these as DMs to the bot or in the group)

| Command | Description |
|---|---|
| `/status` | See all pending submissions |
| `/reset <user_id>` | Reset a user so they can resubmit |

## Flow

1. User joins The GateWay! group
2. Bot posts welcome message tagging them
3. User sends 3 files (photos/videos/documents)
4. Bot confirms each file (1/3, 2/3, 3/3)
5. Admin receives all 3 files in DM + ✅ Approve / ❌ Deny buttons
6. Admin taps button → user gets DM with invite link or denial message
