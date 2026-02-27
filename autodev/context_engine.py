"""Lightweight code index and context selector for codebase-aware operations.

Uses only Python stdlib (ast, os, re) — no external dependencies.
Provides symbol/import extraction for Python (via ast), TypeScript, and Go (via regex).
"""

from __future__ import annotations

import ast
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .workspace import Workspace


@dataclass
class SymbolInfo:
    """A named symbol (class, function, constant) found in a source file."""

    name: str
    kind: str  # "class", "function", "constant", "import"
    file: str
    line: int
    docstring: str | None = None


@dataclass
class FileMetadata:
    """Parsed metadata for a single source file."""

    path: str
    size: int
    symbols: list[SymbolInfo] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    language: str = "unknown"


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

_LANGUAGE_MAP: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
}


def _detect_language(path: str) -> str:
    _, ext = os.path.splitext(path)
    return _LANGUAGE_MAP.get(ext.lower(), "unknown")


# ---------------------------------------------------------------------------
# Python parser (ast-based)
# ---------------------------------------------------------------------------


def _extract_import_names_from_node(node: ast.AST) -> list[str]:
    """Extract module names from an Import or ImportFrom node."""
    names: list[str] = []
    if isinstance(node, ast.Import):
        for alias in node.names:
            names.append(alias.name)
    elif isinstance(node, ast.ImportFrom):
        module = node.module or ""
        if module:
            names.append(module)
    return names


def _get_docstring(node: ast.AST) -> str | None:
    """Extract docstring from a function/class node, truncated."""
    try:
        ds = ast.get_docstring(node)  # type: ignore[arg-type]
        if ds and len(ds) > 120:
            return ds[:117] + "..."
        return ds
    except Exception:
        return None


def _parse_python(path: str, source: str) -> FileMetadata:
    """Parse a Python file using the ast module."""
    symbols: list[SymbolInfo] = []
    imports: list[str] = []
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return FileMetadata(path=path, size=len(source), language="python")

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(
                SymbolInfo(
                    name=node.name,
                    kind="function",
                    file=path,
                    line=node.lineno,
                    docstring=_get_docstring(node),
                )
            )
        elif isinstance(node, ast.ClassDef):
            symbols.append(
                SymbolInfo(
                    name=node.name,
                    kind="class",
                    file=path,
                    line=node.lineno,
                    docstring=_get_docstring(node),
                )
            )
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.extend(_extract_import_names_from_node(node))

    # Deduplicate imports while preserving order
    seen: set[str] = set()
    unique_imports: list[str] = []
    for imp in imports:
        if imp not in seen:
            seen.add(imp)
            unique_imports.append(imp)

    return FileMetadata(
        path=path,
        size=len(source),
        symbols=symbols,
        imports=unique_imports,
        language="python",
    )


# ---------------------------------------------------------------------------
# TypeScript parser (regex-based)
# ---------------------------------------------------------------------------

_TS_EXPORT_RE = re.compile(
    r"^\s*export\s+(?:default\s+)?(?:abstract\s+)?"
    r"(?:class|function|const|let|var|interface|type|enum)\s+(\w+)",
    re.MULTILINE,
)
_TS_IMPORT_RE = re.compile(
    r"""import\s+.*?\s+from\s+['"]([^'"]+)['"]""",
    re.MULTILINE,
)


def _parse_typescript(path: str, source: str) -> FileMetadata:
    """Parse a TypeScript/JavaScript file using regex."""
    symbols: list[SymbolInfo] = []
    imports: list[str] = []

    for m in _TS_EXPORT_RE.finditer(source):
        line = source[: m.start()].count("\n") + 1
        symbols.append(SymbolInfo(name=m.group(1), kind="export", file=path, line=line))

    for m in _TS_IMPORT_RE.finditer(source):
        imports.append(m.group(1))

    return FileMetadata(
        path=path,
        size=len(source),
        symbols=symbols,
        imports=list(dict.fromkeys(imports)),
        language=_detect_language(path),
    )


# ---------------------------------------------------------------------------
# Go parser (regex-based)
# ---------------------------------------------------------------------------

_GO_FUNC_RE = re.compile(r"^func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\(", re.MULTILINE)
_GO_TYPE_RE = re.compile(r"^type\s+(\w+)\s+(?:struct|interface)\b", re.MULTILINE)
_GO_IMPORT_RE = re.compile(r'"([^"]+)"')


def _parse_go(path: str, source: str) -> FileMetadata:
    """Parse a Go file using regex."""
    symbols: list[SymbolInfo] = []
    imports: list[str] = []

    for m in _GO_FUNC_RE.finditer(source):
        line = source[: m.start()].count("\n") + 1
        symbols.append(SymbolInfo(name=m.group(1), kind="function", file=path, line=line))

    for m in _GO_TYPE_RE.finditer(source):
        line = source[: m.start()].count("\n") + 1
        symbols.append(SymbolInfo(name=m.group(1), kind="type", file=path, line=line))

    # Locate import blocks
    import_block_re = re.compile(r"^import\s*\((.*?)\)", re.MULTILINE | re.DOTALL)
    import_single_re = re.compile(r'^import\s+"([^"]+)"', re.MULTILINE)
    for m in import_block_re.finditer(source):
        for im in _GO_IMPORT_RE.finditer(m.group(1)):
            imports.append(im.group(1))
    for m in import_single_re.finditer(source):
        imports.append(m.group(1))

    return FileMetadata(
        path=path,
        size=len(source),
        symbols=symbols,
        imports=list(dict.fromkeys(imports)),
        language="go",
    )


# ---------------------------------------------------------------------------
# CodeIndex
# ---------------------------------------------------------------------------

# Max source bytes to read for parsing (skip very large generated files)
_MAX_PARSE_BYTES = 256_000


class CodeIndex:
    """Lightweight code index using Python ast module for Python files
    and regex for TypeScript/Go files."""

    def __init__(self, ws: "Workspace"):
        self.ws = ws
        self._files: dict[str, FileMetadata] = {}
        self._symbol_map: dict[str, list[SymbolInfo]] = defaultdict(list)
        self._import_map: dict[str, list[str]] = defaultdict(list)  # module → [importers]

    @property
    def files(self) -> dict[str, FileMetadata]:
        return self._files

    def scan(self, max_files: int = 500) -> None:
        """Scan workspace and build index."""
        context_files = self.ws.list_context_files(max_files=max_files)
        for rel_path in context_files:
            lang = _detect_language(rel_path)
            if lang == "unknown":
                continue
            try:
                source = self.ws.read_text(rel_path)
            except Exception:
                continue
            if len(source) > _MAX_PARSE_BYTES:
                continue

            meta: FileMetadata
            if lang == "python":
                meta = _parse_python(rel_path, source)
            elif lang in ("typescript", "javascript"):
                meta = _parse_typescript(rel_path, source)
            elif lang == "go":
                meta = _parse_go(rel_path, source)
            else:
                continue

            self._files[rel_path] = meta

            # Build symbol map
            for sym in meta.symbols:
                self._symbol_map[sym.name].append(sym)

            # Build import map (module → files that import it)
            for imp in meta.imports:
                self._import_map[imp].append(rel_path)

    def find_symbol(self, name: str) -> list[SymbolInfo]:
        """Find all definitions of a symbol by name."""
        return list(self._symbol_map.get(name, []))

    def find_importers(self, module: str) -> list[str]:
        """Find all files that import a given module."""
        results: list[str] = []
        for key, files in self._import_map.items():
            # Match exact module name or submodule
            if key == module or key.startswith(module + ".") or module.startswith(key + "."):
                results.extend(files)
        return list(dict.fromkeys(results))

    def file_summary(self, path: str) -> str:
        """One-line summary: symbols, size, imports count."""
        meta = self._files.get(path)
        if meta is None:
            return f"{path}: <not indexed>"
        sym_names = [s.name for s in meta.symbols[:8]]
        sym_str = ", ".join(sym_names)
        if len(meta.symbols) > 8:
            sym_str += f" (+{len(meta.symbols) - 8} more)"
        return (
            f"{path} ({meta.language}, {meta.size}B, "
            f"{len(meta.symbols)} symbols: [{sym_str}], "
            f"{len(meta.imports)} imports)"
        )

    def structure_summary(self, max_lines: int = 50) -> str:
        """Project structure: dirs, file counts, key patterns."""
        if not self._files:
            return "Empty index (no source files found)."

        # Collect directory stats
        dir_counts: dict[str, int] = defaultdict(int)
        lang_counts: dict[str, int] = defaultdict(int)
        total_symbols = 0
        for meta in self._files.values():
            parent = os.path.dirname(meta.path) or "."
            dir_counts[parent] += 1
            lang_counts[meta.language] += 1
            total_symbols += len(meta.symbols)

        lines: list[str] = []
        lines.append(
            f"Indexed {len(self._files)} files, "
            f"{total_symbols} symbols, "
            f"{len(self._import_map)} unique imports"
        )

        # Language breakdown
        lang_parts = [f"{lang}: {count}" for lang, count in sorted(lang_counts.items())]
        lines.append(f"Languages: {', '.join(lang_parts)}")

        # Directory tree (sorted by file count descending)
        lines.append("Directories:")
        sorted_dirs = sorted(dir_counts.items(), key=lambda x: -x[1])
        for d, count in sorted_dirs[: max_lines - 3]:
            lines.append(f"  {d}/ ({count} files)")

        return "\n".join(lines[:max_lines])


# ---------------------------------------------------------------------------
# ContextSelector
# ---------------------------------------------------------------------------


class ContextSelector:
    """Select relevant context for a task, within a token budget."""

    def __init__(self, index: CodeIndex, ws: "Workspace"):
        self.index = index
        self.ws = ws

    def select_for_task(
        self,
        goal: str,
        seed_files: list[str],
        max_files: int = 15,
        max_chars_per_file: int = 6000,
    ) -> dict[str, str]:
        """Smart context selection:
        1. Start with seed_files (task.files)
        2. Follow imports from seed files (1-hop)
        3. Find files containing symbols referenced in seed files
        4. Rank by relevance (import distance, symbol overlap)
        5. Return within budget
        """
        result: dict[str, str] = {}
        scored: dict[str, float] = {}

        # Phase 1: seed files get highest priority
        for f in seed_files:
            scored[f] = 100.0

        # Phase 2: follow imports from seed files (1-hop)
        for f in seed_files:
            meta = self.index.files.get(f)
            if meta is None:
                continue
            for imp in meta.imports:
                # Find files that define this module
                for candidate in self._resolve_import_to_files(imp):
                    if candidate not in scored:
                        scored[candidate] = 50.0

        # Phase 3: find files that share symbols with seed files
        seed_symbols: set[str] = set()
        for f in seed_files:
            meta = self.index.files.get(f)
            if meta:
                seed_symbols.update(s.name for s in meta.symbols)

        if seed_symbols:
            for sym_name in seed_symbols:
                for sym_info in self.index.find_symbol(sym_name):
                    if sym_info.file not in scored:
                        scored[sym_info.file] = 25.0

        # Phase 4: keyword matching from goal (simple term overlap + prefix)
        if goal:
            goal_terms = set(re.findall(r"\w{3,}", goal.lower()))
            for path, meta in self.index.files.items():
                if path in scored:
                    continue
                file_terms = set()
                # Include file basename as a term
                basename = os.path.splitext(os.path.basename(path))[0].lower()
                file_terms.update(
                    t for t in re.findall(r"[a-z]+", basename) if len(t) >= 3
                )
                for s in meta.symbols:
                    # Convert CamelCase and snake_case to terms
                    file_terms.update(
                        t.lower() for t in re.findall(r"[A-Z][a-z]+|[a-z]+", s.name) if len(t) >= 3
                    )
                # Exact overlap
                overlap = goal_terms & file_terms
                # Prefix-based overlap (e.g. "authentication" matches "authenticate")
                prefix_matches = 0
                for gt in goal_terms:
                    for ft in file_terms:
                        if gt != ft and len(gt) >= 4 and len(ft) >= 4:
                            if gt.startswith(ft[:4]) or ft.startswith(gt[:4]):
                                prefix_matches += 1
                                break
                match_score = len(overlap) * 10.0 + prefix_matches * 5.0
                if match_score > 0:
                    scored[path] = match_score

        # Rank and select top files within budget
        ranked = sorted(scored.items(), key=lambda x: -x[1])

        for path, _score in ranked[:max_files]:
            try:
                if self.ws.exists(path):
                    content = self.ws.read_text(path)
                    result[path] = content[:max_chars_per_file]
                else:
                    result[path] = "<missing>"
            except Exception:
                result[path] = "<unreadable>"

        return result

    def select_for_planner(
        self,
        prd_keywords: list[str],
        max_chars: int = 8000,
    ) -> dict[str, Any]:
        """Provide planner with project structure awareness:
        - Directory tree (summarized)
        - Key files with their symbol lists
        - Existing test structure
        - Detected patterns (framework, db, auth)
        """
        structure = self.index.structure_summary(max_lines=30)

        # Key files: those with most symbols, likely core modules
        key_files: list[dict[str, Any]] = []
        sorted_files = sorted(
            self.index.files.values(),
            key=lambda m: len(m.symbols),
            reverse=True,
        )
        chars_used = len(structure)
        for meta in sorted_files[:20]:
            entry: dict[str, Any] = {
                "path": meta.path,
                "language": meta.language,
                "symbols": [
                    {"name": s.name, "kind": s.kind}
                    for s in meta.symbols[:15]
                ],
                "imports": meta.imports[:10],
            }
            entry_size = len(str(entry))
            if chars_used + entry_size > max_chars:
                break
            key_files.append(entry)
            chars_used += entry_size

        # Detect patterns
        patterns = self._detect_patterns()

        # Test structure
        test_files = [
            p for p in self.index.files
            if "test" in p.lower() or p.startswith("tests/")
        ]

        return {
            "structure": structure,
            "key_files": key_files,
            "test_files": test_files[:20],
            "detected_patterns": patterns,
            "total_indexed_files": len(self.index.files),
        }

    def _resolve_import_to_files(self, module: str) -> list[str]:
        """Resolve an import module name to indexed file paths."""
        candidates: list[str] = []

        # Try direct path mapping: 'src.models' → 'src/models.py'
        module_path = module.replace(".", "/")
        for suffix in (".py", "/index.ts", "/index.js", ".ts", ".js", ".go"):
            candidate = module_path + suffix
            if candidate in self.index.files:
                candidates.append(candidate)

        # Also check __init__.py for packages
        init_candidate = module_path + "/__init__.py"
        if init_candidate in self.index.files:
            candidates.append(init_candidate)

        return candidates

    def _detect_patterns(self) -> list[str]:
        """Detect common framework/library patterns in the codebase."""
        patterns: list[str] = []
        all_imports: set[str] = set()
        for meta in self.index.files.values():
            all_imports.update(meta.imports)

        pattern_checks: list[tuple[str, list[str]]] = [
            ("fastapi", ["fastapi"]),
            ("flask", ["flask"]),
            ("django", ["django"]),
            ("sqlalchemy", ["sqlalchemy"]),
            ("pytest", ["pytest"]),
            ("asyncio", ["asyncio"]),
            ("pydantic", ["pydantic"]),
            ("httpx", ["httpx"]),
            ("requests", ["requests"]),
            ("celery", ["celery"]),
            ("redis", ["redis"]),
            ("docker", ["docker"]),
        ]
        for pattern_name, modules in pattern_checks:
            if any(m in all_imports for m in modules):
                patterns.append(pattern_name)

        return patterns
