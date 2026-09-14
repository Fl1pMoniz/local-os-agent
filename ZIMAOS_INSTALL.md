# Installing Aperture GLaDOS on ZimaOS

This guide explains how to install the Aperture Science GLaDOS Agent onto your ZimaOS (or CasaOS) server with one-click app configuration.

---

## Prerequisites

1. **ZimaOS or CasaOS Server** running on your local network (for example, `http://192.168.1.123`).
2. **Local LLM Runner (Ollama)**:
   - **Option A (Installed directly on ZimaOS via App Store)**: Ollama runs as a container on the server at `http://host.docker.internal:11434`.
   - **Option B (Running on your main desktop PC)**: Ollama runs on your LAN workstation at `http://<your-pc-ip>:11434`.
   - **Recommended Zero-VRAM Models (Runs fast on any standard CPU)**:
     ```bash
     ollama pull qwen2.5:1.5b
     ollama pull llama3.2:1b
     ```

---

## Method 1: One-Click Import via ZimaOS Dashboard (Recommended)

1. Open your ZimaOS dashboard in your web browser (`http://<zimaos-ip>`).
2. Click on the **App Store** icon on your home dashboard.
3. In the top right corner of the App Store window, click **Install a customized app**.
4. Click the **Import** button (top right of the customized app modal).
5. Paste the complete contents of `docker-compose.yml` (found in the root of this repository) into the import box, or upload the file directly.
6. Click **Submit**.
7. ZimaOS will automatically detect the configuration and populate the app fields:
   - **Title**: Aperture GLaDOS
   - **Icon**: Authentic Aperture Science Diaphragm logo
   - **Web UI Port**: 5000
   - **Network**: Bridge with host gateway access
8. Under **Environment Variables**, verify:
   - `LLM_BASE_URL`: Set to `http://host.docker.internal:11434/v1` (if Ollama is on the ZimaOS server) or `http://192.168.1.X:11434/v1` (if Ollama is on your desktop PC).
   - `LLM_MODEL`: `qwen2.5:1.5b` (or your preferred lightweight CPU model).
9. Click **Install**.
10. Once installation finishes, click the new **Aperture GLaDOS** app tile on your dashboard. Your full-screen Amber CRT terminal will open at `http://<zimaos-ip>:5000`.

---

## Method 2: Command Line Deployment via SSH

If you prefer deploying via terminal SSH onto your ZimaOS server:

1. Connect to your ZimaOS server over SSH:
   ```bash
   ssh root@<zimaos-ip>
   ```

2. Clone the repository and switch to the docker branch:
   ```bash
   git clone https://github.com/Fl1pMoniz/local-os-agent.git
   cd local-os-agent
   git checkout feat/docker-zimaos
   ```

3. Launch the container using Docker Compose:
   ```bash
   docker compose up -d --build
   ```

4. Verify that the service is running and healthy:
   ```bash
   docker ps
   curl -I http://127.0.0.1:5000/api/state
   ```

5. Access the terminal interface from any phone, tablet, or PC on your network at:
   ```
   http://<zimaos-ip>:5000
   ```

---

## Features Available in Container Mode

When running headlessly inside Docker on ZimaOS, the agent automatically enables container mode:
- **Amber CRT Web Management Console**: Fully accessible over your local network on port 5000.
- **Hardware & Server Telemetry**: Real-time component temperatures, CPU loads, and memory metrics.
- **Airspace Radar Tracking**: Live ADS-B aircraft monitoring via callsign queries.
- **Jellyfin Remote Control**: Media search and playback triggering across your network.
- **Zero-VRAM Inference**: Lightweight model execution on modest home server CPUs.
- **Headless Audio Degradation**: Graceful mute of desktop audio devices while maintaining full terminal, tool dispatch, and visual telemetry operations.
