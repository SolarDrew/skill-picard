import asyncio
import logging
from textwrap import dedent

from markdown import markdown
from opsdroid.constraints import constrain_connectors
from opsdroid.matchers import match_regex
from opsdroid.events import (JoinRoom, Message, NewRoom, OpsdroidStarted,
                             RoomDescription, UserInvite)

from .constraints import ignore_appservice_users, admin_command

_LOGGER = logging.getLogger(__name__)


class PicardCommands:
    @match_regex("!help")
    @ignore_appservice_users
    async def on_help(self, message):
        help_text = dedent(f"""\
        Hi {message.user}! Here are the commands you can use in the chat. Please use these commands in a private chat with the bot, to avoid spamming other users.

        * `!help`: show this help message
        * `!createroom (name of new room) "[topic of new room, optional]"`: make a new room (on both matrix and slack). On the matrix side, this is the only way to make a new room, because it will be automatically added to the community and bridged to slack. From the slack side, you can either run this command or create the room normally through the UI, both will work correctly on the matrix side.
        """)

        if message.connector is self.matrix_connector:
            help_text += dedent("""\

            These additional commands are only available here on the matrix side:

            * `!inviteall`: make the bot invite you to all rooms currently in the community
            * `!autoinvite` / `!autoinvite disable`: Switch on/off automatic invitations to new rooms when they are created
            """)

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

    @match_regex("!createroom (?P<name>.+?)(?P<topic> .+)?")
    @ignore_appservice_users
    async def on_create_room_command(self, message):
        await message.respond('Creating room please wait, this takes a little while...')

        name, topic = (message.regex['name'],
                       message.regex['topic'])

        is_public = self.config.get("make_public", False)
        matrix_room_id = await self.create_new_matrix_room()

        await self.configure_new_matrix_room_pre_bridge(matrix_room_id, is_public)

        async with self._slack_channel_lock:
            # Create the corresponding slack channel
            slack_channel_id = await self.create_slack_channel(name)

            # Just to make sure we get the slack new room event
            await asyncio.sleep(0.1)

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

        await self.announce_new_room(matrix_room_alias, message.user, topic)

        return matrix_room_id

    @match_regex('!welcomeall')
    @ignore_appservice_users
    async def on_welcome_all(self, message):
        """Send the appropriate welcome message to all current users"""
        matrix_users = await self.get_all_community_users()
        for user in matrix_users:
            await self.send_matrix_welcome_message(user)

        slack_users = await self.get_all_slack_users()
        for user in slack_users:
            await self.send_slack_welcome_message()
