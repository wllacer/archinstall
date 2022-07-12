# WORK IN PROGRESS
from copy import deepcopy, copy
from dataclasses import asdict
from os import system

from archinstall.lib.disk import BlockDevice, fs_types
from archinstall.lib.output import log

from archinstall.lib.menu.menu import Menu
from archinstall.lib.menu.text_input import TextInput
from archinstall.lib.menu.selection_menu import GeneralMenu, Selector
from archinstall.lib.menu.list_manager import ListManager
from archinstall.lib.user_interaction.subvolume_config import SubvolumeList

from .dataclasses import PartitionSlot, DiskSlot, StorageSlot
from .discovery import hw_discover
from .helper import unit_best_fit, units_from_model
from .output import FormattedOutput

from typing import Any, TYPE_CHECKING  # , Dict, Optional, List

if TYPE_CHECKING:
	_: Any

# TODO generalize


# @dataclass
# class FlexSize:
# 	# TODO check nones
# 	input_value: Union[str, int]
#
# 	@property
# 	def sectors(self):
# 		return int(convert_units(self.input_value, 's', 's'))
#
# 	@property
# 	def normalized(self):
# 		return unit_best_fit(self.sectors, 's')
#
# 	def pretty_print(self):
# 		return f"{self.sectors:,} ({self.normalized})"
#
# 	def adjust_other(self, other):
# 		if other.input_value.strip().endswith('%'):
# 			pass
# 		else:
# 			_, unit = split_number_unit(self.input_value)
# 			if unit:
# 				other.input_value = f"{convert_units(other.sectors, unit, 's')} {unit.upper()}"


# TODO check real format of (mount|format)_options
# TODO convert location as a StorageSlot instead of FlexSize
# A prompt i need
class PartitionMenu(GeneralMenu):
	def __init__(self, object, caller=None, disk=None):
		# Note if object.sizeInput has -1 it is a new partition. is a small trick to keep object passed as reference
		self.data = object
		self.caller = caller
		# if there is a listmanager disk comes from the list not the parameter.
		# if no parameter
		self._list = self.caller._data if isinstance(caller, ListManager) else []
		if self._list:
			self.disk = object.parent(self._list)
		elif disk:
			self.disk = disk
		else:
			my_disk = BlockDevice(object.device)
			self.disk = DiskSlot(my_disk.device, 0, my_disk.size, my_disk.partition_type)
		self.ds = {}
		self.ds = self._conversion_from_object()
		super().__init__(data_store=self.ds)

	def _conversion_from_object(self):
		my_dict = deepcopy(asdict(self.data) if isinstance(self.data, PartitionSlot) else {})  # TODO verify independence
		# print('before')
		# print(my_dict)
		# if my_dict['startInput'] != -1:
		# 	my_start = FlexSize(my_dict['startInput'])
		# else:
		# 	my_start = None
		# if my_dict['sizeInput'] != -1:
		# 	my_size = FlexSize(my_dict['sizeInput'])
		# else:
		# 	my_size = None
		my_dict['location'] = StorageSlot(self.data.device, self.data.start, self.data.size)
		del my_dict['startInput']
		del my_dict['sizeInput']
		if 'btrfs' in my_dict:
			my_dict['subvolumes'] = deepcopy(my_dict['btrfs'])
			del my_dict['btrfs']
		# temporary
		if 'type' not in my_dict:
			my_dict['type'] = 'primary'
		return my_dict

	def _conversion_to_object(self):
		for item in self.ds:
			if item == 'location':
				self.data['startInput'] = self.ds['location'].startInput
				self.data['sizeInput'] = self.ds['location'].sizeInput
			elif item == 'subvolumes':
				self.data['btrfs'] = self.ds['subvolumes']
			else:
				self.data[item] = self.ds[item]

	def _setup_selection_menu_options(self):
		self._menu_options['location'] = Selector(str(_("Physical layout")),
									self._select_physical,
									display_func=self._show_location,
									enabled=True)
		self._menu_options['type'] = Selector(str(_("Partition type")),
							enabled=False)
		# TODO ensure unicity
		self._menu_options['mountpoint'] = Selector(str(_("Mount Point")),
							lambda prev: self._generic_string_editor(str(_('Edit Mount Point :')), prev),

							dependencies=['filesystem'], enabled=True)
		self._menu_options['filesystem'] = Selector(str(_("File System Type")),
							self._select_filesystem,
							enabled=True)
		self._menu_options['filesystem_format_options'] = Selector(str(_("File System Format Options")),
							lambda prev: self._generic_string_editor(str(_('Edit format options :')), prev),
							dependencies=['filesystem'], enabled=True)
		self._menu_options['filesystem_mount_options'] = Selector(str(_("File System Mount Options")),
							lambda prev: self._generic_string_editor(str(_('Edit mount options :')), prev),
							dependencies=['filesystem'], enabled=True)
		self._menu_options['subvolumes'] = Selector(str(_("Btrfs Subvolumes")),
							self._manage_subvolumes,
							dependencies=['filesystem'],
							enabled=True if self.ds.get('filesystem') == 'btrfs' else False)  # TODO only if it is btrfs
		self._menu_options['boot'] = Selector(str(_("Is bootable")),
							self._select_boot,
							enabled=True)
		self._menu_options['encrypted'] = Selector(str(_("Encrypted")),
							lambda prev: self._generic_boolean_editor(str(_('Set ENCRYPTED partition :')), prev),
							enabled=True)
		# readonly options
		if self.ds.get('uuid'):
			self._menu_options['actual_mountpoint'] = Selector(str(_("Actual mount")),
								enabled=True)
			if self.ds.get('filesystem') == 'btrfs':
				self._menu_options['actual_subvolumes'] = Selector(str(_("Actual Btrfs Subvolumes")),
									enabled=True)
			self._menu_options['uuid'] = Selector(str(_("uuid")),
								enabled=True)

		self._menu_options['save'] = Selector(str(_('Save')),
													exec_func=lambda n, v: True,
													enabled=True)
		self._menu_options['cancel'] = Selector(str(_('Cancel')),
													func=lambda pre: True,
													exec_func=lambda n, v: self.fast_exit(n),
													enabled=True)
		self.cancel_action = 'cancel'
		self.save_action = 'save'
		self.bottom_list = [self.save_action, self.cancel_action]

	def fast_exit(self, accion):
		if self.option(accion).get_selection():
			for item in self.list_options():
				if self.option(item).is_mandatory():
					self.option(item).set_mandatory(False)
		return True

	def exit_callback(self):
		# we exit without moving data
		if self.option(self.cancel_action).get_selection():
			return
		# if no location is given we abort
		if self.ds.get('location') is None:
			return
		self._conversion_to_object()

	def _generic_string_editor(self, prompt, prev):
		return TextInput(prompt, prev).run()

	def _generic_boolean_editor(self, prompt, prev):
		if prev:
			base_value = 'yes'
		else:
			base_value = 'no'
		response = Menu(prompt, ['yes', 'no'], preset_values=base_value).run()
		if response.value == 'yes':
			return True
		else:
			return False

	def _show_location(self, location):
		# return f" start : {location.pretty_print('start')}, size : {location.pretty_print('size')}"
		return f"start {location.startInput}, size {location.sizeInput}"

	def _select_boot(self, prev):
		value = self._generic_boolean_editor(str(_('Set bootable partition :')), prev)
		# only a boot per disk is allowed
		if value and self._list:
			bootable = [entry for entry in self.disk.partition_list(self._list) if entry.boot]
			if len(bootable) > 0:
				log(_('There exists another bootable partition on disk. Unset it before defining this one'))
				if self.disk.type.upper() == 'GPT':
					log(_('On GPT drives ensure that the boot partition is an EFI partition'))
				input()
				return prev
		# TODO It's a bit more complex than that. This is only for GPT drives
		# problem is when we set it backwards
		if value and self.disk.type.upper() == 'GPT':
			self.ds['mountpoint'] = '/boot'
			self.ds['filesystem'] = 'FAT32'
			self.ds['encrypted'] = False
			self.ds['type'] = 'EFI'   # TODO this has to be done at the end of processing
		return value

	def _select_filesystem(self, prev):
		fstype_title = _('Enter a desired filesystem type for the partition: ')
		fstype = Menu(fstype_title, fs_types(), skip=False, preset_values=prev).run()
		#  TODO broken escape control
		# if fstype.type_ == MenuSelectionType.Esc:
		# 	return prev
		if not fstype.value:
			return None
		# changed FS means reformat if the disk exists
		if fstype.value != prev and self.ds.get('uuid'):
			self.ds['wipe'] = True
		if fstype.value == 'btrfs':
			self.option('subvolumes').set_enabled(True)
		else:
			self.option('subvolumes').set_enabled(False)
		return fstype.value

	# this block is for assesing space allocation. probably it ougth to be taken off the class
	def _get_gaps_in_disk(self, list_to_check):
		if list_to_check is None:
			tmp_list = hw_discover([self.disk.device])
			return self._get_gaps_in_disk(tmp_list)
		elif len(list_to_check) == 0:
			return []
		else:
			tmp_list = [part for part in self.disk.partition_list(list_to_check) if part != self.data]
			return self.disk.gap_list(tmp_list)

	def _get_current_gap_pos(self, gap_list, need):
		if not need.start or need.start < 0:
			return None
		for i, gap in enumerate(gap_list):
			if gap.start <= need.start < gap.end:
				return i
		return None

	def _adjust_size(self, original, need):
		if str(need.sizeInput).strip().endswith('%'):
			need.sizeInput = original.sizeInput
		newsize = need.size - (need.start - original.start)
		need.sizeInput = units_from_model(newsize, original.sizeInput)

	def _show_gaps(self, gap_list):
		screen_data = FormattedOutput.as_table_filter(gap_list, ['start', 'end', 'size', 'sizeN'])
		print('Current free space is')
		print(screen_data)

	def _ask_for_start(self, gap_list, need):
		pos = self._get_current_gap_pos(gap_list, need)
		original = copy(need)
		print(f"Current allocation need is start:{need.pretty_print('start')} size {need.pretty_print('size')}")
		if pos:
			prompt = _("Define a start sector for the partition. Enter a value or \n"
					"c to get the first sector of the current slot \n"
					"q to quit \n"
					"==> ")
			starts = need.startInput
			starts = TextInput(prompt, starts).run()
			if starts == 'q':
				return 'quit'
			elif starts == 'c':
				starts = gap_list[pos].startInput
		else:
			prompt = _("Define a start sector for the partition. Enter a value or \n"
					"f to get the first sector of the first free slot which can hold a partition\n"
					"l to get the first sector of the last free slot \n"
					"q to quit \n"
					"==> ")
			starts = need.startInput
			starts = TextInput(prompt, starts).run()
			if starts == 'q':
				return need, 'quit'
			elif starts == 'f':
				starts = gap_list[0].startInput  # TODO 32 o 4K
				pos = 0
			elif starts == 'l':
				starts = gap_list[-1].startInput
				pos = len(gap_list) - 1

		need.startInput = starts
		pos = self._get_current_gap_pos(gap_list, need)
		if pos is None:
			print(f"Requested start position {need.pretty_print('start')}not in an avaliable slot. Try again")
			need.startInput = original.startInput
			return 'repeat'
		if gap_list[pos].start <= need.start < gap_list[pos].end:
			self._adjust_size(original, need)
			return None

	def _ask_for_size(self, gap_list, need):
		# TODO optional ... ask for size confirmation
		original = copy(need)
		print(f"Current allocation need is start:{need.pretty_print('start')} size {need.pretty_print('size')}")
		pos = self._get_current_gap_pos(gap_list, need)
		if pos is not None:
			maxsize = gap_list[pos].size - need.start
			maxsizeN = unit_best_fit(maxsize, 's')
			prompt = _("Define a size for the partition max {}\n \
		as a quantity (with units at the end) or a percentaje of the free space (ends with %),\n \
		or q to quit \n ==> ".format(f"{maxsize} s. ({maxsizeN})"))

			sizes = need.sizeInput
			sizes = TextInput(prompt, sizes).run()
			sizes = sizes.strip()
			if sizes.lower() == 'q':
				return 'quit'
			if sizes.endswith('%'):
				# from gap percentage to disk percentage
				pass  # TODO
			need.sizeInput = sizes
			if need.size > maxsize:
				print(_('Size {} exceeds the maximum size {}'.format(need.pretty_print('size'), f"{maxsize} s. ({maxsizeN})")))
				need = original
				return 'repeat'
			return None
		else:
			return 'quit'

	def _select_physical(self, prev):
		# from os import system
		# an existing partition can not be physically changed
		if self.data.uuid:
			return prev
		# TODO The gap list should respect alignment and minimum size
		gap_list = self._get_gaps_in_disk(self._list)
		my_need = copy(prev)
		while True:
			system('clear')
			self._show_gaps(gap_list)
			action = 'begin'
			while action:
				my_need = copy(prev)  # I think i don't need a deepcopy
				action = self._ask_for_start(gap_list, my_need)
				if action == 'quit':
					return prev
			action = 'begin'
			while action:
				my_need_full = copy(my_need)
				action = self._ask_for_size(gap_list, my_need_full)
				if action == 'quit':
					return prev
			return my_need_full

	def _manage_subvolumes(self, prev):
		if self.option('filesystem').get_selection() != 'btrfs':
			return []
		if prev is None:
			prev = []
		return SubvolumeList(_("Manage btrfs subvolumes for current partition"), prev).run()
