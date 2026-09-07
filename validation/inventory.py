"""
Crawl the S_LAB repository into a structured SystemInventory for doc writers.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent

SYSTEM_NAME = "S Testing Laboratory Customer Test Request App"
ORGANIZATION = "S Testing Laboratory"
SYSTEM_VERSION = "1.0"


@dataclass
class PageInfo:
    filename: str
    title: str
    roles: list[str]
    summary: str


@dataclass
class ServiceModule:
    name: str
    path: str
    docstring: str
    public_functions: list[str]


@dataclass
class TableInfo:
    name: str
    columns: list[str]
    comment: str


@dataclass
class LabTestInfo:
    key: str
    name: str
    method: str
    unit: str
    formula_display: str


@dataclass
class TestCaseInfo:
    tc_id: str
    title: str
    priority: str
    tc_type: str
    preconditions: str
    steps: str
    expected: str
    source_file: str


@dataclass
class TraceabilityRow:
    feature: str
    manual_tc_ids: str
    automated: str


@dataclass
class SystemInventory:
    root: Path
    generated_at: str
    roles: list[str] = field(default_factory=list)
    pages: list[PageInfo] = field(default_factory=list)
    services: list[ServiceModule] = field(default_factory=list)
    tables: list[TableInfo] = field(default_factory=list)
    lab_tests: list[LabTestInfo] = field(default_factory=list)
    audit_actions: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    env_keys: list[str] = field(default_factory=list)
    docker_image: str = ""
    docker_host_port: str = ""
    scripts: list[str] = field(default_factory=list)
    migrations: list[str] = field(default_factory=list)
    test_cases: list[TestCaseInfo] = field(default_factory=list)
    traceability: list[TraceabilityRow] = field(default_factory=list)
    features: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _module_docstring(path: Path) -> str:
    try:
        tree = ast.parse(_read_text(path))
        doc = ast.get_docstring(tree) or ""
        return " ".join(doc.strip().split())
    except SyntaxError:
        return ""


def _public_functions(path: Path) -> list[str]:
    try:
        tree = ast.parse(_read_text(path))
    except SyntaxError:
        return []
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                names.append(node.name)
    return names


def _scan_roles(root: Path) -> list[str]:
    auth = root / "services" / "auth.py"
    if not auth.exists():
        return ["admin", "reception", "analyst", "reviewer"]
    text = _read_text(auth)
    m = re.search(r"ROLES\s*=\s*\(([^)]+)\)", text)
    if not m:
        return ["admin", "reception", "analyst", "reviewer"]
    return re.findall(r"['\"](\w+)['\"]", m.group(1))


def _scan_pages(root: Path) -> list[PageInfo]:
    pages_dir = root / "pages"
    results: list[PageInfo] = []
    if not pages_dir.is_dir():
        return results
    for path in sorted(pages_dir.glob("*.py")):
        text = _read_text(path)
        roles = re.findall(r'require_role\(\s*((?:["\']\w+["\']\s*,?\s*)+)\)', text)
        role_list: list[str] = []
        if roles:
            role_list = re.findall(r"['\"](\w+)['\"]", roles[0])
        title_m = re.search(r'title\s*=\s*["\']([^"\']+)["\']', text)
        title = title_m.group(1) if title_m else path.stem.replace("_", " ")
        doc = _module_docstring(path)
        summary = doc.split(".")[0].strip() if doc else path.stem
        results.append(
            PageInfo(
                filename=path.name,
                title=title,
                roles=role_list or ["unknown"],
                summary=summary,
            )
        )
    return results


def _scan_services(root: Path) -> list[ServiceModule]:
    svc = root / "services"
    results: list[ServiceModule] = []
    if not svc.is_dir():
        return results
    for path in sorted(svc.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        rel = path.relative_to(root).as_posix()
        results.append(
            ServiceModule(
                name=path.stem,
                path=rel,
                docstring=_module_docstring(path)[:240],
                public_functions=_public_functions(path),
            )
        )
    return results


def _scan_schema(root: Path, inv: SystemInventory) -> list[TableInfo]:
    schema = root / "db" / "schema.sql"
    if not schema.exists():
        inv.warnings.append("Missing db/schema.sql")
        return []
    text = _read_text(schema)
    tables: list[TableInfo] = []
    # Split on CREATE TABLE blocks
    for m in re.finditer(
        r"CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\((.*?)\);",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    ):
        name = m.group(1)
        body = m.group(2)
        columns: list[str] = []
        for line in body.splitlines():
            line = line.strip().rstrip(",")
            if not line or line.startswith("--"):
                continue
            # skip constraints
            upper = line.upper()
            if upper.startswith(
                ("PRIMARY ", "FOREIGN ", "UNIQUE ", "CHECK ", "CONSTRAINT ", "REFERENCES ")
            ):
                continue
            col = line.split()[0]
            if re.match(r"^[a-zA-Z_]\w*$", col):
                columns.append(col)
        # preceding comment block (last -- lines before table)
        comment = ""
        pos = m.start()
        ahead = text[max(0, pos - 400) : pos]
        comments = re.findall(r"--\s*(.+)", ahead)
        if comments:
            comment = " ".join(c.strip() for c in comments[-3:] if c.strip())
        tables.append(TableInfo(name=name, columns=columns, comment=comment))
    return tables


def _scan_lab_tests(root: Path) -> list[LabTestInfo]:
    catalog = root / "services" / "protocols" / "test_catalog.py"
    if not catalog.exists():
        return []
    text = _read_text(catalog)
    results: list[LabTestInfo] = []
    # Match LabTest( blocks starting with key=
    pattern = re.compile(
        r'LabTest\(\s*'
        r'key\s*=\s*["\'](\w+)["\']\s*,\s*'
        r'name\s*=\s*["\']([^"\']+)["\']\s*,\s*'
        r'method\s*=\s*["\']([^"\']*)["\']\s*,\s*'
        r'unit\s*=\s*["\']([^"\']*)["\']\s*,\s*'
        r'formula_display\s*=\s*["\']([^"\']*)["\']',
        re.DOTALL,
    )
    for m in pattern.finditer(text):
        results.append(
            LabTestInfo(
                key=m.group(1),
                name=m.group(2),
                method=m.group(3),
                unit=m.group(4),
                formula_display=m.group(5),
            )
        )
    return results


def _scan_audit_actions(root: Path) -> list[str]:
    actions: set[str] = set()
    for path in root.rglob("*.py"):
        if "validation" in path.parts:
            continue
        text = _read_text(path)
        # log_from_user(actor, "action.name", ...
        for m in re.finditer(
            r'log_from_user\(\s*[^,]+,\s*["\']([a-zA-Z0-9_.]+)["\']',
            text,
        ):
            actions.add(m.group(1))
    return sorted(actions)


def _scan_dependencies(root: Path) -> list[str]:
    req = root / "requirements.txt"
    if not req.exists():
        return []
    deps: list[str] = []
    for line in _read_text(req).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        deps.append(line)
    return deps


def _scan_env_keys(root: Path) -> list[str]:
    env = root / ".env.example"
    if not env.exists():
        return []
    keys: list[str] = []
    for line in _read_text(env).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        keys.append(line.split("=", 1)[0].strip())
    return keys


def _scan_docker(root: Path) -> tuple[str, str]:
    compose = root / "docker-compose.yml"
    if not compose.exists():
        return "", ""
    text = _read_text(compose)
    image_m = re.search(r"image:\s*(\S+)", text)
    port_m = re.search(r'["\']?(\d+):5432["\']?', text)
    return (
        image_m.group(1) if image_m else "",
        port_m.group(1) if port_m else "",
    )


def _scan_scripts(root: Path) -> tuple[list[str], list[str]]:
    scripts_dir = root / "scripts"
    scripts: list[str] = []
    migrations: list[str] = []
    if not scripts_dir.is_dir():
        return scripts, migrations
    for path in sorted(scripts_dir.iterdir()):
        if path.suffix == ".py":
            scripts.append(path.name)
        elif path.suffix == ".sql" and path.name.startswith("migrate_"):
            migrations.append(path.name)
    return scripts, migrations


def _parse_field_table(block: str, field_name: str) -> str:
    """Extract a markdown table Field|Value row."""
    pat = re.compile(
        rf"\|\s*\*\*{re.escape(field_name)}\*\*\s*\|\s*(.*?)\s*\|",
        re.IGNORECASE,
    )
    m = pat.search(block)
    return (m.group(1).strip() if m else "")


def _scan_test_cases(root: Path) -> list[TestCaseInfo]:
    tc_dir = root / "docs" / "test-cases"
    results: list[TestCaseInfo] = []
    if not tc_dir.is_dir():
        return results
    for path in sorted(tc_dir.glob("*.md")):
        if path.name in ("00_TEST_PLAN.md", "TRACEABILITY.md"):
            continue
        text = _read_text(path)
        # Split on ## TC-...
        parts = re.split(r"(?=^## TC-[A-Z]+-\d+)", text, flags=re.MULTILINE)
        for part in parts:
            hm = re.match(
                r"^##\s+(TC-[A-Z]+-\d+)\s*[—\-–]\s*(.+)$",
                part.strip(),
                flags=re.MULTILINE,
            )
            if not hm:
                continue
            tc_id = hm.group(1).strip()
            title = hm.group(2).strip()
            results.append(
                TestCaseInfo(
                    tc_id=tc_id,
                    title=title,
                    priority=_parse_field_table(part, "Priority"),
                    tc_type=_parse_field_table(part, "Type"),
                    preconditions=_parse_field_table(part, "Preconditions"),
                    steps=_parse_field_table(part, "Steps"),
                    expected=_parse_field_table(part, "Expected"),
                    source_file=path.name,
                )
            )
    return results


def _scan_traceability(root: Path) -> list[TraceabilityRow]:
    path = root / "docs" / "test-cases" / "TRACEABILITY.md"
    if not path.exists():
        return []
    rows: list[TraceabilityRow] = []
    for line in _read_text(path).splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        if cells[0].startswith("---") or cells[0].lower().startswith("feature"):
            continue
        rows.append(
            TraceabilityRow(
                feature=cells[0],
                manual_tc_ids=cells[1],
                automated=cells[2],
            )
        )
    return rows


def _derive_features(inv: SystemInventory) -> list[str]:
    features = [
        "User authentication with bcrypt password hashing",
        "Forced password change for new staff accounts",
        "Role-based access control (up to two roles per user)",
        "Reception Customer Test Request (CTR) intake",
        "Permanent customer master keyed by GST number",
        "Automatic sample codes in format SLS-YYMMDD-NNNN",
        "Analyst protocol worksheets and shared formula catalog",
        "Reviewer Final Test Report PDF (QSF 7.8.2)",
        "Admin user management (create, role, activate, reset password)",
        "Audit trail for meaningful write actions",
        "Generator stamps on CTR / Protocol / Final reports",
        "50-day sample retention with purge",
        "Document generation: CTR PDF/DOCX, Protocol PDF/DOCX, Final Report PDF",
    ]
    for page in inv.pages:
        features.append(f"Workspace page: {page.filename} ({', '.join(page.roles)})")
    for test in inv.lab_tests:
        features.append(f"Lab formula: {test.name} ({test.key})")
    return features


def build_inventory(root: Optional[Path] = None) -> SystemInventory:
    """Scan the repository and return a populated SystemInventory."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    root = (root or PROJECT_ROOT).resolve()
    now = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M %Z")
    inv = SystemInventory(root=root, generated_at=now)

    if not (root / "db" / "schema.sql").exists():
        inv.warnings.append("Critical: db/schema.sql not found")

    inv.roles = _scan_roles(root)
    inv.pages = _scan_pages(root)
    inv.services = _scan_services(root)
    inv.tables = _scan_schema(root, inv)
    inv.lab_tests = _scan_lab_tests(root)
    inv.audit_actions = _scan_audit_actions(root)
    inv.dependencies = _scan_dependencies(root)
    inv.env_keys = _scan_env_keys(root)
    inv.docker_image, inv.docker_host_port = _scan_docker(root)
    inv.scripts, inv.migrations = _scan_scripts(root)
    inv.test_cases = _scan_test_cases(root)
    inv.traceability = _scan_traceability(root)
    inv.features = _derive_features(inv)
    return inv
