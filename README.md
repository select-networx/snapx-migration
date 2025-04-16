Snapx Migration Assistants
===
These scripts assist in migrating existing setups (Mikrotik only at this point) to the new Snapx platform.

First Steps (Mikrotik)
===
- You need to obtain configuration details, and copy the included [Example Configuration File](./mikrotik/config.ini.example) into `mikrotik/config.ini`, and change the values.
- You need to get details of the devices that are to be reconfigured, and populate the [Example Devices File](./mikrotik/devices.csv.example) file accordingly, giving it a filename of `mikrotik/devices.csv`.


Running the script
===
install the paramiko dependency: `pip install paramiko`
Run the script `python mikrotik/reconfig.py` without any arguments to use defaults.


Errors
===
When running the script, there might be some lines in the output that report as `failed` like so:

```
Executing: ip hotspot profile add name=sn_choice html-directory=sn_choice
✗ Command failed!
```

This would indicate that the profile might already exist, we've tried to use a name that would not 
be common in the wild.

