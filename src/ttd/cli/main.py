from cyclopts import App

from ttd.core.services import health

app = App(name="ttd", help="Terminal-native billable ledger.")


@app.default
async def health_cmd() -> None:
    """Check service and database connectivity."""
    result = await health.ping()
    print(f"status: {result['status']}")
    print(f"db: {result['db_path']}")


def main() -> None:
    app()
