"""GLaDOS AI Core Telemetry & Neural Inference Performance Tracker.

Tracks live metrics for the local language model and neural subsystems:
- AI Process RAM usage (Ollama, llama-server, LM Studio, Piper TTS, GLaDOS host)
- Model VRAM footprint and parameter quantization
- Total session tokens produced (prompt vs output/completion)
- Inference generation rate (tokens per second, peak, average)
- Roundtrip inference latency (ms)
- Context window capacity & utilization
- Subsystem health (Voice synthesis, Optical Vision, Aperture Core)
"""

import logging
import os
import threading
import time
from typing import Any

import psutil
import requests

from config import config
from tools import register_tool

logger = logging.getLogger("local_os_agent.tools.ai_telemetry")

_working_ollama_base_url: str | None = None
_last_probe_time: float = 0.0


def get_working_ollama_base_url() -> str:
    """Probes and returns the first reachable Ollama base URL across Docker and LAN."""
    global _working_ollama_base_url, _last_probe_time
    now = time.time()
    if _working_ollama_base_url and (now - _last_probe_time < 30.0):
        return _working_ollama_base_url

    candidates: list[str] = []
    if config.llm_base_url:
        candidates.append(config.llm_base_url)
    candidates.extend(
        [
            "http://host.docker.internal:11434/v1",
            "http://172.17.0.1:11434/v1",
            "http://192.168.1.123:11434/v1",
            "http://ollama:11434/v1",
            "http://localhost:11434/v1",
        ]
    )

    try:
        from tools.zimaos import get_zimaos_host
        import urllib.parse

        zh = get_zimaos_host()
        parsed = urllib.parse.urlparse(zh)
        if parsed.hostname:
            candidates.append(f"http://{parsed.hostname}:11434/v1")
    except Exception:
        pass

    seen: set[str] = set()
    for cand in candidates:
        norm = cand.rstrip("/")
        if norm in seen:
            continue
        seen.add(norm)
        base = norm[:-3] if norm.endswith("/v1") else norm
        test_url = f"{base}/api/tags"
        try:
            r = requests.get(test_url, timeout=0.6)
            if r.status_code == 200:
                _working_ollama_base_url = norm
                _last_probe_time = now
                config.llm_base_url = norm
                return norm
        except Exception:
            continue

    fallback = config.llm_base_url or "http://host.docker.internal:11434/v1"
    _working_ollama_base_url = fallback
    _last_probe_time = now
    return fallback


class AITelemetryTracker:
    """Thread-safe telemetry engine tracking real-time LLM performance and memory."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.session_start = time.time()
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_tokens = 0
        self.total_queries = 0
        self.total_latency_s = 0.0

        self.last_prompt_tokens = 0
        self.last_completion_tokens = 0
        self.last_latency_s = 0.0
        self.last_tokens_per_sec = 0.0
        self.peak_tokens_per_sec = 0.0
        self.avg_tokens_per_sec = 0.0

        self.last_context_tokens = 0
        self.active_model_name = config.llm_model

        self._cached_ollama_info: dict[str, Any] | None = None
        self._last_ollama_poll = 0.0
        self._cached_ram_info: dict[str, Any] | None = None
        self._last_ram_poll = 0.0

    def record_inference(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        latency_s: float,
        model: str | None = None,
        context_tokens: int | None = None,
    ) -> None:
        """Records metrics from an executed LLM completion call."""
        with self._lock:
            p_tok = max(0, int(prompt_tokens))
            c_tok = max(0, int(completion_tokens))
            tot_tok = p_tok + c_tok
            lat_s = max(0.01, float(latency_s))

            self.total_prompt_tokens += p_tok
            self.total_completion_tokens += c_tok
            self.total_tokens += tot_tok
            self.total_queries += 1
            self.total_latency_s += lat_s

            self.last_prompt_tokens = p_tok
            self.last_completion_tokens = c_tok
            self.last_latency_s = lat_s

            tps = round(c_tok / lat_s, 1) if c_tok > 0 else 0.0
            self.last_tokens_per_sec = tps
            self.peak_tokens_per_sec = max(self.peak_tokens_per_sec, tps)

            if self.total_latency_s > 0 and self.total_completion_tokens > 0:
                self.avg_tokens_per_sec = round(
                    self.total_completion_tokens / self.total_latency_s, 1
                )

            if context_tokens is not None:
                self.last_context_tokens = max(0, int(context_tokens))
            elif p_tok > 0:
                self.last_context_tokens = p_tok

            if model:
                self.active_model_name = str(model).strip()

    def get_ai_ram_usage(self) -> dict[str, Any]:
        """
        Scans active local processes using psutil to calculate precise AI memory footprint.
        Includes Ollama, llama-server, LM Studio, and the GLaDOS agent process.
        """
        now = time.time()
        if self._cached_ram_info and (now - self._last_ram_poll < 2.0):
            return self._cached_ram_info

        llm_runner_rss = 0
        llm_pids: list[int] = []
        runner_names: set[str] = set()

        target_keywords = (
            "ollama",
            "llama-server",
            "ollama_llama_server",
            "lmstudio",
            "lms",
            "vllm",
        )

        try:
            for p in psutil.process_iter(["name", "pid"]):
                try:
                    p_name = (p.info["name"] or "").lower()
                    if any(kw in p_name for kw in target_keywords):
                        mem = p.memory_info()
                        if mem:
                            llm_runner_rss += mem.rss
                            llm_pids.append(p.info["pid"])
                            runner_names.add(p.info["name"])
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception:
            pass

        host_rss = 0
        try:
            host_rss = psutil.Process().memory_info().rss
        except Exception:
            pass

        total_ai_rss = llm_runner_rss + host_rss
        llm_mb = round(llm_runner_rss / (1024 * 1024), 1)
        host_mb = round(host_rss / (1024 * 1024), 1)
        total_mb = round(total_ai_rss / (1024 * 1024), 1)

        primary_runner = (
            "Ollama"
            if any("ollama" in n.lower() or "llama" in n.lower() for n in runner_names)
            else ("LM Studio" if any("lms" in n.lower() for n in runner_names) else "LLM Runtime")
        )

        if llm_runner_rss == 0 and self._cached_ollama_info:
            cached_status = self._cached_ollama_info.get("status")
            if cached_status in ("LOADED", "ONLINE"):
                primary_runner = "Ollama (Container)"
                llm_mb = round(float(self._cached_ollama_info.get("vram_mb", 0)), 1)
                total_ai_rss = int(llm_mb * 1024 * 1024) + host_rss
                total_mb = round(total_ai_rss / (1024 * 1024), 1)
            elif cached_status == "STANDBY":
                primary_runner = "Ollama (Standby)"

        res = {
            "total_ai_ram_mb": total_mb,
            "llm_runner_ram_mb": llm_mb,
            "host_agent_ram_mb": host_mb,
            "llm_pids": llm_pids,
            "runner_name": primary_runner
            if (llm_runner_rss > 0 or llm_mb > 0)
            else "Offline / Standby",
            "active_processes": len(llm_pids) + 1,
        }
        self._cached_ram_info = res
        self._last_ram_poll = now
        return res

    def get_ollama_model_info(self) -> dict[str, Any]:
        """Queries local Ollama runtime API (/api/ps and /api/tags) to fetch active model parameters."""
        now = time.time()
        if self._cached_ollama_info and (now - self._last_ollama_poll < 2.0):
            return self._cached_ollama_info

        endpoint = get_working_ollama_base_url()
        base = endpoint.rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]
        ps_url = f"{base}/api/ps"
        tags_url = f"{base}/api/tags"

        model_info: dict[str, Any] = {
            "name": self.active_model_name,
            "parameter_size": "3.2B" if "3b" in self.active_model_name.lower() else "Local",
            "quantization": "Q4_K_M",
            "vram_mb": 0,
            "context_length": config.llm_num_ctx,
            "status": "ONLINE",
        }

        # 1. First attempt /api/ps to see if model weights are resident in RAM/VRAM
        try:
            resp = requests.get(ps_url, timeout=1.5)
            if resp.status_code == 200:
                data = resp.json()
                models = data.get("models", [])
                if models:
                    m = models[0]
                    model_info["name"] = m.get("name", self.active_model_name)
                    details = m.get("details", {})
                    if details.get("parameter_size"):
                        model_info["parameter_size"] = details.get("parameter_size")
                    if details.get("quantization_level"):
                        model_info["quantization"] = details.get("quantization_level")
                    if m.get("size_vram"):
                        model_info["vram_mb"] = round(m["size_vram"] / (1024 * 1024))
                    elif m.get("size"):
                        model_info["vram_mb"] = round(m["size"] / (1024 * 1024))
                    if m.get("context_length"):
                        model_info["context_length"] = m.get("context_length")
                    model_info["status"] = "LOADED"
                    self.active_model_name = model_info["name"]
                    self._cached_ollama_info = model_info
                    self._last_ollama_poll = now
                    return model_info
        except Exception:
            pass

        # 2. Fallback: Query /api/tags for installed models on the Ollama host
        try:
            resp_tags = requests.get(tags_url, timeout=1.5)
            if resp_tags.status_code == 200:
                data_tags = resp_tags.json()
                models_tags = data_tags.get("models", [])
                if models_tags:
                    target_model = None
                    target_names = [self.active_model_name.lower(), config.llm_model.lower()]
                    for m in models_tags:
                        m_name = m.get("name", "").lower()
                        if any(tn in m_name or m_name in tn for tn in target_names):
                            target_model = m
                            break
                    if not target_model:
                        target_model = models_tags[0]

                    model_info["name"] = target_model.get("name", self.active_model_name)
                    details = target_model.get("details", {})
                    if details.get("parameter_size"):
                        model_info["parameter_size"] = details.get("parameter_size")
                    if details.get("quantization_level"):
                        model_info["quantization"] = details.get("quantization_level")
                    if target_model.get("size"):
                        model_info["vram_mb"] = round(target_model["size"] / (1024 * 1024))
                    model_info["status"] = "STANDBY"
                    self.active_model_name = model_info["name"]
        except Exception:
            pass

        self._cached_ollama_info = model_info
        self._last_ollama_poll = now
        return model_info

    def get_telemetry(self) -> dict[str, Any]:
        """Returns structured dictionary of all GLaDOS AI performance and hardware metrics."""
        with self._lock:
            p_tok = self.total_prompt_tokens
            c_tok = self.total_completion_tokens
            tot_tok = self.total_tokens
            queries = self.total_queries
            last_p = self.last_prompt_tokens
            last_c = self.last_completion_tokens
            last_lat_ms = round(self.last_latency_s * 1000, 1)
            last_tps = self.last_tokens_per_sec
            peak_tps = self.peak_tokens_per_sec
            avg_tps = self.avg_tokens_per_sec
            ctx_tokens = self.last_context_tokens

        model_data = self.get_ollama_model_info()
        ram_data = self.get_ai_ram_usage()

        # Check Aperture Subsystems
        piper_path = config.base_dir / "voice" / "models" / "glados.onnx"
        voice_subsys = "Piper VITS GLaDOS" if piper_path.exists() else "SAPI5 / OS Native"

        vision_key = os.getenv("GEMINI_API_KEY")
        vision_subsys = "Gemini Optical Matrix" if vision_key else "Local Optical Sensor"

        ctx_max = model_data.get("context_length", config.llm_num_ctx)
        ctx_pct = round((ctx_tokens / max(1, ctx_max)) * 100.0, 1) if ctx_tokens > 0 else 0.0

        return {
            "model_name": model_data.get("name", self.active_model_name),
            "parameter_size": model_data.get("parameter_size", "3.2B"),
            "quantization": model_data.get("quantization", "Q4_K_M"),
            "model_vram_mb": model_data.get("vram_mb", 0),
            "model_status": model_data.get("status", "ONLINE"),
            "ai_ram_total_mb": ram_data["total_ai_ram_mb"],
            "ai_ram_runner_mb": ram_data["llm_runner_ram_mb"],
            "ai_ram_host_mb": ram_data["host_agent_ram_mb"],
            "ai_runner_name": ram_data["runner_name"],
            "total_tokens_produced": tot_tok,
            "prompt_tokens": p_tok,
            "completion_tokens": c_tok,
            "total_queries": queries,
            "last_prompt_tokens": last_p,
            "last_completion_tokens": last_c,
            "last_latency_ms": last_lat_ms,
            "tokens_per_sec": last_tps,
            "peak_tokens_per_sec": peak_tps,
            "avg_tokens_per_sec": avg_tps,
            "context_tokens": ctx_tokens,
            "context_max": ctx_max,
            "context_percent": ctx_pct,
            "voice_subsystem": voice_subsys,
            "vision_subsystem": vision_subsys,
        }


# Global singleton tracker instance
ai_tracker = AITelemetryTracker()


def format_glados_ai_hud(ai_data: dict[str, Any] | None = None) -> list[str]:
    """
    Renders the clinical 70-column Aperture Science ASCII card section
    for GLaDOS AI stats (AI RAM, Tokens Produced, Tokens/sec, Model Info).
    """
    data = ai_data or ai_tracker.get_telemetry()

    model_name = data.get("model_name", "glados:3b")
    param_size = data.get("parameter_size", "3.2B")
    quant = data.get("quantization", "Q4_K_M")
    status = data.get("model_status", "ONLINE")
    engine_info = f"{model_name} ({param_size} {quant}) [* {status}]"

    ai_ram_mb = data.get("ai_ram_total_mb", 0.0)
    runner_mb = data.get("ai_ram_runner_mb", 0.0)
    host_mb = data.get("ai_ram_host_mb", 0.0)
    runner_name = data.get("ai_runner_name", "Ollama")
    if runner_mb > 0:
        ai_ram_str = (
            f"{ai_ram_mb:,.1f} MB ({runner_name}: {runner_mb:,.1f}M | Host: {host_mb:,.1f}M)"
        )
    else:
        ai_ram_str = f"{ai_ram_mb:,.1f} MB (Host: {host_mb:,.1f}M)"

    vram_mb = data.get("model_vram_mb", 0)
    if vram_mb > 0:
        vram_str = f"{vram_mb:,.0f} MB (Dedicated Tensor Weights)"
    else:
        vram_str = "Dynamic UMA / Shared System Memory"

    tot_tokens = data.get("total_tokens_produced", 0)
    p_tokens = data.get("prompt_tokens", 0)
    c_tokens = data.get("completion_tokens", 0)
    if tot_tokens > 0:
        tokens_str = f"{tot_tokens:,} produced (In: {p_tokens:,} | Out: {c_tokens:,})"
    else:
        tokens_str = "0 produced (Inference Core Standby)"

    tps = data.get("tokens_per_sec", 0.0)
    peak_tps = data.get("peak_tokens_per_sec", 0.0)
    if tps > 0:
        tps_pct = min(100.0, (tps / 60.0) * 100.0)
        filled = int(round((tps_pct / 100.0) * 12))
        tps_bar = "█" * filled + "░" * (12 - filled)
        rate_str = f"{tps:>5.1f} tok/s [{tps_bar}] (Peak: {peak_tps:>4.1f})"
    else:
        rate_str = "Standby (Ready for test subject prompt)"

    lat_ms = data.get("last_latency_ms", 0.0)
    avg_tps = data.get("avg_tokens_per_sec", 0.0)
    if lat_ms > 0:
        lat_str = f"{lat_ms:,.0f} ms (Avg Session Speed: {avg_tps:.1f} tok/s)"
    else:
        lat_str = "0 ms (Ready for testing cycle)"

    ctx_tokens = data.get("context_tokens", 0)
    ctx_max = data.get("context_max", 8192)
    ctx_pct = data.get("context_percent", 0.0)
    if ctx_tokens > 0:
        filled_ctx = int(round((ctx_pct / 100.0) * 12))
        ctx_bar = "█" * filled_ctx + "░" * (12 - filled_ctx)
        ctx_str = f"{ctx_tokens:,} / {ctx_max:,} tok ({ctx_pct}%) [{ctx_bar}]"
    else:
        ctx_str = f"0 / {ctx_max:,} tokens (0.0%) [░░░░░░░░░░░░]"

    voice_sub = data.get("voice_subsystem", "Piper VITS GLaDOS")
    vision_sub = data.get("vision_subsystem", "Optical Online")
    subsys_str = f"Voice: {voice_sub[:14]} | Vision: {vision_sub[:14]}"

    lines = [
        "|            GLaDOS AI NEURAL CORE & INFERENCE TELEMETRY             |",
        "+--------------------------------------------------------------------+",
        f"| Neural Engine     : {engine_info[:46]:<46} |",
        f"| AI RAM Footprint  : {ai_ram_str[:46]:<46} |",
        f"| Model VRAM Alloc  : {vram_str[:46]:<46} |",
        f"| Session Tokens    : {tokens_str[:46]:<46} |",
        f"| Generation Rate   : {rate_str[:46]:<46} |",
        f"| Inference Latency : {lat_str[:46]:<46} |",
        f"| Context Window    : {ctx_str[:46]:<46} |",
        f"| Aperture Subsystem: {subsys_str[:46]:<46} |",
        "+--------------------------------------------------------------------+",
    ]
    return lines


@register_tool
def get_glados_ai_stats() -> dict[str, Any]:
    """
    Returns real-time GLaDOS AI neural performance metrics including AI RAM footprint,
    session tokens produced, generation rate (tok/s), model VRAM allocation, and context utilization.
    """
    data = ai_tracker.get_telemetry()
    lines = format_glados_ai_hud(data)
    box = ["+--------------------------------------------------------------------+"] + lines
    card_str = "\n".join(box)
    return {
        "success": True,
        "metrics": data,
        "terminal_card": card_str,
        "message": f"GLaDOS AI Engine {data['model_name']} ({data['parameter_size']}) nominal. Generation rate: {data['tokens_per_sec']} tok/s.",
    }
