# skill-picard

This opsdroid skill enables the bridging of a slack team to a matrix communtiy. It uses the
[slack appservice](https://github.com/matrix-org/matrix-appservice-slack) to
bridge individual rooms, but it monitors slack for new channels and creates
rooms on matrix for these new channels and then configures the appservice to
bridge them. It also will add these rooms to a matrix communtiy.


**This only works with
[this](https://github.com/matrix-org/matrix-appservice-slack/pull/66) version of
the appservice, as it is assumed you will exceed your slack integration limit
using the webhooks version of the bridge on the released version.**


For the community features to work you will need
[this](https://github.com/matrix-org/matrix-python-sdk/pull/179/) version of the
python SDK for the groups support.


All the rooms created or linked by this bridge will be made public.


# Configuration

This skill has to be used in combination with the 
[matrix connector](https://github.com/opsdroid/connector-matrix). It expects the
matrix connector to be configured with two rooms, one named "main" and one named
"bridge". i.e.

```
connectors:
  - name: matrix
    mxid: "@picard:matrix.federation.org"
    password: ""  # Your password
    homeserver: "https://matrix.federation.org"
    rooms:
      main: "#picard:matrix.federation.org"
      bridge: "!YOhwXiVmjNBNnUdHtX:matrix.federation.org"
```

the "main" room will be used to report the status of the bot, and can be used to
issue commands to the bot. The "bridge" room is the admin room of the 
[slack appservice](https://github.com/matrix-org/matrix-appservice-slack).


Given this configuration of the matrix connector the following are the
configuration options for this skill:


```
- name: picard
  repo: https://github.com/SolarDrew/skill-matrixslack.git
  slack_bot_token: #  Bot User OAuth Access Token
  slack_user_token: #  OAuth Access Token 
  bridge_bot_name: # The username of the bot in your team
  room_alias_prefix: # Matrix room alias prefix i.e. "enterprise_"
  room_name_prefix: # Prefix to add to the room name (defaults to room_alias_prefix)
  server_name: # Remote part of your matrix ID
  as_userid: # The user ID of the slack AS bot user.
  community_id: # The full ID of the communtiy you want rooms added to
  users_as_admin:
      - "@nechayev:matrix.federation.org"
      - "@riker:matrix.federation.org"
  room_pl_0: false # Enable everyone to send @room notifications in matrix. (This enables @channel to work in both slack and matrix)
```


## Why is this called Picard?

He commands the bridge!
