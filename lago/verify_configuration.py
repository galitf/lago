#
# Copyright 2014 Red Hat, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA
#
# Refer to the README and COPYING files for full details of the license
#

# permissions
# group
# and configure
# ask the user to run with sudo

#groups qemu,libvirt - USERNAME
#groups USERNAME - qemu

#/var/lib/lago
# owner USERNAME:USERNAME
# systemctl restart libvirtd

import os
import commands
import argparse
import sys
import getpass
import platform

class VerifyLagoStatus(object):
    """
    Verify Lago configuration
    """
    verificationStatus = False
    def __init__(self,username,envs_dir,groups,nested,virtualization,lago_env_dir,kvm_configure,install_pkg,verify_status):
        self.username = username
        self.envs_dir = envs_dir
        self.groups = groups
        self.nested = nested
        self.virtualization = virtualization
        self.lago_env_dir = lago_env_dir
        self.kvm_configure = kvm_configure
        self.install_pkg = install_pkg
        VerifyLagoStatus.verificationStatus = verify_status

    def displayLagoStatus(self):
        """
        Display Lago configuration status (OK/Not-OK) Verify Lago configuration
        """
        print "Configuration Status:"
        print "====================="
        print "Username used by Lago: " + self.username
        print "Environment directory used by Lago: " + self.envs_dir 
        print "Nested: " + self.return_status(self.nested)
        print "Virtualization: " +  self.return_status(self.virtualization)
        print "Groups: " + self.return_status(self.groups)
        print "Lago Environment Directory " +  self.envs_dir + ": " + self.return_status(self.lago_env_dir)
        print "Kvm Configure: " +  self.return_status(self.kvm_configure)
        print "All packages installed: " +  self.return_status(self.install_pkg)
        print "Status: " + str(VerifyLagoStatus.verificationStatus)
        if (VerifyLagoStatus.verificationStatus == False):
            print "Please read configuration setup:"
            print "  http://lago.readthedocs.io/en/latest/Installation.html#troubleshooting"
            return 2
        else: 
            return 0    
        
    def fixLagoConfiguration(self):
        """
        Fix Lago configuration if possible
        """
        print "Nested: " + self.return_status(self.nested)
        print "Virtualization: " +  self.return_status(self.virtualization)
        print "Groups: " + self.return_status(self.groups)
        print "Lago Environment Directory " +  self.envs_dir + ": " + self.return_status(self.lago_env_dir)
        print "Kvm Configure: " +  self.return_status(self.kvm_configure)
        print "All packages installed: " +  self.return_status(self.install_pkg)
        print "Status: " + str(VerifyLagoStatus.verificationStatus)
        if (VerifyLagoStatus.verificationStatus == False):
            print "Please read configuration setup:"
            print "  http://lago.readthedocs.io/en/latest/Installation.html#troubleshooting"

    def return_status(self,status):
        """
        Display OK or Not-OK
        """
        if status == 'Y':
            return "OK"
        else:
            return "Not-OK"    

def validate_status(list_status):
    """
    Validate the status of all configuration checks
    """
    status = True
    if 'N' in list_status :
        status = False
    return status    

def check_virtualization():
    """
    Check if KVM configure in BIOS
    """    
    if os.system("dmesg | grep -q 'kvm: disabled by BIOS'"):
      virtualization =  'N'
    else:
      virtualization =  'Y'
    return virtualization

def get_cpu_vendor():
    """
    Get the CPU vendor ie. intel/amd
    """ 
    Input = commands.getoutput("lscpu | awk '/Vendor ID/{print $3}'")   
    if Input == 'GenuineIntel': 
        vendor = "intel"
    elif vendor == 'AuthenticAMD':
        #print "amd"
        vendor = "amd"
    else:
        #print "unrecognized CPU vendor: $vendor, only Intel/AMD are supported"
        vendor = "problem"
    return vendor

def is_virtualization_enable():
    """
    Check if Virtualization enabled
    """ 
    res = commands.getoutput("cat /proc/cpuinfo | egrep 'vmx|svm'")   
    if res == "": 
        status = "N"
    else:
        status = "Y"
    return status

def check_kvm_configure(vendor):
    """
    Check if KVM configure
    """ 
    res = commands.getoutput("lsmod | grep kvm_"+vendor)   
    if res == "": 
        status = "N"
    else:
        status = "Y"
    return status

def check_nested(vendor):
    """
    Check if nested is available
    """ 
    mod="kvm_"+vendor
    cmd = "cat /sys/module/"+mod+"/parameters/nested"
    is_enabled= commands.getoutput(cmd)
    if is_enabled == 'Y':
        return 'Y'
    else: 
        return 'N'

def check_groups(username):
    """
    Check the groups are confiugre correct for LAGO
    """ 
    ## all groups username in
    groups_username = commands.getoutput("groups " + username) 
    status_username = all(x in groups_username for x in ['qemu','libvirt','lago',username])
    groups_qemu = commands.getoutput("groups qemu") 
    status_qemu = all(x in groups_qemu for x in [username])
    if ( status_username &  status_qemu ):
        return 'Y'
    else: 
        return 'N'

def change_groups(username):
    """
    Update the groups according to LAGO permissions
    """ 
    os.system("usermod -a -G qemu,libvirt,lago " + username) 
    os.system("usermod -a -G " + username + " qemu" ) 

def check_permissions(envs_dirs,username):
    """
    Check directory permissions
    """ 
    status = True
    uid = int(commands.getoutput("id -u  " + username) )
    gid = int(commands.getoutput("getent group  " + username + " | awk -F: '{print $3}'") )

    for dirpath, dirnames, filenames in os.walk(envs_dirs):  
        for dirname in dirnames:  
            if ( os.stat(os.path.join(dirpath, dirname)).st_uid != uid ) &  (os.stat(os.path.join(dirpath, dirname)).st_gid != gid):
                status = False
        for filename in filenames:
            if ( os.stat(os.path.join(dirpath, filename)).st_uid != uid ) &  (os.stat(os.path.join(dirpath, filename)).st_gid != gid):
                status = False
    if ( status ):
        return 'Y'
    else: 
        return 'N'

def change_permissions(envs_dirs,username):
    """
    Change directory permissions
    """ 
    uid = int(commands.getoutput("id -u  " + username) )
    gid = int(commands.getoutput("getent group  " + username + " | awk -F: '{print $3}'") )  
    for dirpath, dirnames, filenames in os.walk(envs_dirs):  
        for dirname in dirnames:  
            os.chown(os.path.join(dirpath, dirname), uid, gid)
        for filename in filenames:
            os.chown(os.path.join(dirpath, filename), uid, gid)
 
def check_packages_installed():
    """
    Check if all required packages are installed
    """ 
    missing_pkg = []
    status = "Y"
    if  platform.linux_distribution()[0] == "CentOS Linux":
        pkg_list = ["mysql-community-server","epel-release", "centos-release-qemu-ev", "python-devel", "libvirt", "libvirt-devel" , "libguestfs-tools", "libguestfs-devel", "gcc", "libffi-devel", "openssl-devel", "qemu-kvm-ev"]
    else:
        pkg_list = ["python2-devel", "libvirt", "libvirt-devel" , "libguestfs-tools", "libguestfs-devel", "gcc", "libffi-devel", "openssl-devel", "qemu-kvm"]
    rpm_output = commands.getoutput("rpm -qa ")
    for pkg in pkg_list:        
        if pkg not in rpm_output:
            missing_pkg.append(pkg)  
            status =  'N'
    return (status,missing_pkg)

def install_missing_packages(missing_pkg):
    """
    Install missing packages
    """ 
    for pkg in missing_pkg:     
        os.system("yum install -y " + pkg) 
 
def reload_kvm():
    """
    reload kvm
    """

def reload_nested():
    """
    reload kvm
    """

def enable_service():
    """
    enable service
    """

def enable_services():
    """
    enable services
    """   

def reload_libvirtd():
    """
    reload libvirtd
    """
    output = os.system("systemctl restart libvirtd") 
    print "Reload:"+ str(output)
       

def check_user(username):
    """
    Check if user exists in passwd
    """ 
    msg=""
    uid = commands.getoutput("id -u  " + username) 
    if "no such user" in uid: 
        msg = "\'"+username+"\'"+ " username doesn't exists"
    return msg
        
def check_directory(envs_dir):
    """
    Check if directory exists
    """ 
    msg=""
    if (os.path.isdir(envs_dir)==False):
        msg = "\'"+envs_dir+"\'"+ " envs_dir doesn't exists"
    return msg    

def check_configuration(username,envs_dir):
    """
    Check the configuration of LAGO (what is configure)
    """ 
    vendor = get_cpu_vendor()
    nested = check_nested(vendor)
    #virtualization = check_virtualization()
    virtualization = is_virtualization_enable()
    groups = check_groups(username)
    lago_env_dir = check_permissions(envs_dir,username)
    kvm_configure = check_kvm_configure(vendor)
    (install_pkg,missing_pkg) = check_packages_installed()
    return (groups,nested,virtualization,lago_env_dir,kvm_configure,install_pkg)

def fix_configuration(username,envs_dir,groups,nested,virtualization,lago_env_dir,install_pkg):
    """
    Fix configuration, if possible
    """ 
    if (lago_env_dir == 'N'):
        change_permissions(envs_dir,username)
    if (groups == 'N'):
        change_groups(username)

    if (install_pkg == 'N'):
        print "Check missing packages: "
        install_missing_packages(missing_pkg)      
    reload_libvirtd()    
    # if nested
    # update the value of LagoStatus
    # reload libvirtd
