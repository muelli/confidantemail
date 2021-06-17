import os
import re
import zipfile
import datetime
import struct
import logging
import flatstore
import filestore
import syncstore
import key_value_file

re_addr = re.compile("^(.+) ([0123456789abcdef]{40})$",re.IGNORECASE)
re_from = re.compile("^FROM: (.+) ([0123456789abcdef]{40})$",re.IGNORECASE)
re_to = re.compile("^TO: (.+) ([0123456789abcdef]{40})$",re.IGNORECASE)
re_cc = re.compile("^CC: (.+) ([0123456789abcdef]{40})$",re.IGNORECASE)
re_bcc = re.compile("^BCC: (.+) ([0123456789abcdef]{40})$",re.IGNORECASE)
re_ack = re.compile("^ACK-([0123456789abcdef]{40}): ([0123456789abcdef]{40})$",re.IGNORECASE)
re_subj = re.compile("^SUBJECT: (.*)$",re.IGNORECASE)
re_datetime = re.compile("^DATE: (\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ)$",re.IGNORECASE)
re_ab = re.compile("^ANNOUNCEBLOCK: ([0123456789abcdef]{40})$",re.IGNORECASE)
re_db = re.compile("^DATABLOCK: ([0123456789abcdef]{40})$",re.IGNORECASE)

id_new_messages = 'New Messages'
id_inbox = 'Inbox'
id_sent_messages = 'Sent'
id_drafts = 'Drafts'
id_deleted = 'Deleted'
id_archive = 'Archive'
id_send_pending = 'Send Pending'
id_ack_pending = 'Ack Pending'
id_forwarded_originals = 'Forwarded Originals'
id_system_messages = 'System Messages'

predefined_folders = [
	id_new_messages,
	id_inbox,
	id_sent_messages,
	id_drafts,
	id_deleted,
	id_send_pending,
	id_ack_pending,
	id_forwarded_originals,
	id_system_messages
]


# 'g' + name = global variable
# 'xF'+number = high folder number
# 'A'+number = folder name
# 'I'+folder = high_index
# 'E'+folder+index = message_id
# 'H'+folder+message_id = index
# 'F'+message_id = list of folders containing
# 'M'+message_id = headers dict

class folders:

	def __init__(self,folder_file_path,folder_log_path,local_store,outbox_store,outgoing_sync = None):
		self.sync_enabled = False
		self.kvf = key_value_file.key_value_file(folder_file_path,folder_log_path)
		self.local_store = local_store
		self.outbox_store = outbox_store
		self.outgoing_sync = outgoing_sync
		self.high_index = dict()
		self.slack_entries = dict()
		self.known_folders = dict()
		self.logger = logging.getLogger(__name__)
		self.load_folder_indexes()
		self.check_add_folder(id_new_messages)
		self.check_add_folder(id_inbox)
		self.check_add_folder(id_sent_messages)
		self.check_add_folder(id_drafts)
		self.check_add_folder(id_deleted)
		self.check_add_folder(id_send_pending)
		self.check_add_folder(id_ack_pending)
		self.check_add_folder(id_forwarded_originals)
		self.check_add_folder(id_system_messages)
		self.sync_enabled = True

	def close(self):
		if self.kvf != None:
			self.kvf.close()
			self.kvf = None
		if self.outgoing_sync != None:
			self.outgoing_sync.flush()

	def disable_sync(self):
		self.sync_enabled = False

	def enable_sync(self):
		self.sync_enabled = True

	def commit(self):
		if self.kvf != None:
			self.kvf.commit()
	
	def extract_incoming_message_headers(self,ann_id):
		ann_idH = ann_id.encode('hex')
		zip_path = self.local_store.getPath(ann_idH) + '.ZIP'
		sig_path = self.local_store.getPath(ann_idH) + '.SIG'
		if os.path.isfile(zip_path) == False:
			return False,'No zip file'
		if os.path.isfile(sig_path) == False:
			return False,'No sig file'

		try:
			zip = zipfile.ZipFile(zip_path,'r')
			headers_fh = zip.open('HEADER.TXT','r')
			header_lines = headers_fh.read().decode('utf-8')
			zip.close()
		except Exception as exc:
			return False,str(type(exc))+' on zip file'
			
		headers = dict()
		recips = [ ]
		acks = dict()
		
		headers['ID'] = ann_id
		headers['TY'] = 'I'
		for line in header_lines.split('\n'):
			line = line.rstrip('\r\n')
			m = re_from.match(line)
			if m:
				headers['FR'] = ( m.group(2).decode('hex'),m.group(1) )
				continue
			m = re_to.match(line)
			if m:
				recip = ( 'T',m.group(2).decode('hex'),m.group(1) )
				recips.append(recip)
				continue
			m = re_cc.match(line)
			if m:
				recip = ( 'C',m.group(2).decode('hex'),m.group(1) )
				recips.append(recip)
				continue
			m = re_bcc.match(line)
			if m:
				recip = ( 'B',m.group(2).decode('hex'),m.group(1) )
				recips.append(recip)
				continue
			m = re_ack.match(line)
			if m:
				acks[m.group(1).decode('hex')] = m.group(2).decode('hex')
				continue
			m = re_subj.match(line)
			if m:
				headers['SU'] = m.group(1)
				continue
			m = re_datetime.match(line)
			if m:
				headers['DA'] = m.group(1)
				continue
		headers['RE'] = recips
		headers['AK'] = acks
		return True,headers
	
	def extract_outgoing_message_headers(self,message_data,from_address,save_hash,state):
		recipients,recipients_full,attachments,reply_thread_id,forward_original_id,subject,body_text,body_html,body_xml,save_date = message_data
		headers = dict()
		headers['ID'] = save_hash
		headers['TY'] = 'O'
		headers['ST'] = state
		recips = [ ]
		m = re_addr.match(from_address)
		if m:
			headers['FR'] = ( m.group(2).decode('hex'),m.group(1) )
		else:
			headers['FR'] = from_address
		for recip in recipients_full:
			rtyp = recip[0]
			rnam = recip[2:]
			m = re_addr.match(rnam)
			if m:
				recips.append( ( rtyp,m.group(2).decode('hex'),m.group(1) ) )
			else:
				recips.append( ( rtyp,None,rnam ) )
		headers['RE'] = recips
		headers['SU'] = subject
		headers['DA'] = save_date
		return headers

	def save_message(self,announcement_id,headers):
		self.kvf.pickle('M'+announcement_id,headers)

	def message_exists(self,announcement_id):
		return self.kvf.exists('M'+announcement_id)

	def get_message(self,announcement_id):
		return self.kvf.unpickle('M'+announcement_id)

	def load_folder_indexes(self):
		self.folder_number_to_name = [ ]
		self.folder_name_to_number = dict()
		found,self.high_folder_number = self.kvf.unpickle('xF')
		if found == False:
			self.high_folder_number = -1
		else:
			for i in range(self.high_folder_number+1):
				found,name = self.kvf.unpickle('A' + struct.pack('I',i))
				if found:
					self.folder_name_to_number[name] = i
					self.folder_number_to_name.append(name)
				else:
					self.folder_number_to_name.append(None)
				#DBGOUT#print "folder",i,self.folder_number_to_name[i]

	def get_all_data_blocks_for_message(self,ann_id):
		ann_idH = ann_id.encode('hex')
		data_blocks = [ ]
		found,headers = self.get_message(ann_id)
		is_incoming = False
		if found == True and headers['TY'] == 'I':
			is_incoming = True
			foundA,announcement = self.local_store.retrieveHeaders(ann_idH)
			if foundA == True:
				for line in announcement:
					match = re_db.match(line)
					if match:
						blockhashH = match.group(1).upper()
						data_blocks.append(blockhashH)
		elif found == True and headers['TY'] == 'O':
			headername = self.local_store.getPath(ann_idH) + '.HDR'
			try:
				fh = open(headername,'r')
				headers = fh.read()
				fh.close()
				for line in headers.split('\n'):
					line = line.rstrip('\r\n')
					m = re_db.match(line)
					if m:
						data_blocks.append(m.group(1))
					m = re_ab.match(line)
					if m:
						data_blocks.append(m.group(1))
			except IOError:
				pass
		return data_blocks,is_incoming

	def delete_all_files_for_message(self,ann_id,outgoing_pending_only = False,allow_refetch = False,force_incoming = False):
		ann_idH = ann_id.encode('hex')
		ann_path = self.local_store.getPath(ann_idH)
		zip_path = ann_path + '.ZIP'
		sig_path = ann_path + '.SIG'
		dts_path = ann_path + '.DTS'
		hdr_path = ann_path + '.HDR'
		del_path = ann_path + '.DEL'
		
		delete_blocks,is_incoming = self.get_all_data_blocks_for_message(ann_id)
		if force_incoming == True:
			is_incoming = True
		if outgoing_pending_only == True and is_incoming == True:
			return True
		if is_incoming:
			if len(delete_blocks) > 0:
				foundH,headers = self.extract_incoming_message_headers(ann_id)
				if foundH == True:
					for block in headers['AK'].values():
						delete_blocks.append(block.encode('hex').upper())
			
			for block in delete_blocks:
				delete_path = self.local_store.getPath(block,False)	
				if os.path.isfile(delete_path):
					os.unlink(delete_path)
		else: # outgoing send pending
			for block in delete_blocks:
				self.outbox_store.__delitem__(block)
		if outgoing_pending_only == True:
			return True # only deletes the files in outbox

		try:
			if os.path.isfile(zip_path) == True:
				os.unlink(zip_path)
		except Exception:
			return False # file open and locked
		if os.path.isfile(ann_path) == True:
			os.unlink(ann_path)
		if os.path.isfile(sig_path) == True:
			os.unlink(sig_path)
		if os.path.isfile(dts_path) == True:
			os.unlink(dts_path)
		if os.path.isfile(hdr_path) == True:
			os.unlink(hdr_path)

		# Save deleted flag to prevent re-downloading
		if is_incoming == True and allow_refetch == False:
			filehandle = open(del_path,'w')
			filehandle.write(datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ") + '\n')
			filehandle.close()
		return True
				
	def check_add_folder_recurse(self,folder):
		if folder.find('\x00') >= 0:
			pre,last = folder.rsplit('\x00',1)
			self.check_add_folder_recurse(pre)
		self.check_add_folder(folder)

	def check_exist_folder(self,folder):
		return folder in self.folder_name_to_number

	def check_add_folder(self,folder):
		if folder not in self.folder_name_to_number:
			new_folder_number = -1
			if self.high_folder_number >= 0:
				for i in range(self.high_folder_number+1):
					if self.folder_number_to_name[i] == None:
						new_folder_number = i
						break
			if new_folder_number >= 0:
				self.folder_number_to_name[i] = folder
			else:
				self.high_folder_number += 1
				new_folder_number = self.high_folder_number
				self.folder_number_to_name.append(folder)
				self.kvf.pickle('xF',self.high_folder_number)
			self.folder_name_to_number[folder] = new_folder_number
			self.kvf.pickle('A' + struct.pack('I',new_folder_number),folder)
			if self.outgoing_sync != None and self.sync_enabled == True:
				self.outgoing_sync.addChange( [ 'AddCat',folder ] )

	def rename_folder(self,old_folder,new_folder):
		if old_folder not in self.folder_name_to_number:
			return

		folder_number = self.folder_name_to_number[old_folder]
		del self.folder_name_to_number[old_folder]
		self.folder_name_to_number[new_folder] = folder_number
		self.folder_number_to_name[folder_number] = new_folder
		self.kvf.pickle('A' + struct.pack('I',folder_number),new_folder)

		old_folders = self.folder_name_to_number.keys()
		old_base = old_folder + '\x00'
		old_base_len = len(old_base)
		new_base = new_folder + '\x00'
		for old_folder_sub in old_folders:
			if old_folder_sub[0:old_base_len] == old_base:
				new_folder_sub = new_base + old_folder_sub[old_base_len:]
				folder_number = self.folder_name_to_number[old_folder_sub]
				del self.folder_name_to_number[old_folder_sub]
				self.folder_name_to_number[new_folder_sub] = folder_number
				self.folder_number_to_name[folder_number] = new_folder_sub
				self.kvf.pickle('A' + struct.pack('I',folder_number),new_folder_sub)
		if self.outgoing_sync != None and self.sync_enabled == True:
			self.outgoing_sync.addChange( [ 'RenCat',old_folder,new_folder ] )

	def delete_folder(self,folder): # assumes empty and no subfolders - check first!
		if folder not in self.folder_name_to_number:
			return
		folder_number = self.folder_name_to_number[folder]
		del self.folder_name_to_number[folder]
		self.folder_number_to_name[folder_number] = None
		self.kvf.delete('A' + struct.pack('I',folder_number))
		if self.outgoing_sync != None and self.sync_enabled == True:
			self.outgoing_sync.addChange( [ 'DelCat',folder ] )

	def get_folder_list(self):
		listout = [ ]
		for folder in self.folder_number_to_name:
			if folder != None:
				listout.append(folder)
		return listout

	def get_high_index(self,fn):
		if fn in self.high_index:
			high_index = self.high_index[fn]
		else:
			found,high_index = self.kvf.unpickle('I' + struct.pack('I',fn))
			if found == False:
				high_index = 0
			self.high_index[fn] = high_index
		return high_index

	def set_high_index(self,fn,high_index):
		self.high_index[fn] = high_index
		self.kvf.pickle('I' + struct.pack('I',fn),high_index)

	def is_message_in_folder(self,folder,announcement_id):
		if folder not in self.folder_name_to_number:
			return False
		fn = self.folder_name_to_number[folder]
		keyH = 'H' + struct.pack('I',fn) + announcement_id
		found,index = self.kvf.get(keyH)
		return found

	def get_messages_in_folder(self,folder):
		#DBGOUT#print 'called for',folder
		if folder not in self.folder_name_to_number:
			self.check_add_folder(folder)
		fn = self.folder_name_to_number[folder]

		high_index = self.get_high_index(fn)	
		slack_entries = [ ]
		messages = [ ]
		for i in range(high_index):
			key = 'E' + struct.pack('I',fn)+struct.pack('I',i)
			found,message = self.kvf.get(key)
			#DBGOUT#if message == None:
				#DBGOUT#print "get msg",i,found,'none'
			#DBGOUT#else:
				#DBGOUT#print "get msg",i,found,type(message)
			if found:
				messages.append(message)
				#DBGOUT#print 'appended',i
			else:
				#DBGOUT#print 'not appended',i
				if len(slack_entries) < 1024:
					slack_entries.append(i)
		self.slack_entries[fn] = slack_entries
		#DBGOUT#print 'returning',messages
		#DBGOUT#print "slack entries",slack_entries
		return messages
			
	def put_message_in_folder(self,folder,announcement_id,skip_sync = False):
		self.logger.debug("Putting %s in %s",announcement_id.encode('hex'),folder)
		#DBGOUT#print "putting into",folder
		if folder not in self.folder_name_to_number:
			self.check_add_folder(folder)
		fn = self.folder_name_to_number[folder]

		fns_containing = self.get_fns_containing_message(announcement_id)
		if fn in fns_containing:
			return
		fns_containing.add(fn)
		self.kvf.pickle('F'+announcement_id,fns_containing)

		message_index = None
		if fn in self.slack_entries:
			slack_entries = self.slack_entries[fn]
			#DBGOUT#print "got slack entries",slack_entries
			if len(slack_entries) > 0:
				message_index = slack_entries.pop(0)
				#DBGOUT#print "using slack_entry",message_index
		if message_index == None:
			high_index = self.get_high_index(fn)
			message_index = high_index
			#DBGOUT#print "using high index",message_index
			high_index += 1
			self.set_high_index(fn,high_index)
		index = struct.pack('I',message_index)
		keyE = 'E' + struct.pack('I',fn) + index
		keyH = 'H' + struct.pack('I',fn) + announcement_id
		self.kvf.set(keyE,announcement_id)
		self.kvf.set(keyH,index)
		if self.outgoing_sync != None and self.sync_enabled == True and skip_sync == False:
			self.outgoing_sync.addChange( [ 'AddMsg',folder,announcement_id ] )
	
	def get_fns_containing_message(self,announcement_id):
		found,fns_containing = self.kvf.unpickle('F'+announcement_id)
		if found == False:
			return set()
		else:
			return fns_containing

	def get_folders_containing_message(self,announcement_id):
		found,fns_containing = self.kvf.unpickle('F'+announcement_id)
		folders_containing = [ ]
		if found == True:
			for fn in fns_containing:
				folders_containing.append(self.folder_number_to_name[fn])
		return folders_containing
		
#	def delete_message_from_all_folders(self,announcement_id):
#		self.logger.debug("Deleting %s from all",announcement_id.encode('hex'))
#		fns_containing = self.get_fns_containing_message(announcement_id)
#		for fn in fns_containing:
#			keyH = 'H' + struct.pack('I',fn) + announcement_id
#			found,index = self.kvf.get(keyH)
#			if found == False:
#				self.logger.error("Message index entry not found for %s in %s",announcement_id.encode('hex'),self.folder_number_to_name[fn])
#			else:
#				keyE = 'E' + struct.pack('I',fn) + index
#				message_index, = struct.unpack('I',index)
#				self.kvf.delete(keyH)
#				self.kvf.delete(keyE)
#				if fn in self.slack_entries:
#					self.slack_entries[fn].append(message_index)
#		self.kvf.delete('F'+announcement_id)
#		self.kvf.delete('M'+announcement_id)

	# Returns True if last copy of message deleted
	def delete_message_from_folder(self,folder,announcement_id,skip_sync = False):
		if folder not in self.folder_name_to_number:
			return
		fn = self.folder_name_to_number[folder]

		all_deleted = False
		self.logger.debug("Deleting %s from %s",announcement_id.encode('hex'),folder)
		fns = self.get_fns_containing_message(announcement_id)
		if fn not in fns:
			return False
		fns.remove(fn)
		if len(fns) == 0:
			self.kvf.delete('F'+announcement_id)
			self.kvf.delete('M'+announcement_id)
			all_deleted = True
		else:
			self.kvf.pickle('F'+announcement_id,fns)
		keyH = 'H' + struct.pack('I',fn) + announcement_id
		found,index = self.kvf.get(keyH)
		if found == False:
			self.logger.error("Message index entry not found for %s in %s",announcement_id.encode('hex'),folder)
		else:
			keyE = 'E' + struct.pack('I',fn) + index
			message_index, = struct.unpack('I',index)
			self.kvf.delete(keyH)
			self.kvf.delete(keyE)
			if fn in self.slack_entries:
				self.slack_entries[fn].append(message_index)
		if self.outgoing_sync != None and self.sync_enabled == True and \
				skip_sync == False and folder != id_deleted:
			self.outgoing_sync.addChange( [ 'DelMsg',folder,announcement_id ] )
		return all_deleted

	def set_global(self,name,value):
		self.kvf.set('g' + name,value)

	def get_global(self,name): # found,value
		return self.kvf.get('g' + name)

	def del_global(self,name):
		self.kvf.delete('g' + name)

# EOF
		
