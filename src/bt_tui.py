##Script function and purpose: FreeBSD Bluetooth TUI Client.
##This script provides a terminal user interface (TUI) using the Textual library
##to manage Bluetooth devices on FreeBSD. It communicates with the bt-tui daemon
##via Unix Domain Socket to perform privileged Bluetooth operations.
##
##Architecture Role:
##  - Runs as unprivileged user (no root required)
##  - Connects to root daemon via /var/run/bt-tui.sock
##  - Sends JSON commands and receives JSON responses
##  - Provides visual interface for device discovery and pairing
##
##Key Components:
##  - DaemonClient: Handles IPC communication with the daemon
##  - DeviceListItem: Custom widget for displaying device info
##  - DeviceListPanel: Scrollable list of discovered devices
##  - ControlPanel: Action buttons (Scan, Pair)
##  - BluetoothTUI: Main application class
##
##Keybindings:
##  - 'q': Quit application
##  - 's': Scan for devices
##  - 'p': Pair with selected device
##
##Dependencies:
##  - textual: Modern Python TUI framework
##  - Running bt_daemon.py instance with accessible socket

import socket
import json
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Header, Footer, Static, Button, ListView, ListItem, Label, Log
from textual.reactive import reactive
from utils import SOCKET_PATH, BUFFER_SIZE


##Class purpose: Handle IPC communication with the bt-tui daemon.
##This class encapsulates all socket communication logic, providing a clean
##interface for the TUI to send commands and receive responses.
##
##Communication Protocol:
##  - Uses Unix Domain Sockets (AF_UNIX) for local IPC
##  - JSON-encoded requests and responses
##  - Synchronous request/response pattern (one socket per command)
##
##Error Handling:
##  - Returns error dict if socket not found (daemon not running)
##  - Returns error dict if connection refused
##  - Returns error dict if permission denied (socket permissions)
##  - Returns error dict for any other connection errors
class DaemonClient:
    ##Method purpose: Initialize the client with socket path.
    ##The socket path can be overridden for testing or custom configurations.
    def __init__(self, socket_path=SOCKET_PATH):
        ##Step purpose: Store socket path for later connection attempts.
        self.socket_path = socket_path

    ##Method purpose: Send a command to the daemon and receive response.
    ##This is the core communication method used by all higher-level methods.
    ##Creates a new socket connection for each command (request/response pattern).
    ##
    ##Parameters:
    ##  command: Dictionary to be JSON-encoded and sent to daemon
    ##
    ##Returns: Dictionary with status and data/message from daemon (or error dict)
    def send_command(self, command):
        ##Error purpose: Handle connection and communication errors.
        ##Multiple specific exceptions provide meaningful error messages.
        try:
            ##Action purpose: Create and connect Unix Domain Socket.
            ##AF_UNIX for Unix domain, SOCK_STREAM for reliable stream.
            client_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            
            ##Action purpose: Connect to daemon socket.
            ##This will raise FileNotFoundError if socket doesn't exist.
            client_socket.connect(self.socket_path)
            
            ##Action purpose: Send JSON-encoded command to daemon.
            ##UTF-8 encoding is standard for JSON over sockets.
            request_str = json.dumps(command)
            client_socket.sendall(request_str.encode('utf-8'))
            
            ##Action purpose: Receive and decode response from daemon.
            ##BUFFER_SIZE limits how much data we read in one call.
            response_data = client_socket.recv(BUFFER_SIZE)
            response_str = response_data.decode('utf-8')
            
            ##Action purpose: Close socket and return parsed response.
            client_socket.close()
            return json.loads(response_str)
        
        ##Error purpose: Handle specific socket errors with user-friendly messages.
        except FileNotFoundError:
            ##Error purpose: Daemon socket doesn't exist - daemon not running.
            return {"status": "error", "message": "Daemon not running (socket not found)"}
        except ConnectionRefusedError:
            ##Error purpose: Socket exists but daemon not accepting connections.
            return {"status": "error", "message": "Connection refused by daemon"}
        except PermissionError:
            ##Error purpose: Socket exists but user lacks permission to connect.
            ##User needs to be in appropriate group or socket permissions changed.
            return {"status": "error", "message": "Permission denied - check socket permissions"}
        except Exception as e:
            ##Error purpose: Catch-all for unexpected connection errors.
            return {"status": "error", "message": f"Connection error: {str(e)}"}

    ##Method purpose: Request device scan from daemon.
    ##Convenience method that sends a scan action command.
    ##Returns: Dictionary with status and data (list of devices) or error message.
    def scan_devices(self):
        return self.send_command({"action": "scan"})

    ##Method purpose: Request device pairing from daemon.
    ##Sends pair action with MAC address and optional PIN code.
    ##
    ##Parameters:
    ##  mac: Bluetooth MAC address of device to pair
    ##  pin: PIN code for pairing (default "0000" for most audio devices)
    ##
    ##Returns: Dictionary with status and success/error message.
    def pair_device(self, mac, pin="0000"):
        return self.send_command({"action": "pair", "mac": mac, "pin": pin})


##Class purpose: Custom ListItem widget to hold and display device data.
##Extends Textual's ListItem to store device dictionary data and provide
##custom rendering with device name, MAC address, and paired status.
##
##This allows the ListView to maintain the association between visual items
##and the underlying device data for selection and pairing operations.
class DeviceListItem(ListItem):
    ##Method purpose: Initialize list item with device data.
    ##Stores device dictionary for later retrieval when item is selected.
    def __init__(self, device_data, **kwargs):
        ##Action purpose: Call parent constructor with any additional args.
        super().__init__(**kwargs)
        ##Step purpose: Store device data for access by parent widgets.
        self.device_data = device_data

    ##Method purpose: Compose the visual content of the list item.
    ##Returns a Label widget showing device info in formatted layout.
    def compose(self) -> ComposeResult:
        ##Step purpose: Extract device information with defaults for missing data.
        mac = self.device_data.get("mac", "Unknown")
        name = self.device_data.get("name", "Unknown")
        
        ##Step purpose: Create paired status indicator.
        ##Checkmark shown for paired devices, empty string otherwise.
        paired = "✓ Paired" if self.device_data.get("paired") else ""
        
        ##Action purpose: Yield formatted label with device info.
        ##Format: "DeviceName  |  XX:XX:XX:XX:XX:XX  ✓ Paired"
        yield Label(f"{name}  |  {mac}  {paired}")


##Class purpose: Panel widget displaying scrollable list of discovered Bluetooth devices.
##This is the main display area showing devices found during Bluetooth scan.
##Uses Textual's Vertical container for layout with header and ListView.
class DeviceListPanel(Vertical):
    ##Method purpose: Compose the device list panel UI elements.
    ##Returns the header label and scrollable list view.
    def compose(self) -> ComposeResult:
        ##Action purpose: Yield header with bold styling.
        yield Static("[bold]Discovered Devices[/bold]", id="device-list-header")
        
        ##Action purpose: Yield empty ListView to be populated after scan.
        ##ID allows querying from parent widget.
        yield ListView(id="device-list")


##Class purpose: Panel widget containing action buttons and status display.
##Provides Scan and Pair buttons, plus display of currently selected device.
##Uses Textual's Vertical container for stacked layout.
class ControlPanel(Vertical):
    ##Method purpose: Compose the control panel UI elements.
    ##Returns header, action buttons, and selected device info display.
    def compose(self) -> ComposeResult:
        ##Action purpose: Yield header with bold styling.
        yield Static("[bold]Controls[/bold]", id="control-header")
        
        ##Action purpose: Yield Scan button with primary styling.
        ##Primary variant makes it visually prominent.
        yield Button("Scan for Devices", id="scan-btn", variant="primary")
        
        ##Action purpose: Yield Pair button with default styling.
        ##Less prominent than Scan since it requires device selection first.
        yield Button("Pair Selected", id="pair-btn", variant="default")
        
        ##Action purpose: Yield status display for selected device.
        ##Updated when user selects a device from the list.
        yield Static("No device selected", id="selected-device-info")


##Class purpose: Main application class for the Bluetooth TUI.
##This is the root Textual application that orchestrates the entire UI.
##Manages layout, keybindings, daemon communication, and user interactions.
##
##Layout Structure:
##  ┌─────────────────────────────────────┐
##  │            Header                    │
##  ├─────────────────────┬───────────────┤
##  │   DeviceListPanel   │ ControlPanel  │
##  │   (2fr width)       │ (1fr width)   │
##  ├─────────────────────┴───────────────┤
##  │         Status Log (full width)     │
##  ├─────────────────────────────────────┤
##  │            Footer                    │
##  └─────────────────────────────────────┘
##
##State Management:
##  - devices: List of discovered device dictionaries
##  - selected_device: Currently selected device (reactive)
class BluetoothTUI(App):
    ##Step purpose: Define CSS styling for the application layout.
    ##Uses Textual's CSS dialect for terminal UI styling.
    ##Grid layout provides responsive 2-column design.
    CSS = """
    Screen {
        layout: grid;
        grid-size: 2 2;
        grid-columns: 2fr 1fr;
        grid-rows: 1fr auto;
    }
    
    DeviceListPanel {
        border: solid green;
        height: 100%;
        padding: 1;
    }
    
    #device-list-header {
        text-style: bold;
        margin-bottom: 1;
    }
    
    #device-list {
        height: 100%;
    }
    
    ControlPanel {
        border: solid blue;
        padding: 1;
    }
    
    #control-header {
        margin-bottom: 1;
    }
    
    Button {
        margin: 1 0;
        width: 100%;
    }
    
    #status-log {
        column-span: 2;
        height: 8;
        border: solid yellow;
    }
    
    DeviceListItem {
        padding: 1;
    }
    """

    ##Step purpose: Define global keybindings for the application.
    ##Each tuple is (key, action_method, description).
    ##Action methods are called automatically by Textual.
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("s", "scan", "Scan"),
        ("p", "pair", "Pair"),
    ]

    ##Step purpose: Define reactive state for selected device.
    ##Reactive properties automatically trigger UI updates when changed.
    selected_device = reactive(None)

    ##Method purpose: Initialize the application with daemon client.
    ##Sets up the DaemonClient for IPC and initializes device list.
    def __init__(self):
        ##Action purpose: Call parent App constructor.
        super().__init__()
        
        ##Step purpose: Create daemon client for socket communication.
        self.daemon_client = DaemonClient()
        
        ##Step purpose: Initialize empty device list.
        ##Populated after successful scan.
        self.devices = []

    ##Method purpose: Compose the main UI layout.
    ##Returns all top-level widgets in rendering order.
    def compose(self) -> ComposeResult:
        ##Action purpose: Yield header bar with app title.
        yield Header()
        
        ##Action purpose: Yield main panels (placed by CSS grid).
        yield DeviceListPanel()
        yield ControlPanel()
        
        ##Action purpose: Yield log panel for status messages.
        yield Log(id="status-log")
        
        ##Action purpose: Yield footer bar with keybinding hints.
        yield Footer()

    ##Method purpose: Handle application startup.
    ##Called by Textual after all widgets are mounted.
    def on_mount(self) -> None:
        ##Action purpose: Log startup message to guide user.
        self.log_status("FreeBSD Bluetooth Manager started. Press 's' to scan.")

    ##Method purpose: Log messages to the status panel.
    ##Provides user feedback for operations and errors.
    ##
    ##Parameters:
    ##  message: String to display in the log panel
    def log_status(self, message):
        ##Step purpose: Query the log widget by ID and write message.
        log_widget = self.query_one("#status-log", Log)
        log_widget.write_line(message)

    ##Method purpose: Handle button press events.
    ##Routes button presses to appropriate action methods.
    ##
    ##Parameters:
    ##  event: Button.Pressed event containing button info
    def on_button_pressed(self, event: Button.Pressed) -> None:
        ##Condition purpose: Route button presses to appropriate handlers.
        if event.button.id == "scan-btn":
            ##Action purpose: Trigger scan action.
            self.action_scan()
        elif event.button.id == "pair-btn":
            ##Action purpose: Trigger pair action.
            self.action_pair()

    ##Method purpose: Handle list view selection events.
    ##Updates selected_device state when user clicks/selects a device.
    ##
    ##Parameters:
    ##  event: ListView.Selected event containing selected item
    def on_list_view_selected(self, event: ListView.Selected) -> None:
        ##Step purpose: Get the selected list item.
        item = event.item
        
        ##Condition purpose: Verify it's a DeviceListItem with data.
        if isinstance(item, DeviceListItem):
            ##Action purpose: Update selected device state.
            self.selected_device = item.device_data
            
            ##Step purpose: Update info display in control panel.
            info_widget = self.query_one("#selected-device-info", Static)
            mac = self.selected_device.get('mac', 'None')
            info_widget.update(f"Selected: {mac}")
            
            ##Action purpose: Log selection for user feedback.
            self.log_status(f"Selected device: {mac}")

    ##Method purpose: Execute device scan action.
    ##Communicates with daemon to discover nearby Bluetooth devices.
    ##Updates device list panel with results.
    def action_scan(self) -> None:
        ##Action purpose: Log scan start for user feedback.
        self.log_status("Scanning for devices...")
        
        ##Action purpose: Request scan from daemon via IPC.
        response = self.daemon_client.scan_devices()
        
        ##Condition purpose: Handle scan response based on status.
        if response.get("status") == "success":
            ##Step purpose: Store discovered devices.
            self.devices = response.get("data", [])
            
            ##Action purpose: Update UI with new device list.
            self.update_device_list()
            
            ##Action purpose: Log success with device count.
            self.log_status(f"Scan complete: found {len(self.devices)} device(s)")
        else:
            ##Action purpose: Log error message from daemon.
            error_msg = response.get("message", "Unknown error")
            self.log_status(f"Scan failed: {error_msg}")

    ##Method purpose: Update the device list display with scan results.
    ##Clears existing items and populates with current device data.
    def update_device_list(self):
        ##Step purpose: Get the device list widget by ID.
        list_view = self.query_one("#device-list", ListView)
        
        ##Action purpose: Clear existing items from previous scan.
        list_view.clear()
        
        ##Condition purpose: Handle empty results gracefully.
        if not self.devices:
            ##Note: Could add a "No devices found" placeholder here.
            return
        
        ##Loop purpose: Create UI entry for each discovered device.
        for device in self.devices:
            ##Step purpose: Create DeviceListItem with device data.
            item = DeviceListItem(device)
            
            ##Action purpose: Append to list view.
            list_view.append(item)

    ##Method purpose: Execute device pairing action.
    ##Sends pair command to daemon for currently selected device.
    def action_pair(self) -> None:
        ##Condition purpose: Check if a device is selected.
        if not self.selected_device:
            ##Action purpose: Log error for missing selection.
            self.log_status("No device selected for pairing")
            return
        
        ##Step purpose: Extract MAC address from selected device.
        mac = self.selected_device.get("mac")
        
        ##Action purpose: Log pairing attempt for user feedback.
        self.log_status(f"Pairing with {mac}...")
        
        ##Action purpose: Request pairing from daemon via IPC.
        response = self.daemon_client.pair_device(mac)
        
        ##Condition purpose: Handle pairing response based on status.
        if response.get("status") == "success":
            ##Action purpose: Log successful pairing.
            self.log_status(f"Paired successfully with {mac}")
        else:
            ##Action purpose: Log error message from daemon.
            error_msg = response.get("message", "Unknown error")
            self.log_status(f"Pairing failed: {error_msg}")


##Function purpose: Entry point for the TUI application.
##Creates the app instance and starts the Textual event loop.
def main():
    ##Step purpose: Create BluetoothTUI application instance.
    app = BluetoothTUI()
    
    ##Action purpose: Start the Textual event loop.
    ##This blocks until the app is closed (via 'q' key or other means).
    app.run()


##Condition purpose: Run the Textual application when executed directly.
##This Python idiom allows the file to be imported as a module (for testing)
##without automatically starting the app, while still running when executed directly.
if __name__ == "__main__":
    main()