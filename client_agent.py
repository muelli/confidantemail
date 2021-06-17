import multiprocessing
import twisted.internet.reactor
import twisted.names.client
import datetime
import time
import codecs
import zipfile
import struct
import os
import hashlib
import sys
import re
import pickle
import logging
import global_config
import gnupg
import keyannounce
import validate_merge
import flatstore
import filestore
import syncstore
import postmessage
import fetchmail
import remote_dns_lookup
import rotate_key
import bypass_token

re_keyid = re.compile("^[0123456789abcdef]{40}$",re.IGNORECASE)
re_server_line = re.compile("^server=\S+:\d+(,\S+:\d+)*$",re.IGNORECASE)
re_email_get_domain = re.compile("\S+@(\S+\.\S+)")
re_from = re.compile("^FROM: (.+) ([0123456789abcdef]{40})$",re.IGNORECASE)
re_forwarded = re.compile("^ForwardedMessageId: ([0123456789abcdef]{40})$",re.IGNORECASE)
re_key_transport = re.compile("KeyTransport-([0123456789abcdef]{40}): (server=.*)$|KeyTransport-([0123456789abcdef]{40}): (entangled)$",re.IGNORECASE)
re_version_check = re.compile("^(\d+) (.*)$")
re_ack = re.compile("^ack=([0123456789abcdef]{40})$",re.IGNORECASE)
re_bypasstoken = re.compile("^bt=([0123456789abcdef]{40}),(\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ),(.*)$",re.IGNORECASE)
random_pool_size = 1024

class client_agent:
	def __init__(self,homedir,to_agent_queue,from_agent_queue,log_debug,log_all_traffic):
		self.homedir = homedir
		self.to_agent_queue = to_agent_queue
		self.from_agent_queue = from_agent_queue
		self.send_timeout = 15
		self.receive_timeout = 15
		self.key_search_running = False
		self.get_messages_running = False
		self.post_messages_running = False
		self.get_acks_running = False
		self.update_status_due = False
		self.agent_queue = [ ]
		self.status_line_stack = [ None,None ]
		self.serverConnection = 'Direct'
		self.torProxy = None
		self.i2pProxy = None
		self.socksProxy = None
		self.proxyIP = False
		self.proxyTOR = False
		self.proxyI2P = False
		self.useExitNode = False
		self.proxyDNS = False
		self.agentStopped = False
		self.askedForPassphrase = False
		self.passphraseRefused = False
		self.newVersionCheck = False
		self.useBypassTokens = True
		self.oldTransport = None
		self.pubTransport = None
		self.altDNSServer = None
		self.endPollOldDate = None	
		self.authKey = None
		self.oldAuthKey = None
		self.pubAuthKey = None
		self.folderSync = 0
		self.search_mailboxes = None
		self.accept_sender_proof_of_work = None
		self.log_debug = log_debug
		self.log_all_traffic = log_all_traffic
		self.scrub_force_full_check = False
		self.shutdown_flag = False

	def set_status_line(self,level,message): # Lowest level has priority
		if level >= 0:
			self.status_line_stack[level] = message
		for line in self.status_line_stack:
			if line != None:
				self.from_agent_queue.put( [ 'SET_STATUS_LINE',None,line ] )
				return
		if len(self.agent_queue) == 0:
			self.from_agent_queue.put( [ 'SET_STATUS_LINE',None,'Agent Idle' ] )

	def status_callback(self,message):
		self.set_status_line(0,message)
	
	def rotkey_output(self,text):
		self.logger.debug("Rotate key: %s",text)

	def parse_config_and_setup(self):
		twisted.python.log.addObserver(self.save_error_log)

		config_file_path = self.homedir + os.sep + 'config.txt'
		config_file_handle = codecs.open(config_file_path,'r','utf-8')
		config_data = config_file_handle.read()
		config_file_handle.close()

		if ( sys.platform == 'win32' or sys.platform == 'darwin' ) and sys.executable.lower().find("python") < 0:
			isPythonw = True
			logFile = self.homedir + os.sep + "agterror.log"
			twLogFile = self.homedir + os.sep + "neterror.log"
		else:
			isPythonw = False

		if self.log_debug == True:
			if isPythonw == True:
				twisted.python.log.startLogging(open(twLogFile,'w'))
				logging.basicConfig(level=logging.DEBUG,filename = logFile,filemode = 'w',
        			format="%(asctime)s %(levelname)-5s %(name)-10s %(threadName)-10s %(message)s")
			else:
				logging.basicConfig(level=logging.DEBUG,
        			format="%(asctime)s %(levelname)-5s %(name)-10s %(threadName)-10s %(message)s")
		else:
			if isPythonw == True:
				twisted.python.log.startLogging(open(twLogFile,'w'))
				logging.basicConfig(level=logging.INFO,filename = logFile,filemode = 'w',
        			format="%(asctime)s %(levelname)-5s %(name)-10s %(threadName)-10s %(message)s")
			else:
				logging.basicConfig(level=logging.INFO,
        			format="%(asctime)s %(levelname)-5s %(name)-10s %(threadName)-10s %(message)s")
		self.logger = logging.getLogger(__name__)
		if self.log_all_traffic == True:
			self.log_traffic_callback = self.traffic_log_writer
		else:
			self.log_traffic_callback = None
		rand_hasher = hashlib.new('sha256')
			
		for line in config_data.split('\n'):
			line = line.encode('utf-8')
			rand_hasher.update(line)
			line = line.rstrip('\r\n')
			lineL = line.lower()
			#DBGOUT#print lineL
			if lineL[0:7] == 'keyid: ' :
				self.client_keyid_hex = line[7:]
				self.client_keyid = self.client_keyid_hex.decode("hex")
			elif lineL[0:19] == 'senderproofofwork: ':
				self.sender_proof_of_work = line[19:]
			elif lineL[0:23] == 'prevsenderproofofwork: ':
				self.accept_sender_proof_of_work = line[23:]
			elif lineL[0:11] == 'mailboxes: ':
				self.mailboxes = line[11:]
			elif lineL[0:15] == 'prevmailboxes: ':
				self.search_mailboxes = line[15:]
			elif lineL[0:11] == 'transport: ':
				self.transport = line[11:]
			elif lineL[0:14] == 'oldtransport: ':
				self.oldTransport = line[14:]
			elif lineL[0:14] == 'pubtransport: ':
				self.pubTransport = line[14:]
			elif lineL[0:17] == 'entangledserver: ':
				self.entangled_server = line[17:]
			elif lineL[0:18] == 'serverconnection: ':
				self.serverConnection = line[18:]
			elif lineL[0:14] == 'altdnsserver: ':
				self.altDNSServer = line[14:]
			elif lineL[0:10] == 'torproxy: ':
				self.torProxy = line[10:]
			elif lineL[0:10] == 'i2pproxy: ':
				self.i2pProxy = line[10:]
			elif lineL[0:12] == 'socksproxy: ':
				self.socksProxy = line[12:]
			elif lineL == 'proxyip: true':
				self.proxyIP = True
			elif lineL == 'proxytor: true':
				self.proxyTOR = True
			elif lineL == 'proxydns: true':
				self.proxyDNS = True
			elif lineL == 'useexitnode: true':
				self.useExitNode = True
			elif lineL == 'newversioncheck: true':
				self.newVersionCheck = True
			elif lineL == 'usebypasstokens: true':
				self.useBypassTokens = True
			elif lineL == 'usebypasstokens: false':
				self.useBypassTokens = False
			elif lineL[0:16] == 'endpollolddate: ':
				self.endPollOldDate = line[16:]
			elif lineL[0:9] == 'authkey: ':
				self.authKey = line[9:]
				if self.authKey == '':
					self.authKey = None
			elif lineL[0:12] == 'oldauthkey: ':
				self.oldAuthKey = line[12:]
			elif lineL[0:12] == 'pubauthkey: ':
				self.pubAuthKey = line[12:]
			elif lineL[0:12] == 'foldersync: ':
				self.folderSync = int(line[12:])
			elif lineL[0:19] == 'connectiontimeout: ':
				self.send_timeout = int(line[19:])
				self.receive_timeout = self.send_timeout

		if self.accept_sender_proof_of_work == None:
			self.accept_sender_proof_of_work = self.sender_proof_of_work
		if self.search_mailboxes == None:
			self.search_mailboxes = self.mailboxes
		if self.endPollOldDate != None and self.oldTransport != None:
			nowtime = datetime.datetime.now().strftime("%Y-%m-%d")
			if self.endPollOldDate < nowtime:
				self.oldTransport = None

		rand_hasher.update(str(time.time()))
		self.random_pool = rand_hasher.digest()
		self.local_store = filestore.filestore(self.homedir + os.sep + "localstore")
		self.outbox_store = flatstore.flatstore(self.homedir + os.sep + "outbox")
		self.complete_store = flatstore.flatstore(self.homedir + os.sep + "complete")
		self.incomplete_store = flatstore.flatstore(self.homedir + os.sep + "incomplete")
		self.prepmsgs = flatstore.flatstore(self.homedir + os.sep + "prepmsgs")
		if self.folderSync > 0:
			self.outgoing_sync = syncstore.syncstore(self.homedir + os.sep + "syncstore",False)
		else:
			self.outgoing_sync = None

		self.outgoing_content_directory = self.homedir + os.sep + "content"
		gpg_homedir = self.homedir + os.sep + 'gpg'
		self.gpg_tempdir = self.homedir + os.sep + 'tempkeys'
		self.tempkeys = flatstore.flatstore(self.gpg_tempdir)
		self.gpg = gnupg.GPG(gpgbinary = global_config.gnupg_path,verbose = False,options = global_config.gpg_opts,gnupghome = gpg_homedir)
		self.gpg.encoding = 'utf-8'
		self.temp_gpg = gnupg.GPG(gpgbinary = global_config.gnupg_path,verbose = False,options = global_config.gpg_opts,gnupghome = self.gpg_tempdir)
		self.temp_gpg.encoding = 'utf-8'
		self.passphrase = None
		self.post_message = postmessage.postmessage(self.gpg,self.outbox_store,self.entangled_server,self.torProxy,self.i2pProxy,self.socksProxy,self.proxyIP,self.proxyTOR,self.proxyI2P,self.useExitNode,self.serverConnection,self.send_timeout,self.log_traffic_callback,self.client_keyid_hex,self.authKey)

		self.keyannounce = keyannounce.keyannounce(self.gpg,self.torProxy,self.i2pProxy,self.socksProxy,self.proxyIP,self.proxyTOR,self.proxyI2P,self.useExitNode,self.serverConnection,self.log_traffic_callback)
		self.valmerge = validate_merge.validate_merge(self.gpg,self.keyannounce)
		if self.useBypassTokens == True:
			self.bypasstoken = bypass_token.bypass_token(self.homedir + os.sep + "bypass_tokens.txt",self.get_random)
		else:
			self.bypasstoken = None
		self.fetch_mail = fetchmail.fetchmail(self.gpg,self.local_store,self.complete_store,self.incomplete_store,self.entangled_server,self.torProxy,self.i2pProxy,self.socksProxy,self.useExitNode,self.serverConnection,self.receive_timeout,self.log_traffic_callback,self.valmerge,self.bypasstoken)
		self.keyannounce_tempdir = keyannounce.keyannounce(self.temp_gpg,self.torProxy,self.i2pProxy,self.socksProxy,self.proxyIP,self.proxyTOR,self.proxyI2P,self.useExitNode,self.serverConnection,self.log_traffic_callback)
		self.rotkey = rotate_key.rotate_key(global_config.gnupg_path,self.homedir,self.client_keyid_hex,self.rotkey_output)
		if self.newVersionCheck == True:
			task = [ 'NEW_VERSION_CHECK',False ]
			self.agent_queue.append(task)

		pending = self.prepmsgs.keys()
		for msg in pending:
			msgH = msg.encode('hex')
			self.logger.debug("Queued pending message %s",msgH)
			task = 'ENCODE_SEND',msgH,False
			self.agent_queue.append(task)

	def save_error_log(self,log_dict):
		if self.agentStopped == False and 'failure' in log_dict:
			error_message = log_dict['failure'].getTraceback()
			if error_message.find('twisted.internet.error.DNSLookupError: DNS lookup failed') < 0:
				# If DNS lookup is attempted while the Internet connection is down,
				# this causes a bunch of exceptions on root server lookup. Ignore them.
				self.post_system_message('Client Agent','Exception in Client Agent',log_dict['failure'].getTraceback())
				self.set_status_line(0,'Agent Exception')

	def log_error_messages(self,operation,error_messages):
		#DBGOUT#print "Log error messages from",operation,len(error_messages)
		if len(error_messages) > 0:
			error_message = ""
			for line in error_messages:
				error_message += line + "\n"	
			#DBGOUT#print error_message,"*"
			self.post_system_message('Client Agent','Error messages from ' + operation,error_message)
	def traffic_log_writer(self,typ,data):
		self.logger.info('C%s %s',typ,data)

	# Log a system message for new or changed certificates
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
		if self.local_store.exists(server_hash)	== False:
			self.post_system_message('Client Agent','Cert for new server ' + server_str,
			"New server accessed for the first time:\n" + cert_desc)
			write_cert_file = True
		else:
			found,old_cert_desc = self.local_store.retrieve(server_hash)
			if old_cert_desc != cert_desc:
				self.post_system_message('Client Agent','Cert changed for server ' + server_str,
				"New certificate:\n" + cert_desc + \
				"\nOld certificate:\n" + old_cert_desc)
				write_cert_file = True
		if write_cert_file == True:
			self.local_store.store(server_hash,cert_desc)

		return True
#OFF#		self.logger.debug("Server " + nethost + " port " + str(netport) + " cert typeof " + str(type(server_cert)) +
#OFF#			" text " + str(server_cert) +
#OFF# 			" type "+ str(server_cert.get_signature_algorithm()) +
#OFF# 			" subject " + str(server_cert.get_subject()) +
#OFF# 			" sn " + str(server_cert.get_serial_number()) +
#OFF# 			" digest " + str(server_cert.digest('sha1')) +
#OFF# 			" notBefore " + str(server_cert.get_notBefore()) +
#OFF# 			" notAfter " + str(server_cert.get_notAfter())
#OFF#			)
#OFF#		return True

	def encode_send(self,task_id,is_folder_sync):
		# get the send request
		found,message_data = self.prepmsgs.retrievePickle(task_id)
		if found == False:
			return
		embargo_time = None
		embargo_user = None
		custom_from = None
		try:
			filehandle = open(self.prepmsgs.getPath(task_id) + '.EMBARGO','rb')
			for line in filehandle:
				line = line.rstrip('\r\n')
				if line[0:2] == 'T:': # time
					embargo_time = line[2:]
				elif line[0:2] == 'U:': # user (for mailing list)
					embargo_user = line[2:]
				elif line[0:2] == 'F:': # custom from (for mailing list)
					custom_from = line[2:].decode('utf-8')
			filehandle.close()
		except IOError:
			pass
		recipients,recipients_full,attachments,reply_thread_id,forward_original_id,subject,body_text,body_html,body_xml,save_date = message_data

		# clear the content directory
		for filename in os.listdir(self.outgoing_content_directory):
			filepath = self.outgoing_content_directory + os.sep + filename
			if os.path.isfile(filepath):
				os.unlink(filepath)

		# write out the body
		self.set_status_line(0,'Prepare')
		if body_text != None:
			filepath = self.outgoing_content_directory + os.sep + 'BODY.TXT'
			filehandle = codecs.open(filepath,'wb','utf-8')
			filehandle.write(body_text)
			filehandle.close()
		if body_html != None:
			filepath = self.outgoing_content_directory + os.sep + 'BODY.HTML'
			filehandle = open(filepath,'wb')
			filehandle.write(body_html)
			filehandle.close()
		if body_xml != None:
			filepath = self.outgoing_content_directory + os.sep + 'BODY.XML'
			filehandle = open(filepath,'wb')
			filehandle.write(body_xml)
			filehandle.close()
		self.post_messages_running = True

		twisted.internet.reactor.callInThread(self.encode_send_part2,task_id, \
			recipients,attachments,reply_thread_id,forward_original_id, \
			subject,embargo_time,embargo_user,custom_from,is_folder_sync)

	def encode_send_part2(self,task_id,recipients,attachments,reply_thread_id, \
			forward_original_id,subject,embargo_time,embargo_user,custom_from, \
			is_folder_sync):
		# call encode_message in thread so we don't block key lookup
		time.sleep(0.5)
		header_path,announce_hashes,data_hashes,bypass_tokens = self.post_message.encode_message( \
			self.local_store,self.outgoing_content_directory,self.client_keyid, \
			self.transport,recipients,attachments,reply_thread_id,forward_original_id, \
			subject,embargo_time,embargo_user,custom_from,self.passphrase, \
			self.status_callback,self.bypasstoken,is_folder_sync,self.get_random)
		if self.shutdown_flag == True:
			self.post_messages_running = False
			return		
		save_header_path = self.local_store.getPath(task_id) + '.HDR'
		in_fh = open(header_path,'r')
		out_fh = open(save_header_path,'w')
		out_fh.write(in_fh.read())
		in_fh.close()
		for line in announce_hashes:
			out_fh.write('AnnounceBlock: ' + line + '\n')
		for line in data_hashes:
			out_fh.write('DataBlock: ' + line + '\n')
		out_fh.close()
		if bypass_tokens != None and self.outgoing_sync != None and len(bypass_tokens) > 0:
			for bypass_token in bypass_tokens:
				self.from_agent_queue.put( [ 'SYNC_BYPASS_TOKEN',bypass_token ] )
		twisted.internet.reactor.callFromThread(self.encode_send_part3,task_id,recipients, \
			attachments,subject,data_hashes,is_folder_sync)

	def encode_send_part3(self,task_id,recipients,attachments,subject,data_hashes,is_folder_sync):
		# call send
		self.set_status_line(0,'Send')
		self.post_message.start_post_message(self.post_messages_callback,self.validate_server_certificate,self.status_callback)

		# delete the job file
		self.prepmsgs.__delitem__(task_id)
		embargo_file = self.prepmsgs.getPath(task_id) + '.EMBARGO'
		if os.path.exists(embargo_file) == True:
			os.unlink(embargo_file)

		if is_folder_sync == True:
			# Add .DEL so this client does not re-download
			hasher = hashlib.new('sha1')
			for hash in data_hashes:
				hasher.update(hash.decode('hex'))
			store_hash = hasher.digest().encode('hex')
			del_path = self.local_store.getPath(store_hash) + '.DEL'
			filehandle = open(del_path,'w')
			filehandle.write(datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ") + '\n')
			filehandle.close()
			# clear the outgoing_sync directory
			self.outgoing_sync.clearSendList()

	def check_send(self,since,full_get_mode = False):
		if global_config.gnupg_is_v2 == True: # gpg 2.1 forgets the passphrase whenever it wants to
			if self.check_secret_key_available(self.passphrase) == False:
				self.from_agent_queue.put( [ 'ENABLE_CHECK_SEND',False ] )
				return # passphrase has timed out
		self.get_messages_running = True
		if self.scrub_force_full_check == True:
			since = None
			self.scrub_force_full_check = False
		self.get_since = since
		self.set_status_line(0,'Check Mail')
		self.get_new_was_successful = True
		if full_get_mode == True:
			self.effective_spof = 'ignore'
		else:
			self.effective_spof = self.accept_sender_proof_of_work
		
		if self.oldTransport != None:
			callback = self.check_send_old_server
		else:
			callback = self.get_new_messages_callback
		if self.transport.lower() == 'entangled':
			self.fetch_mail.get_new_messages(self.client_keyid,callback,self.validate_server_certificate,self.status_callback,
					since_date = since,server = self.entangled_server,entangled_mode = True,
					userhash = self.client_keyid_hex,authkey = self.authKey,
					mailboxes = self.search_mailboxes,sender_proof_of_work = self.effective_spof)
		else:
			self.fetch_mail.get_new_messages(self.client_keyid,callback,self.validate_server_certificate,self.status_callback,
					since_date = since,server = self.transport,entangled_mode = False,
					userhash = self.client_keyid_hex,authkey = self.authKey,
					mailboxes = self.search_mailboxes,sender_proof_of_work = self.effective_spof)

	def post_messages_callback(self,error_messages):
		#DBGOUT#print "Post messages done"	
		self.log_error_messages("Post Messages",error_messages)
		self.set_status_line(0,None)
		if len(error_messages) > 0:
			hasErrors = True
		else:
			hasErrors = False
		self.from_agent_queue.put( [ 'CHECK_SEND_PENDING',hasErrors ] )
		self.post_messages_running = False

	def check_send_old_server(self,error_messages):
		#DBGOUT#print "check send old server called after main check send"
		if len(error_messages) > 0:
			self.get_new_was_successful = False
		self.log_error_messages("Get New Messages from old server",error_messages)
		self.set_status_line(0,'Check Mail Old')
		if self.oldTransport.lower() == 'entangled':
			self.fetch_mail.get_new_messages(self.client_keyid,self.get_new_messages_callback,self.validate_server_certificate,self.status_callback,
											 since_date = self.get_since,server = self.entangled_server,entangled_mode = True,
											 userhash = self.client_keyid_hex,authkey = self.oldAuthKey,
											 mailboxes = self.search_mailboxes,sender_proof_of_work = self.effective_spof)
		else:
			self.fetch_mail.get_new_messages(self.client_keyid,self.get_new_messages_callback,self.validate_server_certificate,self.status_callback,
											 since_date = self.get_since,server = self.oldTransport,entangled_mode = False,
											 userhash = self.client_keyid_hex,authkey = self.oldAuthKey,
											 mailboxes = self.search_mailboxes,sender_proof_of_work = self.effective_spof)

	def get_new_messages_callback(self,error_messages):
		#DBGOUT#print "get new messages callback",len(error_messages)
		if len(error_messages) > 0:
			self.get_new_was_successful = False
		self.log_error_messages("Get New Messages",error_messages)
		#DBGOUT#print "back from log error messages x"
		self.messages_to_reassemble = self.complete_store.keys()
		#DBGOUT#print "back from log error messages",len(self.messages_to_reassemble)
		if len(self.messages_to_reassemble) == 0:
			#DBGOUT#print "No messages to reassemble after get"

			messages_to_post = self.outbox_store.keys()
			if len(messages_to_post) > 0:
				#DBGOUT#print "Send without decrypt"
				self.post_messages_running = True
				self.set_status_line(0,'Send')
				self.post_message.start_post_message(self.get_post_messages_callback,self.validate_server_certificate,self.status_callback)
			else:
				self.set_status_line(0,None)
				self.from_agent_queue.put( [ 'ENABLE_CHECK_SEND',self.get_new_was_successful ] )
				self.get_messages_running = False
		else:
			#DBGOUT#print "Messages to reassemble after get"
			twisted.internet.reactor.callInThread(self.assemble_decrypt_messages,None)

	def get_post_messages_callback(self,error_messages):
		#DBGOUT#print "Post after get messages done"	
		self.log_error_messages("Post Messages",error_messages)
		self.post_messages_running = False
		self.get_messages_running = False
		self.from_agent_queue.put( [ 'ENABLE_CHECK_SEND',self.get_new_was_successful ] )
		if len(error_messages) > 0:
			hasErrors = True
		else:
			hasErrors = False
		self.from_agent_queue.put( [ 'CHECK_SEND_PENDING',hasErrors ] )
		new_messages = self.complete_store.keys()
		self.set_status_line(0,None)
		if len(new_messages) > 0:
			self.agent_queue.append( [ 'CLIENT_NEW_MESSAGES' ] )

	def decrypt_retry(self,retry_announcement_id):
		self.get_messages_running = True
		twisted.internet.reactor.callInThread(self.assemble_decrypt_messages,retry_announcement_id)

	def generate_sig_file(self,sigcheck_result,sig_path,from_key,from_key_exists):
		nowtime = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
		sig_fh = codecs.open(sig_path,'w','utf-8')
		sig_fh.write('CheckDate: ' + nowtime + '\n')
		if (sigcheck_result.valid != None):
			sig_fh.write('Valid: ' + str(sigcheck_result.valid) + '\n')
		if (sigcheck_result.valid != True):
			if from_key != None and from_key_exists == False:
				sig_fh.write('Sender key is unavailable: ' + from_key + '\n')
			elif from_key == None:
				sig_fh.write('Unable to identify sender key\n')
			elif from_key_exists == True:
				sig_fh.write('Sender key is present, but signature is bad\n')
		if (sigcheck_result.status != None) and (sigcheck_result.status != ''):
			sig_fh.write('Status: ' + sigcheck_result.status + '\n')
		if (sigcheck_result.username != None) and (sigcheck_result.username != ''):
			sig_fh.write('Username: ' + sigcheck_result.username + '\n')
		if (sigcheck_result.key_id != None) and (sigcheck_result.key_id != ''):
			sig_fh.write('KeyID: ' + sigcheck_result.key_id + '\n')
		if (sigcheck_result.signature_id != None) and (sigcheck_result.signature_id != ''):
			sig_fh.write('SignatureID: ' + sigcheck_result.signature_id + '\n')
		if (sigcheck_result.fingerprint != None) and (sigcheck_result.fingerprint != ''):
			sig_fh.write('Fingerprint: ' + sigcheck_result.fingerprint + '\n')
		if (sigcheck_result.pubkey_fingerprint != None) and (sigcheck_result.pubkey_fingerprint != ''):
			sig_fh.write('PubkeyFingerprint: ' + sigcheck_result.pubkey_fingerprint + '\n')
		if (sigcheck_result.trust_level != None) and (sigcheck_result.trust_level != ''):
			sig_fh.write('TrustLevel: ' + str(sigcheck_result.trust_level) + '\n')
		if (sigcheck_result.trust_text != None) and (sigcheck_result.trust_text != ''):
			sig_fh.write('TrustText: ' + sigcheck_result.trust_text + '\n')
		if (sigcheck_result.key_status != None) and (sigcheck_result.key_status != ''):
			sig_fh.write('KeyStatus: ' + sigcheck_result.key_status + '\n')
		if (sigcheck_result.sig_timestamp != None) and (sigcheck_result.sig_timestamp != ''):
			sig_fh.write('SigTimestamp: ' + sigcheck_result.sig_timestamp + '\n')
		if (sigcheck_result.expire_timestamp != None) and (sigcheck_result.expire_timestamp != ''):
			sig_fh.write('ExpireTimestamp: ' + sigcheck_result.expire_timestamp + '\n')
		sig_fh.close()

	def send_acknowledgment(self,announcement_id,from_key,from_transport,ack_is_pgp,ack_content):
		if ack_is_pgp:
			#DBGOUT#print "sending gpg acknowledgment to ",from_transport,announcement_id
			decrypt_result = self.gpg.decrypt(ack_content,passphrase = self.passphrase)
			#DBGOUT#print "gpg returned:",decrypt_result.valid,decrypt_result.status,len(decrypt_result.data)
			if decrypt_result.status == 'decryption ok' and len(decrypt_result.data) == 20:
				ack_content = decrypt_result.data
			elif decrypt_result.status == 'decryption ok' and len(decrypt_result.data) > 20:
				ack_content = None
				for ack_part in decrypt_result.data.split("|"):
					m = re_ack.match(ack_part)
					if m:
						ack_content = m.group(1).decode("hex")
						continue
					m = re_bypasstoken.match(ack_part)
					if m:
						token = m.group(1)
						create_time = m.group(2)
						expire_time = m.group(3)
						if self.bypasstoken != None:
							self.bypasstoken.add_incoming_or_replicated_token(from_key,token,create_time,expire_time,'in')
						continue
			else:
				ack_content = None
		if ack_content != None and from_transport != None:
			#DBGOUT#print "sending ack ",ack_content.encode('hex')
			self.post_message.make_acknowledgment(from_transport,ack_content)

	def assemble_decrypt_messages(self,retry_announcement_id):
		keys_to_get = set()
		keys_to_check = set()
		messages_to_decrypt = [ ]
		if retry_announcement_id != None:
			messages_to_decrypt.append(retry_announcement_id)
			self.messages_to_reassemble = [ ]
		else:
			time.sleep(0.5)
		new_messages = False
		n_asm = len(self.messages_to_reassemble)
		i_asm = 1
		for announcement_id in self.messages_to_reassemble:
			asm_msg = 'Assemble %i of %i' % (i_asm,n_asm)
			self.set_status_line(0,asm_msg)
			announcement_id = announcement_id.encode('hex')
			dest_path = self.local_store.getPath(announcement_id) + '.PGP'
			if os.path.isfile(dest_path):
				self.logger.debug('Reassemble deleting existing %s',dest_path)
				os.unlink(dest_path)	
			self.logger.debug('Reassemble %s to %s',announcement_id,dest_path)
			status,errormsg = self.fetch_mail.reassemble_message(announcement_id,dest_path)
			if status == False:
				self.logger.debug('Reassemble %s failed: %s',announcement_id,errormsg)
				self.post_system_message('Client Agent','Reassembly of incoming message failed','Message ID ' + announcement_id + "\nCause: " + errormsg + "\nMessage will be scrubbed for errors now, and retried at the next Check/Send.\nIf this error repeats, use Actions/Dequeue Bad Messages to Delete and Ban the corrupt message.")
				time.sleep(2.0)
				self.set_status_line(0,"Scrub data blocks")
				scrub_status = self.fetch_mail.scrub_data_blocks(announcement_id)	
				old_path = self.complete_store.getPath(announcement_id)
				new_path = self.incomplete_store.getPath(announcement_id)
				if (os.path.isfile(old_path) == True) and (os.path.isfile(new_path) == False):
					os.rename(old_path,new_path) # kick it back into incomplete
				annc_path = self.local_store.getPath(announcement_id)
				if os.path.isfile(annc_path):
					os.unlink(annc_path) # delete from local store to mark as not done
				self.scrub_force_full_check = True # re-fetch it next time
			else:
				messages_to_decrypt.append(announcement_id)
			i_asm += 1
		self.messages_to_reassemble = [ ]

		n_decr = len(messages_to_decrypt)
		i_decr = 1
		for announcement_id in messages_to_decrypt:
			if retry_announcement_id != None:
				decr_msg = 'Decrypt Retry'
			else:
				decr_msg = 'Decrypt %i of %i' % (i_decr,n_decr)
			self.set_status_line(0,decr_msg)
			msgtime = time.time()
			source_path = self.local_store.getPath(announcement_id) + '.PGP'
			temp_path = self.local_store.getPath(announcement_id) + '.TMP'
			dest_path = self.local_store.getPath(announcement_id) + '.ZIP'
			dts_path = self.local_store.getPath(announcement_id) + '.DTS'
			sig_path = self.local_store.getPath(announcement_id) + '.SIG'
			if os.path.isfile(temp_path):
				self.logger.debug('Decrypt deleting existing %s',temp_path)
				os.unlink(temp_path)	
			if os.path.isfile(dest_path):
				self.logger.debug('Decrypt deleting existing %s',dest_path)
				os.unlink(dest_path)	
			self.logger.debug("Decrypt %s to %s",source_path,dest_path)
			source_fh = open(source_path,'rb')
			decrypt_result = self.gpg.decrypt_file(source_fh,always_trust = True,passphrase = self.passphrase,output = temp_path)
			source_fh.close()
			if type(decrypt_result) != gnupg.Crypt or decrypt_result.ok == False:
				if self.check_secret_key_available(self.passphrase) == False:
					error_message = 'Secret key unavailable during decryption of incoming message ' + source_path + '\n' + \
						'Decryption will be retried at next fetch.\n'
					self.post_system_message('Client Agent','Decryption of incoming message failed',error_message)
					os.unlink(source_path)
					continue # failed to decrypt
				else:
					error_message = 'Incoming message ' + source_path + ' failed to decrypt\n'
					if type(decrypt_result) != gnupg.Crypt:
						error_message += 'No error message from GPG\n'
					else:
						error_message += 'Error message from GPG: ' + decrypt_result.status + '\n'
					del_path = self.local_store.getPath(announcement_id) + '.DEL'
					error_message += 'Message was deleted. Remove file ' + del_path + ' if you want to retry.\n'
					self.post_system_message('Client Agent','Decryption of incoming message failed',error_message)
					os.unlink(source_path)
					self.fetch_mail.delete_data_blocks(announcement_id)
					self.complete_store.__delitem__(announcement_id)
					os.unlink(self.local_store.getPath(announcement_id))
					errPath = self.local_store.getPath(announcement_id) + '.ERR'
					if os.path.isfile(errPath):
						os.unlink(errPath)
					filehandle = open(del_path,'w')
					filehandle.write(datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ") + '\n')
					filehandle.write(error_message)
					filehandle.close()
					continue # failed to decrypt

			if retry_announcement_id != None:
				decr_msg = 'Extract Sig'
			else:
				decr_msg = 'Extract Sig %i of %i' % (i_decr,n_decr)
			nowtime = time.time()
			if nowtime - msgtime >= 2.0:
				self.set_status_line(0,decr_msg)
				msgtime = nowtime
			chunkSize = 262144
			infh = open(temp_path,'rb')
			zipfh = open(dest_path,'wb')
			dtsfh = open(dts_path,'wb')
			sig_len_bin = infh.read(2)
			sig_len, = struct.unpack('>h',sig_len_bin)
			buf = infh.read(sig_len)
			dtsfh.write(buf)
			while True:
				buf = infh.read(chunkSize)
				if len(buf) == 0:
					break
				zipfh.write(buf)
				if len(buf) < chunkSize:
					break
			infh.close()
			zipfh.close()
			dtsfh.close()

			if retry_announcement_id != None:
				decr_msg = 'Check Sig'
			else:
				decr_msg = 'Check Sig %i of %i' % (i_decr,n_decr)
			nowtime = time.time()
			if nowtime - msgtime >= 2.0:
				self.set_status_line(0,decr_msg)
				msgtime = nowtime
			chunkSize = 262144
			dtsfh = open(dts_path,'rb')
			sigcheck_result = self.gpg.verify_file(dtsfh,dest_path)
			dtsfh.close()

			new_messages = True
			from_key = None
			from_key_transport = None
			from_key_exists = False
			ack_is_pgp = None
			ack_content = None
			try:
				zip = None
				zip = zipfile.ZipFile(dest_path,'r')
				headers_fh = zip.open('HEADER.TXT','r')
				header_lines = headers_fh.read().decode('utf-8')
				headers_fh.close()
				for line in header_lines.split('\n'):
					line = line.rstrip('\r\n')
					m = re_from.match(line)
					if m:
						from_key = m.group(2).lower()
				for line in header_lines.split('\n'):
					line = line.rstrip('\r\n')
					m = re_key_transport.match(line)
					if m:
						if m.group(1) != None and m.group(1).lower() == from_key:
							from_key_transport = m.group(2)
						elif m.group(3) != None and m.group(3).lower() == from_key:
							from_key_transport = m.group(4)
				if from_key != None:
					from_key_exists = self.local_store.exists(from_key)
				ack1 = 'ACK_' + self.client_keyid_hex.upper()
				ack2 = ack1 + '.PGP'
				ack1 += '.BIN'
				for fn in zip.namelist():
					if fn != ack1 and fn != ack2:
						continue
					if fn == ack2:
						ack_is_pgp = True
					else:
						ack_is_pgp = False
					ack_fh = zip.open(fn,'r')
					ack_content = ack_fh.read()
					ack_fh.close()
					break
				zip.close()
				zip = None
			except Exception as exc:
				#DBGOUT#print "Exception",exc
				from_key = None
				from_key_transport = None
				if zip != None:
					zip.close()
			self.generate_sig_file(sigcheck_result,sig_path,from_key,from_key_exists)
			# If we get an unknown from key, fetch it and retry decrypt
			skipDeleteSource = False
			if sigcheck_result.valid != True and retry_announcement_id == None:
				#DBGOUT#print "Decrypt failed to get valid sig, retrying"
				#DBGOUT#print "Decrypt retry got key",from_key,"and transport",from_key_transport
				if from_key != None:
					if from_key not in keys_to_get:
						if from_key_transport.lower() == 'entangled':
							task = [ 'BG_KEY_SEARCH',True,True,None, [ from_key ] ]
						else:
							task = [ 'BG_KEY_SEARCH',True,True,from_key_transport, [ from_key ] ]
						self.agent_queue.append(task)
						keys_to_get.add(from_key)
					task = [ 'DECRYPT_RETRY',announcement_id ]
					self.agent_queue.append(task)
					skipDeleteSource = True
			elif sigcheck_result.valid == True:
				# If we got a valid decrypt and signature, post the acknowledgment
				if ack_is_pgp != None and ack_content != None:
					self.send_acknowledgment(announcement_id,from_key,from_key_transport,ack_is_pgp,ack_content)
				# Delete the DATA blocks after a fully successful download and decrypt
				self.fetch_mail.delete_data_blocks(announcement_id)
				errPath = self.local_store.getPath(announcement_id) + '.ERR'
				if os.path.isfile(errPath):
					os.unlink(errPath)
			if from_key != None and from_key not in keys_to_get and from_key not in keys_to_check:
					if from_key_transport.lower() == 'entangled':
						task = [ 'EXP_KEY_SEARCH',True,True,None, [ from_key ] ]
					else:
						task = [ 'EXP_KEY_SEARCH',True,True,from_key_transport, [ from_key ] ]
					self.agent_queue.append(task)
					keys_to_check.add(from_key)
			i_decr += 1
			if skipDeleteSource == False:
				os.unlink(source_path)
			os.unlink(temp_path)

		if retry_announcement_id != None:
			self.agent_queue.append( [ 'CLIENT_NEW_KEYS' ] )
		messages_to_post = self.outbox_store.keys()
		if len(messages_to_post) > 0:
			#DBGOUT#print "Send after decrypt"
			self.post_messages_running = True
			self.set_status_line(0,'Send')
			twisted.internet.reactor.callFromThread(self.post_message.start_post_message,self.get_post_messages_callback,self.validate_server_certificate,self.status_callback)
		else:
			#DBGOUT#print "Do not send after decrypt"
			self.set_status_line(0,None)
			self.from_agent_queue.put( [ 'ENABLE_CHECK_SEND',self.get_new_was_successful ] )
			self.get_messages_running = False
			if new_messages == True:
				self.agent_queue.append( [ 'CLIENT_NEW_MESSAGES' ] )

	# Call with message id of the first message (containing the forwarded one)
	def check_prep_forwarded_message(self,containing_message_id,attempt_key_lookup,after_key_lookup):
		self.logger.debug('Extract forwarded message from %s %s',containing_message_id,attempt_key_lookup)
		self.set_status_line(0,'Extract forwarded message')

		orig_path = self.local_store.getPath(containing_message_id) + '.ZIP'
		zip = zipfile.ZipFile(orig_path,'r')
		headers_fh = zip.open('HEADER.TXT','r')
		header_lines = headers_fh.read().decode('utf-8')
		headers_fh.close()
		forwarded_message_id = None
		for line in header_lines.split('\n'):
			line = line.rstrip('\r\n')
			m = re_forwarded.match(line)
			if m:
				forwarded_message_id = m.group(1).upper()
				break
		if forwarded_message_id == None:
			zip.close()
			return # no message ID found, should not happen

		# we generate a different local forwarded message ID to prevent collisions
		hasher = hashlib.new('sha1')
		hasher.update(forwarded_message_id.decode("hex"))
		hasher.update(containing_message_id.decode("hex"))
		hasher.update(self.client_keyid)
		local_fwd_id = hasher.digest()
		local_fwd_id_hex = local_fwd_id.encode("hex")

		fwd_zip_path = self.local_store.getPath(local_fwd_id_hex) + '.ZIP'
		fwd_zip_name = local_fwd_id_hex + '.ZIP'
		fwd_dts_path = self.local_store.getPath(local_fwd_id_hex) + '.DTS'
		fwd_dts_name = local_fwd_id_hex + '.DTS'
		fwd_sig_path = self.local_store.getPath(local_fwd_id_hex) + '.SIG'
		tmp_zip_path = self.local_store.getPath(forwarded_message_id) + '.ZIP'
		tmp_zip_name = forwarded_message_id + '.ZIP'
		tmp_dts_path = self.local_store.getPath(forwarded_message_id) + '.DTS'
		tmp_dts_name = forwarded_message_id + '.DTS'

		if after_key_lookup == False and os.path.exists(fwd_zip_path) == True:
			os.unlink(fwd_zip_path)
		if os.path.exists(fwd_dts_path) == True:
			os.unlink(fwd_dts_path)
		if os.path.exists(fwd_sig_path) == True:
			os.unlink(fwd_sig_path)
		if after_key_lookup == False: # no need to do this over after looking up signature
			zip.extract(tmp_zip_name,self.gpg_tempdir)
			os.rename(self.gpg_tempdir + os.sep + tmp_zip_name,fwd_zip_path)
		zip.extract(tmp_dts_name,self.gpg_tempdir)
		os.rename(self.gpg_tempdir + os.sep + tmp_dts_name,fwd_dts_path)
		zip.close()

		# Get the required key id for the forwarded zip
		zip = zipfile.ZipFile(fwd_zip_path,'r')
		headers_fh = zip.open('HEADER.TXT','r')
		header_lines = headers_fh.read().decode('utf-8')
		headers_fh.close()
		zip.close()
		from_key_transport = None
		for line in header_lines.split('\n'):
			line = line.rstrip('\r\n')
			m = re_from.match(line)
			if m:
				from_key = m.group(2).lower()
		for line in header_lines.split('\n'):
			line = line.rstrip('\r\n')
			m = re_key_transport.match(line)
			if m:
				if m.group(1) != None and m.group(1).lower() == from_key:
					from_key_transport = m.group(2)
				elif m.group(3) != None and m.group(3).lower() == from_key:
					from_key_transport = m.group(4)
		if from_key == None:
			self.set_status_line(0,None)
			return # should not happen, no from key

		from_key_exists = self.local_store.exists(from_key)
		if from_key_exists == False and from_key_transport != None and attempt_key_lookup == True:
			self.logger.debug('Attempting key lookup for forwarded message')
			if from_key_transport.lower() == 'entangled':
				task = [ 'BG_KEY_SEARCH',True,True,None, [ from_key ] ]
			else:
				task = [ 'BG_KEY_SEARCH',True,True,from_key_transport, [ from_key ] ]
			self.agent_queue.append(task)
			task = [ 'PREP_FWD_MSG',containing_message_id,False,True ]
			self.agent_queue.append(task)
			self.set_status_line(0,None)
			return # try to get the key, then do this again
		else:
			self.logger.debug('Not attempting key lookup for forwarded message')
		
		dtsfh = open(fwd_dts_path,'rb')
		sigcheck_result = self.gpg.verify_file(dtsfh,fwd_zip_path)
		dtsfh.close()

		self.generate_sig_file(sigcheck_result,fwd_sig_path,from_key,from_key_exists)
		self.from_agent_queue.put( [ 'NEW_FORWARDED_ORIGINAL',local_fwd_id ] )
		if after_key_lookup == True:
			self.from_agent_queue.put( [ 'AGENT_NEW_KEYS' ] )
		self.from_agent_queue.put( [ 'OPEN_MESSAGE',local_fwd_id ] )
		self.set_status_line(0,None)
		return

	# go through list of keys and throw out the ones we have that are not expired
	# expects list of hex key ids
	def key_search_find_expired_transport(self,key_list_in):
		key_list_out = [ ]
		transport_by_keyid = dict()
		current_datetime = datetime.datetime.utcnow()
		for keyid_hex in key_list_in:	
			keep_key = True
			expired_found = False
			found,announce_message = self.local_store.retrieveHeaders(keyid_hex)
			if found == True:
				for line in announce_message:
					lineL = line.lower()
					if expired_found == False and lineL[0:9] == "expires: ":
						expires_date = line[9:]
						expires_datetime = datetime.datetime.strptime(expires_date,"%Y-%m-%dT%H:%M:%SZ")
						expires_age = current_datetime - expires_datetime
						ageS = expires_age.total_seconds()
						if ageS > 0:
							keep_key = False
						#DBGOUT#print "key_search_find_expired_transport found(2) ",keyid_hex,"age ",ageS," get ",keep_key
						expired_found = True
					elif expired_found == False and lineL[0:6] == "date: ":
						posting_date = line[6:]
						posting_datetime = datetime.datetime.strptime(posting_date,"%Y-%m-%dT%H:%M:%SZ")
						announcement_age = current_datetime - posting_datetime
						ageS = announcement_age.total_seconds()
						if ageS < global_config.renew_age_key:
							keep_key = False
						#DBGOUT#print "key_search_find_expired found(2) ",keyid_hex,"age ",ageS," get ",keep_key
						expired_found = True
					elif lineL[0:18] == "transport: server=":
						transport_by_keyid[keyid_hex] = lineL[11:]
			#DBGOUT#else:
				#DBGOUT#print "key_search_find_expired not found",keyid_hex
			if keep_key:
				key_list_out.append(keyid_hex)	
		return key_list_out,transport_by_keyid
			

	def key_search_start(self,is_addressbook,expired_only,refresh_mode,search_entangled,search_DNS,specific_server,key_list):
		if specific_server != None and specific_server.lower() == 'entangled':
			specific_server = None
		for n,key in enumerate(key_list):
			if type(key) == unicode:
				key_list[n] = key.encode('utf-8')
		if type(specific_server) == unicode:
			specific_server = specific_server.encode('utf-8')
		if expired_only == True: # hex keys only in this mode
			key_list,transport_by_keyid = self.key_search_find_expired_transport(key_list)
			if len(key_list) == 0:
				return
			self.key_search_existing_transport = transport_by_keyid
		elif refresh_mode == True: # hex keys only in this mode
			key_list_ignore,transport_by_keyid = self.key_search_find_expired_transport(key_list)
			self.key_search_existing_transport = transport_by_keyid
		else:
			self.key_search_existing_transport = None
	
		self.set_status_line(1,'Key Lookup')
		self.key_search_running = True
		self.key_search_refresh_mode = refresh_mode
		self.key_search_addressbook = is_addressbook
		self.key_search_key_list = key_list
		self.key_search_entangled = search_entangled
		self.key_search_DNS = search_DNS
		self.key_search_specific = specific_server
		self.key_search_keys_found = [ ]
		self.key_search_current = None
		if self.key_search_addressbook == True:
			for filename in os.listdir(self.gpg_tempdir):
				filepath = self.gpg_tempdir + os.sep + filename
				if os.path.isfile(filepath):
					os.unlink(filepath)

		self.key_search_DNS_list = set()
		if self.key_search_DNS == True:
			for key in self.key_search_key_list:
				m = re_email_get_domain.match(key)
				if m:
					lookup_domain = 'cmsvr.' + m.group(1)
					self.key_search_DNS_list.add(lookup_domain)
		self.key_search_DNS_list = list(self.key_search_DNS_list)
		if self.key_search_DNS == True and self.proxyDNS == False and len(self.key_search_DNS_list) > 0:
			self.key_search_DNS_results = dict()
			message = 'Performing DNS lookups'
			self.from_agent_queue.put( [ 'SET_AB_STATUS_LINE',message ] )
			self.key_search_nextdns()
		elif self.key_search_DNS == True and self.proxyDNS == True and len(self.key_search_DNS_list) > 0:
			if self.altDNSServer != None:
				remoteDNSServer = self.altDNSServer
			else:
				remoteDNSServer = self.entangled_server
			lookup = remote_dns_lookup.remote_dns_lookup(remoteDNSServer,self.torProxy,self.i2pProxy,self.socksProxy,self.useExitNode,self.serverConnection,self.receive_timeout,self.log_traffic_callback,self.validate_server_certificate,userhash = None,authkey = None)
			lookup.lookup(self.key_search_DNS_list,self.key_search_rdns_callback,False)
		else:
			self.key_search_DNS_list = None
			self.key_search_nextphase()

	def key_search_rdns_callback(self,result,error_messages):
		self.log_error_messages("Remote DNS TXT Lookup",error_messages)
	
		self.key_search_DNS_results = dict()
		for domain in result.keys():
			if re_server_line.match(result[domain]):
				self.key_search_DNS_results[domain] = result[domain]
		self.key_search_nextphase()
	
	def key_search_nextdns(self):
		if len(self.key_search_DNS_list) == 0:
			self.key_search_DNS_list = None
			self.key_search_nextphase()
		else:
			deferred = twisted.names.client.lookupText(self.key_search_DNS_list[0])
			deferred.addCallback(self.key_search_dns_txt_callback)
			deferred.addErrback(self.key_search_dns_txt_failure)
		
	def key_search_dns_txt_callback(self,result):
		#DBGOUT#print "DNS TXT callback"
		server_list = None
		done = False
		for l1 in result:
			for l2 in l1:
				if l2.payload.__class__ == twisted.names.dns.Record_TXT:
					#DBGOUT#print "DNS response: " + l2.payload.data[0]
					if re_server_line.match(l2.payload.data[0]):
						server_list = l2.payload.data[0]
						self.key_search_DNS_results[self.key_search_DNS_list[0]] = server_list
						done = True
						break
			if done == True:
				break
		self.key_search_DNS_list.pop(0)
		self.key_search_nextdns()

	def key_search_dns_txt_failure(self,result):
		#DBGOUT#print "DNS search failure"
		self.key_search_DNS_list.pop(0)
		self.key_search_nextdns()

	def key_search_nextphase(self):
		self.key_search_keyid_list = [ ]
		self.key_search_email_addr_list = [ ]
		for key in self.key_search_key_list:
			if re_keyid.match(key):
				self.key_search_keyid_list.append(key)
			else:
				self.key_search_email_addr_list.append(key)
		self.key_search_nextkey()

	def key_search_nextkey(self):
		if self.key_search_existing_transport != None:
			#DBGOUT#print 'Start existing'
			if len(self.key_search_keyid_list) > 0:
				self.key_search_current = self.key_search_keyid_list.pop(0)
				if self.key_search_current not in self.key_search_existing_transport:
					#DBGOUT#print "Lookup existing " + self.key_search_current + " no transport"
					self.key_search_nextkey()
					return
				existing_transport = self.key_search_existing_transport[self.key_search_current]
				#DBGOUT#print "Lookup existing " + self.key_search_current + " on " + existing_transport
				self.keyannounce.get_key_announcements(existing_transport,None,[ self.key_search_current ],False,self.key_search_callback,self.receive_timeout,self.validate_server_certificate)
			else:
				self.key_search_existing_transport = None
				self.key_search_nextphase()
		elif self.key_search_specific != None:
			#DBGOUT#print "Start specific"
			if len(self.key_search_email_addr_list) > 0:
				self.key_search_current = self.key_search_email_addr_list.pop(0)
				if self.key_search_addressbook == True:
					message = 'Searching for ' + self.key_search_current + ' on ' + self.key_search_specific
					self.from_agent_queue.put( [ 'SET_AB_STATUS_LINE',message ] )
				self.keyannounce.get_key_announcements(self.key_search_specific,self.key_search_current,None,False,self.key_search_callback,self.receive_timeout,self.validate_server_certificate)
			elif len(self.key_search_keyid_list) > 0:
				self.key_search_current = self.key_search_keyid_list
				self.key_search_keyid_list = [ ]
				if self.key_search_addressbook == True:
					if len(self.key_search_current) == 1:
						message = "Searching for " + str(len(self.key_search_current)) + " keyid on " + self.key_search_specific
					else:
						message = "Searching for " + str(len(self.key_search_current)) + " keyids on " + self.key_search_specific
					self.from_agent_queue.put( [ 'SET_AB_STATUS_LINE',message ] )
				self.keyannounce.get_key_announcements(self.key_search_specific,None,self.key_search_current,False,self.key_search_callback,self.receive_timeout,self.validate_server_certificate)
			else:
				self.key_search_specific = None
				#DBGOUT#print "Specific phase done"
				self.key_search_nextphase()
		elif self.key_search_DNS == True:
			#DBGOUT#print "Start DNS",len(self.key_search_email_addr_list)
			if len(self.key_search_email_addr_list) > 0:
				self.key_search_current = self.key_search_email_addr_list.pop(0)
				m = re_email_get_domain.match(self.key_search_current)
				if m:
					lookup_domain = 'cmsvr.' + m.group(1)
					if self.key_search_addressbook == True:
						message = 'Searching for ' + self.key_search_current + ' on DNS'
						self.from_agent_queue.put( [ 'SET_AB_STATUS_LINE',message ] )
		
					if lookup_domain in self.key_search_DNS_results:
						server_list = self.key_search_DNS_results[lookup_domain]
						self.keyannounce.get_key_announcements(server_list,self.key_search_current,None,False,self.key_search_callback,self.receive_timeout,self.validate_server_certificate)
					else:
						self.key_search_nextkey()
				else:
					self.key_search_nextkey()
			else:
				self.key_search_DNS = False
				self.key_search_DNS_results = None
				#DBGOUT#print "DNS phase done"
				self.key_search_nextphase()
		elif self.key_search_entangled == True:
			#DBGOUT#print "Start Entangled"
			if len(self.key_search_email_addr_list) > 0:
				self.key_search_current = self.key_search_email_addr_list.pop(0)
				if self.key_search_addressbook == True:
					message = 'Searching for ' + self.key_search_current + ' on Entangled'
					self.from_agent_queue.put( [ 'SET_AB_STATUS_LINE',message ] )
				self.keyannounce.get_key_announcements(self.entangled_server,self.key_search_current,None,True,self.key_search_callback,self.receive_timeout,self.validate_server_certificate)
			elif len(self.key_search_keyid_list) > 0:
				self.key_search_current = self.key_search_keyid_list
				self.key_search_keyid_list = [ ]
				if self.key_search_addressbook == True:
					if len(self.key_search_current) == 1:
						message = "Searching for " + str(len(self.key_search_current)) + " keyid on Entangled"
					else:
						message = "Searching for " + str(len(self.key_search_current)) + " keyids on Entangled"
					self.from_agent_queue.put( [ 'SET_AB_STATUS_LINE',message ] )
				self.keyannounce.get_key_announcements(self.entangled_server,None,self.key_search_current,True,self.key_search_callback,self.receive_timeout,self.validate_server_certificate)
			else:
				self.key_search_entangled = False
				#DBGOUT#print "Entangled phase done"
				self.key_search_nextphase()
		else:
			#DBGOUT#print "Start completion"
			if self.key_search_addressbook == True:
				uniq_keyids = set()
				for keyid,key in self.key_search_keys_found:
					uniq_keyids.add(keyid.lower())
				num_keys_found = len(uniq_keyids)
				if num_keys_found == 0:
					message = "No keys found"
				elif num_keys_found == 1:
					message = "Found " + str(num_keys_found) + " key.  Click Import to add it to your Address Book."
				else:
					message = "Found " + str(num_keys_found) + " keys.  Select keys and click Import."
				self.from_agent_queue.put( [ 'SET_AB_STATUS_LINE',message ] )
				self.from_agent_queue.put( [ 'AB_KEY_SEARCH_DONE' ] )
			elif self.key_search_refresh_mode == True:
				self.from_agent_queue.put( [ 'AB_REF_KEY_SEARCH_DONE' ] )
			self.key_search_running = False
			self.set_status_line(1,None)
			#DBGOUT#print "Search done"

	def key_search_callback(self,key_list,claim_list,error_messages):
		self.log_error_messages("Key Search",error_messages)
		self.key_search_keys_found.extend(key_list)
		for key_tuple in key_list:
			hash,key = key_tuple
			announcement_text = ''
			result = False
			for line in key:
				announcement_text += line + "\n"
			if self.key_search_addressbook == True:
				result,fingerprint,age,isexp,cause,gpgstatus = self.keyannounce_tempdir.verify_key_announcement_message(announcement_text,0,0)
			else:
				found,old_key = self.local_store.retrieve(hash)
				if found == True and old_key == key:
					#DBGOUT#print "key search callback: Unchanged"
					result = False
				else:
					result,fingerprint,age,isexp,cause,gpgstatus = self.keyannounce.verify_key_announcement_message(announcement_text,0,0)
					if found == True and result == True:
						if (fingerprint != None) and (fingerprint.lower() != self.client_keyid_hex.lower()):
							self.rotkey.remove_old_revoked_keys(fingerprint)
						old_lines,old_type,old_date,old_age,old_pow,old_data = self.valmerge.extract_headers_data(old_key)
						if (old_age != None) and (age != None) and (old_age <= age):
							#DBGOUT#print "key search callback: Not newer"
							result = False
						#DBGOUT#else:
							#DBGOUT#print "key search callback: Newer"
					#DBGOUT#else:
						#DBGOUT#print "key search callback: Not found"
			if result == True:
				if self.key_search_addressbook == True:
					self.tempkeys.storeList(fingerprint,key)
				else:
					self.local_store.storeList(fingerprint,key)
				if self.key_search_addressbook == True:
					self.from_agent_queue.put( [ 'AB_KEY_FOUND',fingerprint ] )
		self.key_search_nextkey()

	def ab_key_import(self,keyids):
		self.set_status_line(1,'Key Import')
		if len(keyids) == 1:
			message = "Importing one key into Address Book"
		else:
			message = "Importing " + str(len(keyids)) + " keys into Address Book"
		self.from_agent_queue.put( [ 'SET_AB_STATUS_LINE',message ] )
		n = 0
		for key in keyids:
			found,data = self.tempkeys.retrieve(key)
			old_found,old_data = self.local_store.retrieve(key)
			if found == True:
				# Verify it to load it into the GPG keyring
				result,fingerprint,age,isexp,cause,gpgstatus = self.keyannounce.verify_key_announcement_message(data,0,0)
				if result == True:
					if old_found == True:
						if fingerprint.lower() != self.client_keyid_hex.lower():
							self.rotkey.remove_old_revoked_keys(fingerprint)
						old_lines,old_type,old_date,old_age,old_pow,old_data = self.valmerge.extract_headers_data(old_data)
						if old_age <= age:
							#DBGOUT#print "ab key import: Not newer"
							result = False
						#DBGOUT#else:
							#DBGOUT#print "ab key import: Newer"
				if result == True:
					self.local_store.store(key,data)
				n += 1
		if n == 1:
			message = "Imported one key into Address Book"
		else:
			message = "Imported " + str(n) + " keys into Address Book"
		self.from_agent_queue.put( [ 'SET_AB_STATUS_LINE',message ] )
		self.from_agent_queue.put( [ 'AB_KEY_IMP_DEL_DONE' ] )
		self.set_status_line(1,None)

	def ab_key_delete(self,keyids):
		self.set_status_line(0,"Delete keys")
		for key in keyids:
			if key.lower() == self.client_keyid_hex.lower():
				continue # do not delete own key
			self.gpg.delete_keys(key,False) # do not delete secret key
			filepath = self.local_store.getPath(key)
			if os.path.isfile(filepath):
				os.unlink(filepath)
		self.from_agent_queue.put( [ 'AB_KEY_IMP_DEL_DONE' ] )
		self.set_status_line(0,None)
		

	def ack_search_start(self,ack_list):
		self.get_acks_running = True
		self.set_status_line(0,'Ack lookup')
		self.acks_found = None
		if self.oldTransport != None:
			callback = self.ack_search_old_server
			self.ack_list = [ ]
			self.ack_list.extend(ack_list) # process eats them
		else:
			callback = self.ack_search_callback
		if self.transport.lower() == 'entangled':
			self.fetch_mail.get_message_acknowledgments(self.client_keyid,ack_list,callback,self.validate_server_certificate,
					server = self.entangled_server,entangled_mode = True,
					userhash = self.client_keyid_hex,authkey = self.authKey)
		else:
			self.fetch_mail.get_message_acknowledgments(self.client_keyid,ack_list,callback,self.validate_server_certificate,
					server = self.transport,entangled_mode = False,
					userhash = self.client_keyid_hex,authkey = self.authKey)

	def ack_search_old_server(self,acks_found,error_messages):
		self.log_error_messages("Ack Search Old Server",error_messages)
		self.acks_found = acks_found
		self.set_status_line(0,'Ack lookup old')
		if self.oldTransport.lower() == 'entangled':
			self.fetch_mail.get_message_acknowledgments(self.client_keyid,self.ack_list,self.ack_search_callback,self.validate_server_certificate,
					server = self.entangled_server,entangled_mode = True,
					userhash = self.client_keyid_hex,authkey = self.oldAuthKey)
		else:
			self.fetch_mail.get_message_acknowledgments(self.client_keyid,self.ack_list,self.ack_search_callback,self.validate_server_certificate,
					server = self.oldTransport,entangled_mode = False,
					userhash = self.client_keyid_hex,authkey = self.oldAuthKey)

	def ack_search_callback(self,acks_found,error_messages):
		self.log_error_messages("Ack Search",error_messages)
		if self.acks_found != None:
			acks_found.extend(self.acks_found)
			self.ack_list = None
			self.acks_found = None
		self.from_agent_queue.put( [ 'ACK_SEARCH_RESULTS',acks_found ] )
		self.get_acks_running = False
		self.set_status_line(0,None)

	def mark_update_queue_status(self):
		self.update_status_due = True
		
	def post_key(self,post_to_entangled,post_to_server):
		#DBGOUT#print "Publishing key",post_to_entangled,post_to_server
		self.post_key_to_entangled = post_to_entangled
		self.post_key_to_server = post_to_server
		self.post_messages_running = True
		pow_nbits_key = global_config.pow_nbits_key
		pow_nmatches_key = global_config.pow_nmatches_key

		self.set_status_line(0,'Gen Key Announce')
		key_announcement,address_claim_hash,address_claim = self.keyannounce.create_key_announcement_message( \
				self.client_keyid_hex,self.sender_proof_of_work,pow_nbits_key,pow_nmatches_key, \
				self.mailboxes,self.transport,self.bypasstoken,self.passphrase)
		self.local_store.store(self.client_keyid_hex,key_announcement)
		self.local_store.store(address_claim_hash,address_claim)
		self.key_announcement = key_announcement
		self.address_claim_hash = address_claim_hash
		self.address_claim = address_claim
	
		self.set_status_line(0,'Send Key Announce')
		self.keyannounce.post_key_announcement(self.entangled_server,self.client_keyid_hex,key_announcement, \
			address_claim_hash,address_claim,post_to_server,post_to_entangled, \
			self.post_key_callback,self.send_timeout,self.validate_server_certificate,
			userhash = self.client_keyid_hex,authkey = self.authKey)

	def post_key_callback(self,posted_key_to_server,posted_key_to_entangled, \
			posted_claim_to_server,posted_claim_to_entangled,error_messages):
		if self.oldTransport == None or self.oldTransport.lower() == 'entangled':
			self.post_messages_running = False
		self.from_agent_queue.put( [ 'POST_KEY_RESULTS',posted_key_to_server,posted_key_to_entangled,posted_claim_to_server,posted_claim_to_entangled ] )
		error_message = ""
		if self.post_key_to_server == True and posted_key_to_server == False:
			error_message += "Failed to post key to server\n"
		if self.post_key_to_server == True and posted_claim_to_server == False:
			error_message += "Failed to post claim to server\n"
		if self.post_key_to_entangled == True and posted_key_to_entangled == False:
			error_message += "Failed to post key to entangled\n"
		if self.post_key_to_entangled == True and posted_claim_to_entangled == False:
			error_message += "Failed to post claim to entangled\n"
		for line in error_messages:
			error_message += line + "\n"
		if error_message != '':
			self.post_system_message('Client Agent','Key posting error',error_message)

		if self.oldTransport != None and self.oldTransport.lower() != 'entangled':
			self.set_status_line(0,'Send Key Old')
			self.keyannounce.post_key_announcement(self.oldTransport,self.client_keyid_hex,self.key_announcement, \
				self.address_claim_hash,self.address_claim,True,False, \
				self.post_key_old_server_callback,self.send_timeout,self.validate_server_certificate,
				userhash = self.client_keyid_hex,authkey = self.oldAuthKey)
		elif self.pubTransport != None:
			self.set_status_line(0,'Send Key Pub')
			self.keyannounce.post_key_announcement(self.pubTransport,self.client_keyid_hex,self.key_announcement, \
				self.address_claim_hash,self.address_claim,True,False, \
				self.post_key_pub_server_callback,self.send_timeout,self.validate_server_certificate,
				userhash = self.client_keyid_hex,authkey = self.pubAuthKey)
		else:
			self.set_status_line(0,None)
			self.key_announcement = None
			self.address_claim_hash = None
			self.address_claim = None

	def post_key_old_server_callback(self,posted_key_to_server,posted_key_to_entangled, \
			posted_claim_to_server,posted_claim_to_entangled,error_messages):
		self.post_messages_running = False
		error_message = ""
		if self.post_key_to_server == True and posted_key_to_server == False:
			error_message += "Failed to post key to old server\n"
		if self.post_key_to_server == True and posted_claim_to_server == False:
			error_message += "Failed to post claim to old server\n"
		for line in error_messages:
			error_message += line + "\n"
		if error_message != '':
			self.post_system_message('Client Agent','Key posting error (old server)',error_message)

		if self.pubTransport != None:
			self.set_status_line(0,'Send Key Pub')
			self.keyannounce.post_key_announcement(self.pubTransport,self.client_keyid_hex,self.key_announcement, \
				self.address_claim_hash,self.address_claim,True,False, \
				self.post_key_pub_server_callback,self.send_timeout,self.validate_server_certificate,
				userhash = self.client_keyid_hex,authkey = self.pubAuthKey)
		else:
			self.set_status_line(0,None)
			self.key_announcement = None
			self.address_claim_hash = None
			self.address_claim = None

	def post_key_pub_server_callback(self,posted_key_to_server,posted_key_to_entangled, \
			posted_claim_to_server,posted_claim_to_entangled,error_messages):
		self.post_messages_running = False
		error_message = ""
		if self.post_key_to_server == True and posted_key_to_server == False:
			error_message += "Failed to post key to pub server\n"
		if self.post_key_to_server == True and posted_claim_to_server == False:
			error_message += "Failed to post claim to pub server\n"
		for line in error_messages:
			error_message += line + "\n"
		if error_message != '':
			self.post_system_message('Client Agent','Key posting error (pub server)',error_message)
		self.set_status_line(0,None)
		self.key_announcement = None
		self.address_claim_hash = None
		self.address_claim = None

	def check_secret_key_available(self,passphrase):
		testdata = "passphrase test message"
		result = self.gpg.sign(testdata,keyid = self.client_keyid_hex,passphrase = passphrase)
		if result:
			return True
		else:
			return False

	def set_passphrase(self,passphrase):
		if passphrase == '':
			passphrase = None
		if self.check_secret_key_available(passphrase) == True:
			self.passphrase = passphrase
			self.from_agent_queue.put( [ 'SET_PASSPHRASE_GOOD' ] )
		else:
			if global_config.gnupg_is_v2 == True:
				self.from_agent_queue.put( [ 'PASSPHRASE_REFUSED' ] )
			else:
				self.from_agent_queue.put( [ 'SET_PASSPHRASE_FAIL' ] )

	def new_version_check_start(self,notify_always):
		self.new_version_check_notify_always = notify_always
		self.set_status_line(0,'New Version Check')
		deferred = twisted.names.client.lookupText(global_config.upgrade_check_server)
		deferred.addCallback(self.new_version_check_dns_callback)
		deferred.addErrback(self.new_version_check_dns_failure)
	
	def new_version_check_dns_callback(self,result):
		self.set_status_line(0,None)
		upgrade_check_text = None
		done = False
		for l1 in result:
			for l2 in l1:
				if l2.payload.__class__ == twisted.names.dns.Record_TXT:
					upgrade_check_text = l2.payload.data[0]
					done = True
					break
			if done == True:
				break
		#DBGOUT#print upgrade_check_text
		newest_version = -1
		m = re_version_check.match(upgrade_check_text)
		if m:
			newest_version = int(m.group(1))
			upgrade_check_text = m.group(2)
		if (newest_version < 0) or (newest_version > global_config.upgrade_check_expected_version):
			self.from_agent_queue.put( [ 'NEW_VERSION_CHECK_RESULT',True,upgrade_check_text ] )
		elif self.new_version_check_notify_always == True:
			self.from_agent_queue.put( [ 'NEW_VERSION_CHECK_RESULT',True,"No newer version found" ] )
		else:
			self.from_agent_queue.put( [ 'NEW_VERSION_CHECK_RESULT',True,None ] )

	def new_version_check_dns_failure(self,result):
		self.set_status_line(0,None)
		self.from_agent_queue.put( [ 'NEW_VERSION_CHECK_RESULT',False,None ] )

	def send_folder_changes(self,from_address):
		numRecs,sendFiles = self.outgoing_sync.getSendList()
		if numRecs == 0:
			return # nothing to send
		recipients = [ ]
		recipients.append('T:' + self.client_keyid_hex)
		recipients_full = [ ]
		recipients_full.append('T:' + from_address)
		attachments = [ ]
		attachments.append(self.outgoing_sync.logfileProcPath)
		nowtime = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
		for filehash in sendFiles:
			sent_file = self.outgoing_sync.getPath(filehash.encode('hex'))
			attachments.append(sent_file)
			hdr_file = self.local_store.getPath(filehash.encode('hex')) + '.HDR'
			if os.path.exists(hdr_file):
				attachments.append(hdr_file)
		subject = '_FOLDER_SYNC_MESSAGE_' + self.client_keyid_hex.upper()
		body_text = 'You should not see this. This is an internal folder sync message.\n' + \
		"If you are receiving this in the Inbox, please turn on Sync Multiple Clients in Configuration."
		message_data = recipients,recipients_full,attachments,None,None,subject,body_text,None,None,nowtime
		pickled_message = pickle.dumps(message_data,pickle.HIGHEST_PROTOCOL)
		hasher = hashlib.new('sha1')
		hasher.update(pickled_message)
		save_hashH = hasher.digest().encode('hex')
		self.prepmsgs.store(save_hashH,pickled_message)
		self.to_agent_queue.put( [ 'ENCODE_SEND',save_hashH,True ] )

	def post_system_message(self,fromaddr,subject,text):
		message = dict()
		message['FR'] = ( '',fromaddr )
		message['SU'] = subject
		message['DA'] = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
		message['TX'] = text
		hasher = hashlib.new('sha1')
		hasher.update(fromaddr)
		hasher.update(subject)
		hasher.update(message['DA'])
		hasher.update(text)
		message_hash = hasher.digest()
		message['ID'] = message_hash
		self.from_agent_queue.put( [ 'POST_SYSTEM_MESSAGE',message ] )

	def sync_bypass_token_in(self,bypass_token):
		if self.bypasstoken != None:
			from_key,token,create_time,expire_time = bypass_token.split(',')
			self.bypasstoken.add_incoming_or_replicated_token(from_key,token,create_time,expire_time,'out')

	def get_random(self,nbytes,extrapool = None):
		rand_hasher = hashlib.new('sha256')
		rand_hasher.update(self.random_pool)
		rand_hasher.update(str(time.time()))
		rand_hasher.update(str(nbytes))
		if extrapool != None:
			rand_hasher.update(extrapool)
		self.random_pool = rand_hasher.digest() + self.random_pool[0:random_pool_size]
		return self.random_pool[0:nbytes]

	# Dispatch one get or post at a time.
	# Dispatch one address book key lookup even if a get or post is running.
	# Do not dispatch a get or post while a key lookup is running.
	def check_queue(self):
		# queue it locally so pipe queue does not fill up
		if self.to_agent_queue.empty() == False:
			task = self.to_agent_queue.get(False)
			task_type = task[0]
			if task_type == 'TERMINATE':
				self.post_message.shutdown()
				self.fetch_mail.shutdown()
				self.shutdown_flag = True
				self.logger.debug("Shutdown command posted")
			if task_type == 'TERMINATE' or task_type == 'SET_PASSPHRASE' or task_type == 'AB_KEY_SEARCH' or task_type == 'AB_KEY_IMPORT':
				self.agent_queue.insert(0,task) # These go to the front of the line
			else:
				self.agent_queue.append(task)
		
		twisted.internet.reactor.callLater(1,self.check_queue)
		if self.update_status_due == True:
			self.update_status_due = False
			self.set_status_line(-1,None) # prevent down indication
			twisted.internet.reactor.callLater(45,self.mark_update_queue_status)

		#print "get",self.get_messages_running,"post",self.post_messages_running,"key",self.key_search_running,"cont",self.agent_queue,"time",time.time()
		# cases where we do not start the next event
		if len(self.agent_queue) == 0:
			return

		task = self.agent_queue[0]
		task_type = task[0]

		if task_type == 'AB_KEY_SEARCH' or task_type == 'AB_KEY_IMPORT' or task_type == 'THROTTLE_OUTBOUND':
			if self.key_search_running == True:
				return
		elif self.post_messages_running == True or self.get_messages_running == True or \
			 self.key_search_running == True or self.get_acks_running == True:
			return

		task = self.agent_queue.pop(0)
		task_type = task[0]
		#DBGOUT#print "got task ",task_type

		if self.passphrase == None and task_type != 'TERMINATE' and task_type != 'SET_PASSPHRASE' and task_type != 'NEW_VERSION_CHECK':
			if self.askedForPassphrase == False:
				if self.passphraseRefused == False or task_type == 'CHECK_SEND':
					if global_config.gnupg_is_v2 == False: # v2, agent must handle it
						self.from_agent_queue.put( [ 'PASSPHRASE_REQUIRED' ] )
					else:
						self.to_agent_queue.put( [ 'SET_PASSPHRASE','none' ] )
					self.askedForPassphrase = True
					self.passphraseRefused = False

			# User refused passphrase: discard any CHECK_SEND, unlock his Check button,
			# and idle until he clicks Check again
			if task_type == 'PASSPHRASE_REFUSED':
				new_agent_queue = [ ]
				got_check_send = False
				for entry in self.agent_queue:
					if entry[0] == 'CHECK_SEND':
						got_check_send = True
					else:
						new_agent_queue.append(entry)
				if got_check_send == True:
					self.from_agent_queue.put( [ 'ENABLE_CHECK_SEND',False] )
				self.agent_queue = new_agent_queue
				self.passphraseRefused = True	
				self.askedForPassphrase = False
			else:
				self.agent_queue.append(task)
			return

		rand_hasher = hashlib.new('sha256')
		rand_hasher.update(self.random_pool)
		rand_hasher.update(str(time.time()))
		for t in task:
			if type(t) == str:
				rand_hasher.update(t)
		self.random_pool = rand_hasher.digest() + self.random_pool[0:random_pool_size]

		if task_type == 'TERMINATE':
			self.agentStopped = True
			self.from_agent_queue.put( [ 'TERMINATE' ] )
			twisted.internet.reactor.stop()
		elif task_type == 'ENCODE_SEND':
			self.encode_send(task[1],task[2])
		elif task_type == 'CHECK_SEND':
			if len(task) > 2:
				self.check_send(task[1],task[2])
			else:
				self.check_send(task[1])
		elif task_type == 'DECRYPT_RETRY':
			self.decrypt_retry(task[1])
		elif task_type == 'CLIENT_NEW_KEYS':
			self.from_agent_queue.put( [ 'AGENT_NEW_KEYS' ] )
		elif task_type == 'CLIENT_NEW_MESSAGES':
			self.from_agent_queue.put( [ 'NEW_MESSAGES' ] )
		elif task_type == 'AB_KEY_SEARCH':
			self.key_search_start(True,False,False,task[1],task[2],task[3],task[4])
		elif task_type == 'AB_KEY_IMPORT':
			self.ab_key_import(task[1])
		elif task_type == 'AB_KEY_DELETE':
			self.ab_key_delete(task[1])
		elif task_type == 'EXP_KEY_SEARCH':
			self.key_search_start(False,True,False,task[1],task[2],task[3],task[4])
		elif task_type == 'BG_KEY_SEARCH':
			self.key_search_start(False,False,False,task[1],task[2],task[3],task[4])
		elif task_type == 'REF_KEY_SEARCH':
			self.key_search_start(False,False,True,True,True,None,task[1])
		elif task_type == 'ACK_SEARCH':
			self.ack_search_start(task[1])
		elif task_type == 'POST_KEY':
			self.post_key(task[1],task[2])
		elif task_type == 'SET_PASSPHRASE':
			self.passphraseRefused = False
			self.set_passphrase(task[1])
		elif task_type == 'PREP_FWD_MSG':
			self.check_prep_forwarded_message(task[1],task[2],task[3])
		elif task_type == 'NEW_VERSION_CHECK':
			self.new_version_check_start(task[1])
		elif task_type == 'SEND_FOLDER_CHANGES':
			self.send_folder_changes(task[1])
		elif task_type == 'SYNC_BYPASS_TOKEN':
			self.sync_bypass_token_in(task[1])
		elif task_type == 'THROTTLE_OUTBOUND':
			self.post_message.set_throttle(task[1])

def process_run(homedir,to_agent_queue,from_agent_queue,log_debug,log_all_traffic):
	#DBGOUT#print "Agent process started at",homedir
	agent = client_agent(homedir,to_agent_queue,from_agent_queue,log_debug,log_all_traffic)
	agent.parse_config_and_setup()
	twisted.internet.reactor.callLater(3,agent.set_status_line,0,None)
	twisted.internet.reactor.callLater(4,agent.check_queue)
	twisted.internet.reactor.callLater(45,agent.mark_update_queue_status)
	twisted.internet.reactor.run()
	#DBGOUT#print "Agent process terminated"	

# EOF
