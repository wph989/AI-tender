"""从 FastAPI OpenAPI 生成前端线格式类型。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "apps/web/src/types/api.generated.ts"


def quoted(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def schema_type(schema: dict | bool) -> str:
    if schema is True:
        return "unknown"
    if schema is False:
        return "never"
    if "$ref" in schema:
        return f"ApiSchemas[{quoted(schema['$ref'].rsplit('/', 1)[-1])}]"
    for key in ("anyOf", "oneOf", "allOf"):
        if key in schema:
            join = " & " if key == "allOf" else " | "
            return "(" + join.join(map(schema_type, schema[key])) + ")"
    if "enum" in schema:
        return " | ".join(map(quoted, schema["enum"]))
    if "const" in schema:
        return quoted(schema["const"])
    kind = schema.get("type")
    if kind == "array":
        if "prefixItems" in schema:
            return "[" + ", ".join(map(schema_type, schema["prefixItems"])) + "]"
        return "Array<" + schema_type(schema.get("items", {})) + ">"
    if kind == "object" or "properties" in schema:
        if fields := schema.get("properties"):
            required = set(schema.get("required", []))
            return "{ " + " ".join(
                f"{quoted(name)}{'' if name in required else '?'}: {schema_type(field)};"
                for name, field in sorted(fields.items())
            ) + " }"
        return "Record<string, " + schema_type(schema.get("additionalProperties", True)) + ">"
    if kind not in (None, "integer", "number", "string", "boolean", "null"):
        raise ValueError(f"不支持的 OpenAPI 类型：{kind}")
    return "number" if kind == "integer" else kind or "unknown"


def render(document: dict) -> str:
    lines = [
        "// 由 scripts/generate-api-types.py 从 FastAPI OpenAPI 生成。",
        "export interface ApiSchemas {",
    ]
    for name, schema in sorted(document["components"]["schemas"].items()):
        lines.append(f"  {quoted(name)}: {schema_type(schema)};")
    lines += ["}", "", "export interface ApiPaths {"]
    for path, operations in sorted(document["paths"].items()):
        routes = []
        for method, operation in sorted(operations.items()):
            responses = operation.get("responses", {})
            schemas = [
                data["schema"]
                for code, response in sorted(responses.items()) if code.startswith("2")
                if (data := response.get("content", {}).get("application/json"))
            ]
            if not schemas:
                continue
            response = " | ".join(schema_type(schema) for schema in schemas)
            request = operation.get("requestBody", {}).get("content", {}).get("application/json")
            input_type = f"request: {schema_type(request['schema'])}; " if request else ""
            routes.append(f"    {method}: {{ {input_type}response: {response} }};")
        if routes:
            lines.extend([f"  {quoted(path)}: {{", *routes, "  };"])
    lines += [
        "}",
        "",
        "export type ApiResult<P extends keyof ApiPaths, M extends keyof ApiPaths[P]> =",
        '  ApiPaths[P][M] extends { response: infer R } ? R : never;',
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "apps/api/src"))

    from tender.api.app import app

    current = render(app.openapi())
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != current:
            raise SystemExit("OpenAPI 类型已变化，请运行 scripts/generate-api-types.py 更新生成文件。")
    else:
        OUTPUT.write_text(current, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
