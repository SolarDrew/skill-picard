import logging

from opsdroid.matchers import match_regex
from opsdroid.events import *
from opsdroid.skill import Skill


_LOGGER = logging.getLogger(__name__)


class Picard(Skill):

    @match_regex("!createroom (?P<name>.+?) (?P<topic>.+?) (?P<desc>.+?)")
    async def create_new_matrix_channel(self, message):
        name, topic, desc = message.regex['name'], message.regex['topic'], message.regex['desc']
        # Enable flair
        await message.respond('Riker to the Bridge')

        # Create Room
        room_id = await self.opsdroid.send(NewRoom())

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
        if self.config.get("community_avatar"):
            url = self.config["community_avatar"]
            await self.opsdroid.send(RoomImage(Image(url=url), target=room_id))

        # Set Room Description
        await self.opsdroid.send(RoomDescription(desc, target=room_id))

        # Invite Users
        # Invite Command User
        await self.opsdroid.send(UserInvite(target=room_id,
                                            user=message.raw_event['sender']))
        # Invite users in the config
        if self.config.get("users_to_invite", None):
            for user in config["users_to_invite"]:
                await self.opsdroid.send(UserInvite(target=room_id,
                                                    user=user))

        # Add to community
