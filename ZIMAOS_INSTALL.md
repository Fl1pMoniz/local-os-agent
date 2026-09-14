# Installing Aperture GLaDOS on ZimaOS

This guide provides step-by-step instructions to install the Aperture Science GLaDOS Agent onto your ZimaOS server (`MonizServer` at `http://192.168.1.123`) using your existing Ollama container.

---

## 1. Hardware Specs & Model Recommendation

Based on the live telemetry inspected directly from your ZimaOS server via GLaDOS:
- **Server Name**: MonizServer (`http://192.168.1.123`)
- **CPU**: Intel Core i5-8400 (6 Cores / 6 Threads @ 2.80GHz base, up to 4.00GHz Turbo)
- **RAM**: 16 GB DDR4 (15.4 GB total, ~10.5 GB available)
- **GPU**: Intel UHD Graphics 630 (Integrated, zero dedicated VRAM)
- **Existing Containers**: 25 microservices active (including your `ollama` container)

### Cherry-Picked Model: `qwen2.5:3b` (or `qwen2.5:1.5b`)
Because your server runs on an Intel Core i5-8400 CPU with integrated graphics and zero dedicated VRAM, the model executes entirely using CPU vector instructions (AVX2):
- **Primary Recommendation: `qwen2.5:3b`**
  - **Memory Footprint**: ~2.5 GB RAM (leaves ~8 GB free for Jellyfin, Home Assistant, and Sonarr).
  - **Inference Speed**: ~20-30 tokens/second on all 6 cores.
  - **Capability**: Highest accuracy under 4B parameters for structured JSON tool-calling, agent directives, and complex conversational responses.
- **Speed Alternative: `qwen2.5:1.5b`**
  - **Memory Footprint**: ~1.4 GB RAM.
  - **Inference Speed**: ~45-55 tokens/second (near-instantaneous responses).
  - **Capability**: Superb for rapid media control, hardware checks, and direct commands.

---

## 2. Step 1: Pull the Model into your Ollama Container

Before importing the app, ensure your existing Ollama container has the cherry-picked model downloaded.

### Option A: From your ZimaOS Web Terminal or SSH (Recommended)
1. In your browser, open your ZimaOS web terminal at `http://192.168.1.123:7681` (or SSH into `root@192.168.1.123`).
2. Run the command to pull the model directly into your Ollama container:
   ```bash
   docker exec -it ollama ollama pull qwen2.5:3b
   ```
   *(If you also want the ultra-fast 1.5B model, run: `docker exec -it ollama ollama pull qwen2.5:1.5b`)*
3. Verify that the model is loaded:
   ```bash
   docker exec -it ollama ollama list
   ```

### Option B: Via HTTP API Call from any Computer on your LAN
You can trigger the download remotely without opening a terminal by running this in Windows PowerShell:
```powershell
Invoke-RestMethod -Method Post -Uri "http://192.168.1.123:11434/api/pull" -ContentType "application/json" -Body '{"name": "qwen2.5:3b"}'
```

---

## 3. Step 2: Add GLaDOS to your ZimaOS Dashboard

1. Open your ZimaOS dashboard in your web browser:
   ```
   http://192.168.1.123
   ```
2. Click the **App Store** icon on your home dashboard.
3. In the top right corner of the App Store window, click **Install a customized app**.
4. In the customized app setup window, click the **Import** button in the top right corner.
5. Paste the following clean Compose configuration into the import text area:

```yaml
name: glados-agent

x-casaos:
  architectures:
    - amd64
    - arm64
  main: glados
  author: "Fl1pMoniz"
  category: "Utilities"
  developer: "Aperture Laboratories"
  icon: "https://raw.githubusercontent.com/Fl1pMoniz/local-os-agent/main/ui/assets/glados.png"
  thumbnail: "https://raw.githubusercontent.com/Fl1pMoniz/local-os-agent/main/ui/assets/glados.png"
  title:
    en_us: "Aperture GLaDOS"
  tagline:
    en_us: "Aperture Science AI Terminal & Homelab Controller"
  description:
    en_us: |
      Aperture Science GLaDOS Autonomous Agent & CRT Management Console.
      Tuned for Intel Core i5-8400 and ZimaOS homelabs.
      Controls hardware sensors, ADS-B radar aircraft tracking, Jellyfin media playback,
      soundboard acoustics, and provides an authentic Old School Amber CRT Terminal.
      Runs zero-VRAM CPU models (Qwen 2.5 3B / 1.5B) directly against your Ollama container.
  port_map: "5000"
  scheme: "http"
  index: "/"

services:
  glados:
    image: glados-agent:latest
    build:
      context: https://github.com/Fl1pMoniz/local-os-agent.git#feat/docker-zimaos
      dockerfile: Dockerfile
    container_name: glados-agent
    restart: unless-stopped
    ports:
      - "5000:5000"
    environment:
      - CONTAINER_MODE=true
      - UI_HOST=0.0.0.0
      - UI_PORT=5000
      - HEADLESS=true
      - LLM_BASE_URL=http://host.docker.internal:11434/v1
      - LLM_MODEL=qwen2.5:3b
      - LLM_API_KEY=ollama
      - ZIMAOS_HOST=http://host.docker.internal
      - LOG_LEVEL=INFO
    extra_hosts:
      - "host.docker.internal:host-gateway"
    volumes:
      - /DATA/AppData/glados/captures:/app/captures
      - /DATA/AppData/glados/logs:/app/logs
    healthcheck:
      test: ["CMD", "curl", "-f", "http://127.0.0.1:5000/api/state"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
    x-casaos:
      ports:
        - container: "5000"
          description:
            en_us: "Aperture CRT Web Console"
      volumes:
        - container: /app/captures
          description:
            en_us: "Video highlights & captures directory"
        - container: /app/logs
          description:
            en_us: "System execution and telemetry logs"
      envs:
        - container: LLM_BASE_URL
          description:
            en_us: "Ollama container API endpoint (default: http://host.docker.internal:11434/v1)"
        - container: LLM_MODEL
          description:
            en_us: "Cherry-picked CPU model tag for Intel i5-8400 (recommended: qwen2.5:3b or qwen2.5:1.5b)"
        - container: ZIMAOS_HOST
          description:
            en_us: "ZimaOS dashboard host URL"
```

6. Click **Submit**.
7. ZimaOS will automatically detect the `x-casaos` metadata and populate the interface:
   - **App Name**: Aperture GLaDOS
   - **Icon**: Authentic ASCII Aperture Science Diaphragm badge
   - **Web UI Port**: 5000
   - **Host Gateway**: Configured to connect to your host's services
8. In the **Environment Variables** section, confirm the defaults:
   - `LLM_BASE_URL`: `http://host.docker.internal:11434/v1` (routes directly to your host's port 11434 where Ollama is listening).
   - `LLM_MODEL`: `qwen2.5:3b` (or `qwen2.5:1.5b`).
   - `ZIMAOS_HOST`: `http://host.docker.internal`
9. Click **Install**.
10. ZimaOS will fetch the build files, build the container, and place the **Aperture GLaDOS** tile directly on your dashboard.

---

## 4. Step 3: Accessing the Terminal

1. Click on the **Aperture GLaDOS** icon on your ZimaOS dashboard.
2. The full-screen Amber CRT terminal interface will open at:
   ```
   http://192.168.1.123:5000
   ```
3. Test your connection by entering any directive into the console:
   - `hw` : View live CPU and memory telemetry.
   - `server` : Inspect ZimaOS health and running microservices.
   - `flight AA100` : Track live airspace radar.
   - `ai stats` : Display AI inference metrics and token latency.
   - `help` : View the complete directive directory.

---

## 5. Troubleshooting & Tips

- **Ollama Connection Test**:
  To confirm that your GLaDOS container can communicate with your Ollama container, run from your server terminal:
  ```bash
  docker exec -it glados-agent curl -s http://host.docker.internal:11434/api/tags
  ```
  It should return a JSON response containing your downloaded `qwen2.5:3b` model.

- **Changing the Model Later**:
  Click the three dots (`...`) on the **Aperture GLaDOS** tile on your ZimaOS dashboard, select **Settings**, change `LLM_MODEL` to any model you have pulled in Ollama, and click **Save**.
