# upgrade-assurance-cli — Test and Backup your PAN-OS Environment

This project is a simple CLI wrapper around the [PAN-OS Upgrade Assurance](https://github.com/PaloAltoNetworks/pan-os-upgrade-assurance)
 library.

<p>
<img src="https://badge.fury.io/py/upgrade-assurance-cli.svg"/>
</p>



## Installation

It is recommended to install this project with [pipx](https://pipx.pypa.io/stable/).

Installing with pipx will automatically make the main script, `assurance-cli` available at the command line.

```shell
pipx install upgrade-assurance-cli
```

You can also install directly from this repository if you want to get changes as we develop them, but before they are
formally released.

```shell
# Install from the main branch
pipx install git+https://github.com/PaloAltoNetworks/upgrade-assurance-cli.git 
# Install from <branch_name>, useful for testing.
pipx install git+https://github.com/PaloAltoNetworks/upgrade-assurance-cli.git@<branch_name> 
```

## Quickstart

Run a readiness check ("pre-checks") against a given device.

```shell
assurance-cli readiness myfirewall.com
```

Read the last readiness report for a specific device

```shell
assurance-cli report --device myfirewall.com
```

Take a capacity report

```shell
assurance-cli capacity myfirewall.com
```

Take an operational snapshot

```shell
assurance-cli snapshot myfirewall.com
```

Compare two snapshots 

```shell
assurance-cli compare-snapshots <first-snapshot-path> <second-snapshot-path>
```

Backup the configuration running-configuration

```shell
assurance-cli backup myfirewall.com
```

Backup the configuration device-state

```shell
assurance-cli backup myfirewall.com --export-type device-state
```

## Configuration

### Report storage

By default, `assurance-cli` uses the following directory structure to store all
reports and artifacts:

```
.
├── ./
│   ├── snapshots/
│   │   ├── snapshot_<device-str>_<timestamp>.json
│   ├── store/
│   │   ├── capacity_<device-str>_<timestamp>.json
│   │   ├── readiness_<device-str>_<timestamp>.json
│   │   ├── snapshotr_<device-str>_<timestamp>.json
│   ├── backups/
│   │   ├── backup_<device-str>_<timestamp>.json
```

### Running Against Multiple Devices

This tool allows you to run against multiple devices at once using `multiprocessing`.

Multiple devices can be passed to the comand line as arguments to the `readiness` and `snapshot` commands.

```shell
assurance-cli readiness myfirstfirewall.com mysecondfirewall.com 
```

Or, they can be passed via a text file containing one device per line.

```text
myfirstfirewall.com
mysecondfirewall.com
```

```shell
assurance-cli readiness <path_to_devices_file>
```

### Connecting Via Panorama

Connections can be proxied via Panorama for simplicity. To do so, use the following format for the device string;
`<panorama_hostname>:<firewall_serial_number>`

```shell
assurance-cli readiness my_panorama.com:1234567891011
```

### Environment Variables

envvar | description
--- | ---
UA_USERNAME | Username to use for authentication - prompts if not given
UA_PASSWORD | Username to use for authentication - prompts if not given

### Customizing the Test Suite

All commands support passing the `--config-path` flag to pass in a config file. This CLI ships with the most commonly
used tests but it is expected that most users will need to customize it.

The config file is in YAML format and specifies the tests used by the upgrade assurance library.

**Complete example**

```yaml
pre_checks:
  - "active_support"
  - "candidate_config"
  - "expired_licenses"
  - "jobs"
  - "ntp_sync"
  - "panorama"
  # tests below have optional configuration
  - certificates_requirements:
      ecdsa:
        hash_method: "sha512"
      rsa:
        key_size: 1024
        hash_method: "sha1"
  - content_version:
      version: "8634-7678"
  - dp_cpu_utilization:
      threshold: 50
      minutes: 2
  - dynamic_updates:
      test_window: 120
  - expired_licenses:
      skip_licenses:
        - "Threat Prevention"
  - free_disk_space:
      image_version: "10.1.6-h6"
  - ha:
      skip_config_sync: true
  - mp_cpu_utilization:
      threshold: 40
  - planes_clock_sync:
      diff_threshold: 30
  # tests below require additional configuration
  - arp_entry_exist:
      ip: "10.0.1.1"
  - ip_sec_tunnel_status:
      tunnel_name: "ipsec_tun"
  - session_exist:
      source: "134.238.135.137"
      destination: "10.1.0.4"
      dest_port: "80"
snapshot_comparison_config:
  - ip_sec_tunnels:
      properties:
        - "state"
  - arp_table:
      properties:
        - "!ttl"
      count_change_threshold: 10
  - nics:
      count_change_threshold: 10
  - license:
      properties:
        - "!serial"
  - routes:
      properties:
        - "!flags"
      count_change_threshold: 10
  - fib_routes:
      properties:
        - "!flags"
      count_change_threshold: 10
  - are_routes:
      properties:
        - "!uptime"
        - "!internalNextHopNum"
      count_change_threshold: 10
  - are_fib_routes:
      properties:
        - "!flags"
      count_change_threshold: 10
  - bgp_peers:
      properties:
        - "status"
  - content_version
  - session_stats:
      thresholds:
        - num-max: 10
        - num-tcp: 10
  - mtu
snapshot_config:
 - routes
 - nics
 - are_fib_routes
 - arp_table
 - license
 - fib_routes
 - are_routes
 - are_fib_routes
 - bgp_peers
 - content_version
 - session_stats
 - mtu
 - ip_sec_tunnels
```

For a full list of checks and al their configuration options view the 
[Upgrade Assurance Documentation site.](https://pan.dev/panos/docs/panos-upgrade-assurance/configuration-details/)
