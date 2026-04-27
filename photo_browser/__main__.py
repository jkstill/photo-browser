from __future__ import annotations

from .app import create_app
from .config import load_config


def main() -> None:
    config = load_config()
    app = create_app(config)
    app.run(host=config.host, port=config.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
