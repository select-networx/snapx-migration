Snapx Migration Assistants
===
These scripts assist in migrating existing setups (Mikrotik only at this point) to the new Snapx platform.

First Steps (Mikrotik)
===
- You need to obtain configuration details, and copy the included mikrotik/config.ini.example into mikrotik/config.ini, and change the values.
- You need to get details of the devices that are to be reconfigured, and populate the mikrotik/devices.csv file accordingly.


Running the script
===
install the paramiko dependency: `pip install paramiko`
Run the script `python mikrotik/reconfig.py` without any arguments to use defaults.