import sys
import yaml
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from broll_engine.api.app import create_app


def export_openapi() -> None:
    app = create_app()
    openapi_schema = app.openapi()

    # Ensure OpenAPI 3.1.0 declaration
    openapi_schema["openapi"] = "3.1.0"

    output_path = Path(__file__).parent.parent / "openapi.yaml"
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(openapi_schema, f, sort_keys=False, allow_unicode=True)

    print(f"Exported OpenAPI 3.1.0 specification to {output_path}")


if __name__ == "__main__":
    export_openapi()
