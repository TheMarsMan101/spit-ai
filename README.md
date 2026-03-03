# 🦙 Spit AI

**Made with AI. Powered by AI. Spitting facts.**

Talk to an AI directly from Minecraft chat. Spit AI bridges your Minecraft Java client to a local [Ollama](https://ollama.com) instance — when anyone in chat mentions `@Spit`, the prompt is sent to your local LLM and the response is typed back into the game.

```
<Steve>          Hey @Spit, where do I find diamonds?
<SpitAI_Bot>     [Spit] Mine at Y=-59 for the best concentration. Use Fortune III on your pickaxe to maximize drops.
```

---

## How It Works

```
┌─────────────┐   latest.log    ┌─────────────┐   HTTP API    ┌─────────┐
│  Minecraft   │ ──────────────▶ │  bridge.py   │ ────────────▶│  Ollama  │
│  Java 1.21.5 │ ◀────────────── │  (Python)    │ ◀────────────│  (local) │
└─────────────┘   xdotool keys  └─────────────┘   response    └─────────┘
```

1. **Monitors** Minecraft's `latest.log` file in real time for new chat messages
2. **Detects** `@Spit` anywhere in a message — beginning, middle, or end
3. **Extracts** everything after `@Spit` as the prompt
4. **Sends** the prompt to Ollama's local REST API (`localhost:11434`)
5. **Types** the response back into Minecraft chat via `xdotool`

---

## Features

- **Natural trigger** — `@Spit` works anywhere in the message, not just at the start. Say `"Hey @Spit, what's the weather like on Mars?"` or `"Does anyone know, @Spit, how redstone repeaters work?"` and it just works.
- **Threaded queue system** — multiple players can send prompts at the same time. Requests are queued (up to 20 by default) and processed in order. Nothing gets lost.
- **Per-player cooldown** — prevents spam with a configurable per-player cooldown timer.
- **Smart chunking** — long responses are automatically split across multiple messages to stay within Minecraft's 256-character chat limit.
- **Context-aware** — ambiguous questions like `"where do I find iron?"` default to Minecraft context, while clearly real-world questions get normal answers.
- **Runs 100% locally** — no API keys, no cloud services, no data leaving your machine. Just Ollama and a Python script.
- **Any Ollama model** — use Llama, Mistral, Gemma, Phi, or [any model Ollama supports](https://ollama.com/library).

---

## Prerequisites

| Requirement | Notes |
|---|---|
| **Python 3.8+** | Pre-installed on most Linux distros |
| **Ollama** | [Install from ollama.com](https://ollama.com/download) |
| **An Ollama model** | e.g. `ollama pull llama3.1:8b` |
| **xdotool** | For simulating keyboard input into Minecraft |
| **requests** (Python) | HTTP library for Ollama API calls |
| **Minecraft Java Edition** | Tested on 1.21.5 with Fabric |
| **Dedicated Minecraft account** | A separate account for the bot (see [Important](#%EF%B8%8F-important-dedicated-account-required)) |
| **X11 display server** | Required by xdotool — works on most Linux desktops (Wayland is not supported) |

> **Tested on:** Linux Mint 22.3 (Cinnamon / X11) with Minecraft Java 1.21.5 (Fabric), Ollama running llama3.1:8b. Should work on any Linux distribution with X11.

---

## Installation

### 1. Install system dependencies

```bash
sudo apt install xdotool
pip install requests --break-system-packages
```

### 2. Install Ollama and pull a model

```bash
# Install Ollama (if you haven't already)
curl -fsSL https://ollama.com/install.sh | sh

# Pull a model
ollama pull llama3.1:8b
```

### 3. Download Spit AI

Clone this repo or download `bridge.py` directly:

```bash
git clone https://github.com/TheMarsMan101/spit-ai.git
cd spit-ai
```

---

## ⚠️ Important: Dedicated Account Required

Spit AI uses `xdotool` to simulate keyboard input — it physically takes over the Minecraft window to open chat, type the response, and press Enter. This means:

- **You need a dedicated Minecraft account** for Spit AI to run on. This account logs into the world or server and acts as the bot. It cannot be the same account you play on.
- **It's not advised to play on the same machine or VM** that Spit AI is running on. When a response comes in, `xdotool` steals window focus for about 1 second, which will interrupt whatever you're doing. Additionally, if you have multiple Minecraft instances open on the same machine, the bot has no way to distinguish between them — it will take over whichever instance has priority, which could be your personal account instead of the bot's.
- **If you want to play and run Spit AI**, you need two Minecraft accounts and ideally two machines (or a separate VM for the bot). One account plays normally, the other sits in-game as the Spit AI bot.

For LAN worlds, the dedicated bot account joins your LAN world as a second player. For servers, the bot account joins the server like any other player.

---

## Quick Start

You need **three things running** on the bot's machine at the same time:

1. **Minecraft** — **launch first.** Log into the bot's dedicated account and join the world or server
2. **Ollama** — running as a service or in the background
3. **bridge.py** — **launch last.** It needs Minecraft's log file to exist and starts reading from the end, so it only catches new messages

### Start Ollama and the bridge

> **⚠️ Make sure Minecraft is open and in-game before starting the bridge.** The bridge reads from Minecraft's `latest.log`, which doesn't exist until the game is running. If you start the bridge first, it will exit with a "log file not found" error.

Ollama often runs as a system service automatically after installation. You can check with `curl http://localhost:11434` — if it responds, you're good. If not, start it first:

```bash
ollama serve &
```

Then start the bridge:

```bash
python3 bridge.py
```

That's it. Open Minecraft, join a world or server, and type something like:

```
Hey @Spit, what's the best food source in Minecraft?
```

---

## Trigger Examples

`@Spit` is detected **anywhere** in the message. Everything after `@Spit` becomes the prompt. All of these work:

```
@Spit what is redstone?
Hey @Spit, how do I enchant a sword?
yo @Spit who was the first person on the moon?
Does anyone know, @Spit, what time the sun sets?
```

---

## Command-Line Flags

| Flag | Default | Description |
|---|---|---|
| `--model` | `llama3.1:8b` | Ollama model name (run `ollama list` to see installed models, or [browse all available models](https://ollama.com/library)) |
| `--log` | `~/.minecraft/logs/latest.log` | Path to Minecraft's log file |
| `--trigger` | `@spit` | Chat trigger phrase |
| `--ignore` | *(none)* | Space-separated player names to ignore |
| `--self-name` | *(none)* | The bot's Minecraft username (auto-ignored to prevent loops) |
| `--workers` | `2` | Number of worker threads (see [Workers](#workers) below) |

### Examples

```bash
# Use a different model
python3 bridge.py --model mistral

# Ignore specific players
python3 bridge.py --ignore SpamBot123 AnotherPlayer

# Prevent the bot's own @Spit messages from triggering a loop
python3 bridge.py --self-name SpitAI_Bot

# Custom log path (e.g. Prism Launcher)
python3 bridge.py --log ~/.local/share/PrismLauncher/instances/1.21.5/.minecraft/logs/latest.log

# All options together
python3 bridge.py --model llama3.1:8b --self-name SpitAI_Bot --ignore BotAccount --workers 2
```

---

## Configuration

These constants are at the top of `bridge.py` and can be edited directly.

### Model & Prompt

| Constant | Default | Description |
|---|---|---|
| `DEFAULT_MODEL` | `llama3.1:8b` | The Ollama model used when `--model` isn't specified |
| `SYSTEM_PROMPT` | *(see below)* | The system prompt that shapes the AI's personality and behavior |
| `MAX_TOKENS` | `200` | Maximum tokens in the Ollama response (keeps answers chat-friendly) |

The default system prompt:

```
You are Spit, a helpful AI assistant in a Minecraft in-game chat,
powered by Ollama. Answer any topic the user asks about. Only assume
Minecraft context when the question is genuinely ambiguous (e.g.
'where do I find diamonds'). If the question is clearly about the
real world, answer normally. Keep answers concise (1-3 sentences).
No markdown formatting. No asterisks, no bullet points — plain text only.
```

**To customize the AI's personality**, edit the `SYSTEM_PROMPT` string in `bridge.py`. Some ideas:

- Make it talk like a pirate
- Turn it into a Minecraft lore expert
- Remove the Minecraft context bias entirely for a general-purpose chatbot
- Give it a sarcastic personality
- Make it only respond in haikus

### Chat Behavior

| Constant | Default | Description |
|---|---|---|
| `TRIGGER` | `@spit` | The phrase that activates the bot (case-insensitive, detected anywhere in message) |
| `BOT_PREFIX` | `[Spit] ` | Prefix on all response messages in Minecraft chat |
| `MC_CHAT_LIMIT` | `256` | Minecraft's character limit per chat message |
| `MAX_CHUNKS` | `5` | Maximum messages per response (prevents wall-of-text spam) |
| `COOLDOWN_SEC` | `1` | Per-player cooldown in seconds between accepted prompts |

### Queue

| Constant | Default | Description |
|---|---|---|
| `MAX_QUEUE_SIZE` | `20` | Maximum pending requests before new ones are dropped |
| `NUM_WORKERS` | `2` | Number of worker threads (see below) |

---

## Workers

The bridge uses a threaded queue system with 2 worker threads by default:

- **Worker 1** picks up a prompt → sends it to Ollama → waits → types the response into Minecraft
- **Worker 2** picks up the next prompt → sends it to Ollama → Ollama queues it until Worker 1's generation finishes

**Adding more workers has no real effect.** Ollama processes one generation at a time (it's GPU-bound), so extra workers just pre-queue HTTP requests. The only benefit of Worker 2 is that it can send the next prompt to Ollama while Worker 1 is busy typing into Minecraft.

**Leave `NUM_WORKERS` at 2** unless you've configured the `OLLAMA_NUM_PARALLEL` environment variable and have enough VRAM to run multiple concurrent generations.

---

## LAN Worlds vs. Online Servers

- **LAN worlds** — the bot's dedicated account joins your LAN world as a second player. Open your single-player world to LAN, then log in with the bot account on the machine running Spit AI.
- **Online servers** — the bot account joins the server like any other player. The bridge reads the bot's local `latest.log` and types responses through the bot's client.

In both cases, other players simply type `@Spit` in chat and the bot account responds.

> **Note:** On servers with chat reporting or custom chat plugins, the log format may differ. See [Troubleshooting](#troubleshooting) if messages aren't being detected.

---

## Troubleshooting

### "Log file not found"
Minecraft isn't running, or the log path is wrong. Some launchers use different directories:
- **Vanilla / Fabric:** `~/.minecraft/logs/latest.log`
- **Prism Launcher:** `~/.local/share/PrismLauncher/instances/<name>/.minecraft/logs/latest.log`
- **MultiMC:** `~/.local/share/multimc/instances/<name>/.minecraft/logs/latest.log`

Use `--log` to point to the correct path.

### "Cannot find Minecraft window"
The window title must contain "Minecraft". Make sure the game window isn't minimized. If you're using a tiling window manager, the window needs to be mapped and visible.

### "Could not connect to Ollama"
Make sure Ollama is running. Start it with `ollama serve` in a separate terminal, or verify with:
```bash
curl http://localhost:11434
```

### Response isn't appearing in chat
The `xdotool` timing may need adjustment for your system. In `bridge.py`, increase the `time.sleep()` values in the `send_mc_chat()` function — try bumping `0.4` to `0.5` or `0.6`.

### Opens inventory instead of chat
This is a key targeting issue. Make sure you're running the latest `bridge.py` which sends keypresses without the `--window` flag. The script presses `T` to open chat — if your chat keybind is different, you'll need to change the `"t"` in `send_mc_chat()`.

### Special characters break the response
`xdotool` can struggle with some Unicode. The system prompt tells the AI to use plain text only, which helps. If issues persist, the model may be generating characters `xdotool` can't type.

### Bot triggers itself in a loop
Use `--self-name BotAccountName` to auto-ignore the bot's own messages. The `[Spit]` prefix also prevents loops since it doesn't contain `@Spit`.

### Nothing happens when someone types @Spit
- Make sure you started the bridge **after** Minecraft was already running. The script reads from the end of the log file and only catches new messages.
- Check the log format. The bridge expects `[CHAT] <PlayerName> message` in the log. Modded servers with custom chat formatting may not match.
- Run `tail -f ~/.minecraft/logs/latest.log | grep "@"` in a separate terminal to verify your messages are appearing in the log.

---

## Limitations

- **Window focus** — when sending a response, `xdotool` briefly steals focus to the Minecraft window for about 1 second. This is why a dedicated machine or VM is recommended for the bot — you can't comfortably use the same machine while it's running.
- **X11 only** — `xdotool` requires X11. Should work on most Linux distributions and desktop environments running X11. Wayland is not supported. Linux Mint, Ubuntu, Fedora, Debian, Arch, etc. with X11 should all work.
- **One game instance** — the bridge targets the first window with "Minecraft" in the title. Running multiple Minecraft windows may cause unexpected behavior.
- **Chat format dependent** — relies on the standard Minecraft chat log format (`[CHAT] <Player> message`). Servers with heavily customized chat plugins may not be detected.
- **No conversation memory** — each prompt is independent. The AI doesn't remember what was asked earlier in the session. Every `@Spit` message is a fresh conversation.
- **Response length** — capped at 200 tokens by default and split across a maximum of 5 chat messages. This is intentional to keep chat clean, but both values are configurable.
- **Linux / X11 only** — depends on `xdotool` which is an X11 tool. Any Linux distribution running X11 should work. macOS and Windows are not supported.

---

## Tested On

| Component | Version |
|---|---|
| **OS** | Linux Mint 22.3 (Cinnamon) |
| **Display Server** | X11 |
| **Minecraft** | Java Edition 1.21.5 |
| **Mod Loader** | Fabric |
| **Ollama** | Latest |
| **Ollama Model** | llama3.1:8b |
| **Python** | 3.12 |

---

## Alternative Approaches

If the `xdotool` method doesn't suit your needs, here are other ways to achieve a similar result:

| | Spit AI | Fabric/Forge Mod | Mineflayer Bot | RCON |
|---|---|---|---|---|
| **Cost** | Free | Free | Free | Free |
| **Privacy** | ✅ Fully local | Depends | Depends on LLM | Depends on LLM |
| **Mods needed** | ✅ None | Java mod dev | None | None |
| **Extra account** | Yes | ✅ No | Yes | ✅ No |
| **Setup difficulty** | Low | High | Medium | Medium |
| **LAN support** | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No |
| **Steals focus** | Yes | ✅ No | ✅ No | ✅ No |
| **Any LLM model** | ✅ Yes | Depends | Depends | Depends |
| **MC update proof** | ✅ Yes | ❌ Breaks often | ✅ Yes | ✅ Yes |

---

## License

MIT

---

<p align="center">
  <b>🦙 Spit AI</b><br>
  <i>Made with AI. Powered by AI. Spitting facts.</i>
</p>
