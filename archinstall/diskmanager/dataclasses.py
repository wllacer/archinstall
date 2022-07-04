import archinstall
from .helper import unit_best_fit, convert_units
from dataclasses import dataclass, field, asdict, KW_ONLY
from typing import List #, Any, Dict
# from pprint import pprint

def parent_from_list(objeto,lista):
	parent = [item for item in lista if item.device == objeto.device and isinstance(item,DiskSlot)]
	if len(parent) > 1:
		raise ValueError(f'Device {self.device} is more than one times on the list')
	elif len(parent) == 0:
		return None
	return parent[0]

@dataclass(eq=True)
class StorageSlot:
	device: str
	startInput: str
	sizeInput: str

	@property
	def start(self):
		return convert_units(self.startInput,'s','s')
	@property
	def size(self):
		return convert_units(self.sizeInput,'s','s')
	@property
	def sizeN(self):
		return unit_best_fit(self.size,'s')
	@property
	def end(self):
		return self.start + self.size - 1

	def __lt__(self,other):
		if isinstance(other,StorageSlot):
			if self.device == other.device:
				return self.start < other.start
			else:
				return self.device < other.device
		# TODO throw exception when not comparable

	def asdict(self):
		non_generated = {'start':self.start,'end':self.end,'size': self.size,'sizeN':self.sizeN}
		return asdict(self) | non_generated

	def asdict_filter(self,filter):
		# TODO there are alternate ways of code. which is the most efficient ?
		result = {}
		for key,value in self.asdict().items():
			if key in filter:
				result[key] = value
		return result

@dataclass
class DiskSlot(StorageSlot):
	type: str = None
	wipe: bool = False
	# TODO probably not here but code is more or less the same


	def create_gaps(self,lista):
		short_list = sorted([elem for elem in lista if elem.device == self.device and isinstance(elem,PartitionSlot)])
		gap_list = []
		start = 32
		for elem in short_list:
			if elem.start > start:
				# create gap
				gap_list.append(GapSlot(self.device,start,elem.start - start))  #OFF BY ONE perhaps
			start = elem.end + 1
		if start < self.end:
			gap_list.append(GapSlot(self.device,start,self.end - start + 1))
		return sorted(short_list + gap_list)

@dataclass
class GapSlot(StorageSlot):
	pass
	def parent(self,lista):
		return parent_from_list(self,lista)

@dataclass
class PartitionSlot(StorageSlot):
	# _:KW_ONLY
	mountpoint: str = None
	filesystem: str = None
	filesystem_options : str = None
	filesystem_format_options : str = None
	boot: bool = False
	encrypted: bool = False
	wipe: bool = False
	btrfs: List[archinstall.Subvolume] = None
	# info for existing partitions
	path: str = None
	actual_mountpoint: str = None
	actual_subvolumes: List[archinstall.Subvolume] = None
	uuid: str = None
	partnr: int = None
	type: str = 'primary'

	def parent_in_list(self,lista):
		return parent_from_list(self,lista)

	def order_nr(self,lista):  # self must be a member of the list
		siblings = sorted([item for item in lista if item.device == self.device and isinstance(item,PartitionSlot)])
		try:
			return siblings.index(self)
		except ValueError: # element not in list
			return -1

	#@classmethod
	#def from_dict(cls, entries: List[Dict[str, Any]]) -> List['VirtualPartitionSlot']:
		#partitions = []
		#for entry in entries:
			#partition = VirtualPartitionSlot(
				#start=entry.get('start', 0),
				#size=entry.get('size', 0),
				#encrypted=entry.get('encrypted', False),
				#mountpoint=entry.get('mountpoint', None),
				#filesystem=entry['filesystem']['format'],
				#wipe=entry['wipe']
			#)
			#partitions.append(partition)

		#return partitions

