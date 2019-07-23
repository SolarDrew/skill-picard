import asyncio
import logging

from opsdroid.connector.matrix import ConnectorMatrix
from opsdroid.connector.slack import ConnectorSlack
from opsdroid.constraints import constrain_connectors
from opsdroid.events import (JoinRoom, Message, NewRoom, OpsdroidStarted,
                             RoomDescription, UserInvite)
from opsdroid.matchers import match_event, match_regex
from opsdroid.skill import Skill

from .constraints import ignore_appservice_users, admin_command
from .matrix import MatrixMixin
from .matrix_groups import MatrixCommunityMixin
from .slackbridge import SlackBridgeMixin
from .util import RoomMemory
from .commands import PicardCommands

_LOGGER = logging.getLogger(__name__)


class Picard(Skill, PicardCommands, MatrixMixin, SlackBridgeMixin, MatrixCommunityMixin):

    def __init__(self, opsdroid, config, *args, **kwargs):
        super().__init__(opsdroid, config, *args, **kwargs)

        self._slack_channel_lock = asyncio.Lock()
        self.memory = RoomMemory(self.opsdroid)

    @property
    def matrix_connector(self):
        return self.opsdroid._connector_names['matrix']

    @property
    def slack_connector(self):
        return self.opsdroid._connector_names['slack']

    @match_regex('!bridgeall')
    @match_event(OpsdroidStarted)
    @admin_command
    async def bridge_all_slack_channels(self, message):
        """
        Iterate over all slack channels and bridge them one by one.
        """
        if (isinstance(message, OpsdroidStarted) and
            not self.config.get("copy_from_slack_startup", True)):

            return

        channels = await self.get_slack_channel_mapping()
        for slack_channel_id, channel in channels.items():
            slack_channel_name = channel['name']
            _LOGGER.info(f"Processing... {slack_channel_name}")

            matrix_room_id = await self.join_or_create_matrix_room(slack_channel_name)

            # TODO: This iteration doesn't include archived channels.
            if channel['is_archived'] and matrix_room_id:
                # await self.archive_matrix_room(matrix_room_id)
                continue

            if not matrix_room_id:
                matrix_room_id = await self.create_new_matrix_room()

            await self.configure_new_matrix_room_pre_bridge(matrix_room_id,
                                                            self.config.get("make_public", False))

            # Link the two rooms
            await self.link_room(matrix_room_id, slack_channel_id)

            # Setup the matrix room
            await self.configure_new_matrix_room_post_bridge(matrix_room_id,
                                                             slack_channel_name,
                                                             channel['topic']['value'],
                                                             _bridgeall=False)

        await self.opsdroid.send(Message("Finished adding all channels.",
                                         target="main",
                                         connector=self.matrix_connector))

    @match_event(NewRoom)
    @constrain_connectors("slack")
    async def on_new_slack_channel(self, channel):
        """
        React to a new slack channel event.
        """
        # If we have created a slack channel we want to not react to it.
        if self._slack_channel_lock.locked():
            _LOGGER.info("Ignoring channel create event from slack, creation locked.")
            return

        is_public = self.config.get("make_public", False)
        matrix_room_id = await self.join_or_create_matrix_room(channel.name)

        await self.configure_new_matrix_room_pre_bridge(matrix_room_id,
                                                        is_public)

        # Link the two rooms
        await self.link_room(matrix_room_id, channel.target)

        # Retrieve topic from slack
        topic = await self.get_slack_channel_topic(channel.target)

        # Setup the matrix room
        await self.configure_new_matrix_room_post_bridge(matrix_room_id,
                                                         channel.name,
                                                         topic)

        await self.announce_new_room(matrix_room_id, channel.target)

    @match_event(RoomDescription)
    async def on_topic_change(self, topic):
        """Handle a topic change."""

        if topic.connector is self.matrix_connector:
            slack_channel_id = await self.slack_channel_id_from_matrix_room_id(topic.target)
            await self.set_slack_channel_description(slack_channel_id, topic.description)

        elif topic.connector is self.slack_connector:
            user_id = await self._id_for_slack_user_token()
            if topic.raw_event['user'] == user_id:
                return

            slack_channel_name = await self.get_slack_channel_name(topic.target)
            matrix_room_id = await self.matrix_room_id_from_slack_channel_name(slack_channel_name)

            topic.target = matrix_room_id
            topic.connector = self.matrix_connector

            await self.opsdroid.send(topic)

    @match_event(UserInvite)
    @constrain_connectors("matrix")
    async def on_invite_to_room(self, invite):
        """
        Join all rooms on invite.
        """
        return await invite.respond(JoinRoom())

    async def announce_new_room(self, matrix_room_id, slack_channel_id):
        """
        Send a message to the configured room announcement room.
        """

        # Stuart proposes the wording of this be:
        # "<username> just created the <room_id> [room/channel] for discussing <topic>"

        # await self.opsdroid.send(Message(
        #     text="A new room was created! Head to #{matrix_room_alias} to follow the conversation",
        #     target=matrix_room_id,
        #     connector=self.matrix_connector))

        # await self.opsdroid.send(Message(
        #     text="A new room was created! Head to #{slack_channel_name} to follow the conversation",
        #     target=slack_channel_id,
        #     connector=self.slack_connector))
