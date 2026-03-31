import pytest
import os

from panos_upgrade_assurance.firewall_proxy import FirewallProxy


@pytest.fixture(scope="session")
def firewall_fixture():
    if not os.getenv("UA_USERNAME"):
        pytest.skip("UA_USERNAME environment variable not set")

    return FirewallProxy(
        api_username=os.getenv("UA_USERNAME"),
        api_password=os.getenv("UA_PASSWORD"),
        hostname=os.getenv("UA_HOSTNAME"),
    )


def test_get_device_state(firewall_fixture):
    from upgrade_assurance_cli.cli.exporter import get_device_state

    result = get_device_state(firewall_fixture._fw)
    print(len(result.content))

def test_get_capacity_details():
    from upgrade_assurance_cli.cli.capacity import get_capacity_details
    print(get_capacity_details().items[0].model_dump_json(indent=4))

def test_get_firewall_statistics(firewall_fixture):
    from upgrade_assurance_cli.cli.runner import get_current_statistics
    result = get_current_statistics(firewall_fixture)
    print(result.model_dump_json(indent=4))


def test_get_firewall_statistics_and_compare(firewall_fixture):
    from upgrade_assurance_cli.cli.capacity import get_capacity_details
    from upgrade_assurance_cli.cli.runner import get_current_statistics
    current = get_current_statistics(firewall_fixture)
    limits = get_capacity_details()
    result = limits.compare_with_running(current)
    print(result.model_dump_json(indent=4))
