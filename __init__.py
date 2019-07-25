import asyncio
import logging
from textwrap import dedent

from markdown import markdown
from parse import parse

from opsdroid.connector.matrix import ConnectorMatrix
from opsdroid.connector.slack import ConnectorSlack
from opsdroid.connector.slack import events as slack_events
from opsdroid.events import (JoinGroup, JoinRoom, Message, NewRoom,
                             OpsdroidStarted, RoomDescription, RoomName,
                             UserInvite)
from opsdroid.matchers import match_event, match_regex
from opsdroid.skill import Skill

from .commands import PicardCommands
from .constraints import (admin_command, constrain_matrix_connector,
                          constrain_slack_connector, ignore_appservice_users)
from .matrix import MatrixMixin
from .matrix_groups import MatrixCommunityMixin
from .slackbridge import SlackBridgeMixin
from .util import RoomMemory

_LOGGER = logging.getLogger(__name__)


class Picard(Skill, PicardCommands, MatrixMixin, SlackBridgeMixin, MatrixCommunityMixin):

    def __init__(self, opsdroid, config, *args, **kwargs):
        super().__init__(opsdroid, config, *args, **kwargs)

        self._slack_channel_lock = asyncio.Lock()
        self._slack_rename_lock = asyncio.Lock()
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

        if isinstance(message, Message):
            await message.respond("Running the bridgeall command.")

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

    @match_event(slack_events.ChannelArchived)
    async def on_archive_slack_channel(self, archive):
        matrix_room_id = await self.matrix_room_id_from_slack_channel_id(archive.target)
        if not matrix_room_id:
            return

        await self.archive_matrix_room(matrix_room_id)

        await self.unlink_room(matrix_room_id, archive.target)

    @match_event(slack_events.ChannelUnarchived)
    async def on_unarchive_slack_channel(self, unarchive):
        matrix_room_id = await self.matrix_room_id_from_slack_channel_id(unarchive.target)
        if matrix_room_id:
            await self.unarchive_matrix_room(matrix_room_id)

        name = await self.get_slack_channel_name(unarchive.target)
        new_room = NewRoom(name=name,
                           target=unarchive.target,
                           connector=unarchive.connector)

        return await self.on_new_slack_channel(new_room)

    @match_event(NewRoom)
    @constrain_slack_connector
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
        canonical_alias = await self.configure_new_matrix_room_post_bridge(matrix_room_id,
                                                                           channel.name,
                                                                           topic)

        await self.announce_new_room(canonical_alias, channel.user, topic)

    @match_event(RoomDescription)
    async def on_topic_change(self, topic):
        """Handle a topic change."""
        _LOGGER.debug(f"Got RoomDescription object from {topic.connector.name}")
        if topic.connector is self.matrix_connector:
            with self.memory[topic.target]:
                room_options = await self.opsdroid.memory.get("picard.options") or {}

            if not room_options.get("skip_room_description"):
                _LOGGER.debug(f"Setting slack room description to: {topic.description}")
                slack_channel_id = await self.slack_channel_id_from_matrix_room_id(topic.target)
                await self.set_slack_channel_description(slack_channel_id, topic.description)
            else:
                _LOGGER.debug("Matrix Connector: Not setting topic because of room options.")

        elif topic.connector is self.slack_connector:
            user_id = await self._id_for_slack_user_token()
            if topic.raw_event['user'] == user_id:
                return

            slack_channel_name = await self.get_slack_channel_name(topic.target)
            matrix_room_id = await self.matrix_room_id_from_slack_channel_name(slack_channel_name)
            with self.memory[matrix_room_id]:
                room_options = await self.opsdroid.memory.get("picard.options") or {}

            if not room_options.get("skip_room_description"):
                _LOGGER.debug(f"Setting matrix room description to: {topic.description}")
                topic.target = matrix_room_id
                topic.connector = self.matrix_connector
                topic.description = self.clean_slack_message(topic.description)

                await self.opsdroid.send(topic)
            else:
                _LOGGER.debug(f"{room_options}")
                _LOGGER.debug("Slack Connector: Not setting topic because of room options.")

    @match_event(RoomName)
    async def on_name_change(self, room_name):
        """Handle a room name change."""
        name_template = self.config.get("room_name_template")
        if not name_template:
            return
        if room_name.connector is self.matrix_connector:
            name = parse(name_template, room_name.name)['name']
            matrix_room_id = room_name.target
            slack_channel_id = await self.slack_channel_id_from_matrix_room_id(room_name.target)
            old_name = await self.get_slack_channel_name(slack_channel_id)

        if room_name.connector is self.slack_connector:
            if self._slack_rename_lock.locked():
                return
            slack_channel_id = room_name.target
            old_name = room_name.raw_event['old_name']
            matrix_room_id = await self.matrix_room_id_from_slack_channel_name(old_name)
            name = room_name.name

            if old_name == name:
                return

        with self.memory[matrix_room_id]:
            room_options = await self.opsdroid.memory.get("picard.options") or {}
        if room_options.get("skip_room_name"):
            return

        # Remove the aliases for the old name
        await self.remove_room_aliases(old_name)

        # Add new aliases
        await self.configure_room_aliases(matrix_room_id, name)

        if room_name.connector is self.matrix_connector:
            async with self._slack_rename_lock:
                await self.set_slack_channel_name(slack_channel_id, name)

        if room_name.connector is self.slack_connector:
            new_name = RoomName(name=name_template.format(name=name),
                                target=matrix_room_id,
                                connector=self.matrix_connector)
            return await self.opsdroid.send(new_name)

    @match_event(UserInvite)
    @constrain_matrix_connector
    async def on_invite_to_room(self, invite):
        """
        Join all rooms on invite.
        """
        await invite.respond(JoinRoom())

        if await self.is_one_to_one_chat(invite.target):
            dms = await self.opsdroid.memory.get("direct_messages") or {}
            dms.update({invite.raw_event['sender']: invite.target})
            await self.opsdroid.memory.put("direct_messages", dms)

            return await self.send_matrix_welcome_message(invite.target)

    @match_event(JoinGroup)
    @constrain_matrix_connector
    async def on_new_community_user(self, join):
        """
        React to a new user joining the community on matrix.
        """
        dms = await self.opsdroid.memory.get("direct_messages") or {}

        if join.user not in dms:
            matrix_room_id = await self.create_new_matrix_direct_message(join.user)
            dms.update({join.user: matrix_room_id})
            await self.opsdroid.memory.put("direct_messages", dms)
        else:
            matrix_room_id = dms[join.user]

        await self.send_matrix_welcome_message(matrix_room_id)

    async def send_matrix_welcome_message(self, matrix_room_id):
        """
        Send the welcome message to a matrix 1-1.
        """
        welcome_message = self.config.get('welcome', {}).get('matrix')
        if welcome_message:
            welcome_message = markdown(dedent(welcome_message))
            return await self.opsdroid.send(Message(welcome_message,
                                                    target=matrix_room_id,
                                                    connector=self.matrix_connector))

    @match_event(JoinGroup)
    @constrain_slack_connector
    async def on_new_team_user(self, join):
        """
        React to a new user joining the team on slack.
        """
        return await self.send_slack_welcome_message(join.user)

    async def send_slack_welcome_message(self, slack_user_id):
        """
        Send the welcome message to a slack 1-1.
        """
        welcome_message = self.config.get('welcome', {}).get('slack')
        slack_room_id = await self.get_slack_direct_message_channel(slack_user_id)
        if welcome_message:
            return await self.opsdroid.send(Message(dedent(welcome_message),
                                                    target=slack_room_id,
                                                    connector=self.slack_connector))

    async def announce_new_room(self, matrix_room_alias, username, topic):
        """
        Send a message to the configured room announcement room.
        """
        room_name = self.config.get("announcement_room_name")
        if not room_name:
            return
        matrix_room_id = await self.matrix_room_id_from_slack_channel_name(room_name)

        pill = f'<a href="https://matrix.to/#/{matrix_room_alias}">{matrix_room_alias}</a>'

        text = f"{username} just created the {pill} room"
        if topic:
            text += f" for discussing '{topic}'"
        text += '.'

        await self.opsdroid.send(Message(
            text=text,
            target=matrix_room_id,
            connector=self.matrix_connector))
