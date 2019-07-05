from opsdroid.events import Message, UserInvite


class SlackBridgeMixin:
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
        return await self._link_room_admin_message(matrix_room_id, slack_channel_id)

    async def _link_room_admin_message(self, matrix_room_id, slack_channel_id):
        """
        Send a message to the slack bridge admin room to link this room to slack.
        """
        # Invite the appservice bot to the matrix room
        await self.invite_appservice_bot(matrix_room_id)

        # Invite the slack event bot to the slack channel
        await self.invite_slack_event_bot(slack_channel_id)

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
        bot_name = self.config['slack_bot_name']
        # Defined in SlackMixin
        bot_user_id = await self.get_slack_user_id(bot_name)

        # Defined in SlackMixin
        return await self.invite_user_to_slack_channel(slack_channel_id, bot_user_id)

    async def matrix_room_id_from_slack_channel_name(self, slack_channel_name):
        """
        Return the first template alias for the given channel name.
        """
        room_alias_template = self.config.get('room_alias_template')[0]
        room_alias = room_alias_template.format(name=slack_channel_name)

        return await self.room_id_if_exists(room_alias)
