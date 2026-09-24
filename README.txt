AIR COMMANDER — 8 COMMAND FILE PACK

Files:
01_moderation_security.py
02_tickets.py
03_server_roles.py
04_logs_automation.py
05_ai_utility_youtube.py
06_community_games.py
07_voice_backup_applications.py
08_owner_analytics_health.py

Install:
- Upload these 8 .py files into your bot's cogs/commands folder.
- Load each file as a normal discord.py extension with:
  await bot.load_extension("cogs.01_moderation_security")
  ...etc.
- Each module creates/uses aircommander.db automatically at runtime.
- Do NOT load a second ticket cog if your existing ticket.py is already loaded, or Discord will see duplicate /ticket commands.
- The files intentionally use SQLite runtime storage rather than requiring a separate database file.

IMPORTANT:
This is a command pack. Some integrations such as real AI generation, live YouTube polling/webhooks, and long-term analytics require API credentials/background workers in the bot core. The commands are included and provide configuration/test interfaces.
