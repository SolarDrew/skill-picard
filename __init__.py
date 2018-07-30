from opsdroid.matchers import match_regex
from opsdroid.matchers import match_crontab
from opsdroid.message import Message

from .picard import *

import logging

import slacker


_LOGGER = logging.getLogger(__name__)


@match_crontab('* * * * *')
@match_regex('!updatechannels')
async def mirror_slack_channels(opsdroid, config, message):
    """
    Check what channels exist in the Slack workspace and list them.
    """
    _LOGGER.info("Captain Picard to the bridge.")

    conn = get_matrix_connector(opsdroid)

    if not message:
        message = Message("",
                          None,
                          config.get("room", conn.default_room),
                          conn)

    token = config['slack_bot_token']
    u_token = config['slack_user_token']
    slack = slacker.Slacker(token)

    # Make public
    make_public = config.get("make_public", True)

    # Get userid for bot user
    bridge_bot_id = config['bridge_bot_name']
    bridge_bot_id = slack.users.get_user_id(bridge_bot_id)

    # Get the channels we have already processed out of memory
    seen_channels = await opsdroid.memory.get("seen_channels")
    seen_channels = seen_channels if seen_channels else {}

    # Get channels that are now in the workspace that we haven't seen before
    new_channels = get_new_channels(slack, config, seen_channels)

    # Ensure that the community exists and we are admin
    # Will return None if we don't have the groups API PR
    community = await admin_of_community(opsdroid, config["community_id"])

    # Get the room name prefix
    room_name_prefix = config.get("room_name_prefix", config["room_alias_prefix"])

    related_groups = config.get("related_groups", [])

    # Get a list of rooms currently in the community
    if community:
        response = await conn.connection.get_rooms_in_group(community)
        rooms_in_community = {r['room_id'] for r in response['chunk']}

    for channel_id, (channel_name, room_alias, topic) in new_channels.items():
        # Apparently this isn't needed
        # Join the slack bot to these new channels
        join_bot_to_channel(slack, config, bridge_bot_id, channel_id)

        # Create a new matrix room for this channels
        room_id = await intent_self_in_room(opsdroid, room_alias)

        # Change the room name to something sane
        room_name = f"{room_name_prefix}{channel_name}"
        await conn.connection.set_room_name(room_id, room_name)
        if topic:
            await conn.connection.set_room_topic(room_id, topic)

        avatar_url = config.get("room_avatar_url", None)
        if avatar_url:
            await set_room_avatar(opsdroid, room_id, avatar_url)

        if make_public:
            # Make room publicly joinable
            try:
                await conn.connection.send_state_event(room_id,
                                                       "m.room.join_rules",
                                                       content={'join_rule': "public"})
                await conn.connection.send_state_event(room_id,
                                                       "m.room.history_visibility",
                                                       content={'history_visibility': "world_readable"})
            except Exception:
                logging.exception("Could not make room publicly joinable")
                await message.respond(f"ERROR: Could not make {room_alias} publically joinable.")

        # Invite the Appservice matrix user to the room
        room_id = await intent_user_in_room(opsdroid, config['as_userid'], room_id)
        if room_id is None:
            await message.respond("ERROR: Could not invite appservice bot"
                                  f"to {room_alias}, skipping channel.")
            continue

        # Make all the changes to room power levels, for both @room and admins
        await configure_room_power_levels(opsdroid, config, room_id)

        # Update related groups
        if related_groups:
            await update_related_groups(opsdroid, room_id, related_groups)

        # Run link command in the appservice admin room
        await message.respond(
            f"link --channel_id {channel_id} --room {room_id}"
            f" --slack_bot_token {token} --slack_user_token {u_token}",
            room='bridge')

        # Invite Users
        if config.get("users_to_invite", None):
            for user in config["users_to_invite"]:
                await intent_user_in_room(opsdroid, user, room_id)

        # Add room to community
        if community and room_id not in rooms_in_community:
            try:
                await conn.connection.add_room_to_group(community, room_id)
            except Exception:
                _LOGGER.exception(f"Failed to add {room_alias} to {community}.")

        if community:
            all_users = await conn.connection.get_users_in_group(community)
            if config.get('invite_communtiy_to_rooms', False):
                for user in all_users['chunk']:
                    # await conn.connection.invite_user(room_id, user['user_id'])
                    in_room = await user_in_state(opsdroid, room_id, user['user_id'])
                    if not in_room:
                        await intent_user_in_room(opsdroid, user['user_id'], room_id)

        await message.respond(f"Finished Adding room {room_alias}")

    if new_channels:
        # update the memory with the channels we just processed
        seen_channels.update(new_channels)
        await opsdroid.memory.put("seen_channels", seen_channels)

        await message.respond(f"Finished adding all rooms.")
