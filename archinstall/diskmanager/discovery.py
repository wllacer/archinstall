import archinstall
import pathlib
import os
from pprint import pprint
# from pudb import set_trace
import logging
from copy import deepcopy, copy
import re

from typing import Any, TYPE_CHECKING, Dict, Optional, List

if TYPE_CHECKING:
	_: Any

from archinstall.lib.user_interaction.disk_conf import get_default_partition_layout
from archinstall.lib.user_interaction.subvolume_config import SubvolumeList
from .dataclasses import *
def device_size_sectors(path):
	nombre = path.split('/')[-1]
	filename = f"/sys/class/block/{nombre}/size"
	with open(filename,'r') as file:
		size = file.read()
	return int(size) - 33 # The last 34 sectors are used by the system in GPT drives. If I substract 34 i miss 1 sector

def device_sector_size(path):
	nombre = path.split('/')[-1]
	filename = f"/sys/class/block/{nombre}/queue/logical_block_size"
	with open(filename,'r') as file:
		size = file.read()
	return int(size)

def get_device_info(device):
	try:
		information = archinstall.blkid(f'blkid -p -o export {device}')
	# TODO: No idea why F841 is raised here:
	except archinstall.SysCallError as error: # noqa: F841
		if error.exit_code in (512, 2):
			# Assume that it's a loop device, and try to get info on it
			try:
				information = archinstall.get_loop_info(device)
				if not information:
					raise archinstall.SysCallError("Could not get loop information", exit_code=1)

			except archinstall.SysCallError:
				information = archinstall.get_blockdevice_uevent(pathlib.Path(device).name)
		else:
			raise error

	information = archinstall.enrich_blockdevice_information(information)
	return information

def list_subvols(object):
	subvol_info = [archinstall.Subvolume(subvol.name,str(subvol.full_path)) for subvol in object.subvolumes]
	return subvol_info

def createPartitionSlot(path,partition):
	# TODO encrypted volumes, get internal info
	# TODO btrfs subvolumes if not mounted
	# TODO aditional fields
	# TODO swap volumes and other special types
	try:
		device_info = get_device_info(path)[path]

		if device_info['TYPE'] == 'crypto_LUKS':
			encrypted = True
			# encrypted_partitions.add(res)
		else:
			encrypted = False
		# TODO make the subvolumes work
		if partition.filesystem == 'btrfs':
			subvol_info = list_subvols(partition)
		else:
			subvol_info = []
		partition_entry = PartitionSlot(partition.parent,
			device_info['PART_ENTRY_OFFSET'],
			device_info['PART_ENTRY_SIZE'],
			type = device_info.get('PART_ENTRY_NAME',device_info.get('PART_ENTRY_TYPE','')),
			boot = partition.boot,
			encrypted = encrypted,
			wipe = False,
			mountpoint = None,
			filesystem = partition.filesystem,
			btrfs=[],
			uuid= partition.uuid,
			partnr= device_info['PART_ENTRY_NUMBER'],
			path= device_info['PATH'],
			actual_mountpoint = partition.mountpoint,  # <-- this is false
			actual_subvolumes= subvol_info
		)
		return partition_entry
	except KeyError as e:
		print(f"Horror at {path} Terror at {e}")
		pprint(device_info)
		exit()

def hw_discover(disks=None):
	global_map = []

	archinstall.log(_("Waiting for the system to get actual block device info"),fg="yellow")
	hard_drives = []
	disk_layout = {}
	encrypted_partitions = set()
	my_disks = {item.path for item in disks} if disks else {}
	# warning if executed without root privilege everything is a block device
	all_storage = archinstall.all_blockdevices(partitions=True)

	for path in sorted(all_storage):
		storage_unit = all_storage[path]
		match type(storage_unit):
			case archinstall.BlockDevice:
				if my_disks and path not in my_disks:
					continue
				# TODO BlockDevice gives
				global_map.append(DiskSlot(path,0,f"{storage_unit.size} GiB",storage_unit.partition_type))
			case  archinstall.Partition:
				if my_disks and storage_unit.parent not in my_disks:
					continue
				global_map.append(createPartitionSlot(path,storage_unit))
			case archinstall.DMCryptDev:
				# to do
				print(' enc  ',path)
			case _:
				print(' error ',path, storage_unit)
	return global_map

def create_global_block_map(disks=None):
	""" OBSOLETE
	    For reference of missing parts only
	"""
	archinstall.log(_("Waiting for the system to get actual block device info"),fg="yellow")
	result = archinstall.all_blockdevices(partitions=True)
	hard_drives = []
	disk_layout = {}
	encrypted_partitions = set()
	my_disks = {item.path for item in disks} if disks else {}

	for res in sorted(result):
		device_info = {}
		for entry in get_device_info(res):
			device_info = device_info | get_device_info(res)[entry]
		print(res,type(result[res]))
		if isinstance(result[res],archinstall.BlockDevice): # disk
			if my_disks and res not in my_disks:
				continue
			hard_drives.append(result[res])
			if result[res].size == 0:
				continue
			try:
				disk_layout[res] = {'partitions':[],
									'structure':[], # physical structure
							'wipe':False,
							'pttype':result[res].info.get('PTTYPE',None),
							'ptuuid':result[res].info.get('PTUUID',None),
							'sizeG':result[res].size,
							'size':device_size_sectors(res),
							'sector_size':device_sector_size(res)}

			except KeyError as e:
				print(f"Horror at {res} Terror at {e}")
				pprint(device_info)
				exit(1)

		if isinstance(result[res],archinstall.Partition):
			if my_disks and result[res].parent not in my_disks:
				continue
			try:
				if device_info['TYPE'] == 'crypto_LUKS':
					encrypted = True
					encrypted_partitions.add(res)
				else:
					encrypted = False
				# TODO make the subvolumes work
				if result[res].filesystem == 'btrfs':
					subvol_info = list_subvols(result[res])
				else:
					subvol_info = {}
				partition = {
					"id": f"{result[res].parent} {device_info['PART_ENTRY_OFFSET']:>15}",
					"type" : device_info.get('PART_ENTRY_NAME',device_info.get('PART_ENTRY_TYPE','')),
					"start" : device_info['PART_ENTRY_OFFSET'],
					"size" : device_info['PART_ENTRY_SIZE'],
					# "sizeG": round(int(device_info['PART_ENTRY_SIZE']) * 512 / archinstall.GIGA,1),
					"boot" : result[res].boot,
					"encrypted" : encrypted,
					"wipe" : False,
					"actual_mountpoint" : result[res].mountpoint,  # <-- this is false
					"mountpoint" : None,
					"filesystem" : {
						"format" : result[res].filesystem
					},
					"uuid": result[res].uuid,
					"partnr": device_info['PART_ENTRY_NUMBER'],
					"path": device_info['PATH'],
					"actual_subvolumes": subvol_info,
					"subvolumes":[]
				}
				disk_layout[result[res].parent]['structure'].append(partition)
			except KeyError as e:
				print(f"Horror at {res} Terror at {e}")
				pprint(device_info)
				exit()
			# TODO encrypted volumes
			# TODO btrfs subvolumes
			# TODO aditional fields
			# TODO swap volumes
			# gaps
		if isinstance(result[res],archinstall.DMCryptDev):
			# TODO we need to ensure the device is opened and later closed to get the info
			# Problems with integration. Returned prior to normal partitions
			print('==>')
			print(res)
			print(result[res])
			print('\t',result[res].name)
			print('\t',result[res].path)
			print('\t',result[res].MapperDev)
			print('\t\t',result[res].MapperDev.name)
			print('\t\t',result[res].MapperDev.partition)
			print('\t\t',result[res].MapperDev.partition.path)  # <-- linkage
			print('\t\t',result[res].MapperDev.path)
			print('\t\t',result[res].MapperDev.filesystem) # <--
			print('\t\t',list_subvols(result[res].MapperDev)) # <-- is empty if not mounted/
			print('\t\t',result[res].MapperDev.mount_information) # <-- error if not mounted
			print('\t\t',result[res].MapperDev.mountpoint) # <-- error if not mounted
			print('\t',result[res].mountpoint)
			print('\t',result[res].filesystem)
			pprint(device_info)
			print()
			# TODO move relevant information to the corresponding partition
			input('yep')
	GLOBAL_BLOCK_MAP.update(disk_layout)
