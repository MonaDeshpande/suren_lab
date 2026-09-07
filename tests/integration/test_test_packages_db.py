"""

Integration tests for test packages (requires PostgreSQL).

"""



from __future__ import annotations



import uuid



import pytest



from services.test_packages import (

    PACKAGE_TYPE_BASIC_NUTRITION,

    PACKAGE_TYPE_FSSAI,

    PACKAGE_TYPE_NUTRITION_ONLY,

    activate_package,

    create_package,

    delete_package,

    describe_sample_package,

    describe_sample_package_for_product,

    get_package,

    list_package_versions,

    package_status_label,

    resolve_package_for_product,

    resolve_package_tests,

    update_package,

)

from db.connection import get_db



pytestmark = pytest.mark.integration





@pytest.fixture

def clean_packages():

    """Remove test packages created during the test."""

    created_ids: list[int] = []

    yield created_ids

    if not created_ids:

        return

    with get_db() as conn:

        with conn.cursor() as cur:

            cur.execute(

                "DELETE FROM sample_test_package_tests WHERE package_id = ANY(%s)",

                (created_ids,),

            )

            cur.execute(

                "DELETE FROM entity_versions WHERE entity_table = %s AND entity_id = ANY(%s)",

                ("sample_test_packages", [str(i) for i in created_ids]),

            )

            cur.execute(

                "DELETE FROM sample_test_packages WHERE id = ANY(%s)",

                (created_ids,),

            )





def test_package_crud_and_versioning(require_db, clean_packages):

    suffix = uuid.uuid4().hex[:8]

    name = f"QA Jaggery {suffix}"

    keys_wl = ["moisture", "total_ash", "added_color"]

    keys_nwl = ["bn_protein"]

    pkg = create_package(name, PACKAGE_TYPE_FSSAI, keys_wl, keys_nwl)

    clean_packages.append(pkg.id)



    assert pkg.current_version_no == 1

    assert pkg.test_keys_with_logo == keys_wl

    assert pkg.test_keys_without_logo == keys_nwl

    assert pkg.test_keys == keys_wl + keys_nwl



    resolved = resolve_package_tests(name, PACKAGE_TYPE_FSSAI)

    assert resolved is not None

    assert resolved.package_id == pkg.id

    assert resolved.test_keys_with_logo == keys_wl

    assert resolved.test_keys_without_logo == keys_nwl



    updated = update_package(

        pkg.id,

        ["moisture"],

        ["bn_protein", "bn_total_fat"],

        "Removed ash per SOP update for QA",

    )

    assert updated.id != pkg.id
    assert updated.is_active is True
    assert get_package(pkg.id).is_active is False
    clean_packages.append(updated.id)

    assert updated.current_version_no == 2

    assert updated.test_keys_with_logo == ["moisture"]

    assert updated.test_keys_without_logo == ["bn_protein", "bn_total_fat"]



    versions = list_package_versions(pkg.id)

    assert len(versions) >= 1

    assert versions[0].edit_reason



    resolved2 = resolve_package_tests(name, PACKAGE_TYPE_FSSAI)

    assert resolved2 is not None

    assert resolved2.package_id == updated.id

    assert resolved2.package_version_no == 2

    assert resolved2.test_keys_with_logo == ["moisture"]



    delete_package(updated.id, "QA cleanup deactivate package")

    assert get_package(updated.id).is_active is False

    assert resolve_package_tests(name, PACKAGE_TYPE_FSSAI) is None





def test_package_unique_per_name(require_db, clean_packages):

    suffix = uuid.uuid4().hex[:8]

    name = f"QA Sugar {suffix}"

    pkg = create_package(name, PACKAGE_TYPE_NUTRITION_ONLY, ["bn_moisture"], [])

    clean_packages.append(pkg.id)

    with pytest.raises(ValueError, match="already exists"):
        create_package(name, PACKAGE_TYPE_NUTRITION_ONLY, ["bn_protein"], [])

    with pytest.raises(ValueError, match="already exists"):
        create_package(name, PACKAGE_TYPE_FSSAI, ["moisture"], ["total_ash"])


def test_activate_package_after_deactivate(require_db, clean_packages):
    suffix = uuid.uuid4().hex[:8]
    name = f"QA Activate {suffix}"
    pkg = create_package(name, PACKAGE_TYPE_FSSAI, ["moisture"], ["total_ash"])
    clean_packages.append(pkg.id)

    delete_package(pkg.id, "QA deactivate before activate test")
    assert resolve_package_tests(name, PACKAGE_TYPE_FSSAI) is None
    desc = describe_sample_package(name, PACKAGE_TYPE_FSSAI)
    assert desc["status"] == "inactive"

    activated = activate_package(pkg.id, "QA reactivate package for intake")
    assert activated.is_active is True
    assert resolve_package_tests(name, PACKAGE_TYPE_FSSAI) is not None
    desc2 = describe_sample_package(name, PACKAGE_TYPE_FSSAI)
    assert desc2["status"] == "defined"
    assert package_status_label(desc2) == "Defined"


def test_activate_package_rejects_already_active(require_db, clean_packages):
    suffix = uuid.uuid4().hex[:8]
    name = f"QA AlreadyActive {suffix}"
    pkg = create_package(name, PACKAGE_TYPE_FSSAI, ["moisture"], [])
    clean_packages.append(pkg.id)

    with pytest.raises(ValueError, match="already active"):
        activate_package(pkg.id, "QA try activate active package")


def test_describe_sample_package_not_defined(require_db):
    desc = describe_sample_package("NoSuchProduct", PACKAGE_TYPE_FSSAI)
    assert desc["status"] == "not_defined"
    assert package_status_label(desc) == "Not defined"


def test_resolve_package_for_product_single_active(require_db, clean_packages):
    suffix = uuid.uuid4().hex[:8]
    name = f"QA ProductOnly {suffix}"
    pkg = create_package(name, PACKAGE_TYPE_FSSAI, ["moisture"], ["total_ash"])
    clean_packages.append(pkg.id)

    resolved = resolve_package_for_product(name)
    assert resolved is not None
    assert resolved.package_id == pkg.id
    assert set(resolved.test_keys) == {"moisture", "total_ash"}

    desc = describe_sample_package_for_product(name)
    assert desc["status"] == "defined"
    assert len(desc["test_keys"]) == 2


def test_resolve_package_for_product_duplicate(require_db, clean_packages):
    suffix = uuid.uuid4().hex[:8]
    name = f"QA Dup {suffix}"
    pkg1 = create_package(name, PACKAGE_TYPE_FSSAI, ["moisture"], [])
    clean_packages.append(pkg1.id)
    delete_package(pkg1.id, "QA setup duplicate test")
    pkg2 = create_package(name, PACKAGE_TYPE_BASIC_NUTRITION, ["bn_protein"], [])
    clean_packages.append(pkg2.id)

    from db.connection import get_db

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE sample_test_packages SET is_active = TRUE WHERE id = %s",
                (pkg1.id,),
            )

    assert resolve_package_for_product(name) is None
    desc = describe_sample_package_for_product(name)
    assert desc["status"] == "duplicate"
    assert desc["active_count"] >= 2
    assert len(desc.get("duplicate_package_ids") or []) >= 2

