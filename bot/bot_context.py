"""Singleton to share the bot instance across modules."""

_bot = None


def set_bot(bot):
    global _bot
    _bot = bot


def get_bot():
    return _bot
