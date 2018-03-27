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

    # Join the Appservice bot to these new channels
    for channel_id in new_channels:
        join_bot_to_channel(slack, bridge_bot_id, channel_id)

    # Create a new matrix room for this channel

    # Invite the Appservice matrix user to the room

    # Run link command in the appservice admin room

    # Add room to community

    # update the memory with the channels we just processed
    await opsdroid.memory.put("seen_channels", seen_channels + new_channels)

    await message.respond(f"Finished")
