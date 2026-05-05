from __future__ import annotations

import ast
import re
from pathlib import Path


def _module_exists_in_tree(tree_root: Path, top_level_name: str) -> bool:
    return (tree_root / f"{top_level_name}.py").exists() or (tree_root / top_level_name).is_dir()


def _iter_relaymd_import_roots(py_file: Path) -> set[str]:
    tree = ast.parse(py_file.read_text(), filename=str(py_file))
    imports: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("relaymd."):
                    parts = alias.name.split(".")
                    if len(parts) > 1:
                        imports.add(parts[1])
        elif (
            isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("relaymd.")
        ):
            parts = node.module.split(".")
            if len(parts) > 1:
                imports.add(parts[1])

    return imports


def test_build_cli_binary_stages_required_core_modules() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    src_relaymd_root = repo_root / "src" / "relaymd"
    core_relaymd_root = repo_root / "packages" / "relaymd-core" / "src" / "relaymd"
    build_script = repo_root / "scripts" / "build_cli_binary.sh"

    cli_imported_roots: set[str] = set()
    for py_file in (repo_root / "src" / "relaymd").rglob("*.py"):
        cli_imported_roots.update(_iter_relaymd_import_roots(py_file))

    required_core_roots = {
        name
        for name in cli_imported_roots
        if not _module_exists_in_tree(src_relaymd_root, name)
        and _module_exists_in_tree(core_relaymd_root, name)
    }

    script_text = build_script.read_text()
    stages_full_core_package = (
        'packages/relaymd-core/src/relaymd/." "${STAGE_ROOT}/relaymd/' in script_text
    )
    if stages_full_core_package:
        return

    staged_core_roots = set(
        re.findall(r"packages/relaymd-core/src/relaymd/([A-Za-z0-9_]+)(?:\\.py)?", script_text)
    )

    missing = sorted(required_core_roots - staged_core_roots)
    assert not missing, (
        "scripts/build_cli_binary.sh does not stage required relaymd-core modules/packages: "
        + ", ".join(missing)
    )
