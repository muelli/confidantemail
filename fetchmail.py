import os
import os.path
import logging
import zipfile
import re
import random
import datetime
import global_config
import twisted.protocols.basic
import twisted.internet.protocol
import twisted.internet.reactor
import twisted.internet.endpoints
import gnupg
import proofofwork
import bypass_token
import hashlib
import client

re_data = re.compile("^DATA: ([1-9][0-9]*)$",re.IGNORECASE)
re_db = re.compile("^DATABLOCK: ([0123456789abcdef]{40})$",re.IGNORECASE)
re_mh = re.compile("^MESSAGEHASH: ([0123456789abcdef]{40})$",re.IGNORECASE)
re_ah = re.compile("^HASH: ([0123456789abcdef]{40})$",re.IGNORECASE)
re_rec = re.compile("^RECIPIENT: ([0123456789abcdef]{40})$",re.IGNORECASE)
re_datetime = re.compile("^DATE: (\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ)$",re.IGNORECASE)

re_server_is_tor = re.compile('.*\.onion:\d+$',re.IGNORECASE)
re_server_is_i2p = re.compile('.*\.i2p:\d+$',re.IGNORECASE)

def re_order_servers(server_list,anon_first,server_connection):
	s_in = [ ]
	s_tor = [ ]
	s_i2p = [ ]
	s_dir = [ ]	
	s_out = [ ]
	s_in.extend(server_list)
	random.shuffle(s_in)
	for server in s_in:
		if re_server_is_tor.match(server):
			s_tor.append(server)
		elif re_server_is_i2p.match(server):
			s_i2p.append(server)
		else:
			s_dir.append(server)
	if server_connection == 'I2P':
		s_out.extend(s_i2p)	
		s_out.extend(s_tor)	
		s_out.extend(s_dir)	
	elif anon_first == True or server_connection == 'TOR':
		s_out.extend(s_tor)	
		s_out.extend(s_dir)	
		s_out.extend(s_i2p)	
	else:
		s_out.extend(s_dir)	
		s_out.extend(s_tor)	
		s_out.extend(s_i2p)	
	return s_out

class fetchmail:

	def __init__(self,gnupg,block_store,complete_store,incomplete_store,entangled_server, \
				 tor_proxy,i2p_proxy,socks_proxy,use_exit_node,server_connection,timeout, \
				 log_traffic_callback,valmerge,bypasstoken):
		self.gnupg = gnupg
		self.logger = logging.getLogger(__name__)
		self.block_store = block_store
		self.complete_store = complete_store
		self.incomplete_store = incomplete_store
		self.entangled_server = entangled_server
		self.tor_proxy = tor_proxy # address:port
		self.i2p_proxy = i2p_proxy # address:port
		self.socks_proxy = socks_proxy # address:port
		self.use_exit_node = use_exit_node
		self.server_connection = server_connection
		self.timeout = timeout
		self.log_traffic_callback = log_traffic_callback
		self.valmerge = valmerge
		self.bypasstoken = bypasstoken
		self.shutdown_flag = False

	def get_new_messages(self,keyid,callback,validate_cert_callback,status_callback,
						 key_announcement = None,since_date = None,
						 server = None,entangled_mode = None,userhash = None,authkey = None,
						 mailboxes = None,sender_proof_of_work = None):
		keyidH = keyid.encode("hex")
		self.completion_callback = callback
		self.validate_cert_callback = validate_cert_callback
		self.status_callback = status_callback
		self.since_date = since_date
		self.fetch_data_mode = False
		self.userhash = userhash
		self.authkey = authkey
		self.error_messages = [ ]
		self.bypasstoken_earliest = None
		if key_announcement == None:
			found,key_announcement = self.block_store.retrieve(keyidH)
			if found == False:
				self.error_messages.append('Key not found: ' + keyidH)
				twisted.internet.reactor.callLater(0.1,self.completion_callback,self.error_messages)
				return

		for line in key_announcement.split('\n'):
			line = line.rstrip('\r\n')
			lineL = line.lower()
			if lineL[0:19] == 'senderproofofwork: ':
				self.sender_proof_of_work = line[19:]
			elif lineL[0:11] == 'mailboxes: ':
				self.mailboxes = line[11:].rstrip('\r\n\t')
			elif lineL[0:11] == 'transport: ':
				self.transport = line[11:]
			elif lineL[0:21] == "bypasstokenaccepted: ":
				self.bypasstoken_earliest = line[21:]

		if mailboxes != None:
			self.mailboxes = mailboxes
		if sender_proof_of_work != None and sender_proof_of_work != 'ignore':
			self.sender_proof_of_work = sender_proof_of_work
		if sender_proof_of_work == 'ignore':
			self.pow_nbits_req = 0
			self.pow_nmatches_req = 0
		else:
			bd,nb,nm = self.sender_proof_of_work.split(',')
			self.pow_nbits_req = int(nb)
			self.pow_nmatches_req = int(nm)

		if entangled_mode == None:
			if self.transport.lower() == 'entangled':
				entangled_mode = True
			else:
				entangled_mode = False
		self.entangled_mode = entangled_mode

		if entangled_mode == True:
			if server == None:
				self.server = self.entangled_server
			else:
				self.server = server
		else:
			if server == None:
				self.server = self.transport
			else:
				self.server = server

		#DBGOUT#print "self.sender_proof_of_work",self.sender_proof_of_work
		#DBGOUT#print "self.server",self.server
		
		self.mailbox_hashes = [ ]
		for prefix in self.mailboxes.split(','):
			hash = hashlib.new('sha1')
			hash.update(prefix)
			hash.update(keyid)
			mailbox = hash.digest()
			self.mailbox_hashes.append(mailbox)

		self.fetch_servers = self.server[7:].split(',') # skipping server=
		self.fetch_data_servers = self.fetch_servers[0:] # COPY! Otherwise pop(0) depletes both lists
		if len(self.fetch_servers) > 1:
			self.fetch_servers = re_order_servers(self.fetch_servers,self.use_exit_node,self.server_connection)

		self.blocks_needed = None
		self.session_terminated = False
		self.hash_pending = None
		self.start_next_server()
		
	def start_next_server(self):
		if self.shutdown_flag == True:
			self.error_messages.append('Shutdown')
			self.completion_callback(self.error_messages)
			return
		if len(self.fetch_servers) == 0:
			self.error_messages.append("Ran out of servers fetching mailboxes")
			self.session_terminated = True
			self.get_data_blocks()
			return

		self.fetch_server = self.fetch_servers.pop(0)
		sockshost = None
		socksport = None
		if re_server_is_tor.match(self.fetch_server):
			if self.tor_proxy == None:
				self.error_messages.append("got tor server and no tor proxy configured")
				self.start_next_server()
				return
			sockshost,socksport = self.tor_proxy.rsplit(':',1)
		elif re_server_is_i2p.match(self.fetch_server):
			if self.i2p_proxy == None:
				self.error_messages.append("got i2p server and no i2p proxy configured")
				self.start_next_server()
				return
			sockshost,socksport = self.i2p_proxy.rsplit(':',1)
		elif self.use_exit_node == True:
			if self.tor_proxy == None:
				self.error_messages.append("got use exit node and no tor proxy configured")
				self.start_next_server()
				return
			sockshost,socksport = self.tor_proxy.rsplit(':',1)
		elif self.socks_proxy != None:
			sockshost,socksport = self.socks_proxy.rsplit(':',1)
		else:
			nethost,netport = self.fetch_server.rsplit(':',1)
			netport = int(netport)

		if socksport != None:
			socksport = int(socksport)

		nethost,netport = self.fetch_server.rsplit(':',1)
		netport = int(netport)
		self.nethost = nethost
		self.netport = netport

		endpoint = client.getEndpoint(twisted.internet.reactor,nethost,netport,self.timeout,bindAddress=None,socksHost = sockshost,socksPort = socksport)
		#DBGOUT#if sockshost != None:
			#DBGOUT#self.logger.debug("Starting connection %s %i via socks %s %i",nethost,netport,sockshost,socksport)
		#DBGOUT#else:
			#DBGOUT#self.logger.debug("Starting connection %s %i direct",nethost,netport)

		if self.fetch_data_mode == True:
			clientProt = client.clientProtocol(self.data_client_completion_callback,None,self.timeout,logCallback = self.log_traffic_callback)
		else:
			clientProt = client.clientProtocol(self.announcements_client_completion_callback,None,self.timeout,logCallback = self.log_traffic_callback)
		clientProt.openConnection(endpoint,userhash = self.userhash,authkey = self.authkey)

	def send_next_fetch_announcements(self,client):
		if self.hash_pending == None:
			if len(self.mailbox_hashes) != 0:
				self.status_callback('Check Mail ' + str(len(self.mailbox_hashes)))
				self.hash_pending = self.mailbox_hashes.pop(0)
		if self.shutdown_flag == True or self.hash_pending == None:
			command = "QUIT"
		else:		
			if self.entangled_mode == True:
				if self.since_date == None:
					command = "GET ENTANGLED " + self.hash_pending.encode("hex")
				else:
					command = "GET ENTANGLED " + self.hash_pending.encode("hex") + ' SINCE ' + self.since_date
			else:
				if self.since_date == None:
					command = "GET SERVER " + self.hash_pending.encode("hex")
				else:
					command = "GET SERVER " + self.hash_pending.encode("hex") + ' SINCE ' + self.since_date
		client.sendCommand(command,None)

	def report_error_once(self,announcement_id,error_message): # report on second occurrence only
		errPath = self.block_store.getPath(announcement_id) + '.ERR'
		if os.path.exists(errPath):
			fh = open(errPath,'r')
			num_errors = fh.read()
			num_errors = int(num_errors)
			fh.close()
		else:
			num_errors = 0
		num_errors += 1
		fh = open(errPath,'w')
		fh.write(str(num_errors))
		fh.close()
		if num_errors == 2:
			self.error_messages.append(error_message)

	# Stores an announcement and its list of needed data blocks
	def save_or_check_announcement(self,announcement):
		hasher = hashlib.new('sha1')
		have_all_blocks = True
		nblocks = 0
		expired = False
		blocks_needed = [ ]
		btoken = None
		block_date = ""
		dbs = ""
		rec = ""
		mh = ""

		for line in announcement:
			lineL = line.lower()
			match = re_db.match(line)
			if match:
				blockhashH = match.group(1)
				blockhash = blockhashH.decode("hex")
				dbs += blockhash
				nblocks += 1
				hasher.update(blockhash)
				if self.block_store.exists(blockhashH) == False:
					if self.blocks_needed != None:
						blocks_needed.append(blockhash)
					have_all_blocks = False
			elif lineL[0:6] == 'date: ':
				block_date = line[6:]
			elif lineL[0:13] == 'bypasstoken: ':
				btoken = line[13:]
			else:
				match = re_mh.match(line)
				if match:
					mh = match.group(1).decode("hex")
					continue
				match = re_rec.match(line)
				if match:
					rec = match.group(1).decode("hex")
					continue

		savehash = hasher.digest()
		savehashH = savehash.encode("hex")
		pow_nbits_req = self.pow_nbits_req
		pow_nmatches_req = self.pow_nmatches_req

		# Do not re-download existing or deleted emails
		zipPath = self.block_store.getPath(savehashH) + '.ZIP'
		if os.path.exists(zipPath):
			self.logger.debug("Message already downloaded: "+savehashH)
			self.incomplete_store.__delitem__(savehashH)
			return

		delPath = self.block_store.getPath(savehashH) + '.DEL'
		if os.path.exists(delPath):
			self.logger.debug("Message is deleted: "+savehashH)
			self.incomplete_store.__delitem__(savehashH)
			return

		if self.bypasstoken != None and btoken != None:
			powblock = rec + mh + block_date + dbs
			match = self.bypasstoken.verify_bypass_hash(btoken,powblock)
			if match != None:
				pow_nbits_req = 0
				pow_nmatches_req = 0

		is_valid,posting_datetime,recip,invalid_reason = self.valmerge.validate_message_announcement(None,announcement,False,pow_nbits_req,pow_nmatches_req,True)
		if is_valid == False:
			self.logger.debug("Announcement invalid: %s",invalid_reason)
			if invalid_reason.find("Message proof of work no good") >= 0:
				# Various cases where this would occur once, so report it on second occurrence
				self.report_error_once(savehashH,"Announcement invalid: %s" % (invalid_reason))
			else:
				self.error_messages.append("Announcement invalid: %s" % (invalid_reason))
			self.incomplete_store.__delitem__(savehashH)
			return

		if block_date == None:
			expired = True
		else:
			current_datetime = datetime.datetime.utcnow()
			posting_datetime = datetime.datetime.strptime(block_date,"%Y-%m-%dT%H:%M:%SZ")
			ageS = (current_datetime - posting_datetime).total_seconds()
			if ageS > global_config.max_age_message:
				expired = True
				
		if expired == True:			
			self.logger.debug("Expired incomplete message %s date %s age %i sec",savehashH,block_date,ageS)
			self.delete_data_blocks(None,announcement)
			self.incomplete_store.__delitem__(savehashH)
			errPath = self.block_store.getPath(savehashH) + '.ERR'
			if os.path.isfile(errPath):
				os.unlink(errPath)
			return

		if nblocks == 0:
			self.logger.debug("Got zero data blocks in announcement: " + savehashH)
			self.error_messages.append("Got zero data blocks in announcement: " + savehashH)
			self.incomplete_store.__delitem__(savehashH)
			return
		
		if self.blocks_needed != None:
			self.blocks_needed.extend(blocks_needed)
		found_complete_store = self.complete_store.exists(savehashH) or \
			self.block_store.exists(savehashH)
		found_incomplete_store = self.incomplete_store.exists(savehashH)

		if (found_incomplete_store == True) and (found_complete_store == True) and (have_all_blocks == True):
			#DBGOUT#self.logger.debug("Announcement %s was complete and in both lists",savehashH)
			self.incomplete_store.__delitem__(savehashH)
		elif (found_incomplete_store == True) and (found_complete_store == True) and (have_all_blocks == False):
			#DBGOUT#self.logger.debug("Announcement %s was incomplete and in both lists",savehashH)
			self.complete_store.__delitem__(savehashH)
			self.block_store.__delitem__(savehashH)
		elif (found_complete_store == True) and (have_all_blocks == False):
			#DBGOUT#self.logger.debug("Announcement %s was in complete list with data blocks missing",savehashH)
			self.incomplete_store.storeList(savehashH,announcement)
			self.complete_store.__delitem__(savehashH)
			self.block_store.__delitem__(savehashH)
		elif (found_incomplete_store == True) and (have_all_blocks == True):
			#DBGOUT#self.logger.debug("Announcement %s was incomplete and is now complete",savehashH)
			self.complete_store.storeList(savehashH,announcement)
			self.block_store.storeList(savehashH,announcement)
			self.incomplete_store.__delitem__(savehashH)
		elif (found_incomplete_store == False) and (found_complete_store == False) and (have_all_blocks == False):
			#DBGOUT#self.logger.debug("Announcement %s was new and incomplete",savehashH)
			self.incomplete_store.storeList(savehashH,announcement)
		elif (found_incomplete_store == False) and (found_complete_store == False) and (have_all_blocks == True):
			#DBGOUT#self.logger.debug("Announcement %s was new and complete",savehashH)
			self.complete_store.storeList(savehashH,announcement)
			self.block_store.storeList(savehashH,announcement)

	def process_received_announcements(self,messages):
		this_message = [ ]
		new_announcements = [ ]
		for line in messages:
			lineL = line.lower()
			if lineL == "nextmessage":
				self.save_or_check_announcement(this_message)
				this_message = [ ]
			else:
				this_message.append(line)
		if len(this_message) > 0:
			self.save_or_check_announcement(this_message)

	def announcements_client_completion_callback(self,client,context,command,resultmsg,textdata,bindata):
		resultL = resultmsg.lower()
		if self.session_terminated == True:
			return # ignore spurious message

		#DBGOUT#print "announcement completion result",resultL,textdata
		if resultL == "connected" and self.validate_cert_callback != None:
			validate_result = self.validate_cert_callback(self.nethost,self.netport,client.serverCertificate)
			if validate_result == False: # This abort logic is not being used and has not been checked out.
				send_command = "QUIT"
				client.sendCommand(send_command,None)
				return	

		if resultL == "connected": # new connection
			self.send_next_fetch_announcements(client)
		elif resultL == "found": # got result
			self.process_received_announcements(textdata)
			self.hash_pending = None
			self.send_next_fetch_announcements(client)
		elif resultL == "not found": # got no result
			self.hash_pending = None
			self.send_next_fetch_announcements(client)
		elif resultL == "disconnect" or resultL == "connect failed" or client.connectionClosed == True:
			if resultL != "disconnect":
				self.error_messages.append(self.fetch_server + ': ' + resultmsg)
				self.error_messages.extend(textdata)
			if self.hash_pending == None and len(self.mailbox_hashes) == 0:
				#DBGOUT#self.logger.debug("Done fetching all mailboxes")
				self.session_terminated = True
				self.get_data_blocks()
			else:
				self.start_next_server()
		else: # unknown but still connected
			client.sendCommand("QUIT",None)

	def get_data_blocks(self):
		self.blocks_needed = [ ]
		incomplete_messages = self.incomplete_store.keys()
		for key in incomplete_messages:
			keyH = key.encode("hex")
			found,announcement = self.incomplete_store.retrieveHeaders(keyH)
			if found:
				self.save_or_check_announcement(announcement)
		if len(self.blocks_needed) == 0:
			#DBGOUT#self.logger.debug("No new data blocks to download")
			self.completion_callback(self.error_messages)
			return
		#DBGOUT#else:
			#DBGOUT#self.logger.debug("Need to download %i data blocks",len(self.blocks_needed))
		
		self.new_data_blocks_received = 0
		self.fetch_data_mode = True
		self.fetch_servers = self.fetch_data_servers[0:] # COPY! Otherwise pop(0) depletes both lists
		if len(self.fetch_servers) > 1:
			self.fetch_servers = re_order_servers(self.fetch_servers,self.use_exit_node,self.server_connection)

		self.session_terminated = False
		self.hash_pending = None
		self.start_next_server()
		
	def send_next_fetch_data(self,client):
		if self.hash_pending == None:
			if len(self.blocks_needed) != 0:
				self.status_callback('Get Block ' + str(len(self.blocks_needed)))
				self.hash_pending = self.blocks_needed.pop(0)
		if self.shutdown_flag == True or self.hash_pending == None:
			command = "QUIT"
		else:		
			if self.entangled_mode == True:
				command = "GET ENTANGLED " + self.hash_pending.encode("hex")
			else:
				command = "GET SERVER " + self.hash_pending.encode("hex")
		client.sendCommand(command,None)

	def process_received_data(self,key,textdata,bindata):
		keyH = key.encode("hex")
		len_data = -1
		textstr = ""
		for line in textdata:
			lineL = line.lower()
			if (lineL[0:6] == 'type: ') and (lineL != 'type: data'):
				self.error_messages.append("Got %s, expecting type: data for key %s" % (line,keyH))
				return
			match = re_data.match(line)
			if match:
				len_data = int(match.group(1))
			textstr += line + '\n'
			
		if len_data != len(bindata):
			self.error_messages.append("Got %i bytes, expected %i for key %s",(len(bindata),len_data,keyH))
			return
		hasher = hashlib.new('sha1')
		hasher.update(bindata)
		data_hash = hasher.digest()
		if data_hash != key:
			self.error_messages.append("Got bad hash %s for key %s" % (data_hash.encode("hex"),keyH))
			return
		self.block_store.store(keyH,textstr + bindata)
		self.new_data_blocks_received += 1

	def data_client_completion_callback(self,client,context,command,resultmsg,textdata,bindata):
		resultL = resultmsg.lower()
		if self.session_terminated == True:
			return # ignore spurious message

		#DBGOUT#print "data completion result",resultL
		if resultL == "connected" and self.validate_cert_callback != None:
			validate_result = self.validate_cert_callback(self.nethost,self.netport,client.serverCertificate)
			if validate_result == False: # This abort logic is not being used and has not been checked out.
				send_command = "QUIT"
				client.sendCommand(send_command,None)
				return	

		if resultL == "connected": # new connection
			self.send_next_fetch_data(client)
		elif resultL == "found": # got result
			self.process_received_data(self.hash_pending,textdata,bindata)
			self.hash_pending = None
			self.send_next_fetch_data(client)
		elif resultL == "not found": # got no result
			self.hash_pending = None
			self.send_next_fetch_data(client)
		elif resultL == "disconnect" or resultL == "connect failed" or client.connectionClosed == True:
			if resultL != "disconnect":
				self.error_messages.append(self.fetch_server + ': ' + resultmsg)
				self.error_messages.extend(textdata)
			if self.hash_pending == None and len(self.blocks_needed) == 0:
				#DBGOUT#self.logger.debug("Done fetching all data")
				self.session_terminated = True
				self.get_data_finalize()
			elif len(self.fetch_servers) == 0:
				#DBGOUT#self.logger.debug("Unable to fetch all data")
				self.session_terminated = True
				self.get_data_finalize()
			else:
				self.start_next_server()
		else: # unknown but still connected
			client.sendCommand("QUIT",None)
			
	def get_data_finalize(self):
		#DBGOUT#self.logger.debug("Downloaded %i new data blocks",self.new_data_blocks_received)
		if self.new_data_blocks_received > 0:
			incomplete_messages = self.incomplete_store.keys()
			for key in incomplete_messages:
				keyH = key.encode("hex")
				found,announcement = self.incomplete_store.retrieveHeaders(keyH)
				if found:
					self.save_or_check_announcement(announcement)
		#DBGOUT#self.logger.debug("Done fetching")
		self.completion_callback(self.error_messages)
									
	def reassemble_message(self,announcement_id,dest_path):
		found,announcement = self.block_store.retrieveHeaders(announcement_id)
		if found == False:
			return False,'Announcement not found'
		filehandle = open(dest_path,'wb')
		hasher = hashlib.new('sha1')
		expected_hash = ""
		fail_reason = None
		for line in announcement:
			line = line.rstrip('\r\n')
			match = re_db.match(line)
			if match:
				datablock_id = match.group(1)
				found,block = self.block_store.retrieve(datablock_id)
				if found == False:
					fail_reason = 'Data block '+datablock_id+' not found'
					self.error_messages.append("Data block not found: " + datablock_id) 
					break
				while block != "":
					line,block = block.split("\n",1)
					lineL = line.lower()
					if lineL[0:6] == 'data: ':
						break
				hasher.update(block)
				filehandle.write(block)
				continue
			match = re_mh.match(line)
			if match:
				expected_hash = match.group(1).decode('hex')

		filehandle.close()
		actual_hash = hasher.digest()
		if fail_reason == None and actual_hash != expected_hash:
			fail_reason = 'Message hash incorrect'
			self.error_messages.append("Message hash incorrect: " + datablock_id) 
		if fail_reason != None:
			os.unlink(dest_path)
			return False,fail_reason
		else:
			return True,None	
		
	def delete_data_blocks(self,announcement_id,announcement_lines = None):
		if announcement_id == None:
			found = True
			announcement = announcement_lines
		else:
			found,announcement = self.block_store.retrieveHeaders(announcement_id)
		if found == False:
			return # False,'Announcement not found'
		for line in announcement:
			line = line.rstrip('\r\n')
			match = re_db.match(line)
			if match:
				datablock_id = match.group(1)
				filepath = self.block_store.getPath(datablock_id)
				if os.path.exists(filepath):
					os.unlink(filepath)
					self.logger.debug("Delete data block %s",filepath)

	# Note: I had a real-world failure where a large message failed to decode.
	# I received the whole CM directory and analyzed the failure. One of the data
	# blocks, which had been checked at download, was corrupt when read back.
	# The last partial 512-byte block of the file was all zeroes.
	# Computers do make mistakes.
	def scrub_data_blocks(self,announcement_id,announcement_lines = None):
		fault_found = False
		if announcement_id == None:
			found = True
			announcement = announcement_lines
		else:
			found,announcement = self.block_store.retrieveHeaders(announcement_id)
		if found == False:
			return True # Announcement not found
		for line in announcement:
			line = line.rstrip('\r\n')
			match = re_db.match(line)
			if match:
				datablock_id = match.group(1)
				found,block = self.block_store.retrieve(datablock_id)
				if found == False:
					self.logger.debug("Scrub found missing data block %s",datablock_id)
					fault_found = True
				else:
					while block != "":
						line,block = block.split("\n",1)
						lineL = line.lower()
						if lineL[0:6] == 'data: ':
							break
					hasher = hashlib.new('sha1')
					hasher.update(block)
					actual_hash = hasher.digest()
					if actual_hash != datablock_id.decode("hex"):
						self.logger.debug("Scrub found and deleted corrupt data block %s",datablock_id)
						self.logger.debug("actual " + actual_hash.encode("hex") + " len " + str(len(block)))
						fault_found = True
						filepath = self.block_store.getPath(datablock_id)
						if os.path.exists(filepath):
							os.unlink(filepath)
		return fault_found

	def get_message_acknowledgments(self,keyid,acknowledgments,callback,validate_cert_callback,key_announcement = None,
			server = None, entangled_mode = None, userhash = None,authkey = None):
		keyidH = keyid.encode("hex")
		self.acks_to_find = acknowledgments
		self.acks_found = [ ]
		self.ack_completion_callback = callback
		self.validate_cert_callback = validate_cert_callback
		self.userhash = userhash
		self.authkey = authkey
		self.error_messages = [ ]
		if key_announcement == None:
			found,key_announcement = self.block_store.retrieve(keyidH)
			if found == False:
				#DBGOUT#self.logger.debug('Key not found')
				self.error_messages.append('Key not found: ' + keyidH)
				twisted.internet.reactor.callLater(0.1,self.ack_completion_callback,acks_found)
				return

		for line in key_announcement.split('\n'):
			line = line.rstrip('\r\n')
			lineL = line.lower()
			if lineL[0:19] == 'senderproofofwork: ':
				self.sender_proof_of_work = line[19:]
			elif lineL[0:11] == 'mailboxes: ':
				self.mailboxes = line[11:].rstrip('\r\n\t')
			elif lineL[0:11] == 'transport: ':
				self.transport = line[11:]

		if entangled_mode == None:
			if self.transport.lower() == 'entangled':
				entangled_mode = True
			else:
				entangled_mode = False
		self.entangled_mode = entangled_mode

		if entangled_mode == True:
			if server == None:
				self.server = self.entangled_server
			else:
				self.server = server
		else:
			if server == None:
				self.server = self.transport
			else:
				self.server = server
		
		self.fetch_servers = self.server[7:].split(',') # skipping server=
		if len(self.fetch_servers) > 1:
			self.fetch_servers = re_order_servers(self.fetch_servers,self.use_exit_node,self.server_connection)

		self.session_terminated = False
		self.hash_pending = None
		self.start_next_ack_server()
		
	def start_next_ack_server(self):
		if self.shutdown_flag == True:
			self.error_messages.append('Shutdown')
			self.ack_completion_callback(self.acks_found,self.error_messages)
			return
		if len(self.fetch_servers) == 0:
			#DBGOUT#self.logger.debug("Unable to fetch all acks")
			self.session_terminated = True
			self.get_ack_finalize()
			return

		self.fetch_server = self.fetch_servers.pop(0)
		nethost,netport = self.fetch_server.rsplit(':',1)
		netport = int(netport)
		sockshost = None
		socksport = None

		if re_server_is_tor.match(self.fetch_server):
			if self.tor_proxy == None:
				self.error_messages.append("got tor server and no tor proxy configured")
				self.start_next_ack_server()
				return
			sockshost,socksport = self.tor_proxy.rsplit(':',1)
		elif re_server_is_i2p.match(self.fetch_server):
			if self.i2p_proxy == None:
				self.error_messages.append("got i2p server and no i2p proxy configured")
				self.start_next_ack_server()
				return
			sockshost,socksport = self.i2p_proxy.rsplit(':',1)
		elif self.use_exit_node == True:
			if self.tor_proxy == None:
				self.error_messages.append("got use exit node and no tor proxy configured")
				self.start_next_ack_server()
				return
			sockshost,socksport = self.tor_proxy.rsplit(':',1)
		elif self.socks_proxy != None:
			sockshost,socksport = self.socks_proxy.rsplit(':',1)
		else:
			nethost,netport = self.fetch_server.rsplit(':',1)
			netport = int(netport)

		if socksport != None:
			socksport = int(socksport)

		nethost,netport = self.fetch_server.rsplit(':',1)
		netport = int(netport)
		self.nethost = nethost
		self.netport = netport

		endpoint = client.getEndpoint(twisted.internet.reactor,nethost,netport,self.timeout,bindAddress=None,socksHost = sockshost,socksPort = socksport)
		#DBGOUT#if sockshost != None:
			#DBGOUT#self.logger.debug("Starting get ack connection %s %i via socks %s %i",nethost,netport,sockshost,socksport)
		#DBGOUT#else:
			#DBGOUT#self.logger.debug("Starting get ack connection %s %i direct",nethost,netport)
		clientProt = client.clientProtocol(self.ack_client_completion_callback,None,self.timeout,logCallback = self.log_traffic_callback)
		clientProt.openConnection(endpoint,userhash = self.userhash,authkey = self.authkey)
			
	def send_next_fetch_ack(self,client):
		if self.hash_pending == None:
			if len(self.acks_to_find) != 0:
				self.hash_pending = self.acks_to_find.pop(0)
		if self.shutdown_flag == True or self.hash_pending == None:
			command = "QUIT"
		else:		
			if self.entangled_mode == True:
				command = "GET ENTANGLED " + self.hash_pending.encode("hex")
			else:
				command = "GET SERVER " + self.hash_pending.encode("hex")
		client.sendCommand(command,None)

	def process_received_ack(self,message):
		hash = None
		for line in message:
			m = re_ah.match(line)
			if m:
				prehash = m.group(1)
		if prehash == None:
			return	
		hasher = hashlib.new('sha1')
		hasher.update(prehash.decode('hex'))
		testhash = hasher.digest()
		if testhash == self.hash_pending:
			self.block_store.storeList(self.hash_pending.encode('hex'),message)
			self.acks_found.append(self.hash_pending)

	def get_ack_finalize(self):
			self.ack_completion_callback(self.acks_found,self.error_messages)

	def ack_client_completion_callback(self,client,context,command,resultmsg,textdata,bindata):
		resultL = resultmsg.lower()
		if self.session_terminated == True:
			return # ignore spurious message

		#DBGOUT#print "ack completion result",resultL,textdata
		if resultL == "connected" and self.validate_cert_callback != None:
			validate_result = self.validate_cert_callback(self.nethost,self.netport,client.serverCertificate)
			if validate_result == False: # This abort logic is not being used and has not been checked out.
				send_command = "QUIT"
				client.sendCommand(send_command,None)
				return	

		if resultL == "connected": # new connection
			self.send_next_fetch_ack(client)
		elif resultL == "found": # got result
			self.process_received_ack(textdata)
			self.hash_pending = None
			self.send_next_fetch_ack(client)
		elif resultL == "not found": # got no result
			self.hash_pending = None
			self.send_next_fetch_ack(client)
		elif resultL == "disconnect" or resultL == "connect failed" or client.connectionClosed == True:
			if resultL != "disconnect":
				self.error_messages.append(self.fetch_server + ': ' + resultmsg)
				self.error_messages.extend(textdata)
			if self.hash_pending == None and len(self.acks_to_find) == 0:
				#DBGOUT#self.logger.debug("Done fetching all acks")
				self.session_terminated = True
				self.get_ack_finalize()
			else:
				self.start_next_ack_server()
		else: # unknown but still connected
			client.sendCommand("QUIT",None)

	def shutdown(self):
		self.shutdown_flag = True			


# EOF
