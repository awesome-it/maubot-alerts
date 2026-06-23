# Maubot Alerts

This is a plugin for [maubot](https://mau.bot/) that receives alerts from
[Prometheus Alertmanager](https://prometheus.io/docs/alerting/latest/alertmanager/) and sends them to a Matrix room.

## Features

- Receiving alerts from Prometheus Alertmanager by webhook
- Message sending for each alert in an alert group to a Matrix room
- Message editing for alerts when they have been resolved or acknowledged
- Alert acknowledgement by reacting with 👍 (and un-acknowledgement with 👎)
- Manual alert resolution by reacting with ✅
- Message pinning for firing alerts (optional, per room)
- Canary: post a warning when no alert is received within a configured interval (optional, per room)

### Possible future features

- [ ] Alert grouping: send only one message per alert group, 
      list the alerts in the message, ideally with their unique labels only
- [ ] Message templating: currently the contents of alert messages are hardcoded, they should be made configurable
- [ ] Authentication: currently there is no authentication for the webhook that receives the alerts.
      The URL includes the room ID so you're already quite safe as long as you don't publicly list the room

## Installation

1. Build the mbp-file as described below
2. Go to the webinterface of your maubot instance
3. Click on the plus sign next to "Plugins"
4. Upload the .mbp file
5. Click on the plus sign next to "Instances"
6. Give the instance an ID, select a primary user, for type select "de.awesome-it.maubot-alerts"
7. Click on "Create"
8. Invite the selected primary user to a Matrix room
9. Configure alertmanager to send alerts as webhooks to alertbot:
   ```yaml
   receivers:
     - name: 'maubot_alerts'
       webhook_configs:
         - url: https://<maubot_instance_hostname>/plugin/<instance_id>/prom-alerts/<room_id>
           send_resolved: true
   ```

## Usage

Once the plugin instance is created, the bot's primary user is invited to a room, and
Alertmanager is pointed at the webhook URL (see [Installation](#installation)), the bot
works automatically. The target room is encoded in the webhook URL via `<room_id>`, so you
can send alerts to different rooms by creating multiple `webhook_configs` entries.

> **Note:** There is no authentication on the webhook. Security relies on keeping the room ID
> in the URL secret, so don't publicly list the room.

### Receiving alerts

- When an alert starts **firing**, the bot posts a colored HTML message to the room:
  - 🔴 red = firing
  - 🟠 orange = acknowledged
  - 🟢 green = resolved / manually resolved

  Each message links to the alert's Prometheus `generatorURL` and shows the alert name and
  its description.
- When an alert is **resolved** by Alertmanager (requires `send_resolved: true`), the bot
  edits the original message to green and reacts to it with ✅.
- There is one message per alert (keyed by the Alertmanager `fingerprint`); status changes
  edit the existing message in place rather than posting a new one.

### Interacting with alerts (reactions)

React to an alert message to change its state. The acting user's Matrix ID is shown in the
edited message.

| Reaction | Action                                                         |
|----------|----------------------------------------------------------------|
| 👍       | Acknowledge the alert (turns orange, annotated with your user) |
| 👎       | Un-acknowledge an acknowledged alert (back to firing/red)      |
| ✅        | Manually resolve the alert (turns green)                       |

### Commands

The bot responds to the following commands in the room:

- `!ping` — replies with `pong` (liveness check).
- `!feature <enable|disable> <pinning|canary> [interval]` — enable or disable an optional
  feature for the current room.

#### Pinning

```
!feature enable pinning
!feature disable pinning
```

When enabled, firing alert messages are pinned in the room and unpinned once they are
resolved, so old unresolved alerts stay visible. The bot needs a power level of at least 50
(Moderator) in the room to pin messages; otherwise it will post an error asking you to raise
its power level or disable pinning.

#### Canary (heartbeat / dead man's switch)

```
!feature enable canary           # default interval: 300 seconds (5 minutes)
!feature enable canary 600        # custom interval in seconds
!feature disable canary
```

When enabled, the bot expects to receive at least one alert webhook within the configured
interval. If no alert arrives in time, it posts a prominent **"CANARY IS DEAD"** message so
you know your Alertmanager pipeline may be broken. Configure Alertmanager (or a separate
recurring alert) to repeatedly send a firing alert to keep the canary alive.

## Development

Clone the project, create a venv and install dependencies, log in to your maubot instance.

```bash
python -m venv ./.venv
source .venv/bin/activate
pip install .
mbc login --server https://maubot.example.org/
```


For the plugin binary, it is recommended to download the artifact from the CI/CD pipeline.
Alternatively, you can build and upload locally using:

```bash
mbc build --upload
```

You can also build without the `--upload` option and upload the created `.mbp` file manually
through the maubot webinterface.

> IMPORTANT: maubot versions <0.5.2 don't update the webhook receivers on plugin updates.

### Deploy new version

1. Test new version:
    1. Bump plugin version to [NEW_VERSION] in `pyproject.toml` and `maubot.yaml`
    2. Download artifact from `maubot-plugin-test-mbp`
    3. Upload `*.mbp` file to https://maubot.local.awesome-it.de/#/plugin/de.awesome-it.maubot-alerts-test (You should see the new version in the `Version` field [NEW_VERSION].dev0+[DATE][HASH])
    4. Execute `curl -X POST 'https://maubot.local.awesome-it.de/plugin/awe-alerts-test/prom-alerts/!W5z1xQZXbwl76hkXQUGfF7gz1fokec1osRfQLqwFvAY' --json @./test/10_firing.json`
    5. You should see alerts in the `alert-bot-test` room
2. Release in prod:
    1. Merge your branch into main
    2. Create a new version tag
    3. Download artifact from `maubot-plugin-test-mbp`
    4. Upload `*.mbp` file to https://maubot.local.awesome-it.de/#/plugin/de.awesome-it.maubot-alerts (You should see the new version in the `Version` field [NEW_VERSION])


### Test

After uploading the plugin for the first time, use the maubot webinterface to create a new
instance of the plugin.
Invite your maubot client user into a room where you want to receive test alerts.

In the `test` directory you can find some JSON files which were sent by Prometheus Alertmanager.
You can use `curl` to send test alerts to the plugin endpoint:

```bash
curl 'https://maubot.example.org/plugin/<plugin_instance_id>/prom-alerts/<room_id>' \
--json @./test/<filename>.json
```

### Important Notes

> **Note:** Python module names in maubot (such as 'alertbot') must be unique across all maubot plugins.
