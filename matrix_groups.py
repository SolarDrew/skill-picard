"""
This file handles all the community interaction stuff with matrix.

It is implemented here and not in the connector because it isn't part of the
matrix spec yet and liable to change.
"""
import logging
from functools import wraps
from urllib.parse import quote

import parse
from matrix_client.errors import MatrixRequestError

from opsdroid.connector.matrix.events import MatrixStateEvent

_LOGGER = logging.getLogger(__name__)


def if_community_configured(f):
    """
    Call the decorated method only if the communtiy_id key is in the picard
    configuration.
    """
    @wraps(f)
    async def wrapper(self, *args, **kwargs):
        if self.config.get("community_id", "").startswith("+"):
            community_id = self.config['community_id']
            if not await self._community_exists(community_id):
                await self.create_community(community_id)
            return await f(self, *args, **kwargs)
        else:
            _LOGGER.info("No community is configured, skipping community actions.")
        return
    return wrapper


class MatrixCommunityMixin:

    # API methods

    async def create_community(self, community_id):
        """
        Create the configured community.
        """
        localpart = parse.parse("+{localpart}:{server_name}", community_id)
        localpart = localpart['localpart']
        body = {
            "localpart": localpart
        }
        return await self.matrix_api._send("POST", "/create_group", body)

    async def _add_room_to_community(self, matrix_room_id, community_id):
        """
        Add a room to a community.
        """
        try:
            return await self.matrix_api._send(
                "PUT",
                f"/groups/{quote(community_id)}/admin/rooms/{quote(matrix_room_id)}")
        except MatrixRequestError:
            # it seems that Synapse 500's if the room is already in the community.
            _LOGGER.exception("Failed to add room to community.")

    async def _invite_user_to_community(self, matrix_user_id, community_id):
        """
        Invite a user to the community.
        """
        return await self.matrix_api._send(
            "PUT",
            f"/groups/{quote(community_id)}/admin/users/invite/{quote(matrix_user_id)}")

    async def _get_community_members(self, community_id):
        response = await self.matrix_api._send(
            "GET",
            f"/groups/{quote(community_id)}/users")
        print(response)
        return response

    async def _get_community_rooms(self, community_id):
        response = await self.matrix_api._send(
            "GET",
            f"/groups/{quote(community_id)}/rooms")
        rooms = [r['room_id'] for r in response['chunk']]
        return rooms

    async def _get_community_profile(self, community_id):
        return await self.matrix_api._send("GET", f"/groups/{quote(community_id)}/profile")

    async def _make_community_joinable(self, community_id):
        content = {"m.join_policy": {"type": "open"}}
        return await self.matrix_api._send("PUT",
                                           f"groups/{quote(community_id)}/settings/m.join_policy",
                                           content=content)

    # Picard methods

    async def _community_exists(self, community_id):
        """
        Looks up a community to see if it exists. Also caches all the lookups.
        """
        if not hasattr(self, "_community_cache"):
            self._community_cache = []

        if community_id in self._community_cache:
            return True

        try:
            await self._get_community_profile(community_id)
        except MatrixRequestError:
            return False

        self._community_cache.append(community_id)
        return True

    @if_community_configured
    async def get_all_community_rooms(self):
        return await self._get_community_rooms(self.config['community_id'])

    @if_community_configured
    async def add_room_to_community(self, matrix_room_id):
        """
        Add the room to the configured community.
        """
        # TODO: Check if room is already in communtiy before calling this.
        return await self._add_room_to_community(matrix_room_id,
                                                 self.config['community_id'])

    @if_community_configured
    async def invite_all_community_users_to_room(self, matrix_room_id):
        """
        Get the list of users from the community and then invite them all to
        the given room.
        """
        members = await self._get_community_members(self.config['community_id'])
        return await self.invite_to_matrix_room(matrix_room_id, members)

    async def set_related_groups(self, matrix_room_id):
        """
        Set the m.room.related_groups state from a room
        """
        groups = self.config.get("related_groups", [])
        community_id = self.config.get("community_id")
        if community_id:
            groups.append(community_id)

        if not groups:
            return

        for group in groups:
            if not group.startswith("+"):
                _LOGGER.error(f"{group} is not a valid group identifier.")
                groups.remove(group)

        content = {'groups': groups}

        return await self.opsdroid.send(MatrixStateEvent("m.room.related_groups",
                                                         content=content,
                                                         target=matrix_room_id,
                                                         connector=self.matrix_connector))
