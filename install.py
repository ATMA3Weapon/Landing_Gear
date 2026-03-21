from pathlib import Path

from landing_gear.install_support import build_install_cli

from service import build_app


CONFIG_PATH = Path(__file__).with_name('conf.toml')
main = build_install_cli(build_app, CONFIG_PATH)


if __name__ == '__main__':
    main()
