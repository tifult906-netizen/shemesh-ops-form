"""`python -m shemesh_ops.web` — launches uvicorn."""
from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.environ.get("SHEMESH_HOST", "127.0.0.1")
    port = int(os.environ.get("SHEMESH_PORT", "8000"))
    uvicorn.run("shemesh_ops.web.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
