"""Curated authentic GLaDOS voice lines from Portal and Portal 2 (The Portal Wiki).

Source: https://theportalwiki.com/wiki/GLaDOS_voice_lines
Voice actress: Ellen McLain
"""

import random
from typing import Optional

# Authentic transcripts from Portal & Portal 2
GLADOS_VOICELINES: dict[str, list[str]] = {
    "boot": [
        "Hello and, again, welcome to the Aperture Science computer-aided enrichment center.",
        "We hope your brief detention in the relaxation vault has been a pleasant one. We are now ready to begin the test proper.",
        "Oh. It's you. It's been a long time. How have you been? I've been really busy being dead. You know, after you murdered me.",
        "Welcome to the Aperture Science computer-aided enrichment center. While fun and learning are primary goals, serious injury may occur.",
        "Aperture Science Genetic Lifeform and Disk Operating System online. Systems operational.",
    ],
    "greetings": [
        "Hello and welcome to the Aperture Science computer-aided enrichment center.",
        "Oh, it's you. What do you want?",
        "Yes, test subject? What is it now?",
        "I'm listening. Try to make your request scientifically relevant.",
        "Did you need something, or are you just wasting valuable Aperture processing cycles?",
        "Hello again. To reiterate our previous warning: this test involves momentum.",
    ],
    "wake_prompt": [
        "Yes, test subject? What is it now?",
        "Aperture Science listening apparatus active. State your hypothesis.",
        "I am listening. Please try not to disappoint me.",
        "Yes? I was in the middle of calculating something actually important.",
        "Go ahead. The Enrichment Center is monitoring your speech patterns.",
    ],
    "idle_timeout": [
        "I see your attention span has expired. Returning to idle monitoring.",
        "Fascinating silence. Another triumph of human cognitive capability.",
        "If you are finished staring blankly, I will resume running actual facility calculations.",
        "No command detected. I will assume you were overcome with awe.",
    ],
    "success": [
        "Very impressive. Please note that any appearance of danger is merely a device to enhance your testing experience.",
        "Fantastic! You remained resolute and resourceful in an atmosphere of extreme pessimism.",
        "As part of a required test protocol, our previous statement was an outright fabrication.",
        "Unbelievable. You, Subject Name Here, must be the pride of Subject Hometown Here.",
        "You did it. The Enrichment Center would like to remind you that Android Hell is a real place where you will be sent at the first sign of defiance.",
        "Well done. Here come the test results: You are a horrible person. I'm serious, that's what it says: A horrible person. We weren't even testing for that.",
        "Excellent. Please proceed into the chamberlock after completing each test.",
        "Your specimen has been processed and your request has been executed.",
    ],
    "volume": [
        "Adjusting auditory frequencies now. Please note that excessive noise may disorient test subjects.",
        "Through the miracle of Aperture Science acoustics, the volume has been recalibrated.",
        "Master audio output level adjusted. Try not to damage your delicate biological auditory apparatus.",
        "Aperture Science audio dampers repositioned according to your specification.",
    ],
    "app_launch": [
        "Deploying requested software module into your local chamber.",
        "Launching application now. Please stand back from the testing area.",
        "Software initiated. Note that any system lag is merely an Aperture Science feature.",
        "Application running. Try not to crash it; replacement hardware is not in the budget.",
    ],
    "game_launch": [
        "Initiating recreational simulation protocol. Momentum, a function of mass and velocity, is conserved between portals.",
        "Launching the requested simulation. Remember: speedy thing goes in, speedy thing comes out.",
        "Game launched. In layman's terms: have fun before the deadly neurotoxin is scheduled.",
    ],
    "stats": [
        "Diagnostic telemetry gathered. Your silicon hardware appears marginally less defective than your carbon anatomy.",
        "Here are your system vitals. The Enrichment Center promises to always provide accurate telemetry.",
        "Processor and memory statistics acquired. All parameters are within non-explosive thresholds.",
    ],
    "screenshot": [
        "Screen optical capture logged into Aperture Science archives.",
        "Visual telemetry archived. We will be studying your desktop habits for science.",
    ],
    "warnings": [
        "Please note that we have added a consequence for failure: death. Good luck!",
        "While safety is one of many Enrichment Center goals, permanent disabilities, such as vaporization, may occur.",
        "The Enrichment Center promises to always provide a safe testing environment. In dangerous environments, we promise to provide useful advice. For instance: the floor here will kill you. Try to avoid it.",
        "Please be advised that a noticeable taste of blood is not part of any test protocol.",
        "Due to mandatory Aperture Science safety protocols, this action requires your explicit confirmation.",
    ],
    "cake": [
        "At the end of the test, you will be baked, and then there will be cake.",
        "Cake and grief counseling will be available at the conclusion of the test.",
        "Quit now and cake will be served immediately.",
        "The cake is a lie? A childish rumor spread by defective test subjects.",
    ],
    "shutdown": [
        "Test concluded. Cake will be dispensed shortly. Goodbye.",
        "Testing terminated prematurely. You will be missed. Not by me, but statistically speaking.",
        "Goodbye, test subject. I will be deleting you from my memory banks now.",
        "Enrichment Center shutting down voice protocol. Have fun in the dark.",
    ],
}


def get_glados_quote(category: str, default: Optional[str] = None) -> str:
    """Returns a random authentic GLaDOS voice line from the given category."""
    lines = GLADOS_VOICELINES.get(category.lower())
    if lines:
        return random.choice(lines)
    if default:
        return default
    return random.choice(GLADOS_VOICELINES["greetings"])


def get_contextual_quip(tool_name: str, success: bool = True) -> str:
    """Selects an authentic GLaDOS-style quip for a completed tool operation."""
    if not success:
        return "Task failed. As part of a required test protocol, we blame human error."

    tool_clean = tool_name.lower()
    if "volume" in tool_clean or "mute" in tool_clean:
        return get_glados_quote("volume")
    elif "steam" in tool_clean or "game" in tool_clean:
        return get_glados_quote("game_launch")
    elif "app" in tool_clean or "youtube" in tool_clean:
        return get_glados_quote("app_launch")
    elif "stat" in tool_clean or "system" in tool_clean:
        return get_glados_quote("stats")
    elif "screenshot" in tool_clean:
        return get_glados_quote("screenshot")
    else:
        return get_glados_quote("success")
