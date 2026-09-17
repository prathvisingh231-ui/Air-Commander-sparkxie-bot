import re
import discord
from discord import app_commands
import db


_NAME_RE = re.compile(r"^[a-z0-9_-]{1,32}$")


def _embed(title, description, color=None):
    e = discord.Embed(title=f"✈️ {title}", description=description, color=color or discord.Color.blurple(), timestamp=discord.utils.utcnow())
    e.set_footer(text="Air Commander • CmdMaker")
    return e


async def _ensure_table():
    if not db._pool:
        return False
    await db._pool.execute("""
        CREATE TABLE IF NOT EXISTS custom_commands(
            guild_id BIGINT NOT NULL,
            cmd_name TEXT NOT NULL,
            cmd_usage TEXT NOT NULL,
            cmd_prompt TEXT NOT NULL,
            creator_id BIGINT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY(guild_id, cmd_name)
        )
    """)
    return True


async def save_command(guild_id, name, usage, prompt, creator_id):
    if not await _ensure_table():
        return False
    await db._pool.execute(
        """INSERT INTO custom_commands(guild_id,cmd_name,cmd_usage,cmd_prompt,creator_id)
           VALUES($1,$2,$3,$4,$5)
           ON CONFLICT(guild_id,cmd_name) DO UPDATE SET
             cmd_usage=EXCLUDED.cmd_usage,
             cmd_prompt=EXCLUDED.cmd_prompt,
             creator_id=EXCLUDED.creator_id""",
        guild_id, name, usage, prompt, creator_id,
    )
    return True


async def load_rows():
    if not await _ensure_table():
        return []
    return await db._pool.fetch("SELECT guild_id,cmd_name,cmd_usage,cmd_prompt,creator_id FROM custom_commands ORDER BY created_at")


def _render_prompt(prompt, interaction, user_input=""):
    guild = interaction.guild
    values = {
        "user": interaction.user.mention,
        "username": interaction.user.display_name,
        "server": guild.name if guild else "Discord",
        "channel": interaction.channel.mention if hasattr(interaction.channel, "mention") else "this channel",
        "input": user_input or "",
    }
    try:
        return prompt.format(**values)
    except (KeyError, ValueError):
        return prompt


def _make_command(bot, guild_id, name, usage, prompt):
    async def callback(interaction: discord.Interaction, input: str = ""):
        text = _render_prompt(prompt, interaction, input)
        e = _embed(name.replace("_", " ").title(), text)
        e.add_field(name="How to use", value=usage[:1024], inline=False)
        await interaction.response.send_message(embed=e)

    return app_commands.Command(name=name, description=usage[:100] or f"Custom Air Commander command: {name}", callback=callback)


async def load_custom_commands(bot):
    rows = await load_rows()
    loaded = 0
    for row in rows:
        guild = discord.Object(id=row["guild_id"])
        name = row["cmd_name"]
        if bot.tree.get_command(name, guild=guild):
            continue
        try:
            bot.tree.add_command(_make_command(bot, row["guild_id"], name, row["cmd_usage"], row["cmd_prompt"]), guild=guild, override=True)
            loaded += 1
        except Exception as exc:
            print(f"⚠️ Could not load custom command /{name}: {type(exc).__name__}: {exc}")
    return loaded


def setup(bot):
    @bot.tree.command(name="cmdmaker", description="Create a custom server slash command")
    @app_commands.describe(
        cmdname="Command name, for example rules or welcome",
        cmd_usage="What the command is for / how users use it",
        cmd_prompt="How the command should work and what it should do",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def cmdmaker(interaction: discord.Interaction, cmdname: str, cmd_usage: str, cmd_prompt: str):
        if not interaction.guild:
            return await interaction.response.send_message("❌ CmdMaker can only be used in a server.", ephemeral=True)
        name = cmdname.strip().lower().lstrip("/")
        if not _NAME_RE.fullmatch(name):
            return await interaction.response.send_message("❌ Command name must be 1–32 characters using lowercase letters, numbers, `_` or `-`.", ephemeral=True)
        reserved = {c.name for c in bot.tree.get_commands()}
        if name in reserved:
            return await interaction.response.send_message(f"❌ `/{name}` already exists. Choose another name.", ephemeral=True)
        if not cmd_usage.strip() or not cmd_prompt.strip():
            return await interaction.response.send_message("❌ Cmd usage and cmd prompt cannot be empty.", ephemeral=True)
        if len(cmd_usage.strip()) > 100:
            return await interaction.response.send_message("❌ Cmd usage must be 100 characters or fewer.", ephemeral=True)
        if len(cmd_prompt.strip()) > 1800:
            return await interaction.response.send_message("❌ Cmd prompt must be 1800 characters or fewer.", ephemeral=True)
        if not await save_command(interaction.guild.id, name, cmd_usage.strip(), cmd_prompt.strip(), interaction.user.id):
            return await interaction.response.send_message("❌ Database is not connected, so I can't save this command yet.", ephemeral=True)

        bot.tree.add_command(_make_command(bot, interaction.guild.id, name, cmd_usage.strip(), cmd_prompt.strip()), guild=interaction.guild, override=True)
        try:
            await bot.tree.sync(guild=interaction.guild)
        except Exception as exc:
            return await interaction.response.send_message(f"❌ Saved, but Discord sync failed: `{type(exc).__name__}`.", ephemeral=True)

        e = _embed("CmdMaker • Command Created", f"Your custom command **/{name}** is ready.", discord.Color.green())
        e.add_field(name="Command", value=f"`/{name}`", inline=True)
        e.add_field(name="Usage", value=cmd_usage.strip(), inline=True)
        e.add_field(name="Prompt / Behavior", value=cmd_prompt.strip()[:1024], inline=False)
        e.add_field(name="Placeholders", value="`{user}` • `{username}` • `{server}` • `{channel}` • `{input}`", inline=False)
        e.add_field(name="Status", value="🟢 Created • Saved • Synced", inline=False)
        await interaction.response.send_message(embed=e)

    @bot.tree.error
    async def cmdmaker_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            msg = "❌ Manage Server permission is required to use CmdMaker."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)

    @bot.listen("on_ready")
    async def _load_cmdmaker_commands():
        try:
            await db.init_db()
            loaded = await load_custom_commands(bot)
            if loaded:
                for guild_id in {row["guild_id"] for row in await load_rows()}:
                    try:
                        await bot.tree.sync(guild=discord.Object(id=guild_id))
                    except Exception as exc:
                        print(f"⚠️ Custom command sync failed for {guild_id}: {type(exc).__name__}: {exc}")
            print(f"🧩 CmdMaker: loaded {loaded} saved custom command(s).")
        except Exception as exc:
            print(f"⚠️ CmdMaker startup load failed: {type(exc).__name__}: {exc}")

    bot._air_load_custom_commands = load_custom_commands
