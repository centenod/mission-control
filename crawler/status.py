# crawler/status.py
import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class RunStatus:
    status: str  # "idle" | "running"
    seed: str | None = None
    max_hops: int | None = None
    started_at: str | None = None
    current_hop: int | None = None
    devices_found: int = 0
    links_found: int = 0
    auth_failed_count: int = 0
    unreachable_count: int = 0
    last_updated: str | None = None


def write_status(status: RunStatus, path: Path = Path("output/.status.json")) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(status), indent=2))


def read_status(path: Path = Path("output/.status.json")) -> RunStatus:
    path = Path(path)
    try:
        data = json.loads(path.read_text())
        return RunStatus(**data)
    except (FileNotFoundError, json.JSONDecodeError, TypeError):
        # A missing or corrupt status file must never break the GUI — idle
        # is always a safe default to show.
        return RunStatus(status="idle")


class RunLogger:
    """Writes each message to stdout (like print) and appends it to a log
    file, so the web GUI can tail exactly what a terminal run would show."""

    def __init__(self, path: Path = Path("output/.current-run.log")):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Truncate any stale log left over from a previous run.
        self.path.write_text("")

    def log(self, message: str) -> None:
        print(message)
        with open(self.path, "a") as f:
            f.write(message + "\n")
