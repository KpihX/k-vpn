# k-vpn

**k-vpn** is a modern, automated CLI tool designed to easily fetch and connect to public VPN Gate servers directly from your terminal. Built with Python, Typer, and Rich, it offers a beautiful and interactive experience for securing your connection.

## Features

-   **Automated Fetching**: Retrieves the latest list of public VPN servers from VPN Gate.
-   **Rich UI**: Displays server availability by country in a formatted table.
-   **Interactive Selection**: Easily choose your desired country.
-   **Secure Connection**: Automates the OpenVPN connection process using temporary configuration files.
-   **Smart Defaults**: Filters for high-speed, uptime-reliable servers.

## Prerequisites

-   **Python 3.8+**
-   **OpenVPN**: Must be installed and accessible via `sudo openvpn` on your system.
-   **uv**: Recommended for project management and execution.

## Installation & Usage

It is recommended to use `uv` to run this tool directly without manual environment setup.

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/KpihX/k-vpn.git
    cd k-vpn
    ```

2.  **Run the tool:**
    ```bash
    uv run k-vpn.py
    ```

    The tool will verify your environment, fetch the server list, and present you with options.

## How it Works

1.  **Fetch**: The tool downloads the CSV list from `http://www.vpngate.net/api/iphone/`.
2.  **Parse & Filter**: It parses the data, filtering for valid OpenVPN configurations.
3.  **Display**: Aggregates servers by country and displays a summary table (Country, Server Count).
4.  **Connect**:
    *   You select a country by its index.
    *   The tool picks the best server (based on score/speed) for that country.
    *   It decodes the base64 OpenVPN configuration.
    *   It creates a temporary `.ovpn` file.
    *   It executes `sudo openvpn --config <temp_file>` to establish the tunnel.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This tool uses public servers from VPN Gate. The availability, speed, and security of these servers are not guaranteed by the author. Use at your own risk.
