import logging

from opsdroid.matchers import match_regex
from opsdroid.matchers import match_crontab
import slacker
from slacker import Slacker

from matrix_client.errors import MatrixRequestError

_LOGGER = logging.getLogger(__name__)


def get_room_members(slack, channel_id):
    """
    Get a list of members in a given room
    """
    resp = slack.channels.get("conversations.members", params={'channel': channel_id})
    return resp.body['members']


def join_bot_to_channel(slack, bot_id, channel_id):
    """
    Invite the bot to the channel if the bot is not already in the channel.
    """
    members = get_room_members(slack, channel_id)
    if bot_id not in members:
        # Do an extra guard here just in case
        try:
            slack.channels.invite(channel_id, bot_id)
        except slacker.Error:
            _LOGGER.exception("Invite failed")


def get_channel_mapping(slack):

    response = slack.channels.list()
    channels = response.body['channels']

    return {c['id']: c['name'] for c in channels}


def get_new_channels(slack, seen_channels):
    """
    Get channels in the workspace that are not in seen_channels
    """
    # Get channel list
    response = slack.channels.list()
    channels = response.body['channels']

    # Get the new channels we need to process
    new_channels = []
    for channel in channels:
        if channel['id'] not in seen_channels:
            new_channels.append(channel['id'])

    return new_channels


def get_matrix_connector(opsdroid):
    """
    Return the first configured matrix connector.
    """
    for conn in opsdroid.connectors:
        if conn.name == "ConnectorMatrix":
            return conn


async def room_id_if_exists(api, room_alias):
    """
    Returns the room id if the room exists or `None` if it doesn't.
    """
    try:
        room_id = await api.get_room_id(room_alias)
        return room_id['room_id']
    except MatrixRequestError as e:
        if e.code != 404:
            raise e
        return None


async def joined_rooms(api):
    json = await api._send("GET", "/joined_rooms")
    return json['joined_rooms']


async def is_in_matrix_room(api, room_id):
    rooms = await joined_rooms(api)
    return room_id in rooms


async def intent_self_in_room(opsdroid, room):
    """
    This function should result in the connector user being in the given room.
    Irrespective of if that room existed before.
    """

    connector = get_matrix_connector(opsdroid)

    room_id = room_id_if_exists(connector.api, room)

    if room_id is None:
        json = await connector.api.create_room(alias=room)
        room_id = json['room_id']
        json = await connector.api.join_room(room_id)
    else:
        is_in_room = is_in_matrix_room(connector.api, room_id)

        if not is_in_room:
            json = await connector.api.join_room(room_id)

    return room_id


async def intent_user_in_room(opsdroid, user, room):
    """
    Ensure a user is in a room.
    """
    await opsdroid.connector.api.invite_user(room_id, config['as_userid'])

# @match_crontab('* * * * *')
@match_regex('slack')
async def mirror_slack_channels(opsdroid, config, message):
    """
    Check what channels exist in the Slack workspace and list them.
    """

    token = config['slack_token']
    slack = Slacker(token)

    # Get userid for bot user
    bridge_bot_id = config['bridge_bot_name']
    bridge_bot_id = slack.users.get_user_id(bridge_bot_id)

    # Get the channels we have already processed out of memory
    seen_channels = await opsdroid.memory.get("seen_channels")
    seen_channels = seen_channels if seen_channels else []

    # Get channels that are now in the workspace that we haven't seen before
    new_channels = get_new_channels(slack, seen_channels)

    for channel_id in new_channels:
        # Join the Appservice bot to these new channels
        join_bot_to_channel(slack, bridge_bot_id, channel_id)

        # Create a new matrix room for this channels
        channel_name = get_channel_mapping(slack)[channel_id]
        prefix = config['room_prefix']
        server_name = config['server_name']
        room_alias = f"#{prefix}{channel_name}:{server_name}"
        room_id = await intent_self_in_room(opsdroid, room_alias)

        # Invite the Appservice matrix user to the room
        # TODO: will fail if already in room
        await opsdroid.connector.api.invite_user(room_id, config['as_userid'])

        # Run link command in the appservice admin room

        # Add room to community

    # update the memory with the channels we just processed
    await opsdroid.memory.put("seen_channels", seen_channels + new_channels)

    await message.respond(f"Finished")
