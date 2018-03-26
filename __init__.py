import logging

from opsdroid.matchers import match_regex
from opsdroid.matchers import match_crontab
import slacker
from slacker import Slacker

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

    # Get channel list
    response = slack.channels.list()
    channels = response.body['channels']

    seen_channels = await opsdroid.memory.get("seen_channels")
    seen_channels = seen_channels if seen_channels else []
    for channel in channels:
        if channel['id'] not in seen_channels:
            join_bot_to_channel(slack, bridge_bot_id, channel['id'])
            seen_channels.append(channel['id'])
            await message.respond(f"Adding {channel['name']}")
    await opsdroid.memory.put("seen_channels", seen_channels)
