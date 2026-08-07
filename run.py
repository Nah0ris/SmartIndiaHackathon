"""Entry point — initialise the database and start the API server."""

import os

import uvicorn
from dotenv import load_dotenv

from db.database import init_db

load_dotenv()

if __name__ == "__main__":
    init_db()

    host = os.getenv("KIRTI_HOST", "0.0.0.0")
    port = int(os.getenv("KIRTI_PORT", "8000"))
    reload = os.getenv("KIRTI_RELOAD", "0") == "1"
    workers = int(os.getenv("KIRTI_WORKERS", "1"))

    uvicorn.run(
        "api.main:app",
        host=host,
        port=port,
        reload=reload,
        workers=workers,
    )
