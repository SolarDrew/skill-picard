# skill-matrixslack

[Opsdroid](https://github.com/opsdroid/opsdroid) skill to handle events passed to Matrix by Slack through a [bridge](https://github.com/matrix-org/matrix-appservice-slack).

# Requirements

None

# Configuration

```
- name: matrixslack
  repo: https://github.com/SolarDrew/skill-matrixslack.git
  slack_bot_token: #  Bot User OAuth Access Token"
  slack_user_token: #  OAuth Access Token 
  bridge_bot_name: oabot
  room_prefix: # Matrix room name prefix (probably the name of your slack team)
  server_name: # Remote part of your matrix ID
  as_userid: # The user ID of the slack AS bot user.
```
