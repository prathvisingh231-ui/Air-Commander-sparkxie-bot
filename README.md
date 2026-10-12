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


### Slash-command troubleshooting

- Set `GUILD_ID` in Render to the numeric ID of your test Discord server for fast guild command updates.
- After deployment, the bot owner can run `,syncslash` inside the target server. It copies the current registered commands to that server, syncs them, and reports the commands Discord confirms.
- The startup log now prints the actual commands fetched back from Discord after syncing, including the `/youtube` subcommands.


## PostgreSQL persistence and recovery

- Set `DATABASE_URL` in Render to a valid PostgreSQL connection string. Prefer the Render Postgres **internal** URL when the bot and database are in the same Render region. For Supabase, use a supported pooler URL if the direct host is not reachable from Render.
- `,dbstatus` is an owner-only diagnostic. It reports whether the environment variable is present, whether PostgreSQL is connected, and how many JSON snapshots are stored. It never prints the connection string.
- Legacy JSON-backed module files are backed up to the `air_json_snapshots` PostgreSQL table every 10 seconds and restored before feature modules initialize on the next deployment.
- PostgreSQL-backed records such as warnings, game/player data, tickets, and giveaways continue using their own database tables. Keep the same database instance and `DATABASE_URL` between deployments; creating a new database starts with a new empty data store.
- If `,dbstatus` reports that PostgreSQL is disconnected, check Render logs for the first `Database initialization attempt failed` error. Do not paste the full connection URL into chat or commit it to GitHub.

## Slash command sync

- Slash commands are synced globally so the same command set is available across servers.
- `,syncslash` is an owner-only manual global sync and clears old guild-scoped copies in the server where it is run to prevent duplicate entries.
- On startup, the bot also cleans stale guild-scoped copies across servers it has joined.
