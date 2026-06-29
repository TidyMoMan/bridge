#!/usr/bin/env python3
"""
Commands:
  /quit, /q              exit
  /clear                 wipe conversation history
  /rewind [n]            remove last n messages from history (default: 1)
  /<name>                toggle a bot in or out of the chat
  /say <name> <msg>      address one bot directly; only they respond
  /as <name> <msg>       inject a message into history as a bot
  /as narrator <msg>     inject a message as the narrator (no speaker)
  /con [name]            nudge last speaker (or named bot) to continue
  /retry [name]          re-prompt last speaker (or named bot), dropping their last response
  /save <name>           save conversation to saves/<name>.json
  /burn <name|all>       delete a save or all saves
"""

import atexit, itertools, json, os, random, readline, sys, textwrap, threading, time
import ollama


def load_config(path="../config/crew-config.txt"):
    user, user_color, bots = "User", "82", []
    in_bots = False
    try:
        for raw in open(path):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("bots"):
                in_bots = True
                continue
            if in_bots:
                if "," in line:
                    name, model = [p.strip() for p in line.split(",", 1)]
                    bots.append((name, model))
                continue
            if "=" in line:
                key, _, val = line.partition("=")
                key, val = key.strip().lower(), val.strip()
                if key == "user":
                    user = val
                if key == "user_color":
                    user_color = val
    except FileNotFoundError:
        print("✗ config.txt not found.")
        sys.exit(1)
    if not bots:
        print("✗ No bots defined in config.txt.")
        sys.exit(1)
    return user, f"\033[38;5;{user_color}m", bots


USER, USER_COLOR, BOTS = load_config()

RESET = "\033[0m"
BOLD = "\033[1m"
SYS_COLOR = "\033[38;5;240m"
NARRATOR_COLOR = "\033[38;5;250m"
NARRATOR = "Narrator"
SPINNER = "⣾⣽⣻⢿⡿⣟⣯⣷"

PALETTE = [
    "\033[38;5;208m",  # orange
    "\033[38;5;213m",  # pink/violet
    "\033[38;5;39m",  # sky blue
    "\033[38;5;220m",  # yellow
    "\033[38;5;203m",  # coral
    "\033[38;5;123m",  # cyan
    "\033[38;5;183m",  # lavender
    "\033[38;5;118m",  # lime
    "\033[38;5;215m",  # peach
    "\033[38;5;171m",  # purple
]


def assign_colors():
    return {
        name: PALETTE[i]
        if i < len(PALETTE)
        else f"\033[38;5;{random.randint(16, 231)}m"
        for i, (name, _) in enumerate(BOTS)
    }


def show(name, text, colors, target=None):
    if name == NARRATOR:
        print(f"\n  {NARRATOR_COLOR}~ {text.strip()} ~{RESET}\n")
        return
    c = USER_COLOR if name == USER else colors[name]
    header = f"  {c}{BOLD}{name}{RESET}"
    if target:
        tc = colors.get(target, SYS_COLOR)
        header += f"  {SYS_COLOR}→ {tc}{BOLD}{target}{RESET}  {SYS_COLOR}{time.strftime('%H:%M')}{RESET}"
    else:
        header += f"  {SYS_COLOR}{time.strftime('%H:%M')}{RESET}"
    print(f"\n{header}")
    for line in textwrap.fill(text.strip(), 66).splitlines():
        print(f"  {c}│{RESET}  {line}")
    print()


def spinner(label):
    stop = threading.Event()

    def _spin():
        for f in itertools.cycle(SPINNER):
            if stop.is_set():
                sys.stdout.write("\r\033[K")
                sys.stdout.flush()
                break
            sys.stdout.write(f"\r  {SYS_COLOR}{f} {label}…{RESET}")
            sys.stdout.flush()
            time.sleep(0.08)

    threading.Thread(target=_spin, daemon=True).start()
    return stop


def ask(model, history):
    return ollama.chat(model=model, messages=history)["message"]["content"].strip()


def prompt_bot(name, model, history, colors):
    s = spinner(f"{name} is typing")
    try:
        reply = ask(model, history)
    except Exception as e:
        s.set()
        print(f"\n  {SYS_COLOR}[Error from {name}: {e}]{RESET}\n")
        return None
    s.set()
    time.sleep(0.05)
    if not reply:
        print(f"  {SYS_COLOR}[{name} returned an empty response]{RESET}\n")
        return None
    show(name, reply, colors)
    return reply


def main():
    try:
        available = [m.model.split(":")[0] for m in ollama.list().models]
    except Exception:
        print("✗ Ollama not reachable. Run: ollama serve")
        sys.exit(1)
    for name, model in BOTS:
        if model not in available:
            print(f"✗ '{model}' not found. Run: ollama create {model} -f Modelfile")
            sys.exit(1)

    try:
        readline.read_history_file(".chat_history")
    except FileNotFoundError:
        pass
    atexit.register(readline.write_history_file, ".chat_history")

    colors = assign_colors()
    bot_names = {name.lower(): (name, model) for name, model in BOTS}
    history = []
    active = {name for name, _ in BOTS}
    last_spoke = None

    while True:
        try:
            msg = input(f"\001{USER_COLOR}\002>>> \001{RESET}\002").strip()
            cols = os.get_terminal_size().columns
            sys.stdout.write(f"\033[{max(1, (len(msg) + 5) // cols + 1)}A\033[J")
            sys.stdout.flush()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not msg:
            continue
        if msg.lower() in ("/quit", "/q"):
            break
        if msg.lower() == "/clear":
            history.clear()
            os.system("clear")
            continue

        parts = msg.split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        # /name — toggle a bot
        if msg.startswith("/") and msg[1:].lower() in bot_names:
            name, _ = bot_names[msg[1:].lower()]
            active ^= {name}
            print(
                f"  {SYS_COLOR}{name} {'joined' if name in active else 'left'} the chat.{RESET}\n"
            )
            continue

        # /con [name] — nudge last speaker or named bot to continue
        if cmd == "/con":
            key = arg.lower() or (last_spoke.lower() if last_spoke else None)
            if not key or key not in bot_names:
                print(
                    f"  {SYS_COLOR}{'Unknown bot.' if key else 'No one has spoken yet.'}{RESET}\n"
                )
                continue
            name, model = bot_names[key]
            history.append(
                {"role": "user", "content": f"{USER} (to {name}): Please continue."}
            )
            reply = prompt_bot(name, model, history, colors)
            if reply:
                history.append({"role": "assistant", "content": f"{name}: {reply}"})
                last_spoke = name
            continue

        # /retry [name] — drop last response and re-prompt
        if cmd == "/retry":
            key = arg.lower() or (last_spoke.lower() if last_spoke else None)
            if not key or key not in bot_names:
                print(
                    f"  {SYS_COLOR}{'Unknown bot.' if key else 'No one has spoken yet.'}{RESET}\n"
                )
                continue
            name, model = bot_names[key]
            if history and history[-1]["role"] == "assistant":
                history.pop()
            print(f"  {SYS_COLOR}↺ {name} is retrying…{RESET}\n")
            reply = prompt_bot(name, model, history, colors)
            if reply:
                history.append({"role": "assistant", "content": f"{name}: {reply}"})
                last_spoke = name
            continue

        # /as <name|narrator> <msg> — inject a message as a speaker
        if cmd == "/as":
            rest = arg.split(None, 1)
            speaker_key = rest[0].lower() if rest else ""
            text = rest[1] if len(rest) > 1 else ""
            if not speaker_key or not text:
                print(f"  {SYS_COLOR}Usage: /as <name|narrator> <message>{RESET}\n")
                continue
            if speaker_key == "narrator":
                show(NARRATOR, text, colors)
                history.append({"role": "user", "content": f"[Narrator]: {text}"})
            elif speaker_key in bot_names:
                name, _ = bot_names[speaker_key]
                show(name, text, colors)
                history.append({"role": "assistant", "content": f"{name}: {text}"})
                last_spoke = name
            else:
                print(f"  {SYS_COLOR}Unknown speaker '{rest[0]}'.{RESET}\n")
            continue

        # /rewind [n] — remove last n messages from history
        if cmd == "/rewind":
            try:
                n = int(arg) if arg else 1
            except ValueError:
                print(f"  {SYS_COLOR}Usage: /rewind [n]{RESET}\n")
                continue
            removed = min(n, len(history))
            del history[-removed:]
            print(
                f"  {SYS_COLOR}↩ Rewound {removed} message{'s' if removed != 1 else ''}.{RESET}\n"
            )
            continue

        # /save <name> — save history to saves/<name>.json
        if cmd == "/save":
            if not arg:
                print(f"  {SYS_COLOR}Usage: /save <name>{RESET}\n")
                continue
            os.makedirs("saves", exist_ok=True)
            path = f"saves/{arg}.json"
            with open(path, "w") as f:
                json.dump(history, f, indent=2)
            print(f"  {SYS_COLOR}✓ Saved to {path}{RESET}\n")
            continue

        # /load <name> — load history from saves/<name>.json
        if cmd == "/load":
            if not arg:
                print(f"  {SYS_COLOR}Usage: /load <name>{RESET}\n")
                continue
            path = f"saves/{arg}.json"
            if not os.path.exists(path):
                print(f"  {SYS_COLOR}✗ No save found: {path}{RESET}\n")
                continue
            if history:
                try:
                    confirm = (
                        input(
                            f"  {SYS_COLOR}⚠ Unsaved chat will be lost. Load anyway? (y/n) {RESET}"
                        )
                        .strip()
                        .lower()
                    )
                    sys.stdout.write("\033[1A\033[J")
                    sys.stdout.flush()
                except (EOFError, KeyboardInterrupt):
                    print()
                    break
                if confirm != "y":
                    continue
            with open(path) as f:
                history = json.load(f)
            os.system("clear")
            print(f"  {SYS_COLOR}✓ Loaded '{arg}' ({len(history)} messages){RESET}\n")
            continue

        # /burn <name|all> — delete a save or all saves
        if cmd == "/burn":
            if not arg:
                print(f"  {SYS_COLOR}Usage: /burn <name|all>{RESET}\n")
                continue
            if arg == "all":
                saves = (
                    [f for f in os.listdir("saves")] if os.path.exists("saves") else []
                )
                if not saves:
                    print(f"  {SYS_COLOR}No saves to delete.{RESET}\n")
                    continue
                try:
                    confirm = (
                        input(
                            f"  {SYS_COLOR}⚠ Delete all {len(saves)} save(s)? (y/n) {RESET}"
                        )
                        .strip()
                        .lower()
                    )
                    sys.stdout.write("\033[1A\033[J")
                    sys.stdout.flush()
                except (EOFError, KeyboardInterrupt):
                    print()
                    break
                if confirm != "y":
                    continue
                for f in saves:
                    os.remove(f"saves/{f}")
                print(f"  {SYS_COLOR}✓ Deleted {len(saves)} save(s).{RESET}\n")
            else:
                path = f"saves/{arg}.json"
                if not os.path.exists(path):
                    print(f"  {SYS_COLOR}✗ No save found: {path}{RESET}\n")
                    continue
                try:
                    confirm = (
                        input(f"  {SYS_COLOR}⚠ Delete '{arg}'? (y/n) {RESET}")
                        .strip()
                        .lower()
                    )
                    sys.stdout.write("\033[1A\033[J")
                    sys.stdout.flush()
                except (EOFError, KeyboardInterrupt):
                    print()
                    break
                if confirm != "y":
                    continue
                os.remove(path)
                print(f"  {SYS_COLOR}✓ Deleted '{arg}'.{RESET}\n")
            continue

        # /say <name> <msg> — address one bot directly
        target = None
        if cmd == "/say":
            rest = arg.split(None, 1)
            if len(rest) == 2 and rest[0].lower() in bot_names:
                target, _ = bot_names[rest[0].lower()]
                msg = rest[1]
            else:
                print(f"  {SYS_COLOR}Usage: /say <name> <message>{RESET}\n")
                continue

        # unknown command
        if msg.startswith("/") and not target:
            print(f"  {SYS_COLOR}Unknown command '{cmd}'.{RESET}\n")
            continue

        show(USER, msg, colors, target)
        history.append(
            {
                "role": "user",
                "content": f"{USER}{f' (to {target})' if target else ''}: {msg}",
            }
        )

        for name, model in BOTS:
            if name not in active or (target and name != target):
                continue
            reply = prompt_bot(name, model, history, colors)
            if reply:
                history.append({"role": "assistant", "content": f"{name}: {reply}"})
                last_spoke = name


if __name__ == "__main__":
    main()
