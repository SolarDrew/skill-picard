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


# Installation



### Configure the Application Service
To use this you need to setup the 
[slack appservice](https://github.com/matrix-org/matrix-appservice-slack) on the
bot API branch
[here](https://github.com/matrix-org/matrix-appservice-slack/pull/66).


### Configure a Bot User

To do this you need to setup a slack bot by following these steps lovingly
borrowed from the
[README](https://github.com/perissology/matrix-appservice-slack/blob/master/README.md#recommended)
of the slack appservice:

1. Add a custom app to your slack team/workspace by visiting https://api.slack.com/apps
   and clicking on `Create New App`.
   
2. Name the app & select the team/workspace this app will belong to.

3. Click on `bot users` and add a new bot user. We will use this account to bridge the
   the rooms.
   
4. Click on `Event Subscriptions` and enable them. At this point, the bridge needs to be
   started as slack will do some verification of the request rul. The request url should be
   `https://$HOST:$SLACK_PORT"`. Then add the following events and save:
   
   Bot User Events:
     
       - team_domain_change
       - message.channels
       - message.groups (if you want to bridge private channels)
       
5. Skip this step if you do not want to bridge files.
   Click on `OAuth & Permissions` and add the following scopes:

   - files:read
   - files:write:user
   - channels:write
   - channels:history
   - chat:write:bot 
   - chat:write:user
   
   Note: any media uploaded to matrix is currently accessible by anyone who knows the url.
   In order to make slack files visible to matrix users, this bridge will make slack files
   visible to anyone with the url (including files in private channels). This is different
   then the current behavior in slack, which only allows authenticated access to media
   posted in private channels.
 
6. Click on `Install App` and `Install App to Workspace`. Note the access tokens show.
   You will need the `Bot User OAuth Access Token` and if you want to bridge files, the
   `OAuth Access Token` whenever you link a room.
   
   
### Configure Picard Bot

This bot uses the client-server API so can be configured on any machine. It uses
[opsdroid](http://opsdroid.readthedocs.io/), which can be installed via pip:

    pip install opsdroid

or run from docker:

    # Pull the container image
    docker pull opsdroid/opsdroid:latest

    # Run the container
    docker run --rm -it -v /path/to/configuration.yaml:/etc/opsdroid/configuration.yaml:ro opsdroid/opsdroid:latest
    

the configuration file must contain the following two sections, to configure both the matrix connector and the picard bt:


#### Configuring the matrix connector

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


#### Configuring the picard bot

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
  invite_communtiy_to_rooms: false # Invite all members of the communtiy to new rooms
  room_avatar_url: null # http or mxc url for the room avatar
```


## Why is this called Picard?

He commands the bridge!
