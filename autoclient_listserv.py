import sys
import os
import multiprocessing
import logging
import thread
import cgi
import re
import gnupg
import global_config
import filelock
import folders
import traceback
import codecs
import hashlib
import flatstore
import filestore
import client
import client_agent
import Queue
import datetime
import pickle
import time
import zipfile
import twisted.internet.reactor
wx_missing = False
try:
	import wx
	import wx.lib.newevent
except ImportError:
	wx_missing = True

# Mailing list automatic client
# Hard coded settings in seconds
check_for_acks_interval = 3600
poll_interval = 120
key_post_interval = 86400
key_refresh_interval = 86400
recips_per_message_entangled = 8
recips_per_message_server = 8
max_entangled_original = 8388608
passphrase = "test"
message_header_top = [
	"This message is from the test mailing list.",
]
message_header_bot = [
	"Original message follows.",
]

re_name_email = re.compile("^(.*) <([^>]+)>$")
re_resolution = re.compile("^(....)WindowSize: ([0-9]+)x([0-9]+)$",re.IGNORECASE)
re_remove_addr_keyid = re.compile("^(.*) <[^>]*> [0-9A-F]{40}$",re.IGNORECASE)
re_remove_keyid = re.compile("^(.*) [0-9A-F]{40}$",re.IGNORECASE)
re_keyid = re.compile("^.*\s\s*([0-9A-F]{40})\s*$|^\s*([0-9A-F]{40})\s*$",re.IGNORECASE)
re_ack = re.compile("Ack-([0123456789abcdef]{40}): ([0123456789abcdef]{40})$",re.IGNORECASE)

class autoclient_listserv:

	def LoadKeyList(self):
		self.keyList = self.gpg.list_keys()
		for key in self.keyList:
			keyid = key['fingerprint']
			key['ent'] = False
			found,data = self.local_store.retrieveHeaders(keyid)
			if found == False:
				key['noannounce'] = True # don't display keys we don't have announce for
			else:
				for line in data:
					lineL = line.lower()
					if lineL == 'transport: entangled':
						key['ent'] = True
			m = re_name_email.match(key['uids'][0])
			if m:
				key['adr'] = m.group(2)
				nsp = m.group(1).split(' ',1)
				if len(nsp) == 1:
					key['fn'] = nsp[0]
					key['ln'] = nsp[0]
				else:
					key['fn'] = nsp[0]
					key['ln'] = nsp[1]
			else:
				key['adr'] = key['uids'][0]
				key['fn'] = key['uids'][0]
				key['ln'] = key['uids'][0]

	def main(self,argv):
		cmdline = argv[1:]
		if len(cmdline) == 0:
			print "Usage: python autoclient_listserv.py -homedir /path"
			sys.exit(1)
		
		self.homedir = None
		calledFromChooser = False
		logDebug = False
		logAllTraffic = False

		n = 0
		while n < len(cmdline):
			cmd = cmdline[n]
			#print n,cmd
			if cmd == '-homedir':
				n += 1
				self.homedir = cmdline[n]
				n += 1
			elif cmd == '-chooser':
				calledFromChooser = True
				n += 1
			elif cmd == '-debug':
				logDebug = True
				n += 1
			elif cmd == '-logtraffic':
				logAllTraffic = True
				n += 1

		if sys.platform == 'win32' and sys.executable.lower().find("python.exe") < 0:
			isPythonw = True
			logFile = self.homedir + os.sep + "guierror.log"
		else:
			isPythonw = False

		if logDebug == True:
			if isPythonw == True:
				logging.basicConfig(level=logging.DEBUG,filename = logFile,
        			format="%(asctime)s %(levelname)-5s %(name)-10s %(threadName)-10s %(message)s")
			else:
				logging.basicConfig(level=logging.DEBUG,
        			format="%(asctime)s %(levelname)-5s %(name)-10s %(threadName)-10s %(message)s")
		else:
			if isPythonw == True:
				logging.basicConfig(level=logging.INFO,filename = logFile,
        			format="%(asctime)s %(levelname)-5s %(name)-10s %(threadName)-10s %(message)s")
			else:
				logging.basicConfig(level=logging.INFO,
        			format="%(asctime)s %(levelname)-5s %(name)-10s %(threadName)-10s %(message)s")
			
#		hasher = hashlib.new('sha1')
#		hasher.update('CONFIDANTMAIL')
#		hasher.update(self.homedir.lower())
#		self.singleInstanceName = '.' + hasher.digest().encode('hex')
#		if wx_missing == False:
#			self.singleInstanceChecker = wx.SingleInstanceChecker(self.singleInstanceName)
#			if self.singleInstanceChecker.IsAnotherRunning():
#				if calledFromChooser == True:
#					return('INUSE')
#				else:
#					print "Account already open"
#					sys.exit(2)
		# The approach above is not reliable on Linux, using filelock.py instead
		lock_file_path = self.homedir + os.sep + 'LOCKFILE'
		self.singleInstanceChecker = filelock.filelock(lock_file_path,True)
		if self.singleInstanceChecker.lock_nowait() == False:
			if calledFromChooser == True:
				return('INUSE')
			else:
				print "Account already open"
				sys.exit(2)

		for subdir in ( 'complete', 'content', 'incomplete', 'localstore',
				'outbox', 'prepmsgs', 'tempkeys', 'txlogs' ):
			cspath = self.homedir + os.sep + subdir
			if not os.path.exists(cspath):
				os.mkdir(cspath)

		config_file_path = self.homedir + os.sep + 'config.txt'
		config_file_handle = codecs.open(config_file_path,'r','utf-8')
		config_data = config_file_handle.read()
		config_file_handle.close()

		self.torProxy = None
		self.i2pProxy = None
		self.socksProxy = None
		self.proxyIP = False
		self.proxyTOR = False
		self.proxyI2P = False
		self.useExitNode = False
		self.newMessageCheck = 0
		self.newMessageNotification = 'None'
		self.fieldOrder = 'From Subject Date To'
		self.spellcheckLanguage = 'en_US'
		self.closeOnReply = False
		for line in config_data.split('\n'):
			line = line.encode('utf-8')
			line = line.rstrip('\r\n')
			lineL = line.lower()
			m = re_resolution.match(line)
			if m:
				mt = m.group(1).lower()
				x = int(m.group(2))
				y = int(m.group(3))
				if mt == 'list':
					self.list_window_size = [ x,y ]
				elif mt == 'edit':
					self.edit_window_size = [ x,y ]
				elif mt == 'view':
					self.view_window_size = [ x,y ]
				elif mt == 'addr':
					self.addr_window_size = [ x,y ]
			elif lineL[0:24] == 'newmessagenotification: ':
				self.newMessageNotification = line[24:]
			elif lineL[0:7] == 'keyid: ' :
				self.client_keyid_hex = line[7:]
				self.client_keyid = self.client_keyid_hex.decode("hex")
			elif lineL[0:10] == 'torproxy: ':
				self.torProxy = line[10:]
			elif lineL[0:10] == 'i2pproxy: ':
				self.i2pProxy = line[10:]
			elif lineL[0:12] == 'socksproxy: ':
				self.socksProxy = line[12:]
			elif lineL[0:12] == 'fieldorder: ':
				self.fieldOrder = line[12:]
			elif lineL == 'proxyip: true':
				self.proxyIP = True
			elif lineL == 'proxytor: true':
				self.proxyTOR = True
			elif lineL == 'useexitnode: true':
				self.useExitNode = True
			elif lineL[0:17] == 'newmessagecheck: ':
				self.newMessageCheck = int(line[17:])
			elif lineL == 'closeonreply: true':
				self.closeOnReply = True
			elif lineL[0:20] == 'spellchecklanguage: ':
				self.spellcheckLanguage = line[20:]

		gpg_homedir = self.homedir + os.sep + 'gpg'
		self.gpg = gnupg.GPG(gpgbinary = global_config.gnupg_path,verbose = False,options = global_config.gpg_opts,gnupghome = gpg_homedir)
		self.gpg.encoding = 'utf-8'
		self.gpg_tempdir = self.homedir + os.sep + 'tempkeys'
		self.tempkeys = flatstore.flatstore(self.gpg_tempdir)
		self.temp_gpg = gnupg.GPG(gpgbinary = global_config.gnupg_path,verbose = False,options = global_config.gpg_opts,gnupghome = self.gpg_tempdir)
		self.temp_gpg.encoding = 'utf-8'

		self.passphrase = None
	
		self.from_address = None
		self.from_address_name = None
		private_keys = self.gpg.list_keys(True)
		mykey = self.client_keyid_hex.lower()
		for key in private_keys:
			if key['fingerprint'].lower() == mykey:
				self.from_address = key['uids'][0] + ' ' + mykey
				self.from_address_name = key['uids'][0]
				break
	 	if self.from_address == None:
			raise KeyError('My private key not found')
		m = re_remove_keyid.match(self.from_address)
		self.from_address_nokey = m.group(1)
	
		self.prepmsgs = flatstore.flatstore(self.homedir + os.sep + "prepmsgs")
		self.complete_store = flatstore.flatstore(self.homedir + os.sep + "complete")
		self.outbox_store = flatstore.flatstore(self.homedir + os.sep + "outbox")
		self.local_store = filestore.filestore(self.homedir + os.sep + "localstore")
		self.folder_store = folders.folders(self.homedir + os.sep + "folder_index",self.homedir + os.sep + "txlogs",self.local_store,self.outbox_store)
		self.mailing_list_file = self.homedir + os.sep + "recipients.txt"
		self.LoadKeyList()
		#self.client_agent_message,self.EVT_CLIENT_AGENT_MESSAGE = wx.lib.newevent.NewEvent()
		self.to_agent_queue = multiprocessing.Queue()
		self.from_agent_queue = multiprocessing.Queue()
		#self.message_list = message_list_window.RunApp(self)

		self.client_agent_process = multiprocessing.Process(target=client_agent.process_run, args = [ self.homedir,self.to_agent_queue,self.from_agent_queue,logDebug,logAllTraffic ] )
		self.client_agent_process.start()
		#thread.start_new_thread(self.agent_receive_thread,())
		#self.message_list.MainLoop()
		
		self.message_loop()
		self.to_agent_queue.put( [ "TERMINATE" ] )
		self.folder_store.commit()
		self.folder_store.close()

	def PostSystemMessage(self,message):
		pickled_message = pickle.dumps(message,pickle.HIGHEST_PROTOCOL)
		message_hash = message['ID']
		message['RE'] = [ ( 'T',self.client_keyid_hex,self.from_address_name ) ]
		message['TY'] = 'S'
		self.folder_store.save_message(message_hash,message)
		self.folder_store.put_message_in_folder(folders.id_system_messages,message_hash)
		self.folder_store.commit()
		#if self.current_folder_path == folders.id_system_messages:
			#self.OpenMailFolder(self.current_folder_path) # refresh
		#statusline = 'System Message: ' + message['SU']
		#self.ShowTemporaryStatus(statusline)

	def CheckSentMessage(self,messageId):
		folder_list = self.folder_store.get_folders_containing_message(messageId)
		if folders.id_send_pending not in folder_list:
			return
		messageIdH = messageId.encode('hex')
		#DBGOUT#print "check if "+messageIdH+" has been sent"
		headername = self.local_store.getPath(messageIdH) + '.HDR'
		try:
			fh = open(headername,'r')
			headers = fh.read()
			fh.close()
		except IOError:
			#DBGOUT#print "unable to read file "+headername
			return	
		blocksExist = False
		for line in headers.split('\n'):
			line = line.rstrip('\r\n')
			lineU = line.upper()
			if lineU[0:11] == 'DATABLOCK: ':
				blockId = lineU[11:]
				blocksExist = blocksExist | self.outbox_store.exists(blockId)
			elif lineU[0:15] == 'ANNOUNCEBLOCK: ':
				blockId = lineU[15:]
				blocksExist = blocksExist | self.outbox_store.exists(blockId)
		if blocksExist == False:
			if folders.id_sent_messages not in folder_list:
				self.folder_store.put_message_in_folder(folders.id_sent_messages,messageId)
				#DBGOUT#print "putting message "+messageIdH+" in sent folder"
			self.folder_store.delete_message_from_folder(folders.id_send_pending,messageId)
			self.folder_store.commit()
			#if self.current_folder_path == folders.id_send_pending or self.current_folder_path == folders.id_sent_messages:
				#self.OpenMailFolder(self.current_folder_path)
			#DBGOUT#print "message has been sent",folder_list
		#DBGOUT#else:
			#DBGOUT#print "message has not been sent"
	
	def GetAcksForMessage(self,messageId):
		messageIdH = messageId.encode('hex')
		headername = self.local_store.getPath(messageIdH) + '.HDR'
		#print "check if",type(messageId),len(messageId),messageIdH,"has been acked, file=",headername
		ackHashes = set()
		tomyselfHash = None
		try:
			fh = open(headername,'r')
			headers = fh.read()
			fh.close()
		except IOError:
			return ackHashes,tomyselfHash
		blocksExist = False
		for line in headers.split('\n'):
			line = line.rstrip('\r\n')
			m = re_ack.match(line)
			if m:
				ackHash = m.group(2).decode('hex')
				ackHashes.add(ackHash)
				if m.group(1).decode('hex') == self.client_keyid:
					tomyselfHash = ackHash
		return ackHashes,tomyselfHash
		
	# Do all the file I/O piecemeal so as to not slow down the GUI
	def CheckSendAck(self):
		if self.sentToCheck != None and len(self.sentToCheck) > 0:
			messageId = self.sentToCheck.pop(0)
			self.CheckSentMessage(messageId)
			if len(self.sentToCheck) == 0:
				self.sentToCheck = None
			#self.check_send_ack_timer.Start(global_config.check_send_ack_interval,wx.TIMER_ONE_SHOT)
		elif self.acksToCheck != None and len(self.acksToCheck) > 0:
			if self.ackHashes == None:
				self.ackHashes = set()
				self.ackHashesByMessageId = dict()
				self.acksWeHave = set()
			messageId = self.acksToCheck.pop(0)
			ackHashes,tomyselfHash = self.GetAcksForMessage(messageId)
			self.ackHashes.update(ackHashes)
			self.ackHashesByMessageId[messageId] = ackHashes
			for ackHash in ackHashes:
				if self.local_store.exists(ackHash.encode('hex')) == True:
					self.acksWeHave.add(ackHash)
				elif ackHash == tomyselfHash:
					self.acksWeHave.add(ackHash) # special case for the listserv, always mark self received since it's fake
			#self.check_send_ack_timer.Start(global_config.check_send_ack_interval,wx.TIMER_ONE_SHOT)
		elif self.acksToCheck != None and len(self.acksToCheck) == 0:
			self.acksToCheck = None
			if self.ackHashes != None and len(self.ackHashes) > 0:
				self.to_agent_queue.put( [ 'ACK_SEARCH', list(self.ackHashes) ] )
			else:
				self.checkSendAckActive = False
		else:
			self.checkSendAckActive = False
			
	# Finalize in one step when the client agent returns the list
	def ProcessAcksFound(self,acksFound):
		#DBGOUT#print "acks found",acksFound
		#DBGOUT#print "acks we have",self.acksWeHave
		self.acksWeHave.update(acksFound)
		#DBGOUT#print "new acks we have",self.acksWeHave
		changesMade = False
		for messageId in self.ackHashesByMessageId.keys():
			#DBGOUT#print "message",messageId,self.ackHashesByMessageId[messageId]
			if self.ackHashesByMessageId[messageId].issubset(self.acksWeHave):
				#DBGOUT#print "got all acks for this one!"

				folders_containing = self.folder_store.get_folders_containing_message(messageId)
				if len(folders_containing) == 1:
					self.folder_store.put_message_in_folder(folders.id_sent_messages,messageId) # don't lose message
				self.folder_store.delete_message_from_folder(folders.id_ack_pending,messageId)
				changesMade = True
		if changesMade == True:
			self.folder_store.commit()
			#if self.current_folder_path == folders.id_ack_pending:
				#self.OpenMailFolder(self.current_folder_path)
		self.checkSendAckActive = False

	def CheckSendPending(self,hasErrors):
		if self.checkSendAckActive != True:
			#DBGOUT#print "Check send pending"
			self.checkSendAckActive = True
			self.sentToCheck = self.folder_store.get_messages_in_folder(folders.id_send_pending)
			self.acksToCheck = None
			self.ackHashes = None
			#self.check_send_ack_timer.Start(global_config.check_send_ack_interval,wx.TIMER_ONE_SHOT)
			#if hasErrors == False:
				#self.ShowTemporaryStatus("Message send completed")

	def StartCheckAckIfDue(self):
		if self.checkSendAckActive != True:
			nowtime = time.time()
			if nowtime - self.lastCheckSendAck >= self.check_for_acks_interval:
				self.lastCheckSendAck = nowtime
				#DBGOUT#print "Check send pending and ack pending"
				self.checkSendAckActive = True
				self.sentToCheck = self.folder_store.get_messages_in_folder(folders.id_send_pending)
				self.acksToCheck = self.folder_store.get_messages_in_folder(folders.id_ack_pending)
				#DBGOUT#print "acksToCheck=",self.acksToCheck
				self.ackHashes = None
				#self.check_send_ack_timer.Start(global_config.check_send_ack_interval,wx.TIMER_ONE_SHOT)

	def load_mailing_list(self):
		while True:
			try:
				filehandle = open(self.mailing_list_file,'r')
				break
			except IOError:
				print "Unable to open " + self.mailing_list_file + " - sleeping and retrying\n"
				time.sleep(5)
		wehave = False
		mailing_list = [ ]
		
		for fline in filehandle:
			fline = fline.rstrip('\r\n')
			m = re_keyid.match(fline)
			keyid = None
			if m:
				keyid = m.group(1)
				if keyid == None:
					keyid = m.group(2)
			if keyid == None:
				continue
			keyid = keyid.lower()	
			wehave,block = self.local_store.retrieveHeaders(keyid)
			postdate = None
			expdate = None
			transport = None
			userid = None
			if wehave == True:
				for line in block:
					lineL = line.lower()
					if lineL[0:6] == "date: ":
						postdate = line[6:]
					elif lineL[0:9] == "expires: ":
						expdate = line[9:]
					elif lineL[0:11] == "transport: ":
						transport = line[11:]
					elif lineL[0:8] == "userid: ":
						userid = line[8:]
			entry = keyid,wehave,postdate,expdate,transport,userid
			mailing_list.append(entry)
		filehandle.close()
		return mailing_list

	def find_expired_keys(self,mailing_list):
		current_datetime = datetime.datetime.utcnow()
		exp_interval = datetime.timedelta(0,global_config.renew_age_key)
		#print 'cd',current_datetime
		expired_keys = [ ]
		for recipient in mailing_list:
			keyid,wehave,postdate,expdate,transport,userid = recipient
			expdate_dt = None
			postdate_dt = None
			expired = False
			if expdate != None:
				expdate_dt = datetime.datetime.strptime(expdate,"%Y-%m-%dT%H:%M:%SZ")
				if expdate_dt < current_datetime:
					expired = True	
			if postdate != None:
				postdate_dt = datetime.datetime.strptime(postdate,"%Y-%m-%dT%H:%M:%SZ")
				postexp_dt = postdate_dt + exp_interval
				if postexp_dt < current_datetime:
					expired = True
			if expired == True:
				expired_keys.append(recipient)
		return expired_keys

	def fetch_missing_and_expired_keys(self):
		mailing_list = self.load_mailing_list()
		missing_keyids = [ ]
		for recipient in mailing_list:
			keyid,wehave,postdate,expdate,transport,userid = recipient
			if wehave == False:
				missing_keyids.append(keyid)
		if len(missing_keyids) > 0:
			print "fetch missing",missing_keyids
			self.to_agent_queue.put( [ 'BG_KEY_SEARCH',True,True,None,missing_keyids ] )
		expired_keys = self.find_expired_keys(mailing_list)
		for recipient in expired_keys:
			print "fetch expired",keyid
			keyid,wehave,postdate,expdate,transport,userid = recipient
			self.to_agent_queue.put( [ 'BG_KEY_SEARCH',True,True,transport, [ keyid ] ] )

	def check_poll(self):
		nowtime = time.time()
		if nowtime - self.last_key_post > self.key_post_interval:
			self.last_key_post = nowtime
			self.to_agent_queue.put( [ 'POST_KEY', True,True ] )
		if nowtime - self.last_key_refresh > self.key_refresh_interval:
			self.last_key_refresh = nowtime
			self.fetch_missing_and_expired_keys()
		if (self.check_send_enabled == True) and \
		   (nowtime - self.last_poll_time > self.poll_interval):
			self.last_poll_time = nowtime
			if self.numIncrementalChecks >= global_config.max_incremental_checks:
				self.numIncrementalChecks = 0
				self.lastCheckSendDate = None
			else:
				self.numIncrementalChecks += 1
			self.to_agent_queue.put( [ 'CHECK_SEND',self.lastCheckSendDate ] )
			self.check_send_enabled = False

	def add_to_inbox(self,new_message):
		if self.folder_store.message_exists(new_message) == False:
			found,headers = self.folder_store.extract_incoming_message_headers(new_message)
			if found:
				self.folder_store.save_message(new_message,headers)
				self.folder_store.put_message_in_folder(folders.id_new_messages,new_message)
				self.folder_store.put_message_in_folder(folders.id_inbox,new_message)
				self.folder_store.commit()

	def add_lines_to_html(self,text_in,add_lines): # customize appearance of header here
		text_in = text_in.decode('utf-8')
		header = ''
		for line in add_lines:
			header += \
			'<p align="left"><font face="Segoe UI" size="2" color="#000000" ><font  face="Times New Roman" size="2" style="background-color: #FFFFFF" >' + \
			cgi.escape(line) + '</font></font></p>\n\n'
		pasted = False
		text_out = ''
		for line in text_in.split('\n'):
			if pasted == False and line.find('<p align') >= 0:
				text_out += header
				pasted = True
			text_out += line + '\n'
		text_out = text_out.encode('utf-8')
		return text_out

	def add_lines_to_xml(self,text_in,add_lines): # customize appearance of header here
		text_in = text_in.decode('utf-8')
		header = ''
		for line in add_lines:
			header += '    <paragraph>\n' + \
			'      <text textcolor="#000000" bgcolor="#FFFFFF" fontpointsize="10" fontstyle="90" fontweight="90" fontunderlined="0" fontface="Times New Roman">' + \
			cgi.escape(line) + '</text>\n' + \
			'    </paragraph>\n'

		pasted = False
		text_out = ''
		for line in text_in.split('\n'):
			if pasted == False and (line.find('<paragraph>') >= 0 
								 or line.find('<paragraph ') >= 0):
				text_out += header
				pasted = True
			text_out += line + '\n'
		text_out = text_out.encode('utf-8')
		return text_out

	def add_lines_to_txt(self,text_in,add_lines):
		text_in = text_in.decode('utf-8')
		header = ''
		for line in add_lines:
			header += line + "\n"	
		text_out = header + text_in
		#NOT FOR TEXT#text_out = text_out.encode('utf-8')
		return text_out

	def sort_compare_transport(self,a,b):
		if a[4] < b[4]:
			return -1
		elif a[4] == b[4]:
			return 0
		else:
			return 1

	def process_new_message(self,messageId):
		mailing_list = self.load_mailing_list()
		zipFilePath = self.local_store.getPath(messageId) + '.ZIP'
		sigFilePath = self.local_store.getPath(messageId) + '.SIG'
		headerData = None
		messageXML = ""
		messageHTML = ""
		messageText = ""
		attachments = [ ]
		try:
			zipFile = zipfile.ZipFile(zipFilePath,'r')
		except (IOError,KeyError):
			return

		total_attachment_size = 0
		for member in zipFile.infolist():
			if member.filename[0] == '_':
				attachments.append(member.filename[1:] + ' (' + \
					format(member.file_size,',d') + ' bytes)')
				total_attachment_size += member.file_size

		try:
			headerData = zipFile.read('HEADER.TXT').decode('utf-8')
		except (IOError,KeyError):
			pass

		try:
			body_xml = zipFile.read('BODY.XML')
		except (IOError,KeyError):
			pass

		try:
			body_text = zipFile.read('BODY.TXT')
			#body_text = body_text.decode('utf-8')
		except (IOError,KeyError):
			pass

		try:
			body_html = zipFile.read('BODY.HTML')
			#messageHtml = messageHtml.decode('utf-8')
		except (IOError,KeyError):
			pass
		zipFile.close()

		try:
			fh = open(sigFilePath,'r')
			sigData = fh.read()
			fh.close()
		except (IOError,KeyError):
			return

		fromAddr = None
		subject = None
		toAddrs = [ ]
		ccAddrs = [ ]
		sentDate = None
		messageUniqueId = None
		
		for line in headerData.split('\n'):
			line = line.rstrip('\r\n')
			lineU = line.upper()
			if lineU[0:6] == 'FROM: ':
				fromAddr = line[6:]
			elif lineU[0:9] == 'SUBJECT: ':
				subject = line[9:].decode('utf-8')
			elif lineU[0:4] == 'TO: ':
				toAddrs.append(line[4:])
			elif lineU[0:4] == 'CC: ':
				ccAddrs.append(line[4:])
			elif lineU[0:6] == 'DATE: ':
				sentDate = line[6:]
			elif lineU[0:17] == 'MESSAGEUNIQUEID: ':
				m = re_keyid.match(line[17:])
				if m:
					messageUniqueId = m.group(1)
					if messageUniqueId == None:
						messageUniqueId = m.group(2)

		fromKeyid = None
		m = re_keyid.match(fromAddr)
		if m:
			fromKeyid = m.group(1).lower()
			if fromKeyid == None:
				fromKeyid = m.group(2).lower()

		sigGotValid = False
		sigKeyMatch = False
		keyInMailingList = False
		for line in sigData.split('\n'):
			line = line.rstrip('\r\n')
			if line == 'Valid: True':
				sigGotValid = True
			elif line[0:13] == 'Fingerprint: ':
				sigFingerprint = line[13:].lower()
				if sigFingerprint == fromKeyid:
					sigKeyMatch = True
			elif line[0:19] == 'PubkeyFingerprint: ': # subkey signing case
				pkFingerprint = line[19:].lower()
				if pkFingerprint == fromKeyid:
					sigKeyMatch = True

		if sigGotValid == False:
			print "Signature invalid, skipped"
			return

		if sigKeyMatch == False:
			print "Signature does not match from, skipped"
			return

		for line in mailing_list:
			if line[0] == fromKeyid:
				keyInMailingList = True
				break

		if keyInMailingList == False:
			print "From key is not in the mailing list, skipped"
			return

		custom_from = fromAddr
		m = re_remove_addr_keyid.match(custom_from)
		if m:
			custom_from = m.group(1)
		custom_from += ' via ' + self.from_address_nokey

		header_lines = [ ]
		header_lines.extend(message_header_top)
		header_lines.append('Sender: ' + fromAddr)
		for attach in attachments:
			header_lines.append('Attachment in original: ' + attach)
		header_lines.extend(message_header_bot)
		header_lines.append('')
		body_text = self.add_lines_to_txt(body_text,header_lines)
		body_html = self.add_lines_to_html(body_html,header_lines)
		body_xml = self.add_lines_to_xml(body_xml,header_lines)

		original_too_big = False
		if total_attachment_size > max_entangled_original:
			original_too_big = True
			header_lines.pop()
			header_lines.append('Original not attached because you are on Entangled and the original is too large.')
			header_lines.append('')
			body_text_e = self.add_lines_to_txt(body_text,header_lines)
			body_html_e = self.add_lines_to_html(body_html,header_lines)
			body_xml_e = self.add_lines_to_xml(body_xml,header_lines)

		mailing_list.sort(self.sort_compare_transport)
		mailing_list_groups = [ ]
		mailing_list_entangled = [ ]
		mailing_list_current = [ ]
		for line in mailing_list:
			if line[4] == 'entangled':
				mailing_list_entangled.append(line)
				if len(mailing_list_entangled) >= recips_per_message_entangled:
					mailing_list_groups.append(mailing_list_entangled)
					mailing_list_entangled = [ ]
			else:
				mailing_list_current.append(line)
				if len(mailing_list_current) >= recips_per_message_server:
					mailing_list_groups.append(mailing_list_current)
					mailing_list_current = [ ]
		if len(mailing_list_current) > 0:
			mailing_list_groups.append(mailing_list_current)
		if len(mailing_list_entangled) > 0:
			mailing_list_groups.append(mailing_list_entangled)

		for mailing_list_group in mailing_list_groups:
			recipients = [ ]
			recipients.append('T:' + self.client_keyid_hex.lower())
			recipients_full = [ ]
			recipients_full.append('T:' + self.from_address)
			is_entangled = False
			for recipient in mailing_list_group:
				keyid,wehave,postdate,expdate,transport,userid = recipient
				if transport == 'entangled':
					is_entangled = True
				if wehave == True:
					recipients.append('B:' + keyid)
					recipients_full.append('B:' + userid + ' ' + keyid.lower())
			attachments = [ ]
			reply_thread_id = None
			forward_original_id = messageId
			nowtime = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
			if original_too_big == True and is_entangled == True:
				message_data = recipients,recipients_full,attachments,reply_thread_id,None,subject,body_text_e,body_html_e,body_xml_e,nowtime
			else:
				message_data = recipients,recipients_full,attachments,reply_thread_id,forward_original_id,subject,body_text,body_html,body_xml,nowtime
			pickled_message = pickle.dumps(message_data,pickle.HIGHEST_PROTOCOL)
			hasher = hashlib.new('sha1')
			hasher.update(pickled_message)
			save_hash = hasher.digest()
			save_hashH = save_hash.encode('hex')
			headers = self.folder_store.extract_outgoing_message_headers(message_data,self.from_address,save_hash,'S')
			self.prepmsgs.store(save_hashH,pickled_message)
			self.local_store.store(save_hashH,pickled_message)
	
			filehandle = open(self.prepmsgs.getPath(save_hashH) + '.EMBARGO','wb')
			filehandle.write('U:' + self.client_keyid_hex.lower() + "\n") # Do not actually send back to mailing list
			filehandle.write('F:' + custom_from.encode('utf-8') + "\n") # Modify from address
			filehandle.close()
	
			self.folder_store.save_message(save_hash,headers)
			self.folder_store.put_message_in_folder(folders.id_send_pending,save_hash)
			self.folder_store.put_message_in_folder(folders.id_ack_pending,save_hash)
			self.folder_store.commit()
			self.to_agent_queue.put( [ 'ENCODE_SEND',save_hashH,False ] )

	def process_new_messages(self):
		new_messages = self.complete_store.keys()
		for msgid in new_messages:
			msgidH = msgid.encode('hex')
			try:
				print "Processing",msgidH
				self.add_to_inbox(msgid)
				self.process_new_message(msgidH)
				self.folder_store.delete_message_from_folder(folders.id_new_messages,msgid)
				self.folder_store.commit()
			except Exception as exc:
				print traceback.format_exc()
			self.complete_store.__delitem__(msgidH)

	def message_loop(self):
		self.check_for_acks_interval = check_for_acks_interval
		self.poll_interval = poll_interval
		self.key_post_interval = key_post_interval
		self.key_refresh_interval = key_refresh_interval
		self.passphrase = passphrase
		self.numIncrementalChecks = global_config.max_incremental_checks
		self.last_key_post = 0
		self.last_key_refresh = 0
		self.lastCheckSendAck = 0
		self.checkSendAckActive = False
		self.lastCheckSendDate = None
		self.last_poll_time = 0
		self.check_send_enabled = True
		while True:
			try:
				if self.checkSendAckActive == True:
					self.CheckSendAck()
					message = self.from_agent_queue.get(True,1)
				else:
					message = self.from_agent_queue.get(True,30)
			except Queue.Empty:
				print "no message"
				self.check_poll()
				self.StartCheckAckIfDue()
				continue
			except KeyboardInterrupt:
				print "Exiting on keyboard interrupt"
				return
				
			msg_cmd = message[0]
			msg_args = message[1:]
			print msg_cmd,msg_args
			if msg_cmd == 'TERMINATE':
				break
			elif msg_cmd == 'PASSPHRASE_REQUIRED':
				self.to_agent_queue.put( [ 'SET_PASSPHRASE',self.passphrase ] )
			elif msg_cmd == 'NEW_MESSAGES':
				self.process_new_messages()
			elif msg_cmd == 'ACK_SEARCH_RESULTS':
				self.ProcessAcksFound(msg_args[0])
			elif msg_cmd == 'POST_SYSTEM_MESSAGE':
				self.PostSystemMessage(msg_args[0])	
			elif msg_cmd == 'ENABLE_CHECK_SEND':
				self.check_send_enabled = True

			self.check_poll()
			self.StartCheckAckIfDue()

if __name__ == "__main__":
	#DBGOUT#logging.basicConfig(level=logging.DEBUG, 
       	#DBGOUT#format="%(asctime)s %(levelname)-5s %(name)-10s %(threadName)-10s %(message)s")
	acobj = autoclient_listserv()
	acobj.main(sys.argv)
	sys.exit(0)

# EOF
