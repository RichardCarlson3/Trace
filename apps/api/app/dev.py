"""Cross-platform entry point with paths independent of the working directory."""

import uvicorn

from app.core.config import API_ROOT, get_settings

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
        reload_dirs=[str(API_ROOT / "app")],
    )
