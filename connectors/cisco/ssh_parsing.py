from pathlib import Path

import textfsm

from connectors.cisco.models import DeviceFacts, NeighborLink

_TEMPLATE_DIR = Path(__file__).parent / "textfsm_templates"


def _run_template(template_name: str, raw_text: str) -> list[dict]:
    template_path = _TEMPLATE_DIR / template_name
    with open(template_path) as f:
        fsm = textfsm.TextFSM(f)
        rows = fsm.ParseText(raw_text)
    return [dict(zip(fsm.header, row)) for row in rows]


def parse_show_version(raw_text: str, hop: int) -> DeviceFacts:
    rows = _run_template("cisco_ios_show_version.textfsm", raw_text)
    row = rows[0]
    return DeviceFacts(
        name=row["HOSTNAME"],
        serial=row["SERIAL"],
        manufacturer="Cisco",
        model=row["MODEL"],
        software_version=row["SOFTWARE_VERSION"],
        source="ssh",
        discovered_via_hop=hop,
    )


def parse_cdp_neighbors_detail(raw_text: str, local_device_serial: str, hop: int) -> list[NeighborLink]:
    rows = _run_template("cisco_ios_show_cdp_neighbors_detail.textfsm", raw_text)
    return [
        NeighborLink(
            a_device_serial=local_device_serial,
            a_interface=row["LOCAL_INTERFACE"],
            b_device_hostname=row["DEST_HOST"],
            b_interface=row["NEIGHBOR_INTERFACE"],
            protocol="cdp",
            discovered_via_hop=hop,
            source="ssh",
            b_device_ip=row["MGMT_IP"] or None,
        )
        for row in rows
        if row["DEST_HOST"]  # TextFSM fires an implicit EOF Record after the trailing "Management address(es): / IP address:" line at end-of-file with no preceding "Device ID:" line to populate DEST_HOST — filter out that synthetic empty-DEST_HOST artifact
    ]


def parse_lldp_neighbors_detail(raw_text: str, local_device_serial: str, hop: int) -> list[NeighborLink]:
    rows = _run_template("cisco_ios_show_lldp_neighbors_detail.textfsm", raw_text)
    return [
        NeighborLink(
            a_device_serial=local_device_serial,
            a_interface=row["LOCAL_INTERFACE"],
            b_device_hostname=row["SYSTEM_NAME"],
            b_interface=row["NEIGHBOR_INTERFACE"],
            protocol="lldp",
            discovered_via_hop=hop,
            source="ssh",
            b_device_ip=row["MGMT_IP"] or None,
        )
        for row in rows
    ]
