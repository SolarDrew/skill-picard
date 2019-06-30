import logging

from opsdroid.matchers import match_regex
from opsdroid.events import *
from opsdroid.skill import Skill

from opsdroid.connector.matrix import ConnectorMatrix
from opsdroid.connector.matrix.events import *


_LOGGER = logging.getLogger(__name__)


class Picard(Skill):

    @property
    def matrix_connector(self):
        return list(filter(lambda x: isinstance(x, ConnectorMatrix),
                           self.opsdroid.connectors))[0]

    @property
    def matrix_api(self):
        return self.matrix_connector.connection

    @match_regex("!createroom (?P<name>.+?) (?P<topic>.+?) (?P<desc>.+?)")
    async def matrix_create_room_command(self, message):
        await message.respond('Riker to the Bridge')
        name, topic, desc = (message.regex['name'],
                             message.regex['topic'],
                             message.regex['desc'])

        is_public = self.config.get("make_public", False)
        room_id = await self.create_new_matrix_channel(name, topic, desc, is_public)
        invite_users = (self.config.get("users_to_invite", []) +
                        self.config.get('users_to_admin', []))

        await self.invite_to_matrix_room(room_id, invite_users)

        # Invite Command User
        await self.opsdroid.send(UserInvite(target=room_id,
                                            user=message.raw_event['sender']))

        await self.make_matrix_admin_from_config(room_id)

        if self.config.get("allow_at_room", False):
            await self.matrix_atroom_pl_0(room_id)

        return room_id

    async def create_new_matrix_channel(self, name, topic, desc, is_public=True):
        """
        Create a new matrix channel with defaults from config.
        """
        # Create Room
        room_id = await self.opsdroid.send(NewRoom())
        if is_public:
            await self.opsdroid.send(MatrixJoinRules("public", target=room_id))
            await self.opsdroid.send(MatrixHistoryVisibility("world_readable", target=room_id))

        # Set Aliases
        if self.config.get("alias_template"):
            alias_template = self.config['alias_template']
            await self.opsdroid.send(RoomAddress(target=room_id,
                                                 address=alias_template.format(name=name)))

        # Set Room Name
        if self.config.get("name_template"):
            name_template = self.config['name_template']
            await self.opsdroid.send(RoomName(target=room_id,
                                              name=name_template.format(name=name)))

        # Set Room Image
        url = self.config.get("room_avatar_url")
        if url:
            await self.opsdroid.send(RoomImage(Image(url=url), target=room_id))

        # Set Room Description
        await self.opsdroid.send(RoomDescription(desc, target=room_id))

        # Add to community
        # Enable flairs

        return room_id

    async def invite_to_matrix_room(self, room_id, users):
        """
        Invite the listed users to the room.
        """
        for user in users:
            await self.opsdroid.send(UserInvite(target=room_id,
                                                user=user))

    async def make_matrix_admin_from_config(self, room_id):
        """
        Read the configuration file and make people in the 'users_as_admin'
        list admin in the room.
        """
        # Make config people admin
        for user in self.config.get("users_as_admin", []):
            await self.opsdroid.send(UserRole(target=room_id,
                                              user=user, role='admin'))

    async def matrix_atroom_pl_0(self, room_id):
        power_levels = await self.matrix_api.get_power_levels(room_id)

        notifications = power_levels.get('notifications', {})
        notifications['room'] = 0
        power_levels['notifications'] = notifications

        return await self.opsdroid.send(MatrixPowerLevels(power_levels, target=room_id))
