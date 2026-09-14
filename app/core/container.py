"""Inversion of Control (IoC) Container registry using Injector."""

from __future__ import annotations

import logging
from typing import Any

from injector import Injector, Module

from app.core.config import AppSettings, settings
from app.core.modules import PlatformModule

logger = logging.getLogger("glados.core.container")

_container_instance: Injector | None = None


def create_container(
    app_settings: AppSettings | None = None,
    custom_modules: list[Module | type[Module]] | None = None,
) -> Injector:
    """Creates a new configured Injector container instance."""
    base_settings = app_settings or settings
    module_list: list[Any] = [PlatformModule(app_settings=base_settings)]

    if custom_modules:
        module_list.extend(custom_modules)

    return Injector(module_list, auto_bind=False)


def get_container() -> Injector:
    """Retrieves or lazily instantiates the application global Injector container."""
    global _container_instance
    if _container_instance is None:
        _container_instance = create_container()
    return _container_instance


def reset_container() -> None:
    """Clears the cached container instance, primarily used across automated test suites."""
    global _container_instance
    _container_instance = None
