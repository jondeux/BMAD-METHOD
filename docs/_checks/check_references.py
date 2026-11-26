#!/usr/bin/env python3
"""Check local file, source line, and explicit Python symbol references in Markdown."""

import argparse
import ast
import re
from functools import cache
from pathlib import Path
from urllib.parse import unquote, urlsplit

DOCS = ("docs", "claude", ".claude")
ROOTS = {"docs", "docs-site", "skills", "tools", "claude", ".claude", ".github", ".ai-context"}
LINK = re.compile(r"\[(?P<label>[^\]]*)\]\(\s*(?:<(?P<angle>[^>]+)>|(?P<url>[^)\s]+))")
DEFINITION = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*(?:<(?P<angle>[^>]+)>|(?P<url>\S+))")
TICK = re.compile(r"\x60([^\x60]+)\x60")
FILE_LINE = re.compile(r"(?<![\w/:.])((?:[\w./-]+/)?[\w.-]+\.\w+:\d+(?::\d+)?)(?![\d:/])")
LOCATION = re.compile(r"([^:]+):(\d+)(?::\d+)?$")
LINE_ANCHOR = re.compile(r"L(\d+)(?:-L(\d+))?$")
SYMBOL = re.compile(r"[a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*)*")
FENCE = re.compile(r"^\s{0,3}(\x60{3,}|~{3,})")
EXAMPLE = re.compile(r"<!-- freshness-example:\s*([^ ]+)\s*-->")
ROOT_PATH = re.compile(rf"(?<![\w./:@])(?:{'|'.join(re.escape(name) for name in sorted(ROOTS))})/[\w./-]+")


def documents(root):
    for name in ("README.md", "AGENTS.md", "CLAUDE.md"):
        path = root / name
        if path.is_file() and path.resolve().is_relative_to(root):
            yield path
    for name in DOCS:
        for path in sorted((root / name).rglob("*")):
            if path.suffix in {".md", ".mdx"} and path.is_file() and path.resolve().is_relative_to(root):
                yield path


def prose_lines(contents):
    contents = re.sub(r"<!--.*?-->", lambda m: "\n" * m[0].count("\n"), contents, flags=re.S)
    fence = ""
    for number, line in enumerate(contents.splitlines(), 1):
        mark = FENCE.match(line)
        if fence:
            if mark and mark[1].startswith(fence) and not line[mark.end() :].strip():
                fence = ""
        elif mark:
            fence = mark[1]
        else:
            yield number, line


def references(line):
    def link(match):
        return match["angle"] or match["url"]

    for match in LINK.finditer(line):
        yield link(match), match["label"], False
    line = LINK.sub(" ", line)
    definition = DEFINITION.match(line)
    if definition:
        yield link(definition), "", False
        line = line[definition.end() :]
    for match in TICK.finditer(line):
        for token in match[1].split():
            value = token.strip("(),;").rstrip(".")
            if re.fullmatch(r"[\w./:#-]+", value) and (
                value.split("/", 1)[0] in ROOTS
                or FILE_LINE.fullmatch(value)
                or re.fullmatch(r"[\w./-]+\.py::[\w.]+", value)
            ):
                yield value, "", True
    outside_code = TICK.sub(" ", line)
    for match in FILE_LINE.finditer(outside_code):
        yield match[1], "", True
    outside_lines = FILE_LINE.sub(" ", outside_code)
    for match in ROOT_PATH.finditer(outside_lines):
        path = match[0].rstrip(".")
        if Path(path).suffix and not outside_lines[match.end() :].startswith(("/", "*", "<", "{")):
            yield path, "", True


def target_path(root, document, value, root_first):
    if not value:
        return document
    path = Path(value)
    if path.is_absolute():
        key = value.lstrip("/")
        candidates = [path, root / key, root / "docs" / key, root / "docs-site/public" / key]
        if key.startswith("diagrams/"):
            candidates.append(root / "docs-site/src" / key)
        if key and not Path(key).suffix:
            candidates.extend((root / "docs" / f"{key.rstrip('/')}.md", root / "docs" / key / "index.md"))
    else:
        candidates = [document.parent / path]
        if root_first:
            candidates.insert(0, root / path)
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_relative_to(root) and resolved.exists():
            return resolved
    return None


@cache
def python_symbols(path):
    result = {}

    def gather(nodes, parent=""):
        for node in nodes:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified = f"{parent}.{node.name}" if parent else node.name
                first = min([node.lineno, *[item.lineno for item in node.decorator_list]])
                result.setdefault(qualified, []).append((first, node.end_lineno))
                if isinstance(node, ast.ClassDef):
                    gather(node.body, qualified)

    gather(ast.parse(path.read_text(encoding="utf-8")).body)
    return result


def problem(root, document, reference, title, root_first):
    if (
        reference in ("", "...")
        or reference.startswith(("//", "{", "$", "<"))
        or re.match(r"^[a-zA-Z][\w+.-]*://", reference)
    ):
        return None
    reference, _, symbol = reference.partition("::")
    location = LOCATION.fullmatch(reference)
    fragment = ""
    if location:
        value, first, last = location[1], int(location[2]), int(location[2])
    else:
        try:
            address = urlsplit(reference)
        except ValueError:
            return "invalid link target"
        if address.scheme or address.netloc:
            return None
        value, fragment = unquote(address.path), unquote(address.fragment)
        lines = LINE_ANCHOR.fullmatch(fragment)
        first = int(lines[1]) if lines else None
        last = int(lines[2] or lines[1]) if lines else None
    path = target_path(root, document, value, root_first)
    if path is None:
        return "file or directory does not exist"
    if first is not None:
        if not path.is_file() or first < 1 or last < first:
            return "invalid source line range"
        if last > len(path.read_text(encoding="utf-8", errors="replace").splitlines()):
            return "source line is past the end of the file"
    if path.suffix != ".py":
        return None
    if not symbol and first is None and SYMBOL.fullmatch(fragment):
        symbol = fragment
    if not symbol and first is not None and title.startswith("\x60") and title.endswith("\x60"):
        candidate = title[1:-1].removesuffix("()")
        symbol = candidate if SYMBOL.fullmatch(candidate) else ""
    if not symbol:
        return None
    try:
        definitions = python_symbols(path).get(symbol, [])
    except SyntaxError:
        return "cannot resolve symbols in invalid Python"
    if not definitions:
        return f"Python symbol {symbol} does not exist"
    if first is not None and not any(start <= first <= end for start, end in definitions):
        return f"line does not point to Python symbol {symbol}"
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    files = list(documents(root))
    issues = 0
    for path in files:
        contents = path.read_text(encoding="utf-8")
        raw_lines = contents.splitlines()
        for number, line in prose_lines(contents):
            examples = EXAMPLE.findall(raw_lines[number - 1])
            for item in dict.fromkeys(references(line)):
                if item[0] in examples:
                    continue
                issue = problem(root, path, *item)
                if issue:
                    print(f"{path.relative_to(root)}:{number}: {item[0]}: {issue}")
                    issues += 1
    if issues:
        print(f"{issues} stale reference(s) in {len(files)} checked documents.")
        return 1
    print(f"Freshness check passed for {len(files)} documents.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
