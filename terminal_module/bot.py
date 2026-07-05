import os
import asyncio
import subprocess
import tempfile
import shutil
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

# ---------- EXTENDED ALIASES ----------
ALIASES = {
    # File / directory operations
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

    # System info
    "whoami": "whoami",
    "uname": "uname -a",
    "uptime": "uptime",
    "free": "free -h",
    "ps": "ps aux",
    "top": "top -b -n 1 | head -20",
    "htop": "htop -b -n 1",
    "neofetch": "neofetch",
    "screenfetch": "screenfetch",

    # Process management
    "kill": "kill -9",
    "pkill": "pkill -f",
    "pgrep": "pgrep -a",
    "bg": "jobs -l",
    "fg": "fg",

    # Networking
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

    # Package management (apt / yum / dnf)
    "install": "sudo apt install -y",
    "update": "sudo apt update",
    "upgrade": "sudo apt upgrade -y",
    "clean": "sudo apt autoremove -y",
    "yum": "sudo yum install -y",

    # System services
    "systemctl": "systemctl status",
    "service": "service",
    "journalctl": "journalctl -n 50",

    # Docker
    "docker": "docker",
    "dps": "docker ps -a",
    "drm": "docker rm -f",
    "dstop": "docker stop",
    "dstart": "docker start",

    # Git
    "git": "git",
    "gst": "git status",
    "gco": "git checkout",
    "gcb": "git checkout -b",
    "gbr": "git branch -a",
    "glog": "git log --oneline --graph",

    # Python
    "py": "python3",
    "pip": "pip3",

    # Node.js
    "node": "node",
    "npm": "npm",
    "npx": "npx",
    "yarn": "yarn",

    # Archive
    "tar": "tar -czvf",
    "untar": "tar -xzvf",
    "zip": "zip -r",
    "unzip": "unzip",

    # Permissions
    "chmod": "chmod",
    "chown": "chown",

    # Misc
    "history": "history",
    "clear": "clear",
    "alias": "alias",
    "echo": "echo",
    "date": "date",
    "cal": "cal",
}

# ---------- CORE COMMAND EXECUTOR ----------
def run_cmd(cmd: str) -> str:
    global cwd
    cmd = ALIASES.get(cmd, cmd)   # expand alias if present

    # Built‑ins
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

    # Shell command
    try:
        out = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, cwd=cwd)
        return out.decode(errors="ignore")
    except subprocess.CalledProcessError as e:
        return e.output.decode(errors="ignore")
    except Exception as e:
        return str(e)

# ---------- TELEGRAM HANDLERS ----------
async def terminal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Any text message (non‑command) runs as a shell command."""
    if not update.message or not update.message.text:
        return
    if update.effective_user.id not in context.bot_data.get("owners", []):
        return

    cmd = update.message.text.strip()
    async with cwd_lock:
        output = run_cmd(cmd)

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

async def download_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a file from the VPS to the user."""
    if update.effective_user.id not in context.bot_data.get("owners", []):
        return
    if not context.args:
        await update.message.reply_text("Usage: /download <filename>")
        return

    filename = context.args[0]
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

async def getall_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Pack the current directory (or a given relative path) into a .tar.gz archive
    and send it as a document.
    """
    user_id = update.effective_user.id
    if user_id not in context.bot_data.get("owners", []):
        return

    target = context.args[0] if context.args else "."
    async with cwd_lock:
        abs_path = os.path.abspath(os.path.join(cwd, target))
        if not os.path.isdir(abs_path):
            await update.message.reply_text(f"❌ Directory not found: {target}")
            return

        # Create temporary archive
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
            archive_path = tmp.name

        try:
            # Compress without excluding (since it's a specific folder)
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

async def dumpall_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Archive the entire VPS (or a given absolute path) and send.
    Excludes system pseudo‑filesystems to avoid errors.
    """
    user_id = update.effective_user.id
    if user_id not in context.bot_data.get("owners", []):
        return

    # Optional path, default to root
    target = context.args[0] if context.args else "/"
    async with cwd_lock:
        if not os.path.exists(target):
            await update.message.reply_text(f"❌ Path not found: {target}")
            return

        # Warn user about potential size
        await update.message.reply_text(f"⏳ Compressing `{target}` ... this may take a while.")

        # Create temporary archive
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
            archive_path = tmp.name

        try:
            # Exclude common pseudo‑filesystems to avoid errors and reduce size
            exclude_dirs = ["/proc", "/sys", "/dev", "/run", "/tmp", "/mnt", "/media"]
            exclude_opts = " ".join(f"--exclude={d}" for d in exclude_dirs)

            # Use tar from the parent directory to avoid including the archive itself
            # We'll cd to / and archive from there, but exclude the temp file path if inside /tmp
            # Actually, we can archive from the target directory.
            # We'll use -C to change to the directory and archive "."
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

            # Send the archive
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

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all available aliases and commands."""
    if update.effective_user.id not in context.bot_data.get("owners", []):
        return

    aliases = sorted(ALIASES.keys())
    msg = (
        "📋 **Available aliases:**\n\n"
        "• `{}`\n\n"
        "💡 **Commands:**\n"
        "• `/download <file>` – download a file\n"
        "• `/getall [path]` – download all files from a directory (relative to current)\n"
        "• `/dumpall [path]` – download the entire VPS (default: /) as .tar.gz (excludes /proc, /sys, etc.)\n"
        "• `/help` – show this message"
    ).format("\n• ".join(f"`{a}` → `{ALIASES[a]}`" for a in aliases))

    # Split if too long
    if len(msg) > 4000:
        for i in range(0, len(msg), 4000):
            await update.message.reply_text(msg[i:i+4000], parse_mode="Markdown")
    else:
        await update.message.reply_text(msg, parse_mode="Markdown")

# ---------- BOT STARTER ----------
def start_bot(token: str, owners: list):
    app = ApplicationBuilder().token(token).build()
    app.bot_data["owners"] = owners

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, terminal))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(CommandHandler("download", download_command))
    app.add_handler(CommandHandler("getall", getall_command))
    app.add_handler(CommandHandler("dumpall", dumpall_command))
    app.add_handler(CommandHandler("takeall", dumpall_command))   # alias
    app.add_handler(CommandHandler("help", help_command))

    print("🤖 Bot is running...")
    app.run_polling()
