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


def get_new_channels(slack, config, seen_channels):
    """
    Get channels in the workspace that are not in seen_channels
    """
    # Get channel list
    response = slack.channels.list()
    channels = response.body['channels']

    # Get the new channels we need to process
    new_channels = {}
    token = config['slack_bot_token']
    slack = Slacker(token)
    for channel in channels:
        if channel['id'] not in seen_channels.keys():
            prefix = config['room_prefix']
            channel_name = get_channel_mapping(slack)[channel['id']]
            server_name = config['server_name']
            alias = f"#{prefix}-{channel_name}:{server_name}"
            new_channels[channel['id']] = alias

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

    room_id = await room_id_if_exists(connector.connection, room)

    if room_id is None:
        logging.debug(room)
        try:
            json = await connector.connection.create_room(alias=room.split(':')[0][1:])
            room_id = json['room_id']
        except MatrixRequestError:
            room_id = await connector.connection.get_room_id(room)
        json = await connector.connection.join_room(room_id)
    else:
        is_in_room = is_in_matrix_room(connector.connection, room_id)

        if not is_in_room:
            json = await connector.connection.join_room(room_id)

    return room_id


async def intent_user_in_room(opsdroid, user, room):
    """
    Ensure a user is in a room.

    If the room doesn't exist or the invite fails, then return None
    """
    connector = get_matrix_connector(opsdroid)
    room_id = await room_id_if_exists(connector.connection, room)
    logging.debug(f"1: {room_id}")

    if room_id is not None:
        try:
            await connector.connection.invite_user(room_id, user)
        except MatrixRequestError as e:
            logging.debug(f"---- {e}")
            if "already in the room" in str(e):
                return room_id
            room_id = None
            # raise

    return room_id


#  @match_crontab('* * * * *')
@match_regex('slack')
async def mirror_slack_channels(opsdroid, config, message):
    """
    Check what channels exist in the Slack workspace and list them.
    """

    conn = get_matrix_connector(opsdroid)

    token = config['slack_bot_token']
    u_token = config['slack_user_token']
    slack = Slacker(token)

    # Get userid for bot user
    bridge_bot_id = config['bridge_bot_name']
    bridge_bot_id = slack.users.get_user_id(bridge_bot_id)

    # Get the channels we have already processed out of memory
    seen_channels = await opsdroid.memory.get("seen_channels")
    seen_channels = seen_channels if seen_channels else {}

    # Get channels that are now in the workspace that we haven't seen before
    new_channels = get_new_channels(slack, config, seen_channels)

    for channel_id, room_alias in new_channels.items():
        # Join the Appservice bot to these new channels
        join_bot_to_channel(slack, bridge_bot_id, channel_id)

        # Create a new matrix room for this channels
        room_id = await intent_self_in_room(opsdroid, room_alias)
        # Make room publicly joinable
        logging.debug(room_alias)
        await conn.connection.send_state_event(room_id,
                                               'm.room.join_rules',
                                               content={'join_rule': 'public'})

        # Invite the Appservice matrix user to the room
        room_id = await intent_user_in_room(opsdroid, config['as_userid'], room_id)
        logging.debug(f"2: {room_id}")
        if room_id is None:
            # If the room dosen't exist. Panic.
            return

        # Run link command in the appservice admin room
        await message.respond(f"link --channel_id {channel_id} --room {room_id} --slack_bot_token {token} --slack_user_token {u_token}", room='bridge')
        # Add room to community
        community = '+botdev:testmatrix.home.cadair.com'
        response = await conn.connection.get_rooms_in_group(community)
        ids = [r['room_id'] for r in response['chunk']]
        logging.debug(ids)
        if room_id not in ids:
            await conn.connection.add_room_to_group(community, room_id)
        # Change the room name to something sane
        await conn.connection.set_room_name(room_id, room_alias.split(':')[0][1:])

    # update the memory with the channels we just processed
    logging.debug(f"+++++++\n{seen_channels}\n{new_channels}+++++++")
    seen_channels.update(new_channels)
    await opsdroid.memory.put("seen_channels", seen_channels)

    await message.respond(f"Finished")
