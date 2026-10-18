"""Secure Discord OAuth2 dashboard for Air Commander.

This module adds read-only dashboard APIs to the existing Flask app. It does not
replace bot commands or mutate feature configuration files.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

DISCORD_API = "https://discord.com/api/v10"
MANAGE_GUILD = 1 << 5
ADMINISTRATOR = 1 << 3
_SESSION_TTL = 7 * 24 * 60 * 60
_AUTH_SESSIONS: dict[str, dict] = {}


def _json_request(url: str, *, method: str = "GET", data: dict | None = None,
                  token: str | None = None) -> dict | list:
    headers = {"User-Agent": "AirCommanderDashboard/1.0", "Accept": "application/json"}
    body = None
    if data is not None:
        body = urlencode(data).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=12) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read(1024).decode("utf-8", "replace")
        raise RuntimeError(f"Discord API returned HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError("Could not reach Discord. Please retry.") from exc


def _base_url() -> str:
    configured = (os.getenv("DASHBOARD_BASE_URL") or "").strip().rstrip("/")
    if configured:
        return configured
    return request.url_root.rstrip("/")


def _redirect_uri() -> str:
    return f"{_base_url()}/oauth/callback"


def _client_id() -> str:
    return (os.getenv("DISCORD_CLIENT_ID") or "").strip()


def _oauth_ready() -> bool:
    return bool(_client_id() and os.getenv("DISCORD_CLIENT_SECRET"))


def _current_auth() -> dict | None:
    sid = session.get("air_sid")
    if not sid:
        return None
    auth = _AUTH_SESSIONS.get(sid)
    if not auth:
        return None
    if auth.get("expires_at", 0) <= time.time():
        _AUTH_SESSIONS.pop(sid, None)
        session.pop("air_sid", None)
        return None
    return auth


def _fetch_user_guilds(auth: dict) -> list[dict]:
    result = _json_request(f"{DISCORD_API}/users/@me/guilds", token=auth["access_token"])
    return result if isinstance(result, list) else []


def _managed_guilds(auth: dict) -> list[dict]:
    guilds = _fetch_user_guilds(auth)
    output = []
    for guild in guilds:
        try:
            permissions = int(guild.get("permissions", "0"))
        except (ValueError, TypeError):
            permissions = 0
        if permissions & (MANAGE_GUILD | ADMINISTRATOR):
            output.append(guild)
    return output


def _read_config(path: str, guild_id: str, *, nested_key: str | None = None) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            return {}
        if nested_key:
            value = value.get(nested_key, {})
        item = value.get(guild_id, {}) if isinstance(value, dict) else {}
        return item if isinstance(item, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _feature_status(guild_id: str) -> list[dict]:
    automode = _read_config("automode_config.json", guild_id)
    antinuke = _read_config("antinuke_config.json", guild_id)
    welcome = _read_config("welcome_config.json", guild_id)
    leveling = _read_config("airleveling_data.json", guild_id)
    youtube = _read_config("data/youtube_alerts.json", guild_id, nested_key="guilds")
    tickets = _read_config("data/tickets.json", guild_id)
    return [
        {"name": "AutoMode", "description": "Spam and link protection", "enabled": bool(automode.get("enabled", False))},
        {"name": "AntiNuke", "description": "Server damage protection", "enabled": bool(antinuke.get("enabled", False))},
        {"name": "Welcome & autorole", "description": "Join messages and role assignment", "enabled": bool(welcome.get("channel_id") or welcome.get("enabled", False))},
        {"name": "Leveling", "description": "XP and member ranks", "enabled": bool(leveling.get("enabled", False))},
        {"name": "YouTube alerts", "description": "Creator upload notifications", "enabled": bool(youtube.get("enabled", False))},
        {"name": "Tickets", "description": "Support ticket panel", "enabled": bool(tickets.get("panel", {}).get("channel_id"))},
    ]


def register_dashboard(app, bot) -> None:
    """Register dashboard routes on the already-running Flask app."""
    secret_key = (os.getenv("DASHBOARD_SECRET_KEY") or "").strip()
    if secret_key:
        app.secret_key = secret_key
    elif not app.secret_key:
        # Fallback lets local development run; set DASHBOARD_SECRET_KEY on Render
        # to keep cookie signing stable across restarts.
        app.secret_key = secrets.token_urlsafe(48)
        print("⚠️ DASHBOARD_SECRET_KEY is missing; dashboard sessions will reset on restart.", flush=True)

    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=(os.getenv("DASHBOARD_COOKIE_SECURE", "true").lower() == "true"),
        PERMANENT_SESSION_LIFETIME=_SESSION_TTL,
    )
    dashboard = Blueprint("air_dashboard", __name__)

    @dashboard.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    @dashboard.get("/dashboard")
    def dashboard_home():
        auth = _current_auth()
        csrf_token = session.setdefault("air_csrf", secrets.token_urlsafe(32))
        return render_template(
            "dashboard.html",
            user=(auth or {}).get("user"),
            oauth_ready=_oauth_ready(),
            client_id=_client_id(),
            csrf_token=csrf_token,
        )

    @dashboard.get("/login")
    def login():
        if not _oauth_ready():
            return render_template("dashboard.html", user=None, oauth_ready=False, client_id=_client_id()), 503
        state = secrets.token_urlsafe(32)
        session["air_oauth_state"] = state
        session.permanent = True
        params = {
            "client_id": _client_id(),
            "redirect_uri": _redirect_uri(),
            "response_type": "code",
            "scope": "identify guilds",
            "state": state,
            "prompt": "consent",
        }
        return redirect("https://discord.com/oauth2/authorize?" + urlencode(params))

    @dashboard.get("/oauth/callback")
    def oauth_callback():
        expected_state = session.pop("air_oauth_state", None)
        returned_state = request.args.get("state", "")
        if not expected_state or not returned_state or not secrets.compare_digest(expected_state, returned_state):
            return render_template("dashboard.html", user=None, oauth_ready=_oauth_ready(),
                                   client_id=_client_id(), error="Login verification failed. Please try again."), 400
        if request.args.get("error"):
            return redirect(url_for("air_dashboard.dashboard_home"))
        code = request.args.get("code", "")
        if not code or not _oauth_ready():
            return render_template("dashboard.html", user=None, oauth_ready=False,
                                   client_id=_client_id(), error="Discord OAuth2 is not configured correctly."), 400
        try:
            token_data = _json_request(
                f"{DISCORD_API}/oauth2/token",
                method="POST",
                data={
                    "client_id": _client_id(),
                    "client_secret": os.environ["DISCORD_CLIENT_SECRET"],
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": _redirect_uri(),
                },
            )
            access_token = token_data.get("access_token")
            if not access_token:
                raise RuntimeError("Discord did not return an access token.")
            user = _json_request(f"{DISCORD_API}/users/@me", token=access_token)
            if not isinstance(user, dict) or not user.get("id"):
                raise RuntimeError("Discord did not return a valid user profile.")
            now = time.time()
            for old_sid, old_auth in list(_AUTH_SESSIONS.items()):
                if old_auth.get("expires_at", 0) <= now:
                    _AUTH_SESSIONS.pop(old_sid, None)
            sid = secrets.token_urlsafe(32)
            _AUTH_SESSIONS[sid] = {
                "access_token": access_token,
                "user": {
                    "id": str(user["id"]),
                    "username": user.get("global_name") or user.get("username") or "Discord user",
                    "discriminator": user.get("discriminator", "0"),
                    "avatar": user.get("avatar"),
                },
                "expires_at": time.time() + min(int(token_data.get("expires_in", _SESSION_TTL)), _SESSION_TTL),
            }
            old_sid = session.get("air_sid")
            if old_sid:
                _AUTH_SESSIONS.pop(old_sid, None)
            session.clear()
            session["air_sid"] = sid
            session.permanent = True
            return redirect(url_for("air_dashboard.dashboard_home"))
        except (RuntimeError, KeyError, ValueError) as exc:
            print(f"Dashboard OAuth callback failed: {type(exc).__name__}: {exc}", flush=True)
            return render_template("dashboard.html", user=None, oauth_ready=_oauth_ready(),
                                   client_id=_client_id(), error="Discord login failed. Check OAuth settings and try again."), 502

    @dashboard.post("/logout")
    def logout():
        expected_csrf = session.get("air_csrf", "")
        supplied_csrf = request.form.get("csrf_token", "")
        if not expected_csrf or not supplied_csrf or not secrets.compare_digest(expected_csrf, supplied_csrf):
            return "Invalid CSRF token.", 400
        sid = session.pop("air_sid", None)
        if sid:
            _AUTH_SESSIONS.pop(sid, None)
        session.clear()
        return redirect(url_for("air_dashboard.dashboard_home"))

    @dashboard.get("/api/guilds")
    def api_guilds():
        auth = _current_auth()
        if not auth:
            return jsonify({"error": "login_required"}), 401
        try:
            manageable = _managed_guilds(auth)
        except RuntimeError:
            return jsonify({"error": "discord_unavailable", "message": "Could not load Discord servers. Please sign in again."}), 502
        bot_guild_ids = {str(g.id) for g in getattr(bot, "guilds", [])}
        rows = []
        for guild in manageable:
            guild_id = str(guild.get("id", ""))
            rows.append({
                "id": guild_id,
                "name": guild.get("name", "Discord server"),
                "icon": (f"https://cdn.discordapp.com/icons/{guild_id}/{guild['icon']}.png?size=96"
                         if guild.get("icon") else None),
                "bot_present": guild_id in bot_guild_ids,
            })
        rows.sort(key=lambda item: (not item["bot_present"], item["name"].lower()))
        return jsonify({"guilds": rows, "bot_ready": bool(bot.is_ready())})

    @dashboard.get("/api/guild/<guild_id>/overview")
    def api_guild_overview(guild_id: str):
        auth = _current_auth()
        if not auth:
            return jsonify({"error": "login_required"}), 401
        if not re.fullmatch(r"[0-9]{15,22}", guild_id):
            return jsonify({"error": "invalid_guild_id"}), 400
        try:
            allowed_ids = {str(g.get("id")) for g in _managed_guilds(auth)}
        except RuntimeError:
            return jsonify({"error": "discord_unavailable"}), 502
        if guild_id not in allowed_ids:
            return jsonify({"error": "forbidden"}), 403
        guild = bot.get_guild(int(guild_id))
        if guild is None:
            return jsonify({"error": "bot_not_in_guild", "message": "Invite Air Commander to this server first."}), 404
        database_connected = bool(getattr(__import__("db"), "_pool", None))
        return jsonify({
            "guild": {"id": str(guild.id), "name": guild.name, "icon": guild.icon.url if guild.icon else None},
            "bot": {"ready": bool(bot.is_ready()), "latency_ms": round(bot.latency * 1000) if bot.is_ready() else None},
            "stats": {
                "members": guild.member_count or 0,
                "text_channels": sum(1 for channel in guild.channels if getattr(channel, "type", None) and channel.type.name == "text"),
                "voice_channels": sum(1 for channel in guild.channels if getattr(channel, "type", None) and channel.type.name == "voice"),
                "roles": max(0, len(guild.roles) - 1),
                "slash_commands": len(bot.tree.get_commands()),
                "feature_modules": len(getattr(bot, "_air_loaded_feature_modules", set())),
            },
            "database": {"configured_pool": database_connected},
            "features": _feature_status(guild_id),
        })


    @dashboard.route("/api/guild/<guild_id>/config/security", methods=["GET", "POST"])
    def api_security_config(guild_id: str):
        """Manage the first dashboard config group without replacing bot commands."""
        auth = _current_auth()
        if not auth:
            return jsonify({"error": "login_required"}), 401
        if not re.fullmatch(r"[0-9]{15,22}", guild_id):
            return jsonify({"error": "invalid_guild_id"}), 400
        try:
            allowed_ids = {str(g.get("id")) for g in _managed_guilds(auth)}
        except RuntimeError:
            return jsonify({"error": "discord_unavailable"}), 502
        if guild_id not in allowed_ids:
            return jsonify({"error": "forbidden"}), 403
        guild = bot.get_guild(int(guild_id))
        if guild is None:
            return jsonify({"error": "bot_not_in_guild"}), 404

        try:
            import automation
        except Exception:
            return jsonify({"error": "security_module_unavailable"}), 503

        if request.method == "GET":
            auto = automation.get_automode_config(int(guild_id))
            anti = automation.get_antinuke_config(int(guild_id))
            links = automation.get_antilink_config(int(guild_id))
            return jsonify({
                "antilink": {
                    "enabled": bool(links.get("enabled", False)),
                    "warning_enabled": bool(links.get("warning_enabled", True)),
                    "dm_enabled": bool(links.get("dm_enabled", True)),
                    "delete_enabled": bool(links.get("delete_enabled", True)),
                    "types": {key: bool(value) for key, value in links.get("types", {}).items()},
                    "log_channel_id": links.get("log_channel_id"),
                },
                "automode": {
                    "enabled": bool(auto.get("enabled", False)),
                    "spam_messages": int(auto.get("spam_messages", 5)),
                    "spam_window": int(auto.get("spam_window", 7)),
                    "link_protection": bool(auto.get("link_protection", True)),
                    "mention_limit": int(auto.get("mention_limit", 5)),
                    "duplicate_limit": int(auto.get("duplicate_limit", 3)),
                    "log_channel_id": auto.get("log_channel_id"),
                },
                "antinuke": {
                    "enabled": bool(anti.get("enabled", False)),
                    "action": str(anti.get("action", "ban")),
                    "window": int(anti.get("window", 10)),
                    "log_channel_id": anti.get("log_channel_id"),
                    "thresholds": anti.get("thresholds", {}),
                },
            })

        expected_csrf = session.get("air_csrf", "")
        supplied_csrf = request.headers.get("X-CSRF-Token", "")
        if not expected_csrf or not supplied_csrf or not secrets.compare_digest(expected_csrf, supplied_csrf):
            return jsonify({"error": "csrf_failed"}), 400
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "invalid_json"}), 400

        def bounded_int(value, low, high):
            if isinstance(value, bool):
                raise ValueError
            result = int(value)
            if result < low or result > high:
                raise ValueError
            return result

        try:
            if "automode" in payload:
                incoming = payload["automode"]
                if not isinstance(incoming, dict):
                    raise ValueError
                cfg = automation.get_automode_config(int(guild_id))
                if "enabled" in incoming:
                    if not isinstance(incoming["enabled"], bool): raise ValueError
                    cfg["enabled"] = incoming["enabled"]
                for key, low, high in (("spam_messages", 2, 30), ("spam_window", 2, 60),
                                        ("mention_limit", 2, 30), ("duplicate_limit", 2, 15)):
                    if key in incoming: cfg[key] = bounded_int(incoming[key], low, high)
                if "link_protection" in incoming:
                    if not isinstance(incoming["link_protection"], bool): raise ValueError
                    cfg["link_protection"] = incoming["link_protection"]
                if "log_channel_id" in incoming:
                    raw = incoming["log_channel_id"]
                    if raw in ("", None):
                        cfg["log_channel_id"] = None
                    else:
                        channel_id = bounded_int(raw, 1, 10**22)
                        channel = guild.get_channel(channel_id)
                        if not isinstance(channel, __import__("discord").TextChannel): raise ValueError
                        cfg["log_channel_id"] = channel_id
                if not automation.automode_save_all():
                    return jsonify({"error": "save_failed", "message": "Could not save AutoMode settings."}), 500

            if "antilink" in payload:
                incoming = payload["antilink"]
                if not isinstance(incoming, dict):
                    raise ValueError
                cfg = automation.get_antilink_config(int(guild_id))
                for key in ("enabled", "warning_enabled", "dm_enabled", "delete_enabled"):
                    if key in incoming:
                        if not isinstance(incoming[key], bool): raise ValueError
                        cfg[key] = incoming[key]
                if "types" in incoming:
                    types = incoming["types"]
                    if not isinstance(types, dict): raise ValueError
                    allowed_types = set(cfg.get("types", {}))
                    for key, value in types.items():
                        if key not in allowed_types or not isinstance(value, bool): raise ValueError
                        cfg.setdefault("types", {})[key] = value
                if "log_channel_id" in incoming:
                    raw = incoming["log_channel_id"]
                    if raw in ("", None):
                        cfg["log_channel_id"] = None
                    else:
                        channel_id = bounded_int(raw, 1, 10**22)
                        channel = guild.get_channel(channel_id)
                        if not isinstance(channel, __import__("discord").TextChannel): raise ValueError
                        cfg["log_channel_id"] = channel_id
                if not automation.antilink_save_all():
                    return jsonify({"error": "save_failed", "message": "Could not save AntiLink settings."}), 500

            if "antinuke" in payload:
                incoming = payload["antinuke"]
                if not isinstance(incoming, dict):
                    raise ValueError
                cfg = automation.get_antinuke_config(int(guild_id))
                if "enabled" in incoming:
                    if not isinstance(incoming["enabled"], bool): raise ValueError
                    cfg["enabled"] = incoming["enabled"]
                if "action" in incoming:
                    if incoming["action"] not in {"ban", "kick", "timeout", "strip"}: raise ValueError
                    cfg["action"] = incoming["action"]
                if "window" in incoming: cfg["window"] = bounded_int(incoming["window"], 3, 60)
                if "log_channel_id" in incoming:
                    raw = incoming["log_channel_id"]
                    if raw in ("", None):
                        cfg["log_channel_id"] = None
                    else:
                        channel_id = bounded_int(raw, 1, 10**22)
                        channel = guild.get_channel(channel_id)
                        if not isinstance(channel, __import__("discord").TextChannel): raise ValueError
                        cfg["log_channel_id"] = channel_id
                if "thresholds" in incoming:
                    thresholds = incoming["thresholds"]
                    if not isinstance(thresholds, dict): raise ValueError
                    allowed = set(cfg.get("thresholds", {}))
                    for key, value in thresholds.items():
                        if key not in allowed: raise ValueError
                        cfg.setdefault("thresholds", {})[key] = bounded_int(value, 1, 20)
                if not automation.antinuke_save_all():
                    return jsonify({"error": "save_failed", "message": "Could not save AntiNuke settings."}), 500
        except (ValueError, TypeError, KeyError):
            return jsonify({"error": "invalid_config", "message": "One or more settings are invalid."}), 400

        return jsonify({"ok": True, "message": "Security settings saved."})

    @dashboard.route("/api/guild/<guild_id>/config/welcome", methods=["GET", "POST"])
    def api_welcome_config(guild_id: str):
        """Read and update welcome-message and join-role settings for one authorized guild."""
        auth = _current_auth()
        if not auth:
            return jsonify({"error": "login_required"}), 401
        if not re.fullmatch(r"[0-9]{15,22}", guild_id):
            return jsonify({"error": "invalid_guild_id"}), 400
        try:
            allowed_ids = {str(g.get("id")) for g in _managed_guilds(auth)}
        except RuntimeError:
            return jsonify({"error": "discord_unavailable"}), 502
        if guild_id not in allowed_ids:
            return jsonify({"error": "forbidden"}), 403
        guild = bot.get_guild(int(guild_id))
        if guild is None:
            return jsonify({"error": "bot_not_in_guild"}), 404

        try:
            import welcome_autorole
        except Exception:
            return jsonify({"error": "welcome_module_unavailable"}), 503

        cfg = welcome_autorole.guild_data(guild.id)
        if request.method == "GET":
            return jsonify({
                "channel_id": str(cfg.get("channel_id") or ""),
                "message": str(cfg.get("message") or ""),
                "join_role_id": str(cfg.get("join_role_id") or ""),
                "channels": [
                    {"id": str(ch.id), "name": ch.name}
                    for ch in guild.text_channels
                    if not ch.is_news()
                ],
                "roles": [
                    {"id": str(role.id), "name": role.name}
                    for role in guild.roles
                    if not role.is_default() and not role.managed
                ],
            })

        expected_csrf = session.get("air_csrf", "")
        supplied_csrf = request.headers.get("X-CSRF-Token", "")
        if not expected_csrf or not supplied_csrf or not secrets.compare_digest(expected_csrf, supplied_csrf):
            return jsonify({"error": "csrf_failed"}), 400
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "invalid_json"}), 400

        raw_channel = payload.get("channel_id", "")
        raw_role = payload.get("join_role_id", "")
        message = payload.get("message", "")
        if not isinstance(message, str) or len(message) > 2000:
            return jsonify({"error": "invalid_config", "message": "Welcome message must be 2,000 characters or fewer."}), 400
        if raw_channel in ("", None):
            channel_id = None
        else:
            try:
                channel_id = int(raw_channel)
            except (ValueError, TypeError):
                return jsonify({"error": "invalid_config", "message": "Choose a valid text channel."}), 400
            if not isinstance(guild.get_channel(channel_id), __import__("discord").TextChannel):
                return jsonify({"error": "invalid_config", "message": "The selected channel is not a text channel in this server."}), 400
        if raw_role in ("", None):
            role_id = None
        else:
            try:
                role_id = int(raw_role)
            except (ValueError, TypeError):
                return jsonify({"error": "invalid_config", "message": "Choose a valid join role."}), 400
            role = guild.get_role(role_id)
            me = guild.me
            if role is None or role.is_default() or role.managed or me is None or role >= me.top_role:
                return jsonify({"error": "invalid_config", "message": "Choose a role below Air Commander's highest role."}), 400

        cfg["channel_id"] = channel_id
        cfg["message"] = message
        cfg["join_role_id"] = role_id
        try:
            welcome_autorole.save_data(welcome_autorole.DATA)
        except (OSError, TypeError, ValueError) as exc:
            print(f"Dashboard welcome config save failed: {type(exc).__name__}: {exc}", flush=True)
            return jsonify({"error": "save_failed", "message": "Could not save welcome settings."}), 500
        return jsonify({"ok": True, "message": "Welcome and join-role settings saved."})

    @dashboard.get("/api/health")
    def api_health():
        return jsonify({"ok": True, "discord_ready": bool(bot.is_ready())})

    app.register_blueprint(dashboard)
