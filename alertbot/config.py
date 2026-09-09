from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper


class AlertBotConfig(BaseProxyConfig):
    def do_update(self, helper: ConfigUpdateHelper) -> None:
        helper.copy_dict("templates")
