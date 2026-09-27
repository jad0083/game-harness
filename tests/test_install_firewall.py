"""The installer's firewall rule admits only the controller, only on a Private network, and a
reinstall tightens a rule left by an older installer (no PowerShell on the controller, so these
check the script's text)."""

import re
from pathlib import Path

INSTALL = (Path(__file__).resolve().parents[1] / "windows_agent/install.ps1").read_text(encoding="utf-8")
FIREWALL = INSTALL.split("# --- 3. Firewall", 1)[1].split("# --- 4.", 1)[0]


def test_rule_is_private_only():
    assert "-Profile Any" not in INSTALL
    assert re.search(r"\$FwProfile\s*=\s*if \(\$env:GA_FW_PROFILE\).*else \{ 'Private' \}", FIREWALL)
    assert "-Profile $FwProfile" in FIREWALL


def test_remote_address_is_the_controller_with_local_subnet_fallback():
    assert re.search(r"\$env:GA_CONTROLLER", FIREWALL)
    assert re.search(r"\[Uri\]\$env:GA_SRC\)\.Host", FIREWALL), "controller address taken from the download URL"
    assert "'LocalSubnet'" in FIREWALL, "local installs fall back to the local subnet"
    assert "-RemoteAddress $Remote" in FIREWALL
    assert "-RemoteAddress LocalSubnet" not in FIREWALL


def test_values_spliced_into_the_elevated_command_are_validated():
    assert re.search(r"\$Remote -notmatch '\^\(LocalSubnet\|", FIREWALL)
    assert re.search(r"\$FwProfile -notmatch", FIREWALL)


def test_an_existing_rule_is_replaced_when_it_differs():
    assert "rule already present" not in FIREWALL
    assert "Get-NetFirewallAddressFilter" in FIREWALL, "compares the existing rule's remote address"
    cmd = re.search(r"\$cmd = \"(.+)\"", FIREWALL).group(1)
    assert cmd.index("Remove-NetFirewallRule") < cmd.index("New-NetFirewallRule")


def test_warns_when_the_network_is_not_private():
    assert "Get-NetConnectionProfile" in FIREWALL
    assert "Set-NetConnectionProfile" in FIREWALL
