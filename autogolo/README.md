# Installation
Install python required modules, and make the script executable
```
pip install -r requirements.txt
chmod +x autogolo.py
```

# Usage

**Always run as root**
```
usage: autogolo.py [-h] -ho HOST [-id LIGOLO_ID] -i LOCAL_IP [-t THRU] -u USER [-pw PASSWORD] [-p PORT] [-c]
                   [-l LISTENERS]

options:
  -h, --help            show this help message and exit
  -ho HOST, --host HOST
                        Target IP/Host
  -id LIGOLO_ID, --ligolo-id LIGOLO_ID
                        Ligolo Session ID
  -i LOCAL_IP, --local-ip LOCAL_IP
                        Local IP
  -t THRU, --thru THRU  Tunnel goes through instance
  -u USER, --user USER  User
  -pw PASSWORD, --password PASSWORD
                        Password
  -p PORT, --port PORT  Port
  -c, --clean           Cleanup only (remove routes, tunnels, etc...)
  -l LISTENERS, --listeners LISTENERS
                        Automatically create this amount of ligolo listeners. Default 5.
```

# Basic Example

# Double Pivot Example