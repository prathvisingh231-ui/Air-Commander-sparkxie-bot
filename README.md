# Air Commander — Sparkxie Bot

All-in-one Discord bot with rich embeds, server intelligence, moderation records, suggestions, and persistent PostgreSQL storage.

## Commands

Basic:
- /ping
- /help
- /about
- /serverinfo
- /userinfo
- /avatar
- /uptime

Intelligence:
- /ghostscan — inactive/old member candidates
- /activitymap — stored channel activity and category map
- /membercard — detailed member profile
- /airscan — server security/configuration/intelligence report

Moderation & community:
- /modcase — persistent AC case numbers with target, moderator, reason, and evidence
- /suggestionlab — create suggestions, voting, status changes, and staff responses

## Render

The repository includes a Render Web Service configuration and a Flask health endpoint.

Environment variables:
- DISCORD_TOKEN
- GUILD_ID (optional; recommended for instant slash-command sync during testing)
- DATABASE_URL
- OPENAI_API_KEY (required for the /ai chat command)
- OPENAI_MODEL (optional; defaults to gpt-4o-mini)

Render Postgres should be in the same region as the bot. Render provides an internal connection URL for same-region services; use that for the bot. citeturn0search1

Do not commit secrets or a local .env file. Use Render Environment Variables. citeturn0search3

## Discord setup

Enable the Server Members Intent in the Discord Developer Portal because GhostScan/member data uses the guild member cache.

Invite the bot with the applications.commands scope and the permissions required by the features you enable.


## AI chat channel

The existing `/ai prompt:` command remains available for private AI answers. Server admins with **Manage Server** can also configure conversational AI in one text channel:

- `/ai-channel-set channel:#your-channel` — enable AI chat in that channel
- `/ai-channel-remove` — disable automatic AI chat for the server
- `,ai channel set #your-channel` — prefix equivalent
- `,ai channel remove` — prefix equivalent

In the configured channel, members can mention **Air Commander** or reply to one of its messages to chat. The bot uses a short per-user cooldown and stores the channel setting in PostgreSQL, so it survives redeploys. The bot needs Message Content Intent enabled in code and in the Discord Developer Portal.
