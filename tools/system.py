"""System diagnostics, window management, application execution, and safety gatekeeper tools."""

import datetime
import logging
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any, Tuple

import psutil
from PIL import ImageGrab

from config import config

logger = logging.getLogger("local_os_agent.tools.system")


def launch_app(app_name: str) -> Tuple[bool, str]:
    """
    Opens a standard native application or user-specified program via subprocess.
    """
    if not app_name or not app_name.strip():
        return False, "Application name cannot be empty."

    app_clean = app_name.strip()

    # Block accidental command shell spawning from voice or LLM hallucination
    if app_clean.lower() in ("cmd", "command", "cmd.exe", "powershell", "powershell.exe"):
        return False, "Direct shell execution via launch_app is disabled for system safety."

    alias_map = {
        "calculator": "calc.exe",
        "calc": "calc.exe",
        "notepad": "notepad.exe",
        "explorer": "explorer.exe",
        "file explorer": "explorer.exe",
        "terminal": "wt.exe",
        "task manager": "taskmgr.exe",
        "taskmgr": "taskmgr.exe",
        "paint": "mspaint.exe",
        "mspaint": "mspaint.exe",
        "control panel": "control.exe",
        "settings": "ms-settings:",
    }

    target = alias_map.get(app_clean.lower(), app_clean)

    try:
        if platform.system() == "Windows":
            # For URI protocols like ms-settings: or direct app execution
            if target.startswith("ms-") or ":" in target and not Path(target).is_absolute():
                os.startfile(target)
            else:
                # Check if in PATH or executable
                exec_path = shutil.which(target) or target
                subprocess.Popen(exec_path, shell=True)
            return True, f"Application '{app_name}' launched successfully."
        else:
            subprocess.Popen([target], shell=True)
            return True, f"Application '{app_name}' launched."
    except Exception as e:
        logger.exception(f"Failed to launch application '{app_name}'")
        return False, f"Could not launch '{app_name}': {e}"


def get_system_stats() -> Tuple[bool, dict[str, Any]]:
    """
    Returns CPU usage percentage, RAM stats (total, used, free, percent),
    and battery status.
    """
    try:
        # CPU
        cpu_pct = psutil.cpu_percent(interval=0.2)
        cpu_count_logical = psutil.cpu_count(logical=True)
        cpu_count_physical = psutil.cpu_count(logical=False)

        # Memory
        mem = psutil.virtual_memory()
        mem_stats = {
            "total_gb": round(mem.total / (1024**3), 2),
            "used_gb": round(mem.used / (1024**3), 2),
            "free_gb": round(mem.available / (1024**3), 2),
            "percent_used": mem.percent,
        }

        # Battery
        battery = psutil.sensors_battery()
        if battery:
            battery_stats = {
                "percent": battery.percent,
                "power_plugged": battery.power_plugged,
                "secs_left": battery.secsleft if battery.secsleft != psutil.POWER_TIME_UNLIMITED else "Unlimited",
            }
        else:
            battery_stats = {"percent": None, "power_plugged": True, "info": "Desktop / No battery detected"}

        # GPU (NVIDIA CUDA)
        gpu_stats = None
        try:
            import torch
            if torch.cuda.is_available():
                device_name = torch.cuda.get_device_name(0)
                alloc_mb = round(torch.cuda.memory_allocated(0) / (1024**2), 1)
                reserved_mb = round(torch.cuda.memory_reserved(0) / (1024**2), 1)
                total_mem_gb = round(torch.cuda.get_device_properties(0).total_memory / (1024**3), 2)
                gpu_stats = {
                    "device": device_name,
                    "total_gb": total_mem_gb,
                    "allocated_mb": alloc_mb,
                    "reserved_mb": reserved_mb,
                }
        except Exception:
            pass

        stats = {
            "cpu": {
                "percent_used": cpu_pct,
                "physical_cores": cpu_count_physical,
                "logical_cores": cpu_count_logical,
            },
            "ram": mem_stats,
            "gpu": gpu_stats,
            "battery": battery_stats,
            "platform": platform.platform(),
        }
        return True, stats
    except Exception as e:
        logger.exception("Error collecting system stats")
        return False, {"error": str(e)}


def take_screenshot(filename: str | None = None) -> Tuple[bool, str]:
    """
    Captures the screen and saves it locally to the dedicated captures folder.
    Handles locked or background session gracefully.
    """
    try:
        config.captures_dir.mkdir(parents=True, exist_ok=True)
        if not filename:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}.png"
        elif not filename.lower().endswith((".png", ".jpg", ".jpeg")):
            filename = f"{filename}.png"

        target_path = config.captures_dir / filename

        try:
            image = ImageGrab.grab(all_screens=True)
        except OSError:
            # When Windows is locked or display DC is inaccessible in non-interactive session
            from PIL import Image, ImageDraw
            image = Image.new("RGB", (1920, 1080), color=(30, 30, 30))
            draw = ImageDraw.Draw(image)
            msg = f"Screen Capture Placeholder\nSession display locked or headless at {datetime.datetime.now()}"
            draw.text((50, 50), msg, fill=(255, 255, 255))

        image.save(str(target_path))
        return True, f"Screenshot successfully saved to: {target_path.resolve()}"
    except Exception as e:
        logger.exception("Failed to take screenshot")
        return False, f"Screenshot error: {e}"


def minimize_all_windows() -> Tuple[bool, str]:
    """
    Minimizes active windows to show the desktop.
    """
    try:
        if platform.system() == "Windows":
            # Using Shell.Application COM interface for clean MinimizeAll
            import comtypes.client
            shell = comtypes.client.CreateObject("Shell.Application")
            shell.MinimizeAll()
            return True, "All windows minimized."
        else:
            import pyautogui
            pyautogui.hotkey("super", "d")
            return True, "Triggered show desktop."
    except Exception as e:
        logger.exception("Error minimizing windows")
        return False, f"Failed to minimize windows: {e}"


# --- Contextual Safety Gatekeeper Tools ---

def kill_process(name_or_pid: str | int) -> Tuple[bool, str]:
    """
    Terminates a process by name or PID. SENSITIVE: requires confirmation.
    """
    try:
        target_pid: int | None = None
        target_name: str | None = None

        if isinstance(name_or_pid, int) or (isinstance(name_or_pid, str) and name_or_pid.isdigit()):
            target_pid = int(name_or_pid)
        else:
            target_name = str(name_or_pid).lower()

        killed = []
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                p_pid = proc.info["pid"]
                p_name = proc.info["name"] or ""
                if target_pid is not None and p_pid == target_pid:
                    proc.terminate()
                    killed.append(f"{p_name} (PID: {p_pid})")
                elif target_name is not None and target_name in p_name.lower():
                    proc.terminate()
                    killed.append(f"{p_name} (PID: {p_pid})")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if killed:
            return True, f"Terminated {len(killed)} process(es): {', '.join(killed)}"
        return False, f"No running process matching '{name_or_pid}' found."
    except Exception as e:
        return False, f"Failed to terminate process: {e}"


def shutdown(delay_seconds: int = 60) -> Tuple[bool, str]:
    """
    Initiates system shutdown after specified delay. SENSITIVE: requires confirmation.
    """
    try:
        delay = max(0, int(delay_seconds))
        if platform.system() == "Windows":
            subprocess.run(["shutdown", "/s", "/t", str(delay)], check=True)
            return True, f"System shutdown scheduled in {delay} seconds. Run 'shutdown /a' to abort."
        else:
            return False, f"Shutdown not implemented for {platform.system()}."
    except Exception as e:
        return False, f"Failed to initiate shutdown: {e}"


def sleep_pc() -> Tuple[bool, str]:
    """
    Puts the computer into sleep mode. SENSITIVE: requires confirmation.
    """
    try:
        if platform.system() == "Windows":
            subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], check=True)
            return True, "Computer sleep command initiated."
        else:
            return False, f"Sleep command not implemented for {platform.system()}."
    except Exception as e:
        return False, f"Failed to sleep computer: {e}"


def lock_workstation() -> Tuple[bool, str]:
    """
    Locks the Windows workstation immediately.
    """
    try:
        if platform.system() == "Windows":
            import ctypes
            ctypes.windll.user32.LockWorkStation()
            return True, "Workstation locked successfully."
        return False, f"Lock workstation not implemented for {platform.system()}."
    except Exception as e:
        return False, f"Failed to lock workstation: {e}"


def empty_recycle_bin() -> Tuple[bool, str]:
    """
    Empties the Windows Recycle Bin without prompt. SENSITIVE: requires confirmation.
    """
    try:
        if platform.system() == "Windows":
            import ctypes
            # SHERB_NOCONFIRMATION (0x1) | SHERB_NOPROGRESSUI (0x2) | SHERB_NOSOUND (0x4) = 7
            res = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 7)
            return True, "Recycle Bin emptied successfully."
        return False, f"Empty recycle bin not implemented for {platform.system()}."
    except Exception as e:
        return False, f"Failed to empty Recycle Bin: {e}"


def set_timer(seconds: int, label: str = "Test") -> Tuple[bool, str]:
    """
    Sets an asynchronous countdown timer that announces completion via GLaDOS voice.
    """
    try:
        sec = int(seconds)
        if sec <= 0:
            return False, "Timer duration must be greater than 0 seconds."

        import threading
        import time

        def _timer_worker():
            time.sleep(sec)
            try:
                from voice.speaker import speak
                speak(f"Attention test subject: Your timer for {label} has expired. Resume testing immediately.")
            except Exception as e:
                logger.error("Timer alarm failed: %s", e)

        t = threading.Thread(target=_timer_worker, daemon=True)
        t.start()
        return True, f"Timer set for {sec} seconds ({label})."
    except Exception as e:
        return False, f"Failed to set timer: {e}"


def get_clipboard() -> Tuple[bool, str]:
    """
    Retrieves the current text content from the system clipboard.
    """
    try:
        import pyperclip
        content = pyperclip.paste()
        if not content:
            return True, "Clipboard is currently empty."
        return True, content
    except Exception as e:
        return False, f"Failed to read clipboard: {e}"


def set_clipboard(text: str) -> Tuple[bool, str]:
    """
    Copies text to the system clipboard.
    """
    try:
        import pyperclip
        pyperclip.copy(text)
        return True, f"Copied {len(text)} characters to clipboard."
    except Exception as e:
        return False, f"Failed to write clipboard: {e}"


def read_clipboard_aloud() -> Tuple[bool, str]:
    """
    Reads the system clipboard text aloud using GLaDOS voice.
    """
    try:
        import pyperclip
        from voice.speaker import speak
        content = pyperclip.paste()
        if not content or not content.strip():
            return False, "Clipboard is empty. Nothing to read."
        
        # Announce snippet or full text
        trimmed = content.strip()
        if len(trimmed) > 300:
            speech_text = f"Your clipboard contains: {trimmed[:290]}... and more text."
        else:
            speech_text = f"Your clipboard contains: {trimmed}"
        speak(speech_text)
        return True, f"Read {len(trimmed)} characters aloud."
    except Exception as e:
        return False, f"Failed to read clipboard aloud: {e}"


# Register tools
from tools import register_tool

register_tool(
    name="launch_app",
    description="Opens a standard native application.",
    sensitive=False,
)(launch_app)

register_tool(
    name="get_system_stats",
    description="Returns CPU, RAM, GPU, and battery data.",
    sensitive=False,
)(get_system_stats)

register_tool(
    name="take_screenshot",
    description="Captures the screen and saves it locally.",
    sensitive=False,
)(take_screenshot)

register_tool(
    name="minimize_all_windows",
    description="Minimizes active windows to show the desktop.",
    sensitive=False,
)(minimize_all_windows)

register_tool(
    name="lock_workstation",
    description="Locks the Windows workstation.",
    sensitive=False,
)(lock_workstation)

register_tool(
    name="set_timer",
    description="Sets a countdown timer that speaks an announcement when done.",
    sensitive=False,
)(set_timer)

register_tool(
    name="get_clipboard",
    description="Gets text from the clipboard.",
    sensitive=False,
)(get_clipboard)

register_tool(
    name="set_clipboard",
    description="Copies text into the clipboard.",
    sensitive=False,
)(set_clipboard)

register_tool(
    name="read_clipboard_aloud",
    description="Reads current clipboard text aloud with GLaDOS voice.",
    sensitive=False,
)(read_clipboard_aloud)

# Sensitive tools
register_tool(
    name="kill_process",
    description="Terminates a process by name or PID.",
    sensitive=True,
)(kill_process)

register_tool(
    name="shutdown",
    description="Initiates system shutdown.",
    sensitive=True,
)(shutdown)

register_tool(
    name="sleep_pc",
    description="Puts the computer into sleep mode.",
    sensitive=True,
)(sleep_pc)

register_tool(
    name="empty_recycle_bin",
    description="Empties the Windows Recycle Bin permanently.",
    sensitive=True,
)(empty_recycle_bin)

