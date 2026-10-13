import base64
import io
import json
import os
import zipfile
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import discord
from discord import app_commands
from discord.ext import commands
import db

ROOT = Path(".").resolve()
BACKUP_DIR = Path("data/backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_FILES = 3000
OWNER_IDS = {int(v.strip()) for v in os.getenv("DISCORD_OWNER_ID", "").split(",") if v.strip().isdigit()}

async def _is_owner(bot, user):
    if user.id in OWNER_IDS:
        return True
    try:
        return await bot.is_owner(user)
    except Exception:
        return False

def _json_default(value):
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bytes):
        return {"__air_bytes_b64__": base64.b64encode(value).decode("ascii")}
    if hasattr(value, "items"):
        return dict(value)
    return str(value)

def _restore_value(value):
    if isinstance(value, dict) and set(value) == {"__air_bytes_b64__"}:
        return base64.b64decode(value["__air_bytes_b64__"])
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value

def _quote_ident(value):
    if not isinstance(value, str) or not value or not value.replace("_", "").isalnum():
        raise ValueError("Unsafe database identifier in backup.")
    return '"' + value.replace('"', '""') + '"'

def _json_files():
    excluded = {".git", ".venv", "venv", "__pycache__", "node_modules", "backups"}
    results = []
    for path in ROOT.rglob("*.json"):
        try:
            relative = path.relative_to(ROOT)
            if any(part in excluded for part in relative.parts):
                continue
            if path.is_file() and path.stat().st_size <= 20 * 1024 * 1024:
                results.append((path, relative.as_posix()))
        except (OSError, ValueError):
            continue
    return results[:MAX_FILES]

async def _database_dump():
    pool = getattr(db, "_pool", None)
    if pool is None:
        return {}, {}, "PostgreSQL disconnected; database tables were not included."
    tables = await pool.fetch("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
    table_data, primary_keys = {}, {}
    table_errors = []
    for item in tables:
        table = item["tablename"]
        try:
            rows = await pool.fetch(f"SELECT * FROM {_quote_ident(table)}")
            table_data[table] = [dict(row) for row in rows]
            pk_rows = await pool.fetch(
                """SELECT a.attname
                   FROM pg_index i
                   JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=ANY(i.indkey)
                   WHERE i.indrelid=$1::regclass AND i.indisprimary
                   ORDER BY a.attnum""", table)
            primary_keys[table] = [row["attname"] for row in pk_rows]
        except Exception as exc:
            print(f"[Backup] Could not dump table {table}: {type(exc).__name__}: {exc}", flush=True)
            table_errors.append(table)
            table_data[table] = []
            primary_keys[table] = []
    warning = ("Some tables could not be backed up: " + ", ".join(table_errors[:20])) if table_errors else None
    return table_data, primary_keys, warning

async def _build_backup():
    files = {}
    for path, relative in _json_files():
        try:
            files[relative] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
    tables, primary_keys, warning = await _database_dump()
    manifest = {
        "format": "air-commander-backup-v1",
        "created_at": discord.utils.utcnow().isoformat(),
        "database_included": bool(getattr(db, "_pool", None)),
        "database_tables": len(tables),
        "json_files": len(files),
        "warning": warning,
        "restore_mode": "merge/upsert; existing rows not present in the archive are not deleted",
    }
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))
        archive.writestr("config_json_files.json", json.dumps(files, ensure_ascii=False))
        archive.writestr("database_tables.json", json.dumps({"tables": tables, "primary_keys": primary_keys}, default=_json_default, ensure_ascii=False))
    memory.seek(0)
    return memory, manifest

async def _restore_database(payload):
    pool = getattr(db, "_pool", None)
    if payload.get("tables") and pool is None:
        raise RuntimeError("PostgreSQL is disconnected. Database restore was stopped before changing files.")
    tables = payload.get("tables", {})
    pks = payload.get("primary_keys", {})
    if not tables:
        return "No database tables were present in this archive."
    known = {row["tablename"] for row in await pool.fetch("SELECT tablename FROM pg_tables WHERE schemaname='public'")}
    pending = [name for name in tables if name in known]
    restored, skipped, failures = 0, 0, {}
    for _pass in range(3):
        still_pending = []
        before_pass = restored
        for table in pending:
            pk = pks.get(table, [])
            rows = tables.get(table, [])
            try:
                qtable = _quote_ident(table)
                columns = sorted({key for row in rows for key in row.keys()})
                if not columns:
                    continue
                qcolumns = ", ".join(_quote_ident(c) for c in columns)
                placeholders = ", ".join("$" + str(i + 1) for i in range(len(columns)))
                table_failed = False
                if pk:
                    conflict = ", ".join(_quote_ident(c) for c in pk)
                    updates = [c for c in columns if c not in pk]
                    action = "DO UPDATE SET " + ", ".join(f"{_quote_ident(c)}=EXCLUDED.{_quote_ident(c)}" for c in updates) if updates else "DO NOTHING"
                    query = f"INSERT INTO {qtable} ({qcolumns}) VALUES ({placeholders}) ON CONFLICT ({conflict}) {action}"
                    for row in rows:
                        try:
                            await pool.execute(query, *[_restore_value(row.get(column)) for column in columns])
                            restored += 1
                        except Exception as exc:
                            table_failed = True
                            failures[table] = f"{type(exc).__name__}: {exc}"[:250]
                else:
                    # Tables without a primary key are merged by exact-row matching
                    # so repeating a restore does not normally duplicate existing rows.
                    predicates = " AND ".join(f"{_quote_ident(column)} IS NOT DISTINCT FROM $" + str(len(columns) + i + 1) for i, column in enumerate(columns))
                    query = f"INSERT INTO {qtable} ({qcolumns}) SELECT {placeholders} WHERE NOT EXISTS (SELECT 1 FROM {qtable} WHERE {predicates})"
                    for row in rows:
                        try:
                            values = [_restore_value(row.get(column)) for column in columns]
                            await pool.execute(query, *(values + values))
                            restored += 1
                        except Exception as exc:
                            table_failed = True
                            failures[table] = f"{type(exc).__name__}: {exc}"[:250]
                if table_failed:
                    still_pending.append(table)
                else:
                    failures.pop(table, None)
            except Exception as exc:
                failures[table] = f"{type(exc).__name__}: {exc}"[:250]
                still_pending.append(table)
        if not still_pending or restored == before_pass:
            break
        pending = still_pending
    return f"Rows restored/merged: {restored}. Rows skipped: {skipped}. Tables with errors: {len(failures)}."

def _safe_json_path(relative):
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts or candidate.suffix.lower() != ".json":
        raise ValueError("Backup contains an unsafe configuration path.")
    if any(part in {".git", ".venv", "venv", "__pycache__", "node_modules", "backups"} for part in candidate.parts):
        raise ValueError("Backup contains a blocked path.")
    full = (ROOT / candidate).resolve()
    if ROOT != full and ROOT not in full.parents:
        raise ValueError("Backup path escapes the project folder.")
    return full

async def _restore_archive(raw_bytes):
    if len(raw_bytes) > MAX_ARCHIVE_BYTES:
        raise ValueError("Backup archive is too large (100 MB limit).")
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw_bytes))
    except Exception as exc:
        raise ValueError("This is not a valid Air Commander ZIP backup.") from exc
    names = archive.namelist()
    if sum(item.file_size for item in archive.infolist()) > MAX_ARCHIVE_BYTES:
        raise ValueError("Backup expands beyond the 100 MB safety limit.")
    if len(names) > MAX_FILES + 3:
        raise ValueError("Backup contains too many files.")
    required = {"manifest.json", "config_json_files.json", "database_tables.json"}
    if not required.issubset(names):
        raise ValueError("Required Air Commander backup metadata is missing.")
    manifest = json.loads(archive.read("manifest.json"))
    if manifest.get("format") != "air-commander-backup-v1":
        raise ValueError("Unsupported backup format.")
    configs = json.loads(archive.read("config_json_files.json"))
    db_payload = json.loads(archive.read("database_tables.json"))
    if db_payload.get("tables") and not getattr(db, "_pool", None):
        raise RuntimeError("PostgreSQL is disconnected. No restore changes were applied.")
    db_result = await _restore_database(db_payload)
    written = 0
    for relative, text in configs.items():
        target = _safe_json_path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(target.suffix + ".restore-tmp")
        temp.write_text(text, encoding="utf-8")
        temp.replace(target)
        written += 1
    return manifest, db_result, written

async def _create_response(interaction=None, ctx=None):
    memory, manifest = await _build_backup()
    stamp = discord.utils.utcnow().strftime("%Y%m%d-%H%M%S")
    path = BACKUP_DIR / f"air-commander-{stamp}.zip"
    path.write_bytes(memory.getvalue())
    note = "FULL backup" if manifest["database_included"] and not manifest.get("warning") else "PARTIAL backup — review the warning; some or all database records may be missing"
    description = f"{note}\nConfig files: {manifest['json_files']}\nDatabase tables: {manifest['database_tables']}\nArchive size: {path.stat().st_size:,} bytes"
    if manifest.get("warning"):
        description += f"\nWarning: {manifest['warning']}"
    if interaction:
        await interaction.followup.send(description, file=discord.File(path, filename=path.name), ephemeral=True)
    else:
        await ctx.send(description, file=discord.File(path, filename=path.name))

def setup(bot):
    group = app_commands.Group(name="backup", description="Owner-only Air Commander backup and restore")
    @group.command(name="create", description="Create and download a backup archive")
    async def backup_create(interaction: discord.Interaction):
        if not await _is_owner(bot, interaction.user):
            return await interaction.response.send_message("Bot owner only.", ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            await _create_response(interaction=interaction)
        except Exception as exc:
            print(f"[Backup] Create failed: {type(exc).__name__}: {exc}", flush=True)
            await interaction.followup.send(f"Backup failed: {type(exc).__name__}: {str(exc)[:500]}", ephemeral=True)

    @group.command(name="list", description="List backup archives stored on this running instance")
    async def backup_list(interaction: discord.Interaction):
        if not await _is_owner(bot, interaction.user):
            return await interaction.response.send_message("Bot owner only.", ephemeral=True)
        files = sorted(BACKUP_DIR.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)[:15]
        text = "\n".join(f"• {p.name} — {p.stat().st_size:,} bytes" for p in files)
        await interaction.response.send_message(text or "No local backups found. Save downloaded backups outside Render because local disk may reset.", ephemeral=True)

    @group.command(name="restore", description="Merge a backup archive into the current bot data")
    @app_commands.describe(backup_file="A ZIP created by /backup create", confirm="Confirm that you want to merge this backup")
    async def backup_restore(interaction: discord.Interaction, backup_file: discord.Attachment, confirm: bool):
        if not await _is_owner(bot, interaction.user):
            return await interaction.response.send_message("Bot owner only.", ephemeral=True)
        if not confirm:
            return await interaction.response.send_message("Restore cancelled. Set confirm to true to continue.", ephemeral=True)
        if not backup_file.filename.lower().endswith(".zip"):
            return await interaction.response.send_message("Please attach an Air Commander ZIP backup.", ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            manifest, db_result, written = await _restore_archive(await backup_file.read())
            await interaction.followup.send(f"Restore finished. Config files restored: {written}. {db_result}\nArchive created at: {manifest.get('created_at')}\nDatabase rows are merged/upserted; unrelated current rows are not deleted.", ephemeral=True)
        except Exception as exc:
            print(f"[Backup] Restore failed: {type(exc).__name__}: {exc}", flush=True)
            await interaction.followup.send(f"Restore failed: {type(exc).__name__}: {str(exc)[:500]}", ephemeral=True)

    @bot.group(name="backup", invoke_without_command=True)
    async def prefix_backup(ctx):
        if not await _is_owner(bot, ctx.author):
            return await ctx.send("Bot owner only.")
        await ctx.send("Owner-only commands: ,backup create | ,backup list | attach ZIP then use ,backup restore yes")

    @prefix_backup.command(name="create")
    async def prefix_backup_create(ctx):
        if not await _is_owner(bot, ctx.author):
            return await ctx.send("Bot owner only.")
        try:
            await _create_response(ctx=ctx)
        except Exception as exc:
            print(f"[Backup] Create failed: {type(exc).__name__}: {exc}", flush=True)
            await ctx.send(f"Backup failed: {type(exc).__name__}: {str(exc)[:400]}")

    @prefix_backup.command(name="list")
    async def prefix_backup_list(ctx):
        if not await _is_owner(bot, ctx.author):
            return await ctx.send("Bot owner only.")
        files = sorted(BACKUP_DIR.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)[:15]
        text = "\n".join(f"• {p.name} — {p.stat().st_size:,} bytes" for p in files)
        await ctx.send(text or "No local backups found. Save downloaded backups outside Render.")

    @prefix_backup.command(name="restore")
    async def prefix_backup_restore(ctx, confirm: str = "no"):
        if not await _is_owner(bot, ctx.author):
            return await ctx.send("Bot owner only.")
        if confirm.lower() not in {"yes", "confirm"}:
            return await ctx.send("Restore cancelled. Attach the ZIP and run ,backup restore yes.")
        if not ctx.message.attachments:
            return await ctx.send("Attach the ZIP backup to the same message: ,backup restore yes")
        attachment = ctx.message.attachments[0]
        if not attachment.filename.lower().endswith(".zip"):
            return await ctx.send("Please attach an Air Commander ZIP backup.")
        try:
            manifest, db_result, written = await _restore_archive(await attachment.read())
            await ctx.send(f"Restore finished. Config files restored: {written}. {db_result}\nArchive created at: {manifest.get('created_at')}\nCurrent rows not present in the archive are not deleted.")
        except Exception as exc:
            print(f"[Backup] Restore failed: {type(exc).__name__}: {exc}", flush=True)
            await ctx.send(f"Restore failed: {type(exc).__name__}: {str(exc)[:400]}")

    existing = bot.tree.get_command("backup")
    if existing is None:
        bot.tree.add_command(group)
    elif isinstance(existing, app_commands.Group):
        for child in group.commands:
            if existing.get_command(child.name) is None:
                existing.add_command(child)
    print("Owner-only backup system registered.", flush=True)
