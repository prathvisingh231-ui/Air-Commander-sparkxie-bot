"""Dashboard intentionally disabled: Air Commander is bot-only now."""

from flask import Flask


def register_dashboard(app: Flask, bot) -> None:
    """Keep the legacy import compatible while exposing no dashboard or OAuth APIs."""

    @app.get("/dashboard")
    def dashboard_disabled():
        return (
            "Air Commander Discord bot is running. The web dashboard has been disabled.",
            200,
            {"Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store"},
        )
