"""Web integration tools for GLaDOS.

Provides:
  - open_website: Opens URLs or known aliases (YouTube, Reddit, GitHub, Portal Wiki, etc.)
  - get_weather: Retrieves real-time weather reports using wttr.in JSON API
  - wikipedia_lookup: Searches Wikipedia summaries for factual queries
"""

import json
import logging
import urllib.parse
import urllib.request
import webbrowser

from tools import register_tool

logger = logging.getLogger("local_os_agent.tools.web")

KNOWN_URL_ALIASES = {
    "youtube": "https://www.youtube.com",
    "reddit": "https://www.reddit.com",
    "github": "https://github.com",
    "google": "https://www.google.com",
    "portal wiki": "https://theportalwiki.com",
    "aperture science": "https://aperturescience.com",
    "steam": "https://store.steampowered.com",
    "chatgpt": "https://chatgpt.com",
    "claude": "https://claude.ai",
    "wikipedia": "https://www.wikipedia.org",
    "spotify": "https://open.spotify.com",
    "discord": "https://discord.com/app",
    "twitch": "https://www.twitch.tv",
    "gmail": "https://mail.google.com",
    "twitter": "https://x.com",
    "x": "https://x.com",
}


@register_tool(
    "open_website",
    description="Opens a website by URL or common alias (YouTube, Reddit, GitHub, Portal Wiki, etc.).",
)
def open_website(target: str) -> tuple[bool, str]:
    """Open a website by URL or common alias."""
    target_clean = target.strip().lower()

    if target_clean in KNOWN_URL_ALIASES:
        url = KNOWN_URL_ALIASES[target_clean]
    elif target_clean.startswith("http://") or target_clean.startswith("https://"):
        url = target.strip()
    elif "." in target_clean and " " not in target_clean:
        url = f"https://{target_clean}"
    else:
        query = urllib.parse.quote_plus(target.strip())
        url = f"https://www.google.com/search?q={query}"

    try:
        webbrowser.open(url)
        return True, f"Opened {url} in your default browser."
    except Exception as e:
        logger.error("Failed to open website '%s': %s", target, e)
        return False, f"Failed to open website: {e}"


@register_tool(
    "get_weather",
    description="Retrieves current weather conditions for a specified location or local area.",
)
def get_weather(location: str | None = None) -> tuple[bool, str]:
    """Get current weather information using wttr.in JSON API."""
    loc_part = urllib.parse.quote_plus(location.strip()) if location else ""
    url = f"https://wttr.in/{loc_part}?format=j1"

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Aperture-Science-GLaDOS-Weather-Facility/1.0"},
    )

    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))

        current = data.get("current_condition", [{}])[0]
        nearest = data.get("nearest_area", [{}])[0]

        temp_c = current.get("temp_C", "Unknown")
        temp_f = current.get("temp_F", "Unknown")
        feels_c = current.get("FeelsLikeC", "Unknown")
        weather_desc = current.get("weatherDesc", [{}])[0].get("value", "Unknown")
        humidity = current.get("humidity", "Unknown")
        wind_kmh = current.get("windspeedKmph", "Unknown")

        area_name = nearest.get("areaName", [{}])[0].get("value", location or "Local Area")
        country = nearest.get("country", [{}])[0].get("value", "")
        loc_str = f"{area_name}, {country}".strip(", ")

        summary = (
            f"External temperature in {loc_str} is {temp_c}° Celsius ({temp_f}° Fahrenheit), feels like {feels_c}°. "
            f"Conditions: {weather_desc}. Humidity is {humidity} percent, wind speed {wind_kmh} kilometers per hour."
        )
        return True, summary
    except Exception as e:
        logger.error("Failed to fetch weather: %s", e)
        return (
            False,
            "External environmental sensors are currently unreachable. Assuming hostile atmospheric conditions.",
        )


@register_tool("wikipedia_lookup", description="Looks up a concise factual summary from Wikipedia.")
def wikipedia_lookup(query: str) -> tuple[bool, str]:
    """Lookup a concise summary from Wikipedia REST API."""
    clean_query = query.strip()
    encoded = urllib.parse.quote(clean_query.replace(" ", "_"))
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Aperture-Science-GLaDOS/1.0 (contact@aperturescience.com)"},
    )

    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        extract = data.get("extract", "")
        if not extract:
            return False, f"Wikipedia has no summary regarding '{clean_query}'."

        sentences = extract.split(". ")
        short_summary = ". ".join(sentences[:2])
        if not short_summary.endswith("."):
            short_summary += "."

        return True, short_summary
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False, f"Wikipedia has no entry regarding '{clean_query}'."
        return False, f"Wikipedia query error: {e}"
    except Exception as e:
        logger.error("Wikipedia search failed: %s", e)
        return False, f"Failed to search Wikipedia: {e}"
