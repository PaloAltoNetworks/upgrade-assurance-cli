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
    pass
