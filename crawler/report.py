import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from crawler.crawl import CrawlResult


def format_summary(result: CrawlResult) -> str:
    lines = [f"Discovered {len(result.visited)} device(s), {len(result.links)} link(s)."]
    for facts in result.visited.values():
        lines.append(f"  [{facts.discovered_via_hop}] {facts.name} ({facts.serial}) - {facts.primary_ip4}")
    if result.auth_failed:
        lines.append(f"Auth failed on {len(result.auth_failed)} device(s):")
        for ip, hop in result.auth_failed:
            lines.append(f"  [{hop}] {ip}")
    if result.unreachable:
        lines.append(f"Unreachable: {len(result.unreachable)} device(s):")
        for ip, hop in result.unreachable:
            lines.append(f"  [{hop}] {ip}")
    return "\n".join(lines)


def write_json(result: CrawlResult, interfaces: list, output_dir: Path = Path("output")) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"{timestamp}-discovery.json"
    payload = {
        "devices": [asdict(f) for f in result.visited.values()],
        "interfaces": [asdict(i) for i in interfaces],
        "links": [asdict(link) for link in result.links],
        "auth_failed": [{"ip": ip, "hop": hop} for ip, hop in result.auth_failed],
        "unreachable": [{"ip": ip, "hop": hop} for ip, hop in result.unreachable],
    }
    path.write_text(json.dumps(payload, indent=2))
    return path
