import asyncio
import logging
from textwrap import dedent

from markdown import markdown

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
from .slack import SlackMixin
from .slackbridge import SlackBridgeMixin
from .util import RoomMemory

_LOGGER = logging.getLogger(__name__)


class Picard(Skill, MatrixMixin, SlackMixin, SlackBridgeMixin, MatrixCommunityMixin):

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

    @match_regex("!help")
    @ignore_appservice_users
    async def on_help(self, message):
        help_text = dedent("""\
        Valid Commands are:


        * !createroom (name) "(topic)"

        Create a new room.

        Matrix user commands:

        * !inviteall

        Get invites to all matrix rooms.

        * !autoinvite [disable]

        Enable or disable invites to all new matrix rooms.

        """)

        if message.connector is self.matrix_connector:
            help_text = markdown(help_text)

        return await message.respond(help_text)

    @match_regex("!inviteall")
    @constrain_connectors("matrix")
    @ignore_appservice_users
    async def on_invite_all(self, message):
        rooms = await self.get_all_community_rooms()
        for r in rooms:
            await message.respond(UserInvite(user=message.raw_event['sender'],
                                             target=r,
                                             connector=self.matrix_connector))

    @match_regex("!autoinvite")
    @constrain_connectors("matrix")
    @ignore_appservice_users
    async def on_auto_invite(self, message):
        sender = message.raw_event['sender']
        users = await self.opsdroid.memory.get("autoinvite_users") or []
        if sender in users:
            return await message.respond("You already have autoinvite enabled.")
        users.append(sender)
        await self.opsdroid.memory.put("autoinvite_users", users)

        return await message.respond(
            "You will be invited to all future rooms. Use !inviteall to get invites to existing rooms.")

    @match_regex("!autoinvite disable")
    @constrain_connectors("matrix")
    @ignore_appservice_users
    async def on_disable_auto_invite(self, message):
        sender = message.raw_event['sender']
        users = await self.opsdroid.memory.get("autoinvite_users") or []
        if sender not in users:
            return await message.respond("You do not have autoinvite enabled.")
        users.remove(sender)
        await self.opsdroid.memory.put("autoinvite_users", users)

        return await message.respond("Autoinvite disabled.")

    @match_regex('!createroom (?P<name>.+?) "(?P<topic>.+?)"')
    @ignore_appservice_users
    async def on_create_room_command(self, message):
        # TODO: Ignore duplicates here, if a slack user sends this message in a
        # bridged room, we react to both the original slack message and the
        # matrix message.
        async with self._slack_channel_lock:
            await message.respond('Creating room please wait...')

            name, topic = (message.regex['name'],
                           message.regex['topic'])

            is_public = self.config.get("make_public", False)
            matrix_room_id = await self.create_new_matrix_room()

            await self.configure_new_matrix_room_pre_bridge(matrix_room_id, is_public)

            # Create the corresponding slack channel
            slack_channel_id = await self.create_slack_channel(name)

            # Link the two rooms
            await self.link_room(matrix_room_id, slack_channel_id)

            # Setup the matrix room
            matrix_room_alias = await self.configure_new_matrix_room_post_bridge(
                matrix_room_id, name, topic)

            # Set the description of the slack channel
            await self.set_slack_channel_description(slack_channel_id, topic)

            # Invite Command User
            if message.connector is self.matrix_connector:
                user = message.raw_event['sender']
                target = matrix_room_id
                command_room = message.target

                await self.opsdroid.send(UserInvite(target=target,
                                                    user=user,
                                                    connector=message.connector))

            elif message.connector is self.slack_connector:
                user = message.raw_event['user']
                target = slack_channel_id
                command_room = await self.matrix_room_id_from_slack_channel_name(message.target)

                await self.invite_user_to_slack_channel(slack_channel_id, user)

            # Inform users about the new room/channel
            pill = f'<a href="https://matrix.to/#/{matrix_room_alias}">{matrix_room_alias}</a>'
            await self.opsdroid.send(Message(f"Created a new room: {pill}",
                                             target=command_room,
                                             connector=self.matrix_connector))

            await self.announce_new_room(matrix_room_id, slack_channel_id)

            return matrix_room_id

    @match_event(OpsdroidStarted)
    @match_regex('!bridgeall')
    @admin_command
    async def bridge_all_slack_channels(self, message):
        """
        Iterate over all slack channels and bridge them one by one.
        """
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
    async def on_new_slack_channel(self, channel):
        """
        React to a new slack channel event.
        """
        # This should be an opsdroid constraint one day
        if channel.connector is not self.slack_connector:
            return

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
