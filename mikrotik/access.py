import requests
from requests.auth import HTTPBasicAuth

# Step 1: Allow an IP address into the firewall
def allow_firewall_address(ip, username, password):
    firewall_url = f"http://{ip}/rest/ip/firewall/address-list"
    payload = {
        "address": ip,
        "list": "allowed",
        "comment": "Allowed by API"
    }
    response = requests.put(firewall_url, auth=HTTPBasicAuth(username, password), json=payload)
    print("Firewall rule response:", response.status_code, response.text)

# Step 2: Assign SSH permission to a specific user
def configure_ssh_for_user(ip, username, password, target_user, group="full"):
    user_url = f"http://{ip}/rest/user"
    # Update user group
    response = requests.patch(f"{user_url}/{target_user}", auth=HTTPBasicAuth(username, password), json={"group": group})
    print("User group update response:", response.status_code, response.text)

def configure_mikrotik(ip, username, password):
    allow_firewall_address(ip, username, password)
    configure_ssh_for_user(ip, username, password, "myuser", group="full")

def main():
    csv_file = "./devices.csv"  # Update with your actual file path
    
    try:
        with open(csv_file, newline='') as file:
            reader = csv.DictReader(file)
            for row in reader:
                try:
                    configure_mikrotik(
                        ip=row['ip'],
                        username=row['username'],
                        password=row['password'],
                    )
                except Exception as e:
                    print(f"Error processing row for {row.get('ip', 'unknown')}: {str(e)}")
    except FileNotFoundError:
        print(f"CSV file not found: {csv_file}")
    except Exception as e:
        print(f"Error reading CSV file: {str(e)}")

if __name__ == "__main__":
    main()