from opsdroid.events import NewRoom, RoomDescription


class SlackMixin:
    """
    The methods relating to the slack side of the bridge.
    """

    async def create_slack_channel(self, channel_name):
        """
        Create a channel on slack.
        """
        return await self.opsdroid.send(NewRoom(name=channel_name,
                                                connector=self.slack_connector))

    async def set_slack_channel_description(self, slack_channel_id, description):
        """
        Set the description or topic of a channel.
        """
        return await self.opsdroid.send(RoomDescription(description,
                                                        connector=self.slack_connector))
