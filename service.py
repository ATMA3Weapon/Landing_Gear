from pathlib import Path

from landing_gear.service_factory import build_web_app_from_config


def resolve_default_config_path() -> Path:
    repo_root = Path(__file__).resolve().parent
    primary = repo_root / 'conf.toml'
    if primary.exists():
        return primary
    example = repo_root / 'conf.example.toml'
    if example.exists():
        return example
    return primary


CONFIG_PATH = resolve_default_config_path()


async def build_app(config_path: str | Path = CONFIG_PATH):
    return await build_web_app_from_config(config_path)
