from pathlib import Path

from landing_gear.service_factory import build_web_app_from_config


CONFIG_PATH = Path(__file__).with_name('conf.toml')


async def build_app(config_path: str | Path = CONFIG_PATH):
    return await build_web_app_from_config(config_path)
