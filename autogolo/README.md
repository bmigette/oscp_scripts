# Installation
Install python required modules, and make the script executable
```
pip install -r requirements.txt
chmod +x autogolo.py
```

# Usage

**Always run as root**
```
┌──(admin㉿kali) - 15:43:55 - [/opt/oscp_scripts/autogolo]
└─$ sudo ./autogolo.py -h
usage: autogolo.py [-h] -ho HOST [-i LIGOLO_ID] [-t THRU] -u USER [-pw PASSWORD] [-p PORT] [-c]

options:
  -h, --help            show this help message and exit
  -ho HOST, --host HOST
                        Target IP/Host
  -i LIGOLO_ID, --ligolo-id LIGOLO_ID
                        Ligolo Session ID
  -t THRU, --thru THRU  Tunnel goes through instance
  -u USER, --user USER  User
  -pw PASSWORD, --password PASSWORD
                        Password
  -p PORT, --port PORT  Port
  -c, --clean           Cleanup only (remove routes, tunnels, etc...)
```

# Basic Example

# Double Pivot Example