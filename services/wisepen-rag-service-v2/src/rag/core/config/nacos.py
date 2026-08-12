from common.cloud.nacos_client import NacosClientManager

from rag.core.config.bootstrap_settings import RagBootstrapSettings


def build_nacos_client_manager(
    bootstrap_settings: RagBootstrapSettings,
) -> NacosClientManager:
    return NacosClientManager(bootstrap_settings)
