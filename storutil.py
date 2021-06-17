import sys
import os
import os.path
import re
import datetime
import stat
import time
import global_config
import filestore
import filelock

re_datetime = re.compile("^DATE: (\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ)$",re.IGNORECASE)
re_type = re.compile("^TYPE: (.+)$",re.IGNORECASE)
re_recipient = re.compile("^RECIPIENT: ([0123456789abcdef]{40})$",re.IGNORECASE)
re_datablock = re.compile("^DATABLOCK: ([0123456789abcdef]{40})$",re.IGNORECASE)
re_userid = re.compile("^USERID: (.+)$",re.IGNORECASE)
re_keyid = re.compile("^KEYID: ([0123456789abcdef]{40})$",re.IGNORECASE)
re_message_hash = re.compile("^MESSAGEHASH: ([0123456789abcdef]{40})$",re.IGNORECASE)

html_escape_table = { "&": "&amp;", '"': "&quot;", "'": "&apos;", ">": "&gt;", "<": "&lt;", }

def html_escape(text):
	"""Produce entities within text."""
	return "".join(html_escape_table.get(c,c) for c in text)

def nowtime():
	return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

class storutil:

	def __init__(self,homedir,report_mode,prune_localstore,prune_entangled,prune_simulate,report_html,report_csv,report_tab,per_file_delay,disk_block_size,sort_cmd,no_total,keep_temp):
		self.homedir = homedir
		self.report_mode = report_mode
		self.prune_localstore = prune_localstore
		self.prune_entangled = prune_entangled
		self.prune_simulate = prune_simulate
		self.report_html = report_html
		self.report_csv = report_csv
		self.report_tab = report_tab
		self.per_file_delay = float(per_file_delay) / 1000.0
		self.alt_localstore = None
		self.storutil_temp = self.homedir + os.sep + 'storutil'
		self.storutil_lockfile = self.storutil_temp + os.sep + 'LOCKFILE'
		self.runtime = datetime.datetime.utcnow()
		self.max_age_key_entangled = global_config.max_age_key 
		self.max_age_data_entangled = global_config.max_age_data 
		self.max_age_message_entangled = global_config.max_age_message 
		self.max_age_ack_entangled = global_config.max_age_ack 
		self.max_age_claim_entangled = global_config.max_age_claim 
		self.max_age_key_server = global_config.max_age_key 
		self.max_age_data_server = global_config.max_age_data 
		self.max_age_message_server = global_config.max_age_message 
		self.max_age_ack_server = global_config.max_age_ack 
		self.max_age_claim_server = global_config.max_age_claim 
		self.report1_fn = self.storutil_temp + os.sep + 'report1.txt'
		self.report2_fn = self.storutil_temp + os.sep + 'report2.txt'
		self.report3_fn = self.storutil_temp + os.sep + 'report3.txt'
		self.report4_fn = self.storutil_temp + os.sep + 'report4.txt'
		self.last_lockfile = None
		self.last_lockobj = None
		self.last_progress = 0
		self.disk_block_size = disk_block_size
		self.sort_cmd = sort_cmd
		self.no_total = no_total
		self.keep_temp = keep_temp
		self.total_bytes_reclaimed = 0

	def parse_server_config_file(self):
		config_file = self.homedir + os.sep + "config.txt"
		filehandle = open(config_file,'r')	
		config_parse = re.compile(":[\t ]*")
		for line in filehandle:
			line = line.rstrip('\r\n')
			if line == '' or line[0] == '#' or line[0] == ';':
				continue
			param,pval = config_parse.split(line,1)
			if param == 'alt_localstore':
				self.alt_localstore = pval
			elif param == 'max_age_key':
				self.max_age_key_server = int(pval)
			elif param == 'max_age_data':
				self.max_age_data_server = int(pval)
			elif param == 'max_age_message':
				self.max_age_message_server = int(pval)
			elif param == 'max_age_ack':
				self.max_age_ack_server = int(pval)
			elif param == 'max_age_claim':
				self.max_age_claim_server = int(pval)
		filehandle.close()
	
	def round_up_to_blocksize(self,rawsize):
		return (((rawsize + self.disk_block_size - 1) // self.disk_block_size) * self.disk_block_size)

	def run_main_pass(self):
		self.file_count = 0
		if self.generate_report == True:
			self.report_fh = open(self.report1_fn,'w') #  first pass of report
		self.traverse_path(self.root_path,self.process_file_locking)
		if self.generate_report == True:
			self.report_fh.close()
	
	def clear_prune_counts(self):
		self.num_del_key = 0
		self.num_del_data = 0
		self.num_del_message = 0
		self.num_del_ack = 0
		self.num_del_claim = 0
		self.num_tot_key = 0
		self.num_tot_data = 0
		self.num_tot_message = 0
		self.num_tot_ack = 0
		self.num_tot_claim = 0
		self.num_trim_message = 0
		self.num_tot_message_parts = 0
		self.num_del_message_parts = 0
		self.num_trim_claim = 0
		self.num_tot_claim_parts = 0
		self.num_del_claim_parts = 0
		self.num_bytes_deleted = 0

	def print_prune_counts(self):
		print "key-announce blocks count =",self.num_tot_key
		print "key-announce blocks deleted =",self.num_del_key
		print "data blocks count =",self.num_tot_data
		print "data blocks deleted =",self.num_del_data
		print "message-announce blocks count =",self.num_tot_message
		print "message-announce blocks deleted =",self.num_del_message
		print "message-announce blocks trimmed =",self.num_trim_message
		print "message-announcements count =",self.num_tot_message_parts
		print "message-announcements trimmed =",self.num_del_message_parts
		print "acknowledgments count =",self.num_tot_ack
		print "acknowledgments deleted =",self.num_del_ack
		print "address-claim blocks count =",self.num_tot_claim
		print "address-claim blocks deleted =",self.num_del_claim
		print "address-claim blocks trimmed =",self.num_trim_claim
		print "address-claims count =",self.num_tot_claim_parts
		print "address-claims trimmed =",self.num_del_claim_parts
		print "bytes in deleted files =",self.num_bytes_deleted

	def check_get_storutil_lock(self):
		if os.path.exists(self.storutil_temp) == False:
			print nowtime(),"Creating temporary directory",self.storutil_temp
			os.mkdir(self.storutil_temp)
		print nowtime(),"Acquire storutil lock"
		self.storutil_lock = filelock.filelock(self.storutil_lockfile)
		got_lock = self.storutil_lock.lock_nowait()
		if got_lock == False:
			print nowtime(),"Another storutil is running, exiting"
		return got_lock

	def release_storutil_lock(self):
		print nowtime(),"Release storutil lock"
		self.storutil_lock.unlock_close()

	def run_process(self):	
		print nowtime(),"Process start"
		self.parse_server_config_file()
		if self.report_mode == True:
			self.generate_report = True
		else:
			self.generate_report = False

		if self.prune_localstore == True or self.report_mode == True:
			self.max_age_key = self.max_age_key_server
			self.max_age_data = self.max_age_data_server
			self.max_age_message = self.max_age_message_server
			self.max_age_ack = self.max_age_ack_server
			self.max_age_claim = self.max_age_claim_server
			self.clear_prune_counts()
			
			if self.alt_localstore == None:
				self.root_path = self.homedir + os.sep + 'localstore'
			else:
				self.root_path = self.alt_localstore
			if self.prune_localstore == True and self.report_mode == True:
				print nowtime(),"Starting prune and report on localstore"
			elif self.prune_localstore == True:
				print nowtime(),"Starting prune on localstore"
			elif self.report_mode == True:
				print nowtime(),"Starting report on localstore"
			self.local_store = filestore.filestore(self.root_path)
			self.prune_mode = self.prune_localstore
			self.run_main_pass()
			if self.prune_localstore == True:
				print nowtime(),"Localstore prune counts:"
				self.print_prune_counts()
				self.total_bytes_reclaimed += self.num_bytes_deleted
			print nowtime(),"Main pass on localstore complete"

		if self.report_mode == True:
			print nowtime(),"Sorting first report intermediate file"	
			self.sort_file(self.report1_fn,self.report2_fn) 
			print nowtime(),"Running report pass 2"
			self.report_pass2()
			print nowtime(),"Sorting second report intermediate file"
			self.sort_file(self.report3_fn,self.report4_fn) 
			print nowtime(),"Generating report"
			self.report_pass3()
			print nowtime(),"Report generation complete"

		if self.prune_entangled == True:
			self.max_age_key = self.max_age_key_entangled
			self.max_age_data = self.max_age_data_entangled
			self.max_age_message = self.max_age_message_entangled
			self.max_age_ack = self.max_age_ack_entangled
			self.max_age_claim = self.max_age_claim_entangled
			self.clear_prune_counts()
			print nowtime(),"Starting prune on entangled"
			self.prune_mode = True
			self.generate_report = False
			self.root_path = self.homedir + os.sep + 'entangled'
			self.local_store = filestore.filestore(self.root_path)
			self.run_main_pass()
			print nowtime(),"Entangled prune counts:"
			self.print_prune_counts()
			self.total_bytes_reclaimed += self.num_bytes_deleted
			print nowtime(),"Prune on entangled complete"

		if self.prune_localstore == True or self.prune_entangled == True:
			print nowtime(),"Approx total bytes reclaimed =",self.total_bytes_reclaimed
		print nowtime(),"Process end"

	# Iterate through the path and call the callback for each file
	def traverse_path(self,iter_path,callback):
		count = 0
		for l1 in os.listdir(iter_path):
			l1path = iter_path + os.sep + l1
			if os.path.isdir(l1path):
				for l2 in os.listdir(l1path):
					l2path = l1path + os.sep + l2
					for l3 in os.listdir(l2path):
						if l3 == 'LOCKFILE':
							continue
						l3path = l2path + os.sep + l3
						if os.path.isfile(l3path):
							count += 1
							if count % 10 == 0:
								nowtimecheck = time.time()
								if nowtimecheck - self.last_progress > 10.0:
									self.last_progress = nowtimecheck
									print nowtime(),"Processing file #" + str(self.file_count),l3path
							self.file_count += 1
							callback(l3path,l3)

	def sort_file(self,infile,outfile):
		if os.path.exists(outfile):
			os.unlink(outfile)
		os.environ['LC_ALL'] = 'C' # gsort collation sequence
		os.environ['TMPDIR'] = self.storutil_temp # sort temp directory
		if self.sort_cmd != None:
			res = os.system(self.sort_cmd + ' < "' + infile + '" > "' + outfile + '"')
			infilesize = 0
			outfilesize = 0
			try:
				filestat = os.stat(outfile)
				outfilesize = filestat.st_size
			except Exception:
				pass
			try:
				filestat = os.stat(infile)
				infilesize = filestat.st_size
			except Exception:
				pass
			if infilesize > 0 and outfilesize == 0:
				print nowtime(),"ERROR Sort command produced zero-length output, check -sort option"
		else: # guess
			res = os.system('gsort < "' + infile + '" > "' + outfile + '"')
			infilesize = 0
			outfilesize = 0
			try:
				filestat = os.stat(outfile)
				outfilesize = filestat.st_size
			except Exception:
				pass
			try:
				filestat = os.stat(infile)
				infilesize = filestat.st_size
			except Exception:
				pass
			if infilesize > 0 and outfilesize == 0:
				if sys.platform == 'win32':
					print nowtime(),"Using system sort on win32, GNU sort not found"
				else:
					print nowtime(),"gsort not found, using sort"
				res = os.system('sort < "' + infile + '" > "' + outfile + '"')
				outfilesize = 0
				try:
					filestat = os.stat(outfile)
					outfilesize = filestat.st_size
				except Exception:
					pass
				if outfilesize == 0:
					print nowtime(),"ERROR Sort command produced zero-length output, please specify -sort option"

	def process_message_announcement(self,filepath,filename,filesize,lines):
		an_keep = [ ]
		an_this = [ ]
		keep_all = True
		del_all = True
		blockdate = None
		for line in lines:
			lineL = line.lower()
			match = re_datetime.match(line)
			if match:
				blockdate = match.group(1)
			if lineL == 'nextmessage' or lineL == 'endblock':
				self.num_tot_message_parts += 1
				ageS = None
				if blockdate != None:
					blockdate_obj = datetime.datetime.strptime(blockdate,"%Y-%m-%dT%H:%M:%SZ")
					ageS = (self.runtime - blockdate_obj).total_seconds()
				if (ageS != None) and (ageS <= self.max_age_message):
					if len(an_keep) != 0:
						an_keep.append('NextMessage')
					an_keep.extend(an_this)
					an_this = [ ]
					del_all = False
				else:
					self.num_del_message_parts += 1
					an_this = [ ]
					keep_all = False
			else:
				an_this.append(line)
		if del_all == True:
			self.num_del_message += 1
			self.num_bytes_deleted += self.round_up_to_blocksize(filesize)
			if self.prune_simulate == False:
				os.unlink(filepath)
			return False
		elif keep_all == True:
			return True
		else:
			self.num_trim_message += 1
			if self.prune_simulate == False:
				self.local_store.storeList(filename,an_keep)
			return True
				
	def process_address_claim(self,filepath,filename,filesize,lines):
		an_keep = [ ]
		an_this = [ ]
		keep_all = True
		del_all = True
		blockdate = None
		for line in lines:
			lineL = line.lower()
			match = re_datetime.match(line)
			if match:
				blockdate = match.group(1)
			if lineL == 'nextclaim' or lineL == 'endblock':
				self.num_tot_claim_parts += 1
				ageS = None
				if blockdate != None:
					blockdate_obj = datetime.datetime.strptime(blockdate,"%Y-%m-%dT%H:%M:%SZ")
					ageS = (self.runtime - blockdate_obj).total_seconds()
				if (ageS != None) and (ageS <= self.max_age_claim):
					if len(an_keep) != 0:
						an_keep.append('NextClaim')
					an_keep.extend(an_this)
					an_this = [ ]
					del_all = False
				else:
					self.num_del_claim_parts += 1
					an_this = [ ]
					keep_all = False
			else:
				an_this.append(line)
		if del_all == True:
			self.num_del_claim += 1
			self.num_bytes_deleted += self.round_up_to_blocksize(filesize)
			if self.prune_simulate == False:
				os.unlink(filepath)
			return False
		elif keep_all == True:
			return True
		else:
			self.num_trim_claim = 0
			if self.prune_simulate == False:
				self.local_store.storeList(filename,an_keep)
			return True

	def process_file_locking(self,filepath,filename):
		if self.per_file_delay > 0.0:
			time.sleep(self.per_file_delay)
		lockfile = self.local_store.getLockfile(filename)
		if lockfile != self.last_lockfile:
			if self.last_lockobj != None:
				self.last_lockobj.unlock_close()
			self.last_lockfile = lockfile
			self.last_lockobj = filelock.filelock(lockfile)
		self.last_lockobj.lock_wait()
		self.process_file(filepath,filename)	
		self.last_lockobj.unlock()

	def process_file(self,filepath,filename):
		found,lines = self.local_store.retrieveHeadersEntangled(filename)
		if found == False:
			#DBGOUT#print "block not found - error"
			return
		#DBGOUT#print filepath,filesize
		filestat = os.stat(filepath)
		filesize = filestat.st_size
		blockdate = None
		blocktype = None
		recipient = None
		userid = None
		keyid = None
		
		for line in lines:
			lineL = line.lower()
			match = re_datetime.match(line)
			if match:
				blockdate = match.group(1)
				continue
			match = re_type.match(line)
			if match:
				blocktype = match.group(1)
				blocktypeL = blocktype.lower()
				continue
			match = re_recipient.match(line)
			if match:
				recipient = match.group(1)
				continue
			match = re_userid.match(line)
			if match:
				userid = match.group(1)
				continue
			match = re_keyid.match(line)
			if match:
				keyid = match.group(1)
				continue

		if blocktype == None:
			return

		if blocktypeL != 'data' and blocktypeL != 'message-announcement' and blocktypeL != 'key-announcement' and blocktypeL != 'address-claim' and blocktypeL != 'acknowledgment' and blocktypeL != 'acknowledgement':
			return
			
		if blocktypeL == 'message-announcement' or blocktypeL == 'address-claim':
			lines.append('EndBlock') # end marker makes it easier to process the component messages

		if self.prune_mode == True:
			if blocktypeL == 'message-announcement':
				self.num_tot_message += 1
				keep_file = self.process_message_announcement(filepath,filename,filesize,lines)
			elif blocktypeL == 'address-claim':
				self.num_tot_claim += 1
				keep_file = self.process_address_claim(filepath,filename,filesize,lines)
			else:
				max_age = 0
				if blocktypeL == 'data':
					self.num_tot_data += 1
					max_age = self.max_age_data
				elif blocktypeL == 'key-announcement':
					self.num_tot_key += 1
					max_age = self.max_age_key
				elif blocktypeL == 'acknowledgment' or blocktypeL == 'acknowledgement':
					self.num_tot_ack += 1
					max_age = self.max_age_ack
				ageS = None
				if blockdate != None:
					blockdate_obj = datetime.datetime.strptime(blockdate,"%Y-%m-%dT%H:%M:%SZ")
					ageS = (self.runtime - blockdate_obj).total_seconds()
				if (ageS != None) and (ageS <= max_age):
					keep_file = True
				else:
					if blocktypeL == 'data':
						self.num_del_data += 1
					elif blocktypeL == 'key-announcement':
						self.num_del_key += 1
					elif blocktypeL == 'acknowledgment' or blocktypeL == 'acknowledgement':
						self.num_del_ack += 1
					self.num_bytes_deleted += self.round_up_to_blocksize(filesize)
					if self.prune_simulate == False:
						os.unlink(filepath)
					keep_file = False
		else:
			keep_file = True

		if self.generate_report == True and keep_file == True:
			if self.prune_mode == True and (blocktypeL == 'message-announcement' or blocktypeL == 'address-claim'):
				found,lines = self.local_store.retrieveHeadersEntangled(filename) # file could have changed
				lines.append('EndBlock') # end marker makes it easier to process the component messages
				filestat = os.stat(filepath)
				filesize = filestat.st_size
				
			if blocktypeL == 'message-announcement':
				self.report_message_announcement(filename,filesize,lines)
			elif blocktypeL == 'address-claim':
				self.report_fh.write(keyid.upper() + '\tL\t' + str(filesize) + '\n')
			elif blocktypeL == 'data':
				self.report_fh.write(filename.upper() + '\tD\t' + str(filesize) + '\n')
			elif blocktypeL == 'key-announcement':
				self.report_fh.write(filename.upper() + '\tA\t' + str(filesize) + '\t' + userid + '\n')
			elif blocktypeL == 'acknowledgment' or blocktypeL == 'acknowledgement':
				self.report_fh.write(filename.upper() + '\tC\t' + str(filesize) + '\n')

	def report_message_announcement(self,filename,filesize,lines):
		thismsg = [ ]
		for line in lines:
			lineL = line.lower()
			if lineL == 'endblock' or lineL == 'nextmessage':
				self.report_message_announcement_one(filename,filesize,thismsg)
				thismsg = [ ]
			else:
				thismsg.append(line)

	def report_message_announcement_one(self,filename,filesize,lines):
		#print ""
		#print "--new message announcement--",filename
		datablocks = [ ]
		message_hash = None
		recipient = None
		for line in lines:
			match = re_datablock.match(line)
			if match:
				datablocks.append(match.group(1))
				continue
			match = re_message_hash.match(line)
			if match:
				message_hash = match.group(1)
				continue
			match = re_recipient.match(line)
			if match:
				recipient = match.group(1)
				continue
		if len(datablocks) == 0 or message_hash == None or recipient == None:
			return
		for datablock in datablocks:
			self.report_fh.write(datablock.upper() + '\tM\t' + filename.upper() + '\t' + recipient.upper() + '\t' + message_hash.upper() + '\t' + str(filesize) + '\n')

	def report_pass2(self): # associate data blocks with their message blocks
		report2_fh = open(self.report2_fn,'r')
		report3_fh = open(self.report3_fn,'w')
		db_hash = None
		db_len = None
		line = None
		
		f_hash = 0 # all types
		f_type = 1 # all types
		f_size = 2 # all types except m
		m_filename = 2 # message 
		m_recipient = 3 # message
		m_hash = 4 # message
		m_size = 5 # message
		last_hash = None
		datablock = None
		messages = [ ]
		while True:
			if line == None:
				line = report2_fh.readline()
				if line == '':
					line = 'EOF\tEOF\tEOF'	
				line = line.rstrip('\r\n')
			fields = line.split('\t')

			type = fields[f_type]
			hash = fields[f_hash]
			if last_hash != hash:
				if len(messages) != 0:
					if datablock != None:
						for msg in messages:
							report3_fh.write(msg[m_recipient] + '\tD\t' + datablock[f_size] + '\t' + str(len(messages)) + '\n')
				elif datablock != None: # unmatched data block
					report3_fh.write('UNMATCHED\tD\t' + datablock[f_size] + '\t1\n')
				if hash == 'EOF':
					break
				datablock = None
				messages = [ ]
				last_hash = hash
			if type == 'D':
				datablock = fields
				line = None
			elif type == 'M':
				messages.append(fields)
				report3_fh.write(fields[m_recipient] + '\tM\t' + fields[m_filename] + '\t' + fields[m_hash] + '\t' + fields[m_size] + '\n')
				line = None
			else:
				report3_fh.write(line + '\n')
				line = None
		report2_fh.close()
		report3_fh.close()

	def output_row(self,out_line):
		if self.report_html != None:
			self.html_fh.write('<tr>')

		count = 0
		for field in out_line:
			if self.report_html != None:
				if count > 1:
					self.html_fh.write('<td align="right">' + field + '</td>')
				else:
					self.html_fh.write('<td>' + html_escape(field) + '</td>')
			if self.report_csv != None:
				if count == 0:
					self.csv_fh.write('"' + field.replace('"','""') + '"')
				else:
					self.csv_fh.write(',' + field)
			if self.report_tab != None:
				if count == 0:
					self.tab_fh.write(field.replace('\t',' '))
				else:
					self.tab_fh.write('\t' + field.replace('\t',' '))
			count += 1

		if self.report_html != None:
			self.html_fh.write('</tr>\n')
	
		if self.report_tab != None:
			self.tab_fh.write('\n')
	
		if self.report_csv != None:
			self.csv_fh.write('\n')

	def report_pass3(self):
		out_fields = [ 'Email address','Key ID','Num Data Blocks','Data Total Bytes',
					   "Data App'd Bytes",'Num Msg Anncs','Msg Annc Bytes','Num Msgs',
					   'Key Annc Bytes','Address Claim Bytes','Total Num Blocks',
					   'Total Raw Bytes',"Total App'd Bytes" ]
		report4_fh = open(self.report4_fn,'r')
		if self.report_html != None:
			self.html_fh = open(self.report_html,'w')
		if self.report_csv != None:
			self.csv_fh = open(self.report_csv,'w')
		if self.report_tab != None:
			self.tab_fh = open(self.report_tab,'w')

		if self.report_html != None:
			self.html_fh.write('<table border="1" cellspacing="0" cellpadding="3">\n<tr>')
			for field in out_fields:
				self.html_fh.write('<th>' + field + '</th>')
			self.html_fh.write('</tr>\n')
		
		if self.report_tab != None:
			first = True
			for field in out_fields:
				if first == True:
					first = False
					self.tab_fh.write(field)
				else:
					self.tab_fh.write('\t' + field)
			self.tab_fh.write('\n')
		
		if self.report_csv != None:
			first = True
			for field in out_fields:
				if first == True:
					first = False
					self.csv_fh.write(field)
				else:
					self.csv_fh.write(',' + field)
			self.csv_fh.write('\n')
		
		total_num_key_announce = 0
		total_size_key_announce = 0
		total_num_messages = 0
		total_num_message_announce = 0
		total_size_message_announce = 0
		total_num_address_claim = 0
		total_size_address_claim = 0
		total_num_data = 0
		total_raw_size_data = 0
		total_app_size_data = 0
		total_num_ack = 0
		total_size_ack = 0
		total_num_blocks = 0
		total_size = 0
		key_name = None
		key_size_key_announce = 0
		key_size_address_claim = 0
		key_num_messages = 0
		key_num_message_announce = 0
		key_size_message_announce = 0
		key_num_data = 0
		key_raw_size_data = 0
		key_app_size_data = 0

		line = None
		last_hash = None
		last_message_announce = None
		last_message_hash = None
		while True:
			line = report4_fh.readline()
			if line == '':
				line = 'EOF\tEOF\tEOF'	
			line = line.rstrip('\r\n')
			fields = line.split('\t')
			hash = fields[0]
			type = fields[1]

			if last_hash != hash and last_hash != None:
				key_total_raw_bytes = key_size_key_announce + key_size_address_claim + key_size_message_announce + key_raw_size_data
			if last_hash != hash and last_hash != None and key_total_raw_bytes != 0:
				key_total_blocks = key_num_message_announce + key_num_data
				if key_size_key_announce != 0:
					key_total_blocks += 1
				if key_size_address_claim != 0:
					key_total_blocks += 1
				key_total_raw_bytes = key_size_key_announce + key_size_address_claim + key_size_message_announce + key_raw_size_data
				key_total_app_bytes = key_size_key_announce + key_size_address_claim + key_size_message_announce + key_app_size_data
				out_line = [ ]
				if key_name == None:
					out_line.append('Unknown')
				else:
					out_line.append(key_name)
				out_line.append(last_hash)
				out_line.append(str(key_num_data))
				out_line.append(str(key_raw_size_data))
				out_line.append(str(int(key_app_size_data)))
				out_line.append(str(key_num_message_announce))
				out_line.append(str(key_size_message_announce))
				out_line.append(str(key_num_messages))
				out_line.append(str(key_size_key_announce))
				out_line.append(str(key_size_address_claim))
				out_line.append(str(key_total_blocks))
				out_line.append(str(key_total_raw_bytes))
				out_line.append(str(int(key_total_app_bytes)))
				self.output_row(out_line)

			if last_hash != hash:
				key_name = None
				key_size_key_announce = 0
				key_size_address_claim = 0
				key_num_message_announce = 0
				key_size_message_announce = 0
				key_num_messages = 0
				key_num_data = 0
				key_raw_size_data = 0
				key_app_size_data = 0
				if hash == 'EOF':
					break
				last_hash = hash
	
				#report3_fh.write(fields[m_recipient] + '\tM\t' + fields[m_filename] + '\t' + fields[m_hash] + '\t' + fields[m_size] + '\n')
			if type == 'M': # message announcement
				if fields[3] != last_message_hash:
					key_num_messages += 1
					total_num_messages += 1
					last_message_hash = fields[3]
				if fields[2] != last_message_announce:
					last_message_announce = fields[2]
					size = self.round_up_to_blocksize(int(fields[4]))
					total_num_message_announce += 1
					total_size_message_announce += size
					key_num_message_announce += 1
					key_size_message_announce += size
			elif type == 'D': # data
				size = self.round_up_to_blocksize(int(fields[2]))
				recips = int(fields[3])
				app_size = size / recips
				total_num_data += 1
				total_raw_size_data += size
				total_app_size_data += app_size
				key_num_data += 1
				key_raw_size_data += size
				key_app_size_data += app_size
			elif type == 'A': # key announcement
				size = self.round_up_to_blocksize(int(fields[2]))
				key_size_key_announce = size
				key_name = fields[3]
				total_num_key_announce += 1
				total_size_key_announce += size
			elif type == 'C': # acknowledgment
				size = self.round_up_to_blocksize(int(fields[2]))
				total_num_ack += 1
				total_size_ack += size
			elif type == 'L': # address claim
				size = self.round_up_to_blocksize(int(fields[2]))
				key_size_address_claim = size
				total_num_address_claim += 1
				total_size_address_claim += size

		total_num_blocks = total_num_key_announce + total_num_message_announce + total_num_address_claim + total_num_data + total_num_ack
		total_size = total_size_key_announce + total_size_message_announce + total_size_address_claim + total_app_size_data + total_size_ack

		if self.no_total == False:
			out_line = [ ]
			out_line.append('Total')
			out_line.append('Total')
			out_line.append(str(total_num_data))
			out_line.append('-')
			out_line.append(str(int(total_app_size_data)))
			out_line.append(str(total_num_message_announce))
			out_line.append(str(total_size_message_announce))
			out_line.append(str(total_num_messages))
			out_line.append(str(total_size_key_announce))
			out_line.append(str(total_size_address_claim))
			out_line.append(str(total_num_blocks))
			out_line.append('-')
			out_line.append(str(total_size))
			self.output_row(out_line)

		report4_fh.close()
		if self.report_html != None:
			self.html_fh.write('</table>\n')
			self.html_fh.close()
		if self.report_csv != None:
			self.csv_fh.close()
		if self.report_tab != None:
			self.tab_fh.close()

		if self.keep_temp == False:
			os.unlink(self.report1_fn)
			os.unlink(self.report2_fn)
			os.unlink(self.report3_fn)
			os.unlink(self.report4_fn)

		print nowtime(),"Localstore report summary counts:"
		print "Total number of key announcements =",total_num_key_announce
		print "Total bytes in key announcements  =",total_size_key_announce
		print "Total number of message announcements =",total_num_message_announce
		print "Total bytes in message announcements =",total_size_message_announce
		print "Total number of messages =",total_num_messages
		print "Total number of address claims =",total_num_address_claim
		print "Total bytes in address claims =",total_size_address_claim
		print "Total number of data blocks =",total_num_data
		print "Total bytes in data blocks =",total_app_size_data
		print "Total number of acknowledgments =",total_num_ack
		print "Total bytes in acknowledgments =",total_size_ack
		print "Total number of blocks =",total_num_blocks
		print "Total bytes in all blocks =",total_size
		print "Calculated using filesystem block size =",self.disk_block_size
		
def usage():
	print "Usage: python storutil.py -homedir SERVER-PATH OPTIONS"
	print "Options are:"
	print "  -report-html REPORT-PATH"
	print "    generates the report as HTML"
	print "  -report-csv REPORT-PATH"
	print "    generates the report as CSV"
	print "  -report-tab REPORT-PATH"
	print "    generates the report as TAB delimited"
	print "  -prune-entangled"
	print "    removes expired messages from entangled"
	print "  -prune-localstore"
	print "    removes expired messages from the server local store"
	print "  -prune-simulate"
	print "    report prune counts without actually deleting anything"
	print "  -delay MILLISECONDS"
	print "    delay between files to reduce server load"
	print "  -blocksize N"
	print "    set storage block size (default 512 bytes)"
	print "  -sort SORTCMD"
	print "    specify file sorting program (used for reporting)"
	print "  -nototal"
	print "    do not include total line in report"
	print "  -keeptemp"
	print "    do not delete report temporary files (for debugging)"
	print "Report and prune can be done simultaneously, in which case the report"
	print "will contain post-prune numbers."

def storutil_main(cmdline):
	homedir = None
	report_html = None
	report_csv = None
	report_tab = None
	prune_localstore = False
	prune_entangled = False
	prune_simulate = False
	report_mode = False
	per_file_delay = 0
	disk_block_size = 512
	sort_cmd = None
	no_total = False
	keep_temp = False
	
	n = 0
	while n < len(cmdline):
		cmd = cmdline[n]
		#print n,cmd
	
		if cmd == '-homedir':
			n += 1
			homedir = cmdline[n]
			n += 1
		elif cmd == '-report-html':
			n += 1
			report_html = cmdline[n]
			report_mode = True
			n += 1
		elif cmd == '-report-csv':
			n += 1
			report_csv = cmdline[n]
			report_mode = True
			n += 1
		elif cmd == '-report-tab':
			n += 1
			report_tab = cmdline[n]
			report_mode = True
			n += 1
		elif cmd == '-prune-entangled':
			n += 1
			prune_entangled = True
		elif cmd == '-prune-localstore':
			n += 1
			prune_localstore = True
		elif cmd == '-prune-simulate':
			n += 1
			prune_simulate = True
		elif cmd == '-delay':
			n += 1
			per_file_delay = int(cmdline[n])
			n += 1
		elif cmd == '-blocksize':
			n += 1
			disk_block_size = int(cmdline[n])
			n += 1
		elif cmd == '-sort':
			n += 1
			sort_cmd = cmdline[n]
			n += 1
		elif cmd == '-nototal':
			n += 1
			no_total = True
		elif cmd == '-keeptemp':
			n += 1
			keep_temp = True
		else:
			print "Unrecognized (cmdline): "+cmd
			n += 1
	
	if len(cmdline) == 0:
		usage()
		sys.exit(1)
	
	if homedir == None:
		print "ERROR: homedir not specified"
		usage()
		sys.exit(1)
	
	if report_mode == False and prune_entangled == False and prune_localstore == False:
		print "ERROR: no task specified"
		usage()
		sys.exit(1)
	
	su = storutil(homedir,report_mode,prune_localstore,prune_entangled,prune_simulate,report_html,report_csv,report_tab,per_file_delay,disk_block_size,sort_cmd,no_total,keep_temp)
	got_lock = su.check_get_storutil_lock()
	if got_lock == False:
		sys.exit(1)
	else:
		su.run_process()
		su.release_storutil_lock()
		sys.exit(0)

if __name__ == "__main__":
	storutil_main(sys.argv[1:])

# EOF
