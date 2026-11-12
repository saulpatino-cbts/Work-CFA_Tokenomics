"""One shared fictional cast, so every sample source describes the same people and applications.

Nothing here is real. Emails use the reserved ``example.test`` domain, account identifiers are
obviously fake, and prices are placeholders, not any provider's rates.
"""

from __future__ import annotations

from dataclasses import dataclass

ORG = "Example Co"
WORKSPACE_ID = "ws-example-0001"
AWS_ACCOUNT = "000000000001"
AWS_ACCOUNT_NAME = "example-aws-sandbox"
AZURE_SUBSCRIPTION = "00000000-0000-4000-8000-0000000000a1"
AZURE_ACCOUNT_NAME = "example-azure-sandbox"
CREDIT_USD = "0.04"  # an illustrative credit price, not a vendor rate


@dataclass(frozen=True)
class User:
    user_id: str
    email: str
    team: str


@dataclass(frozen=True)
class App:
    key: str  # the tag value on cloud cost lines
    name: str
    team: str


APPS = (
    App("claims-assistant", "Claims assistant", "claims-ops"),
    App("support-copilot", "Support copilot", "service-desk"),
    App("dev-assistant", "Dev assistant", "platform-eng"),
)
TEAMS = tuple(a.team for a in APPS)
USERS = tuple(
    User(f"user-{n:04d}", f"user{n:04d}@example.test", TEAMS[(n - 1) // 4]) for n in range(1, 13)
)  # four users per team


def users_of(team: str) -> list[User]:
    return [u for u in USERS if u.team == team]


def app_of_team(team: str) -> App:
    return next(a for a in APPS if a.team == team)
