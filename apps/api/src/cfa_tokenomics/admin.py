"""Operator commands. Run against the database as its owner (CFA_DATABASE_URL).

python -m cfa_tokenomics.admin create-tenant NAME CURRENCY
python -m cfa_tokenomics.admin app-role-sql ROLE     prints the grants for the runtime role
"""

import os
import sys

from sqlalchemy import create_engine

from .store import create_tenant
from .tenancy import app_role_grants_sql


def main(argv: list[str]) -> int:
    if len(argv) == 3 and argv[0] == "create-tenant":
        url = os.environ.get("CFA_DATABASE_URL")
        if not url:
            print("CFA_DATABASE_URL is required", file=sys.stderr)
            return 2
        print(create_tenant(create_engine(url), argv[1], argv[2]))
        return 0
    if len(argv) == 2 and argv[0] == "app-role-sql":
        print(app_role_grants_sql(argv[1]))
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
