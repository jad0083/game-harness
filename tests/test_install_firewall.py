"""The installer's firewall rule admits only the controller, only on a Private network, and a
reinstall tightens a rule left by an older installer without ever cutting the controller off (no
PowerShell on the controller, so these check the script's text)."""

import re
from pathlib import Path

INSTALL = (Path(__file__).resolve().parents[1] / "windows_agent/install.ps1").read_text(encoding="utf-8")
SETTINGS = INSTALL.split("# --- 0b. Firewall settings", 1)[1].split("# --- 1.", 1)[0]
FIREWALL = INSTALL.split("# --- 5. Firewall", 1)[1]


def test_rule_is_private_only():
    assert "-Profile Any" not in INSTALL
    assert re.search(r"\$FwProfile\s*=\s*if \(\$env:GA_FW_PROFILE\).*else \{ 'Private' \}", SETTINGS)
    assert "-Profile $FwProfile" in FIREWALL


def test_remote_address_is_the_controller_with_local_subnet_fallback():
    assert "$env:GA_CONTROLLER" in SETTINGS
    assert re.search(r"\[Uri\]\$env:GA_SRC\)\.Host", SETTINGS), "controller address taken from the download URL"
    assert "'LocalSubnet'" in SETTINGS, "local installs fall back to the local subnet"
    assert "-RemoteAddress $Remote" in FIREWALL
    assert "-RemoteAddress LocalSubnet" not in INSTALL


def test_settings_are_validated_before_the_agent_is_stopped():
    assert re.search(r"\$Remote -notmatch '\^\(LocalSubnet\|", SETTINGS)
    assert re.search(r"\$FwProfile -notmatch", SETTINGS)
    assert INSTALL.index("# --- 0b. Firewall settings") < INSTALL.index("Stop-Process")


def test_rule_changes_come_after_the_agent_is_restarted_and_never_abort():
    # The UAC prompt cannot be answered remotely; a declined prompt must not leave the agent down.
    assert INSTALL.index("Start-ScheduledTask") < INSTALL.index("# --- 5. Firewall")
    assert not re.search(r"^\s*throw", FIREWALL, re.MULTILINE)
    assert re.search(r"try \{\s*Start-Process powershell -Verb RunAs", FIREWALL)


def test_an_existing_rule_is_replaced_when_it_differs():
    assert "rule already present" not in INSTALL
    assert "Get-NetFirewallAddressFilter" in FIREWALL, "compares the existing rule's remote address"
    cmd = re.search(r"\$cmd = \"(.+)\"", FIREWALL).group(1)
    assert cmd.index("Remove-NetFirewallRule") < cmd.index("New-NetFirewallRule")


def test_an_old_rule_is_kept_while_the_controllers_network_is_not_covered():
    assert "Get-NetConnectionProfile" in FIREWALL and "Set-NetConnectionProfile" in FIREWALL
    assert "Find-NetRoute" in FIREWALL, "only the network toward the controller counts"
    assert re.search(r"elseif \(\$uncovered\.Count -gt 0 -and \$have -ne '0 rules'\)", FIREWALL)
    keep = FIREWALL.split("$uncovered.Count -gt 0", 1)[1].split("} else {", 1)[0]
    assert "Keeping the existing firewall rule" in keep and "RunAs" not in keep
