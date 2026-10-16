#!/usr/bin/env python3
"""Statically inventory automated test assets without executing repository code."""

from __future__ import annotations

import argparse
import ast
import configparser
import fnmatch
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_EXCLUDES = {
    ".git", "node_modules", "bin", "obj", "dist", "build", ".next", ".nuxt",
    "coverage", "vendor", "__pycache__", ".venv", "venv", ".tox",
}
CONFIG_HINTS = {
    "playwright": ("playwright.config.",),
    "jest": ("jest.config.",),
    "cypress": ("cypress.config.", "cypress.json"),
    "vitest": ("vitest.config.",),
    "mocha": (".mocharc", "mocha.opts"),
    "webdriverio": ("wdio.conf.",),
    "protractor": ("protractor.conf.",),
    "testcafe": ("testcafe.config.",),
}
SOURCE_SUFFIXES = {
    ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts", ".cs",
    ".py", ".java", ".kt", ".go", ".rb", ".php", ".rs", ".scala", ".swift",
}
IGNORED_SUFFIXES = {
    ".lock", ".map", ".min.js", ".min.css", ".dll", ".exe", ".pdb", ".so",
    ".dylib", ".class", ".pyc", ".png", ".jpg", ".jpeg", ".gif", ".pdf",
}
JS_FRAMEWORKS = {
    "playwright": ("Playwright", "JavaScript/TypeScript", ["@playwright/test"], r"\b(?:test|expect)\b|\bpage\.(?:goto|click|locator)\b"),
    "jest": ("Jest", "JavaScript/TypeScript", ["jest"], r"\b(?:jest|expect)\b"),
    "cypress": ("Cypress", "JavaScript/TypeScript", ["cypress"], r"\bcy\.(?:visit|request|get|contains)\b"),
    "vitest": ("Vitest", "JavaScript/TypeScript", ["vitest"], r"\b(?:vi|expect)\b"),
    "mocha": ("Mocha", "JavaScript/TypeScript", ["mocha"], r"\b(?:describe|context|it|beforeEach|afterEach)\b"),
    "jasmine": ("Jasmine", "JavaScript/TypeScript", ["jasmine"], r"\b(?:jasmine|expect|fit|xit)\b"),
    "webdriverio": ("WebdriverIO", "JavaScript/TypeScript", ["webdriverio", "@wdio/cli"], r"\b(?:browser|driver)\.(?:url|navigateTo)\b"),
    "selenium-js": ("Selenium WebDriver", "JavaScript/TypeScript", ["selenium-webdriver"], r"\b(?:webdriver|By)\b"),
    "puppeteer": ("Puppeteer", "JavaScript/TypeScript", ["puppeteer"], r"\b(?:puppeteer|page)\.(?:launch|goto)\b"),
    "protractor": ("Protractor", "JavaScript/TypeScript", ["protractor"], r"\b(?:browser\.get|element\(|by\.)"),
    "testcafe": ("TestCafe", "JavaScript/TypeScript", ["testcafe"], r"\b(?:Selector|fixture)\s*\("),
}
DOTNET_FRAMEWORKS = {
    "nunit": ("NUnit", ".NET", ["nunit", "NUnit.Framework"], r"\[(?:Test|TestCase|TestCaseSource|Theory)\b"),
    "xunit": ("xUnit", ".NET", ["xunit", "Xunit"], r"\[(?:Fact|Theory|InlineData|MemberData|ClassData)\b"),
    "mstest": ("MSTest", ".NET", ["MSTest.TestFramework", "Microsoft.VisualStudio.TestTools.UnitTesting"], r"\[(?:TestMethod|DataTestMethod|TestClass|DataRow)\b"),
}
PYTHON_FRAMEWORKS = {
    "pytest": ("pytest", "Python", ["pytest"], r"\bpytest\b"),
}
FRAMEWORKS = {**JS_FRAMEWORKS, **DOTNET_FRAMEWORKS, **PYTHON_FRAMEWORKS}
AUTOMATION_TOOLS = {"selenium-js", "puppeteer"}
PYTEST_CONFIGS = {"pytest.ini", ".pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini"}
SUPPORT_PACKAGES = {
    "react-testing-library": ("React Testing Library", ["@testing-library/react", "react-testing-library"]),
    "angular-testing-library": ("Angular Testing Library", ["@testing-library/angular", "@testing-library/jest-angular"]),
    "enzyme": ("Enzyme", ["enzyme"]),
    "moq": ("Moq", ["Moq"]),
    "nsubstitute": ("NSubstitute", ["NSubstitute"]),
    "fluentassertions": ("FluentAssertions", ["FluentAssertions"]),
    "selenium-dotnet": ("Selenium WebDriver for .NET", ["Selenium.WebDriver"]),
    "playwright-dotnet": ("Microsoft Playwright for .NET", ["Microsoft.Playwright"]),
    "bunit": ("bUnit", ["bunit"]),
}
JS_DECLARATION = re.compile(
    r"(?<![\w.$])(?P<name>test|it|specify|xit|fit|xtest)\b"
    r"(?P<chain>(?:\s*\.\s*(?:skip|only|todo|each|concurrent|fails|cb))*)"
    r"\s*\(",
)
JS_SUITE = re.compile(r"(?<![\w.$])(?:test\s*\.\s*)?(?P<name>describe|context|suite|xdescribe|fdescribe)\b(?P<chain>(?:\s*\.\s*(?:skip|only|each))*)\s*\(")
CS_ATTRIBUTE = re.compile(
    r"\[(?P<attribute>TestMethod|DataTestMethod|Fact|Theory|Test|TestCase|TestCaseSource)"
    r"\b(?P<arguments>[^\]]*)\]",
    re.IGNORECASE,
)
UNKNOWN_DECLARATIONS = {
    ".go": re.compile(r"^\s*func\s+(?P<name>Test\w+)\s*\(", re.MULTILINE),
    ".java": re.compile(r"@\s*Test\b"),
    ".kt": re.compile(r"@\s*Test\b"),
    ".rs": re.compile(r"#\s*\[\s*test\s*\]"),
    ".rb": re.compile(r"^\s*def\s+(?P<name>test_\w*)\b", re.MULTILINE),
}


def _mask_comments(text: str, hash_comments: bool = False) -> str:
    """Replace comments with spaces while retaining string literals and line positions."""
    chars = list(text)
    i, length = 0, len(chars)
    state = "code"
    quote = ""
    while i < length:
        char = chars[i]
        nxt = chars[i + 1] if i + 1 < length else ""
        if state == "code":
            if char in ("'", '"', "`"):
                quote = char * 3 if char in ("'", '"') and text.startswith(char * 3, i) else char
                state = "string"
                i += len(quote) - 1
            elif char == "/" and nxt == "/":
                chars[i] = chars[i + 1] = " "
                i += 1
                state = "line"
            elif char == "/" and nxt == "*":
                chars[i] = chars[i + 1] = " "
                i += 1
                state = "block"
            elif char == "#" and (nxt == "!" or hash_comments):
                chars[i] = " "
                if nxt == "!":
                    chars[i + 1] = " "
                    i += 1
                state = "line"
        elif state == "string":
            if char == "\\":
                i += 1
            elif text.startswith(quote, i):
                state = "code"
                i += len(quote) - 1
        elif state == "line":
            if char == "\n":
                state = "code"
            else:
                chars[i] = " "
        elif state == "block":
            if char == "*" and nxt == "/":
                chars[i] = chars[i + 1] = " "
                i += 1
                state = "code"
            elif char != "\n":
                chars[i] = " "
        i += 1
    return "".join(chars)


def _mask_inactive_csharp(text: str) -> str:
    lines = text.splitlines(keepends=True)
    result: list[str] = []
    inactive_depth = 0
    for line in lines:
        directive = re.match(r"\s*#\s*(if|else|elif|endif)\b(.*)", line)
        if directive:
            command, expression = directive.group(1), directive.group(2).strip()
            if command == "if" and expression.lower() in {"false", "0"}:
                inactive_depth += 1
            elif command == "endif" and inactive_depth:
                inactive_depth -= 1
            elif command in {"else", "elif"} and inactive_depth:
                inactive_depth -= 1
            result.append("".join("\n" if c == "\n" else " " for c in line))
        elif inactive_depth:
            result.append("".join("\n" if c == "\n" else " " for c in line))
        else:
            result.append(line)
    return "".join(result)


def _mask_strings(text: str) -> str:
    chars = list(text)
    i = 0
    quote = ""
    while i < len(chars):
        if not quote:
            if chars[i] in ("'", '"', "`"):
                character = chars[i]
                quote = character * 3 if character in ("'", '"') and text.startswith(character * 3, i) else character
                for offset in range(len(quote)):
                    chars[i + offset] = " "
                i += len(quote) - 1
        else:
            if chars[i] == "\\":
                if chars[i] != "\n":
                    chars[i] = " "
                if i + 1 < len(chars) and chars[i + 1] != "\n":
                    chars[i + 1] = " "
                i += 1
            elif text.startswith(quote, i):
                delimiter_length = len(quote)
                for offset in range(len(quote)):
                    chars[i + offset] = " "
                quote = ""
                i += delimiter_length - 1
            elif chars[i] != "\n":
                chars[i] = " "
        i += 1
    return "".join(chars)


def _matches(path: str, pattern: str) -> bool:
    if fnmatch.fnmatchcase(path, pattern):
        return True
    if "/" not in pattern:
        return any(fnmatch.fnmatchcase(part, pattern) for part in path.split("/"))
    return False


def _include_allows_directory(path: str, patterns: list[str]) -> bool:
    return any(
        _matches(path, pattern)
        or pattern.startswith(path.rstrip("/") + "/")
        or "/" not in pattern
        for pattern in patterns
    )


def _excluded(relative: str, patterns: set[str]) -> bool:
    parts = relative.split("/")
    return any(_matches(relative, pattern) or any(_matches("/".join(parts[:i]), pattern) for i in range(1, len(parts))) for pattern in patterns)


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _walk(root: Path, includes: list[str], excludes: list[str], default_excludes: bool,
          limitations: list[str], excluded_paths: list[str]) -> list[Path]:
    files: list[Path] = []
    explicit_excludes = set(excludes)
    default_patterns = DEFAULT_EXCLUDES if default_excludes else set()
    def record_walk_error(error: OSError) -> None:
        limitations.append(f"Could not inspect directory {error.filename or root}: {error.strerror or error}")

    for current, directories, names in os.walk(root, topdown=True, onerror=record_walk_error, followlinks=False):
        current_path = Path(current)
        relative_dir = current_path.relative_to(root).as_posix()
        if relative_dir == ".":
            relative_dir = ""
        retained: list[str] = []
        for name in sorted(directories):
            candidate = current_path / name
            relative = (Path(relative_dir) / name).as_posix() if relative_dir else name
            if candidate.is_symlink():
                limitations.append(f"Skipped symbolic link: {relative}")
            elif _excluded(relative, explicit_excludes):
                excluded_paths.append(relative)
                continue
            elif _excluded(relative, default_patterns) and not _include_allows_directory(relative, includes):
                excluded_paths.append(relative)
                continue
            else:
                retained.append(name)
        directories[:] = retained
        for name in sorted(names):
            candidate = current_path / name
            relative = (Path(relative_dir) / name).as_posix() if relative_dir else name
            if candidate.is_symlink():
                limitations.append(f"Skipped symbolic link: {relative}")
                continue
            if _excluded(relative, explicit_excludes):
                excluded_paths.append(relative)
                continue
            if _excluded(relative, default_patterns) and not any(_matches(relative, p) for p in includes):
                excluded_paths.append(relative)
                continue
            basename = name.lower()
            context_file = (
                basename == "package.json"
                or basename in PYTEST_CONFIGS
                or candidate.suffix.lower() in {".csproj", ".sln", ".slnx"}
                or any(basename.startswith(config_name) for config_names in CONFIG_HINTS.values() for config_name in config_names)
            )
            if includes and not context_file and not any(_matches(relative, pattern) for pattern in includes):
                continue
            if candidate.suffix.lower() in IGNORED_SUFFIXES or name.endswith((".min.js", ".min.css")):
                continue
            files.append(candidate)
    return sorted(files, key=lambda p: p.relative_to(root).as_posix())


def _nearest_project(path: Path, projects: list[Path], root: Path) -> str | None:
    parents = [path.parent, *path.parent.parents]
    candidates = [project for project in projects if project.parent in parents and _inside(project, root)]
    if not candidates:
        return None
    return max(candidates, key=lambda p: len(p.parts)).relative_to(root).as_posix()


def _line(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _closing(code: str, opening: int) -> int | None:
    pairs = {"(": ")", "[": "]", "{": "}"}
    stack: list[str] = []
    for position in range(opening, len(code)):
        char = code[position]
        if char in pairs:
            stack.append(pairs[char])
        elif char in ")]}":
            if not stack or stack.pop() != char:
                return None
            if not stack:
                return position
    return None


def _js_declaration(match: re.Match[str], code: str, source: str, kind: str) -> dict[str, Any] | None:
    prefix = code[:match.start()].rstrip()
    if prefix.endswith((".", "?.")) or re.search(r"\bfunction\s*\*?\s*$", prefix):
        return None
    # A locally declared helper shadows the conventional global test API.
    name = match.group("name")
    if re.search(rf"\bfunction\s+{name}\s*\(|\b(?:const|let|var)\s+{name}\s*=", code):
        return None
    chain = re.sub(r"\s+", "", match.group("chain"))
    opening = match.end() - 1
    end = _closing(code, opening)
    if end is None:
        return None
    if ".each" in chain:
        next_call = re.match(r"\s*\(", code[end + 1:])
        if not next_call:
            return None
        opening = end + next_call.end()
        end = _closing(code, opening)
        if end is None:
            return None
    literal = re.match(r"""\s*(?P<quote>['"`])(?P<title>(?:\\.|[^\\])*?)(?P=quote)""", source[opening + 1:end], re.S)
    title = literal.group("title") if literal else None
    if title is not None:
        title = re.sub(r"""\\(['"\\`])""", r"\1", title)
        if literal.group("quote") == "`" and "${" in title:
            title = None
    arguments = code[opening + 1:end]
    callback = "=>" in arguments or bool(re.search(r"\bfunction\b", arguments))
    if title is None and not callback:
        return None
    status = (
        "skipped" if ".skip" in chain or name in {"xit", "xtest", "xdescribe"}
        else "todo" if ".todo" in chain or (kind == "test" and not callback)
        else "active"
    )
    parameterized: bool | None = ".each" in chain
    if not parameterized and title is None:
        parameterized = None
    return {
        "kind": kind, "framework": None, "line": _line(source, match.start()),
        "name": title, "status": status, "status_source": "declaration",
        "parameterized": parameterized,
        "body_iteration": bool(re.search(r"\b(?:for|while)\s*\(|\.forEach\s*\(", arguments)),
        "evidence": match.group(0).strip(), "_start": match.start(), "_end": end,
        "_body": arguments,
    }


def _evidence(path: str, line: int | None, detail: str) -> dict[str, Any]:
    return {"file": path, "line": line, "detail": detail}


def _local_setup(code: str, declaration: dict[str, Any],
                 declarations: list[dict[str, Any]]) -> str:
    start = declaration.get("_start")
    if start is None:
        return ""
    suites = [item for item in declarations if item["kind"] == "suite"]
    enclosing = {item["_start"] for item in suites if item["_start"] < start < item["_end"]}
    bodies = []
    for match in re.finditer(r"(?<![\w.$])beforeEach\s*\(", code):
        scope = {item["_start"] for item in suites if item["_start"] < match.start() < item["_end"]}
        if not scope.issubset(enclosing):
            continue
        end = _closing(code, match.end() - 1)
        if end is not None:
            body = code[match.end():end]
            arrow = body.find("=>")
            if arrow >= 0:
                bodies.append(body[arrow + 2:])
    return "\n".join(bodies)


def _pytest_config(content: str, filename: str) -> bool:
    if filename == "pyproject.toml":
        return bool(re.search(r"(?m)^\s*\[tool\.pytest\.ini_options\]\s*(?:#.*)?$", content))
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.read_string(content)
    return parser.has_section("tool:pytest" if filename == "setup.cfg" else "pytest")


def _python_declarations(source: str, path: str, configured: bool,
                         limitations: list[str]) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        limitations.append(f"Invalid Python syntax: {path}:{error.lineno}: {error.msg}")
        return []
    aliases: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            aliases.update({item.asname or item.name: item.name for item in node.names if item.name == "pytest"})
        elif isinstance(node, ast.ImportFrom) and node.module == "pytest" and node.level == 0:
            aliases.update({item.asname or item.name: f"pytest.{item.name}" for item in node.names})
    for node in tree.body:
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            for child in ast.walk(node):
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                    aliases.pop(child.id, None)
    supported = bool(aliases) or configured

    def qualified(node: ast.AST) -> str:
        if isinstance(node, ast.Call):
            return qualified(node.func)
        if isinstance(node, ast.Name):
            return aliases.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            return f"{qualified(node.value)}.{node.attr}"
        return ""

    def marks(nodes: list[ast.stmt]) -> list[ast.AST]:
        result: list[ast.AST] = []
        for node in nodes:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets):
                result.extend(node.value.elts if isinstance(node.value, (ast.List, ast.Tuple)) else [node.value])
        return result

    declarations: list[dict[str, Any]] = []

    def collect(nodes: list[ast.stmt], inherited: list[ast.AST], prefix: str = "") -> None:
        for node in nodes:
            if isinstance(node, ast.ClassDef):
                if node.name.startswith("Test") and not any(
                    isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == "__init__"
                    for child in node.body
                ) and not node.bases:
                    collect(node.body, inherited + node.decorator_list + marks(node.body), node.name + ".")
                continue
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not node.name.startswith("test"):
                continue
            decorators = inherited + node.decorator_list
            names = {qualified(decorator) for decorator in decorators}
            if names & {"pytest.fixture", "pytest.yield_fixture"}:
                continue
            status = "skipped" if "pytest.mark.skip" in names else "unknown" if names & {
                "pytest.mark.skipif", "pytest.mark.xfail"
            } else "active"
            if any(isinstance(child, ast.Call) and qualified(child) in {"pytest.skip", "pytest.xfail"}
                   for statement in node.body for child in ast.walk(statement)):
                if status != "skipped":
                    status = "unknown"
            body = "\n".join(ast.unparse(statement) for statement in node.body)
            declarations.append({
                "kind": "test" if supported else "suspected_test",
                "framework": "pytest" if supported else None,
                "name": prefix + node.name, "line": node.lineno,
                "status": status if supported else "unknown",
                "parameterized": "pytest.mark.parametrize" in names if supported else None,
                "body_iteration": any(isinstance(child, (ast.For, ast.AsyncFor, ast.While, ast.comprehension))
                                      for statement in node.body for child in ast.walk(statement)),
                "evidence": "Python AST test declaration with pytest import/configuration evidence" if supported else "Python AST test-like declaration",
                "_body": _mask_strings(body),
            })

    collect(tree.body, marks(tree.body))
    return declarations


def _framework_entry(key: str, metadata: tuple[str, str, list[str], str], evidence: list[dict[str, Any]],
                     active: bool) -> dict[str, Any]:
    name, language, _, _ = metadata
    return {
        "name": name,
        "language": language,
        "confidence": "confirmed" if active else "probable",
        "status": "active" if active else "declared",
        "evidence": evidence,
        "test_files": [],
        "test_definition_count": 0,
    }


def _scan(root_arg: str, output_arg: str | None, includes: list[str], excludes: list[str],
          default_excludes: bool, verbose: bool) -> tuple[Path, Path]:
    supplied_root = Path(root_arg).expanduser()
    if not supplied_root.exists():
        raise ValueError(f"Repository path does not exist: {root_arg}")
    if not supplied_root.is_dir():
        raise ValueError(f"Repository path is not a directory: {root_arg}")
    root = supplied_root.resolve(strict=True)
    if not os.access(root, os.R_OK):
        raise ValueError(f"Repository directory is not readable: {root}")

    if output_arg:
        output_dir = Path(output_arg).expanduser().resolve()
    else:
        digest = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:12]
        output_dir = (Path(tempfile.gettempdir()) / "repository-test-inventory" / digest).resolve()
    if _inside(output_dir, root):
        raise ValueError("Output directory must be outside the scanned repository.")

    limitations: list[str] = []
    excluded_paths: list[str] = []
    paths = _walk(root, includes, excludes, default_excludes, limitations, excluded_paths)
    texts: dict[str, str] = {}
    manifest_frameworks: dict[str, list[dict[str, Any]]] = {}
    supporting: dict[str, list[dict[str, Any]]] = {}
    package_framework_keys: dict[str, set[str]] = {}
    config_framework_keys: dict[str, set[str]] = {}
    projects = [path for path in paths if path.suffix.lower() == ".csproj"]
    solutions = [path for path in paths if path.suffix.lower() in {".sln", ".slnx"}]
    for path in paths:
        relative = path.relative_to(root).as_posix()
        basename = path.name.lower()
        is_runner_config = any(
            basename.startswith(config_name)
            for config_names in CONFIG_HINTS.values()
            for config_name in config_names
        )
        if path.suffix.lower() not in SOURCE_SUFFIXES | {".csproj", ".sln", ".slnx"} and path.name != "package.json" and basename not in PYTEST_CONFIGS and not is_runner_config:
            continue
        try:
            if path.stat().st_size > 1_000_000:
                limitations.append(f"Skipped file larger than 1 MB: {relative}")
                continue
            content = path.read_text(encoding="utf-8")
            texts[relative] = content
        except (OSError, UnicodeError) as error:
            limitations.append(f"Could not read {relative}: {error}")

    for relative, content in texts.items():
        lower_path = relative.lower()
        if Path(relative).name.lower() in PYTEST_CONFIGS:
            try:
                if _pytest_config(content, Path(relative).name.lower()):
                    manifest_frameworks.setdefault("pytest", []).append(_evidence(relative, None, "Static pytest configuration section"))
            except configparser.Error as error:
                limitations.append(f"Invalid Python test configuration {relative}: {error}")
        if Path(relative).name == "package.json":
            try:
                manifest = json.loads(content)
            except json.JSONDecodeError as error:
                limitations.append(f"Invalid JSON manifest {relative}: {error.msg} at line {error.lineno}")
                continue
            if not isinstance(manifest, dict):
                limitations.append(f"Invalid JSON manifest {relative}: expected an object")
                continue
            dependencies: dict[str, Any] = {}
            for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                section_value = manifest.get(section, {})
                if isinstance(section_value, dict):
                    dependencies.update(section_value)
            for key, metadata in JS_FRAMEWORKS.items():
                matched = [pkg for pkg in metadata[2] if pkg.lower() in {name.lower() for name in dependencies}]
                if matched:
                    manifest_frameworks.setdefault(key, []).append(_evidence(relative, None, f"Declared package(s): {', '.join(matched)}"))
                    package_framework_keys.setdefault(relative, set()).add(key)
            for key, (label, package_names) in SUPPORT_PACKAGES.items():
                matched = [pkg for pkg in package_names if pkg.lower() in {name.lower() for name in dependencies}]
                if matched:
                    supporting.setdefault(key, []).append(_evidence(relative, None, f"Declared supporting package(s): {', '.join(matched)}"))
        if lower_path.endswith(".csproj"):
            for key, metadata in DOTNET_FRAMEWORKS.items():
                matches = [package for package in metadata[2] if re.search(rf"<PackageReference\b[^>]*\bInclude\s*=\s*['\"]{re.escape(package)}['\"]", content, re.I)]
                if matches:
                    manifest_frameworks.setdefault(key, []).append(_evidence(relative, None, f"Declared package(s): {', '.join(matches)}"))
            for key, (label, package_names) in SUPPORT_PACKAGES.items():
                matches = [package for package in package_names if re.search(rf"<PackageReference\b[^>]*\bInclude\s*=\s*['\"]{re.escape(package)}['\"]", content, re.I)]
                if matches:
                    supporting.setdefault(key, []).append(_evidence(relative, None, f"Declared supporting package(s): {', '.join(matches)}"))
        filename = Path(relative).name.lower()
        for key, config_names in CONFIG_HINTS.items():
            if any(filename.startswith(config_name) for config_name in config_names):
                manifest_frameworks.setdefault(key, []).append(_evidence(relative, None, "Framework configuration file"))
                config_framework_keys.setdefault(relative, set()).add(key)

    active_frameworks: dict[str, dict[str, Any]] = {}
    test_files: list[dict[str, Any]] = []
    all_framework_evidence: dict[str, list[dict[str, Any]]] = {key: list(value) for key, value in manifest_frameworks.items()}
    source_relatives = [rel for rel in texts if Path(rel).suffix.lower() in SOURCE_SUFFIXES]
    for relative in source_relatives:
        raw = texts[relative]
        ext = Path(relative).suffix.lower()
        masked = _mask_comments(raw, hash_comments=ext in {".py", ".rb", ".sh", ".r"})
        if ext == ".cs":
            masked = _mask_inactive_csharp(masked)
        code = _mask_strings(masked)
        imports: list[str] = []
        if ext == ".py":
            parents = [Path(relative).parent, *Path(relative).parent.parents]
            configured = any(Path(e["file"]).parent in parents for e in manifest_frameworks.get("pytest", []))
            declarations = _python_declarations(raw, relative, configured, limitations)
        elif ext == ".cs":
            code = _mask_inactive_csharp(code)
            declarations: list[dict[str, Any]] = []
            csharp_declarations: dict[tuple[int, str], dict[str, Any]] = {}
            for match in CS_ATTRIBUTE.finditer(code):
                attribute = match.group("attribute")
                if attribute.lower() == "theory":
                    project = _nearest_project(root / relative, projects, root)
                    candidates = {
                        framework for framework in ("nunit", "xunit")
                        if any(e["file"] == project for e in manifest_frameworks.get(framework, []))
                    }
                    if re.search(r"\busing\s+Xunit\s*;", code):
                        key = "xunit"
                    elif re.search(r"\busing\s+NUnit\.Framework\s*;", code):
                        key = "nunit"
                    else:
                        key = next(iter(candidates)) if len(candidates) == 1 else None
                    if key is None:
                        limitations.append(f"Ambiguous [Theory] framework: {relative}:{_line(masked, match.start())}")
                        continue
                else:
                    key = next((k for k, (_, _, _, pattern) in DOTNET_FRAMEWORKS.items() if re.fullmatch(pattern, f"[{attribute}]", re.I)), None)
                if not key:
                    key = "nunit" if attribute.lower() in {"test", "testcase", "testcasesource"} else "xunit" if attribute.lower() in {"fact", "theory"} else "mstest"
                following_method = code[match.end():match.end() + 500]
                method = re.search(
                    r"\b(?:public|private|protected|internal)\s+"
                    r"(?:(?:static|async|virtual|override|sealed|new|partial)\s+)*"
                    r"(?:[\w.<>,?\[\]]+\s+)+(?P<name>\w+)\s*\(",
                    following_method,
                )
                if not method:
                    limitations.append(f"Could not resolve attributed test method: {relative}:{_line(masked, match.start())}")
                    continue
                preceding = re.search(r"(?:\[[^\]]*\]\s*)+$", code[:match.start()])
                attributes = (preceding.group(0) if preceding else "") + code[
                    match.start():match.end() + method.start()
                ]
                skipped = bool(re.search(r"\bSkip\s*=|\bIgnore\s*(?:\(|\])", attributes, re.I))
                declaration_offset = match.end() + method.start() if method else match.start()
                declaration_key = (declaration_offset, key)
                method_end = match.end() + method.end()
                opening = code.find("{", method_end)
                expression = code.find("=>", method_end)
                if expression >= 0 and (opening < 0 or expression < opening):
                    end = code.find(";", expression)
                    body = code[expression:end] if end >= 0 else ""
                elif opening >= 0:
                    end = _closing(code, opening)
                    body = code[opening:end] if end is not None else ""
                else:
                    body = ""
                declaration = {
                    "kind": "test",
                    "framework": key,
                    "name": method.group("name"),
                    "line": _line(masked, match.start()),
                    "status": "skipped" if skipped else "active",
                    "parameterized": bool(re.search(r"\b(?:Theory|TestCase|TestCaseSource|DataTestMethod|DataRow|DynamicData)\b", attributes, re.I)),
                    "evidence": f"[{attribute}]",
                    "_body": body,
                }
                existing = csharp_declarations.get(declaration_key)
                if existing:
                    if skipped:
                        existing["status"] = "skipped"
                    if declaration["evidence"] not in existing["evidence"]:
                        existing["evidence"] += ", " + declaration["evidence"]
                else:
                    csharp_declarations[declaration_key] = declaration
            declarations.extend(csharp_declarations.values())
            detected_keys = {d["framework"] for d in declarations}
            for key, (_, _, _, pattern) in DOTNET_FRAMEWORKS.items():
                if re.search(pattern, code, re.I) and key in detected_keys:
                    all_framework_evidence.setdefault(key, []).append(_evidence(relative, None, "Test attribute used in source"))
        elif ext in {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"}:
            declarations = []
            for match in JS_DECLARATION.finditer(code):
                declaration = _js_declaration(match, code, masked, "test")
                if declaration:
                    declarations.append(declaration)
            for match in JS_SUITE.finditer(code):
                declaration = _js_declaration(match, code, masked, "suite")
                if declaration:
                    declarations.append(declaration)
            for declaration in declarations:
                if any(
                    suite["kind"] == "suite" and suite["status"] == "skipped"
                    and suite["_start"] < declaration["_start"] < suite["_end"]
                    for suite in declarations
                ):
                    declaration["status"] = "skipped"
                    declaration["status_source"] = "enclosing_suite"
                if declaration["kind"] == "test" and declaration["status"] != "skipped" and re.search(r"\btest\s*\.\s*(?:skip|fixme)\s*\(", declaration["_body"]):
                    declaration["status"] = "unknown"
                    declaration["status_source"] = "conditional_or_runtime"
        else:
            declarations = []
            unknown_pattern = UNKNOWN_DECLARATIONS.get(ext)
            if unknown_pattern:
                for match in unknown_pattern.finditer(code):
                    declarations.append({
                        "kind": "suspected_test", "framework": None,
                        "name": match.groupdict().get("name"),
                        "line": _line(masked, match.start()), "status": "unknown",
                        "parameterized": None,
                        "evidence": match.group(0).strip() or "Framework-neutral test declaration marker",
                    })

        text_name = Path(relative).name.lower()
        test_like = any(token in text_name for token in ("test", "spec", "checks")) or any(
            part.lower() in {"test", "tests", "__tests__", "spec", "specs"} for part in Path(relative).parts
        )
        if not declarations and (relative in config_framework_keys or text_name in PYTEST_CONFIGS or text_name == "conftest.py"):
            continue
        if not declarations and not test_like:
            continue

        if ext == ".py":
            used_keys = sorted({d["framework"] for d in declarations if d["framework"]})
        elif ext == ".cs":
            used_keys = sorted({item["framework"] for item in declarations if item["kind"] == "test"})
        elif ext in {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"}:
            has_test_declaration = any(item["kind"] == "test" for item in declarations)
            source_path = Path(relative)
            source_parents = [source_path.parent, *source_path.parent.parents]
            local_packages = [
                (len(Path(manifest).parent.parts), keys)
                for manifest, keys in package_framework_keys.items()
                if Path(manifest).parent in source_parents
            ]
            local_configs = [
                (len(Path(config).parent.parts), keys)
                for config, keys in config_framework_keys.items()
                if Path(config).parent in source_parents
            ]
            declared_js: set[str] = set()
            if has_test_declaration and local_packages:
                declared_js.update(max(local_packages, key=lambda item: item[0])[1])
            if has_test_declaration and local_configs:
                declared_js.update(max(local_configs, key=lambda item: item[0])[1])
            for key, metadata in JS_FRAMEWORKS.items():
                if any(re.search(rf"""(?:from\s*|require\s*\()\s*['"]{re.escape(pkg)}['"]""", masked, re.I) for pkg in metadata[2]):
                    imports.append(key)
                    if key in AUTOMATION_TOOLS:
                        all_framework_evidence.setdefault(key, []).append(_evidence(relative, None, "Explicit browser automation tool import"))
            declared_js.difference_update(AUTOMATION_TOOLS)
            if has_test_declaration and imports:
                runners = set(imports) - AUTOMATION_TOOLS
                if not runners:
                    runners = declared_js & {"mocha", "jest", "vitest", "jasmine"}
                used_keys = sorted(runners)
            elif has_test_declaration and len(declared_js) == 1:
                used_keys = sorted(declared_js)
            elif has_test_declaration:
                matched = [
                    key for key, marker in {
                        "jest": r"\bjest\.", "vitest": r"\bvi\.", "cypress": r"\bcy\.",
                        "jasmine": r"\bjasmine\.", "webdriverio": r"\bbrowser\.url\s*\(",
                    }.items() if re.search(marker, code)
                ]
                # Generic assertion and test APIs are not enough to distinguish Jest from Vitest/Mocha.
                used_keys = sorted(matched) if len(matched) == 1 else []
            else:
                used_keys = []
        else:
            used_keys = []
        if ext != ".cs" and used_keys:
            selected = used_keys[0] if len(used_keys) == 1 else None
            for item in declarations:
                if item["kind"] == "test":
                    item["framework"] = selected
        framework_names = []
        for key in used_keys:
            metadata = FRAMEWORKS.get(key)
            if metadata:
                framework_names.append(metadata[0])
                all_framework_evidence.setdefault(key, []).append(_evidence(relative, None, "Recognized test API or attribute"))
        classified, category_evidence = _classify(code, used_keys)
        identities: dict[str, int] = {}
        for declaration in declarations:
            declaration["path"] = relative
            declaration.setdefault("name", None)
            declaration.setdefault("parameterized", None)
            declaration.setdefault("status_source", "declaration")
            body = declaration.pop("_body", "")
            declaration.setdefault("body_iteration", bool(re.search(r"\b(?:for|foreach|while)\s*\(", body)))
            category, evidence = _classify(body, used_keys) if body else ("unknown", [])
            basis = "direct" if evidence else "unknown"
            if category == "unknown" and body and declaration["kind"] == "test":
                setup = _local_setup(code, declaration, declarations)
                if setup and _isolated_assertions((setup + "\n" + body).lower()):
                    category = "unit"
                    evidence = ["Closed local computation/assertions with lexically enclosing beforeEach setup"]
                    basis = "inferred_setup"
            declaration["category"] = category
            declaration["classification_evidence"] = evidence
            declaration["classification_basis"] = basis
            declaration["confidence"] = "confirmed" if declaration.get("framework") else "unknown"
            declaration["tools"] = sorted(set(imports) & {"selenium-js", "puppeteer"})
            identity = f"{relative}::{declaration['kind']}::{declaration['name'] or '@' + str(declaration['line'])}"
            identities[identity] = identities.get(identity, 0) + 1
            declaration["id"] = f"{identity}::{identities[identity]}"
        for declaration in declarations:
            declaration.pop("_start", None)
            declaration.pop("_end", None)
        if ext == ".py":
            categories = {d["category"] for d in declarations}
            classified = next(iter(categories)) if len(categories) == 1 else "unknown"
            category_evidence = sorted({
                evidence for d in declarations for evidence in d["classification_evidence"]
                if d["category"] == classified
            })
        if any(d["kind"] == "suspected_test" for d in declarations):
            limitations.append(f"Unsupported framework syntax retained as suspected declarations: {relative}")
        if len(used_keys) > 1:
            framework_confidence = "probable"
        elif used_keys:
            framework_confidence = "confirmed"
        else:
            framework_confidence = "unknown"
        test_definition_count = sum(1 for item in declarations if item["kind"] == "test")
        test_files.append({
            "path": relative,
            "language": _language(ext),
            "frameworks": framework_names or ["Unknown"],
            "category": classified,
            "confidence": framework_confidence,
            "test_definition_count": test_definition_count,
            "suspected_definition_count": sum(1 for item in declarations if item["kind"] == "suspected_test"),
            "suite_count": sum(1 for item in declarations if item["kind"] == "suite"),
            "skipped_test_count": sum(1 for item in declarations if item["kind"] == "test" and item["status"] == "skipped"),
            "todo_test_count": sum(1 for item in declarations if item["kind"] == "test" and item["status"] == "todo"),
            "definitions": declarations,
            "evidence": [_evidence(relative, item["line"], item["evidence"]) for item in declarations],
            "classification_evidence": category_evidence,
            "test_project": _nearest_project(root / relative, projects, root),
            "suspected": not bool(used_keys),
        })

    for key, evidence in all_framework_evidence.items():
        metadata = FRAMEWORKS.get(key)
        if not metadata:
            continue
        active_files = sorted({item["path"] for item in test_files if any(definition.get("framework") == key for definition in item["definitions"])})
        if not active_files and evidence:
            entry = _framework_entry(key, metadata, evidence, False)
        else:
            entry = _framework_entry(key, metadata, evidence, True)
        entry["test_files"] = active_files
        entry["test_definition_count"] = sum(
            1 for item in test_files for definition in item["definitions"]
            if definition["kind"] == "test" and definition.get("framework") == key
        )
        active_frameworks[key] = entry

    for item in test_files:
        if item["test_project"]:
            continue
        if item["language"] == ".NET" and item["confidence"] == "confirmed":
            item["test_project"] = "(project file not found)"
    test_projects = []
    for project in projects:
        rel = project.relative_to(root).as_posix()
        associated = [item["path"] for item in test_files if item["test_project"] == rel]
        if associated or any(e["file"] == rel for key in ("nunit", "xunit", "mstest") for e in manifest_frameworks.get(key, [])):
            test_projects.append({"path": rel, "test_files": associated, "evidence": "Test source or test framework package reference"})

    summary = {
        "test_file_count": len(test_files),
        "recognized_test_file_count": sum(item["test_definition_count"] > 0 for item in test_files),
        "suspected_test_file_count": sum(item["suspected"] for item in test_files),
        "unknown_framework_file_count": sum(item["frameworks"] == ["Unknown"] for item in test_files),
        "unknown_category_file_count": sum(item["category"] == "unknown" for item in test_files),
        "test_definition_count": sum(item["test_definition_count"] for item in test_files),
        "test_suite_count": sum(item["suite_count"] for item in test_files),
        "explicitly_skipped_test_count": sum(item["skipped_test_count"] for item in test_files),
        "todo_or_pending_test_count": sum(item["todo_test_count"] for item in test_files),
        "unknown_or_unclassified_test_file_count": sum(1 for item in test_files if item["category"] == "unknown" or item["suspected"]),
        "classification_counts": {category: sum(1 for item in test_files if item["category"] == category) for category in ("ui_e2e", "component", "unit", "api", "integration", "unknown")},
        "test_project_count": len(test_projects),
        "framework_count": sum(key not in AUTOMATION_TOOLS for key in active_frameworks),
        "body_iteration_test_count": sum(
            d["kind"] == "test" and d["body_iteration"] for file in test_files for d in file["definitions"]
        ),
        "framework_parameterized_test_count": sum(
            d["kind"] == "test" and d["parameterized"] is True for file in test_files for d in file["definitions"]
        ),
    }
    automation_tools = []
    for key, entry in sorted(active_frameworks.items()):
        if key not in AUTOMATION_TOOLS:
            continue
        uses = [(file, d) for file in test_files for d in file["definitions"]
                if d["kind"] == "test" and key in d["tools"]]
        automation_tools.append({
            "name": entry["name"], "language": entry["language"],
            "confidence": "confirmed" if uses else "probable",
            "status": "used" if uses else "declared",
            "test_files": sorted({file["path"] for file, _ in uses}),
            "associated_definition_count": len(uses),
            "evidence": entry["evidence"],
        })
    scan = {
        "scanner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "source_content_sha256": hashlib.sha256(json.dumps(texts, sort_keys=True).encode("utf-8")).hexdigest(),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "static_read_only",
        "status": "completed_with_limitations" if limitations else "completed",
        "default_exclusions_enabled": default_excludes,
        "include_patterns": includes,
        "exclude_patterns": excludes,
        "excluded_paths": sorted(set(excluded_paths)),
        "files_inspected": len(texts),
        "solutions": [p.relative_to(root).as_posix() for p in solutions],
    }
    languages = sorted({item["language"] for item in test_files if item["language"] != "Unknown"})
    inventory = {
        "schema_version": "1.1",
        "repository": {"path": str(root), "identifier": root.name},
        "scan": scan,
        "languages": languages,
        "frameworks": sorted((entry for key, entry in active_frameworks.items() if key not in AUTOMATION_TOOLS), key=lambda item: item["name"].lower()),
        "automation_tools": automation_tools,
        "supporting_libraries": [
            {"name": SUPPORT_PACKAGES[key][0], "evidence": evidence}
            for key, evidence in sorted(supporting.items())
        ],
        "test_projects": test_projects,
        "test_files": test_files,
        "summary": summary,
        "limitations": sorted(set(limitations)),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / "inventory-report.md"
    json_path = output_dir / "test-inventory.json"
    for report in (md_path, json_path):
        if report.is_symlink() or (report.exists() and report.stat().st_nlink > 1):
            raise ValueError(f"Refusing to overwrite a linked report file: {report}")
    json_path.write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(_render_markdown(inventory), encoding="utf-8")
    if verbose:
        print(f"Inspected {len(texts)} text files; found {len(test_files)} test files.", file=sys.stderr)
    return md_path, json_path


def _language(ext: str) -> str:
    return {
        ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
        ".ts": "TypeScript", ".tsx": "TypeScript", ".mts": "TypeScript", ".cts": "TypeScript",
        ".cs": ".NET", ".py": "Python", ".java": "Java", ".kt": "Kotlin", ".go": "Go",
        ".rb": "Ruby", ".php": "PHP", ".rs": "Rust", ".scala": "Scala", ".swift": "Swift",
    }.get(ext, "Unknown")


def _classify(masked: str, framework_keys: list[str]) -> tuple[str, list[str]]:
    code = masked.lower()
    evidence: list[str] = []
    if re.search(r"\b(?:page|browser|driver)\.(?:goto|navigate|url|get|locator|getby\w+)\b|\bcy\.visit\b|\bselector\s*\(", code):
        evidence.append("Browser automation API")
        return "ui_e2e", evidence
    if re.search(r"@testing-library/(?:react|angular)|\b(?:render|rendercomponent|testcontext)\s*\(", code) or "bunit" in code:
        evidence.append("Component render/testing API")
        return "component", evidence
    if re.search(r"\b(?:request|client|httpclient)\.(?:get|post|put|delete|fetch)\s*\(|\bfetch\s*\(", code):
        evidence.append("HTTP/API request call")
        return "api", evidence
    if re.search(r"\b(?:testserver|webapplicationfactory|testcontainer|databasefixture|integration)\b", code):
        evidence.append("Integration or external-system test indicator")
        return "integration", evidence
    if _isolated_assertions(code):
        return "unit", ["Closed local computation/assertions using recognized standard-library operations"]
    return "unknown", evidence


def _isolated_assertions(code: str) -> bool:
    if not re.search(r"\b(?:expect|assert|assert\.\w+)\b", code):
        return False
    # Require a closed vocabulary: unresolved services, helpers, fixture arguments,
    # side effects and unknown calls must not become unit tests by assertion alone.
    allowed_roots = {
        "expect", "assert", "string", "system", "is", "has", "times",
        "new", "var", "const", "let", "true", "false", "null", "none",
        "throw", "return", "int", "bool", "double", "decimal",
        "dictionary", "list", "invalidoperationexception",
    }
    locals_ = set(re.findall(r"\b(?:var|const|let|string|int|bool|double|decimal)\s+(\w+)\s*=", code))
    locals_.update(re.findall(r"(?<![\w.])([a-z_]\w*)\s*=(?!=|>)", code))
    allowed_methods = {
        "that", "equal", "equalto", "true", "false", "null", "notnull",
        "isempty", "empty", "single", "contains", "containskey", "getvalueordefault",
        "startswith", "endswith", "trim", "tolowerinvariant", "toupperinvariant",
        "isnullorwhitespace", "isnullorempty", "throws",
        "tobe", "toequal", "tobetruthy", "tobefalsy", "tobedefined", "tobenull",
        "tobeundefined", "tobegreaterthan", "tocontain", "tohavelength",
        "tolowercase", "touppercase", "includes", "join",
    }
    for call in re.finditer(r"(?P<member>\.)?\s*(?P<name>[a-z_]\w*)\s*(?:<[^<>]*>)?\s*\(", code):
        name = call.group("name")
        if name not in (allowed_methods if call.group("member") else allowed_roots):
            return False
    roots = re.findall(r"(?<![\w.])([a-z_]\w*)", code)
    return all(name in allowed_roots | locals_ or name in {"length"} for name in roots)


def _render_markdown(data: dict[str, Any]) -> str:
    summary = data["summary"]
    lines = [
        "# Repository Test Inventory", "",
        "## Repository Overview", "",
        f"- Repository: `{data['repository']['path']}`",
        f"- Scan timestamp (UTC): {data['scan']['timestamp_utc']}",
        f"- Scan mode: `{data['scan']['mode']}`",
        f"- Completion status: `{data['scan']['status']}`",
        f"- Languages detected: {', '.join(data['languages']) or 'None'}",
        f"- Frameworks identified: {', '.join(item['name'] for item in data['frameworks']) or 'None'}", "",
        "## Test Inventory Summary", "",
        f"- Test files: {summary['test_file_count']}",
        f"- Files containing recognized declarations: {summary['recognized_test_file_count']}",
        f"- Suspected files: {summary['suspected_test_file_count']}",
        f"- Unknown-framework files: {summary['unknown_framework_file_count']}",
        f"- Unknown-category files: {summary['unknown_category_file_count']}",
        f"- Recognized test definitions: {summary['test_definition_count']}",
        f"- Recognized suites: {summary['test_suite_count']}",
        f"- Framework-parameterized definitions: {summary['framework_parameterized_test_count']}",
        f"- Definitions with body iteration: {summary['body_iteration_test_count']}",
        f"- Test projects: {summary['test_project_count']}",
        f"- Explicitly skipped tests: {summary['explicitly_skipped_test_count']}",
        f"- TODO/pending tests: {summary['todo_or_pending_test_count']}",
        f"- Unknown/unclassified test files: {summary['unknown_or_unclassified_test_file_count']}", "",
        "- Test projects:",
    ]
    if data["test_projects"]:
        lines.extend(
            f"  - `{project['path']}` ({len(project['test_files'])} associated test file(s))"
            for project in data["test_projects"]
        )
    else:
        lines.append("  - None identified.")
    lines.extend([
        "",
        "## Framework Inventory", "",
    ])
    if data["frameworks"]:
        for framework in data["frameworks"]:
            lines.extend([
                f"### {framework['name']}", "",
                f"- Language: {framework['language']}",
                f"- Confidence: `{framework['confidence']}`",
                f"- Status: `{framework['status']}`",
                f"- Test files: {', '.join(f'`{path}`' for path in framework['test_files']) or 'None'}",
                f"- Recognized test definitions: {framework['test_definition_count']}",
                "- Evidence:",
            ])
            lines.extend(f"  - {_format_evidence(evidence)}" for evidence in framework["evidence"])
            lines.append("")
    else:
        lines.extend(["No frameworks identified.", ""])
    lines.extend(["## Browser Automation Tools", ""])
    for tool in data["automation_tools"]:
        lines.extend([
            f"### {tool['name']}", "",
            f"- Status: `{tool['status']}`",
            f"- Test files: {', '.join(tool['test_files']) or 'None'}",
            f"- Associated definitions (not additional tests): {tool['associated_definition_count']}",
            "- Evidence:",
            *[f"  - {_format_evidence(item)}" for item in tool["evidence"]], "",
        ])
    if not data["automation_tools"]:
        lines.extend(["None identified.", ""])
    if data["supporting_libraries"]:
        lines.extend(["### Supporting Libraries", ""])
        for library in data["supporting_libraries"]:
            lines.extend([f"- **{library['name']}**:", *[f"  - {_format_evidence(item)}" for item in library["evidence"]]])
        lines.append("")
    lines.extend(["## Testing Classification", ""])
    for category, count in summary["classification_counts"].items():
        lines.append(f"- {category}: {count}")
    lines.extend(["", "## Test File Inventory", ""])
    if data["test_files"]:
        lines.extend(["| File | Framework | Category | Definitions | Skipped | Confidence |", "|---|---|---:|---:|---:|---|"])
        for item in data["test_files"]:
            lines.append(f"| `{item['path']}` | {', '.join(item['frameworks'])} | {item['category']} | {item['test_definition_count']} | {item['skipped_test_count']} | {item['confidence']} |")
        lines.append("")
        for item in data["test_files"]:
            lines.extend([f"### Evidence: `{item['path']}`", ""])
            lines.extend(f"- {_format_evidence(evidence)}" for evidence in item["evidence"])
            lines.append(f"- Classification: {item['category']} ({', '.join(item['classification_evidence']) or 'insufficient implementation evidence'})")
            lines.append("")
            if item["definitions"]:
                lines.extend([
                    "| Definition | Kind | Category | Basis | Status | Parameterized | Body iteration |",
                    "|---|---|---|---|---|---|---|",
                ])
                for definition in item["definitions"]:
                    name = (definition["name"] or "(dynamic name)").replace("|", "\\|").replace("\n", " ")
                    parameterized = "unknown" if definition["parameterized"] is None else str(definition["parameterized"]).lower()
                    lines.append(
                        f"| {name} | {definition['kind']} | {definition['category']} | "
                        f"{definition['classification_basis']} | {definition['status']} | "
                        f"{parameterized} | {str(definition['body_iteration']).lower()} |"
                    )
                lines.append("")
    else:
        lines.extend(["No test files identified.", ""])
    lines.extend(["## Unknown or Unclassified Assets", ""])
    unknowns = [item for item in data["test_files"] if item["suspected"] or item["category"] == "unknown"]
    lines.extend([
        f"- `{item['path']}`: "
        f"{'unknown framework; ' if item['suspected'] else ''}"
        f"{'unknown category; ' if item['category'] == 'unknown' else ''}"
        f"{item['suspected_definition_count']} suspected declaration site(s)."
        for item in unknowns
    ] or ["None identified."])
    lines.extend(["", "## Scan Limitations", ""])
    lines.extend([f"- {item}" for item in data["limitations"]] or ["- No inaccessible or skipped files were recorded."])
    lines.extend([
        f"- Default exclusions enabled: {data['scan']['default_exclusions_enabled']}.",
        f"- Explicit exclusions: {', '.join(data['scan']['exclude_patterns']) or 'None'}.",
        f"- Excluded paths encountered: {', '.join(f'`{path}`' for path in data['scan']['excluded_paths']) or 'None'}.",
        "- Static pattern analysis cannot resolve arbitrary aliases, generated tests, or runtime-dependent configuration.",
        "- Conditional skip expressions and runner-level excluded test-file patterns are not evaluated.",
        "- Frameworks outside the configured JavaScript/TypeScript, .NET and pytest signatures may remain Unknown.",
        "", "## Evidence", "",
        "Paths are repository-relative; line numbers identify declaration locations. Framework and classification evidence is listed above. Definitions are static declaration counts, not runtime test cases or executions.", "",
    ])
    return "\n".join(lines)


def _format_evidence(item: dict[str, Any]) -> str:
    location = item["file"] + (f":{item['line']}" if item.get("line") else "")
    return f"`{location}` — {item['detail']}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository_path", help="Repository directory to inspect")
    parser.add_argument("--output-directory", help="Report directory outside the repository")
    parser.add_argument("--include", action="append", default=[], help="Repository-relative include pattern (repeatable)")
    parser.add_argument("--exclude", action="append", default=[], help="Repository-relative exclude pattern (repeatable)")
    parser.add_argument("--no-default-excludes", action="store_true", help="Scan normally excluded generated/dependency directories")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    try:
        markdown, structured = _scan(
            args.repository_path, args.output_directory, args.include, args.exclude,
            not args.no_default_excludes, args.verbose,
        )
    except (OSError, ValueError) as error:
        print(f"repository-test-inventory: {error}", file=sys.stderr)
        return 2
    print(f"Markdown report: {markdown}")
    print(f"JSON inventory: {structured}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
