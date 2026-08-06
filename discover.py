# discover.py
import argparse
import getpass
import logging
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from connectors.cisco.models import Credential
from crawler.crawl import crawl
from crawler.normalize_pipeline import apply_normalization
from crawler.reconcile import reconcile_links
from crawler.interfaces import derive_interfaces
from crawler.report import format_summary, write_json
from crawler.status import RunLogger, RunStatus, write_status


def prompt_credential(label: str = "primary") -> Credential:
    print(f"Enter {label} credentials for device access:")
    username = input("  Username: ")
    password = getpass.getpass("  Password: ")
    return Credential(username=username, password=password)


def confirm(prompt_text: str) -> bool:
    answer = input(f"{prompt_text} (y/n): ").strip().lower()
    return answer == "y"


def git_commit(path: Path) -> None:
    # `output/*.json` is gitignored so throwaway runs don't clutter the repo —
    # force-add the one file the user explicitly confirmed they want kept.
    # The JSON is already safely on disk here, so a git failure degrades to a
    # warning rather than losing a completed crawl to a traceback. That
    # includes git being absent entirely (FileNotFoundError) — the Docker
    # image is built on python:3.12-slim, which ships no git binary, and
    # `.dockerignore` excludes `.git/` so /app isn't a repo there anyway.
    try:
        subprocess.run(["git", "add", "-f", str(path)], check=True)
        subprocess.run(["git", "commit", "-m", f"chore: add discovery run {path.name}"], check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(
            f"Warning: git commit failed: {e}. "
            f"The file is saved at {path} — commit manually if desired."
        )


def archive_log(logger_path: Path, json_path: Path) -> None:
    """Copy this run's live log next to its JSON output, same timestamp, so
    past runs are browsable with both their data and their transcript."""
    if logger_path.exists():
        shutil.copy(logger_path, json_path.with_suffix(".log"))


def _make_progress_handler(seed: str, max_hops: int) -> tuple[Callable[[str, int, str], None], dict]:
    """Builds the on_progress callback passed to crawl(). Returns it along
    with the running-counts dict it updates, so main() can read the final
    counts once crawling finishes. devices_found/auth_failed_count/
    unreachable_count are live-accurate; links_found is not derivable from
    the (ip, hop, status) signal alone and is only known once the crawl
    finishes and result.links is available — main() sets it directly in the
    final idle RunStatus rather than through this callback."""
    counts = {"devices_found": 0, "auth_failed_count": 0, "unreachable_count": 0}
    started_at = datetime.now(timezone.utc).isoformat()

    def on_progress(ip: str, hop: int, status: str) -> None:
        if status == "ok":
            counts["devices_found"] += 1
        elif status == "auth_failed":
            counts["auth_failed_count"] += 1
        elif status == "unreachable":
            counts["unreachable_count"] += 1
        write_status(RunStatus(
            status="running",
            seed=seed,
            max_hops=max_hops,
            started_at=started_at,
            current_hop=hop,
            devices_found=counts["devices_found"],
            auth_failed_count=counts["auth_failed_count"],
            unreachable_count=counts["unreachable_count"],
            last_updated=datetime.now(timezone.utc).isoformat(),
        ))

    return on_progress, counts


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Cisco CDP/LLDP discovery crawler")
    parser.add_argument("--seed", required=True, help="Seed device management IP")
    parser.add_argument("--max-hops", type=int, default=3)
    args = parser.parse_args(argv)

    logger = RunLogger()
    on_progress, counts = _make_progress_handler(args.seed, args.max_hops)

    # Publish "running" before anything slow happens: credential prompting is
    # interactive/unbounded and the first device's RESTCONF-then-SSH fallback
    # can take 30+ seconds, during which on_progress hasn't fired yet and the
    # dashboard would otherwise show a stale previous run's status.
    write_status(RunStatus(
        status="running",
        seed=args.seed,
        max_hops=args.max_hops,
        started_at=datetime.now(timezone.utc).isoformat(),
        last_updated=datetime.now(timezone.utc).isoformat(),
    ))

    credential_sets = [prompt_credential()]
    result = crawl(
        [(args.seed, 0)], max_hops=args.max_hops, credential_sets=credential_sets,
        on_progress=on_progress,
    )
    all_unreachable = list(result.unreachable)

    while result.auth_failed:
        logger.log(f"\n{len(result.auth_failed)} device(s) failed authentication:")
        for ip, hop in result.auth_failed:
            logger.log(f"  [{hop}] {ip}")
        if not confirm("Try alternate credentials on these devices?"):
            break
        credential_sets.append(prompt_credential(label="alternate"))
        result = crawl(
            result.auth_failed,
            max_hops=args.max_hops,
            credential_sets=credential_sets,
            visited=result.visited,
            links=result.links,
            # Carry forward which credentials each host already rejected, so the
            # retry never re-submits a known-bad login (AAA lockout risk) while
            # devices newly discovered during the retry still get every set.
            rejected_credentials=result.rejected_credentials,
            on_progress=on_progress,
        )
        all_unreachable.extend(result.unreachable)

    result.unreachable = all_unreachable
    if result.interrupted:
        logger.log("\nInterrupted — showing what was discovered before the interrupt.")
    apply_normalization(result.visited)
    # Derive interfaces from the RAW link list, before reconciliation: a cable
    # seen from both ends is recorded as two links (A->B and B->A), and
    # derive_interfaces only emits the local ("a") side of each. reconcile_links
    # collapses those two into one, so running it first would silently drop the
    # far-end interface of every both-ends-observed cable.
    interfaces = derive_interfaces(result.links)
    result.links = reconcile_links(result.visited, result.links)

    # Crawling is finished — flip to idle now, before the write/commit
    # prompts, since "running" should mean actively crawling, not waiting
    # on user input.
    write_status(RunStatus(
        status="idle",
        seed=args.seed,
        max_hops=args.max_hops,
        devices_found=len(result.visited),
        links_found=len(result.links),
        auth_failed_count=len(result.auth_failed),
        unreachable_count=len(result.unreachable),
        last_updated=datetime.now(timezone.utc).isoformat(),
    ))

    logger.log("\n" + format_summary(result))

    if confirm("\nWrite this discovery to file?"):
        path = write_json(result, interfaces)
        logger.log(f"Wrote {path}")
        archive_log(logger.path, path)
        git_commit(path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
