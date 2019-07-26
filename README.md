# skill-picard

*The re-write of this skill was to facilitate a specific conference. There are many more things we want to do with this, some of which you can see in [this project](https://github.com/SolarDrew/skill-picard/projects/1)*

This opsdroid skill enables the bridging of a slack team to a matrix community. It uses the
[slack appservice](https://github.com/matrix-org/matrix-appservice-slack) to
bridge individual rooms, but it monitors slack for new channels and creates
rooms on matrix for these new channels and then configures the appservice to
bridge them. It also will add these rooms to a matrix community.

This skill was written to facilitate a bridged chat platform for a conference.

**This only works with version >=0.2.0 of the slack appservice, when configured with the Events API.**

This skill also implements a set of commands for users:

* `!createroom <name> [topic]` - Create a new room and bridge it to the configured slack team. (Works from Matrix and Slack.)
* `!inviteall` - Invite the user to all rooms in the community (matrix only).
* `!autoinvite [disable]` - Invite the user to all future rooms (matrix only).


As well as this it reacts to new rooms on slack, changes of room/channel name
and description on both matrix and slack. Also it will react to archive and
unarchive events on slack and it can be configured to send welcome messages (in
DMs) to new users when they join both the slack team and the matrix community.


As well as the user facing commands there are a set of admin commands:

* `!bridgeall` - Bridge all rooms in the slack channel to matrix (will also be run on skill start by default).
* `!welcomeall` - Send welcome DMs to all users already in the slack team.
* `![un]skip name/description/avatar` - Run in a room, and will not bridge the room name, topic and avatar when the room is bridged (normally with `!bridgeall`).


# Installation


### Configure the Application Service
To use this you need to setup the 
[slack appservice](https://github.com/matrix-org/matrix-appservice-slack).


### Configure a Bot User

This should be the same bot user as for the appservice.

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
   started as slack will do some verification of the request url. The request url should be
   `https://$HOST:$SLACK_PORT"`. Then add the following events and save:
   
   Bot User Events:
     
       - team_domain_change
       - message.channels
       - message.groups (if you want to bridge private channels)
       - reactions.added
       - reactions.removed
       
5. Click on `OAuth & Permissions` and add the following scopes:

   - files:read
   - files:write:user
   - channels:write
   - channels:history
   - chat:write:bot 
   - chat:write:user
   - team:read
   
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
[opsdroid](http://opsdroid.readthedocs.io/). 

**Currently Picard requires [this](https://github.com/opsdroid/opsdroid/pull/951) branch of opsdroid.**


Which can be installed via pip:

    pip install git+https://github.com/SolarDrew/opsdroid.git@events

or run from docker (you will need to build your own docker image until the #951 is released):

    # Pull the container image
    docker pull opsdroid/opsdroid:latest

    # Run the container
    docker run --rm -it -v /path/to/configuration.yaml:/etc/opsdroid/configuration.yaml:ro opsdroid/opsdroid:latest
    

the configuration file must contain the following three sections, to configure both the matrix and slack connectors, the picard skill and the matrix database:


#### Configuring the Connectors

This skill has to be used in combination with both the matrix and slack
connectors, they **must** be named `'matrix'` and `'slack'`. It expects the
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

  - name: slack
    api-token: "xoxb-xxxxxxxxxxxxxx-xxxxxxxxxxxxxxxxxxxxx"
    bot-name: "Picard"
```

the "main" room will be used to report the status of the bot, and can be used to
issue commands to the bot. The "bridge" room is the admin room of the 
[slack appservice](https://github.com/matrix-org/matrix-appservice-slack).


#### Configuring the Picard Skill

Given this configuration of the matrix connector the following are the
configuration options for this skill:


```
skills:
  - name: picard
    repo: https://github.com/solardrew/skill-picard.git
    no-cache: true
    slack_bot_token: "xoxb-xxxxxxxxxxx-xxxxxxxxxx" #  Bot User OAuth Access Token
    slack_user_token: "xoxp-xxxxxxxxxx-xxxxxxxx-xxxxxxxx-xxxxxxx" #  OAuth Access Token
    appservice_bot_mxid: "@slackbot:federation.org"
    slack_bot_name: "Picard"
    room_alias_templates: 
      - "#_enterprise_{name}:federation.org"
    room_name_template: "Enterprise {name}"
    announcement_room_name: "general"
    room_avatar_url: "mxc://federation.org/BlgDmTEkHUvXPGHpIpjPxVUt"
    users_as_admin:
      - "@nechayev:federation.org"
      - "@riker:federation.org"
    users_to_invite:
      - "@_neb_github:matrix.org"
    make_public: false  # Make the rooms and the community publically joinable and set history to viewable by Anyone
    allow_at_room: true # Enable everyone to send @room notifications in matrix. (This enables @channel to work in both slack and matrix)
    copy_from_slack_startup: false # Run the !bridgeall command when opsdroid starts (ensures that all rooms exist if the bot has been offline)

    community_id: "+enterprise:federation.org"  # The full ID of the communtiy you want rooms added to, if not specified no communtiy interations will happen.
    related_groups: # A list of groups to be set as "related groupsi" in all rooms, for displaying flair.
      - "+stargazer:federation.org"

    welcome:
      matrix: |
        I'm the Picard bot.

      slack: >
        I'm the Picard bot.
```

#### Configure the Opsdroid Matrix Database

For this skill to work as intended you need to configure the [`database-matrix`](https://github.com/SolarDrew/database-matrix/) opsdroid memory provider. This database provider uses matrix room state to back the opsdroid memory. This means that room preferences as well as seen community users and known DMs are all stored in room state (in both the `'main'` room and in the specific room in the case of room preferences).

```
databases:
  - name: matrix
    repo: https://github.com/SolarDrew/database-matrix
    branch: events
```


## Why is this called Picard?

He commands the bridge!
