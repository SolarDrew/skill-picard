import logging
from contextlib import contextmanager

import slacker
from aioslacker import Slacker

from opsdroid.events import NewRoom, RoomDescription

_LOGGER = logging.getLogger(__name__)


class SlackMixin:
    """
    The methods relating to the slack side of the bridge.
    """

    @property
    def slack_bot_token(self):
        """
        The slack bot token.
        """
        return self.config['slack_bot_token']

    @property
    def slack_user_token(self):
        """
        The other slack token.
        """
        return self.config['slack_user_token']

    @property
    def slacker_bot_client(self):
        return self.slack_connector.slacker

    @property
    def slacker_user_client(self):
        """
        A Slacker client context manager to do operations with the user token.
        """
        @contextmanager
        def _slacker():
            client = Slacker(token=self.slack_user_token)
            yield client
            client.close()
        return _slacker()

    async def set_slack_channel_description(self, slack_channel_id, description):
        """
        Set the description or topic of a channel.
        """
        with self.slacker_user_client as client:
            resp = await client.channels.set_topic(slack_channel_id, description)

        return resp.body['topic']

    async def create_slack_channel(self, channel_name):
        """
        Create a channel on slack.
        """
        with self.slacker_user_client as client:
            resp = await client.channels.create(channel_name)

        return resp.body["channel"]["id"]

    async def invite_user_to_slack_channel(self, slack_channel_id, user_id):
        """
        Invite a user to a channel.
        """
        with self.slacker_user_client as client:
            try:
                resp = await client.channels.invite(slack_channel_id, user_id)
                return resp.body
            except slacker.Error as err:
                _LOGGER.exception(err)

    async def get_slack_user_id(self, user_name):
        """
        Look up a slack user id based on their name.
        """
        # This is bugged in aioslacker, so we reimplement it.
        members = await self.slacker_bot_client.users.list()
        return slacker.get_item_id_by_name(members.body['members'], user_name)

    async def get_slack_channel_list(self):
        response = await self.slacker_bot_client.channels.list()
        return response.body['channels']

    async def get_slack_channel_mapping(self):
        """
        Map slack channel ids to their channel info dict
        """
        channels = await self.get_slack_channel_list()
        return {c['id']: c for c in channels}
