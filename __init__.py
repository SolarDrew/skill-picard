import logging

from opsdroid.matchers import match_regex
from opsdroid.events import UserInvite, Message
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
        matrix_room_id = await self.create_new_matrix_room()

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

        # Inform users about the new room/channel
        await message.respond(f"Created a new room: #{matrix_room_alias}")
        await self.announce_new_room(matrix_room_id, slack_channel_id)

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
                                                             channel['topic']['value'])

    @match_event(NewRoom)
    async def on_new_slack_channel(self, channel):
        """
        React to a new slack channel event.
        """
        # This should be an opsdroid constraint one day
        if NewRoom.connector is not self.slack_connector:
            return

        is_public = self.config.get("make_public", False)
        matrix_room_id = await self.create_new_matrix_room()

        await self.configure_new_matrix_room_pre_bridge(matrix_room_id,
                                                        is_public)

        # Link the two rooms
        await self.link_room(matrix_room_id, slack_channel_id)

        # Setup the matrix room
        await self.configure_new_matrix_room_post_bridge(matrix_room_id,
                                                         channel.name,
                                    # TODO read channel from event
                                                         "topic")

        await self.accounce_new_room(matrix_room_id, slack_channel_id)

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
