"""Classify raw intake and compile catalog selections for local delivery."""

import json
import re
from pathlib import Path

ATTEMPT_VERSION = 2
INTAKE_VERSION = 1
MAX_INPUT_BYTES = 512 * 1024
MAX_TIMEOUT_SECONDS = 86_400
FIELDS = {
    "text",
    "sources",
    "kind",
    "intake_kind",
    "authority",
    "deliverable",
    "checks",
    "budget",
    "timeout_seconds",
    "allowance",
    "route_id",
    "subtype",
    "communication_language",
    "document_output_language",
}
RECEIPT_FIELDS = {"status", "run_id", "attempt", "intake_revision", "route_id"}
CATALOG_PATH = Path(__file__).resolve().parents[1] / "references" / "intake-routes.json"


def read_envelope(path, *, update=False):
    with path.open("rb") as stream:
        data = stream.read(MAX_INPUT_BYTES + 1)
    if len(data) > MAX_INPUT_BYTES:
        raise ValueError("intake exceeds 512 KiB")
    strict_json = update or path.suffix.lower() == ".json"
    try:
        value = json.loads(data)
    except json.JSONDecodeError:
        if strict_json:
            raise
        return {"text": data.decode()}
    if not isinstance(value, dict) and not strict_json:
        return {"text": data.decode()}
    if isinstance(value, str) and not update:
        return {"text": value}
    if not isinstance(value, dict) or value.keys() - FIELDS:
        raise ValueError("intake must be an object with recognized fields")
    return value


def validate_material(envelope):
    if len(json.dumps(envelope, ensure_ascii=False).encode()) > MAX_INPUT_BYTES:
        raise ValueError("intake exceeds 512 KiB")
    if not isinstance(envelope.get("text", ""), str):
        raise ValueError("intake text must be a string")
    sources = envelope.get("sources", [])
    if not isinstance(sources, list):
        raise ValueError("intake sources must be an array")
    ids = set()
    for source in sources:
        if not isinstance(source, dict) or source.keys() - {"id", "excerpt", "readable"}:
            raise ValueError("intake sources accept id, excerpt, and readable")
        source_id = source.get("id")
        if not isinstance(source_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", source_id):
            raise ValueError("intake sources require an opaque ID")
        if source_id in ids:
            raise ValueError("intake source IDs must be unique")
        ids.add(source_id)
        if not isinstance(source.get("excerpt", ""), str) or type(source.get("readable", True)) is not bool:
            raise ValueError("intake sources require text excerpts and boolean readability")
        if source.get("readable") is False and source.get("excerpt"):
            raise ValueError("an unreadable source cannot supply an excerpt")


def material(envelope):
    return {"text": envelope.get("text", ""), "sources": envelope.get("sources", [])}


def canonical_text(envelope):
    source = material(envelope)
    parts = [source["text"]] if source["text"].strip() else []
    parts.extend(f"Source {item['id']}\n{item['excerpt']}" for item in source["sources"])
    return "\n\n".join(parts)


def read_catalog():
    return json.loads(CATALOG_PATH.read_bytes())


def classifier_catalog(catalog):
    return [
        {
            "id": route["id"],
            "when": route["when"],
            "subtypes": [{"id": item["id"], "when": item["when"]} for item in route["subtypes"]],
        }
        for route in catalog["routes"]
    ]


def select(catalog, route_id, subtype):
    route = next((route for route in catalog["routes"] if route["id"] == route_id), None)
    if route is None:
        raise ValueError("unknown intake route ID")
    if subtype is None:
        return route, route["subtypes"][0] if len(route["subtypes"]) == 1 else None
    choice = next((item for item in route["subtypes"] if item["id"] == subtype), None)
    if choice is None:
        raise ValueError("unknown intake subtype for the selected route")
    return route, choice


def classification_receipt(job, route_id, subtype):
    if route_id is None:
        if subtype is not None:
            raise ValueError("a deferred classification cannot name a subtype")
    else:
        select({"routes": job["routes"]}, route_id, subtype)
    result = {
        "status": "ok",
        "run_id": job["run_id"],
        "attempt": job["attempt"],
        "intake_revision": job["intake_revision"],
        "route_id": route_id,
    }
    if subtype is not None:
        result["subtype"] = subtype
    return result


def validate_classification(result, attempt, state, catalog):
    if not isinstance(result, dict) or not RECEIPT_FIELDS <= result.keys() <= RECEIPT_FIELDS | {"subtype"}:
        raise ValueError("classifier receipt must contain only the classification and its binding fields")
    if result["status"] != "ok" or result["run_id"] != state["run_id"]:
        raise ValueError("classifier receipt has the wrong status or run ID")
    if type(result["attempt"]) is not int or result["attempt"] != attempt["number"]:
        raise ValueError("classifier receipt has the wrong attempt")
    revision = result["intake_revision"]
    if type(revision) is not int or revision != attempt["intake_revision"] or revision != state["intake_revision"]:
        raise ValueError("classifier receipt has a stale intake revision")
    if attempt["catalog_version"] != catalog["catalog_version"]:
        raise ValueError("classifier catalog version has changed")
    route_id, subtype = result["route_id"], result.get("subtype")
    if route_id is None and "subtype" not in result:
        return {"route_id": None, "subtype": None, "source": "classifier", "intake_revision": revision}
    if not isinstance(route_id, str) or ("subtype" in result and not isinstance(subtype, str)):
        raise ValueError("classifier receipt requires a route ID and an optional subtype ID")
    select(catalog, route_id, subtype)
    return {"route_id": route_id, "subtype": subtype, "source": "classifier", "intake_revision": revision}
