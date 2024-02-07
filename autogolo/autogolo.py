#!/usr/bin/env python
import argparse
import logging
import paramiko
import os
import json
from getpass import getpass
import pexpect
import subprocess
import shlex

"""
    Script to automate ligolo tunnels creation.
    This script will connect to remote host, get routes, copy ligolo agent
    Then will setup local tunnel interface, routes, and start ligolo
"""
#####  CONFIGURATION ######
# REPLACE PATHS HERE
LIGOLO_AGENT = "/opt/ligolo-ng/agentlin64"
LIGOLO_PROXY = "/opt/ligolo-ng/proxyin64"

CACHE_PATH = "/tmp/autogolo"

# Do not get routes for tunnel / docker / ... interface
ROUTE_EXCLUDE = ["tun", "docker"]
# Ignore /32 Routes
IGNORE_SLASH32 = True

# Base ligolo port: (effective port will be this + ligolo_id)
LIGOLO_BASE_PORT = 11600

# ==================================
args = None

state = {}


FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
logging.basicConfig(format=FORMAT, level=logging.INFO)  # Change level here
logger = logging.getLogger(__name__)


def cleanup():
    pass


def check_privileges():
    if not os.environ.get("SUDO_UID") and os.geteuid() != 0:
        raise PermissionError(
            "You need to run this script with sudo or as root.")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-ho",
        "--host",
        help="Target IP/Host",
        required=True
    )
    parser.add_argument(
        "-i",
        "--ligolo-id",
        help="Ligolo Session ID",
        type=int,
        default=1
    )
    parser.add_argument(
        "-t",
        "--thru",
        help="Tunnel goes through instance",
        type=int,
        default=None
    )
    parser.add_argument(
        "-u",
        "--user",
        help="User",
        required=True
    )
    parser.add_argument(
        "-pw",
        "--password",
        help="Password",
    )
    parser.add_argument(
        "-p",
        "--port",
        help="Port",
        default=22
    )
    parser.add_argument(
        "-c",
        "--clean",
        help="Cleanup only (remove routes, tunnels, etc...)",
        action='store_true'
    )
    args = parser.parse_args()
    if not args.password:
        args.password = getpass()
    return args


def get_command_output_lines(cmd, raise_if_stderr=True):
    global args
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(args.host, args.port, username=args.user,
                   password=args.password)
    logger.debug("Executing %s on host %s", cmd, args.host)
    stdin, stdout, stderr = client.exec_command(cmd)
    stdout = stdout.readlines()
    stderr = stderr.strip()
    if not stderr and raise_if_stderr:
        logger.error("Error in command %s:\n%s", cmd, stderr)
        raise Exception(f"Error in command {cmd}:\n{stderr}")
    client.close()
    logger.debug("%s = %s", cmd, stdout)

    return stdout


def write_state():
    global state, args, CACHE_PATH
    logger.debug("Writing state...")
    with open(os.path.join(CACHE_PATH, f"{args.ligolo_id}.json"), "w") as f:
        f.write(json.dumps(state, indent=4))


def copy_file(filename, remotepath="~"):
    global args
    logger.debug("Copying %s to %s", filename, args.host)
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    ssh.connect(args.host, username=args.user, password=args.password)
    scp = ssh.open_sftp()
    basename = os.path.basename(filename)
    scp.put(filename, os.path.join(remotepath, basename))

    # Close the SCP client
    scp.close()

    # Close the SSH client
    ssh.close()


def get_remote_routes():
    global state, ROUTE_EXCLUDE
    state["routes"] = []
    for route in get_command_output_lines("ip route"):
        route = route.strip()
        if not route:
            continue
        if "default" in route:
            continue
        for rex in ROUTE_EXCLUDE:
            if rex in route:
                logger.debug("Not including route %s", route)
                continue
        route = route.split(" ")[0]
        if "/32" in route and IGNORE_SLASH32:
            logger.debug("Ignoring /32 route %s", route)
            continue
        state["routes"].append(route)
    logger.info("Remote routes: %s", state["routes"])
    write_state()

def run_local_command(cmd):
    global state
    logger.debug("Running local command %s", cmd)
    proc = subprocess.run(shlex.split(cmd), stdout=subprocess.PIPE,  stderr=subprocess.PIPE)
    if proc.returncode != 0:
        logger.error("Error happened in command %s: %s", cmd, proc.stderr)
        proc.check_returncode()
    state["shell_cmds"].append(cmd)
    logger.debug("%s:\n%s\nErr:\n%s",cmd, proc.stdout, proc.stderr)
    return proc.stdout
    

def create_tunnels_and_routes():
    global args
    run_local_command()

def show_shell_commands():
    global state
    logger.info("#"*50 + "\nShell Commands:\n%s\n" +
                "#"*50, "\n".join(state["shell_cmds"]))


def main():
    global args
    check_privileges()
    args = parse_args()
    get_remote_routes()
    create_tunnels_and_routes()
    show_shell_commands()


if __name__ == "__main__":
    main()
