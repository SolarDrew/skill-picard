import parse

from opsdroid.events import Message, UserInvite

from .slack import SlackMixin


class SlackBridgeMixin(SlackMixin):
    """
    Methods relating to interfacing with the Slack bridge.
    """

    link_message_template = ("link --channel_id {slack_channel_id}"
                             " --room {matrix_room_id}"
                             " --slack_bot_token {token}"
                             " --slack_user_token {u_token}")

    async def link_room(self, matrix_room_id, slack_channel_id):
        """
        Link a Matrix room to a slack room.
        """
        # Invite the slack event bot to the slack channel
        await self.invite_slack_event_bot(slack_channel_id)

        return await self._link_room_admin_message(matrix_room_id, slack_channel_id)

    async def _link_room_admin_message(self, matrix_room_id, slack_channel_id):
        """
        Send a message to the slack bridge admin room to link this room to slack.
        """
        # Invite the appservice bot to the matrix room
        await self.invite_appservice_bot(matrix_room_id)

        # Send the link command
        token = self.slack_bot_token
        u_token = self.slack_user_token

        message = self.link_message_template.format(**locals())

        await self.opsdroid.send(Message(message, target='bridge',
                                         connector=self.matrix_connector))

    async def _link_room_provisioning_api(self, matrix_room_id, slack_channel_id):
        """
        Call the slack bridge provisioning api to link this room to slack.
        """
        raise NotImplementedError("Wont get around to this one for a while.")

    async def unlink_room(self, matrix_room_id, slack_channel_id=None):
        """
        Unlink and leave the bridge.
        """
        await self._unlink_room_admin_message(matrix_room_id)

    async def _unlink_room_admin_message(self, matrix_room_id):
        await self.opsdroid.send(Message(f"leave {matrix_room_id}",
                                         target='bridge',
                                         connector=self.matrix_connector))

        await self.opsdroid.send(Message(f"unlink --room {matrix_room_id}",
                                         target='bridge',
                                         connector=self.matrix_connector))

    async def invite_appservice_bot(self, matrix_room_id):
        """
        Invite the slack appservice bot to the matrix room.
        """
        await self.opsdroid.send(UserInvite(target=matrix_room_id,
                                            user=self.config["appservice_bot_mxid"],
                                            connector=self.matrix_connector))

    async def invite_slack_event_bot(self, slack_channel_id):
        """
        Invite the slack bot to the room so it can listen to messages.
        """
        # Ensure the user is in the room.
        channel_name = await self.get_slack_channel_name(slack_channel_id)
        await self.slack_user_client.channels_join(name=channel_name)

        bot_name = self.config['slack_bot_name']
        # Defined in SlackMixin
        bot_user_id = await self.get_slack_user_id(bot_name)

        # Defined in SlackMixin
        return await self.invite_user_to_slack_channel(slack_channel_id, bot_user_id)

    async def matrix_room_id_from_slack_channel_id(self, slack_channel_id):
        slack_channel_name = await self.get_slack_channel_name(slack_channel_id)
        return await self.matrix_room_id_from_slack_channel_name(slack_channel_name)

    async def matrix_room_id_from_slack_channel_name(self, slack_channel_name):
        """
        Return the first template alias for the given channel name.
        """
        room_alias_template = self.config.get('room_alias_templates')[0]
        room_alias = room_alias_template.format(name=slack_channel_name)

        return await self.room_id_if_exists(room_alias)

    async def slack_channel_id_from_matrix_room_id(self, matrix_room_id):
        """
        Get the slack channel id based on the canonical alias.
        """
        room_state = await self.matrix_api.get_room_state(matrix_room_id)
        room_state = list(filter(lambda x: x['type'] == "m.room.canonical_alias", room_state))
        if not room_state:
            return
        canonical_alias = room_state[0]['content']['alias']

        room_alias_templates = self.config.get('room_alias_templates', [])
        if not room_alias_templates:
            return

        name = parse.parse(room_alias_templates[0], canonical_alias)['name']

        return await self.get_slack_channel_id_from_name(name)
