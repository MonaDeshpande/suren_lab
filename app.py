"""
app.py
------
S Testing Laboratory — home / launcher (login required).

Workspaces (role-gated):
  - Reception  — Customer Test Request + sample codes
  - Analyst    — protocol worksheets + calculations
  - Reviewer   — review both + generate final Test Report PDF
  - Admin      — register users and assign roles
"""

from __future__ import annotations

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from db.connection import test_connection  # noqa: E402
from db.migrate import ensure_schema  # noqa: E402
from services.auth import ensure_default_admin, get_session_user, roles_display  # noqa: E402
from services.branding import ORGANIZATION_NAME  # noqa: E402
from services.samples import SAMPLE_RETENTION_DAYS, delete_expired_samples  # noqa: E402
from ui.auth import require_login, user_can_access_page  # noqa: E402
from ui.components import inject_styles, render_db_status, render_hero  # noqa: E402


st.set_page_config(
    page_title=ORGANIZATION_NAME,
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _purge_expired_once() -> None:
    """Run sample cleanup once per browser session."""
    if st.session_state.get("_expired_samples_purged"):
        return
    try:
        deleted = delete_expired_samples(actor=get_session_user())
        st.session_state["_expired_samples_purged"] = True
        st.session_state["_expired_samples_deleted"] = deleted
    except Exception:  # noqa: BLE001
        st.session_state["_expired_samples_purged"] = True
        st.session_state["_expired_samples_deleted"] = -1

def main() -> None:
    inject_styles()

    ok, msg = test_connection()
    if ok:
        try:
            ensure_schema()
            ensure_default_admin()
        except Exception:  # noqa: BLE001
            pass

    user = require_login()
    if user is None:
        return

    render_hero(
        title=ORGANIZATION_NAME,
        subtitle=(
            "Signed in as <b>"
            f"{user.full_name or user.username}</b> "
            f"({roles_display(user.roles)}). Open a workspace allowed for your role(s)."
        ),
        badge="Role-based access",
    )

    render_db_status(ok, msg)
    if not ok:
        st.error(
            "Cannot reach PostgreSQL. Start the database with "
            "`docker compose up -d` (port 5433), then refresh."
        )
        st.stop()

    _purge_expired_once()
    deleted = st.session_state.get("_expired_samples_deleted", 0)
    if isinstance(deleted, int) and deleted > 0:
        st.info(
            f"Cleanup: removed {deleted} sample(s) older than "
            f"{SAMPLE_RETENTION_DAYS} days."
        )

    st.markdown("### Workspaces")

    cols = st.columns(2)
    col_idx = 0

    def _next_col():
        nonlocal col_idx
        c = cols[col_idx % 2]
        col_idx += 1
        return c

    if user_can_access_page(user, "reception"):
        with _next_col():
            st.markdown(
                """
                **Reception**
                - Customer Test Request form
                - Permanent customer master (GST)
                - Auto **sample codes** + tests for analyst
                - Filled PDF / Word download
                """
            )
            st.page_link("pages/1_Reception.py", label="Open Reception", icon="📋")

    if user_can_access_page(user, "analyst"):
        with _next_col():
            st.markdown(
                """
                **Analyst**
                - Find sample by lab / sample / client
                - Protocol header + calculation worksheets
                - Protocol PDF / Word
                - Status: Pending → In progress → Completed
                """
            )
            st.page_link("pages/2_Analyst.py", label="Open Analyst", icon="🔬")

    if user_can_access_page(user, "reviewer"):
        with _next_col():
            st.markdown(
                """
                **Reviewer**
                - Review reception intake + analyst results
                - Preview final report fields
                - **Generate Final Report** PDF (QSF 7.8.2)
                """
            )
            st.page_link("pages/3_Reviewer.py", label="Open Reviewer", icon="✅")

    if user_can_access_page(user, "admin"):
        with _next_col():
            st.markdown(
                """
                **Admin**
                - Register staff users
                - Assign / change roles
                - Reset temporary passwords
                - View **audit log** (who / when / what)
                """
            )
            st.page_link("pages/4_Admin.py", label="Open Admin", icon="👤")


if __name__ == "__main__":
    main()
