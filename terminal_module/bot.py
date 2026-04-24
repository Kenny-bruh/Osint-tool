import os
import asyncio
import subprocess
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

cwd = os.getcwd()
cwd_lock = asyncio.Lock()

ALIASES = {
    "la": "ls -la",
    "ll": "ls -l",
}

def run_cmd(cmd):
    global cwd

    if cmd in ALIASES:
        cmd = ALIASES[cmd]

    if cmd == "pwd":
        return cwd

    if cmd.startswith("cd"):
        path = cmd.split(maxsplit=1)[1] if len(cmd.split()) > 1 else os.path.expanduser("~")
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


async def terminal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    owners = context.bot_data.get("owners", [])

    if user_id not in owners:
        return

    cmd = update.message.text.strip()

    async with cwd_lock:
        output = run_cmd(cmd)

    if not output:
        output = "Done"

    for i in range(0, len(output), 4000):
        await update.message.reply_text(output[i:i+4000])


def start_bot(token, owners):
    app = ApplicationBuilder().token(token).build()

    app.bot_data["owners"] = owners
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, terminal))

    print("Bot running...")
    app.run_polling()
