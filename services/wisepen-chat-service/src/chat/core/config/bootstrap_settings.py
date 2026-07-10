from common.core.config.bootstrap_settings import BootstrapSettings


class ChatBootstrapSettings(BootstrapSettings):
    """
    wisepen-chat-service 引导配置
    """

    APP_NAME: str = "WisePen Chat Service"
    SERVICE_NAME: str = "wisepen-chat-service"
    SERVICE_PORT: int = 19904
    MINERU_CLOUD_TOKEN: str = ""


bootstrap_settings = ChatBootstrapSettings()
