import os
import asyncio
import subprocess
import tempfile
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    filters,
    ContextTypes,
)

cwd = os.getcwd()
cwd_lock = asyncio.Lock()

# ---------- ALIASES ----------
ALIASES = {
    "la": "ls -la",
    "ll": "ls -l",
    "l": "ls -la",
    "dir": "ls -la",
    "rm": "rm -i",
    "rmf": "rm -rf",
    "cp": "cp -i",
    "mv": "mv -i",
    "mkdir": "mkdir -p",
    "touch": "touch",
    "cat": "cat",
    "less": "less",
    "more": "more",
    "head": "head -n 20",
    "tail": "tail -n 20",
    "grep": "grep --color=auto",
    "find": "find . -name",
    "du": "du -sh * | sort -h",
    "df": "df -h",
    "tree": "tree -L 2",
    "whoami": "whoami",
    "uname": "uname -a",
    "uptime": "uptime",
    "free": "free -h",
    "ps": "ps aux",
    "top": "top -b -n 1 | head -20",
    "htop": "htop -b -n 1",
    "neofetch": "neofetch",
    "screenfetch": "screenfetch",
    "kill": "kill -9",
    "pkill": "pkill -f",
    "pgrep": "pgrep -a",
    "bg": "jobs -l",
    "fg": "fg",
    "netstat": "netstat -tulpn",
    "ss": "ss -tulpn",
    "ifconfig": "ifconfig",
    "ip": "ip a",
    "ping": "ping -c 4 8.8.8.8",
    "curl": "curl -s",
    "wget": "wget -q --show-progress",
    "dig": "dig google.com",
    "nslookup": "nslookup",
    "traceroute": "traceroute",
    "install": "sudo apt install -y",
    "update": "sudo apt update",
    "upgrade": "sudo apt upgrade -y",
    "clean": "sudo apt autoremove -y",
    "yum": "sudo yum install -y",
    "systemctl": "systemctl status",
    "service": "service",
    "journalctl": "journalctl -n 50",
    "docker": "docker",
    "dps": "docker ps -a",
    "drm": "docker rm -f",
    "dstop": "docker stop",
    "dstart": "docker start",
    "git": "git",
    "gst": "git status",
    "gco": "git checkout",
    "gcb": "git checkout -b",
    "gbr": "git branch -a",
    "glog": "git log --oneline --graph",
    "py": "python3",
    "pip": "pip3",
    "node": "node",
    "npm": "npm",
    "npx": "npx",
    "yarn": "yarn",
    "tar": "tar -czvf",
    "untar": "tar -xzvf",
    "zip": "zip -r",
    "unzip": "unzip",
    "chmod": "chmod",
    "chown": "chown",
    "history": "history",
    "clear": "clear",
    "alias": "alias",
    "echo": "echo",
    "date": "date",
    "cal": "cal",
}

# ---------- CORE EXECUTOR ----------
def run_cmd(cmd: str) -> str:
    global cwd
    cmd = ALIASES.get(cmd, cmd)

    if cmd == "pwd":
        return cwd

    if cmd.startswith("cd"):
        parts = cmd.split(maxsplit=1)
        path = parts[1] if len(parts) > 1 else os.path.expanduser("~")
        new_path = os.path.abspath(os.path.join(cwd, path))
        if os.path.isdir(new_path):
            cwd = new_path
            return cwd
        return "No such directory"

    try:
        out = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, cwd=cwd)
        return out.decode(errors="ignore")
    except subprocess.CalledProcessError as e:
        return e.output.decode(errors="ignore")
    except Exception as e:
        return str(e)

# ---------- INTERNAL COMMAND HANDLERS ----------
async def download_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, args: list):
    if not args:
        await update.message.reply_text("Usage: download <filename>")
        return
    filename = args[0]
    async with cwd_lock:
        path = os.path.join(cwd, filename)
        if not os.path.isfile(path):
            await update.message.reply_text(f"❌ File not found: {filename}")
            return
        try:
            with open(path, "rb") as f:
                await update.message.reply_document(document=f, filename=filename)
        except Exception as e:
            await update.message.reply_text(f"❌ Error sending: {e}")

async def getall_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, args: list):
    target = args[0] if args else "."
    async with cwd_lock:
        abs_path = os.path.abspath(os.path.join(cwd, target))
        if not os.path.isdir(abs_path):
            await update.message.reply_text(f"❌ Directory not found: {target}")
            return
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
            archive_path = tmp.name
        try:
            cmd = f"tar -czf {archive_path} -C {abs_path} ."
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd)
            if proc.returncode != 0:
                await update.message.reply_text(f"❌ Compression failed:\n{proc.stderr}")
                return
            size = os.path.getsize(archive_path)
            if size > 50 * 1024 * 1024:
                await update.message.reply_text(
                    f"❌ Archive too large ({size // (1024*1024)} MB). Telegram limit is 50 MB."
                )
                return
            with open(archive_path, "rb") as f:
                await update.message.reply_document(
                    document=f,
                    filename=os.path.basename(abs_path) + ".tar.gz",
                    caption=f"📦 All files from `{abs_path}`",
                    parse_mode="Markdown",
                )
            await update.message.reply_text("✅ Archive sent successfully.")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")
        finally:
            if os.path.exists(archive_path):
                os.unlink(archive_path)

async def dumpall_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, args: list):
    target = args[0] if args else "/"
    async with cwd_lock:
        if not os.path.exists(target):
            await update.message.reply_text(f"❌ Path not found: {target}")
            return
        await update.message.reply_text(f"⏳ Compressing `{target}` ... this may take a while.")
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
            archive_path = tmp.name
        try:
            exclude_dirs = ["/proc", "/sys", "/dev", "/run", "/tmp", "/mnt", "/media"]
            exclude_opts = " ".join(f"--exclude={d}" for d in exclude_dirs)
            cmd = f"tar -czf {archive_path} {exclude_opts} -C {target} ."
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd="/")
            if proc.returncode != 0:
                await update.message.reply_text(f"❌ Compression failed:\n{proc.stderr}")
                return
            size = os.path.getsize(archive_path)
            if size > 50 * 1024 * 1024:
                await update.message.reply_text(
                    f"❌ Archive too large ({size // (1024*1024)} MB). Telegram limit is 50 MB.\n"
                    "Try specifying a sub‑directory instead."
                )
                return
            with open(archive_path, "rb") as f:
                await update.message.reply_document(
                    document=f,
                    filename=os.path.basename(target) + ".tar.gz",
                    caption=f"📦 Dump of `{target}` (excluded: {', '.join(exclude_dirs)})",
                    parse_mode="Markdown",
                )
            await update.message.reply_text("✅ Archive sent successfully.")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")
        finally:
            if os.path.exists(archive_path):
                os.unlink(archive_path)

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, args: list):
    aliases = sorted(ALIASES.keys())
    msg = (
        "📋 **Available aliases:**\n\n"
        "• `{}`\n\n"
        "💡 **Commands (no slash needed):**\n"
        "• `download <file>` – download a file\n"
        "• `getall [path]` – download all files from a directory (relative to current)\n"
        "• `dumpall [path]` (or `takeall`) – download entire VPS (default: /)\n"
        "• `help` – show this message\n\n"
        "Any other text is executed as a shell command."
    ).format("\n• ".join(f"`{a}` → `{ALIASES[a]}`" for a in aliases))

    if len(msg) > 4000:
        for i in range(0, len(msg), 4000):
            await update.message.reply_text(msg[i:i+4000], parse_mode="Markdown")
    else:
        await update.message.reply_text(msg, parse_mode="Markdown")

# ---------- MAIN MESSAGE HANDLER ----------
async def terminal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle any text message: internal commands or shell commands."""
    if not update.message or not update.message.text:
        return
    if update.effective_user.id not in context.bot_data.get("owners", []):
        return

    text = update.message.text.strip()
    if not text:
        return

    # Split into command and arguments
    parts = text.split(maxsplit=1)
    first_word = parts[0].lower()
    args = parts[1].split() if len(parts) > 1 else []

    # Internal commands (no slash)
    if first_word in {"download", "getall", "dumpall", "takeall", "help"}:
        if first_word == "download":
            await download_handler(update, context, args)
        elif first_word == "getall":
            await getall_handler(update, context, args)
        elif first_word in {"dumpall", "takeall"}:
            await dumpall_handler(update, context, args)
        elif first_word == "help":
            await help_handler(update, context, args)
        return

    # Otherwise: run as shell command
    async with cwd_lock:
        output = run_cmd(text)

    if not output:
        output = "✅ Done"

    for i in range(0, len(output), 4000):
        await update.message.reply_text(output[i:i+4000])

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save uploaded document to current working directory."""
    if update.effective_user.id not in context.bot_data.get("owners", []):
        return

    doc = update.message.document
    file_name = doc.file_name or "unnamed"
    file_id = doc.file_id

    async with cwd_lock:
        path = os.path.join(cwd, file_name)
        try:
            new_file = await context.bot.get_file(file_id)
            await new_file.download_to_drive(path)
            await update.message.reply_text(f"✅ File saved: {file_name}")
        except Exception as e:
            await update.message.reply_text(f"❌ Error saving: {e}")

# ---------- BOT STARTER ----------
def start_bot(token: str, owners: list):
    app = ApplicationBuilder().token(token).build()
    app.bot_data["owners"] = owners

    # Main text handler (handles both internal commands and shell)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, terminal))

    # Document uploads
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # Still keep slash commands for compatibility (optional)
    app.add_handler(CommandHandler("download", lambda u,c: download_handler(u,c, c.args or [])))
    app.add_handler(CommandHandler("getall", lambda u,c: getall_handler(u,c, c.args or [])))
    app.add_handler(CommandHandler("dumpall", lambda u,c: dumpall_handler(u,c, c.args or [])))
    app.add_handler(CommandHandler("takeall", lambda u,c: dumpall_handler(u,c, c.args or [])))
    app.add_handler(CommandHandler("help", lambda u,c: help_handler(u,c, [])))

    print("🤖 Bot is running... (commands work without /)")
    app.run_polling()
