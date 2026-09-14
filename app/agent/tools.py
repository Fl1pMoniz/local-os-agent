"""LangChain tool definitions with explicit Pydantic parameter schemas.

Provides typed, validated tool calling wrappers for all 43 GLaDOS system capabilities.
"""

from __future__ import annotations

from typing import Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Pydantic Tool Input Schemas
# ---------------------------------------------------------------------------


class VolumeInput(BaseModel):
    level: int = Field(..., ge=0, le=100, description="Master audio volume percentage (0 to 100).")


class RelativeVolumeInput(BaseModel):
    delta: int = Field(
        ...,
        description="Relative volume adjustment percentage, positive or negative (e.g. +10, -15).",
    )


class AppVolumeInput(BaseModel):
    app_name: str = Field(
        ...,
        description="Name of the target process or application (e.g. 'spotify', 'discord', 'chrome').",
    )
    level: int = Field(..., ge=0, le=100, description="Application volume percentage (0 to 100).")


class PlayYouTubeInput(BaseModel):
    query: str = Field(..., description="Search terms, song name, or artist to play.")
    music: bool = Field(
        default=False,
        description="Whether to route playback to YouTube Music instead of standard YouTube.",
    )


class MediaControlInput(BaseModel):
    action: Literal["play_pause", "next_track", "prev_track", "volume_up", "volume_down"] = Field(
        ..., description="Media transport action to perform."
    )


class LaunchAppInput(BaseModel):
    app_name: str = Field(..., description="Name or executable of the application to launch.")


class LaunchSteamGameInput(BaseModel):
    game_name: str = Field(..., description="Name of the Steam game to find and launch.")


class SingSongInput(BaseModel):
    song_name: Literal["still_alive", "want_you_gone"] = Field(
        ..., description="Name of the Portal song for GLaDOS to sing."
    )


class PlaySfxInput(BaseModel):
    effect_name: Literal[
        "radio", "turret_hello", "turret_target", "turret_lost", "turret_goodnight"
    ] = Field(..., description="Portal sound effect identifier.")


class OpenWebsiteInput(BaseModel):
    target: str = Field(
        ...,
        description="Website URL or recognizable shorthand (e.g. 'youtube', 'github', 'reddit').",
    )


class WeatherInput(BaseModel):
    location: str = Field(..., description="City or geographic region to query weather for.")


class WikipediaInput(BaseModel):
    query: str = Field(..., description="Topic or term to search on Wikipedia.")


class SetTimerInput(BaseModel):
    seconds: int = Field(..., gt=0, description="Duration of countdown timer in seconds.")
    label: str = Field(
        default="Test Protocol", description="Descriptive label announced when timer fires."
    )


class TrackFlightInput(BaseModel):
    flight_query: str = Field(
        ..., description="Commercial airline flight number or callsign (e.g. 'DL450', 'AA100')."
    )
    open_browser: bool = Field(
        default=True, description="Whether to open FlightRadar24 tracking map in browser."
    )


class ZimaLaunchAppInput(BaseModel):
    app_name: str = Field(
        ..., description="Name of the Docker container or app on ZimaOS to launch."
    )


class ZimaHostInput(BaseModel):
    new_host: str = Field(..., description="IP address or hostname of the ZimaOS homelab server.")


class MonitorHardwareInput(BaseModel):
    live: bool = Field(
        default=False, description="Whether to launch continuous live monitoring HUD."
    )


class MonitorZimaosInput(BaseModel):
    live: bool = Field(
        default=False, description="Whether to launch continuous live ZimaOS monitoring HUD."
    )


class CaptureClipInput(BaseModel):
    seconds: int = Field(
        default=30, ge=5, le=120, description="Number of preceding seconds of gameplay to archive."
    )


class LaunchObsInput(BaseModel):
    start_buffer: bool = Field(
        default=True, description="Whether to prime and start the replay buffer upon launch."
    )


class ListClipsInput(BaseModel):
    limit: int = Field(
        default=5, ge=1, le=50, description="Maximum number of recent highlights to display."
    )


class JellyfinPlayInput(BaseModel):
    query: str = Field(
        ..., description="Movie, series, episode, or music track to stream from Jellyfin."
    )


class AnalyzeScreenInput(BaseModel):
    prompt: str = Field(
        ..., description="Instruction or diagnostic query for multimodal vision inspection."
    )


class PlaySoundboardInput(BaseModel):
    clip_name: str = Field(..., description="Name of the Aperture soundboard line to play.")


class DiscordClipInput(BaseModel):
    clip_path: str | None = Field(
        default=None, description="Optional path to specific clip video file."
    )
    caption: str | None = Field(
        default=None, description="Accompanying commentary text for the Discord upload."
    )


class LogWaterInput(BaseModel):
    amount_ml: int = Field(
        default=250,
        gt=0,
        le=5000,
        description="Volume of water in milliliters logged for test subject.",
    )


# ---------------------------------------------------------------------------
# LangChain Tools
# ---------------------------------------------------------------------------


@tool(args_schema=VolumeInput)
def set_volume_tool(level: int) -> str:
    """Sets master system volume percentage (0 to 100)."""
    from tools import audio

    success, msg = audio.set_volume(level)
    return msg


@tool(args_schema=RelativeVolumeInput)
def change_volume_relative_tool(delta: int) -> str:
    """Adjusts volume up or down relatively (e.g. +10, -15)."""
    from tools import audio

    success, msg = audio.change_volume_relative(delta)
    return msg


@tool(args_schema=AppVolumeInput)
def set_app_volume_tool(app_name: str, level: int) -> str:
    """Sets volume of a specific background application."""
    from tools import audio

    success, msg = audio.set_app_volume(app_name, level)
    return msg


@tool
def mute_toggle_tool() -> str:
    """Toggles system audio mute state."""
    from tools import audio

    success, msg = audio.mute_toggle()
    return msg


@tool(args_schema=PlayYouTubeInput)
def play_youtube_tool(query: str, music: bool = False) -> str:
    """Directly opens song or video playback on YouTube or YouTube Music."""
    from tools import media

    success, msg = media.play_youtube(query, music=music)
    return msg


@tool(args_schema=MediaControlInput)
def media_control_tool(action: str) -> str:
    """Controls media playback (play_pause, next_track, prev_track)."""
    from tools import media

    success, msg = media.media_control(action)
    return msg


@tool(args_schema=LaunchAppInput)
def launch_app_tool(app_name: str) -> str:
    """Opens a native desktop application."""
    from tools import system

    success, msg = system.launch_app(app_name)
    return msg


@tool(args_schema=LaunchSteamGameInput)
def launch_steam_game_tool(game_name: str) -> str:
    """Fuzzy-matches game title and launches via Steam."""
    from tools import steam

    success, msg = steam.launch_steam_game(game_name)
    return msg


@tool
def get_system_stats_tool() -> str:
    """Returns CPU, RAM, GPU, and system diagnostic telemetry."""
    from tools import system

    success, msg = system.get_system_stats()
    return msg


@tool
def take_screenshot_tool() -> str:
    """Captures the active screen and saves image to captures directory."""
    from tools import system

    success, msg = system.take_screenshot()
    return msg


@tool(args_schema=SingSongInput)
def sing_song_tool(song_name: str) -> str:
    """Plays an authentic Portal song sung by GLaDOS."""
    from tools import songs

    success, msg = songs.sing_song(song_name)
    return msg


@tool
def stop_song_tool() -> str:
    """Halts any currently playing GLaDOS song."""
    from tools import songs

    success, msg = songs.stop_song()
    return msg


@tool
def get_active_window_tool() -> str:
    """Returns the title and process of the foreground window."""
    from tools import companion

    success, msg = companion.get_active_window()
    return msg


@tool
def roast_user_tool() -> str:
    """Analyzes active window and generates sarcastic GLaDOS commentary."""
    from tools import companion

    success, msg = companion.roast_user()
    return msg


@tool(args_schema=PlaySfxInput)
def play_portal_sfx_tool(effect_name: str) -> str:
    """Plays Portal sound effect or radio loop."""
    from tools import sfx

    success, msg = sfx.play_portal_sfx(effect_name)
    return msg


@tool
def stop_sfx_tool() -> str:
    """Stops active Portal sound effect playback."""
    from tools import sfx

    success, msg = sfx.stop_sfx()
    return msg


@tool(args_schema=OpenWebsiteInput)
def open_website_tool(target: str) -> str:
    """Opens specified URL or bookmark in default browser."""
    from tools import web

    success, msg = web.open_website(target)
    return msg


@tool(args_schema=WeatherInput)
def get_weather_tool(location: str) -> str:
    """Fetches meteorological weather data for target location."""
    from tools import web

    success, msg = web.get_weather(location)
    return msg


@tool(args_schema=WikipediaInput)
def wikipedia_lookup_tool(query: str) -> str:
    """Searches Wikipedia encyclopedia for topic summary."""
    from tools import web

    success, msg = web.wikipedia_lookup(query)
    return msg


@tool
def lock_workstation_tool() -> str:
    """Locks the current desktop session immediately."""
    from tools import system

    success, msg = system.lock_workstation()
    return msg


@tool(args_schema=SetTimerInput)
def set_timer_tool(seconds: int, label: str = "Test Protocol") -> str:
    """Schedules a countdown voice alarm for test subjects."""
    from tools import system

    success, msg = system.set_timer(seconds, label=label)
    return msg


@tool
def read_clipboard_aloud_tool() -> str:
    """Reads system clipboard text aloud using speech synthesis."""
    from tools import system

    success, msg = system.read_clipboard_aloud()
    return msg


@tool
def empty_recycle_bin_tool() -> str:
    """Purges system recycle bin or trash permanently."""
    from tools import system

    success, msg = system.empty_recycle_bin()
    return msg


@tool(args_schema=TrackFlightInput)
def track_flight_tool(flight_query: str, open_browser: bool = True) -> str:
    """Tracks a live flight on radar via FlightRadar24."""
    from tools import flight

    success, msg = flight.track_flight(flight_query, open_browser=open_browser)
    return msg


@tool
def get_tracked_flight_info_tool() -> str:
    """Returns full radar telemetry HUD for the currently tracked flight."""
    from tools import flight

    success, msg = flight.get_tracked_flight_info()
    return msg


@tool
def get_zimaos_status_tool() -> str:
    """Inspects health, CPU, memory, and storage of ZimaOS home server."""
    from tools import zimaos

    success, msg = zimaos.get_zimaos_status()
    return msg


@tool
def list_zimaos_apps_tool() -> str:
    """Lists running Docker containers and apps on ZimaOS home server."""
    from tools import zimaos

    success, msg = zimaos.list_zimaos_apps()
    return msg


@tool
def open_zimaos_dashboard_tool() -> str:
    """Opens ZimaOS Web GUI management console in browser."""
    from tools import zimaos

    success, msg = zimaos.open_zimaos_dashboard()
    return msg


@tool(args_schema=ZimaLaunchAppInput)
def launch_zimaos_app_tool(app_name: str) -> str:
    """Launches or opens a Docker container application on ZimaOS."""
    from tools import zimaos

    success, msg = zimaos.launch_zimaos_app(app_name)
    return msg


@tool(args_schema=ZimaHostInput)
def set_zimaos_host_tool(new_host: str) -> str:
    """Updates and persists the IP address of the ZimaOS home server."""
    from tools import zimaos

    success, msg = zimaos.set_zimaos_host(new_host)
    return msg


@tool(args_schema=MonitorHardwareInput)
def monitor_hardware_tool(live: bool = False) -> str:
    """Provides CPU, RAM, GPU, power draw, and AI inference telemetry."""
    from tools import system

    success, msg = system.monitor_hardware(live=live)
    return msg


@tool(args_schema=MonitorZimaosInput)
def monitor_zimaos_tool(live: bool = False) -> str:
    """Provides real-time ZimaOS home server telemetry HUD."""
    from tools import zimaos

    success, msg = zimaos.monitor_zimaos(live=live)
    return msg


@tool(args_schema=CaptureClipInput)
def capture_game_clip_tool(seconds: int = 30) -> str:
    """Captures and archives recent gameplay via OBS Studio Replay Buffer."""
    from tools import game_clipper

    res = game_clipper.capture_game_clip(seconds=seconds)
    return res.get("message", "Clip captured.")


@tool(args_schema=LaunchObsInput)
def launch_obs_tool(start_buffer: bool = True) -> str:
    """Launches OBS Studio with Replay Buffer armed."""
    from tools import game_clipper

    res = game_clipper.launch_obs(start_buffer=start_buffer)
    return res.get("message", "OBS launched.")


@tool(args_schema=ListClipsInput)
def list_recent_clips_tool(limit: int = 5) -> str:
    """Lists recent gameplay recordings and file sizes."""
    from tools import game_clipper

    res = game_clipper.list_recent_clips(limit=limit)
    return res.get("message", "Recent clips listed.")


@tool(args_schema=JellyfinPlayInput)
def search_and_play_jellyfin_tool(query: str) -> str:
    """Searches media library on Jellyfin server and commands playback."""
    from tools import jellyfin

    res = jellyfin.search_and_play_jellyfin(query)
    return res.get("message", "Jellyfin playback commanded.")


@tool
def get_jellyfin_now_playing_tool() -> str:
    """Returns live ASCII Now Playing HUD for Jellyfin streaming."""
    from tools import jellyfin

    res = jellyfin.get_jellyfin_now_playing()
    return res.get("message", "Jellyfin status retrieved.")


@tool(args_schema=AnalyzeScreenInput)
def analyze_screen_tool(prompt: str) -> str:
    """Uses visual multimodal AI to inspect screen contents and errors."""
    from tools import vision

    res = vision.analyze_screen(prompt=prompt)
    return res.get("analysis", res.get("message", "Screen analyzed."))


@tool(args_schema=PlaySoundboardInput)
def play_soundboard_tool(clip_name: str) -> str:
    """Plays authentic Aperture dialogue soundboard clips."""
    from tools import soundboard

    res = soundboard.play_soundboard(clip_name)
    return res.get("message", "Soundboard clip played.")


@tool(args_schema=DiscordClipInput)
def send_clip_to_discord_tool(clip_path: str | None = None, caption: str | None = None) -> str:
    """Transfers the latest highlight clip to configured Discord channel."""
    from tools import discord_relay

    res = discord_relay.send_clip_to_discord(clip_path=clip_path, caption=caption)
    return res.get("message", "Clip sent to Discord.")


@tool
def check_subject_status_tool() -> str:
    """Displays Aperture Subject Biometric HUD with testing hours and hydration."""
    from tools import subject_wellness

    res = subject_wellness.check_subject_status()
    return res.get("hud_card", res.get("message", "Subject status verified."))


@tool(args_schema=LogWaterInput)
def log_water_intake_tool(amount_ml: int = 250) -> str:
    """Logs water consumption in milliliters for the test subject."""
    from tools import subject_wellness

    res = subject_wellness.log_water_intake(amount_ml=amount_ml)
    return res.get("message", "Hydration logged.")


ALL_GLADOS_TOOLS = [
    set_volume_tool,
    change_volume_relative_tool,
    set_app_volume_tool,
    mute_toggle_tool,
    play_youtube_tool,
    media_control_tool,
    launch_app_tool,
    launch_steam_game_tool,
    get_system_stats_tool,
    take_screenshot_tool,
    sing_song_tool,
    stop_song_tool,
    get_active_window_tool,
    roast_user_tool,
    play_portal_sfx_tool,
    stop_sfx_tool,
    open_website_tool,
    get_weather_tool,
    wikipedia_lookup_tool,
    lock_workstation_tool,
    set_timer_tool,
    read_clipboard_aloud_tool,
    empty_recycle_bin_tool,
    track_flight_tool,
    get_tracked_flight_info_tool,
    get_zimaos_status_tool,
    list_zimaos_apps_tool,
    open_zimaos_dashboard_tool,
    launch_zimaos_app_tool,
    set_zimaos_host_tool,
    monitor_hardware_tool,
    monitor_zimaos_tool,
    capture_game_clip_tool,
    launch_obs_tool,
    list_recent_clips_tool,
    search_and_play_jellyfin_tool,
    get_jellyfin_now_playing_tool,
    analyze_screen_tool,
    play_soundboard_tool,
    send_clip_to_discord_tool,
    check_subject_status_tool,
    log_water_intake_tool,
]
