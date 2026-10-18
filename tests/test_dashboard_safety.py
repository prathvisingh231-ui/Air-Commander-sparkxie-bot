"""Focused safety tests for guild backups and command-role policies.

These tests use fake PostgreSQL storage and never connect to a live Discord server
or database. They are intentionally safe to run in GitHub Actions.
"""
import io
import json
import unittest
import zipfile
from unittest.mock import patch

import backup_system
import command_permissions


def make_archive(guild_id, configs=None, tables=None):
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps({
            "format": "air-commander-guild-backup-v2",
            "guild_id": guild_id,
        }))
        archive.writestr("guild_json_fragments.json", json.dumps(configs or {}))
        archive.writestr("database_tables.json", json.dumps(tables or {"tables": {}, "primary_keys": {}}))
    return memory.getvalue()


class FakePool:
    def __init__(self):
        self.saved = {}
        self.executed = []

    async def execute(self, query, *args):
        self.executed.append((query, args))
        if "INSERT INTO air_guild_backups" in query:
            self.saved[(int(args[0]), str(args[1]))] = bytes(args[2])
        elif "DELETE FROM air_guild_backups" in query:
            pass
        return "OK"

    async def fetch(self, query, *args):
        guild_id = int(args[0])
        return [
            {"backup_id": backup_id, "size_bytes": len(raw), "created_at": None}
            for (stored_guild, backup_id), raw in self.saved.items()
            if stored_guild == guild_id
        ]

    async def fetchval(self, query, *args):
        return self.saved.get((int(args[0]), str(args[1])))


class BackupSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_persistent_archive_is_guild_scoped_and_round_trips(self):
        pool = FakePool()
        raw = b"sample-zip-bytes"
        with patch.object(backup_system.db, "_pool", pool):
            self.assertTrue(await backup_system._store_backup(123456789012345, "AC-123456789012345-20261018-120000-A1B2", raw))
            self.assertEqual(await backup_system._read_backup(123456789012345, "AC-123456789012345-20261018-120000-A1B2"), raw)
            self.assertIsNone(await backup_system._read_backup(999999999999999, "AC-123456789012345-20261018-120000-A1B2"))
            listed = await backup_system._stored_backups(123456789012345)
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0]["size_bytes"], len(raw))

    async def test_restore_rejects_backup_from_another_guild(self):
        raw = make_archive(222222222222222, tables={"tables": {}, "primary_keys": {}})
        with self.assertRaisesRegex(PermissionError, "Cross-server restore is blocked"):
            await backup_system._restore_archive(raw, 111111111111111)

    async def test_restore_rejects_path_traversal_before_writing(self):
        raw = make_archive(
            111111111111111,
            configs={"../outside.json": [{"path": ["111111111111111"], "value": {"unsafe": True}}]},
            tables={"tables": {}, "primary_keys": {}},
        )
        with self.assertRaisesRegex(ValueError, "Unsafe config path"):
            await backup_system._restore_archive(raw, 111111111111111)

    async def test_restore_rejects_non_zip_data(self):
        with self.assertRaisesRegex(ValueError, "Invalid ZIP backup"):
            await backup_system._restore_archive(b"not a zip", 111111111111111)

    def test_backup_id_requires_guild_and_expected_shape(self):
        self.assertRegex("AC-123456789012345-20261018-120000-A1B2", backup_system.BACKUP_ID_RE)
        self.assertIsNone(backup_system.BACKUP_ID_RE.fullmatch("AC-999-20261018-120000-A1B2"))
        self.assertIsNone(backup_system.BACKUP_ID_RE.fullmatch("../AC-123456789012345-20261018-120000-A1B2"))

    def test_database_identifier_rejects_sql_injection(self):
        self.assertEqual(backup_system._qid("guild_settings"), '"guild_settings"')
        with self.assertRaises(ValueError):
            backup_system._qid('guild_settings; DROP TABLE users')

    def test_command_permission_policy_and_admin_bypass(self):
        original = command_permissions.DATA
        try:
            command_permissions.DATA = {
                "123": {"commands": {"moderation kick": {"enabled": True, "role_ids": ["456"]}}}
            }
            self.assertEqual(command_permissions._policy(123, "moderation kick"), {456})
            self.assertIsNone(command_permissions._policy(123, "unrestricted"))
            member = type("Member", (), {
                "roles": [type("Role", (), {"id": 789})()],
                "guild_permissions": type("Permissions", (), {"administrator": False, "manage_guild": False})(),
            })()
            self.assertFalse(command_permissions._allowed(member, 123, "moderation kick"))
            member.roles.append(type("Role", (), {"id": 456})())
            self.assertTrue(command_permissions._allowed(member, 123, "moderation kick"))
            member.roles = []
            member.guild_permissions.administrator = True
            self.assertTrue(command_permissions._allowed(member, 123, "moderation kick"))
        finally:
            command_permissions.DATA = original


    def test_parent_and_subcommand_policies_are_both_enforced(self):
        original = command_permissions.DATA
        try:
            command_permissions.DATA = {
                "123": {"commands": {
                    "ai": {"enabled": True, "role_ids": ["456"]},
                    "ai chat": {"enabled": True, "role_ids": ["789"]},
                }}
            }
            member = type("Member", (), {
                "roles": [type("Role", (), {"id": 789})()],
                "guild_permissions": type("Permissions", (), {"administrator": False, "manage_guild": False})(),
            })()
            # Having the subcommand role must not bypass the parent-group policy.
            self.assertFalse(command_permissions._all_policies_allow(member, 123, ["ai chat", "ai", "chat"]))
            member.roles.append(type("Role", (), {"id": 456})())
            self.assertTrue(command_permissions._all_policies_allow(member, 123, ["ai chat", "ai", "chat"]))
        finally:
            command_permissions.DATA = original

if __name__ == "__main__":
    unittest.main()
