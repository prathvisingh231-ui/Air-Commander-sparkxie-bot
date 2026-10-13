import io
import json
import re
import secrets
import zipfile
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import discord
from discord import app_commands
from discord.ext import commands
import db

BACKUP_DIR = Path("data/backups")
MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
BACKUP_ID_RE = re.compile(r"^AC-(\d{5,25})-(\d{8}-\d{6})-([A-F0-9]{4})$")
EXCLUDED = {".git", ".venv", "venv", "__pycache__", "node_modules", "backups"}

def _qid(name):
    if not isinstance(name, str) or not name or not name.replace("_", "").isalnum():
        raise ValueError("Unsafe SQL identifier")
    return '"' + name.replace('"', '""') + '"'

def _json_default(v):
    if isinstance(v, (datetime, date, time)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, UUID):
        return str(v)
    if isinstance(v, bytes):
        return {"__air_bytes_hex__": v.hex()}
    if hasattr(v, "items"):
        return dict(v)
    return str(v)

def _restore_value(v):
    if isinstance(v, dict) and set(v) == {"__air_bytes_hex__"}:
        return bytes.fromhex(v["__air_bytes_hex__"])
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return v

def _guild_folder(guild_id):
    path = BACKUP_DIR / str(int(guild_id))
    path.mkdir(parents=True, exist_ok=True)
    return path

def _make_id(guild_id):
    return f"AC-{guild_id}-{discord.utils.utcnow().strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(2).upper()}"

def _find_fragments(value, guild_id, path=()):
    """Only extract JSON branches explicitly keyed by this guild ID."""
    key = str(guild_id)
    found = []
    if isinstance(value, dict):
        if key in value and isinstance(value[key], (dict, list)):
            found.append({"path": list(path + (key,)), "value": value[key]})
        for k, child in value.items():
            if k != key:
                found.extend(_find_fragments(child, guild_id, path + (k,)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_find_fragments(child, guild_id, path + (index,)))
    return found

def _get_json_fragments(guild_id):
    results = {}
    root = Path(".").resolve()
    for path in root.rglob("*.json"):
        try:
            rel = path.relative_to(root)
            if any(part in EXCLUDED for part in rel.parts) or not path.is_file() or path.stat().st_size > 20 * 1024 * 1024:
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            fragments = _find_fragments(data, guild_id)
            if fragments:
                results[rel.as_posix()] = fragments
        except (OSError, UnicodeError, ValueError, TypeError):
            continue
    return results

async def _dump_guild_db(guild_id):
    pool = getattr(db, "_pool", None)
    if pool is None:
        return {}, {}, "PostgreSQL is disconnected; database rows were not included."
    rows = await pool.fetch(
        """SELECT c.table_name, c.column_name
           FROM information_schema.columns c
           JOIN information_schema.tables t ON t.table_name=c.table_name
           WHERE c.table_schema='public' AND t.table_type='BASE TABLE'
           ORDER BY c.table_name, c.ordinal_position"""
    )
    cols = {}
    for row in rows:
        cols.setdefault(row["table_name"], []).append(row["column_name"])
    data, pks, skipped = {}, {}, []
    for table, columns in cols.items():
        scope = "guild_id" if "guild_id" in columns else ("server_id" if "server_id" in columns else None)
        if not scope:
            skipped.append(table)
            continue
        try:
            table_rows = await pool.fetch(
                f"SELECT * FROM {_qid(table)} WHERE {_qid(scope)}=$1",
                int(guild_id),
            )
            data[table] = [dict(row) for row in table_rows]
            pk_rows = await pool.fetch(
                """SELECT a.attname
                   FROM pg_index i JOIN pg_attribute a
                   ON a.attrelid=i.indrelid AND a.attnum=ANY(i.indkey)
                   WHERE i.indrelid=$1::regclass AND i.indisprimary
                   ORDER BY array_position(i.indkey, a.attnum)""",
                table,
            )
            pks[table] = [row["attname"] for row in pk_rows]
        except Exception as exc:
            print(f"[Backup] Failed to read guild-scoped table {table}: {type(exc).__name__}: {exc}", flush=True)
            data.pop(table, None)
            pks.pop(table, None)
            skipped.append(table)
    warning = ("Skipped tables without guild scope or with read errors: " + ", ".join(skipped[:25])) if skipped else None
    return data, pks, warning

async def _build_backup(guild):
    configs = _get_json_fragments(guild.id)
    tables, pks, warning = await _dump_guild_db(guild.id)
    manifest = {
        "format": "air-commander-guild-backup-v2",
        "guild_id": guild.id,
        "guild_name": guild.name,
        "created_at": discord.utils.utcnow().isoformat(),
        "database_included": bool(getattr(db, "_pool", None)),
        "database_tables": len(tables),
        "json_files_with_guild_data": len(configs),
        "warning": warning,
        "scope": "Only data explicitly associated with this guild ID.",
        "restore_mode": "Merge/upsert scoped rows; unrelated guild data is never intentionally changed or deleted.",
    }
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.writestr("manifest.json", json.dumps(manifest, indent=2))
        z.writestr("guild_json_fragments.json", json.dumps(configs, ensure_ascii=False))
        z.writestr("database_tables.json", json.dumps({"tables": tables, "primary_keys": pks}, default=_json_default, ensure_ascii=False))
    memory.seek(0)
    return memory, manifest

def _set_fragment(root, path, value):
    if not path:
        return False
    current = root
    for idx, part in enumerate(path[:-1]):
        nxt = path[idx + 1]
        if isinstance(current, dict) and isinstance(part, str):
            if part not in current or not isinstance(current[part], (dict, list)):
                current[part] = {} if isinstance(nxt, str) else []
            current = current[part]
        elif isinstance(current, list) and isinstance(part, int):
            while len(current) <= part:
                current.append({} if isinstance(nxt, str) else [])
            current = current[part]
        else:
            return False
    last = path[-1]
    if isinstance(current, dict) and isinstance(last, str):
        current[last] = value
        return True
    if isinstance(current, list) and isinstance(last, int):
        while len(current) < last:
            current.append(None)
        if last == len(current):
            current.append(value)
        else:
            current[last] = value
        return True
    return False

async def _restore_db(payload, guild_id):
    pool = getattr(db, "_pool", None)
    tables = payload.get("tables", {})
    if tables and pool is None:
        raise RuntimeError("PostgreSQL is disconnected. Restore stopped before modifying config files.")
    if not tables:
        return "No database rows were included."
    col_rows = await pool.fetch(
        """SELECT c.table_name, c.column_name
           FROM information_schema.columns c
           JOIN information_schema.tables t ON t.table_name=c.table_name
           WHERE c.table_schema='public' AND t.table_type='BASE TABLE'"""
    )
    available = {}
    for row in col_rows:
        available.setdefault(row["table_name"], set()).add(row["column_name"])
    restored, errors = 0, []
    for table, table_rows in tables.items():
        if table not in available:
            errors.append(table + " (table missing)")
            continue
        scope = "guild_id" if "guild_id" in available[table] else ("server_id" if "server_id" in available[table] else None)
        if not scope:
            errors.append(table + " (not guild-scoped)")
            continue
        for row in table_rows:
            if int(row.get(scope, -1) or -1) != int(guild_id):
                raise ValueError("Backup contains another server's database row; restore blocked.")
            columns = sorted(row.keys())
            if not columns:
                continue
            qtable = _qid(table)
            qcols = ", ".join(_qid(c) for c in columns)
            placeholders = ", ".join("$" + str(i + 1) for i in range(len(columns)))
            vals = [_restore_value(row.get(c)) for c in columns]
            pk = payload.get("primary_keys", {}).get(table, [])
            if pk and all(k in columns for k in pk):
                conflict = ", ".join(_qid(k) for k in pk)
                updates = [c for c in columns if c not in pk]
                action = "DO UPDATE SET " + ", ".join(f"{_qid(c)}=EXCLUDED.{_qid(c)}" for c in updates) if updates else "DO NOTHING"
                query = f"INSERT INTO {qtable} ({qcols}) VALUES ({placeholders}) ON CONFLICT ({conflict}) {action}"
            else:
                predicates = " AND ".join(f"{_qid(c)} IS NOT DISTINCT FROM $" + str(len(columns) + i + 1) for i, c in enumerate(columns))
                query = f"INSERT INTO {qtable} ({qcols}) SELECT {placeholders} WHERE NOT EXISTS (SELECT 1 FROM {qtable} WHERE {predicates})"
                vals += vals
            try:
                await pool.execute(query, *vals)
                restored += 1
            except Exception as exc:
                errors.append(f"{table}: {type(exc).__name__}")
                print(f"[Backup] Restore failed in {table}: {type(exc).__name__}: {exc}", flush=True)
    return f"Rows merged: {restored}; errors: {len(errors)}" + (f" ({', '.join(errors[:8])})" if errors else "")

async def _restore_archive(raw, guild_id):
    if len(raw) > MAX_ARCHIVE_BYTES:
        raise ValueError("Backup exceeds the 100 MB limit.")
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
    except Exception as exc:
        raise ValueError("Invalid ZIP backup.") from exc
    if sum(x.file_size for x in z.infolist()) > MAX_ARCHIVE_BYTES or len(z.namelist()) > 3003:
        raise ValueError("Backup exceeds safety limits.")
    required = {"manifest.json", "guild_json_fragments.json", "database_tables.json"}
    if not required.issubset(z.namelist()):
        raise ValueError("Backup metadata is missing.")
    manifest = json.loads(z.read("manifest.json"))
    if manifest.get("format") != "air-commander-guild-backup-v2":
        raise ValueError("This is not a guild-scoped backup.")
    if int(manifest.get("guild_id", 0)) != int(guild_id):
        raise PermissionError("Cross-server restore is blocked; this backup belongs to another server.")
    configs = json.loads(z.read("guild_json_fragments.json"))
    db_payload = json.loads(z.read("database_tables.json"))
    if db_payload.get("tables") and not getattr(db, "_pool", None):
        raise RuntimeError("PostgreSQL is disconnected. No restore changes were applied.")
    db_result = await _restore_db(db_payload, guild_id)
    written = 0
    root_dir = Path(".").resolve()
    for relative, fragments in configs.items():
        rel = Path(relative)
        if rel.is_absolute() or ".." in rel.parts or rel.suffix.lower() != ".json" or any(p in EXCLUDED for p in rel.parts):
            raise ValueError("Unsafe config path in backup.")
        target = (root_dir / rel).resolve()
        if target != root_dir and root_dir not in target.parents:
            raise ValueError("Config path escapes the project.")
        if target.exists():
            current = json.loads(target.read_text(encoding="utf-8"))
        else:
            current = {}
        for fragment in fragments:
            path = fragment.get("path", [])
            if str(guild_id) not in [str(part) for part in path]:
                raise ValueError("Config fragment does not match this guild.")
            if not _set_fragment(current, path, fragment.get("value")):
                raise ValueError("Could not safely merge a guild config fragment.")
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(target.suffix + ".restore-tmp")
        temp.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(target)
        written += 1
    return manifest, db_result, written

def _local_backups(guild_id):
    folder = _guild_folder(guild_id)
    return sorted(
        [p for p in folder.glob("*.zip") if BACKUP_ID_RE.fullmatch(p.stem) and p.stem.split("-")[1] == str(guild_id)],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

def _prune(guild_id, keep=10):
    for path in _local_backups(guild_id)[keep:]:
        try:
            path.unlink()
        except OSError as exc:
            print(f"[Backup] Could not remove old backup {path.name}: {exc}", flush=True)

def _admin(member):
    return bool(getattr(member, "guild_permissions", None) and member.guild_permissions.manage_guild)

def _server_owner(guild, user):
    return bool(guild and user and guild.owner_id == user.id)

async def _send_create(guild, interaction=None, ctx=None):
    memory, manifest = await _build_backup(guild)
    backup_id = _make_id(guild.id)
    path = _guild_folder(guild.id) / (backup_id + ".zip")
    path.write_bytes(memory.getvalue())
    _prune(guild.id)
    complete = manifest["database_included"] and not manifest.get("warning")
    status = "COMPLETE" if complete else "PARTIAL — read warning"
    msg = (
        f"Backup ID: {backup_id}\nServer: {guild.name} ({guild.id})\nStatus: {status}\n"
        f"Guild-scoped JSON files: {manifest['json_files_with_guild_data']}\n"
        f"Database tables: {manifest['database_tables']}\nArchive size: {path.stat().st_size:,} bytes\n"
        "Use /backup list to see IDs. Only this server's owner can restore."
    )
    if manifest.get("warning"):
        msg += "\nWarning: " + manifest["warning"][:900]
    if interaction:
        await interaction.followup.send(msg, file=discord.File(path, filename=path.name), ephemeral=True)
    else:
        await ctx.send(msg, file=discord.File(path, filename=path.name))

def setup(bot):
    group = app_commands.Group(name="backup", description="Guild-scoped backup tools")
    @group.command(name="create", description="Create a backup ID (Manage Server required)")
    async def slash_create(interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if not _admin(interaction.user):
            return await interaction.response.send_message("Manage Server permission required.", ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            await _send_create(interaction.guild, interaction=interaction)
        except Exception as exc:
            print(f"[Backup] Create failed: {type(exc).__name__}: {exc}", flush=True)
            await interaction.followup.send(f"Backup failed: {type(exc).__name__}: {str(exc)[:350]}", ephemeral=True)

    @group.command(name="list", description="List backup IDs for this server (Manage Server required)")
    async def slash_list(interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if not _admin(interaction.user):
            return await interaction.response.send_message("Manage Server permission required.", ephemeral=True)
        files = _local_backups(interaction.guild.id)[:15]
        lines = [f"{p.stem} — {p.stat().st_size:,} bytes" for p in files]
        await interaction.response.send_message("\n".join(lines) if lines else "No backups found on this running instance. Render local files can reset after redeploy.", ephemeral=True)

    @group.command(name="restore", description="Restore a backup ID (server owner only)")
    @app_commands.describe(backup_id="Backup ID from /backup list for this server")
    async def slash_restore(interaction: discord.Interaction, backup_id: str):
        if not interaction.guild:
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if not _server_owner(interaction.guild, interaction.user):
            return await interaction.response.send_message("Only this server's actual owner can restore backups.", ephemeral=True)
        if not BACKUP_ID_RE.fullmatch(backup_id) or backup_id.split("-")[1] != str(interaction.guild.id):
            return await interaction.response.send_message("Invalid backup ID or it belongs to another server.", ephemeral=True)
        path = _guild_folder(interaction.guild.id) / (backup_id + ".zip")
        if not path.is_file():
            return await interaction.response.send_message("Backup ID not found on this instance. Render local storage may reset after redeploy.", ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            manifest, result, count = await _restore_archive(path.read_bytes(), interaction.guild.id)
            await interaction.followup.send(f"Restore finished for {interaction.guild.name}. Config files: {count}. {result}\nCreated at: {manifest.get('created_at')}", ephemeral=True)
        except Exception as exc:
            print(f"[Backup] Restore failed for guild {interaction.guild.id}: {type(exc).__name__}: {exc}", flush=True)
            await interaction.followup.send(f"Restore failed: {type(exc).__name__}: {str(exc)[:350]}", ephemeral=True)

    @bot.group(name="backup", invoke_without_command=True)
    @commands.guild_only()
    async def prefix_backup(ctx):
        if not _admin(ctx.author):
            return await ctx.send("Manage Server required for create/list. Restore is server-owner only.")
        await ctx.send("Commands: ,backup create | ,backup list | ,backup restore <BACKUP_ID> (server owner only)")

    @prefix_backup.command(name="create")
    @commands.guild_only()
    async def prefix_create(ctx):
        if not _admin(ctx.author):
            return await ctx.send("Manage Server permission required.")
        try:
            await _send_create(ctx.guild, ctx=ctx)
        except Exception as exc:
            print(f"[Backup] Create failed: {type(exc).__name__}: {exc}", flush=True)
            await ctx.send(f"Backup failed: {type(exc).__name__}: {str(exc)[:350]}")

    @prefix_backup.command(name="list")
    @commands.guild_only()
    async def prefix_list(ctx):
        if not _admin(ctx.author):
            return await ctx.send("Manage Server permission required.")
        files = _local_backups(ctx.guild.id)[:15]
        lines = [f"{p.stem} — {p.stat().st_size:,} bytes" for p in files]
        await ctx.send("\n".join(lines) if lines else "No backups found on this running instance. Keep downloaded copies outside Render.")

    @prefix_backup.command(name="restore")
    @commands.guild_only()
    async def prefix_restore(ctx, backup_id: str):
        if not _server_owner(ctx.guild, ctx.author):
            return await ctx.send("Only this server's actual owner can restore backups.")
        if not BACKUP_ID_RE.fullmatch(backup_id) or backup_id.split("-")[1] != str(ctx.guild.id):
            return await ctx.send("Invalid backup ID or it belongs to another server.")
        path = _guild_folder(ctx.guild.id) / (backup_id + ".zip")
        if not path.is_file():
            return await ctx.send("Backup ID not found on this instance. Render local storage may reset after redeploy.")
        try:
            manifest, result, count = await _restore_archive(path.read_bytes(), ctx.guild.id)
            await ctx.send(f"Restore finished for {ctx.guild.name}. Config files: {count}. {result}\nCreated at: {manifest.get('created_at')}")
        except Exception as exc:
            print(f"[Backup] Restore failed for guild {ctx.guild.id}: {type(exc).__name__}: {exc}", flush=True)
            await ctx.send(f"Restore failed: {type(exc).__name__}: {str(exc)[:350]}")

    existing = bot.tree.get_command("backup")
    if existing is None:
        bot.tree.add_command(group)
    elif isinstance(existing, app_commands.Group):
        for child in group.commands:
            if existing.get_command(child.name) is None:
                existing.add_command(child)
    print("Guild backup registered: admins create/list; only each server owner can restore.", flush=True)
