import subprocess
import csv
import configparser

# Load configuration from ini file
config = configparser.ConfigParser()
config.read('config.ini')


radius_egress = config['radius']['egress']
radius_ingress = config['radius']['ingress']
radius_secret = config['radius']['secret']


# Define multiline HTML content
login_html = """
<!doctype html>
<html lang="en">
<head>
<title>internet hotspot > login</title>
<meta http-equiv=\"Content-Type\" content=\"text/html; charset=UTF-8\">
<meta http-equiv=\"pragma\" content=\"no-cache\">
<meta http-equiv=\"expires\" content=\"-1\">
<script>
onload = () => document.querySelector(\"form\").submit()
</script>
</head>
<body>
<form action=\"https://snapx-us1.choice.selectnetworx.com/guests/welcome/__PORTALID__\" method=\"get\">
<input type=\"hidden\" name=\"MA\" value=\"$(mac)\">
<input type=\"hidden\" name=\"IP\" value=\"$(ip)\">
<input type=\"hidden\" name=\"username\" value=\"$(username)\">
<input type=\"hidden\" name=\"link-login-only\" value=\"$(link-login-only)\">
<input type=\"hidden\" name=\"OS\" value=\"$(link-orig)\">
<input type=\"hidden\" name=\"error\" value=\"$(error)\">
<input type=\"hidden\" name=\"interface-name\" value=\"$(interface-name)\">
</form>
</body>
</html>
"""

alogin_html = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<meta http-equiv="refresh" content="1; url=$(link-redirect)">
<meta http-equiv="pragma" content="no-cache">
<meta http-equiv="expires" content="-1">
<title>internet hotspot > redirect</title>
<script>
onload = () => location.href = unescape('$(link-redirect-esc)');
</script> 
</head>
<body>
<h1>You are logged in</h1>
<p><a href="$(link-redirect)">continue</a></p>
</body>
</html>
"""


def configure_mikrotik(ip, port, username, password, portal_id):

    login_html = login_html.replace("__PORTALID__", portal_id)

    try:
        commands = [
            # Add custom entries into the walled garden
            'ip hotspot walled-garden add dst-host=*.safetynetaccess.com',
            'ip hotspot walled-garden add dst-host=*.amazonaws.com',
            'ip hotspot walled-garden add dst-host=*.selectnetworx.com',

            # Create a new HTML directory for `choice`
            'file remove [find name="hotspot/choice"]',
            'mkdir hotspot/choice',
            f'echo "{login_html}" > hotspot/choice/login.html',
            f'echo "{alogin_html}" > hotspot/choice/alogin.html',

            # Create a new hotspot server profile
            'ip hotspot profile add name=choice html-directory=hotspot/choice',

            # Modify existing server to use new profile
            'ip hotspot set [find] profile=choice',

            # Add IP address to SSH allowed list
            'ip firewall address-list add list=ssh allowed address={radius_egress}',

            # Create a new RADIUS profile
            'radius add service=hotspot address={radius_ingress} secret={radius_secret} disabled=yes name=choice',

            # Switch the server profile to the `choice` profile
            'ip hotspot profile set [find name=choice] use-radius=yes',

            # Switch system to use the new RADIUS profile
            'radius set [find] disabled=yes',  # Disable all existing radius profiles
            'radius set [find name=choice] disabled=no'  # Enable the choice radius profile
        ]

        for command in commands:
            ssh_command = [
                "ssh", f"{username}@{ip}", "-p", str(port), "-o", "StrictHostKeyChecking=no", command
            ]
            result = subprocess.run(ssh_command, input=f"{password}\n", text=True, capture_output=True, shell=False)
            if result.stdout:
                print(f"Output from {ip}: {result.stdout}")
            if result.stderr:
                print(f"Error from {ip}: {result.stderr}")
    except Exception as e:
        print(f"Failed to configure {ip}: {str(e)}")


def main():
    csv_file = "./devices.csv"  # Update with your actual file path
    
    with open(csv_file, newline='') as file:
        reader = csv.DictReader(file)
        for row in reader:
            configure_mikrotik(
                ip=row['ip'],
                port=int(row['port']),
                username=row['username'],
                password=row['password'],
                portal_id=row['portal_id']
            )

if __name__ == "__main__":
    main()
