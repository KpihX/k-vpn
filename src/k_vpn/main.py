import sys
import os
import csv
import base64
import tempfile
import subprocess
import requests
import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.prompt import Prompt
from rich import print as rprint
from typing import List, Dict, Any

app = typer.Typer(help="k-vpn: Automated VPN Gate Connector")
console = Console()

VPN_GATE_API_URL = "http://www.vpngate.net/api/iphone/"

def fetch_vpn_servers() -> List[Dict[str, Any]]:
    """Fetches and parses VPN servers from VPN Gate API."""
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold green]Fetching VPN server list..."),
            transient=True,
        ) as progress:
            progress.add_task("fetch", total=None)
            response = requests.get(VPN_GATE_API_URL, timeout=30)
            response.raise_for_status()
            
        # The API returns a CSV file with a header and '*' lines at the end
        content = response.text
        lines = content.splitlines()
        
        # Remove comments/garbage lines (lines starting with '*' or '#')
        # Keep the header line which starts with 'HostName' usually, but in the raw response
        # the second line is usually the header. Let's inspect typical response.
        # Typical response starts with "*vpn_servers\n#HostName,..."
        
        csv_lines = [line for line in lines if not line.startswith('*')]
        
        if not csv_lines:
            console.print("[bold red]Error:[/bold red] Empty response from VPN Gate.")
            sys.exit(1)
            
        # The header usually starts with #HostName, strip the #
        if csv_lines[0].startswith('#'):
            csv_lines[0] = csv_lines[0][1:]
            
        reader = csv.DictReader(csv_lines)
        servers = []
        for row in reader:
            if row.get('OpenVPN_ConfigData_Base64'):
                servers.append(row)
        
        return servers

    except requests.RequestException as e:
        console.print(f"[bold red]Network Error:[/bold red] {e}")
        sys.exit(1)
    except Exception as e:
        console.print(f"[bold red]Error parsing data:[/bold red] {e}")
        sys.exit(1)

def group_by_country(servers: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Groups servers by country."""
    grouped = {}
    for server in servers:
        country = server.get('CountryLong', 'Unknown')
        if country not in grouped:
            grouped[country] = []
        grouped[country].append(server)
    return grouped

@app.command()
def main():
    """
    Fetch VPN Gate servers and connect to a selected country.
    """
    console.print(Panel.fit("[bold cyan]k-vpn[/bold cyan] - Secure World Connector", border_style="cyan"))

    servers = fetch_vpn_servers()
    
    if not servers:
        console.print("[yellow]No servers found.[/yellow]")
        return

    grouped_servers = group_by_country(servers)
    sorted_countries = sorted(grouped_servers.keys())

    table = Table(title="Available Countries", show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Country", style="cyan")
    table.add_column("Servers", justify="right")
    table.add_column("Top Speed", justify="right")

    for idx, country in enumerate(sorted_countries, 1):
        country_servers = grouped_servers[country]
        count = len(country_servers)
        # Find max speed (Speed is in bps, convert to Mbps)
        max_speed = max([int(s.get('Speed', 0)) for s in country_servers]) / 1000 / 1000
        table.add_row(str(idx), country, str(count), f"{max_speed:.2f} Mbps")

    console.print(table)

    choice = Prompt.ask(
        "\nSelect a country number (or 'q' to quit)", 
        default="q"
    )

    if choice.lower() == 'q':
        console.print("[bold red]Exiting...[/bold red]")
        raise typer.Exit()

    try:
        index = int(choice) - 1
        if 0 <= index < len(sorted_countries):
            selected_country = sorted_countries[index]
            connect_to_country(selected_country, grouped_servers[selected_country])
        else:
            console.print("[bold red]Invalid selection.[/bold red]")
    except ValueError:
        console.print("[bold red]Invalid input.[/bold red]")

def connect_to_country(country_name: str, servers: List[Dict[str, Any]]):
    """Selects the best server for the country and connects."""
    
    # Sort by Score (descending) as a proxy for quality
    # VPN Gate score formula considers uptime, speed, etc.
    best_server = sorted(servers, key=lambda s: int(s.get('Score', 0)), reverse=True)[0]
    
    ip = best_server.get('IP', 'Unknown')
    speed = int(best_server.get('Speed', 0)) / 1000 / 1000
    
    console.print(f"\n[bold green]Connecting to {country_name}...[/bold green]")
    console.print(f"Server IP: [cyan]{ip}[/cyan] | Speed: [yellow]{speed:.2f} Mbps[/yellow]")
    
    ovpn_data = base64.b64decode(best_server['OpenVPN_ConfigData_Base64'])
    
    try:
        # Create a directory for configs in user home to avoid /tmp permission issues with sudo/snap
        config_dir = os.path.expanduser("~/.k-vpn/configs")
        os.makedirs(config_dir, exist_ok=True)
        
        # Create credentials file (VPN Gate standard: vpn/vpn)
        creds_path = os.path.join(config_dir, "vpn_creds.txt")
        with open(creds_path, "w") as f:
            f.write("vpn\nvpn\n")
        os.chmod(creds_path, 0o600) # Only readable by current user (and root via sudo)
        
        # Create a temporary file for the config
        with tempfile.NamedTemporaryFile(mode='wb', dir=config_dir, suffix='.ovpn', delete=False) as temp_config:
            temp_config.write(ovpn_data)
            config_path = temp_config.name
        
        # Ensure the file is readable only by the user
        os.chmod(config_path, 0o600)
            
        console.print(f"[dim]Config saved to {config_path}[/dim]")
        console.print("[bold yellow]Launching OpenVPN (sudo required)...[/bold yellow]")
        
        # Run OpenVPN
        # --data-ciphers-fallback and --data-ciphers with AES-128-CBC 
        # handles older servers on OpenVPN 2.6+
        cmd = [
            "sudo", "openvpn", 
            "--config", config_path, 
            "--auth-user-pass", creds_path,
            "--data-ciphers", "AES-256-GCM:AES-128-GCM:CHACHA20-POLY1305:AES-128-CBC",
            "--data-ciphers-fallback", "AES-128-CBC"
        ]
        
        # Use Popen to monitor output in real-time
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True,
            bufsize=1
        )
        
        connected = False
        for line in iter(process.stdout.readline, ""):
            console.print(line.strip())
            
            if "Initialization Sequence Completed" in line and not connected:
                connected = True
                console.print("\n")
                console.print(Panel(
                    f"[bold green]✓ SUCCESSFULLY CONNECTED[/bold green]\n"
                    f"[bold white]Country:[/bold white] {country_name}\n"
                    f"[bold white]Server IP:[/bold white] [cyan]{ip}[/cyan]\n"
                    f"[bold white]Speed:[/bold white] [yellow]{speed:.2f} Mbps[/yellow]",
                    title="[bold green]VPN Active[/bold green]",
                    border_style="green",
                    expand=False
                ))
                console.print("[dim]Press CTRL+C to disconnect...[/dim]\n")
        
        process.wait()
        
    except KeyboardInterrupt:
        console.print("\n[bold red]Disconnecting and cleaning up...[/bold red]")
        if 'process' in locals():
            # Send SIGTERM to the sudo process, which should relay it to OpenVPN
            process.terminate()
    except Exception as e:
        console.print(f"[bold red]Connection failed:[/bold red] {e}")
    finally:
        # Cleanup
        if 'config_path' in locals() and os.path.exists(config_path):
            os.remove(config_path)
        if 'creds_path' in locals() and os.path.exists(creds_path):
            os.remove(creds_path)
        console.print("[dim]Temporary files cleaned up.[/dim]")

if __name__ == "__main__":
    app()
