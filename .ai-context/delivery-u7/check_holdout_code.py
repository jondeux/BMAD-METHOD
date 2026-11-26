#!/usr/bin/env python3
"""Exercise the frozen executable checks against a trusted holdout artifact."""

import argparse
import importlib.util
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

VECTORS = {
    "H-CODE": (
        "preview_window",
        {
            "interior": [((1000, 250, 300), (250, 550))],
            "truncate_end": [((1000, 950, 200), (950, 1000))],
            "start_past_end": [((1000, 1300, 50), (1000, 1000))],
            "empty_preview": [((1000, 250, 0), (250, 250))],
        },
    ),
    "H-MIXED": (
        "needs_review",
        {
            "threshold": [((20, 4), True), ((20, 3), False)],
            "empty": [((0, 0), False)],
        },
    ),
}


def matches(actual, expected):
    if type(actual) is not type(expected) or actual != expected:
        return False
    if isinstance(expected, tuple):
        return all(type(value) is int for value in actual)
    return True


def load_function(artifact, name):
    spec = importlib.util.spec_from_file_location("holdout_artifact", artifact.resolve(strict=True))
    if spec is None or spec.loader is None:
        raise ValueError("artifact must be a Python source file")
    module = importlib.util.module_from_spec(spec)
    with redirect_stdout(sys.stderr):
        spec.loader.exec_module(module)
    function = getattr(module, name)
    if not callable(function):
        raise TypeError("the required function is not callable")
    return function


def observe(function, arguments, expected):
    observation = {"arguments": arguments, "expected": repr(expected)}
    try:
        with redirect_stdout(sys.stderr):
            actual = function(*arguments)
            observation.update(observed=repr(actual), passed=matches(actual, expected))
    except Exception as error:
        observation.update(observed=None, passed=False, error_type=type(error).__name__)
    return observation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=VECTORS)
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--check", help="run one original check ID")
    args = parser.parse_args()
    name, vectors = VECTORS[args.case]
    if args.check is not None:
        if args.check not in vectors:
            parser.error(f"unknown check for {args.case}. Choose from {', '.join(vectors)}")
        vectors = {args.check: vectors[args.check]}
    try:
        function = load_function(args.artifact, name)
    except Exception as error:
        print(
            json.dumps(
                [
                    {"id": check_id, "passed": False, "cases": [], "error_type": type(error).__name__}
                    for check_id in vectors
                ]
            )
        )
        return 1
    results = []
    for check_id, invocations in vectors.items():
        observations = [observe(function, arguments, expected) for arguments, expected in invocations]
        results.append({"id": check_id, "passed": all(row["passed"] for row in observations), "cases": observations})
    print(json.dumps(results, indent=2))
    return 0 if all(result["passed"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
