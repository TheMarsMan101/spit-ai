#!/usr/bin/env python3
"""
Spit AI — Minecraft ↔ Ollama Chat Bridge
─────────────────────────────────────────
Monitors Minecraft Java 1.21.5 chat for "@Spit" prompts,
sends them to a local Ollama instance, and types the
response back into Minecraft chat using xdotool.

Features a threaded queue system so multiple players can
query at the same time without messages being lost.

Requirements:
    pip install requests
    sudo apt install xdotool

Usage:
    python3 bridge.py
    python3 bridge.py --model llama3.1:8b --log ~/.minecraft/logs/latest.log
"""

import re
import time
import subprocess
import requests
import json
import argparse
import signal
import sys
import threading
from queue import Queue, Empty
from pathlib import Path
from datetime import datetime

# ──────────────────────────── defaults ────────────────────────────

OLLAMA_URL       = "http://localhost:11434/api/generate"
DEFAULT_MODEL    = "llama3.1:8b"
MINECRAFT_LOG    = Path.home() / ".minecraft" / "logs" / "latest.log"
TRIGGER          = "@spit"
BOT_PREFIX       = "[Spit] "
MC_CHAT_LIMIT    = 256
MAX_CHUNKS       = 5          # max messages per response (anti-spam)
COOLDOWN_SEC     = 1          # per-player cooldown in seconds
MAX_TOKENS       = 200        # keep responses chat-friendly
MAX_QUEUE_SIZE   = 20         # max pending requests before rejecting
NUM_WORKERS      = 2          # number of Ollama worker threads
# NOTE: Adding more workers has no real effect — Ollama processes one
# generation at a time (GPU-bound). Worker 2 only helps by pre-sending
# the next request while Worker 1 types into Minecraft. Leave at 2
# unless you've configured OLLAMA_NUM_PARALLEL and have enough VRAM.
SYSTEM_PROMPT    = (
    "You are Spit, a helpful AI assistant in a Minecraft in-game chat, "
    "powered by Ollama. Answer any topic the user asks about. Only assume "
    "Minecraft context when the question is genuinely ambiguous (e.g. "
    "'where do I find diamonds'). If the question is clearly about the "
    "real world, answer normally. Keep answers concise (1-3 sentences). "
    "No markdown formatting. No asterisks, no bullet points — plain text only."
)

# ──────────────────────────── colour helpers ──────────────────────

RESET  = "\033[0m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
DIM    = "\033[2m"
BLUE   = "\033[94m"

def log_info(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"{DIM}{ts}{RESET}  {GREEN}INFO{RESET}   {msg}")

def log_warn(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"{DIM}{ts}{RESET}  {YELLOW}WARN{RESET}   {msg}")

def log_err(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"{DIM}{ts}{RESET}  {RED}ERROR{RESET}  {msg}")

def log_chat(player, text):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"{DIM}{ts}{RESET}  {CYAN}CHAT{RESET}   <{player}> {text}")

def log_queue(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"{DIM}{ts}{RESET}  {BLUE}QUEUE{RESET}  {msg}")

# ──────────────────────────── minecraft window ────────────────────

def find_mc_window():
    """Return the X window ID for Minecraft, or None."""
    try:
        result = subprocess.run(
            ["xdotool", "search", "--name", "Minecraft"],
            capture_output=True, text=True, timeout=5
        )
        ids = [w for w in result.stdout.strip().split("\n") if w]
        return ids[0] if ids else None
    except FileNotFoundError:
        log_err("xdotool is not installed!  Run:  sudo apt install xdotool")
        sys.exit(1)
    except Exception as exc:
        log_err(f"xdotool error: {exc}")
        return None

# Lock to prevent multiple threads from typing into MC at the same time
chat_send_lock = threading.Lock()

def send_mc_chat(window_id: str, text: str):
    """Open the Minecraft chat box, type a message, and press Enter."""
    # Activate the window (no --sync, it hangs on Cinnamon)
    subprocess.run(["xdotool", "windowactivate", window_id],
                    capture_output=True, timeout=5)
    time.sleep(0.4)

    # Press 't' to open chat
    subprocess.run(["xdotool", "key", "--clearmodifiers", "t"],
                    capture_output=True)
    time.sleep(0.4)

    # Type the message
    subprocess.run(
        ["xdotool", "type", "--clearmodifiers", "--delay", "8", "--", text],
        capture_output=True
    )
    time.sleep(0.1)

    # Press Enter to send
    subprocess.run(["xdotool", "key", "--clearmodifiers", "Return"],
                    capture_output=True)
    time.sleep(0.35)

def send_response(window_id: str, player: str, response_text: str):
    """Split a response into MC-chat-safe chunks and send each one."""
    text = response_text.replace("\n", " ").strip()
    prefix = BOT_PREFIX
    max_body = MC_CHAT_LIMIT - len(prefix) - 1

    chunks = []
    while text:
        if len(text) <= max_body:
            chunks.append(text)
            break
        idx = text.rfind(" ", 0, max_body)
        if idx == -1:
            idx = max_body
        chunks.append(text[:idx])
        text = text[idx:].strip()

    # Lock so only one thread types at a time
    with chat_send_lock:
        for i, chunk in enumerate(chunks[: MAX_CHUNKS]):
            tag = prefix if i == 0 else f"{BOT_PREFIX}… "
            send_mc_chat(window_id, f"{tag}{chunk}")
            time.sleep(0.6)

        if len(chunks) > MAX_CHUNKS:
            send_mc_chat(window_id, f"{prefix}(response truncated)")

# ──────────────────────────── ollama ──────────────────────────────

def query_ollama(prompt: str, model: str) -> str:
    """Send a prompt to the local Ollama REST API and return the text."""
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={
                "model": model,
                "prompt": prompt,
                "system": SYSTEM_PROMPT,
                "stream": False,
                "options": {
                    "num_predict": MAX_TOKENS,
                },
            },
            timeout=120,
        )
        resp.raise_for_status()
        answer = resp.json().get("response", "").strip()
        if not answer:
            return "(Ollama returned an empty response.)"
        return answer
    except requests.ConnectionError:
        return "(Could not connect to Ollama — is it running?)"
    except requests.Timeout:
        return "(Ollama took too long to respond.)"
    except Exception as exc:
        return f"(Ollama error: {exc})"

# ──────────────────────────── queue + workers ─────────────────────

request_queue = Queue(maxsize=MAX_QUEUE_SIZE)

def worker(worker_id: int, model: str):
    """Worker thread that pulls prompts from the queue and processes them."""
    log_info(f"Worker {worker_id} started")
    while True:
        try:
            item = request_queue.get(timeout=1)
        except Empty:
            continue

        if item is None:
            break  # poison pill — shutdown

        player = item["player"]
        prompt = item["prompt"]
        log_info(f"Worker {worker_id} processing [{player}]: {prompt[:50]}…")

        wid = find_mc_window()
        if not wid:
            log_err(f"Worker {worker_id}: Cannot find Minecraft window — skipping")
            request_queue.task_done()
            continue

        t0 = time.time()
        answer = query_ollama(prompt, model)
        elapsed = time.time() - t0
        log_info(f"Worker {worker_id} got response ({elapsed:.1f}s, {len(answer)} chars)")

        send_response(wid, player, answer)
        log_info(f"Worker {worker_id} sent response for [{player}] ✓")

        request_queue.task_done()

# ──────────────────────────── log parsing ─────────────────────────

CHAT_RE = re.compile(
    r"\[[\d:]+\]\s+\[.+?/INFO\].*?:\s+\[CHAT\]\s+<(\w+)>\s+(.*)"
)

CHAT_RE_ALT = re.compile(
    r"\[[\d:]+\]\s+\[.+?/INFO\].*?:\s+<(\w+)>\s+(.*)"
)

def parse_chat_line(line: str):
    """Return (player_name, message) or (None, None)."""
    m = CHAT_RE.search(line)
    if not m:
        m = CHAT_RE_ALT.search(line)
    if m:
        return m.group(1), m.group(2)
    return None, None

def tail_file(path: Path):
    """Yield new lines appended to *path*, starting from end of file."""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        fh.seek(0, 2)
        while True:
            line = fh.readline()
            if line:
                yield line.rstrip("\n")
            else:
                time.sleep(0.1)

# ──────────────────────────── main loop ───────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Spit AI — Minecraft ↔ Ollama chat bridge (queued)."
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL,
        help=f"Ollama model name (default: {DEFAULT_MODEL})"
    )
    parser.add_argument(
        "--log", default=str(MINECRAFT_LOG),
        help="Path to Minecraft's latest.log"
    )
    parser.add_argument(
        "--trigger", default=TRIGGER,
        help=f'Trigger phrase (default: "{TRIGGER}")'
    )
    parser.add_argument(
        "--ignore", nargs="*", default=[],
        help="Player names whose @ai messages should be ignored"
    )
    parser.add_argument(
        "--self-name", default=None,
        help="Your Minecraft username (auto-ignored to prevent loops)"
    )
    parser.add_argument(
        "--workers", type=int, default=NUM_WORKERS,
        help=f"Number of Ollama worker threads (default: {NUM_WORKERS})"
    )
    args = parser.parse_args()

    log_path = Path(args.log)
    if not log_path.exists():
        log_err(f"Log file not found: {log_path}")
        log_err("Make sure Minecraft is running first!")
        sys.exit(1)

    ignored = {n.lower() for n in args.ignore}
    if args.self_name:
        ignored.add(args.self_name.lower())

    # ── verify Ollama ──
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=5)
        models = [m["name"] for m in r.json().get("models", [])]
        if models:
            log_info(f"Ollama is running — available models: {', '.join(models)}")
        else:
            log_warn("Ollama is running but no models found. Pull one first.")
    except Exception:
        log_warn("Could not reach Ollama at localhost:11434 — is it running?")

    # ── verify xdotool + MC window ──
    wid = find_mc_window()
    if wid:
        log_info(f"Found Minecraft window (id {wid})")
    else:
        log_warn("Minecraft window not found yet — will retry when needed.")

    print()
    print()
    print(f"       \033[33m          ▄▄    ▄▄{RESET}")
    print(f"       \033[33m         ▐{YELLOW}▓▓\033[33m▌  ▐{YELLOW}▓▓\033[33m▌{RESET}")
    print(f"       \033[33m         ▐{YELLOW}▓▓\033[33m▌  ▐{YELLOW}▓▓\033[33m▌{RESET}")
    print(f"       \033[33m         ▐{YELLOW}▓▓\033[33m▙▄▄▟{YELLOW}▓▓\033[33m▌{RESET}")
    print(f"       \033[33m         ▐{YELLOW}▓▓▓▓▓▓▓▓\033[33m▌{RESET}")
    print(f"       \033[33m         ▐{YELLOW}▓\033[97m●\033[90m {YELLOW}▓▓▓▓▓\033[33m▜▄{RESET}")
    print(f"       \033[33m         ▐{YELLOW}▓▓▓\033[33m▙{YELLOW}▓▓▓▓▓\033[33m▀{RESET}")
    print(f"       \033[33m         ▐{YELLOW}▓▓▓\033[33m▌▀▜{YELLOW}▓▓\033[33m▀{CYAN}░▒▓  ·{RESET}")
    print(f"       \033[33m         ▐{YELLOW}▓▓▓\033[33m▌     {CYAN} ·  ░{RESET}")
    print(f"       \033[33m         ▐{YELLOW}▓▓▓\033[33m▌       {CYAN}·{RESET}")
    print(f"       \033[33m         ▐{YELLOW}▓▓▓\033[33m▌{RESET}")
    print(f"       \033[33m          ▀▀▀{RESET}")
    print(f"\033[1m{CYAN}            S P I T  A I{RESET}")
    print(f"{DIM}      Made with AI. Powered by AI.{RESET}")
    print(f"{DIM}            Spitting facts.{RESET}")
    print()

    # Build banner with proper alignment
    W = 42  # visible width between ║ bars
    def banner_line(text="", color_len=0):
        """Print a banner line, padding to W visible chars."""
        pad = W - len(text) + color_len
        print(f"  ║ {text}{' ' * pad}║")

    model_str = args.model
    trigger_str = args.trigger

    print(f"  ╔{'═' * (W + 1)}╗")
    banner_line()
    banner_line(f"  {CYAN}Spit AI{RESET}  (running)", color_len=len(CYAN) + len(RESET))
    banner_line()
    banner_line(f"  Model:   {model_str}")
    banner_line(f"  Trigger: {trigger_str}")
    banner_line(f"  Workers: {args.workers}")
    banner_line(f"  Queue:   max {MAX_QUEUE_SIZE} pending")
    banner_line(f"  Log:     .../{log_path.name}")
    banner_line(f"  License: MIT")
    banner_line()
    banner_line(f"  Type {YELLOW}{trigger_str} <prompt>{RESET} in Minecraft chat", color_len=len(YELLOW) + len(RESET))
    banner_line(f"  Press {YELLOW}Ctrl+C{RESET} to stop", color_len=len(YELLOW) + len(RESET))
    banner_line()
    print(f"  ╚{'═' * (W + 1)}╝")
    print()

    # ── start worker threads ──
    worker_threads = []
    for i in range(args.workers):
        t = threading.Thread(target=worker, args=(i + 1, args.model), daemon=True)
        t.start()
        worker_threads.append(t)

    # Graceful shutdown
    def on_sigint(sig, frame):
        print(f"\n{DIM}Shutting down… draining queue…{RESET}")
        for _ in worker_threads:
            request_queue.put(None)
        for t in worker_threads:
            t.join(timeout=3)
        print(f"{DIM}Goodbye!{RESET}")
        sys.exit(0)
    signal.signal(signal.SIGINT, on_sigint)

    # Per-player cooldown tracking
    player_cooldowns = {}

    for line in tail_file(log_path):
        player, message = parse_chat_line(line)
        if player is None:
            continue

        if player.lower() in ignored:
            continue

        # Check for trigger anywhere in the message
        stripped = message.strip()
        lower_msg = stripped.lower()
        trigger_pos = lower_msg.find(args.trigger.lower())
        if trigger_pos == -1:
            continue

        prompt = stripped[trigger_pos + len(args.trigger) :].strip()
        # Strip leading punctuation/filler like commas, colons, "can you"
        prompt = re.sub(r'^[,:\s]+', '', prompt)
        if not prompt:
            continue

        # Per-player cooldown
        now = time.time()
        last = player_cooldowns.get(player.lower(), 0)
        if now - last < COOLDOWN_SEC:
            log_warn(f"Cooldown — skipping prompt from {player}")
            continue
        player_cooldowns[player.lower()] = now

        log_chat(player, prompt)

        # Enqueue
        if request_queue.full():
            log_warn(f"Queue full ({MAX_QUEUE_SIZE}) — dropping request from {player}")
            continue

        position = request_queue.qsize() + 1
        request_queue.put({
            "player": player,
            "prompt": prompt,
            "time": now,
            "position": position,
        })
        log_queue(f"Queued [{player}] (position {position}, {request_queue.qsize()} pending)")


if __name__ == "__main__":
    main()
