"""
This file handles all the community interaction stuff with matrix.

It is implemented here and not in the connector because it isn't part of the
matrix spec yet and liable to change.
"""
from functools import wraps

import parse


def if_community_configured(f):
    """
    Call the decorated method only if the communtiy_id key is in the picard
    configuration.
    """
    @wraps(f)
    async def wrapper(self, *args, **kwargs):
        if self.config.get("communtiy_id", "").startswith("+"):
            if not self._communtiy_exists():
                await self.create_community(community_id)
            return await f(self, *args, **kwargs)
        return
    return wrapper


class MatrixCommunityMixin:

    # API methods

    async def create_community(self, community_id):
        """
        Create the configured community.
        """
        localpart = parse.parse("+{localpart}:{server_name}")
        localpart = localpart['localpart']
        body = {
            "localpart": localpart
        }
        return self.matrix_api._send("POST", "/create_group", body)

    async def _add_room_to_community(self, matrix_room_id, community_id):
        """
        Add a room to a community.
        """
        return await self.matrix_api._send(
            "PUT",
            f"/groups/{quote(community_id)}/admin/rooms/{quote(matrix_room_id)}")

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
            "/groups/{quote(community_id}/users")
        print(response)
        return response

    async def _get_community_profile(self, community_id):
        return await self.matrix_api._send("GET", f"/groups/{quote(group_id)}/profile")

    # Picard methods

    async def _community_exists(self, community_id):
        """
        Looks up a community to see if it exists. Also caches all the lookups.
        """
        if not hasattr(self, "_community_cache"):
            self._community_cache = []

        if communtiy_id in self._community_cache:
            return True

        try:
            await self._get_community_profile(community_id)
        except MatrixRequestError:
            return False

        self._community_cache.append(communtiy_id)
        return True

    @if_community_configured
    async def add_room_to_community(self, matrix_room_id):
        """
        Add the room to the configured community.
        """
        print("Adding room to communtiy")
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
