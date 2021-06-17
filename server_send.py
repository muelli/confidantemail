import re
import logging
import datetime
import hashlib
import random
import time
import threading
import twisted.protocols.basic
import twisted.internet.protocol
import twisted.internet.reactor
import twisted.internet.endpoints
import flatstore
import filelock
import client

re_loginuser = re.compile("^LOGINUSER: ([0-9A-Z]{8,40})$",re.IGNORECASE)
re_embargo = re.compile("^EMBARGO: (\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ)$",re.IGNORECASE)
re_server_is_tor = re.compile('.*\.onion:\d+$',re.IGNORECASE)
re_server_is_i2p = re.compile('.*\.i2p:\d+$',re.IGNORECASE)
re_datetime = re.compile("^DATE: (\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ)$",re.IGNORECASE)

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

class serverSend:
	def __init__(self,localstore,sendqueue,server_port,replication_peer,repl_authkey, \
				 repl_cert,tor_proxy,i2p_proxy,socks_proxy,use_exit_node, \
				 run_queue_interval,expire_days,retry_schedule,timeout, \
				 log_all_traffic,preferred_connection):
		self.logger = logging.getLogger(__name__)
		self.localstore = localstore
		self.sendqueue = sendqueue
		self.server_port = server_port
		self.entangled_server = 'server=localhost:' + str(server_port)
		self.replication_peer = replication_peer
		self.repl_userhash = 'replication'
		self.repl_authkey = repl_authkey
		self.repl_cert = repl_cert
		self.tor_proxy = tor_proxy
		self.i2p_proxy = i2p_proxy
		self.socks_proxy = socks_proxy
		self.use_exit_node = use_exit_node
		self.timeout = timeout
		self.preferred_connection = preferred_connection
		#self.keyqueue = [ ]
		self.clientProt = None
		self.done_with_target = False
		self.expireDays = expire_days
		self.expireSec = self.expireDays * 86400
		self.failsByTarget = dict()
		self.lastAttemptByTarget = dict()
		self.sendInProgress = False
		self.stepPauseInterval = 0.1
		self.runQueueInterval = run_queue_interval
		self.lastRunQueue = datetime.datetime.min
		self.retrySchedule = retry_schedule
		self.delayedBlocks = dict()
		if log_all_traffic == True:
			self.logCallback = self.logWriter
		else:
			self.logCallback = None

	def logWriter(self,typ,data):
		self.logger.info('S%s %s',typ,data)

	def initialLoadStart(self):
		#DBGOUT#self.logger.debug("Server send started")
		twisted.internet.reactor.callLater(10,self.runQueue) # startup interval

	def runQueue(self):
		twisted.internet.reactor.callLater(self.runQueueInterval,self.runQueue)
		self.submitKeys(None)
		self.lastRunQueue = datetime.datetime.utcnow()

	def submitKeys(self,keyids):
		#DBGOUT#self.logger.debug("submitKeys called " + str(self.sendInProgress))
		if self.sendInProgress == False:
			self.startGeneratePostingList()	

	def validate_server_certificate(self,nethost,netport,server_cert):
		write_cert_file = False
		cert_desc = "Server: " + nethost + " port " + str(netport) + "\n" + \
 			"Digest: " + str(server_cert.digest('sha1')) + "\n" + \
 			"Serial: " + str(server_cert.get_serial_number()) + "\n" + \
 			"Type: " + str(server_cert.get_signature_algorithm()) + \
			' ' + str(server_cert.get_pubkey().bits()) + " bits\n" + \
 			"Subject: " + str(server_cert.get_subject()) + "\n" + \
 			"Issuer: " + str(server_cert.get_issuer()) + "\n" + \
 			"Valid from: " + str(server_cert.get_notBefore()) + "\n" + \
 			"Valid until: " + str(server_cert.get_notAfter()) + "\n"
		server_str = nethost + ':' + str(netport)
		hasher = hashlib.new('sha1')
		hasher.update(server_str)
		server_hash = hasher.digest().encode('hex')
		lock = filelock.filelock(self.localstore.getLockfile(server_hash))
		lock.lock_wait()
		if self.localstore.exists(server_hash) == False:
			self.logger.warning('Certificate for new %s',cert_desc)
			write_cert_file = True
		else:
			found,old_cert_desc = self.localstore.retrieve(server_hash)
			if old_cert_desc != cert_desc:
				self.logger.warning('Certificate changed for %s',cert_desc)
				self.logger.warning('Old certificate for %s',old_cert_desc)
				write_cert_file = True
		if write_cert_file == True:
			self.localstore.store(server_hash,cert_desc)
		lock.unlock_close()
		return True

	def startGeneratePostingList(self):
		self.sendInProgress = True
		self.post_targets_nondata = { }
		self.post_targets = { }
		self.post_blocks = { }
		self.blocks_to_send = self.sendqueue.keys()
		twisted.internet.reactor.callLater(self.stepPauseInterval,self.genPostingListNext)

	def genPostingListNext(self):
		if len(self.blocks_to_send) == 0:
			self.genPostingListFinish()
		else:
			key = self.blocks_to_send.pop(0)
			keyH = key.encode("hex")
			nowtime = datetime.datetime.utcnow()
			self.lastRunQueue = nowtime

			if key in self.delayedBlocks and self.delayedBlocks[key] > nowtime:
				self.logger.debug("Skipping delayed block %s now %s dt %s",keyH,nowtime,self.delayedBlocks[key])
				twisted.internet.reactor.callLater(self.stepPauseInterval,self.genPostingListNext)
				return

			found,headers = self.sendqueue.retrieveHeaders(keyH)
			if found == False:
				#DBGOUT#self.logger.debug("Block not found: %s",keyH)
				twisted.internet.reactor.callLater(self.stepPauseInterval,self.genPostingListNext)
				return
			post_to = [ ]
			is_data = False
			is_replicate = False
			embargo_until = None
			block_date = None
			for line in headers:
				lineL = line.lower()
				m = re_embargo.match(line)
				if m:
					embargo_until = datetime.datetime.strptime(m.group(1),"%Y-%m-%dT%H:%M:%SZ")
					if embargo_until > nowtime:
						self.delayedBlocks[key] = embargo_until
						twisted.internet.reactor.callLater(self.stepPauseInterval,self.genPostingListNext)
						return
				else:
					m = re_datetime.match(line)
					if m:
						block_date = datetime.datetime.strptime(m.group(1),"%Y-%m-%dT%H:%M:%SZ")
					elif lineL == 'storetype: replicate':
						post_to.append('replicate')
						is_replicate = True
					elif lineL[0:9] == 'post-to: ':
						post_to.append(line[9:])
					elif lineL == 'type: data':
						is_data = True

			# Expire proxy message that is undeliverable for too long
			if is_replicate == False and (
				(embargo_until == None and (nowtime - block_date).total_seconds() > self.expireSec) or
				(embargo_until != None and (embargo_until - block_date).total_seconds() > self.expireSec)):
				#DBGOUT#self.logger.debug("Block %s expired")
				self.sendqueue.__delitem__(keyH)
				if key in self.delayedBlocks:
					del self.delayedBlocks[key]
				twisted.internet.reactor.callLater(self.stepPauseInterval,self.genPostingListNext)
				return

			for target in post_to:
				if is_data:
					if target not in self.post_targets:
						self.post_targets[target] = [ ]
					self.post_targets[target].append(key)
				else:
					if target not in self.post_targets_nondata:
						self.post_targets_nondata[target] = [ ]
					self.post_targets_nondata[target].append(key)
				if key not in self.post_blocks:
					self.post_blocks[key] = set()
				self.post_blocks[key].add(target)
			twisted.internet.reactor.callLater(self.stepPauseInterval,self.genPostingListNext)

	def genPostingListFinish(self):
		for target in self.post_targets_nondata.keys():
			if target not in self.post_targets:
				self.post_targets[target] = [ ]
			self.post_targets[target].extend(self.post_targets_nondata[target])
		self.post_targets_list = self.post_targets.keys()
		if len(self.post_targets_list) > 0:
			self.session_terminated = False
			self.posted_blocks_dict = { }
			self.start_new_target()
		else:
			self.done_posting_messages()

	# Returns command tuple if there is one, None if empty
	def generate_next_post_key(self,post_target):
		key_list = self.post_targets[post_target]
		if len(key_list) == 0:
			return None,None

		key = key_list.pop(0)
		keyH = key.encode("hex")

		found,block = self.sendqueue.retrieve(keyH)
		if found == False:
			#DBGOUT#self.logger.debug("Block not found: %s",keyH)
			return self.generate_next_post_key(post_target)


		text = ""
		data = None
		loginuser = 'none'
		sendkey = None
		replogin_user = None
		replogin_auth = None
		while block != "":
			line,rest = block.split("\n",1)
			lineL = line.lower()
			if lineL == 'storetype: replicate':
				block = rest	
			elif lineL == 'storetype: proxy':
				block = rest	
			elif lineL[0:9] == 'embargo: ':
				block = rest	
			elif sendkey == None and lineL[0:12] == 'storekeyid: ': # grab only the first one
				sendkey = line[12:].upper()
				block = rest	
			elif lineL[0:6] == 'data: ':
				data = rest
				break
			elif lineL[0:9] == 'post-to: ':
				block = rest	
			elif lineL[0:11] == 'loginuser: ':
				loginuser = line[11:]
				block = rest	
			elif lineL[0:15] == 'replogin-user: ':
				replogin_user = line[15:]
				block = rest	
			elif lineL[0:15] == 'replogin-auth: ':
				replogin_auth = line[15:]
				block = rest	
			else:
				text += line.replace("\r","") + "\r\n"
				block = rest	

		# Implement different types of store here
		post_targetL = post_target.lower()
		if data == None:
			if post_targetL == "entangled":
				send_data = "STORE ENTANGLED " + sendkey,text
			elif post_targetL == "replicate":
				if replogin_auth != None:
					if replogin_user == None:
						replogin_user = 'undefined'
					send_data = "REPLOGIN " + replogin_user + ' ' + replogin_auth,None
				else:	
					send_data = "REPLICATE " + sendkey + ' ' + loginuser,text
			else:
				send_data = "STORE SERVER " + sendkey,text
		else:
			if post_targetL == "entangled":
				send_data = "STORE ENTANGLED " + sendkey,text,data
			elif post_targetL == "replicate":
				send_data = "REPLICATE " + sendkey + ' ' + loginuser,text,data
			else:
				send_data = "STORE SERVER " + sendkey,text,data
		return key,send_data

	def post_server_completion_callback(self,client,context,command,resultmsg,textdata,bindata):
		resultL = resultmsg.lower()
		
		if self.session_terminated == True:
			return # ignore spurious message

		#DBGOUT#self.logger.debug("completion result %s %s",resultL,str(self.done_with_target))
		if resultL == "connected": # new connection
			self.validate_server_certificate(self.nethost,self.netport,client.serverCertificate)
			if self.post_target == 'replicate' and self.repl_cert != None and \
				str(client.serverCertificate.digest('sha1')) != self.repl_cert:
				self.logger.error("Replication peer key mismatch, got %s, expected %s, aborted",str(client.serverCertificate.digest('sha1')),self.repl_cert)
				client.sendCommand("QUIT",None)
				return

			if self.command_pending != None:
				key,next_tuple = self.command_pending
				#DBGOUT#self.logger.debug("Scheduling first pending key " + key.encode("hex"))
			else:
				key,next_tuple = self.generate_next_post_key(self.post_target)
				if key == None:
					#DBGOUT#self.logger.debug("Got no key after connect, this should not happen")
					self.done_with_target = True
					self.command_pending = None
					client.sendCommand("QUIT",None)
				else:
					self.command_pending = key,next_tuple
					#DBGOUT#self.logger.debug("Scheduling first new key " + key.encode("hex"))
					client.sendCommand(next_tuple,None)

		elif resultL == "done": # good response
			prev_key,prev_tuple = self.command_pending
			self.command_pending = None
			if prev_key not in self.posted_blocks_dict:
				self.posted_blocks_dict[prev_key] = set()
			self.posted_blocks_dict[prev_key].add(self.post_target)

			key,next_tuple = self.generate_next_post_key(self.post_target)
			if key == None:
				#DBGOUT#self.logger.debug("No more keys, sent quit")
				self.done_with_target = True
				client.sendCommand("QUIT",None)
				self.failsByTarget[self.post_target] = 0
			else:
				self.command_pending = key,next_tuple
				#DBGOUT#self.logger.debug("Scheduling next new key " + key.encode("hex"))
				client.sendCommand(next_tuple,None)
				
		elif resultL == "disconnect" and self.done_with_target == True: # good disconnect
			self.start_new_target()
			
		elif resultL == "disconnect" or resultL == "connect failed" or client.connectionClosed == True:
			#DBGOUT#self.logger.debug("start new server after connect failure/hangup")
			self.start_new_server()

		else: # command failed but still connected
			# without done_with_target, so we connect to a new server
			client.sendCommand("QUIT",None)

	def start_new_server(self):
		if len(self.post_servers) == 0:
			#DBGOUT#print "start new target after start new server"
			nowtime = datetime.datetime.utcnow()
			self.lastAttemptByTarget[self.post_target] = nowtime
			if self.post_target in self.failsByTarget:
				self.failsByTarget[self.post_target] += 1
			else:
				self.failsByTarget[self.post_target] = 1
			self.start_new_target()
			return

		self.post_server = self.post_servers.pop(0)
		#DBGOUT#self.logger.debug("self.post_server = " + self.post_server)
		sockshost = None
		socksport = None

		if re_server_is_tor.match(self.post_server):
			if self.tor_proxy == None:
				#DBGOUT#print "got tor server and no tor proxy configured"
				self.start_new_server()
				return
			sockshost,socksport = self.tor_proxy.split(':')
		elif re_server_is_i2p.match(self.post_server):
			if self.i2p_proxy == None:
				#DBGOUT#print "got i2p server and no i2p proxy configured"
				self.start_new_server()
				return
			sockshost,socksport = self.i2p_proxy.split(':')
		elif self.use_exit_node == True:
			if self.tor_proxy == None:
				#DBGOUT#print "got use exit node and no tor proxy configured"
				self.start_new_server()
				return
			sockshost,socksport = self.tor_proxy.split(':')
		elif self.socks_proxy != None:
			sockshost,socksport = self.socks_proxy.split(':')

		nethost,netport = self.post_server.split(':')
		netport = int(netport)
		self.nethost = nethost
		self.netport = netport

		if socksport != None:
			socksport = int(socksport)

		self.done_with_target = False
		endpoint = client.getEndpoint(twisted.internet.reactor,nethost,netport,self.timeout,bindAddress=None,socksHost = sockshost,socksPort = socksport)
		if sockshost != None:
			pass
			#DBGOUT#self.logger.debug("Starting connection %s %i via socks %s %i",nethost,netport,sockshost,socksport)
		else:
			pass
			#DBGOUT#self.logger.debug("Starting connection %s %i direct",nethost,netport)
		clientProt = client.clientProtocol(self.post_server_completion_callback,None,self.timeout,logCallback = self.logCallback)
		if self.post_target == 'replicate' and self.repl_authkey != None:
			clientProt.openConnection(endpoint,userhash = self.repl_userhash,authkey = self.repl_authkey)
		else:
			clientProt.openConnection(endpoint)


	def start_new_target(self):
		if len(self.post_targets_list) == 0:
			self.end_posting_message()
			return

		self.post_target = self.post_targets_list.pop(0)
		if self.post_target in self.failsByTarget and self.post_target in self.lastAttemptByTarget:
			nowtime = datetime.datetime.utcnow()
			numFails = self.failsByTarget[self.post_target]
			lastAttempt = self.lastAttemptByTarget[self.post_target]
			if numFails >= len(self.retrySchedule):
				retryDelay = self.retrySchedule[len(self.retrySchedule)-1]
			else:
				retryDelay = self.retrySchedule[numFails]
			if (nowtime - lastAttempt).total_seconds() < retryDelay:
				self.logger.debug("Skipped %s numFails %i now %s last %s tsec %s cond %s delay %s sched %s",self.post_target,numFails,str(nowtime),str(lastAttempt),str((nowtime - lastAttempt).total_seconds()),str((nowtime - lastAttempt).total_seconds() < retryDelay),retryDelay,str(self.retrySchedule))
				for key in self.post_targets[self.post_target]:
					# If this key only has one target, and the target is delayed, skip re-reading
					# the key every pass. Saves a lot of I/O
					if len(self.post_blocks[key]) == 1:
						nextTry = nowtime +  datetime.timedelta(0,retryDelay)
						self.logger.debug("Delaying key %s until %s",key.encode('hex'),nextTry)
						self.delayedBlocks[key] = nextTry
				self.start_new_target()
				return

		if self.post_target == 'replicate':
			self.post_servers = [ self.replication_peer ]
		elif self.post_target.lower() == 'entangled':
			self.post_servers = self.entangled_server[7:].split(',') # skipping server=
		else:
			self.post_servers = self.post_target[7:].split(',') # skipping server=
		if len(self.post_servers) > 1:
			self.post_servers = re_order_servers(self.post_servers,self.use_exit_node,self.preferred_connection)
		self.command_pending = None
		self.start_new_server()

	def update_posting_list(self,block,posting_list):
		new_block = ""
		new_list = ""
		for target in posting_list:
			new_list += "Post-To: " + target + "\n"
		while block != "":
			line,rest = block.split("\n",1)
			lineL = line.lower()
			if lineL[0:9] == 'post-to: ':
				if new_list != None:
					new_block += new_list
					new_list = None	
			elif lineL[0:6] == 'data: ':
				new_block += line + "\n" + rest
				break
			else:
				new_block += line + "\n"
			block = rest
		return new_block

	def end_posting_message(self):
		self.session_terminated = True
		#DBGOUT#self.logger.debug("All targets sent")
		#DBGOUT#self.logger.debug("Blocks to post")
		for key in self.post_blocks.keys():
			line = key.encode("hex") + ": "
			for target in self.post_blocks[key]:
				line += target + ";"
			#DBGOUT#self.logger.debug(line)
		#DBGOUT#self.logger.debug("Blocks posted")
		for key in self.posted_blocks_dict.keys():
			line = key.encode("hex") + ": "
			for target in self.posted_blocks_dict[key]:
				line += target + ";"
			#DBGOUT#self.logger.debug(line)
		#DBGOUT#self.logger.debug("Blocks NOT posted")
		for key in self.posted_blocks_dict.keys():
			line = key.encode("hex") + ": "
			targets_not_posted = self.post_blocks[key].difference(self.posted_blocks_dict[key])
			for target in targets_not_posted:
				line += target + ";"
			#DBGOUT#self.logger.debug(line)

		for key in self.post_blocks.keys():
			keyH = key.encode("hex")
			if key not in self.posted_blocks_dict:
				targets_not_posted = self.post_blocks[key]
			else:
				targets_not_posted = self.post_blocks[key].difference(self.posted_blocks_dict[key])
			if len(targets_not_posted) == 0: # all are posted
				#DBGOUT#self.logger.debug("Deleting key " + keyH)
				self.sendqueue.__delitem__(keyH)
				if key in self.delayedBlocks:
					del self.delayedBlocks[key]
			elif targets_not_posted == self.post_blocks[key]: # none are posted
				pass
				#DBGOUT#self.logger.debug("Leaving key " + keyH + " unchanged")
			else:
				#DBGOUT#self.logger.debug("Rewriting key " + keyH)
				found,block = self.sendqueue.retrieve(keyH)
				if found == False:
					continue # should not happen
				block = self.update_posting_list(block,targets_not_posted)
				self.sendqueue.store(keyH,block)
		self.done_posting_messages()


	def done_posting_messages(self):
		self.sendInProgress = False


# EOF
