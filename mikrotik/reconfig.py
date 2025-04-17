import csv
import configparser
import paramiko
import socket

# Load configuration from ini file
config = configparser.ConfigParser()
config.read("config.ini")

radius_egress = config["radius"]["egress"]
radius_ingress = config["radius"]["ingress"]
radius_secret = config["radius"]["secret"]

# Create SSH client
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())


def get_current_acl() -> list[str]:
    """Get current SSH access list"""

    print("Retrieving current SSH access list...")
    output = exec("ip service print terse where name=ssh")
    unique_ips = list(set(extract_ip_addresses(output)))
    print("SSH addresses found: " + ",".join(unique_ips))
    return unique_ips


def extract_ip_addresses(output: str) -> list[str]:
    """Find the address part in the output"""

    if "address=" not in output:
        return []

    # Extract the part after "address=" and before the next space
    address_part = output.split("address=")[1].split(" ")[0]

    # Split by comma to get individual IP addresses
    return address_part.split(",")


def test_connection(ip: str, port: int, username: str, password: str) -> bool:
    """Test SSH connection and provide detailed error information"""

    try:
        # Test connectivity first
        print(f"Testing TCP connectivity to {ip}:{port}...")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(5)
            result = sock.connect_ex((ip, port))

        if result != 0:
            print(f"⚠️ Cannot establish TCP connection to {ip}:{port}. Port may be closed or blocked.")
            return False
        else:
            print(f"✓ TCP connection to {ip}:{port} successful.")

        # Try different auth methods
        print(f"Attempting SSH connection with username '{username}'...")

        # First try with default settings
        try:
            client.connect(
                ip,
                port=port,
                username=username,
                password=password,
                timeout=10,
                look_for_keys=False,
                allow_agent=False,
            )
            print("✓ Authentication successful!")
            client.close()
            return True
        except paramiko.AuthenticationException:
            print("✗ Standard authentication failed, trying with keyboard-interactive...")

        # Try with keyboard-interactive auth
        try:
            transport = paramiko.Transport((ip, port))
            transport.connect(username=username, password=password)
            print("✓ Transport-level authentication successful!")
            transport.close()
            return True
        except Exception as e:
            print(f"✗ Transport-level authentication failed: {str(e)}")

        return False

    except paramiko.AuthenticationException:
        print("✗ Authentication failed. Check username and password.")
        return False
    except paramiko.SSHException as e:
        print(f"✗ SSH error: {e}")
        return False
    except socket.error as e:
        print(f"✗ Socket error: {e}")
        return False
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False


def configure_mikrotik(ip: str, port: int, username: str, password: str, portal_id: str, acl: str) -> None:
    # Test connection first
    if not test_connection(ip, port, username, password):
        print(f"Skipping configuration for {ip} due to connection issues.")
        return

    try:
        # Connect to the device with explicit settings
        print(f"Connecting to {ip}:{port} as {username}...")
        client.connect(
            ip,
            port=port,
            username=username,
            password=password,
            timeout=15,
            look_for_keys=False,  # Don't look for keys
            allow_agent=False,  # Don't use SSH agent
        )
        print(f"Successfully connected to {ip}")

        print(f"Retrieving ACL for {ip}...")
        current_acl_list = get_current_acl()  # returns a list
        if acl:
            current_acl_list.append(acl)  # add custom entries
        current_acl_list.append(radius_egress)  # add required snap egress ip
        updated_acl_list = ",".join(current_acl_list)  # it's now a csv string
        print("Updated ACL: " + updated_acl_list)

        # Add custom entries into the walled garden
        exec("ip hotspot walled-garden add dst-host=*.amazonaws.com")
        exec("ip hotspot walled-garden add dst-host=*.selectnetworx.com")

        url = "https://content.selectnetworx.com/snapx-migration"
        exec(f'/tool fetch url="{url}/login.php?portal={portal_id}" mode=http dst-path=sn_choice/login.html')
        exec(f'/tool fetch url="{url}/alogin.php?portal={portal_id}" mode=http dst-path=sn_choice/alogin.html')
        exec(f'/tool fetch url="{url}/rlogin.php?portal={portal_id}" mode=http dst-path=sn_choice/rlogin.html')

        # Create a new hotspot server profile, might already exist
        exec("ip hotspot profile add name=sn_choice html-directory=sn_choice")

        # Modify existing server to use new profile
        exec("ip hotspot set [find] profile=sn_choice")

        if updated_acl_list:
            print("Applying ACL: " + updated_acl_list)
            # Add IP address to SSH allowed list
            # exec(f'ip firewall address-list add list=ssh allowed address={radius_egress}') # not required
            exec(f"ip service set ssh address={updated_acl_list}")

        # Create a new RADIUS profile
        exec(f"radius add service=hotspot,login address={radius_ingress} secret={radius_secret} comment=SN_CHOICE")

        # Switch the server profile to the `sn_choice` profile
        exec("ip hotspot profile set [find name=sn_choice] use-radius=yes")

        # Switch system to use the new RADIUS profile
        radius_to_retain = ""  # Don't disable this RADIUS profile
        exec(f'radius set [find comment!=SN_CHOICE address!="{radius_to_retain}"] disabled=yes')

        # Close the connection
        client.close()
        print(f"Configuration of {ip} completed successfully.")

    except Exception as e:
        raise Exception(f"Failed to configure {ip}") from e


def exec(command: str) -> str:
    try:
        print(f"Executing: {command}")
        _, stdout, stderr = client.exec_command(command)

        # Wait for command to complete
        exit_status = stdout.channel.recv_exit_status()

        # Read both stdout and stderr
        output = stdout.read().decode("utf-8").strip()
        error = stderr.read().decode("utf-8").strip()

        if exit_status == 0:
            print("✓ Command successful.")
            if output:
                print(f"Output: {output}")
        else:
            print("✗ Command failed!")
            print(f"Output: {output}")
            print(f"Error: {error}")
        return output
    except Exception as e:
        raise Exception(f"Failed to execute command: {command}") from e


def main() -> None:
    csv_file = "./devices.csv"  # Update with your actual file path

    with open(csv_file, newline="") as file:
        for row in csv.DictReader(file):
            try:
                configure_mikrotik(
                    ip=row["ip"],
                    port=int(row["port"]),
                    username=row["username"],
                    password=row["password"],
                    portal_id=row["portal_id"],
                    acl=row["ssh_acl"],
                )
            except Exception as e:
                raise Exception(f"Error processing row for {row.get('ip', 'unknown')}: {e}") from e


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nScript interrupted by user.")
    except Exception as e:
        print(f"Unexpected error: {e}")
