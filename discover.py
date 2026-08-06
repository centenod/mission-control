# discover.py
import argparse
import getpass
import logging
import subprocess
import sys
from pathlib import Path

from connectors.cisco.models import Credential
from crawler.crawl import crawl
from crawler.normalize_pipeline import apply_normalization
from crawler.reconcile import reconcile_links
from crawler.interfaces import derive_interfaces
from crawler.report import format_summary, write_json


def prompt_credential(label: str = "primary") -> Credential:
    print(f"Enter {label} credentials for device access:")
    username = input("  Username: ")
    password = getpass.getpass("  Password: ")
    return Credential(username=username, password=password)


def confirm(prompt_text: str) -> bool:
    answer = input(f"{prompt_text} (y/n): ").strip().lower()
    return answer == "y"


def git_commit(path: Path) -> None:
    subprocess.run(["git", "add", str(path)], check=True)
    subprocess.run(["git", "commit", "-m", f"chore: add discovery run {path.name}"], check=True)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Cisco CDP/LLDP discovery crawler")
    parser.add_argument("--seed", required=True, help="Seed device management IP")
    parser.add_argument("--max-hops", type=int, default=3)
    args = parser.parse_args(argv)

    credential_sets = [prompt_credential()]
    result = crawl([(args.seed, 0)], max_hops=args.max_hops, credential_sets=credential_sets)
    all_unreachable = list(result.unreachable)

    while result.auth_failed:
        print(f"\n{len(result.auth_failed)} device(s) failed authentication:")
        for ip, hop in result.auth_failed:
            print(f"  [{hop}] {ip}")
        if not confirm("Try alternate credentials on these devices?"):
            break
        credential_sets.append(prompt_credential(label="alternate"))
        result = crawl(
            result.auth_failed,
            max_hops=args.max_hops,
            credential_sets=credential_sets,
            visited=result.visited,
            links=result.links,
        )
        all_unreachable.extend(result.unreachable)

    result.unreachable = all_unreachable
    if result.interrupted:
        print("\nInterrupted — showing what was discovered before the interrupt.")
    apply_normalization(result.visited)
    result.links = reconcile_links(result.visited, result.links)
    interfaces = derive_interfaces(result.links)

    print("\n" + format_summary(result))

    if confirm("\nWrite this discovery to file?"):
        path = write_json(result, interfaces)
        print(f"Wrote {path}")
        git_commit(path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
