import logging
from urllib.parse import quote

import aiohttp
import slacker

from matrix_client.errors import MatrixRequestError

_LOGGER = logging.getLogger(__name__)


__all__ = ['upload_image_to_matrix', 'set_room_avatar', 'user_in_state',
           'update_related_groups', 'set_related_groups', 'get_related_groups',
           'configure_room_power_levels', 'room_notifications_pl0', 'user_is_room_admin',
           'get_power_levels', 'set_power_levels', 'make_community_joinable',
           'admin_of_community', 'intent_user_in_room', 'intent_self_in_room',
           'is_in_matrix_room', 'joined_rooms', 'room_id_if_exists',
           'get_matrix_connector', 'get_new_channels', 'get_channel_mapping',
           'join_bot_to_channel', 'get_room_members']


def get_room_members(slack, channel_id):
    """
    Get a list of members in a given room
    """
    resp = slack.channels.get("conversations.members", params={'channel': channel_id})
    return resp.body['members']


def join_bot_to_channel(bot_slack, config, bot_id, channel_id):
    """
    Invite the bot to the channel if the bot is not already in the channel.
    """
    u_token = config['slack_user_token']
    slack = slacker.Slacker(u_token)
    members = get_room_members(bot_slack, channel_id)
    if bot_id not in members:
        # Do an extra guard here just in case
        try:
            slack.channels.invite(channel_id, bot_id)
        except slacker.Error:
            _LOGGER.exception("Invite failed")


def get_channel_mapping(slack, channels=None):
    """
    Map slack channel ids to their names
    """
    if not channels:
        response = slack.channels.list()
        channels = response.body['channels']

    return {c['id']: c['name'] for c in channels}


def get_new_channels(slack, config, seen_channels):
    """
    Get channels in the workspace that are not in seen_channels
    """
    # Get channel list
    response = slack.channels.list()
    channels = response.body['channels']

    channel_map = get_channel_mapping(slack, channels=channels)

    # Get the new channels we need to process
    new_channels = {}
    for channel in channels:
        if channel['is_archived']:
            continue
        if channel['id'] not in seen_channels.keys():
            prefix = config['room_alias_prefix']
            channel_name = channel_map[channel['id']]
            server_name = config['server_name']
            alias = f"#{prefix}{channel_name}:{server_name}"
            topic = channel['topic']['value']
            new_channels[channel['id']] = (channel_name, alias, topic)

    return new_channels


def get_matrix_connector(opsdroid):
    """
    Return the first configured matrix connector.
    """
    for conn in opsdroid.connectors:
        if conn.name == "matrix":
            return conn


async def room_id_if_exists(api, room_alias):
    """
    Returns the room id if the room exists or `None` if it doesn't.
    """
    if room_alias.startswith('!'):
        return room_alias
    try:
        room_id = await api.get_room_id(room_alias)
        return room_id
    except MatrixRequestError as e:
        if e.code != 404:
            raise e
        return None


async def joined_rooms(api):
    respjson = await api._send("GET", "/joined_rooms")
    return respjson['joined_rooms']


async def is_in_matrix_room(api, room_id):
    rooms = await joined_rooms(api)
    return room_id in rooms


async def intent_self_in_room(opsdroid, room):
    """
    This function should result in the connector user being in the given room.
    Irrespective of if that room existed before.
    """

    connector = get_matrix_connector(opsdroid)

    room_id = await room_id_if_exists(connector.connection, room)

    if room_id is None:
        try:
            respjson = await connector.connection.create_room(alias=room.split(':')[0][1:])
            room_id = respjson['room_id']
        except MatrixRequestError:
            room_id = await connector.connection.get_room_id(room)
        respjson = await connector.connection.join_room(room_id)
    else:
        is_in_room = await is_in_matrix_room(connector.connection, room_id)

        if not is_in_room:
            respjson = await connector.connection.join_room(room_id)

    return room_id


async def intent_user_in_room(opsdroid, user, room):
    """
    Ensure a user is in a room.

    If the room doesn't exist or the invite fails, then return None
    """
    connector = get_matrix_connector(opsdroid)
    room_id = await room_id_if_exists(connector.connection, room)

    if room_id is not None:
        try:
            await connector.connection.invite_user(room_id, user)
        except MatrixRequestError as e:
            if "already in the room" in e.content:
                return room_id
            room_id = None

    return room_id


async def admin_of_community(opsdroid, community):
    """
    Ensure the community exists, and the user is admin otherwise return None.
    """

    connector = get_matrix_connector(opsdroid)

    # Check the Python SDK speaks communities
    if not hasattr(connector.connection, "create_group"):
        return None

    # Check community exists
    try:
        profile = await connector.connection.get_group_profile(community)
    except MatrixRequestError as e:
        if e.code != 404:
            raise e
        else:
            group = await connector.connection.create_group(community.split(':')[0][1:])
            return group['group_id']

    # Ensure we are admin
    if profile:
        users = await connector.connection.get_users_in_group(community)
        myself = list(filter(lambda key: key['user_id'] == connector.mxid, users['chunk']))
        if not myself[0]['is_privileged']:
            return None

    return community


async def make_community_joinable(opsdroid, community):
    connector = get_matrix_connector(opsdroid)

    content = {"m.join_policy": {"type": "open"}}
    await connector.connection._send("PUT", f"groups/{community}/settings/m.join_policy",
                                     content=content)



"""
Break up all the power level modifications so we only inject one state event
into the room.
"""


async def set_power_levels(opsdroid, room_alias, power_levels):
    connector = get_matrix_connector(opsdroid)
    room_id = await room_id_if_exists(connector.connection, room_alias)
    return await connector.connection.set_power_levels(room_id, power_levels)


async def get_power_levels(opsdroid, room_alias):
    connector = get_matrix_connector(opsdroid)
    room_id = await room_id_if_exists(connector.connection, room_alias)

    return await connector.connection.get_power_levels(room_id)


async def user_is_room_admin(power_levels, room_alias, mxid):
    """
    Modify power_levels so user is admin
    """
    user_pl = power_levels['users'].get(mxid, None)

    # If already admin, skip
    if user_pl != 100:
        power_levels['users'][mxid] = 100

    return power_levels


async def room_notifications_pl0(power_levels, room_alias):
    """
    Set the power levels for @room notifications to 0
    """

    notifications = power_levels.get('notifications', {})
    notifications['room'] = 0

    power_levels['notifications'] = notifications

    return power_levels


async def configure_room_power_levels(opsdroid, config, room_alias):
    """
    Do all the power level related stuff.
    """
    connector = get_matrix_connector(opsdroid)
    room_id = await room_id_if_exists(connector.connection, room_alias)

    # Get the users to be made admin in the matrix room
    users_as_admin = config.get("users_as_admin", [])

    power_levels = await get_power_levels(opsdroid, room_id)

    # Add admin users
    for user in users_as_admin:
        await intent_user_in_room(opsdroid, user, room_id)
        power_levels = await user_is_room_admin(power_levels, room_id, user)

    room_pl_0 = config.get("room_pl_0", False)
    if room_pl_0:
        power_levels = await room_notifications_pl0(power_levels, room_id)

    # Only actually modify room state if we need to
    if users_as_admin or room_pl_0:
        await set_power_levels(opsdroid, room_id, power_levels)


async def get_related_groups(opsdroid, roomid):
    """
    Get the m.room.related_groups state from a room
    """
    connector = get_matrix_connector(opsdroid)
    api = connector.connection

    try:
        json = await api._send("GET", f"/rooms/{roomid}/state/m.room.related_groups")
        return json['groups']
    except MatrixRequestError as e:
        if e.code != 404:
            raise e
        else:
            return []


async def set_related_groups(opsdroid, roomid, communities):
    """
    Set the m.room.related_groups state from a room
    """
    connector = get_matrix_connector(opsdroid)
    api = connector.connection

    content = {'groups': communities}

    return await api.send_state_event(roomid,
                                      "m.room.related_groups",
                                      content)


async def update_related_groups(opsdroid, roomid, communities):
    """
    Add communities to the existing m.room.related_groups state event.
    """

    existing_communities = await get_related_groups(opsdroid, roomid)

    existing_communities += communities

    new_groups = list(set(existing_communities))

    return await set_related_groups(opsdroid, roomid, new_groups)


async def user_in_state(opsdroid, roomid, mxid):
    """
    Check to see if the user exists in the state.
    """
    connector = get_matrix_connector(opsdroid)
    api = connector.connection

    state = await api.get_room_state(roomid)

    keys = [s.get("state_key", "") for s in state]

    return mxid in keys


"""
Helpers for room avatar
"""


async def upload_image_to_matrix(self, image_url):
    """
    Given a URL upload the image to the homeserver for the given user.
    """
    async with aiohttp.ClientSession() as session:
        async with session.request("GET", image_url) as resp:
            data = await resp.read()

    respjson = await self.api.media_upload(data, resp.content_type)

    return respjson['content_uri']


async def set_room_avatar(opsdroid, room_id, avatar_url):
    """
    Set a room avatar.
    """
    connector = get_matrix_connector(opsdroid)

    if not avatar_url.startswith("mxc"):
        avatar_url = await upload_image_to_matrix(avatar_url)

    # Set state event
    content = {
        "url": avatar_url
    }

    return await connector.connection.send_state_event(room_id,
                                                       "m.room.avatar",
                                                       content)
