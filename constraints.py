import asyncio
import logging

from opsdroid.events import Message

_LOGGER = logging.getLogger(__name__)

__all__ = ['admin_command', 'ignore_appservice_users']


def _future_none():
    fu = asyncio.Future()
    fu.set_result(None)
    return fu


def ignore_appservice_users(f):
    def wrapper(self, message):
        prefix = self.config.get("appservice_prefix", "@slack_")
        if (message.connector is self.matrix_connector
            and message.raw_event['sender'].startswith(prefix)):

            return _future_none()

        return f(self, message)

    return wrapper


def admin_command(f):
    def wrapper(self, message):
        if isinstance(message, Message) and message.target != self.matrix_connector.room_ids['main']:
            return _future_none()

        return f(self, message)

    return wrapper
