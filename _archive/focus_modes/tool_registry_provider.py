# 原位于 core/toolchain.py 的多模式工具注册表分发器
from core.toolchain import FunctionRegistry, ToolSpec


class ToolRegistryProvider:
    """按 mode 提供不同 FunctionRegistry。"""

    def __init__(self, default_specs: list[ToolSpec], mode_specs: dict[str, list[ToolSpec]] | None = None):
        self.default_registry = FunctionRegistry()
        self.default_registry.scan_and_register(default_specs)
        self._registries: dict[str, FunctionRegistry] = {"default": self.default_registry}
        self._mode_to_group: dict[str, str] = {}
        for mode, specs in (mode_specs or {}).items():
            registry = FunctionRegistry()
            registry.scan_and_register(specs)
            self._registries[mode] = registry
            self._mode_to_group[mode] = mode

    def get_registry(self, mode: str | None = None) -> FunctionRegistry:
        """获取指定 mode 的工具注册表，未知 mode 回退默认工具组。"""
        if not mode:
            return self.default_registry
        group = self._mode_to_group.get(mode, mode)
        return self._registries.get(group, self.default_registry)

    def get_tools(self, mode: str | None = None) -> list:
        return self.get_registry(mode).get_tools()

    def list_functions(self, mode: str | None = None) -> list:
        return self.get_registry(mode).list_functions()
