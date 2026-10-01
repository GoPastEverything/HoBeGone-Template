"""Minimal JSON-Schema validator (standard library only).
Supports: type, const, enum, anyOf, properties, required, items, minimum, maximum, pattern, $ref (#/$defs/...).
Enough for the skill's own schemas; not a general implementation."""
import re

_TYPES = {"string": str, "object": dict, "array": list, "boolean": bool}


def _type_ok(v, t):
    if t == "integer":
        return isinstance(v, int) and not isinstance(v, bool)
    if t == "number":
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    if t == "null":
        return v is None
    return isinstance(v, _TYPES[t])


def validate(inst, schema, root=None, path="$"):
    root = root or schema
    errs = []
    if "$ref" in schema:
        ref = schema["$ref"]
        node = root
        for part in ref.lstrip("#/").split("/"):
            node = node[part]
        return validate(inst, node, root, path)
    if "const" in schema and inst != schema["const"]:
        errs.append(f"{path}: expected const {schema['const']!r}")
    if "enum" in schema and inst not in schema["enum"]:
        errs.append(f"{path}: {inst!r} not in {schema['enum']}")
    if "anyOf" in schema:
        if not any(not validate(inst, s, root, path) for s in schema["anyOf"]):
            errs.append(f"{path}: matches none of anyOf")
    if "type" in schema and not _type_ok(inst, schema["type"]):
        errs.append(f"{path}: expected {schema['type']}, got {type(inst).__name__}")
        return errs
    if isinstance(inst, (int, float)) and not isinstance(inst, bool):
        if "minimum" in schema and inst < schema["minimum"]:
            errs.append(f"{path}: {inst} < {schema['minimum']}")
        if "maximum" in schema and inst > schema["maximum"]:
            errs.append(f"{path}: {inst} > {schema['maximum']}")
    if isinstance(inst, str) and "pattern" in schema and not re.search(schema["pattern"], inst):
        errs.append(f"{path}: {inst!r} does not match {schema['pattern']}")
    if isinstance(inst, dict):
        for r in schema.get("required", []):
            if r not in inst:
                errs.append(f"{path}: missing required {r}")
        for k, sub in schema.get("properties", {}).items():
            if k in inst:
                errs.extend(validate(inst[k], sub, root, f"{path}.{k}"))
    if isinstance(inst, list) and "items" in schema:
        for i, v in enumerate(inst):
            errs.extend(validate(v, schema["items"], root, f"{path}[{i}]"))
    return errs
