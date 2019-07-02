from opsdroid.events import Message


class SlackBridgeMixin:
    """
    Methods relating to interfacing with the Slack bridge.
    """

    link_message_template = ("link --channel_id {slack_channel_id}"
                             " --room {matrix_room_id}"
                             "--slack_bot_token {token}"
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
        token = self.config['slack_bot_token']
        u_token = self.config['slack_user_token']

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
        await self.opsdroid.send(UserInvite(target=matrix_room_id,
                                            user=self.config["slack_bot_name"],
                                            connector=self.slack_connector))
