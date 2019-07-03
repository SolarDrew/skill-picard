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

    async def _configure_new_matrix_room(self, matrix_room_id):
        """
        Given Picard's config, setup the matrix side as appropriate.
        """
        invite_users = (self.config.get("users_to_invite", []) +
                        self.config.get('users_to_admin', []))

        await self.invite_to_matrix_room(matrix_room_id, invite_users)

        await self.make_matrix_admin_from_config(matrix_room_id)

        if self.config.get("allow_at_room", False):
            await self.matrix_atroom_pl_0(matrix_room_id)

    @match_regex('!createroom (?P<name>.+?) "(?P<topic>.+?)"')
    async def on_matrix_create_room_command(self, message):
        await message.respond('Riker to the Bridge')
        name, topic = (message.regex['name'],
                       message.regex['topic'])

        is_public = self.config.get("make_public", False)
        matrix_room_id = await self.create_new_matrix_channel(name, topic, is_public)

        await self._configure_new_matrix_room(matrix_room_id)

        # Create the corresponding slack channel
        slack_channel_id = await self.create_slack_channel(name)

        # Link the two rooms
        await self.link_room(matrix_room_id, slack_channel_id)

        # Set the description of the slack channel
        await self.set_slack_channel_description(slack_channel_id, topic)

        # Invite Command User
        await self.opsdroid.send(UserInvite(target=matrix_room_id,
                                            user=message.raw_event['sender']))

        return matrix_room_id

    async def on_new_slack_channel(self, channel):
        """
        React to a new slack channel event.
        """
        is_public = self.config.get("make_public", False)
        matrix_room_id = await self.create_new_matrix_channel(name, topic, is_public)

        # Link the rooms
        await self.link_room(matrix_room_id, slack_channel_id)

        # Setup the rest of the matrix room
        await self._configure_new_matrix_room(matrix_room_id)
