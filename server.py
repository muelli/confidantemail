import sys
import threading
import logging
import string
import re
import os
import hashlib
import datetime
import time
import global_config
import twisted.internet.protocol
import twisted.protocols.basic
import twisted.internet.endpoints
import twisted.internet.reactor
import twisted.internet.ssl
import twisted.names.client
import OpenSSL
import entangled.node
import udp_protocol
import filestore
import flatstore
import filelock
import entangled_store
import validate_merge
import server_send
import server_notify
import storutil
import gnupg
if sys.platform != 'win32':
	import daemon

s_waitcmd = 0
s_waitentangled = 1
s_getlinedata = 2
s_getbindata = 3
s_waitdns = 4

c_store_server = 0
c_store_proxy = 1
c_store_proxy_after = 2
c_replicate = 3
c_store_entangled = 4
c_get_entangled = 5
c_dns_txt = 6

re_store_server = re.compile("^STORE SERVER ([0-9A-F]{40})$",re.IGNORECASE)
re_replicate = re.compile("^REPLICATE ([0-9A-F]{40}) ([0-9A-Z]{4,40})$",re.IGNORECASE) # hash user
re_get_server = re.compile("^GET SERVER ([0-9A-F]{40})$",re.IGNORECASE)
re_get_server_since = re.compile("^GET SERVER ([0-9A-F]{40}) SINCE (\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ)$",re.IGNORECASE)
re_store_entangled = re.compile("^STORE ENTANGLED ([0-9A-F]{40})$",re.IGNORECASE)
re_get_entangled = re.compile("^GET ENTANGLED ([0-9A-F]{40})$",re.IGNORECASE)
re_get_entangled_since = re.compile("^GET ENTANGLED ([0-9A-F]{40}) SINCE (\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ)$",re.IGNORECASE)
re_store_proxy = re.compile("^STORE PROXY ([0-9A-F]{40})$",re.IGNORECASE)
re_store_proxy_after = re.compile("^STORE PROXY ([0-9A-F]{40}) AFTER (\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ)$",re.IGNORECASE)
re_login = re.compile("^LOGIN ([0-9A-Z]{8,40}) ([0-9A-Z]{8,40})$",re.IGNORECASE)
re_addlogin = re.compile("^ADDLOGIN ([0-9A-Z]{8,40}) ([0-9A-Z]{8,40})$|^ADDLOGIN ([0-9A-Z]{8,40})$",re.IGNORECASE)
re_rmlogin = re.compile("^RMLOGIN ([0-9A-Z]{8,40})$",re.IGNORECASE)
re_genlogin = re.compile("^GENLOGIN (\d+)$",re.IGNORECASE)
re_replogin = re.compile("^REPLOGIN ([0-9A-Z]{8,40}) ([0-9A-Z]{8,40})$",re.IGNORECASE)
re_dns_txt = re.compile("^DNS TXT ([0-9A-Z\-\.]+)$",re.IGNORECASE)
re_data = re.compile("^DATA: ([1-9][0-9]*)$",re.IGNORECASE)
re_storetype = re.compile("^STORETYPE: ([A-Za-z\-]+)$",re.IGNORECASE)
re_type = re.compile("^TYPE: ([A-Za-z\-]+)$",re.IGNORECASE)
re_loginuser = re.compile("^LOGINUSER: ([0-9A-Z]{4,40})$",re.IGNORECASE)
re_storekeyid = re.compile("^STOREKEYID: ([0-9A-F]{40})$",re.IGNORECASE)
re_datetime = re.compile("^DATE: (\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ)$",re.IGNORECASE)
re_forbidden_headers = re.compile("^storetype: |^storekeyid: |^loginuser: |^embargo: |^replogin-user: |^replogin-auth: ",re.IGNORECASE)
re_server_notify_false = re.compile(".*^\s*ServerNotify: False\s*$.*",re.IGNORECASE|re.MULTILINE|re.DOTALL)


class serverStoreThread:
	def __init__(self,homedir,localstore,inputstore,entangledstore,entangled_node,valmerge):
		self.logger = logging.getLogger(__name__)
		self.homedir = homedir
		self.localstore = localstore
		self.inputstore = inputstore
		self.entangledstore = entangledstore
		self.entangled_node = entangled_node
		self.valmerge = valmerge
		self.queuecond = threading.Condition()
		self.callbackcond = threading.Condition()
		self.servernotify = server_notify.serverNotify(homedir)
		self.keyqueue = [ ]

	def threadRun(self,threadno):
		#DBGOUT#self.logger.debug("Server store thread start wait")
		time.sleep(10)
		#DBGOUT#self.logger.debug("Server store thread started")

		# Queue up any keys left in the input queue
		tempqueue = self.inputstore.keys()
		self.queuecond.acquire(True)
		for k in tempqueue:
			self.keyqueue.append(k.encode('hex'))
		self.queuecond.release()
		tempqueue = None

		while True:
			self.queuecond.acquire(True)
			while len(self.keyqueue) == 0:
				self.queuecond.wait() # this unlocks the condition during wait
			queueid = self.keyqueue.pop(0)
			self.queuecond.release()
			queueparam = None
			if type(queueid) == tuple:
				queueid,queueparam = queueid

			if queueid == "SHUTDOWN":
				break

			if queueid == "SELFTEST":
				# Selftest runs through the store thread to make sure the thread is up.
				twisted.internet.reactor.callFromThread(queueparam.selftest_callback,"PASS")
				continue

			found,block = self.inputstore.retrieve(queueid)
			if found == False:
				continue
				#DBGOUT#self.logger.debug("Tried processing queueid %s but file missing from input queue",queueid)
			else:
				pass
				#DBGOUT#self.logger.debug("Processing queueid %s",queueid)

			type_line,block = block.split('\n',1)
			type_line = type_line.replace('\r','')
			match = re_storetype.match(type_line)
			if not match:
				#DBGOUT#self.logger.debug("Tried processing queueid %s but missing type",queueid)
				self.inputstore.__delitem__(queueid)
				continue
			mtype = match.group(1).upper()

			keyid_line,block = block.split('\n',1)
			keyid_line = keyid_line.replace('\r','')
			match = re_storekeyid.match(keyid_line)
			if not match:
				#DBGOUT#self.logger.debug("Tried processing queueid %s but missing keyid",queueid)
				self.inputstore.__delitem__(queueid)
				continue
			keyid = match.group(1)
			keyidB = keyid.decode('hex')

			if mtype == 'SERVER' or mtype == 'REPL-IN':
				user_line,block = block.split('\n',1)
				user_line = user_line.replace('\r','')
				match = re_loginuser.match(user_line)
				if not match:
					#DBGOUT#self.logger.debug("Tried processing queueid %s but missing user",queueid)
					self.inputstore.__delitem__(queueid)
					continue
				userhash = match.group(1).upper()
			else:
				userhash = None

			if mtype == 'SERVER' or mtype == 'REPL-IN':
				lock = filelock.filelock(self.localstore.getLockfile(keyid))
				lock.lock_wait()
				found,existing_block = self.localstore.retrieve(keyid)
#				if found:
#					pass
#					#DBGOUT#self.logger.debug("Processing server keyid %s from %s with existing block",keyid,userhash)
#				else:
#					pass
#					#DBGOUT#self.logger.debug("Processing server keyid %s from %s without existing block",keyid,userhash)
	
				new_block,notify_recip,error_message = self.valmerge.validate_merge(keyid.decode('hex'),existing_block,block,False,userhash)
				if new_block == None:
					pass
					#DBGOUT#self.logger.debug("Server keyid %s storing no output, message %s",keyid,error_message)
				else:
					self.localstore.store(keyid,new_block)
					if mtype == 'SERVER' and notify_recip != None and notify_recip != '' and re_server_notify_false.match(new_block) == None:
						self.servernotify.notifyRecipient(notify_recip.encode("hex"))
					#DBGOUT#self.logger.debug("Server keyid %s storing output, message %s",keyid,error_message)
				self.inputstore.__delitem__(queueid)
				lock.unlock_close()

			elif mtype == 'ENTANGLED-INCOMING':
				lock = filelock.filelock(self.entangledstore.getLockfile(keyid))
				lock.lock_wait()
				new_headers = block.split('\n',6)
				new_block = new_headers.pop()
				found,existing_block = self.entangledstore.retrieve(keyid)
				if found:
					#DBGOUT#self.logger.debug("Processing entangled-incoming keyid %s with existing block",keyid)
					existing_headers = existing_block.split('\n',6)
					existing_block = existing_headers.pop()
				else:
					#DBGOUT#self.logger.debug("Processing entangled-incoming keyid %s without existing block",keyid)
					existing_headers = None
					existing_block = None
				outblock,notify_recip,error_message = self.valmerge.validate_merge(keyidB,existing_block,new_block,True)
				if outblock != None:
					#DBGOUT#self.logger.debug("Entangled-incoming keyid %s storing output, message %s",keyid,error_message)
					headers_out = ""
					for line in new_headers:
						headers_out += line + "\n"
					outblock = headers_out + outblock
					self.entangledstore.store(keyid,outblock)
				else:
					pass
					#DBGOUT#self.logger.debug("Entangled-incoming keyid %s storing no output, message %s",keyid,error_message)
				self.inputstore.__delitem__(queueid)
				lock.unlock_close()
				
			elif mtype == 'ENTANGLED-OUTGOING':
				found,existing_block = self.entangledstore.retrieve(keyid)
				if found:
					#DBGOUT#self.logger.debug("Processing entangled-outgoing keyid %s with existing block",keyid)
					existing_headers = existing_block.split('\n',6)
					existing_block = existing_headers.pop()
				else:
					#DBGOUT#self.logger.debug("Processing entangled-outgoing keyid %s without existing block",keyid)
					existing_headers = None
					existing_block = None
				outblock,notify_recip,error_message = self.valmerge.validate_merge(keyidB,existing_block,block,True)
				if outblock != None:
					#DBGOUT#self.logger.debug("Entangled-outgoing keyid %s storing output, message %s",keyid,error_message)
					# twisted is not thread safe here, so call it from the event loop thread and wait for it to finish
					self.callbackcond.acquire(True)
					twisted.internet.reactor.callFromThread(self.remoteIterativeStore,keyidB,outblock)
					self.callbackcond.wait() # for store to complete
					self.callbackcond.release()
				else:
					pass
					#DBGOUT#self.logger.debug("Entangled-outgoing keyid %s storing no output, message %s",keyid,error_message)
				self.inputstore.__delitem__(queueid)

		#DBGOUT#self.logger.debug("Server store thread stopped")

	def remoteIterativeStore(self,key,value): # called from the event loop, not the worker thread
		deferred = self.entangled_node.iterativeStore(key,value)
		deferred.addCallback(self.completePostToEntangled)

	def completePostToEntangled(self,result):
		self.callbackcond.acquire(True)
		self.callbackcond.notify()
		self.callbackcond.release()

	def submitKey(self,keyid):
		self.queuecond.acquire(True)
		self.keyqueue.append(keyid)
		self.queuecond.notify()
		self.queuecond.release()

	def submitSelftest(self,prot):
		self.queuecond.acquire(True)
		self.keyqueue.append( ('SELFTEST',prot) )
		self.queuecond.notify()
		self.queuecond.release()

class serverProtocol(twisted.protocols.basic.LineReceiver):
	def __init__(self,factory,filestore,inputstore,sender,sendqueue,replication_peer,storethread,entangled_node,ssl_ctx,timeout):
		self.logger = logging.getLogger(__name__)
		self.factory = factory
		self.filestore = filestore
		self.inputstore = inputstore
		self.sender = sender
		self.sendqueue = sendqueue
		self.replication_peer = replication_peer
		self.storethread = storethread
		self.entangled_node = entangled_node
		self.userhash = None
		self.authkey = None
		self.authenticated = False
		self.ssl_ctx = ssl_ctx
		self.timeout = timeout
		self.timeoutRemaining = timeout
		self.timeoutInterval = 5
		self.connectionClosed = False
		self.invalidCommands = 0
		self.maxInvalidCommands = 3
		self.submitlist = [ ]
		self.slowestConnection = self.factory.slowestConnection
		self.num_ss = 0
		self.num_se = 0
		self.num_sp = 0
		self.num_gs = 0
		self.num_ge = 0
		self.num_dt = 0

	def filterSinceDate(self,data,sinceDate): # only applies to message announce
		origData = data
		outData = ""
		thisRecord = ""
		thisDate = None
		firstOutput = True
		while data != "":
			line,data = string.split(data,'\n',1)
			line = line.rstrip('\r\n')
			lineU = line.upper()
			if lineU[0:6] == 'TYPE: ' and lineU != 'TYPE: MESSAGE-ANNOUNCEMENT':
				return origData # not a message announcements
			m = re_datetime.match(line)
			if m:
				thisDate = m.group(1)
			if lineU == 'NEXTMESSAGE':
				if thisDate == None or thisDate >= sinceDate:
					if firstOutput == True:
						outData += thisRecord
						firstOutput = False
					else:
						outData += 'NextMessage\n' + thisRecord
				thisRecord = ""
				thisDate = None
			else:
				thisRecord += line + '\n'
		if thisRecord != "":
			if thisDate == None or thisDate >= sinceDate:
				if firstOutput == True:
					outData += thisRecord
				else:
					outData += 'NextMessage\n' + thisRecord
		return outData

	def connectionMade(self):
		self.factory.num_connections += 1
		self.factory.total_connections += 1
		if self.factory.num_connections > self.factory.max_connections:
			self.connection_num = -1
			self.sendLineLog("CONFIDANT MAIL SERVER PROTOCOL 1 BUSY")
			self.transport.loseConnection()
			self.state = s_waitcmd
			self.logger.info("Server busy, connection attempt from %s rejected",self.transport.getPeer())
		else:
			self.connection_num = self.factory.total_connections
			self.sendLineLog("CONFIDANT MAIL SERVER PROTOCOL 1 READY")
			self.state = s_waitcmd
			if self.factory.num_connections == 1:
				constr = "connection"
			else:
				constr = "connections"
			self.logger.info("New connection # %i from %s port %i, %i %s open",self.connection_num,self.transport.getPeer().host,self.transport.getPeer().port,self.factory.num_connections,constr)
			twisted.internet.reactor.callLater(self.timeoutInterval,self.timeoutCheck)
	
	def lineReceived(self,line):
		if self.factory.log_all_traffic == True:
			self.logger.info("C%i< %s",self.connection_num,line)
		self.timeoutRemaining = self.timeout
		if self.state == s_waitcmd:
			self.parseCommand(line)
		elif self.state == s_getlinedata:
			self.getLineData(line)

	def connectionLost(self,reason):
		self.connectionClosed = True
		if len(self.submitlist) > 0:
			self.sender.submitKeys(self.submitlist)
		if self.connection_num >= 0:
			if self.authenticated == True:
				login = self.userhash
			else:
				login = 'none'
			self.logger.info("Connection # %i closed, ss=%i, se=%i, sp=%i, gs=%i, ge=%i, dt=%i, login=%s, reason=%s",self.connection_num,self.num_ss,self.num_se,self.num_sp,self.num_gs,self.num_ge,self.num_dt,login,str(reason))
		self.factory.num_connections -= 1

	def parseCommand(self,line):
		self.expbytes = 0
		self.bytes = ""
		self.lines = [ ]
		self.hash = ""
		self.embargo = None
		#self.logger.info("C%i cmd: %s",self.connection_num,line)
		invalidCommands = self.invalidCommands + 1
		self.invalidCommands = 0
		lineU = line.upper()

		match = re_store_server.match(line)
		if match:
			self.state = s_getlinedata
			self.command = c_store_server
			self.hash = match.group(1).upper()
			self.num_ss += 1
			return

		match = re_replicate.match(line)
		if match:
			self.state = s_getlinedata
			self.command = c_replicate
			self.hash = match.group(1).upper()
			self.repl_user = match.group(2)
			self.num_ss += 1
			return

		match = re_store_proxy.match(line)
		if match:
			self.state = s_getlinedata
			self.command = c_store_proxy
			self.hash = match.group(1).upper()
			self.num_sp += 1
			return

		match = re_store_proxy_after.match(line)
		if match:
			self.state = s_getlinedata
			self.command = c_store_proxy_after
			self.hash = match.group(1).upper()
			self.embargo = match.group(2)
			self.num_sp += 1
			return

		match = re_get_server_since.match(line)
		if match:
			self.hash = match.group(1).upper()
			self.since_date = match.group(2)
			self.getServer()
			self.state = s_waitcmd
			self.num_gs += 1
			return

		match = re_get_server.match(line)
		if match:
			self.hash = match.group(1).upper()
			self.since_date = None
			self.getServer()
			self.state = s_waitcmd
			self.num_gs += 1
			return

		match = re_store_entangled.match(line)
		if match:
			self.state = s_getlinedata
			self.command = c_store_entangled
			self.hash = match.group(1).upper()
			self.num_se += 1
			return

		match = re_get_entangled_since.match(line)
		if match:
			self.hash = match.group(1).upper()
			self.since_date = match.group(2)
			self.state = s_waitentangled
			self.command = c_get_entangled
			self.getEntangled()
			self.num_ge += 1
			return

		match = re_get_entangled.match(line)
		if match:
			self.hash = match.group(1).upper()
			self.since_date = None
			self.state = s_waitentangled
			self.command = c_get_entangled
			self.getEntangled()
			self.num_ge += 1
			return

		match = re_login.match(line)
		if match:
			self.userhash = match.group(1)
			self.authkey = match.group(2)
			self.login()
			return

		match = re_addlogin.match(line)
		if match:
			if match.group(3) != None:
				userhash = 'undefined'
				authkey = match.group(3)
			else:
				userhash = match.group(1)
				authkey = match.group(2)
			self.addlogin(userhash,authkey)
			return

		match = re_rmlogin.match(line)
		if match:
			authkey = match.group(1)
			self.rmlogin(authkey)
			return

		match = re_genlogin.match(line)
		if match:
			num_logins = match.group(1)
			self.genlogin(num_logins)
			return

		match = re_replogin.match(line)
		if match:
			userhash = match.group(1)
			authkey = match.group(2)
			self.replogin(userhash,authkey)
			return

		match = re_dns_txt.match(line)
		if match:
			lookup = match.group(1)
			self.dns_txt(lookup)
			self.num_dt += 1
			return

		if lineU[0:5] == "PING ":
			self.sendLineLog("PONG " + line[5:])
			self.state = s_waitcmd
			return
		if lineU == "PING":
			self.sendLineLog("PONG")
			self.state = s_waitcmd
			return

		if lineU == "STARTTLS":
			self.sendLineLog("PROCEED")
			self.startTLS()
			self.sendLineLog("ENCRYPTED")
			self.state = s_waitcmd
			return

		if lineU == "QUIT":
			self.sendLineLog("GOODBYE")
			self.transport.loseConnection()
			self.state = s_waitcmd
			return

		if lineU == "SELFTEST":
			self.storethread.submitSelftest(self)
			return

		if lineU == "SHUTDOWN":
			if self.authenticated == True and self.userhash.lower() == 'administrator':
				self.sendLineLog("GOODBYE")
				self.transport.loseConnection()
				self.state = s_waitcmd
				if self.factory.shutdown_in_progress == False:
					self.factory.shutdown_in_progress = True
					self.storethread.submitKey("SHUTDOWN")
					twisted.internet.reactor.callLater(5,twisted.internet.reactor.stop)
			else:
				self.sendLineLog("FAILED")
			return

		self.invalidCommands = invalidCommands
		self.sendLineLog("INVALID COMMAND")
		if self.invalidCommands >= self.maxInvalidCommands:
			self.transport.loseConnection()
			self.state = s_waitcmd
		return

	def getLineData(self,line):
		lineU = line.upper()
		if lineU[0:9] == 'PADDING: ':
			return
		if lineU == "ENDBLOCK":
			self.completeCommand()
			return
		self.lines.append(line)
		match = re_data.match(line)
		if match:
			self.state = s_getbindata
			self.expbytes = int(match.group(1))
			self.bytes = ""
			self.setRawMode()
			#DBGOUT#self.logger.debug("raw mode enabled %i",self.expbytes)

	def rawDataReceived(self,data):
		self.timeoutRemaining = self.timeout
		self.bytes += data
		#DBGOUT#self.logger.debug("raw received %i %i",len(data),len(self.bytes))
		if len(self.bytes) >= self.expbytes:
			self.setLineMode(self.bytes[self.expbytes:])
			self.bytes = self.bytes[0:self.expbytes]
			self.completeCommand()

	def completeCommand(self):
		accept_msg = True
		for l in self.lines:
			if re_forbidden_headers.match(l):
				self.logger.warn("Got forbidden line: %s",l)
				accept_msg = False
		if accept_msg == False:
			self.sendLineLog("FAILED")
		else:
			#DBGOUT#self.logger.debug("command completed")
			if self.command == c_store_server and len(self.lines) > 0:
				self.storeServer(True,None) # propagate to peer, do not force user
			elif self.command == c_replicate and len(self.lines) > 0:
				if self.authenticated == True and self.userhash == 'replication':
					self.storeServer(False,self.repl_user) # do not propagate, do force user
				else:
					self.sendLineLog("FAILED")
			elif self.command == c_store_proxy and len(self.lines) > 0:
				if ((self.factory.proxy_requires_login == False) or (self.authenticated == True)):
					self.storeProxy(None)
				else:
					self.sendLineLog("FAILED")
			elif self.command == c_store_proxy_after and len(self.lines) > 0:
				if ((self.factory.proxy_requires_login == False) or (self.authenticated == True)):
					self.storeProxy(self.embargo)
				else:
					self.sendLineLog("FAILED")
			elif self.command == c_store_entangled and len(self.lines) > 0:
				self.storeEntangled()
		self.state = s_waitcmd

	def storeServer(self,replicate,repl_user = None): # repl user is the username provided on the replicate command line
		outstr = ""
		for line in self.lines:
			outstr += line + "\n"
		if repl_user != None:
			userstr = "LoginUser: " + repl_user
		elif self.authenticated == True:
			userstr = "LoginUser: " + self.userhash
		else:
			userstr = "LoginUser: none"
		if replicate == False: # this is a replicate incoming
			outstr_l = "StoreType: repl-in\n" + "StoreKeyid: " + self.hash + "\n" + userstr + "\n" + outstr + self.bytes
		else:
			outstr_l = "StoreType: server\n" + "StoreKeyid: " + self.hash + "\n" + userstr + "\n" + outstr + self.bytes
		hasher = hashlib.new('sha1')
		hasher.update(outstr_l)
		temphash = hasher.digest().encode('hex')	
		if not self.inputstore.exists(temphash):
			self.inputstore.store(temphash,outstr_l)
			self.storethread.submitKey(temphash)
		
		if replicate == True and self.replication_peer != None:
			outstr_r = "StoreType: replicate\n" + "StoreKeyid: " + self.hash + "\n" + userstr + "\n" + outstr + self.bytes
			hasher = hashlib.new('sha1')
			hasher.update(outstr_r)
			temphash = hasher.digest().encode('hex')	
			if not self.sendqueue.exists(temphash):
				self.sendqueue.store(temphash,outstr_r)
				self.submitlist.append(temphash)
				#self.sender.submitKey(temphash)
		self.sendLineLog("DONE")

	def storeRepLogin(self,repl_user,repl_auth):
		outstr_r = "StoreType: replicate\n" + "Replogin-User: " + repl_user + "\nReplogin-Auth: " + repl_auth + "\n"
		hasher = hashlib.new('sha1')
		hasher.update(outstr_r)
		temphash = hasher.digest().encode('hex')	
		if not self.sendqueue.exists(temphash):
			self.sendqueue.store(temphash,outstr_r)
			self.submitlist.append(temphash)

	def storeProxy(self,embargo):
		outstr = ""
		for line in self.lines:
			outstr += line + "\n"
		if embargo == None:
			embargo = 'None'
		outstr = "StoreType: proxy\n" + "StoreKeyid: " + self.hash + "\nEmbargo: " + embargo + "\n" + outstr + self.bytes
		hasher = hashlib.new('sha1')
		hasher.update(outstr)
		temphash = hasher.digest().encode('hex')	
		if not self.sendqueue.exists(temphash):
			self.sendqueue.store(temphash,outstr)
			self.submitlist.append(temphash)
			#self.sender.submitKey(temphash)

		self.sendLineLog("DONE")

	def getServer(self):
		found,data = self.filestore.retrieve(self.hash)
		if found == False:
			self.sendLineLog("NOT FOUND")
			#DBGOUT#self.logger.debug("%s not found",self.hash)
			return
		#DBGOUT#self.logger.debug("%s found",self.hash)
		if self.since_date != None:
			data = self.filterSinceDate(data,self.since_date)
			if data == "":
				self.sendLineLog("NOT FOUND")
				#DBGOUT#self.logger.debug("%s not newer",self.hash)
				return
		hasData = False
		data2 = data
		type = ""

		# return bogus NOT FOUND for unauthorized user on message-announcement, data, acknowledgment types.
		if self.authenticated == False:
			while data2 != "": # check type
				line,data2 = string.split(data2,'\n',1)
				match = re_type.match(line)
				if match:
					type = match.group(1).lower()
					break
			if type == 'message-announcement' or type == 'data' or type == 'acknowledgment' or type == 'acknowledgement':
				self.sendLineLog("NOT FOUND")
				#DBGOUT#self.logger.debug("%s unauthorized",self.hash)
				return

		while data != "":
			line,data = string.split(data,'\n',1)
			line = line.rstrip('\r\n')
			self.sendLineLog(line)
			if line[0:6].upper() == "DATA: ":
				hasData = True
				self.timeoutRemaining = len(data) / self.slowestConnection
				if self.timeoutRemaining < self.timeout:
					self.timeoutRemaining = self.timeout
				self.transport.write(data)
				break
		if hasData == False:
			self.sendLineLog("EndBlock")

	def storeEntangled(self):
		outstr = ""
		for line in self.lines:
			outstr += line + "\n"
		outstr = "StoreType: entangled-outgoing\nStoreKeyid: " + self.hash + "\n" + outstr + self.bytes
		hasher = hashlib.new('sha1')
		hasher.update(outstr)
		temphash = hasher.digest().encode('hex')	
		if not self.inputstore.exists(temphash):
			self.inputstore.store(temphash,outstr)
			self.storethread.submitKey(temphash)
		self.sendLineLog("DONE")

	def getEntangled(self):
		deferred = self.entangled_node.iterativeFindValue(self.hash.decode('hex'))
		deferred.addCallback(self.completeGetEntangled)

	def completeGetEntangled(self,result):
		#DBGOUT#self.logger.debug("Serving from entangled: %s",self.hash)
		hashB = self.hash.decode('hex')
		if type(result) == dict and hashB in result:
			data = result[hashB]
			hasData = False
			if self.since_date != None:
				data = self.filterSinceDate(data,self.since_date)
				if data == "":
					self.sendLineLog("NOT FOUND")
					self.state = s_waitcmd
					return
			while data != "":
				line,data = string.split(data,'\n',1)
				line = line.rstrip('\r\n')
				self.sendLineLog(line)
				match = re_data.match(line)
				if match:
					hasData = True
					break
			if hasData == True:
				self.timeoutRemaining = len(data) / self.slowestConnection
				if self.timeoutRemaining < self.timeout:
					self.timeoutRemaining = self.timeout
				self.transport.write(data)
			else:
				self.sendLineLog("EndBlock")
		else:
			self.sendLineLog("NOT FOUND")
		self.state = s_waitcmd

	def startTLS(self):
		#DBGOUT#self.logger.debug("begin starttls")
		self.transport.startTLS(self.ssl_ctx, self.factory)

	def login(self):
		nowtime = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
		if self.authenticated == True or self.userhash.lower() == 'undefined':
			self.sendLineLog("FAILED") # only one login per session, and no tricks
			return

		if self.authkey in self.factory.login_table:
			old_userhash = self.factory.login_table[self.authkey]
			if old_userhash.lower() == 'undefined':
				uhl = self.userhash.lower()
				if uhl != 'administrator' and uhl != 'replication':
					self.factory.login_table[self.authkey] = self.userhash
					self.authenticated = True
			elif old_userhash == 'disabled':
				self.authenticated = False
			elif old_userhash == self.userhash:
				self.authenticated = True

		if self.authenticated == True:
			self.sendLineLog("DONE")
			if old_userhash.lower() == 'undefined': # first login with this userhash
				self.factory.authfile_handle.write(self.userhash + ' ' + self.authkey + ' ' + nowtime + '\n')
				self.factory.authfile_handle.flush()
		else:
			self.sendLineLog("FAILED")
			#OFF#self.factory.authfile_handle.write('#FAILED ' + self.userhash + ' ' + self.authkey + ' ' + nowtime + '\n')
			#OFF#self.factory.authfile_handle.flush()
		self.state = s_waitcmd
	
	def addlogin(self,userhash,authkey):
		if self.authenticated == True and self.userhash.lower() == 'administrator':
			nowtime = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
			self.factory.login_table[authkey] = userhash
			self.factory.authfile_handle.write(userhash + ' ' + authkey + ' ' + nowtime + '\n')
			self.factory.authfile_handle.flush()
			if self.replication_peer != None:
				self.storeRepLogin(userhash,authkey)
			self.sendLineLog("DONE")
		else:
			self.sendLineLog("FAILED")
		self.state = s_waitcmd

	def rmlogin(self,authkey):
		if self.authenticated == True and self.userhash.lower() == 'administrator':
			nowtime = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
			self.factory.login_table[authkey] = 'disabled'
			self.factory.authfile_handle.write('disabled ' + authkey + ' ' + nowtime + '\n')
			self.factory.authfile_handle.flush()
			if self.replication_peer != None:
				self.storeRepLogin('disabled',authkey)
			self.sendLineLog("DONE")
		else:
			self.sendLineLog("FAILED")
		self.state = s_waitcmd

	def genlogin(self,num_logins):
		if self.authenticated == True and self.userhash.lower() == 'administrator':
			num_logins = int(num_logins)
			nowtime = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
			filehandle = open(self.factory.ssl_key_file,'r')	
			random_base = filehandle.read()
			filehandle.close()
			for k in self.factory.login_table.keys():
				random_base += k
			random_base += nowtime
			for i in range(num_logins):
				hasher = hashlib.new('sha1')
				hasher.update(str(i))
				hasher.update(random_base)
				hasher.update(str(i))
				authkey = hasher.digest().encode('hex').upper()
				self.sendLineLog(authkey)
				self.factory.login_table[authkey] = 'undefined'
				self.factory.authfile_handle.write('undefined ' + authkey + ' ' + nowtime + '\n')
				if self.replication_peer != None:
					self.storeRepLogin('undefined',authkey)
			self.factory.authfile_handle.flush()
			self.sendLineLog('EndBlock')
		else:
			self.sendLineLog("FAILED")
		self.state = s_waitcmd

	def replogin(self,userhash,authkey):
		if self.authenticated == True and self.userhash.lower() == 'replication':
			nowtime = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
			self.factory.login_table[authkey] = userhash
			self.factory.authfile_handle.write(userhash + ' ' + authkey + ' ' + nowtime + '\n')
			self.factory.authfile_handle.flush()
			self.sendLineLog("DONE")
		else:
			self.sendLineLog("FAILED")
		self.state = s_waitcmd

	def dns_txt(self,lookup):
		if self.factory.permit_dns_txt == True:
			self.state = s_waitdns
			self.command = c_dns_txt
			deferred = twisted.names.client.lookupText(lookup)
			deferred.addCallback(self.dns_txt_callback)
			deferred.addErrback(self.dns_txt_failure)
		else:
			self.sendLineLog("FAILED")
			self.state = s_waitcmd	

	def dns_txt_callback(self,result):
		dns_response = None
		lines_found = 0
		for l1 in result:
			for l2 in l1:
				if l2.payload.__class__ == twisted.names.dns.Record_TXT:
					dns_response = l2.payload.data[0]
					lines_found += 1
					self.sendLineLog('TXT: ' + dns_response)
		if lines_found >= 0:
			self.sendLineLog("EndBlock");
		else:
			self.sendLineLog("NOT FOUND")
		self.state = s_waitcmd	
	
	def dns_txt_failure(self,result):
		self.sendLineLog("NOT FOUND")
		self.state = s_waitcmd

	def selftest_callback(self,msg):
		if self.connectionClosed == False:
			nowtime = datetime.datetime.utcnow()
			lastsend = int((nowtime - self.sender.lastRunQueue).total_seconds())
			# Could a really slow external server trigger this? possible false positive
			if lastsend > (8 * self.sender.runQueueInterval):
				self.sendLineLog("FAIL SENDER " + str(lastsend))
			else:
				self.sendLineLog(msg)
			self.sendLineLog("EndBlock")
			self.state = s_waitcmd

	def timeoutCheck(self):
		#DBGOUT#self.logger.debug("timeout check %i",self.timeoutRemaining)
		if self.connectionClosed == True:
			# timeout after closed
			#DBGOUT#print "timeout after closed"
			return
		if self.timeoutRemaining <= 0:
			self.transport.abortConnection()
		else:
			self.timeoutRemaining -= self.timeoutInterval
			twisted.internet.reactor.callLater(self.timeoutInterval,self.timeoutCheck)

	def sendLineLog(self,line):
		self.sendLine(line)	
		if self.factory.log_all_traffic == True:
			self.logger.info("C%i> %s",self.connection_num,line)

class serverProtocolFactory(twisted.internet.protocol.ServerFactory):
	def __init__(self,filestore,inputstore,sender,sendqueue,replication_peer,storethread, \
				 entangled_node,ssl_ctx,authfile,ssl_key_file,max_connections,log_all_traffic, \
				 timeout,slowest_connection,permit_dns_txt,preferred_connection,proxy_requires_login):
		self.logger = logging.getLogger(__name__)
		self.filestore = filestore
		self.inputstore = inputstore
		self.sender = sender
		self.sendqueue = sendqueue
		self.replication_peer = replication_peer
		self.storethread = storethread
		self.entangled_node = entangled_node
		self.login_table = dict()
		self.ssl_key_file = ssl_key_file
		self.ssl_ctx = ssl_ctx
		self.timeout = timeout
		self.num_connections = 0
		self.max_connections = max_connections
		self.total_connections = 0
		self.log_all_traffic = log_all_traffic
		self.slowestConnection = slowest_connection # bytes per second
		self.permit_dns_txt = permit_dns_txt
		self.preferred_connection = preferred_connection
		self.proxy_requires_login = proxy_requires_login
		self.shutdown_in_progress = False

		try:
			self.logger.debug("Loading auth file %s",authfile)
			filehandle = open(authfile,'r')	
			for line in filehandle:
				line = line.rstrip('\r\n')
				if line != '' and line[0] != '#': # skip errors/comments
					line += ' ' # in case no datetime
					userhash,authkey,datetime = line.split(' ',2)
					self.login_table[authkey] = userhash
			filehandle.close()
		except IOError:
			self.logger.debug("Creating new auth file %s",authfile)
		self.authfile_handle = open(authfile,'a')

	def buildProtocol(self,addr):
		return serverProtocol(self,self.filestore,self.inputstore,self.sender,self.sendqueue,self.replication_peer,self.storethread,self.entangled_node,self.ssl_ctx,self.timeout)

	def closeAuthFile(self):
		self.authfile_handle.close()

	def beforeShutdown(self):
		if self.shutdown_in_progress == False:
			self.shutdown_in_progress = True
			self.logger.info("Stop on keyboard interrupt")
			self.storethread.submitKey("SHUTDOWN")
			twisted.internet.reactor.callLater(5,twisted.internet.reactor.stop)

def startup(homedir,log_level,log_all_traffic):	
	server_port = 8081
	entangled_port = 8081
	replication_peer = None
	tor_proxy = None
	i2p_proxy = None
	socks_proxy = None
	use_exit_node = False
	preferred_connection = 'Direct'
	permit_dns_txt = True
	enable_ipv6 = False
	proxy_requires_login = False
	timeout = 60
	max_connections = 20
	run_queue_interval = 120
	expire_days = 7
	retry_schedule = [ 0,120,300,1800,3600 ]
	entangled_known_nodes = [ ]
	repl_authkey = None
	repl_cert = None
	alt_localstore = None
	max_age_key = None
	max_age_data = None
	max_age_message = None
	max_age_ack = None
	max_age_claim = None
	slowest_connection = 768 # bytes per second
	# note about slowest connection: data is sent with self.transport.write
	# which is a fire and forget operation. Normally the timeout would cause
	# a disconnect sending a large block to a slow recipient. I am setting a
	# long timeout here based on a worst case slow connection, such as a GSM
	# 9600 baud connection. Reduce if you are serving satellite clients or
	# similarly horrible connections

	logging.basicConfig(level=log_level,
	        	format="%(asctime)s %(levelname)-5s %(name)-10s %(threadName)-10s %(message)s")
	logger = logging.getLogger(__name__)
	
	config_file = homedir + os.sep + "config.txt"
	filehandle = open(config_file,'r')	
	config_parse = re.compile(":[\t ]*")
	for line in filehandle:
		line = line.rstrip('\r\n')
		if line == '' or line[0] == '#' or line[0] == ';':
			continue
		param,pval = config_parse.split(line,1)
		#DBGOUT#print "param=",param,"pval=",pval
		if param == 'sport':
			server_port = int(pval)
		elif param == 'eport':
			entangled_port = int(pval)
		elif param == 'replpeer':
			replication_peer = pval
		elif param == 'knode':
			knode = pval
			khost,kport = knode.rsplit(':',1)
			kport = int(kport)
			entangled_known_nodes.append( (khost,kport) )
		elif param == 'timeout':
			timeout = int(pval)
		elif param == 'max_connections':
			max_connections = int(pval)
		elif param == 'repl_authkey':
			repl_authkey = pval
		elif param == 'repl_cert':
			repl_cert = pval
		elif param == 'retry_schedule':
			retry_schedule = list()
			for e in pval.split(','):
				retry_schedule.append(int(e))
		elif param == 'expire_days':
			expire_days = int(pval)
		elif param == 'run_queue_interval':
			run_queue_interval = int(pval)
		elif param == 'tor_proxy':
			tor_proxy = pval
		elif param == 'i2p_proxy':
			i2p_proxy = pval
		elif param == 'socks_proxy':
			socks_proxy = pval
		elif param == 'alt_localstore':
			alt_localstore = pval
		elif param == 'slowest_connection':
			slowest_connection = int(pval)
		elif param == 'max_age_key':
			max_age_key = int(pval)
		elif param == 'max_age_data':
			max_age_data = int(pval)
		elif param == 'max_age_message':
			max_age_message = int(pval)
		elif param == 'max_age_ack':
			max_age_ack = int(pval)
		elif param == 'max_age_claim':
			max_age_claim = int(pval)
		elif param == 'use_exit_node' and pval.lower() == 'true':
			use_exit_node = True
		elif param == 'proxy_requires_login' and pval.lower() == 'true':
			proxy_requires_login = True
		elif param == 'enable_ipv6' and pval.lower() == 'true':
			enable_ipv6 = True
		elif param == 'permit_dns_txt' and pval.lower() == 'false':
			permit_dns_txt = False
		elif param == 'preferred_connection':
			preferred_connection = pval.upper()
			if preferred_connection == 'DIRECT':
				preferred_connection = 'Direct'
		else:
			logger.warn("Unrecognized (config): %s=%s",param,pval)
		
	filehandle.close()
	
	ssl_dir = homedir + os.sep + "ssl"
	ssl_key_file = ssl_dir + os.sep + "server.key"
	ssl_crt_file = ssl_dir + os.sep + "server.crt"
	ssl_dh_file = ssl_dir + os.sep + "dhparams.pem"
	dh_params = twisted.internet.ssl.DiffieHellmanParameters.fromFile(twisted.python.filepath.FilePath(ssl_dh_file))
	cert_options = twisted.internet.ssl.CertificateOptions(dhParameters = dh_params)
	#ssl_context_factory = twisted.internet.ssl.DefaultOpenSSLContextFactory(ssl_key_file,ssl_crt_file,sslmethod = OpenSSL.SSL.TLSv1_METHOD)
	# This should not be this bloody hard! It took hours of Internet searching and
	# experimenting to figure out how to set up ephemeral key SSL properly. No wonder
	# the state of SSL security is where it is.
	pkey_fd = open(ssl_key_file,'r')
	pkey_obj = OpenSSL.crypto.load_privatekey(OpenSSL.crypto.FILETYPE_PEM,pkey_fd.read())
	pkey_fd.close()
	cert_fd = open(ssl_crt_file,'r')
	cert_obj = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM,cert_fd.read())
	cert_fd.close()
	ssl_context_factory = twisted.internet.ssl.CertificateOptions(pkey_obj,cert_obj,method = OpenSSL.SSL.TLSv1_2_METHOD,dhParameters = dh_params)
	authfile = homedir + os.sep + 'auth.txt'
	
	logging.basicConfig(level=logging.DEBUG,
		format="%(asctime)s %(levelname)-5s %(name)-10s %(threadName)-10s %(message)s")
	
	for subdir in ("gpgtemp","localstore","inputqueue","sendqueue","entangled"):
		subpath = homedir + os.sep + subdir
		#DBGOUT#print subdir,subpath
		if os.path.isdir(subpath) == False:
			os.mkdir(subpath)
	
	gpg_homedir = homedir + os.sep + 'gpgtemp'
	logger = logging.getLogger("server")
	if alt_localstore != None:
		if os.path.isdir(alt_localstore) == False:
			os.mkdir(alt_localstore)
		localstore = filestore.filestore(alt_localstore)
	else:
		localstore = filestore.filestore(homedir + os.sep + "localstore")
	inputstore = flatstore.flatstore(homedir + os.sep + "inputqueue")
	sendqueue = flatstore.flatstore(homedir + os.sep + "sendqueue")
	entangledstore = entangled_store.entangled_store(homedir + os.sep + "entangled")
	if log_level == logging.DEBUG:
		verbose_mode = True
	else:
		verbose_mode = False

	gpg = gnupg.GPG(gpgbinary = global_config.gnupg_path,verbose = verbose_mode,options = global_config.gpg_opts,gnupghome = gpg_homedir)
	gpg.encoding = 'utf-8'
	entangled_protocol = udp_protocol.CustomKademliaProtocol(None)
	entangled_node = entangled.node.EntangledNode(udpPort=entangled_port, dataStore=entangledstore, networkProtocol = entangled_protocol)
	entangled_protocol.setNode(entangled_node)
	entangled_node.joinNetwork(entangled_known_nodes)
	entangled_protocol.setBuffer()
	valmerge = validate_merge.validate_merge(gpg,None,max_age_key,max_age_data,max_age_message,max_age_ack,max_age_claim)
	storethread = serverStoreThread(homedir,localstore,inputstore,entangledstore,entangled_node,valmerge)
	sender = server_send.serverSend(localstore,sendqueue,server_port,replication_peer,repl_authkey,repl_cert,tor_proxy,i2p_proxy,socks_proxy,use_exit_node,run_queue_interval,expire_days,retry_schedule,timeout,log_all_traffic,preferred_connection)
	entangledstore.finish_init(inputstore,storethread,valmerge)
	endpoint = twisted.internet.endpoints.TCP4ServerEndpoint(twisted.internet.reactor,server_port)
	if enable_ipv6:
		endpoint6 = twisted.internet.endpoints.TCP6ServerEndpoint(twisted.internet.reactor,server_port)
	#SSL#endpoint = twisted.internet.endpoints.SSL4ServerEndpoint(twisted.internet.reactor,server_port,ssl_context_factory)
	factory = serverProtocolFactory(localstore,inputstore,sender,sendqueue,replication_peer,storethread,entangled_node,ssl_context_factory,authfile,ssl_key_file,max_connections,log_all_traffic,timeout,slowest_connection,permit_dns_txt,preferred_connection,proxy_requires_login)
	endpoint.listen(factory)
	if enable_ipv6:
		endpoint6.listen(factory)
	#print "STORE THREAD DISABLED"
	twisted.internet.reactor.callInThread(storethread.threadRun,0)
	twisted.internet.reactor.callLater(8,sender.initialLoadStart)
	twisted.internet.reactor.addSystemEventTrigger('before', 'shutdown', factory.beforeShutdown)	
	logger.info("Server startup")
	twisted.internet.reactor.run()
	logger.info("Server shutdown")
	factory.closeAuthFile()
	
cmdline = sys.argv[1:]
if len(cmdline) == 0:
	if sys.platform == 'win32':
		print "Usage: python server.py -homedir \\path\\to\\server [-quiet] [-debug] [-logtraffic] [-daemon] [-logfile \\path\\to\\log] [-pidfile \\path\\to\\pid]"
		print "confserv.exe accepts the same command line arguments: confserv.exe -homedir ..."
		print "confserv.exe -storutil [storutil-options] to run storutil from the exe"
	else:
		print "Usage: python server.py -homedir /path/to/server [-quiet] [-debug] [-logtraffic] [-daemon] [-logfile /path/to/log] [-pidfile /path/to/pid]"
	sys.exit(1)
# storutil pass-through for the Windows binary so server.exe can run storutil
if len(cmdline) > 0 and cmdline[0] == '-storutil':
	storutil.storutil_main(cmdline[1:])
	sys.exit(1)
		
# main()
homedir = None
log_level = logging.INFO
log_all_traffic = False
daemonize = False
logfile = None
pidfile = None

n = 0
while n < len(cmdline):
	cmd = cmdline[n]
	#DBGOUT#print n,cmd

	if cmd == '-homedir':
		n += 1
		homedir = cmdline[n]
		n += 1
	elif cmd == '-quiet':
		log_level = logging.WARN
		n += 1
	elif cmd == '-debug':
		log_level = logging.DEBUG
		n += 1
	elif cmd == '-logtraffic':
		log_all_traffic = True
		n += 1
	elif cmd == '-daemon':
		daemonize = True
		n += 1
	elif cmd == '-logfile':
		n += 1
		logfile = cmdline[n]
		n += 1
	elif cmd == '-pidfile':
		n += 1
		pidfile = cmdline[n]
		n += 1
	else:
		#logger.warn("Unrecognized (cmdline): %s",cmd)
		print "Unrecognized (cmdline): "+cmd
		n += 1

if homedir == None:
	print "No homedir specified - exiting"
	sys.exit(1)

if global_config.gnupg_path == None:
	print "GNU Privacy Guard (" + global_config.gnupg_exename + ") was not found, and the server will not\nwork without it. Please install GnuPG and try again."
	sys.exit(1)

if daemonize == True and sys.platform != 'win32':
	if logfile == None:
		logfile = '/dev/null'
	daemon = daemon.Daemon(pidfile,stdout = logfile,stderr = logfile)
	daemon.daemonize()

startup(homedir,log_level,log_all_traffic)
	
# EOF
