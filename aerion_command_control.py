"""
AERION server-level command control.

This module deliberately keeps command-control state in Supabase through the
injected REST helpers already used by bot1.py.  It does not create a local
database and it does not change membership tiers.

The accompanying aerion_command_control_schema.sql migration must be applied
to Supabase before the panel can persist settings.  Until then, the module
fails open for command visibility and logs a short startup warning instead of
breaking the bot.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Set

import discord


COMMAND_TABLE = "aerion_command_controls"
PANEL_TABLE = "aerion_command_panels"
AUDIT_TABLE = "aerion_command_audit"

# The control surface is button-based, so there is no admin slash command to
# protect.  Keeping this set here makes it easy to protect future commands
# that are required to recover the panel.
PROTECTED_COMMANDS: Set[str] = set()

_bot: Optional[discord.Client] = None
_supabase_get: Optional[Callable[..., Awaitable[Any]]] = None
_supabase_post: Optional[Callable[..., Awaitable[Any]]] = None
_supabase_patch: Optional[Callable[..., Awaitable[Any]]] = None
_view_registered = False
_guild_join_registered = False
_db_available: Optional[bool] = None
_sync_lock = asyncio.Lock()
_command_templates: List[Any] = []


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _command_name(command: Any) -> str:
    return str(getattr(command, "qualified_name", None) or getattr(command, "name", ""))


def _all_commands() -> List[Any]:
    if _bot is None or not hasattr(_bot, "tree"):
        return []
    return list(_bot.tree.get_commands())


def _command_names() -> List[str]:
    names = {
        _command_name(command)
        for command in _all_commands()
        if _command_name(command)
    }
    return sorted(name for name in names if name not in PROTECTED_COMMANDS)


async def _get(table: str, params: Dict[str, str]) -> Optional[List[Dict[str, Any]]]:
    global _db_available
    if _supabase_get is None:
        return None
    try:
        result = await _supabase_get(table, params)
        _db_available = True
        return result if isinstance(result, list) else []
    except Exception as exc:
        if _db_available is not False:
            print(
                f"[COMMAND CONTROL] Supabase read unavailable for {table}: "
                f"{type(exc).__name__}: {exc}"
            )
        _db_available = False
        return None


async def _post(table: str, payload: Dict[str, Any]) -> bool:
    global _db_available
    if _supabase_post is None:
        return False
    try:
        await _supabase_post(table, payload)
        _db_available = True
        return True
    except Exception as exc:
        if _db_available is not False:
            print(
                f"[COMMAND CONTROL] Supabase write unavailable for {table}: "
                f"{type(exc).__name__}: {exc}"
            )
        _db_available = False
        return False


async def _patch(table: str, params: Dict[str, str], payload: Dict[str, Any]) -> bool:
    global _db_available
    if _supabase_patch is None:
        return False
    try:
        await _supabase_patch(table, params, payload)
        _db_available = True
        return True
    except Exception as exc:
        if _db_available is not False:
            print(
                f"[COMMAND CONTROL] Supabase update unavailable for {table}: "
                f"{type(exc).__name__}: {exc}"
            )
        _db_available = False
        return False


async def _control_map(guild_id: int) -> Dict[str, bool]:
    rows = await _get(
        COMMAND_TABLE,
        {
            "guild_id": f"eq.{guild_id}",
            "select": "command_name,enabled",
        },
    )
    if rows is None:
        # Before the migration exists, keep the current bot behaviour.
        return {}
    return {
        str(row.get("command_name")): bool(row.get("enabled", True))
        for row in rows
        if row.get("command_name")
    }


async def _is_enabled(guild_id: int, command_name: str) -> bool:
    if command_name in PROTECTED_COMMANDS:
        return True
    return (await _control_map(guild_id)).get(command_name, True)


async def _record_audit(
    guild_id: int,
    command_name: str,
    action: str,
    actor_id: int,
) -> None:
    await _post(
        AUDIT_TABLE,
        {
            "guild_id": guild_id,
            "command_name": command_name,
            "action": action,
            "actor_id": str(actor_id),
            "created_at": _utc_now(),
        },
    )


async def _set_enabled(
    guild_id: int,
    command_name: str,
    enabled: bool,
    actor_id: int,
) -> bool:
    if command_name in PROTECTED_COMMANDS:
        return False

    payload = {
        "guild_id": guild_id,
        "command_name": command_name,
        "enabled": enabled,
        "updated_by": str(actor_id),
        "updated_at": _utc_now(),
    }
    existing = await _get(
        COMMAND_TABLE,
        {
            "guild_id": f"eq.{guild_id}",
            "command_name": f"eq.{command_name}",
            "select": "guild_id",
        },
    )
    if existing is None:
        return False

    if existing:
        saved = await _patch(
            COMMAND_TABLE,
            {
                "guild_id": f"eq.{guild_id}",
                "command_name": f"eq.{command_name}",
            },
            payload,
        )
    else:
        saved = await _post(COMMAND_TABLE, payload)

    if saved:
        await _record_audit(
            guild_id,
            command_name,
            "enabled" if enabled else "disabled",
            actor_id,
        )
    return saved


async def _is_admin(interaction: discord.Interaction) -> bool:
    if interaction.guild is None:
        return False
    if _bot is not None:
        try:
            if await _bot.is_owner(interaction.user):
                return True
        except Exception:
            pass
    if interaction.user.id == interaction.guild.owner_id:
        return True
    permissions = getattr(interaction.user, "guild_permissions", None)
    return bool(permissions and permissions.administrator)


async def _require_admin(interaction: discord.Interaction) -> bool:
    if await _is_admin(interaction):
        return True
    message = "❌ Sirf server owner, Administrator, ya bot owner ye panel use kar sakta hai."
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)
    return False


def _panel_embed(guild: discord.Guild, controls: Dict[str, bool]) -> discord.Embed:
    names = _command_names()
    enabled_count = sum(1 for name in names if controls.get(name, True))
    disabled_count = len(names) - enabled_count
    embed = discord.Embed(
        title="✈️ AERION Admin Control Panel",
        description=(
            "Buttons se server ke slash commands enable/disable karein.\n"
            "Membership tier control abhi is panel me included nahi hai."
        ),
        color=0x00D4FF,
    )
    embed.add_field(
        name="Command Status",
        value=(
            f"✅ Enabled: **{enabled_count}**\n"
            f"⛔ Disabled: **{disabled_count}**\n"
            f"📋 Total: **{len(names)}**"
        ),
        inline=False,
    )
    embed.add_field(
        name="How it works",
        value=(
            "Command select karein → Enable/Disable button dabayein. "
            "Disable ke baad command is server ke slash menu se remove hogi."
        ),
        inline=False,
    )
    embed.set_footer(text=f"{guild.name} • AERION server controls")
    return embed


class CommandActionView(discord.ui.View):
    def __init__(self, guild_id: int, command_name: str):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.command_name = command_name

    async def _change(self, interaction: discord.Interaction, enabled: bool) -> None:
        if not await _require_admin(interaction):
            return
        if interaction.guild is None or interaction.guild.id != self.guild_id:
            await interaction.response.send_message(
                "❌ Ye control panel kisi aur server ke liye hai.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        saved = await _set_enabled(
            self.guild_id,
            self.command_name,
            enabled,
            interaction.user.id,
        )
        if not saved:
            await interaction.followup.send(
                "⚠️ Supabase command-control table available nahi hai. "
                "Migration apply hone ke baad try karein.",
                ephemeral=True,
            )
            return

        await sync_guild_commands(interaction.guild)
        controls = await _control_map(self.guild_id)
        await _refresh_panel(interaction.guild, controls)
        status = "enabled ✅" if enabled else "disabled ⛔"
        await interaction.followup.send(
            f"`/{self.command_name}` **{status}**. Is server ka slash menu sync ho gaya.",
            ephemeral=True,
        )

    @discord.ui.button(
        label="Enable",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="aerion:command:enable",
    )
    async def enable(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._change(interaction, True)

    @discord.ui.button(
        label="Disable",
        style=discord.ButtonStyle.danger,
        emoji="⛔",
        custom_id="aerion:command:disable",
    )
    async def disable(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._change(interaction, False)


class CommandSelect(discord.ui.Select):
    def __init__(self, guild_id: int, names: Iterable[str]):
        options = [
            discord.SelectOption(
                label=f"/{name}"[:100],
                value=name,
                description="Select this command to manage",
            )
            for name in list(names)[:25]
        ]
        super().__init__(
            placeholder="Select a slash command...",
            min_values=1,
            max_values=1,
            options=options or [
                discord.SelectOption(
                    label="No commands found",
                    value="__none__",
                    description="Commands will appear after the bot syncs",
                )
            ],
            custom_id="aerion:command:select",
        )
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await _require_admin(interaction):
            return
        selected = self.values[0]
        if selected == "__none__":
            await interaction.response.send_message(
                "⚠️ Is server me manage karne ke liye command nahi mili.",
                ephemeral=True,
            )
            return
        controls = await _control_map(self.guild_id)
        enabled = controls.get(selected, True)
        status = "Enabled ✅" if enabled else "Disabled ⛔"
        embed = discord.Embed(
            title=f"Command Control: /{selected}",
            description=f"Current status: **{status}**",
            color=0x00FF88 if enabled else 0xFF4455,
        )
        embed.set_footer(text="Neeche button se status change karein")
        await interaction.response.send_message(
            embed=embed,
            view=CommandActionView(self.guild_id, selected),
            ephemeral=True,
        )


class CommandSelectView(discord.ui.View):
    def __init__(self, guild_id: int, names: Iterable[str]):
        super().__init__(timeout=300)
        self.add_item(CommandSelect(guild_id, names))


class AdminPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Command Control",
        style=discord.ButtonStyle.primary,
        emoji="⚙️",
        custom_id="aerion:admin:command_control",
    )
    async def command_control(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        if not await _require_admin(interaction):
            return
        if interaction.guild is None:
            return
        controls = await _control_map(interaction.guild.id)
        await interaction.response.send_message(
            embed=_panel_embed(interaction.guild, controls),
            view=CommandSelectView(interaction.guild.id, _command_names()),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Refresh",
        style=discord.ButtonStyle.secondary,
        emoji="🔄",
        custom_id="aerion:admin:refresh",
    )
    async def refresh(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        if not await _require_admin(interaction):
            return
        if interaction.guild is None:
            return
        controls = await _control_map(interaction.guild.id)
        await interaction.response.edit_message(
            embed=_panel_embed(interaction.guild, controls),
            view=self,
        )


async def sync_guild_commands(guild: discord.Guild) -> List[Any]:
    """
    Copy the bot's registered commands into this guild, remove disabled ones,
    and sync only this guild.  We intentionally do not perform a global sync:
    guild-scoped registration is what makes the menu change quickly.
    """
    if _bot is None or not hasattr(_bot, "tree"):
        return []
    async with _sync_lock:
        controls = await _control_map(guild.id)
        _bot.tree.clear_commands(guild=guild)
        if _command_templates:
            for command in _command_templates:
                _bot.tree.add_command(command, guild=guild, override=True)
        else:
            _bot.tree.copy_global_to(guild=guild)
        for command in list(_bot.tree.get_commands(guild=guild)):
            name = _command_name(command)
            if name in PROTECTED_COMMANDS:
                continue
            if not controls.get(name, True):
                _bot.tree.remove_command(name, guild=guild)
        try:
            synced = await _bot.tree.sync(guild=guild)
            return synced
        except Exception as exc:
            print(
                f"[COMMAND CONTROL] Guild sync failed for {guild.id}: "
                f"{type(exc).__name__}: {exc}"
            )
            return []


async def _find_panel_channel(guild: discord.Guild) -> Optional[discord.TextChannel]:
    me = guild.me
    candidates = []
    if guild.system_channel:
        candidates.append(guild.system_channel)
    candidates.extend(channel for channel in guild.text_channels if channel not in candidates)
    for channel in candidates:
        if me is None:
            return channel
        permissions = channel.permissions_for(me)
        if permissions.view_channel and permissions.send_messages and permissions.embed_links:
            return channel
    return None


async def _panel_record(guild_id: int) -> Optional[Dict[str, Any]]:
    rows = await _get(
        PANEL_TABLE,
        {
            "guild_id": f"eq.{guild_id}",
            "select": "guild_id,channel_id,message_id",
        },
    )
    if rows is None:
        return None
    return rows[0] if rows else {}


async def _save_panel(guild_id: int, channel_id: int, message_id: int) -> bool:
    record = await _panel_record(guild_id)
    payload = {
        "guild_id": guild_id,
        "channel_id": channel_id,
        "message_id": message_id,
        "updated_at": _utc_now(),
    }
    if record is None:
        return False
    if record:
        return await _patch(
            PANEL_TABLE,
            {"guild_id": f"eq.{guild_id}"},
            payload,
        )
    return await _post(PANEL_TABLE, payload)


async def _refresh_panel(
    guild: discord.Guild,
    controls: Optional[Dict[str, bool]] = None,
) -> None:
    if _db_available is False:
        return
    record = await _panel_record(guild.id)
    if record is None:
        return
    if controls is None:
        controls = await _control_map(guild.id)
    message = None
    channel_id = record.get("channel_id")
    message_id = record.get("message_id")
    if channel_id and message_id:
        channel = guild.get_channel(int(channel_id))
        if isinstance(channel, discord.TextChannel):
            try:
                message = await channel.fetch_message(int(message_id))
                await message.edit(
                    embed=_panel_embed(guild, controls),
                    view=AdminPanelView(),
                )
                return
            except Exception:
                message = None

    channel = await _find_panel_channel(guild)
    if channel is None:
        return
    try:
        message = await channel.send(
            embed=_panel_embed(guild, controls),
            view=AdminPanelView(),
        )
        await _save_panel(guild.id, channel.id, message.id)
    except Exception as exc:
        print(
            f"[COMMAND CONTROL] Could not publish panel in {guild.id}: "
            f"{type(exc).__name__}: {exc}"
        )


async def sync_all_guild_commands() -> List[Any]:
    global _command_templates
    if _bot is None:
        return []
    _command_templates = list(_bot.tree.get_commands())
    results = []
    for guild in list(getattr(_bot, "guilds", [])):
        results.extend(await sync_guild_commands(guild))
        await _refresh_panel(guild)
    # The bot historically registered these commands globally. Clear that
    # registry and sync an empty global set so stale global commands disappear
    # from Discord. Each guild now owns its filtered command set.
    _bot.tree.clear_commands()
    try:
        await _bot.tree.sync()
    except Exception as exc:
        print(
            f"[COMMAND CONTROL] Global command cleanup failed: "
            f"{type(exc).__name__}: {exc}"
        )
    return results


async def _on_guild_join(guild: discord.Guild) -> None:
    await sync_guild_commands(guild)
    await _refresh_panel(guild)


def setup_command_control(
    bot_instance: discord.Client,
    supa_get: Callable[..., Awaitable[Any]],
    supa_post: Callable[..., Awaitable[Any]],
    supa_patch: Callable[..., Awaitable[Any]],
) -> None:
    """Inject the existing bot/Supabase helpers and install the persistent view."""
    global _bot, _supabase_get, _supabase_post, _supabase_patch
    global _view_registered, _guild_join_registered

    _bot = bot_instance
    _supabase_get = supa_get
    _supabase_post = supa_post
    _supabase_patch = supa_patch

    if not _view_registered:
        _bot.add_view(AdminPanelView())
        _view_registered = True

    if not _guild_join_registered:
        _bot.add_listener(_on_guild_join, "on_guild_join")
        _guild_join_registered = True
