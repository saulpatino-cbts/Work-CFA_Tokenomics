"""Run migrations: ``python -m cfa_tokenomics.migrate [upgrade|downgrade] [revision]``.

Requires CFA_DATABASE_URL. Take a customer-approved recovery checkpoint first (docs/operations.md).
"""

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config


def _config() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    return cfg


def main(argv: list[str]) -> None:
    action = argv[0] if argv else "upgrade"
    rev = argv[1] if len(argv) > 1 else ("head" if action == "upgrade" else "-1")
    getattr(command, action)(_config(), rev)


if __name__ == "__main__":
    main(sys.argv[1:])
