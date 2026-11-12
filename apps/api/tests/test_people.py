"""People: pseudonym to name mapping and the admin's display choice (ADR 0013). SYNTHETIC data only
(example.test addresses and invented names)."""

import os

import pytest
from conftest import ROLE
from sqlalchemy import text
from test_economics_api import ADMIN, READER, Api

from cfa_tokenomics import admin, people
from cfa_tokenomics.authz import Principal, Role
from cfa_tokenomics.db import AuditEvent
from cfa_tokenomics.privacy import Pseudonymizer

URL = os.environ.get("CFA_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="CFA_TEST_DATABASE_URL not set")
PZ = Pseudonymizer(b"synthetic-test-key-0123456789")
ROOT = Principal("https://idp.test", "root", Role.ADMIN)
ANN, BOB = "ann@example.test", "bob@example.test"


@pytest.fixture
def api(env):
    return Api(env)


def audit(api, tid=None):
    with api.session(tid) as db:
        return [(e.action, e.detail) for e in db.query(AuditEvent).order_by(AuditEvent.id)]


def load(api, rows=((ANN, "Ann Example"), (BOB, "Bob Example")), tid=None):
    with api.session(tid) as db:
        return people.upsert_people(db, ROOT, tid or api.a, PZ, rows)


def test_the_default_shows_pseudonyms_and_looks_nothing_up(api):
    load(api)
    ids = [PZ.pseudonym(ANN)]
    r = api.c.get("/v1/people/resolve", params={"ids": ids}, headers=READER).json()
    assert r == {"display": "pseudonym", "shown": {ids[0]: ids[0]}}
    assert all(a != "people.resolve" for a, _ in audit(api))


def test_only_an_admin_can_choose_what_is_shown(api):
    body = {"display": "name"}
    assert api.c.put("/v1/admin/people/display", json=body, headers=READER).status_code == 403
    assert api.c.put("/v1/admin/people/display", json=body, headers=ADMIN).status_code == 204
    bad = {"display": "Name"}
    assert api.c.put("/v1/admin/people/display", json=bad, headers=ADMIN).status_code == 422


def test_name_mode_shows_names_and_keeps_unknown_people_as_pseudonyms(api):
    load(api)
    api.c.put("/v1/admin/people/display", json={"display": "name"}, headers=ADMIN)
    unknown = PZ.pseudonym("carol@example.test")
    ids = [PZ.pseudonym(ANN), PZ.pseudonym(BOB), unknown]
    r = api.c.get("/v1/people/resolve", params={"ids": ids}, headers=READER).json()
    assert r["display"] == "name"
    assert r["shown"] == {ids[0]: "Ann Example", ids[1]: "Bob Example", unknown: unknown}


def test_switching_back_hides_names_again(api):
    load(api)
    for mode in ("name", "pseudonym"):
        api.c.put("/v1/admin/people/display", json={"display": mode}, headers=ADMIN)
    ids = [PZ.pseudonym(ANN)]
    shown = api.c.get("/v1/people/resolve", params={"ids": ids}, headers=READER).json()["shown"]
    assert shown == {ids[0]: ids[0]}


def test_every_change_and_every_lookup_is_audited_without_names(api):
    load(api)
    api.c.put("/v1/admin/people/display", json={"display": "name"}, headers=ADMIN)
    ids = [PZ.pseudonym(ANN), PZ.pseudonym("carol@example.test")]
    api.c.get("/v1/people/resolve", params={"ids": ids}, headers=READER)
    log = audit(api)
    assert [a for a, _ in log] == ["people.import", "people.display", "people.resolve"]
    assert log[1][1] == {"from": "pseudonym", "to": "name"}
    assert log[2][1] == {"asked": 2, "shown_as_names": 1}
    assert "Ann" not in str(log) and ANN not in str(log)


def test_a_name_is_never_written_into_usage_or_cost_tables(api):
    load(api)
    api.c.put("/v1/admin/people/display", json={"display": "name"}, headers=ADMIN)
    with api.engine.connect() as c:
        tables = [
            r[0]
            for r in c.execute(
                text(
                    "select table_name from information_schema.columns where column_name = "
                    "'display_name' and table_schema = 'public'"
                )
            )
        ]
    assert tables == ["people"]


def test_only_the_pseudonym_and_the_name_are_stored(api):
    load(api)
    with api.engine.connect() as c:
        cols = {
            r[0]
            for r in c.execute(
                text("select column_name from information_schema.columns where table_name='people'")
            )
        }
        dump = str(c.execute(text("select * from people")).all())
    assert cols == {"tenant_id", "pseudonym", "display_name", "source", "updated_at"}
    assert ANN not in dump and "example.test" not in dump


def test_import_is_idempotent_and_updates_a_changed_name(api):
    assert load(api) == {"added": 2, "updated": 0, "unchanged": 0}
    assert load(api) == {"added": 0, "updated": 0, "unchanged": 2}
    assert load(api, [(ANN.upper(), "Ann Renamed")]) == {"added": 0, "updated": 1, "unchanged": 0}


def test_one_bad_row_refuses_the_whole_batch(api):
    with api.session() as db, pytest.raises(people.PeopleError, match="row 2"):
        people.upsert_people(db, ROOT, api.a, PZ, [(ANN, "Ann Example"), (BOB, "  ")])
    with api.engine.connect() as c:
        assert c.execute(text("select count(*) from people")).scalar() == 0


def test_a_tenant_cannot_see_or_resolve_another_tenants_people(api):
    load(api)
    load(api, [(ANN, "Ann Of Tenant B")], tid=api.b)
    with api.session(api.b) as db:
        people.set_display(db, ROOT, api.b, "name")
        shown = people.resolve(db, ROOT, api.b, [PZ.pseudonym(ANN)])
    assert shown == {PZ.pseudonym(ANN): "Ann Of Tenant B"}
    with api.session(api.a) as db:  # tenant A has its own two people and never sees B's row
        names = {r[0] for r in db.execute(text("select display_name from people"))}
    assert names == {"Ann Example", "Bob Example"}


def test_lookups_are_bounded(api):
    with api.session() as db, pytest.raises(people.PeopleError, match="at most"):
        people.resolve(db, ROOT, api.a, [f"u_{i:032x}" for i in range(people.MAX_LOOKUP + 1)])


def test_the_runtime_role_cannot_delete_the_audit_trail_of_lookups(api):
    load(api)
    with api.session() as db:
        people.set_display(db, ROOT, api.a, "name")
        people.resolve(db, ROOT, api.a, [PZ.pseudonym(ANN)])
    with api.engine.begin() as c:
        c.execute(text(f"set local role {ROLE}"))
        c.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": str(api.a)})
        with pytest.raises(Exception, match="permission denied"):
            c.execute(text("delete from audit_events"))


def test_cli_imports_names_and_sets_display(api, tmp_path, monkeypatch, capsys):
    key = tmp_path / "key"
    key.write_text("synthetic-test-key-0123456789")
    key.chmod(0o600)
    csv_file = tmp_path / "people.csv"
    csv_file.write_text(f"identifier,name\n{ANN},Ann Example\n")
    monkeypatch.setenv("CFA_DATABASE_URL", URL)
    assert admin.main(["people-import", str(api.a), str(csv_file), f"file:{key}"]) == 0
    assert '"added": 1' in capsys.readouterr().out
    assert admin.main(["person-display", str(api.a), "name"]) == 0
    assert admin.main(["person-display", str(api.a), "everyone"]) == 1
    with api.session() as db:
        assert people.resolve(db, ROOT, api.a, [PZ.pseudonym(ANN)]) == {
            PZ.pseudonym(ANN): "Ann Example"
        }


def test_cli_refuses_a_file_without_the_right_columns(api, tmp_path, monkeypatch):
    key = tmp_path / "key"
    key.write_text("synthetic-test-key-0123456789")
    csv_file = tmp_path / "people.csv"
    csv_file.write_text("email,full_name\nx,y\n")
    monkeypatch.setenv("CFA_DATABASE_URL", URL)
    assert admin.main(["people-import", str(api.a), str(csv_file), f"file:{key}"]) == 1
