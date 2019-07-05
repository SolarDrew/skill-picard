import logging

from opsdroid.matchers import match_regex
from opsdroid.events import UserInvite
from opsdroid.skill import Skill

from opsdroid.connector.matrix import ConnectorMatrix
from opsdroid.connector.slack import ConnectorSlack


from .matrix import MatrixMixin
from .slack import SlackMixin
from .slackbridge import SlackBridgeMixin


_LOGGER = logging.getLogger(__name__)


class Picard(Skill, MatrixMixin, SlackMixin, SlackBridgeMixin):

    @property
    def matrix_connector(self):
        return self.opsdroid._connector_names['matrix']

    @property
    def slack_connector(self):
        return self.opsdroid._connector_names['slack']

    @match_regex('!createroom (?P<name>.+?) "(?P<topic>.+?)"')
    async def on_matrix_create_room_command(self, message):
        await message.respond('Riker to the Bridge')
        name, topic = (message.regex['name'],
                       message.regex['topic'])

        is_public = self.config.get("make_public", False)
        matrix_room_id = await self.create_new_matrix_channel()

        await self.configure_new_matrix_room_pre_bridge(matrix_room_id, is_public)

        # Create the corresponding slack channel
        slack_channel_id = await self.create_slack_channel(name)

        # Link the two rooms
        await self.link_room(matrix_room_id, slack_channel_id)

        # Setup the matrix room
        await self.configure_new_matrix_room_post_bridge(matrix_room_id, name, topic)

        # Set the description of the slack channel
        await self.set_slack_channel_description(slack_channel_id, topic)

        # Invite Command User
        await self.opsdroid.send(UserInvite(target=matrix_room_id,
                                            user=message.raw_event['sender']))

        return matrix_room_id

    @match_regex('!bridgeall')
    async def bridge_all_slack_channels(self, message):
        """
        Iterate over all slack channels and bridge them one by one.
        """

        channels = await self.get_slack_channel_mapping()
        for slack_channel_id, channel in channels.items():
            slack_channel_name = channel['name']
            _LOGGER.debug(f"Processing... {slack_channel_name}")

            matrix_room_id = await self.matrix_room_id_from_slack_channel_name(slack_channel_name)

            if channel['is_archived'] and matrix_room_id:
                # await self.archive_matrix_channel(matrix_room_id)
                continue

            if not matrix_room_id:
                matrix_room_id = await self.create_new_matrix_channel()

            await self.configure_new_matrix_room_pre_bridge(matrix_room_id,
                                                            self.config.get("make_public", False))

            # Link the two rooms
            await self.link_room(matrix_room_id, slack_channel_id)

            # Setup the matrix room
            await self.configure_new_matrix_room_post_bridge(matrix_room_id,
                                                             slack_channel_name,
                                                             channel['topic']['value'])

    async def on_new_slack_channel(self, channel):
        """
        React to a new slack channel event.
        """
        is_public = self.config.get("make_public", False)
        matrix_room_id = await self.create_new_matrix_channel(name, topic,
                                                              is_public)

        # Link the rooms
        await self.link_room(matrix_room_id, slack_channel_id)

        # Setup the rest of the matrix room
        await self.configure_new_matrix_room(matrix_room_id)
