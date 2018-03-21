import logging

from opsdroid.matchers import match_cron
from slacker import Slacker

"""
token = os.environ['SLACK_TOKEN']
slack = Slacker(token)

# Get channel list
response = slack.channels.list()
channels = response.body['channels']
for channel in channels:
    print(channel['id'], channel['name'])
    # if not channel['is_archived']:
    # slack.channels.join(channel['name'])
print()

# Get users list
response = slack.users.list()
users = response.body['members']
for user in users:
    if not user['deleted']:
        print(user['id'], user['name'], user['is_admin'], user[
            'is_owner'])
print()"""

@match_cron('* * * * *')
async def mirror_slack_channels(opsdroid, config, message):
    """
    Check what channels exist in the Slack workspace and list them.
    """

    token = config['slack_token']
    slack = Slacker(token)

    # Get channel list
    response = slack.channels.list()
    channels = response.body['channels']

    await message.respond("Existing slack channels")
    for channel in channels:
        await message.respond(f"{channel['id'], channel['name']}")
