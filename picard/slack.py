import os
import logging
from contextlib import contextmanager

import slack

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
    def slack_bot_client(self):
        return self.slack_connector.slack

    @property
    def slack_user_client(self):
        """
        A Slack client context manager to do operations with the user token.
        """
        return slack.WebClient(
            token=self.slack_user_token,
            run_async=True,
            ssl=self.slack_connector.ssl_context,
            proxy=os.environ.get("HTTPS_PROXY"),
        )

    async def _id_for_slack_user_token(self):
        """
        The user id of the slack_user_token.
        """
        resp = await self.slack_user_client.auth_test()
        return resp.data['user_id']

    async def set_slack_channel_description(self, slack_channel_id, description):
        """
        Set the description or topic of a channel.
        """
        try:
            resp = await self.slack_user_client.channels_SetTopic(channel=slack_channel_id,
                                                                  topic=description)
            return resp.data['topic']
        except slack.errors.SlackApiError as err:
            _LOGGER.exception(err)

    async def create_slack_channel(self, channel_name):
        """
        Create a channel on slack.
        """
        resp = await self.slack_user_client.channels_create(name=channel_name)
        return resp.data["channel"]["id"]

    async def invite_user_to_slack_channel(self, slack_channel_id, user_id):
        """
        Invite a user to a channel.
        """
        try:
            resp = await self.slack_user_client.channels_invite(channel=slack_channel_id,
                                                                user=user_id)
            return resp.body
        except slack.errors.SlackApiError as err:
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
        return {c['id']: c for c in channels.data}

    async def get_slack_channel_topic(self, slack_channel_id):
        """
        Get the topic for a channel.
        """
        response = await self.slacker_bot_client.channels_info(channel=slack_channel_id)
        return response.data['channel'].get('topic', {}).get('value', '')

    async def get_slack_channel_name(self, slack_channel_id):
        """
        Get the name for a channel.
        """
        response = await self.slacker_bot_client.channels_info(slack_channel_id)
        return response.data['channel']['name']

    async def set_slack_channel_name(self, slack_channel_id, name):
        """
        Get the name for a channel.
        """
        return await self.slack_user_client.channels.rename(channel=slack_channel_id, name=name)

    async def get_slack_channel_id_from_name(self, slack_channel_name):
        channel_map = await self.get_slack_channel_mapping()
        name_to_id = {c['name']: k for k, c in channel_map.items()}
        return name_to_id[slack_channel_name.lower()]

    def clean_slack_message(self, message):
        message = message.replace("<", "")
        message = message.replace(">", "")
        message = message.replace("&lt;", "<")
        message = message.replace("&gt;", ">")
        message = message.replace("&amp;", "&")
        return message

    async def get_all_slack_users(self):
        response = await self.slacker_bot_client.users_list()
        return [m['id'] for m in response.data['members']]

    async def get_slack_direct_message_channel(self, slack_user_id):
        response = await self.slacker_bot_client.im_open(user=slack_user_id)
        return response.data['channel']['id']
