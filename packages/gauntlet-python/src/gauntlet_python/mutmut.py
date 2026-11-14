"""mutmut's report (`mutmut results --all true`): what its statuses mean, and where a mutant's function is.

The gate only reads results; mutmut itself runs in the sandbox (`gauntlet run`), never on the host.
"""

import ast
from pathlib import Path

from gauntlet.plugin import MutationTool, Where
from gauntlet.safefs import MAX_SOURCE_BYTES, inside, read_text

ROOTS = ("", "src/", "source/")  # mutmut names a module by its path from the project root, less one of these
DEF = (ast.FunctionDef, ast.AsyncFunctionDef)


def _defs(rel: str, prefix: str, body: list[ast.stmt]) -> dict[str, Where]:
    """The functions defined directly in `body`, under mutmut's name for them."""
    return {
        f"{prefix}{node.name}": (rel, node.lineno, node.end_lineno or node.lineno)
        for node in body
        if isinstance(node, DEF)
    }


def _functions(rel: str, text: str) -> dict[str, Where]:
    """mutmut's name for every function and method of the module (`x_f`, `xǁClassǁmethod`) -> where it is."""
    try:
        body = ast.parse(text).body
    except (SyntaxError, ValueError):
        return {}
    found = _defs(rel, "x_", body)
    for node in body:
        if isinstance(node, ast.ClassDef):
            found |= _defs(rel, f"xǁ{node.name}ǁ", node.body)
    return found


def _module(root: Path, module: str) -> dict[str, Where]:
    stem = module.replace(".", "/")
    for rel in (f"{base}{stem}{tail}" for base in ROOTS for tail in (".py", "/__init__.py")):
        path = inside(root, rel)
        if path.is_file():
            return _functions(rel, read_text(path, MAX_SOURCE_BYTES))
    return {}


def locate(names: list[str], root: Path) -> dict[str, Where]:
    """`pkg.mod.x_f__mutmut_3` is in function `f` of pkg/mod.py; a name that points at no function is left out."""
    modules: dict[str, dict[str, Where]] = {}
    found: dict[str, Where] = {}
    for name in names:
        module, _, function = name.rpartition("__mutmut_")[0].rpartition(".")
        if not module:
            continue
        if module not in modules:
            modules[module] = _module(root, module)
        if function in modules[module]:
            found[name] = modules[module][function]
    return found


TOOL = MutationTool(
    artifact="mutmut-results.txt",
    how="mutmut run && mutmut results --all true > mutmut-results.txt (or: gauntlet run)",
    caught=frozenset({"killed", "timeout", "segfault"}),
    ignored=frozenset({"skipped"}),
    never_ran=frozenset({"not checked"}),
    empty="no mutants found; is [tool.mutmut] configured in the target repo?",
    broken=(
        "mutmut checked no mutant: its tests never ran (a failing test or a layout it cannot handle makes it "
        "stop before the first mutant). Run `mutmut run` in the project to see why."
    ),
    locate=locate,
)
