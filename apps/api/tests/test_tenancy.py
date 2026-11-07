"""Tenant isolation, the economics core schema and calculation-node persistence.

Runs against real PostgreSQL. Isolation tests execute as a RESTRICTED role (no superuser, no BYPASSRLS),
because a superuser silently ignores row-level security. All data is synthetic."""

import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from conftest import ROLE, WIDE, _as, app, two_tenants
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session
from test_econ import example

from cfa_tokenomics import admin, migrate, store
from cfa_tokenomics.econ import scenario as sc
from cfa_tokenomics.econ.node import leaf
from cfa_tokenomics.econ.types import Basis
from cfa_tokenomics.models_econ import (
    Application,
    BusinessUnit,
    CalcNodeRow,
    PriceBook,
    Scenario,
    ValueAssumption,
)
from cfa_tokenomics.tenancy import app_role_grants_sql, role_can_bypass_rls

URL = os.environ.get("CFA_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="CFA_TEST_DATABASE_URL not set")
NOW = datetime(2026, 1, 1, tzinfo=UTC)
# ---- the guard -------------------------------------------------------------------------------------


def test_superuser_bypasses_rls_but_the_app_role_does_not(env):
    with env.connect() as c:
        assert role_can_bypass_rls(c) is True
    with app(env, None) as db:
        assert role_can_bypass_rls(db.connection()) is False


def test_grants_sql_is_least_privilege_and_validates_the_role_name():
    sql = app_role_grants_sql("cfa_runtime")
    assert "ALL PRIVILEGES" not in sql and "SUPERUSER" not in sql and "BYPASSRLS" not in sql
    from cfa_tokenomics.tenancy import APPEND_ONLY_TABLES

    append_only = [ln for ln in sql.splitlines() if "value_assumptions" in ln]
    assert append_only == [
        f"GRANT SELECT, INSERT ON {', '.join(APPEND_ONLY_TABLES)} TO cfa_runtime;"
    ]
    assert "UPDATE" not in append_only[0] and "DELETE" not in append_only[0]
    for bad in ("Robert'; drop table x;--", "UPPER", "", "a" * 64):
        with pytest.raises(ValueError):
            app_role_grants_sql(bad)


# ---- isolation -------------------------------------------------------------------------------------


def test_tenants_cannot_see_each_others_rows(env):
    a, b = two_tenants(env)
    with app(env, a) as db:
        store.create_application(db, a, "claims-assistant", "usd")
    with app(env, b) as db:
        assert db.query(Application).count() == 0
    with app(env, a) as db:
        assert db.query(Application).count() == 1


def test_a_tenant_cannot_write_a_row_for_another_tenant(env):
    a, b = two_tenants(env)
    with app(env, b) as db, pytest.raises(DBAPIError, match="row-level security"):
        db.add(Application(tenant_id=a, name="smuggled", currency="USD"))
        db.commit()


def test_no_tenant_context_means_no_rows_and_no_writes(env):
    a, _ = two_tenants(env)
    with app(env, a) as db:
        store.create_application(db, a, "visible", "usd")
    with app(env, None) as db:
        assert db.query(Application).count() == 0
        assert db.query(PriceBook).count() == 0
    with app(env, None) as db, pytest.raises(DBAPIError, match="row-level security"):
        db.add(Application(tenant_id=a, name="x", currency="USD"))
        db.commit()


def test_a_tenant_cannot_be_created_inside_another_tenant(env):
    a = store.create_tenant(env, "A", "usd", _as(ROLE))
    with app(env, a) as db, pytest.raises(DBAPIError, match="row-level security"):
        from cfa_tokenomics.models_econ import Tenant

        db.add(Tenant(id=uuid.uuid4(), name="intruder", base_currency="USD"))
        db.commit()


def test_foreign_keys_include_the_tenant_even_for_a_privileged_writer(env):
    """Superusers bypass RLS, so the schema itself must refuse cross-tenant references."""
    a, b = two_tenants(env)
    with app(env, a) as db:
        bu = BusinessUnit(tenant_id=a, name="finance")
        db.add(bu)
        db.commit()
        bu_id = bu.id
    with Session(env) as admin_db, pytest.raises(IntegrityError, match="fk_app_bu"):
        admin_db.add(Application(tenant_id=b, name="x", currency="USD", business_unit_id=bu_id))
        admin_db.commit()


# ---- append-only -----------------------------------------------------------------------------------


def _assumption(db, tid, app_row, value="0.7"):
    return store.add_assumption(
        db, tid, app_row.id, "realization", Decimal(value), "ratio", "assumed",
        "Pilot team estimate", "ann@example.test",
    )  # fmt: skip


def test_assumptions_are_versioned_and_never_edited(env):
    a, _ = two_tenants(env)
    with app(env, a) as db:
        row = store.create_application(db, a, "app", "usd")
        v1 = _assumption(db, a, row, "0.7")
        v2 = _assumption(db, a, row, "0.5")
        assert (v1.version, v2.version) == (1, 2)
        assert store.current_assumptions(db, row.id)["realization"].value == Decimal("0.5")
        hist = store.assumption_history(db, row.id, "realization")
        assert [h.value for h in hist] == [Decimal("0.7"), Decimal("0.5")]


def test_history_cannot_be_updated_or_deleted_by_the_runtime_role(env):
    a, _ = two_tenants(env)
    with app(env, a) as db:
        row = store.create_application(db, a, "app", "usd")
        _assumption(db, a, row)
    for stmt in ("update value_assumptions set value = 1", "delete from value_assumptions"):
        with app(env, a) as db, pytest.raises(DBAPIError, match="permission denied"):
            db.execute(text(stmt))


def test_row_level_security_alone_also_blocks_updates_and_deletes(env):
    """Even a role that was granted UPDATE and DELETE changes nothing: there is no such policy."""
    a, _ = two_tenants(env)
    with app(env, a, WIDE) as db:
        row = store.create_application(db, a, "app", "usd")
        _assumption(db, a, row)
    with app(env, a, WIDE) as db:
        assert db.execute(text("update value_assumptions set value = 1")).rowcount == 0
        assert db.execute(text("delete from value_assumptions")).rowcount == 0
        db.commit()
    with Session(env) as admin_db:
        assert admin_db.query(ValueAssumption).one().value == Decimal("0.7")


def test_a_rationale_is_required_in_code_and_in_the_database(env):
    a, _ = two_tenants(env)
    with app(env, a) as db:
        row = store.create_application(db, a, "app", "usd")
        with pytest.raises(store.StoreError, match="rationale"):
            store.add_assumption(db, a, row.id, "k", Decimal(1), "u", "assumed", "  ", "ann")
    with Session(env) as admin_db, pytest.raises(IntegrityError, match="ck_assumption_rationale"):
        admin_db.add(
            ValueAssumption(tenant_id=a, application_id=row.id, key="k", value=Decimal(1),
                            unit="u", basis="assumed", rationale="   ", author="x", version=1)
        )  # fmt: skip
        admin_db.commit()


def test_basis_and_domain_constraints(env):
    a, _ = two_tenants(env)
    with app(env, a) as db:
        row = store.create_application(db, a, "app", "usd")
    with app(env, a) as db, pytest.raises(IntegrityError, match="ck_assumption_basis"):
        store.add_assumption(db, a, row.id, "k", Decimal(1), "u", "guessed", "why", "ann")
    with app(env, a) as db, pytest.raises(IntegrityError, match="ck_app_lifecycle"):
        store.create_application(db, a, "bad", "usd", lifecycle="zombie")
    with app(env, a) as db, pytest.raises(IntegrityError, match="ck_app_inv_has_basis"):
        store.create_application(db, a, "x", "usd", initial_investment=Decimal(1000))


# ---- price books -----------------------------------------------------------------------------------


def test_price_entries_cannot_overlap_and_must_match_the_book_currency(env):
    a, _ = two_tenants(env)
    with app(env, a) as db:
        book = PriceBook(tenant_id=a, name="list", currency="USD", source="list")
        db.add(book)
        db.commit()

        def add(**kw):
            base = dict(
                provider="p",
                model_key="m",
                measure="input_tokens",
                unit_price=Decimal(3),
                currency="USD",
                effective_from=NOW,
            )
            return store.add_price_entry(db, a, book, **{**base, **kw})  # fmt: skip

        add(effective_to=NOW + timedelta(days=30))
        with pytest.raises(store.PriceOverlapError):
            add(effective_from=NOW + timedelta(days=10))
        with pytest.raises(store.PriceOverlapError):
            add(effective_from=NOW - timedelta(days=5), effective_to=NOW + timedelta(days=1))
        add(effective_from=NOW + timedelta(days=30))  # starts exactly where the last one ends
        add(measure="output_tokens", effective_from=NOW)  # another measure is independent
        with pytest.raises(store.StoreError, match="currency"):
            add(measure="cache_read_tokens", currency="EUR")


def test_price_at_uses_a_half_open_window_and_database_rejects_bad_prices(env):
    a, _ = two_tenants(env)
    with app(env, a) as db:
        book = PriceBook(tenant_id=a, name="list", currency="USD", source="list")
        db.add(book)
        db.commit()
        store.add_price_entry(db, a, book, "p", "m", "input_tokens", Decimal(3), "USD", NOW,
                              NOW + timedelta(days=30))  # fmt: skip
        store.add_price_entry(db, a, book, "p", "m", "input_tokens", Decimal(4), "USD",
                              NOW + timedelta(days=30))  # fmt: skip
        first = store.price_at(db, book.id, "p", "m", "input_tokens", NOW + timedelta(days=29))
        boundary = store.price_at(db, book.id, "p", "m", "input_tokens", NOW + timedelta(days=30))
        assert (first.unit_price, boundary.unit_price) == (3, 4)
        assert (
            store.price_at(db, book.id, "p", "m", "input_tokens", NOW - timedelta(seconds=1))
            is None
        )
    with app(env, a) as db, pytest.raises(IntegrityError, match="ck_price_nonneg"):
        store.add_price_entry(db, a, book, "p", "z", "input_tokens", Decimal(-1), "USD", NOW)
    with app(env, a) as db, pytest.raises(IntegrityError, match="ck_price_window"):
        store.add_price_entry(db, a, book, "p", "w", "input_tokens", Decimal(1), "USD", NOW, NOW)


# ---- scenarios -------------------------------------------------------------------------------------


def test_scenarios_store_drivers_with_their_basis_and_reject_bad_kinds(env):
    a, _ = two_tenants(env)
    with app(env, a) as db:
        row = store.create_application(db, a, "app", "usd")
        sc_row = store.save_scenario(
            db, a, row.id, "forecast 10x", "forecast",
            {"users": (Decimal(1000), "users", "assumed"), "adoption": (None, "ratio", "assumed")},
        )  # fmt: skip
        assert sc_row.status == "draft"
        from cfa_tokenomics.models_econ import ScenarioDriver

        drivers = {d.driver_key: d for d in db.query(ScenarioDriver)}
        assert (
            drivers["users"].value == 1000 and drivers["adoption"].value is None
        )  # unknown stays unknown
    with app(env, a) as db, pytest.raises(IntegrityError, match="ck_scenario_kind"):
        store.save_scenario(db, a, row.id, "bad", "wishful", {})


def test_a_scenario_cannot_build_on_another_tenants_scenario(env):
    a, b = two_tenants(env)
    with app(env, a) as db:
        row = store.create_application(db, a, "app", "usd")
        base = store.save_scenario(db, a, row.id, "base", "baseline", {})
        base_id = base.id
    with app(env, b) as db:
        other = store.create_application(db, b, "app-b", "usd")
        other_id = other.id
    with Session(env) as admin_db, pytest.raises(IntegrityError, match="fk_scenario_base"):
        admin_db.add(
            Scenario(tenant_id=b, application_id=other_id, name="x", kind="forecast",
                     base_scenario_id=base_id)
        )  # fmt: skip
        admin_db.commit()


# ---- calculation nodes: persistence and tamper detection -------------------------------------------


def _roi(a_session_tid=None):
    return sc.evaluate(example())["roi_capacity"]


def test_a_calculation_tree_round_trips_and_keeps_its_basis(env):
    a, _ = two_tenants(env)
    root = _roi()
    with app(env, a) as db:
        n = store.save_node_tree(db, a, root)
    with app(env, a) as db:
        loaded = store.load_node_tree(db, root.id)
    assert n == len({x.id for x in root.walk()}) > 10
    assert loaded.id == root.id and loaded.value == root.value
    assert loaded.mix == root.mix and loaded.basis is Basis.ASSUMED
    assert [x.key for x in loaded.walk()] == [x.key for x in root.walk()]
    assert {x.key for x in loaded.walk() if x.formula_id == "input"} >= {"price.input", "ops_hours"}


def test_saving_a_tree_twice_adds_nothing(env):
    a, _ = two_tenants(env)
    root = _roi()
    with app(env, a) as db:
        store.save_node_tree(db, a, root)
        store.save_node_tree(db, a, root)
    with Session(env) as admin_db:
        assert admin_db.query(CalcNodeRow).count() == len({x.id for x in root.walk()})


def test_another_tenant_cannot_load_a_calculation(env):
    a, b = two_tenants(env)
    root = _roi()
    with app(env, a) as db:
        store.save_node_tree(db, a, root)
    with app(env, b) as db, pytest.raises(store.StoreError, match="no such"):
        store.load_node_tree(db, root.id)


def test_editing_a_stored_value_is_detected(env):
    a, _ = two_tenants(env)
    root = _roi()
    with app(env, a) as db:
        store.save_node_tree(db, a, root)
    with Session(env) as admin_db:  # a privileged writer tampers with the number
        admin_db.execute(
            text("update calculation_nodes set value = value + 1 where id = :i"), {"i": root.id}
        )
        admin_db.commit()
    with app(env, a) as db, pytest.raises(store.TamperedNodeError):
        store.load_node_tree(db, root.id)


def test_changing_a_stored_basis_from_assumed_to_observed_is_detected(env):
    """Presenting an assumption as observed is the failure the whole model exists to prevent."""
    a, _ = two_tenants(env)
    root = _roi()
    with app(env, a) as db:
        store.save_node_tree(db, a, root)
    with Session(env) as admin_db:
        admin_db.execute(
            text(
                "update calculation_nodes set mix_observed = 1, mix_assumed = 0, mix_estimated = 0 where id = :i"
            ),
            {"i": root.id},
        )
        admin_db.commit()
    with app(env, a) as db, pytest.raises(store.TamperedNodeError):
        store.load_node_tree(db, root.id)


def test_the_runtime_role_cannot_edit_calculation_nodes(env):
    a, _ = two_tenants(env)
    root = _roi()
    with app(env, a) as db:
        store.save_node_tree(db, a, root)
    with app(env, a) as db, pytest.raises(DBAPIError, match="permission denied"):
        db.execute(text("update calculation_nodes set note = 'edited'"))


def test_node_ids_do_not_depend_on_decimal_scale_or_basis_words():
    assert (
        leaf("x", "315.0", "hours", Basis.OBSERVED).id
        == leaf("x", "315", "hours", Basis.OBSERVED).id
    )
    assert leaf("x", 1, "u", Basis.OBSERVED).id != leaf("x", 1, "u", Basis.ASSUMED).id


# ---- migration and operator tools ------------------------------------------------------------------


def test_downgrade_removes_the_economics_tables_and_keeps_the_ledger(env):
    migrate.main(["downgrade", "0004"])
    with env.connect() as c:
        names = {
            r[0]
            for r in c.execute(text("select tablename from pg_tables where schemaname='public'"))
        }
    assert "applications" not in names and "tenants" not in names
    assert {"usage_request_observations", "role_assignments"} <= names
    migrate.main(["upgrade"])


def test_rls_is_forced_on_every_tenant_table(env):
    with env.connect() as c:
        rows = c.execute(
            text("select relname, relrowsecurity, relforcerowsecurity from pg_class where relname in "
                 "('tenants','applications','value_assumptions','calculation_nodes','calculation_edges',"
                 "'price_entries','scenario_drivers','workloads')")
        ).all()  # fmt: skip
    assert len(rows) == 8 and all(r[1] and r[2] for r in rows)


def test_admin_commands(env, capsys):
    assert admin.main(["app-role-sql", "cfa_runtime"]) == 0
    assert "GRANT USAGE ON SCHEMA public TO cfa_runtime" in capsys.readouterr().out
    assert admin.main(["create-tenant", "Acme", "usd"]) == 0
    printed = capsys.readouterr().out.strip()
    assert uuid.UUID(printed)
    assert admin.main(["bogus"]) == 2
