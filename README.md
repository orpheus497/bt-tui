# FreeBSD Bluetooth TUI Manager (bt-tui)

A comprehensive Client-Server application for FreeBSD to manage Bluetooth functionality using a Terminal User Interface (TUI). Designed specifically for FreeBSD's native Bluetooth stack using `netgraph`, `hccontrol`, and `hcsecd`.

---

## License

This project is licensed under the **GNU General Public License v3 (GPLv3)**. See the [LICENSE](LICENSE) file for the full license text.

---

## Overview

`bt-tui` provides a user-friendly terminal interface for managing Bluetooth devices on FreeBSD. It uses a privilege-separated architecture where a root daemon handles hardware operations while a user-space TUI provides the interface.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Space                                │
│  ┌─────────────────┐                                            │
│  │   bt_tui.py     │  ◄── Runs as regular user                  │
│  │   (TUI Client)  │                                            │
│  └────────┬────────┘                                            │
│           │ Unix Domain Socket IPC                              │
│           │ /var/run/bt-tui.sock                                │
│           ▼                                                      │
│  ┌─────────────────┐                                            │
│  │  bt_daemon.py   │  ◄── Runs as root                          │
│  │  (Root Daemon)  │                                            │
│  └────────┬────────┘                                            │
└───────────┼─────────────────────────────────────────────────────┘
            │
┌───────────┼─────────────────────────────────────────────────────┐
│           ▼              Kernel Space                            │
│  ┌─────────────────┐    ┌─────────────────┐                     │
│  │    ng_ubt       │    │    ng_hci       │                     │
│  │ (USB Bluetooth) │────│ (HCI Protocol)  │                     │
│  └─────────────────┘    └─────────────────┘                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Installation & Distribution

### Standard Installation

The project includes a `setup.py` for standard Python installation.

```bash
# Clone and enter directory
git clone <repository-url> bt-tui
cd bt-tui

# Install globally or in a venv
sudo python3 setup.py install
```

This installs two commands:
- `bsd-bt-tui`: The terminal user interface.
- `bsd-bt-daemon`: The background management daemon.

### FreeBSD Service Integration (rc.d)

To run the daemon as a system service, use the provided `rc.d` script.

1.  **Copy the script:**
    ```bash
    sudo cp src/bsd_bt_daemon.rc /usr/local/etc/rc.d/bsd_bt_daemon
    sudo chmod +x /usr/local/etc/rc.d/bsd_bt_daemon
    ```

2.  **Enable the service:**
    Add to `/etc/rc.conf`:
    ```bash
    bsd_bt_daemon_enable="YES"
    ```

3.  **Start the service:**
    ```bash
    sudo service bsd_bt_daemon start
    ```

---

## FreeBSD Bluetooth Stack Prerequisites

### 1. Load Required Kernel Modules

Add to `/boot/loader.conf` or `/etc/rc.conf` (via `kld_list`):
`ng_ubt`, `ng_hci`, `ng_l2cap`, `ng_btsock`.

### 2. Enable Required Services

Add to `/etc/rc.conf`:
```bash
hcsecd_enable="YES"
sdpd_enable="YES"
```

---

## Usage

1.  **Start the Daemon**: Ensure the `bsd_bt_daemon` service is running (see above).
2.  **Launch the TUI**: Run `bsd-bt-tui` from your terminal.
3.  **Scan**: Press `s` to discover devices.
4.  **Pair**: Select a device and press `p`.

---

## Keybindings

| Key | Action |
|-----|--------|
| `s` | Scan for Bluetooth devices |
| `p` | Pair with selected device |
| `q` | Quit the application |

---

## Development & Privacy

- **Private Documentation**: The `.devdocs/` folder contains internal development notes and session history. This folder is excluded from git via `.gitignore`.
- **FOSS Compliance**: This project is 100% Free and Open Source, released under the GPLv3.

---

## Troubleshooting

- **Daemon not running**: Check `service bsd_bt_daemon status`.
- **Permission denied**: Ensure your user is in a group with write access to `/var/run/bt-tui.sock` (the daemon sets 0660 permissions).
- **No devices found**: Ensure `ng_ubt` is loaded and your hardware is recognized by `hccontrol`.

---

*FreeBSD Bluetooth TUI Manager - Built for the community.*