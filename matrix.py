from opsdroid.events import *
from opsdroid.connector.matrix.events import *


class MatrixMixin:
    """
    Matrix Operations for Picard.
    """
    async def create_new_matrix_channel(self, name, topic, is_public=True):
        """
        Create a new matrix channel with defaults from config.
        """
        # Create Room
        matrix_room_id = await self.opsdroid.send(NewRoom())
        if is_public:
            await self.opsdroid.send(MatrixJoinRules("public", target=matrix_room_id,
                                     connector=self.matrix_connector))
            await self.opsdroid.send(MatrixHistoryVisibility("world_readable", target=matrix_room_id,
                                                             connector=self.matrix_connector))

        # Set Aliases
        if self.config.get("alias_template"):
            alias_template = self.config['alias_template']
            await self.opsdroid.send(RoomAddress(target=matrix_room_id,
                                                 address=alias_template.format(name=name),
                                                 connector=self.matrix_connector))

        # Set Room Name
        if self.config.get("name_template"):
            name_template = self.config['name_template']
            await self.opsdroid.send(RoomName(target=matrix_room_id,
                                              name=name_template.format(name=name),
                                              connector=self.matrix_connector))

        # Set Room Image
        url = self.config.get("room_avatar_url")
        if url:
            await self.opsdroid.send(RoomImage(Image(url=url),
                                               target=matrix_room_id,
                                               connector=self.matrix_connector))

        # Set Room Description
        await self.opsdroid.send(RoomDescription(topic, target=matrix_room_id,
                                                 connector=self.matrix_connector))

        # Add to community
        # Enable flairs

        return matrix_room_id

    async def invite_to_matrix_room(self, matrix_room_id, users):
        """
        Invite the listed users to the room.
        """
        for user in users:
            await self.opsdroid.send(UserInvite(target=matrix_room_id,
                                                user=user,
                                                connector=self.matrix_connector))

    async def make_matrix_admin_from_config(self, matrix_room_id):
        """
        Read the configuration file and make people in the 'users_as_admin'
        list admin in the room.
        """
        # Make config people admin
        for user in self.config.get("users_as_admin", []):
            await self.opsdroid.send(UserRole(target=matrix_room_id,
                                              user=user, role='admin',
                                              connector=self.matrix_connector))

    async def matrix_atroom_pl_0(self, matrix_room_id):
        power_levels = await self.matrix_api.get_power_levels(matrix_room_id)

        notifications = power_levels.get('notifications', {})
        notifications['room'] = 0
        power_levels['notifications'] = notifications

        return await self.opsdroid.send(MatrixPowerLevels(power_levels,
                                                          target=matrix_room_id,
                                                          connector=self.matrix_connector))
