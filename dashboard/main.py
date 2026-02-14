"""AgentDB Dashboard - FastAPI application.

Reads SQLite databases directly via SQLAlchemy ORM.
No dependency on the MCP Server at runtime.

Usage:
    python -m dashboard.main
    # or via entry point:
    agentdb-dashboard

Environment variables:
    AGENTDB_AGENTS_DIR  Path to agents database directory (default: ./agents)
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

from .routes import router as html_router
from .api import router as api_router


def create_app() -> FastAPI:
    app = FastAPI(title="AgentDB Dashboard", version="0.1.0")

    # Jinja2 templates
    templates_dir = Path(__file__).parent / "templates"
    app.state.templates = Jinja2Templates(directory=str(templates_dir))

    # Include routers
    app.include_router(html_router)
    app.include_router(api_router, prefix="/api")

    return app


app = create_app()


def main():
    import uvicorn
    uvicorn.run(
        "dashboard.main:app",
        host="0.0.0.0",
        port=5000,
        reload=True,
    )


if __name__ == "__main__":
    main()
