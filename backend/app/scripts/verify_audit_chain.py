import asyncio

from app.audit.verifier import run_cli

if __name__ == "__main__":
    asyncio.run(run_cli())
