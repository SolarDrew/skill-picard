class SlackMixin:
    """
    The methods relating to the slack side of the bridge.
    """

    async def create_slack_channel(self, channel_name, topic):
        """
        Create a channel on slack.
        """
