import importlib
import pkgutil
from typing import Dict, Optional, Tuple, Type

from config import cfg
from providers.base import BaseProvider
from providers.fallback import FallbackProvider
from providers.openai_compatible import OpenAICompatibleProvider
from utils.logger import get_logger

logger = get_logger("provider.registry")

# 平台名称 -> (Provider 类, 默认 base_url)
_PROVIDER_REGISTRY: Dict[str, Tuple[Type[BaseProvider], str]] = {}


def _get_provider_class_and_url(platform: str):
    """根据平台名称返回 (Provider 类, 默认 base_url)。"""
    p = (platform or "").lower().strip()
    if p in _PROVIDER_REGISTRY:
        return _PROVIDER_REGISTRY[p]
    # 未知平台回退到通用 OpenAI 兼容
    return OpenAICompatibleProvider, ""


class ProviderRegistry:
    """
    Provider 注册中心（单例）。
    负责管理所有模型 Provider 的生命周期与路由，支持从 config 自动构建默认 Provider。
    框架内部自动初始化，用户无需感知其存在。
    """

    _instance = None
    _discovered = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            if not cls._discovered:
                cls._discover_providers()
                cls._discovered = True
            cls._instance._providers: Dict[str, BaseProvider] = {}
            cls._instance._build_defaults()
        return cls._instance

    @classmethod
    def _discover_providers(cls):
        """自动扫描 providers 包下的所有模块，读取 PLATFORM_NAME 完成注册。"""
        import importlib
        import inspect
        import pkgutil
        import providers

        for _, modname, ispkg in pkgutil.iter_modules(providers.__path__):
            if ispkg or modname in ("registry", "base"):
                continue
            try:
                module = importlib.import_module(f"providers.{modname}")
                for _, obj in inspect.getmembers(module, inspect.isclass):
                    if (
                        inspect.isclass(obj)
                        and issubclass(obj, BaseProvider)
                        and obj is not BaseProvider
                        and hasattr(obj, "PLATFORM_NAME")
                    ):
                        name = getattr(obj, "PLATFORM_NAME")
                        url = getattr(obj, "DEFAULT_BASE_URL", "")
                        _PROVIDER_REGISTRY[name] = (obj, url)
                        logger.debug(
                            f"[ProviderRegistry] 自动注册平台: {name} -> {obj.__name__}"
                        )
            except Exception as e:
                logger.warning(
                    f"[ProviderRegistry] 自动发现模块失败: {modname}: {e}"
                )

    def _create_provider(
        self,
        name: str,
        platform: str,
        api_key: str,
        override_url: Optional[str] = None,
        default_model: Optional[str] = None,
        timeout: float = 60.0,
    ):
        """工厂方法：根据平台名称创建对应 Provider，支持 URL 覆盖。
        注意：只有 platform 为 'custom' 时才使用 override_url，
        否则强制使用内置 URL，避免旧配置中的 URL 干扰新平台。
        """
        provider_cls, builtin_url = _get_provider_class_and_url(platform)
        # 非 custom 平台强制使用内置 URL；custom 平台优先使用覆盖 URL
        base_url = (override_url or builtin_url) if platform == "custom" else builtin_url
        return provider_cls(
            name=name,
            base_url=base_url,
            api_key=api_key,
            default_model=default_model,
            timeout=timeout,
        )

    def _build_defaults(self):
        """基于现有 config 自动构建默认 Provider。"""
        # --- 默认文本对话 Provider（主备切换）---
        primary = self._create_provider(
            name="primary",
            platform=cfg.LLM_PLATFORM,
            api_key=cfg.LLM_API_KEY,
            override_url=cfg.LLM_BASE_URL or None,
            default_model=cfg.LLM_MODEL,
        )
        # 若备用 API Key 为空且平台与首选一致，自动复用首选 Key
        backup_key = cfg.BACKUP_API_KEY
        if not backup_key and cfg.BACKUP_PLATFORM == cfg.LLM_PLATFORM:
            backup_key = cfg.LLM_API_KEY

        backup = self._create_provider(
            name="backup",
            platform=cfg.BACKUP_PLATFORM,
            api_key=backup_key,
            override_url=cfg.BACKUP_BASE_URL or None,
            default_model=cfg.BACKUP_MODEL,
        )
        default_fallback = FallbackProvider(
            name="default",
            primary=primary,
            backup=backup,
            fallback_message=(
                f"（{cfg.ROBOT_NAME.title()} 好像有点不舒服，"
                f"暂时连接不上大脑...{cfg.MASTER_NAME}等会再找我好吗？）"
            ),
        )
        self.register("default", default_fallback)

        # --- Vision Provider ---
        if cfg.VISION_MODEL and cfg.IMAGE_PROCESS_API_KEY:
            vision = self._create_provider(
                name="vision",
                platform=cfg.VISION_PLATFORM,
                api_key=cfg.IMAGE_PROCESS_API_KEY,
                override_url=cfg.IMAGE_PROCESS_API_URL or None,
                default_model=cfg.VISION_MODEL,
                timeout=40.0,
            )
            self.register("vision", vision)

        logger.info("[ProviderRegistry] 默认 Provider 初始化完成")

    def register(self, name: str, provider: BaseProvider) -> None:
        """注册一个 Provider。"""
        self._providers[name] = provider
        logger.info(
            f"[ProviderRegistry] 注册 Provider: {name} -> {provider.__class__.__name__}"
        )

    def get(self, name: str = "default") -> BaseProvider:
        """按名称获取 Provider。"""
        provider = self._providers.get(name)
        if provider is None:
            available = ", ".join(self._providers.keys())
            raise KeyError(f"未找到 Provider '{name}'，可用: {available}")
        return provider

    def has(self, name: str) -> bool:
        """检查是否已注册指定 Provider。"""
        return name in self._providers

    def reload(self):
        """
        根据当前 config 重新构建默认 Provider。
        在配置热重载后调用，使平台/API Key/模型变更立即生效。
        """
        logger.info("[ProviderRegistry] 配置变更，正在重新构建 Provider...")
        self._providers.clear()
        self._build_defaults()

    async def close_all(self) -> None:
        """关闭所有 Provider 并清理全局 Session。"""
        for name, provider in list(self._providers.items()):
            try:
                await provider.close()
                logger.info(f"[ProviderRegistry] 已关闭 Provider: {name}")
            except Exception as e:
                logger.error(f"[ProviderRegistry] 关闭 Provider {name} 失败: {e}")
        await OpenAICompatibleProvider.close_global_session()
