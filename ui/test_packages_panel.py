"""
ui/test_packages_panel.py
-------------------------
Reception UI for managing versioned Food test packages.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from services.protocols.test_catalog import CATEGORY_FOOD, TEST_CATALOG, list_tests_for_select
from services.test_packages import (
    PACKAGE_TYPE_FSSAI,
    PACKAGE_TYPE_LABELS,
    LABEL_TO_PACKAGE_TYPE,
    activate_package,
    build_current_version_snapshot,
    create_package,
    delete_package,
    diff_package_versions,
    get_package,
    list_package_versions,
    list_packages,
    update_package,
)
from ui.components import edit_reason_field, render_section_title, require_edit_reason


def _catalog_multiselect_options() -> list[tuple[str, str]]:
    return list_tests_for_select(CATEGORY_FOOD)


def _labels_to_keys(selected_labels: list[str]) -> list[str]:
    options = _catalog_multiselect_options()
    label_to_key = {lbl: k for k, lbl in options}
    return [label_to_key[lbl] for lbl in selected_labels if lbl in label_to_key]


def _keys_to_labels(keys: list[str]) -> list[str]:
    options = _catalog_multiselect_options()
    key_to_label = {k: lbl for k, lbl in options}
    return [key_to_label[k] for k in keys if k in key_to_label]


def _render_diff_table(diff_rows: list) -> None:
    if not diff_rows:
        st.info("No tests to compare.")
        return

    rows: list[dict[str, Any]] = []
    for row in diff_rows:
        change = row.change
        if change == "added":
            change_display = "Added"
            css_class = "pkg-diff-added"
        elif change == "removed":
            change_display = "Removed"
            css_class = "pkg-diff-removed"
        else:
            change_display = "—"
            css_class = ""
        rows.append(
            {
                "Test": row.test_name,
                "v A": "✓" if row.in_version_a else "—",
                "v B": "✓" if row.in_version_b else "—",
                "Change": change_display,
                "_class": css_class,
            }
        )

    html_parts = [
        '<table class="pkg-diff-table"><thead><tr>'
        "<th>Test</th><th>v A</th><th>v B</th><th>Change</th>"
        "</tr></thead><tbody>"
    ]
    for r in rows:
        cls = r["_class"]
        tr_class = f' class="{cls}"' if cls else ""
        html_parts.append(
            f"<tr{tr_class}>"
            f"<td>{r['Test']}</td>"
            f"<td>{r['v A']}</td>"
            f"<td>{r['v B']}</td>"
            f"<td>{r['Change']}</td>"
            "</tr>"
        )
    html_parts.append("</tbody></table>")
    st.markdown("".join(html_parts), unsafe_allow_html=True)


def render_test_packages_panel(actor) -> None:
    """Manage Food test packages and compare versions."""
    render_section_title(
        "Sample registration — test packages (Food)",
        "Define the **master test pool** for each product name "
        "(e.g. Paneer, Jaggery, Masala). The union of with-logo and without-logo "
        "lists is the maximum set reception can pick from at intake.",
    )

    packages = list_packages(active_only=False)

    tab_manage, tab_compare = st.tabs(["Manage packages", "Compare versions"])

    with tab_manage:
        _render_manage_tab(actor, packages)

    with tab_compare:
        _render_compare_tab(packages)


def _package_select_label(pkg) -> str:
    status = "" if pkg.is_active else " [inactive]"
    return (
        f"#{pkg.id} — {pkg.sample_product_name} — {pkg.package_type_label} "
        f"(v{pkg.current_version_no}, WL:{len(pkg.test_keys_with_logo)} / "
        f"NWL:{len(pkg.test_keys_without_logo)}){status}"
    )


def _duplicate_product_names(packages: list) -> set[str]:
    """Product names with more than one active package (legacy data)."""
    from collections import Counter

    active_names = [
        (p.sample_product_name or "").strip().lower()
        for p in packages
        if p.is_active and (p.sample_product_name or "").strip()
    ]
    counts = Counter(active_names)
    return {name for name, count in counts.items() if count > 1}


def _render_manage_tab(actor, packages: list) -> None:
    render_section_title(
        "Create package",
        "One active package per **product name**. Define with-logo and without-logo "
        "test lists — reception picks a subset at intake.",
    )
    new_name = st.text_input(
        "Sample product name *",
        key="pkg_new_name",
        placeholder="e.g. Jaggery",
    )
    st.caption(
        "Test type (FSSAI) is stored for legacy compatibility — intake resolves "
        "packages by product name only."
    )
    catalog_options = _catalog_multiselect_options()
    label_options = [lbl for _, lbl in catalog_options]
    new_wl_labels = st.multiselect(
        "With logo tests",
        options=label_options,
        key="pkg_new_tests_wl",
        help="Tests on final reports with lab letterhead (format A or Both).",
    )
    new_nwl_labels = st.multiselect(
        "Without logo tests",
        options=label_options,
        key="pkg_new_tests_nwl",
        help="Tests on final reports without letterhead (format B or Both).",
    )
    overlap = set(new_wl_labels) & set(new_nwl_labels)
    if overlap:
        st.error(
            "A test cannot be in both lists: "
            + ", ".join(sorted(overlap))
        )

    if st.button("Create package", type="primary", key="pkg_create_btn"):
        if overlap:
            st.error("Resolve overlapping tests before creating the package.")
            return
        try:
            wl_keys = _labels_to_keys(new_wl_labels)
            nwl_keys = _labels_to_keys(new_nwl_labels)
            pkg = create_package(
                new_name,
                PACKAGE_TYPE_FSSAI,
                wl_keys,
                nwl_keys,
                actor=actor,
            )
            st.success(
                f"Created **{pkg.display_label}** (v{pkg.current_version_no}, "
                f"WL:{len(pkg.test_keys_with_logo)} / "
                f"NWL:{len(pkg.test_keys_without_logo)} tests)."
            )
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
            name_key = (new_name or "").strip().lower()
            for p in packages:
                if (
                    p.is_active
                    and (p.sample_product_name or "").strip().lower() == name_key
                ):
                    st.info(
                        f"Edit existing package **#{p.id} — {p.sample_product_name}** "
                        "in the list below."
                    )
                    st.session_state["pkg_edit_select"] = _package_select_label(p)
                    break
        except Exception as exc:  # noqa: BLE001
            st.error(str(exc))

    st.divider()
    render_section_title("Existing packages")

    if not packages:
        st.info("No packages yet. Create one above.")
        return

    dup_names = _duplicate_product_names(packages)
    if dup_names:
        st.warning(
            "Duplicate active packages detected for: "
            + ", ".join(sorted(dup_names))
            + ". Deactivate extras — only one active package per product name is allowed. "
            "Run `scripts/migrate_dedupe_packages.sql` if needed."
        )

    list_rows = [
        {
            "ID": p.id,
            "Product": p.sample_product_name,
            "Type": p.package_type_label,
            "Version": p.current_version_no,
            "WL": len(p.test_keys_with_logo),
            "NWL": len(p.test_keys_without_logo),
            "Active": "Yes" if p.is_active else "No",
            "Dup?": (
                "Yes"
                if p.is_active
                and (p.sample_product_name or "").strip().lower() in dup_names
                else ""
            ),
        }
        for p in packages
    ]
    st.dataframe(list_rows, use_container_width=True, hide_index=True)

    pkg_labels = [_package_select_label(p) for p in packages]
    if not pkg_labels:
        return

    selected_label = st.selectbox("View / edit package", options=pkg_labels, key="pkg_edit_select")
    pkg_id = int(selected_label.split("—")[0].strip().lstrip("#"))
    pkg = get_package(pkg_id)
    if pkg is None:
        st.error("Package not found.")
        return

    if not pkg.is_active:
        _render_inactive_package_editor(actor, pkg)
        return

    with st.expander(f"Edit #{pkg.id} — {pkg.display_label}", expanded=True):
        edit_name = st.text_input(
            "Product name",
            value=pkg.sample_product_name,
            key=f"pkg_edit_name_{pkg_id}",
        )
        edit_wl_labels = st.multiselect(
            "With logo tests",
            options=label_options,
            default=_keys_to_labels(pkg.test_keys_with_logo),
            key=f"pkg_edit_tests_wl_{pkg_id}",
        )
        edit_nwl_labels = st.multiselect(
            "Without logo tests",
            options=label_options,
            default=_keys_to_labels(pkg.test_keys_without_logo),
            key=f"pkg_edit_tests_nwl_{pkg_id}",
        )
        edit_overlap = set(edit_wl_labels) & set(edit_nwl_labels)
        if edit_overlap:
            st.error(
                "A test cannot be in both lists: "
                + ", ".join(sorted(edit_overlap))
            )
        edit_reason = edit_reason_field(key=f"pkg_edit_reason_{pkg_id}")

        col_u, col_d = st.columns(2)
        with col_u:
            if st.button("Save changes (new version)", key=f"pkg_save_{pkg_id}"):
                if edit_overlap:
                    st.error("Resolve overlapping tests before saving.")
                    return
                if not require_edit_reason(edit_reason):
                    return
                try:
                    updated = update_package(
                        pkg_id,
                        _labels_to_keys(edit_wl_labels),
                        _labels_to_keys(edit_nwl_labels),
                        edit_reason,
                        sample_product_name=edit_name,
                        actor=actor,
                    )
                    st.success(
                        f"Updated to v{updated.current_version_no} "
                        f"(WL:{len(updated.test_keys_with_logo)} / "
                        f"NWL:{len(updated.test_keys_without_logo)} tests)."
                    )
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(str(exc))
        with col_d:
            del_reason = edit_reason_field(key=f"pkg_del_reason_{pkg_id}")
            if st.button("Deactivate package", key=f"pkg_del_{pkg_id}"):
                if not require_edit_reason(del_reason):
                    return
                try:
                    delete_package(pkg_id, del_reason, actor=actor)
                    st.success("Package deactivated.")
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(str(exc))

        if pkg.test_keys_with_logo:
            st.caption("With logo tests:")
            for key in pkg.test_keys_with_logo:
                name = TEST_CATALOG[key].name if key in TEST_CATALOG else key
                st.write(f"• {name}")
        if pkg.test_keys_without_logo:
            st.caption("Without logo tests:")
            for key in pkg.test_keys_without_logo:
                name = TEST_CATALOG[key].name if key in TEST_CATALOG else key
                st.write(f"• {name}")


def _render_inactive_package_editor(actor, pkg) -> None:
    """Read-only view of an inactive package with activate action."""
    with st.expander(
        f"Inactive #{pkg.id} — {pkg.display_label}",
        expanded=True,
    ):
        st.warning(
            "This package is **deactivated**. Activate it to use at CTR intake "
            "or edit tests (edits require a new version with reason)."
        )
        st.write(f"**Product:** {pkg.sample_product_name}")
        st.write(f"**Type:** {pkg.package_type_label}")
        st.write(f"**Version:** v{pkg.current_version_no}")

        if pkg.test_keys_with_logo:
            st.caption("With logo tests:")
            for key in pkg.test_keys_with_logo:
                name = TEST_CATALOG[key].name if key in TEST_CATALOG else key
                st.write(f"• {name}")
        if pkg.test_keys_without_logo:
            st.caption("Without logo tests:")
            for key in pkg.test_keys_without_logo:
                name = TEST_CATALOG[key].name if key in TEST_CATALOG else key
                st.write(f"• {name}")

        act_reason = edit_reason_field(key=f"pkg_act_reason_{pkg.id}")
        if st.button("Activate package", type="primary", key=f"pkg_act_{pkg.id}"):
            if not require_edit_reason(act_reason):
                return
            try:
                activated = activate_package(pkg.id, act_reason, actor=actor)
                st.success(
                    f"Activated **{activated.display_label}** "
                    f"(v{activated.current_version_no})."
                )
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))


def _render_compare_tab(packages: list) -> None:
    if not packages:
        st.info("Create a package first.")
        return

    pkg_labels = [
        f"#{p.id} — {p.sample_product_name} — {p.package_type_label}"
        for p in packages
    ]
    selected = st.selectbox("Package", options=pkg_labels, key="pkg_compare_select")
    pkg_id = int(selected.split("—")[0].strip().lstrip("#"))
    pkg = get_package(pkg_id)
    if pkg is None:
        return

    versions = list_package_versions(pkg_id, limit=100)
    current_snap = build_current_version_snapshot(pkg_id)
    version_options: list[tuple[str, dict]] = []
    if current_snap:
        version_options.append(
            (f"Current (v{pkg.current_version_no})", current_snap)
        )
    for ver in versions:
        snap = ver.snapshot()
        vn = int(snap.get("version_no") or ver.version_no)
        version_options.append(
            (
                f"v{vn} — {ver.created_at:%Y-%m-%d %H:%M} — {ver.user_name}",
                snap,
            )
        )

    if len(version_options) < 2:
        st.info("Only one version exists. Edit the package to create version history.")
        return

    labels = [v[0] for v in version_options]
    c1, c2 = st.columns(2)
    with c1:
        idx_a = st.selectbox("Version A", options=range(len(labels)), format_func=lambda i: labels[i], key="pkg_ver_a")
    with c2:
        idx_b = st.selectbox("Version B", options=range(len(labels)), format_func=lambda i: labels[i], key="pkg_ver_b", index=min(1, len(labels) - 1))

    snap_a = version_options[idx_a][1]
    snap_b = version_options[idx_b][1]
    diff_rows = diff_package_versions(snap_a, snap_b)

    ver_a_label = labels[idx_a]
    ver_b_label = labels[idx_b]
    st.markdown(f"**Comparing:** {ver_a_label} ↔ {ver_b_label}")
    _render_diff_table(diff_rows)

    added = sum(1 for r in diff_rows if r.change == "added")
    removed = sum(1 for r in diff_rows if r.change == "removed")
    unchanged = sum(1 for r in diff_rows if r.change == "unchanged")
    st.caption(
        f"Summary: {unchanged} unchanged, "
        f"<span class='pkg-diff-added-inline'>{added} added</span>, "
        f"<span class='pkg-diff-removed-inline'>{removed} removed</span>.",
        unsafe_allow_html=True,
    )

    for ver in versions:
        snap = ver.snapshot()
        vn = int(snap.get("version_no") or ver.version_no)
        if vn in (snap_a.get("version_no"), snap_b.get("version_no")):
            with st.expander(f"Version v{vn} — reason & metadata"):
                st.write(f"**Editor:** {ver.user_name}")
                st.write(f"**When:** {ver.created_at}")
                st.write(f"**Reason:** {ver.edit_reason}")
                wl = snap.get("test_keys_with_logo") or []
                nwl = snap.get("test_keys_without_logo") or []
                if wl or nwl:
                    st.write(f"**With logo ({len(wl)}):**")
                    for key in wl:
                        name = TEST_CATALOG[key].name if key in TEST_CATALOG else key
                        st.write(f"• {name}")
                    st.write(f"**Without logo ({len(nwl)}):**")
                    for key in nwl:
                        name = TEST_CATALOG[key].name if key in TEST_CATALOG else key
                        st.write(f"• {name}")
                else:
                    st.write(f"**Tests ({len(snap.get('test_keys') or [])}):**")
                    for key in snap.get("test_keys") or []:
                        name = TEST_CATALOG[key].name if key in TEST_CATALOG else key
                        st.write(f"• {name}")
