# Maubot Alerts

This is a plugin for [maubot](https://mau.bot/) that receives alerts from
[Prometheus Alertmanager](https://prometheus.io/docs/alerting/latest/alertmanager/) and sends them to a Matrix room.

## Features

- Receiving alerts from Prometheus Alertmanager by webhook
- Alert grouping: one message per alert group, listing the individual alerts with their unique labels
- Message editing when the group changes (new alerts, resolved, acknowledged)
- Display of total firing alert count and the notification reason with a timestamp
- Alert acknowledgement by reacting with 👍 (and un-acknowledgement with 👎)
- Manual alert resolution by reacting with ✅
- Configurable message templates (Jinja) via the plugin config
- Message pinning for firing alerts (optional, per room)
- Canary: post a warning when no alert is received within a configured interval (optional, per room)

## Requirements
- Alertmanager >= v0.32.0
- maubot >= v0.6.0

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

- The bot posts **one colored HTML message per alert group**
- Grouping is controlled by `route.group_by` in your Alertmanager config, not the groups
  you define in your prometheus / vmalert config
- The color reflects the group status
  - 🔴 red = firing
  - 🟠 orange = acknowledged
  - 🟢 green = resolved / manually resolved
- The message header shows the group name (linked to the Alertmanager `externalURL`), the
  total firing alert count, and the notification reason with a timestamp. When you use
  `max_alerts` in Alertmanager the total firing alert count might be higher than it actually
  is due to Alertmanager not giving away if the truncated alerts were resolved or firing.
- Below it, firing and resolved alerts are listed individually with a maximum of five,
  each with its name linked to the `generatorURL`, unique labels and summary.
- Follow-up webhooks for the same group **edit the existing message in place** rather than
  posting a new one. Which action the bot takes is driven by the Alertmanager
  `notification_reason` (first notification, new alerts, some/all resolved, repeat interval).
  This requires Alertmanager **v0.32.0 or newer**.
- When the group is fully resolved (requires `send_resolved: true`), the bot edits the
  message to green and reacts with ✅.

### Interacting with alerts (reactions)

React to an alert message to change its state. The acting user's Matrix ID is shown in the
edited message.

| Reaction | Action                                                         |
|----------|----------------------------------------------------------------|
| 👍       | Acknowledge the alert (turns orange, annotated with your user) |
| 👎       | Un-acknowledge an acknowledged alert (back to firing/red)      |
| ✅        | Manually resolve the alert (turns green)                       |

### Custom message templates

Message rendering uses Jinja templates. The packaged defaults live in
`alertbot/templates/` (`alert.jinja`, `alertgroup.jinja`). You can override either one
through the plugin instance config in the maubot webinterface:

```yaml
templates:
  alert: |
    <b>{{ data['labels']['alertname'] }}</b><br/>
    {{ data['annotations'].get('summary', '') }}
  alertgroup: |
    <h4>{{ alertgroup.status | upper }}: {{ alertgroup.group_labels.get("alertname", "Alert") }}</h4>
```

Leave a value `null` (the default) to use the packaged template. Config changes are picked
up without restarting the plugin.

Available context:

- `alert` template: `data` (raw Alertmanager alert), `unique_labels`
- `alertgroup` template: `alertgroup` (fields such as `status`, `group_labels`,
  `common_annotations`, `total_firing_alerts`, `notification_reason`, `updated_at`,
  `firing_alerts`, `resolved_alerts`, `last_actor`, `external_url`)
- `label_color` filter: deterministic pill background/foreground color per label key

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

> **IMPORTANT:** maubot versions <0.5.2 don't update the webhook receivers on plugin updates.

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
