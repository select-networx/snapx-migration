import csv
import configparser
import paramiko
import time
import socket
import sys

# Load configuration from ini file
config = configparser.ConfigParser()
config.read('config.ini')

radius_egress = config['radius']['egress']
radius_ingress = config['radius']['ingress']
radius_secret = config['radius']['secret']

# Define multiline HTML content
login_html_template = """
<!doctype html>
<html lang="en">
<head>
<title>internet hotspot > login</title>
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
<meta http-equiv="pragma" content="no-cache">
<meta http-equiv="expires" content="-1">
<script>
onload = () => document.querySelector("form").submit()
</script>
</head>
<body>
<form action="https://snapx-us1.choice.selectnetworx.com/guests/welcome/__PORTALID__" method="get">
<input type="hidden" name="MA" value="\$(mac)">
<input type="hidden" name="IP" value="\$(ip)">
<input type="hidden" name="username" value="\$(username)">
<input type="hidden" name="link-login-only" value="\$(link-login-only)">
<input type="hidden" name="OS" value="\$(link-orig)">
<input type="hidden" name="error" value="\$(error)">
<input type="hidden" name="interface-name" value="\$(interface-name)">
</form>
</body>
</html>
"""

alogin_html_template = """
<!doctype html>
<html lang="en">
<head>
<title>internet hotspot > login</title>
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
<meta http-equiv="pragma" content="no-cache">
<meta http-equiv="expires" content="-1">
<script>
onload = () => document.querySelector("form").submit()
</script>
</head>
<body>
<form action="https://snapx-us1.choice.selectnetworx.com/guests/welcome/__PORTALID__" method="post">
<input type="hidden" name="MA" value="\$(mac)">
<input type="hidden" name="IP" value="\$(ip)">
<input type="hidden" name="username" value="\$(username)">
<input type="hidden" name="link-login-only" value="\$(link-login-only)">
<input type="hidden" name="OS" value="\$(link-orig)">
<input type="hidden" name="error" value="\$(error)">
<input type="hidden" name="interface-name" value="\$(interface-name)">
<input type="hidden" name="var" value="\$(var)">
<input type="hidden" name="status" value="success">
<input type="hidden" name="do" value="callback">
</form>
</body>
</html>
"""

# Create SSH client with logging enabled
paramiko.util.log_to_file('paramiko.log')
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

def get_current_acl():
    # Get current SSH access list
    print("Retrieving current SSH access list...")
    stdin, stdout, stderr = client.exec_command('ip service print where name=ssh')

    # Wait for command to complete
    exit_status = stdout.channel.recv_exit_status()

    # Read both stdout and stderr
    output = stdout.read().decode('utf-8').strip()
    error = stderr.read().decode('utf-8').strip()

    if exit_status == 0:
        if output:
            print(f"Output: {output}")
    else:
        print(f"Error: {error}")
        return

    ### 
    # we've got the output from the acl command
    # now we need to parse it, because it uses a table

    lines = output.strip().splitlines()

    ssh_addresses = []

    # Parse the columns header to find the index of each column
    column_line = next(line for line in lines if line.startswith("Columns:"))
    columns = [c.strip() for c in column_line.replace("Columns:", "").split(",")]
    address_index = columns.index("ADDRESS")

    if not "ADDRESS" in columns:
        print('no addresses configured in acl')
        return ssh_addresses

    capture = False

    for line in lines:
        stripped = line.strip()

        print("\n\n" + stripped)

        if not stripped or stripped.startswith("Columns") or stripped.startswith("#"):
            continue

        parts = line.split()

        if not capture:
            if "ssh" in parts:
                # Start capturing from this line
                if len(parts) > address_index:
                    ssh_addresses.append(parts[address_index+1])
                capture = True
        else:
            # Handle continuation lines (they usually have only the address column)
            if parts and not parts[0].isdigit():  # Indented continuation
                ssh_addresses.append(parts[0])
            else:
                capture = False  # Stop if it's a new service or invalid line

    print('SSH addresses found: ' + ",".join(ssh_addresses))
    return ssh_addresses

def test_connection(ip, port, username, password):
    """Test SSH connection and provide detailed error information"""
    try:
        
        # Test connectivity first
        print(f"Testing TCP connectivity to {ip}:{port}...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((ip, port))
        sock.close()
        
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
                allow_agent=False
            )
            print(f"✓ Authentication successful!")
            client.close()
            return True
        except paramiko.AuthenticationException:
            print(f"✗ Standard authentication failed, trying with keyboard-interactive...")
            
        # Try with keyboard-interactive auth
        try:
            transport = paramiko.Transport((ip, port))
            transport.connect(username=username, password=password)
            print(f"✓ Transport-level authentication successful!")
            transport.close()
            return True
        except Exception as e:
            print(f"✗ Transport-level authentication failed: {str(e)}")
            
        return False
        
    except paramiko.AuthenticationException:
        print(f"✗ Authentication failed. Check username and password.")
        return False
    except paramiko.SSHException as e:
        print(f"✗ SSH error: {str(e)}")
        return False
    except socket.error as e:
        print(f"✗ Socket error: {str(e)}")
        return False
    except Exception as e:
        print(f"✗ Unexpected error: {str(e)}")
        return False

def configure_mikrotik(ip, port, username, password, portal_id, acl):
    # Apply the portal_id to the login HTML template
    configured_login_html = login_html_template.replace("__PORTALID__", portal_id)
    configured_login_html = configured_login_html.replace('\n', '').replace('"', '\\"')

    configured_alogin_html = alogin_html_template.replace("__PORTALID__", portal_id)
    configured_alogin_html = configured_alogin_html.replace('\n', '').replace('"', '\\"')

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
            allow_agent=False     # Don't use SSH agent
        )
        print(f"Successfully connected to {ip}")

        print(f"Retrieving ACL for {ip}...")
        current_acl_list = get_current_acl()
        current_acl_list.append(acl) # returns an array

        updated_acl_list = ",".join(current_acl_list) # it's now a csv string
        print('Applying ACL: ' + updated_acl_list)

        commands = [
            # Add custom entries into the walled garden
            'ip hotspot walled-garden add dst-host=*.amazonaws.com',
            'ip hotspot walled-garden add dst-host=*.selectnetworx.com',

            # Create a new HTML directory for `choice`
            #'file remove [find name="choice"]',
            'file add name=choice/login.html contents="' + configured_login_html + '"',
            'file add name=choice/alogin.html contents="' + configured_alogin_html + '"',

            # Create a new hotspot server profile
            'ip hotspot profile add name=choice html-directory=choice',

            # Modify existing server to use new profile
            'ip hotspot set [find] profile=choice',

            # Add IP address to SSH allowed list
            # f'ip firewall address-list add list=ssh allowed address={radius_egress}', # not required
            f'ip service set ssh address={updated_acl_list}',

            # Create a new RADIUS profile
            f'radius add service=hotspot,login address={radius_ingress} secret={radius_secret} disabled=yes comment=SN_CHOICE',

            # Switch the server profile to the `choice` profile
            'ip hotspot profile set [find name=choice] use-radius=yes',

            # Switch system to use the new RADIUS profile
            'radius set [find] disabled=yes',  # Disable all existing radius profiles
            'radius set [find comment=SN_CHOICE] disabled=no'  # Enable the choice radius profile
        ]

        # Execute each command
        for command in commands:
            print(f"Executing: {command}")
            stdin, stdout, stderr = client.exec_command(command)
            
            # Wait for command to complete
            exit_status = stdout.channel.recv_exit_status()

            # Read both stdout and stderr
            output = stdout.read().decode('utf-8').strip()
            error = stderr.read().decode('utf-8').strip()
            
            if exit_status == 0:
                print(f"Command successful: {command}")
                if output:
                    print(f"Output: {output}")
            else:
                print(f"Command failed: {command}")
                print(f"Error: {error}")
                break
                
            # Brief pause between commands
            time.sleep(0.5)
            
        # Close the connection
        client.close()
        print(f"Configuration of {ip} completed successfully.")
        
    except Exception as e:
        print(f"Failed to configure {ip}: {str(e)}")
        print(f"Check the paramiko.log file for more detailed error information.")

def main():
    csv_file = "./devices.csv"  # Update with your actual file path
    
    try:
        with open(csv_file, newline='') as file:
            reader = csv.DictReader(file)
            for row in reader:
                try:
                    configure_mikrotik(
                        ip=row['ip'],
                        port=int(row['port']),
                        username=row['username'],
                        password=row['password'],
                        portal_id=row['portal_id'],
                        acl=row['ssh_acl']
                    )
                except Exception as e:
                    print(f"Error processing row for {row.get('ip', 'unknown')}: {str(e)}")
    except FileNotFoundError:
        print(f"CSV file not found: {csv_file}")
    except Exception as e:
        print(f"Error reading CSV file: {str(e)}")

if __name__ == "__main__":
    main()