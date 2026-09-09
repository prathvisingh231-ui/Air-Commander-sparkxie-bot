# Air-Commander-sparkxie-bot

All-in-one Discord bot made with Air Command Bot owner Prithvi.

## Basic slash commands

- `/ping` — Check bot latency
- `/help` — Show the command list
- `/about` — Bot information
- `/serverinfo` — Server information
- `/userinfo` — User information
- `/avatar` — Show a user's avatar
- `/uptime` — Bot uptime

## Render deployment

This project includes `render.yaml` and a Flask health endpoint so it can run as a Render Web Service.

Set `DISCORD_TOKEN` in Render. Optionally set `GUILD_ID` to a test server ID for instant slash-command syncing.

Build command: `pip install -r requirements.txt`

Start command: `python bot.py`
