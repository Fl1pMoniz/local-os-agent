"""Protocol 7: Aperture Subject Maintenance Protocol.
Ergonomics, hydration, eye strain intervals, and session monitoring
delivered with authentic GLaDOS testing axioms and dark humor.
"""

import logging
import random
import time
from typing import Any

from tools import register_tool

logger = logging.getLogger("local_os_agent.tools.subject_wellness")

_session_start_time = time.time()
_last_water_time = time.time()
_water_logged_ml = 0
_breaks_completed = 0

GLADOS_WELLNESS_QUIPS = [
    "The Enrichment Center reminds you that posture correction improves testing accuracy by up to twelve percent.",
    "Attention test subject: Hydration is mandatory. Unconscious test subjects produce statistically invalid research data.",
    "Your continuous sedentary state has been noted. Please blink twenty times and look at a distant wall before resuming.",
    "Ingesting dihydrogen monoxide is recommended to prevent premature biological expiration.",
    "Congratulations. You have remained stationary for an extended period. A triumph of human resilience. Or lethargy.",
]


def format_wellness_card(
    session_str: str, hydration_str: str, breaks_count: int, assessment: str, axiom: str
) -> str:
    """Generates ASCII Subject Biometric & Compliance HUD."""
    card = (
        "+====================================================================+\n"
        "|       APERTURE SCIENCE SUBJECT BIOMETRIC & COMPLIANCE HUD          |\n"
        "| [● BIOMETRICS ACTIVE] Status: Operational     Posture: Sedentary   |\n"
        "+====================================================================+\n"
        f"| Continuous Session : {session_str[:46]:<46} |\n"
        f"| Hydration Logged   : {hydration_str[:46]:<46} |\n"
        f"| Eye Rest Intervals : {f'{breaks_count} Completed (20-20-20 Protocol)'[:46]:<46} |\n"
        f"| Subject Assessment : {assessment[:46]:<46} |\n"
        f"| Testing Axiom      : {axiom[:46]:<46} |\n"
        "+--------------------------------------------------------------------+\n"
    )
    return card


@register_tool
def check_subject_status() -> dict[str, Any]:
    """
    Returns the Aperture Science Subject Biometric HUD showing continuous
    computer session duration, hydration level, and ergonomic recommendations.
    """
    elapsed_sec = int(time.time() - _session_start_time)
    hours = elapsed_sec // 3600
    mins = (elapsed_sec % 3600) // 60
    session_str = f"{hours}h {mins}m active testing"

    time_since_water = int(time.time() - _last_water_time)
    water_mins = time_since_water // 60
    if _water_logged_ml == 0:
        hydration_str = f"0 mL (Last logged: {water_mins}m ago - Deficient)"
        assessment = "Subject hydration deficient. Water consumption advised."
    else:
        hydration_str = f"{_water_logged_ml} mL logged (Last: {water_mins}m ago)"
        assessment = "Nominal biological hydration. Continue testing."

    axiom = random.choice(GLADOS_WELLNESS_QUIPS)

    card = format_wellness_card(
        session_str=session_str,
        hydration_str=hydration_str,
        breaks_count=_breaks_completed,
        assessment=assessment,
        axiom=axiom,
    )

    return {
        "success": True,
        "session_hours": hours,
        "session_minutes": mins,
        "water_logged_ml": _water_logged_ml,
        "terminal_card": card,
        "message": f"Session duration: {session_str}. {axiom}",
    }


@register_tool
def log_water_intake(milliliters: int = 250) -> dict[str, Any]:
    """
    Logs water intake (default 250 mL) to the test subject's biological record.
    """
    global _water_logged_ml, _last_water_time
    _water_logged_ml += milliliters
    _last_water_time = time.time()

    quips = [
        f"Hydration of {milliliters} mL recorded. Your biological degradation has been delayed by another cycle.",
        f"{milliliters} mL logged. The Enrichment Center appreciates your compliance with basic survival requirements.",
        f"Water intake noted ({_water_logged_ml} mL total). You are now minimally capable of enduring further testing.",
    ]
    quip = random.choice(quips)

    return {"success": True, "total_water_ml": _water_logged_ml, "message": quip}


@register_tool
def log_eye_break() -> dict[str, Any]:
    """
    Logs an ergonomic 20-second eye strain relief interval (20-20-20 rule).
    """
    global _breaks_completed
    _breaks_completed += 1
    return {
        "success": True,
        "breaks_completed": _breaks_completed,
        "message": "Ergonomic interval archived. Retinal fatigue sensors recalibrated. Please resume testing.",
    }
