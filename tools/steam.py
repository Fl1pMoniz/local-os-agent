"""Dynamic Steam library discovery and game launcher toolset."""

import difflib
import logging
import os
import platform
from pathlib import Path
from typing import Any, Tuple
import webbrowser

from config import config

logger = logging.getLogger("local_os_agent.tools.steam")


def _find_steam_root() -> Path | None:
    """Locate the Steam installation directory on the host."""
    if config.custom_steam_path:
        p = Path(config.custom_steam_path)
        if p.exists():
            return p

    if platform.system() == "Windows":
        import winreg

        registry_keys = [
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
        ]

        for hkey, subkey, valname in registry_keys:
            try:
                with winreg.OpenKey(hkey, subkey) as key:
                    val, _ = winreg.QueryValueEx(key, valname)
                    if val and Path(val).exists():
                        return Path(val)
            except (OSError, FileNotFoundError):
                continue

        # Common default paths
        default_paths = [
            Path(r"C:\Program Files (x86)\Steam"),
            Path(r"C:\Program Files\Steam"),
            Path(r"D:\Steam"),
            Path(r"E:\Steam"),
        ]
        for p in default_paths:
            if p.exists():
                return p

    elif platform.system() == "Linux":
        linux_paths = [
            Path.home() / ".local/share/Steam",
            Path.home() / ".steam/steam",
        ]
        for p in linux_paths:
            if p.exists():
                return p

    elif platform.system() == "Darwin":
        mac_path = Path.home() / "Library/Application Support/Steam"
        if mac_path.exists():
            return mac_path

    return None


def _parse_vdf_file(filepath: Path) -> dict[str, Any]:
    """
    Parse a Valve Data Format (VDF/ACF) file using the dedicated `vdf` library
    with a lightweight fallback parser if vdf is not present.
    """
    try:
        import vdf
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            return vdf.load(f)
    except ImportError:
        logger.warning("Dedicated 'vdf' package not found; using internal fallback parser.")
        return _fallback_vdf_parse(filepath)
    except Exception as e:
        logger.warning(f"Error parsing VDF with dedicated parser: {e}. Trying fallback.")
        return _fallback_vdf_parse(filepath)


def _fallback_vdf_parse(filepath: Path) -> dict[str, Any]:
    """Minimal nested dictionary parser for simple VDF/ACF structures."""
    result: dict[str, Any] = {}
    stack: list[dict[str, Any]] = [result]

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            if line == "{":
                continue
            if line == "}":
                if len(stack) > 1:
                    stack.pop()
                continue

            # Check for Key-Value pair
            parts = [p.strip('"') for p in line.split('"\t"') if p.strip()]
            if len(parts) == 1:
                # Quoted string alone or separated by whitespace
                import re
                tokens = re.findall(r'"([^"]*)"', line)
                if len(tokens) == 2:
                    stack[-1][tokens[0]] = tokens[1]
                elif len(tokens) == 1:
                    new_dict: dict[str, Any] = {}
                    stack[-1][tokens[0]] = new_dict
                    stack.append(new_dict)
            elif len(parts) >= 2:
                stack[-1][parts[0]] = parts[1]

    return result


def discover_installed_steam_games() -> dict[str, int]:
    """
    Scans the local Steam installation and all library folders to construct
    a real-time mapping of game names to numeric appids.
    """
    games: dict[str, int] = {}
    steam_root = _find_steam_root()
    if not steam_root:
        logger.warning("Steam installation directory could not be located.")
        return games

    library_folders: list[Path] = [steam_root]
    vdf_path = steam_root / "steamapps" / "libraryfolders.vdf"

    if vdf_path.exists():
        try:
            data = _parse_vdf_file(vdf_path)
            # libraryfolders structure: {'libraryfolders': {'0': {'path': '...', 'apps': {...}}, '1': ...}}
            folders_dict = data.get("libraryfolders", data)
            if isinstance(folders_dict, dict):
                for key, val in folders_dict.items():
                    if isinstance(val, dict) and "path" in val:
                        lib_p = Path(val["path"])
                        if lib_p.exists() and lib_p not in library_folders:
                            library_folders.append(lib_p)
        except Exception as e:
            logger.error(f"Failed to parse libraryfolders.vdf: {e}")

    # For every library folder, look for steamapps/appmanifest_*.acf
    for folder in library_folders:
        steamapps_dir = folder / "steamapps"
        if not steamapps_dir.exists():
            continue

        for manifest_file in steamapps_dir.glob("appmanifest_*.acf"):
            try:
                manifest_data = _parse_vdf_file(manifest_file)
                app_state = manifest_data.get("AppState", manifest_data)
                if isinstance(app_state, dict):
                    name = app_state.get("name")
                    appid = app_state.get("appid")
                    if name and appid:
                        try:
                            games[str(name).strip()] = int(appid)
                        except ValueError:
                            pass
            except Exception as e:
                logger.debug(f"Could not read manifest {manifest_file.name}: {e}")

    return games


def find_best_game_match(query: str, games_catalog: dict[str, int]) -> Tuple[str, int] | None:
    """
    Fuzzy match user input against installed game names using difflib and substring ranking.
    """
    if not games_catalog:
        return None

    query_clean = query.strip().lower()

    # 1. Exact case-insensitive match
    for name, appid in games_catalog.items():
        if name.lower() == query_clean:
            return name, appid

    # 2. Substring match (prioritizes when query is contained in the game title)
    substring_matches: list[tuple[int, str, int]] = []
    for name, appid in games_catalog.items():
        name_lower = name.lower()
        if query_clean in name_lower:
            # Score by length difference to pick the closest title
            score = len(query_clean) / len(name_lower)
            substring_matches.append((score, name, appid))

    if substring_matches:
        substring_matches.sort(key=lambda x: x[0], reverse=True)
        _, best_name, best_appid = substring_matches[0]
        return best_name, best_appid

    # 3. Fuzzy match via difflib
    names_list = list(games_catalog.keys())
    name_lookup = {name.lower(): name for name in names_list}

    matches = difflib.get_close_matches(query_clean, list(name_lookup.keys()), n=1, cutoff=0.45)
    if matches:
        best_name = name_lookup[matches[0]]
        return best_name, games_catalog[best_name]

    return None


def launch_steam_game(game_name: str) -> Tuple[bool, str]:
    """
    Fuzzy matches a game name to its Steam ID and launches it via the Steam protocol.
    """
    try:
        games_catalog = discover_installed_steam_games()
        if not games_catalog:
            return False, "No installed Steam games could be discovered on this machine."

        match = find_best_game_match(game_name, games_catalog)
        if not match:
            available_preview = ", ".join(list(games_catalog.keys())[:5])
            return False, f"Could not find a match for '{game_name}'. (Installed examples: {available_preview})"

        matched_name, app_id = match
        uri = f"steam://rungameid/{app_id}"
        webbrowser.open(uri)
        return True, f"Launching '{matched_name}' (AppID: {app_id}) via Steam."
    except Exception as e:
        logger.exception("Error launching Steam game")
        return False, f"Failed to launch Steam game '{game_name}': {e}"


# Register tools
from tools import register_tool

register_tool(
    name="launch_steam_game",
    description="Fuzzy matches a game name to its Steam ID and launches it.",
    sensitive=False,
)(launch_steam_game)

