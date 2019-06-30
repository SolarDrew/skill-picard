class SlackBridgeMixin:
    """
    Methods relating to interfacing with the Slack bridge.
    """

    async def link_room(self, matrix_room_id, slack_channel_id):
        """
        Link a Matrix room to a slack room.
        """
        return self._link_room_admin_message(matrix_room_id, slack_channel_id)

    async def _link_room_admin_message(self, matrix_room_id, slack_channel_id):
        """
        Send a message to the slack bridge admin room to link this room to slack.
        """

    async def _link_room_provisioning_api(self, matrix_room_id, slack_channel_id):
        """
        Call the slack bridge provisioning api to link this room to slack.
        """
        raise NotImplementedError("Wont get around to this one for a while.")

    async def invite_appservice_bot(self, matrix_room_id):
        """
        Invite the slack appservice bot to the matrix room.
        """

    async def invite_slack_event_bot(self, slack_channel_id):
        """
        Invite the slack bot to the room so it can listen to messages.
        """
