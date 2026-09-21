"""Animated Anti-Nuke enable status UI.

This module wraps only the existing successful `/antinuke enable` response.
It does not change the security decision or permission checks; it only presents
those already-completed checks as a polished progress animation.
"""

import asyncio

import discord
from discord.interactions import InteractionResponse


_ORIGINAL_SEND_MESSAGE = InteractionResponse.send_message


async def _animated_antinuke_response(self, *args, **kwargs):
    embed = kwargs.get("embed")
    title = getattr(embed, "title", "") if embed else ""

    # Only intercept the existing successful Anti-Nuke confirmation.
    if "Anti-nuke enabled" not in title:
        return await _ORIGINAL_SEND_MESSAGE(self, *args, **kwargs)

    interaction = getattr(self, "_parent", None)
    if interaction is None:
        return await _ORIGINAL_SEND_MESSAGE(self, *args, **kwargs)

    loading = discord.Embed(
        title="🛡️ Anti-Nuke Security Check",
        description=(
            "⏳ **Bot role above administrators**\n"
            "⏳ **Required security permissions**\n"
            "⏳ **Recovery protection**\n"
            "⏳ **Audit-log access**"
        ),
        colour=discord.Colour.blurple(),
    )

    # Preserve the original response options (especially ephemeral).
    animated_kwargs = dict(kwargs)
    animated_kwargs["embed"] = loading
    animated_kwargs.pop("content", None)

    result = await _ORIGINAL_SEND_MESSAGE(self, *args, **animated_kwargs)

    stages = [
        ("Bot role above administrators", "bot role hierarchy"),
        ("Required security permissions", "required permissions"),
        ("Recovery protection", "recovery protection"),
        ("Audit-log access", "audit-log access"),
    ]

    completed = []
    for label, _ in stages:
        completed.append(label)
        remaining = [x[0] for x in stages[len(completed):]]
        lines = [f"✅ **{x}**" for x in completed]
        lines.extend(f"⏳ **{x}**" for x in remaining)

        current = discord.Embed(
            title="🛡️ Anti-Nuke Security Check",
            description="\n".join(lines),
            colour=discord.Colour.blurple(),
        )
        try:
            await interaction.edit_original_response(embed=current)
        except (discord.NotFound, discord.HTTPException):
            return result
        await asyncio.sleep(0.35)

    try:
        await interaction.edit_original_response(embed=embed)
    except (discord.NotFound, discord.HTTPException):
        pass

    return result


InteractionResponse.send_message = _animated_antinuke_response
