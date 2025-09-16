# Maubot Alertbot

This is a plugin for [maubot](https://mau.bot/) that receives alerts from
[Prometheus Alertmanager](https://prometheus.io/docs/alerting/latest/alertmanager/) and sends them to a Matrix room.

## Features

- Receiving alerts from Prometheus Alertmanager by webhook
- Message sending for each alert in an alert group to a Matrix room
- Message editing for alerts when they have been resolved or acknowledged
- Alert acknowledgement by reacting with 👍
- Manual alert resolution by reacting with ✅

### Possible future features

- [ ] Alert grouping: send only one message per alert group, 
      list the alerts in the message, ideally with their unique labels only
- [ ] Message pinning: pin messages for alerts that are firing so you don't
      overlook unresolved alerts that are old
- [ ] Message preview: currently only an HTML message is sent which clients don't render in
      notifications and room lists
- [ ] Message templating: currently the contents of alert messages are hardcoded, they should be made configurable
- [ ] Authentication: currently there is no authentication for the webhook that receives the alerts.
      The URL includes the room ID so you're already quite safe as long as you don't publicly list the room
- [ ] Heartbeat / Canary: an endpoint which is expected to repeatedly get a firing alert
      and send a message when it does not

## Installation

1. Download the .mbp file from releases
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

## Development

Clone the project, create a venv and install dependencies, log in to your maubot instance.

```bash
python -m venv ./.venv
source .venv/bin/activate
pip install -r requirements.txt
mbc login --server https://maubot.example.org/
```

To build and upload run

```bash
mbc build --upload
```

You can also build without the `--upload` option and upload the created `.mbp` file manually
through the maubot webinterface.

> IMPORTANT: maubot versions <0.5.2 don't update the webhook receivers on plugin updates.

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
