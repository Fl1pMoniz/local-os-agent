"""Protocol 6: Aperture Discord Dispatcher & Mobile Relay.
Enables instant sharing of 30-second game clips and PC/server notifications
directly to your personal Discord channels and mobile device.
"""

import json
import logging
import os
import pathlib
import time
import requests
from typing import Any

from config import config
from tools import register_tool
from tools.game_clipper import find_latest_clip, _get_active_window_title

logger = logging.getLogger("local_os_agent.tools.discord_relay")

DISCORD_CONFIG_FILE = config.captures_dir / "discord_config.json"


def get_discord_webhook() -> str | None:
    """Retrieves Discord Webhook URL from environment or configuration file."""
    env_hook = os.getenv("DISCORD_WEBHOOK_URL")
    if env_hook:
        return env_hook

    if DISCORD_CONFIG_FILE.exists():
        try:
            with open(DISCORD_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("webhook_url")
        except Exception:
            return None
    return None


def format_discord_card(target: str, status: str, details: str) -> str:
    """Generates ASCII Discord Dispatcher terminal card."""
    card = (
        "+====================================================================+\n"
        "|   APERTURE SCIENCE DISCORD RELAY - MOBILE DISPATCH STATUS          |\n"
        f"| [● RELAY ACTIVE] Channel: {target[:16]:<16} Status: {status:<18} |\n"
        "+====================================================================+\n"
        f"| Destination       : {target[:46]:<46} |\n"
        f"| Delivery Status   : {status[:46]:<46} |\n"
        f"| Transmit Summary  : {details[:46]:<46} |\n"
        "+--------------------------------------------------------------------+\n"
    )
    return card


@register_tool
def set_discord_webhook(webhook_url: str) -> dict[str, Any]:
    """
    Configures and persists your personal Discord Webhook URL for clip sharing
    and mobile notifications from GLaDOS.
    """
    if not webhook_url or not webhook_url.startswith("http"):
        return {
            "success": False,
            "message": "Invalid webhook URL. Please provide a valid Discord webhook URL starting with https://discord.com/api/webhooks/..."
        }

    config.captures_dir.mkdir(parents=True, exist_ok=True)
    with open(DISCORD_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({"webhook_url": webhook_url.strip(), "updated_at": time.time()}, f, indent=2)

    return {
        "success": True,
        "message": "Discord Webhook configured successfully. GLaDOS mobile relay online."
    }


@register_tool
def send_clip_to_discord(clip_path: str | None = None, caption: str | None = None) -> dict[str, Any]:
    """
    Uploads the latest 30-second gameplay highlight to your Discord channel.
    If no path is specified, automatically locates the newest video highlight.
    """
    hook_url = get_discord_webhook()
    if not hook_url:
        return {
            "success": False,
            "message": (
                "Discord Webhook not configured. Please use 'set_discord_webhook <url>' "
                "or set DISCORD_WEBHOOK_URL to enable automated clip sharing."
            )
        }

    target_file = pathlib.Path(clip_path) if clip_path else find_latest_clip(max_age_seconds=600)
    if not target_file or not target_file.exists():
        # Fallback to any recent clip in the last 24 hours
        target_file = find_latest_clip(max_age_seconds=86400)

    if not target_file or not target_file.exists():
        return {
            "success": False,
            "message": "No recent game highlight found in captures directory to share."
        }

    game_name = _get_active_window_title()
    file_size_mb = target_file.stat().st_size / (1024 * 1024)

    # Discord standard webhook limit is 25MB
    if file_size_mb > 25.0:
        return {
            "success": False,
            "message": f"Clip file size ({file_size_mb:.1f} MB) exceeds Discord 25MB attachment limit."
        }

    message_content = caption or f"**[Aperture Science Replay Archive]** Test highlight captured for `{game_name}`:"

    try:
        with open(target_file, "rb") as f:
            files = {"file": (target_file.name, f, "video/mp4")}
            payload = {
                "content": message_content,
                "username": "GLaDOS Replay Relay",
            }
            resp = requests.post(hook_url, data=payload, files=files, timeout=60)

        if resp.status_code in (200, 204):
            card = format_discord_card(
                target="Discord Server",
                status="Dispatched Successfully",
                details=f"Shared '{target_file.name}' ({file_size_mb:.1f} MB)"
            )
            return {
                "success": True,
                "file": target_file.name,
                "file_size_mb": round(file_size_mb, 1),
                "terminal_card": card,
                "message": f"Successfully uploaded highlight '{target_file.name}' ({file_size_mb:.1f} MB) to Discord."
            }
        else:
            return {
                "success": False,
                "message": f"Discord returned HTTP {resp.status_code}: {resp.text[:100]}"
            }
    except Exception as e:
        logger.error(f"Failed to post clip to Discord: {e}")
        return {
            "success": False,
            "message": f"Network exception dispatching clip to Discord: {e}"
        }


@register_tool
def send_discord_alert(title: str, message: str) -> dict[str, Any]:
    """Sends a text or status alert directly to your Discord channel."""
    hook_url = get_discord_webhook()
    if not hook_url:
        return {
            "success": False,
            "message": "Discord Webhook not configured. Use 'set_discord_webhook <url>' first."
        }

    payload = {
        "username": "GLaDOS Administrator",
        "embeds": [{
            "title": title,
            "description": message,
            "color": 39372,  # Aperture Blue
            "footer": {"text": "Aperture Science Enrichment Center"}
        }]
    }
    try:
        resp = requests.post(hook_url, json=payload, timeout=5)
        success = resp.status_code in (200, 204)
        return {
            "success": success,
            "message": "Discord notification dispatched." if success else f"HTTP {resp.status_code}"
        }
    except Exception as e:
        return {"success": False, "message": str(e)}

