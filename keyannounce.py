# create key announcements

import datetime
import re
import hashlib
import random
import gnupg
import client
import proofofwork
import global_config
import logging
import bypass_token
import twisted.internet.endpoints;

datetime_match = re.compile("^\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
emailadr_match = re.compile("^[^<]*<([^>]*)>.*$")
re_keyid = re.compile("^KEYID: ([0-9A-F]{40})$",re.IGNORECASE)
re_transport_entangled = re.compile("^transport: entangled$",re.IGNORECASE)
re_transport_server = re.compile("^transport: server=",re.IGNORECASE)
re_transport_tor = re.compile("^transport: server=.*\.onion:[0-9]",re.IGNORECASE)
re_transport_i2p = re.compile("^transport: server=.*\.i2p:[0-9]",re.IGNORECASE)
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

class keyannounce:

	def __init__(self,gnupg,tor_proxy,i2p_proxy,socks_proxy,proxy_ip,proxy_tor,proxy_i2p,use_exit_node,server_connection,log_traffic_callback):
		self.gnupg = gnupg
		self.logger = logging.getLogger(__name__)
		self.tor_proxy = tor_proxy # address:port
		self.i2p_proxy = i2p_proxy # address:port
		self.socks_proxy = socks_proxy # address:port
		self.proxy_ip = proxy_ip # boolean should we proxy direct-ip via server?
		self.proxy_tor = proxy_tor # boolean should we proxy tor via server?
		self.proxy_i2p = proxy_i2p # boolean should we proxy i2p via server?
		self.use_exit_node = use_exit_node
		self.server_connection = server_connection
		self.log_traffic_callback = log_traffic_callback

	# Mailboxes: list of one or two character strings to be prepended to
	# the key hash to generate mailbox addresses
	# Transport: entangled
	# Transport: server:hostname:port
	# Transport: server:ipaddress:port,server:ipaddress:port
	def create_key_announcement_message(self,key_fingerprint,sender_proof_of_work,
	        pow_nbits,pow_nmatches,mailboxes,transport,bypasstoken,passphrase = None):
		""" returns the clearsigned string, address claim hash, and address claim """
		key_fingerprint = key_fingerprint.upper()
	
		nowtime_obj = datetime.datetime.utcnow()
		nowtime = nowtime_obj.strftime("%Y-%m-%dT%H:%M:%SZ")
		exptime_obj = nowtime_obj + datetime.timedelta(0,global_config.renew_age_key)
		exptime = exptime_obj.strftime("%Y-%m-%dT%H:%M:%SZ")
	
		address = ""
		all_keys = self.gnupg.list_keys()
		for key in all_keys:
			if key['fingerprint'].upper() == key_fingerprint.upper():
				address = key['uids'][0]

		expkey = self.gnupg.export_keys(key_fingerprint)
		if expkey == '':
			raise KeyError('public key not found')
		keya = "Type: key-announcement\n" + \
	           "Version: 1\n" + \
	           "Date: " + nowtime + "\n" + \
	           "Expires: " + exptime + "\n"
		if address != '':
			keya += "Userid: " + address + "\n"
		keya +="Transport: " + transport + "\n" + \
		       "Mailboxes: " + mailboxes + "\n" + \
	           "SenderProofOfWork: " + str(sender_proof_of_work) + "\n"
		if bypasstoken != None:
			keya += "BypassTokenAccepted: " + bypasstoken.get_earliest_time() + "\n"
		keya += "\n" + expkey + "\n"
		mkeya = keya.replace("\r","").replace("\n","")
		pow = proofofwork.generate_proof_of_work(mkeya.encode('utf-8'),pow_nbits,pow_nmatches)
		keya = "ProofOfWork: " + pow + "\n" + keya
		skeya = self.gnupg.sign(keya,keyid=key_fingerprint,passphrase=passphrase)
		if type(skeya) == gnupg.Sign:
			skeya = unicode(skeya).encode('utf-8')
			skeya = skeya.replace("\r","")
		if skeya == '':
			raise KeyError('signature operation failed or secret key not found')

		sadrc_hash = None
		sadrc = None
		m = emailadr_match.match(address)
		if m:
			emailadr = m.group(1).lower()
			powblock = nowtime.encode('ascii','ignore') + key_fingerprint.decode('hex') + emailadr.encode('utf-8')
			pow = proofofwork.generate_proof_of_work(powblock,pow_nbits,pow_nmatches)
			adrc =	"Type: address-claim\n" + \
					"Version: 1\n" + \
					"Date: " + nowtime + "\n" + \
				  	"ProofOfWork: " + pow + "\n" + \
				  	"Keyid: " + key_fingerprint + "\n" + \
			   		"Address: " + emailadr + "\n"
			sadrc = self.gnupg.sign(adrc,keyid=key_fingerprint,passphrase=passphrase)
			if type(sadrc) == gnupg.Sign:
				sadrc = unicode(sadrc).encode('utf-8')
				sadrc = sadrc.replace("\r","")
			if sadrc == '':
				raise KeyError('signature operation failed or secret key not found')
			hasher = hashlib.new('sha1')
			hasher.update(emailadr.encode('utf-8'))
			sadrc_hash = hasher.digest().encode('hex')

		return skeya,sadrc_hash,sadrc
	
	def verify_key_announcement_message(self,announce_message,pow_min_nbits,pow_min_nmatches):
		""" Returns boolean isValid, string keyid, timedelta age, boolean isExpired, string errmsg, string gpgstatus """
		public_key = ""
		signed_message = ""
		pow_message = ""
		proof_of_work = ""
		posting_date = ""
		expires_date = ""
		start_public_key = False	
		end_public_key = False	
		start_signed_message = False
		end_signed_message = False
		start_pow_message = False
		end_pow_message = False
		is_expired = False
		announce_message = announce_message.replace("\r","")
		for line in announce_message.split("\n"):
			if line == "-----BEGIN PGP SIGNED MESSAGE-----":
				if end_signed_message == False:
					start_signed_message = True
					signed_message += line + "\n"
			elif line == "-----END PGP SIGNATURE-----":
				end_signed_message = True
				signed_message += line + "\n"
			elif line == "- -----BEGIN PGP PUBLIC KEY BLOCK-----":
				if end_public_key == False:
					start_public_key = True
					signed_message += line + "\n"
					public_key += line[2:] + "\n"
					pow_message += line[2:]
			elif line == "- -----END PGP PUBLIC KEY BLOCK-----":
				end_public_key = True
				signed_message += line + "\n"
				public_key += line[2:] + "\n"
				pow_message += line[2:]
			elif start_signed_message == True and end_signed_message == False:
				signed_message += line + "\n"
				if line == "-----BEGIN PGP SIGNATURE-----":
					end_pow_message = True
				if start_pow_message == True and end_pow_message == False:
					pow_message += line
				if line[0:6] == "Date: " and posting_date == "":
					posting_date = line[6:]
				if line[0:9] == "Expires: " and expires_date == "":
					expires_date = line[9:]
				if line[0:13] == "ProofOfWork: " and proof_of_work == "":
					proof_of_work = line[13:]
					start_pow_message = True
				if start_public_key == True and end_public_key == False:
					public_key += line + "\n"
		
		if start_public_key == False or end_public_key == False or \
				start_signed_message == False or end_signed_message == False or \
				start_pow_message == False or end_pow_message == False or \
				proof_of_work == "" or posting_date == "":
			return False,"",None,is_expired,"message parts missing",""
	
		if datetime_match.match(posting_date) == None:
			return False,"",None,is_expired,"invalid posting date",""
		posting_datetime = datetime.datetime.strptime(posting_date,"%Y-%m-%dT%H:%M:%SZ")
		current_datetime = datetime.datetime.utcnow()
		announcement_age = current_datetime - posting_datetime
		#DBGOUT#print "current datetime",current_datetime,"posting datetime",posting_datetime,"announcement age",announcement_age
	
		if expires_date != "" and datetime_match.match(expires_date) != None:
			expires_datetime = datetime.datetime.strptime(expires_date,"%Y-%m-%dT%H:%M:%SZ")
			expires_age = current_datetime - expires_datetime
			if expires_age.total_seconds() > 0:
				is_expired = True
			#DBGOUT#print "current datetime",current_datetime,"expires datetime",expires_datetime,"expires age",expires_age,"is expired",is_expired
	
		check_nbits,check_nmatches = proofofwork.verify_proof_of_work(pow_message.replace("\r","").replace("\n",""),proof_of_work)
		if check_nbits < pow_min_nbits or check_nmatches < pow_min_nmatches:
			return False,"",announcement_age,is_expired,"invalid proof of work",""
	
		import_result = self.gnupg.import_keys(public_key)
		if import_result == None or type(import_result) != gnupg.ImportResult or \
				len(import_result.fingerprints) != 1:
			return False,"",announcement_age,is_expired,"import failure",""
	
		key_fingerprint = import_result.fingerprints[0]
		verify_result = self.gnupg.verify(signed_message)
		if verify_result == None or type(verify_result) != gnupg.Verify:
			return False,key_fingerprint,announcement_age,is_expired,"verify run failure",""
	
		if verify_result.pubkey_fingerprint != key_fingerprint:
			return False,key_fingerprint,announcement_age,is_expired,"key fingerprint mismatch",""
	
		if verify_result.valid != True:
			return False,key_fingerprint,announcement_age,is_expired,"invalid signature",verify_result.status
	
		return True,key_fingerprint,announcement_age,is_expired,"success",verify_result.status
	
	# Posts key and address claim
	def post_key_announcement(self,server,keyid,announcement,address_claim_hash,address_claim,post_to_server,post_to_entangled,
				callback,timeout,validate_cert_callback,userhash = None,authkey = None):
		self.server = server
		self.keyid = keyid
		self.announcement = announcement
		self.address_claim_hash = address_claim_hash
		self.address_claim = address_claim
		self.post_servers = self.server[7:].split(',') # skipping server=
		self.post_to_server = post_to_server
		self.post_to_entangled = post_to_entangled
		self.posted_key_to_server = False
		self.posted_key_to_entangled = False
		self.posted_claim_to_server = False
		self.posted_claim_to_entangled = False
		self.completion_callback = callback
		self.timeout = timeout
		self.validate_cert_callback = validate_cert_callback
		self.userhash = userhash
		self.authkey = authkey	
		self.done_posting = False
		self.session_terminated = False
		self.error_messages = [ ]

		if len(self.post_servers) > 1:
			self.post_servers = re_order_servers(self.post_servers,self.use_exit_node,self.server_connection)
		self.start_new_post_server()

	def start_new_post_server(self):
		if len(self.post_servers) == 0:
			self.session_terminated = True
			self.completion_callback(self.posted_key_to_server,self.posted_key_to_entangled,self.posted_claim_to_server,self.posted_claim_to_entangled,self.error_messages)
			return

		self.post_server = self.post_servers.pop(0)
		nethost,netport = self.post_server.rsplit(':',1)
		netport = int(netport)
		sockshost = None
		socksport = None

		if re_server_is_tor.match(self.post_server):
			if self.tor_proxy == None:
				self.error_messages.append("got tor server and no tor proxy configured")
				self.start_new_post_server()
				return
			sockshost,socksport = self.tor_proxy.rsplit(':',1)
		elif re_server_is_i2p.match(self.post_server):
			if self.i2p_proxy == None:
				self.error_messages.append("got i2p server and no i2p proxy configured")
				self.start_new_post_server()
				return
			sockshost,socksport = self.i2p_proxy.rsplit(':',1)
		elif self.use_exit_node == True:
			if self.tor_proxy == None:
				self.error_messages.append("got use exit node and no tor proxy configured")
				self.start_new_post_server()
				return
			sockshost,socksport = self.tor_proxy.rsplit(':',1)
		elif self.socks_proxy != None:
			sockshost,socksport = self.socks_proxy.rsplit(':',1)
		else:
			nethost,netport = self.post_server.rsplit(':',1)
			netport = int(netport)

		if socksport != None:
			socksport = int(socksport)

		nethost,netport = self.post_server.rsplit(':',1)
		netport = int(netport)
		self.nethost = nethost
		self.netport = netport

		endpoint = client.getEndpoint(twisted.internet.reactor,nethost,netport,self.timeout,bindAddress=None,socksHost = sockshost,socksPort = socksport)
		#DBGOUT#if sockshost != None:
			#DBGOUT#self.logger.debug("Starting post key connection %s %i via socks %s %i",nethost,netport,sockshost,socksport)
		#DBGOUT#else:
			#DBGOUT#self.logger.debug("Starting post key connection %s %i direct",nethost,netport)

		clientProt = client.clientProtocol(self.post_client_completion_callback,None,self.timeout,logCallback = self.log_traffic_callback)
		clientProt.openConnection(endpoint,userhash = self.userhash,authkey = self.authkey)


	def post_client_completion_callback(self,client,context,command,resultmsg,textdata,bindata):
		resultL = resultmsg.lower()
		
		if self.session_terminated == True:
			return # ignore spurious message

		#DBGOUT#print "completion result",resultL
		if resultL == "connected" and self.validate_cert_callback != None:
			validate_result = self.validate_cert_callback(self.nethost,self.netport,client.serverCertificate)
			if validate_result == False: # This abort logic is not being used and has not been checked out.
				send_command = "QUIT"
				self.done_posting = True
				client.sendCommand(send_command,None)
				return	
				
		if resultL == "connected" or resultL == "done":
			if resultL == "done":
				if self.post_to_server == True and self.posted_key_to_server == False:
					self.posted_key_to_server = True
				elif self.post_to_entangled == True and self.posted_key_to_entangled == False:
					self.posted_key_to_entangled = True
				elif self.post_to_server == True and self.posted_claim_to_server == False:
					self.posted_claim_to_server = True
				elif self.post_to_entangled == True and self.posted_claim_to_entangled == False:
					self.posted_claim_to_entangled = True
			if self.post_to_server == True and self.posted_key_to_server == False:
				send_command = "STORE SERVER " + self.keyid,self.announcement
			elif self.post_to_entangled == True and self.posted_key_to_entangled == False:
				send_command = "STORE ENTANGLED " + self.keyid,self.announcement
			elif self.post_to_server == True and self.posted_claim_to_server == False:
				send_command = "STORE SERVER " + self.address_claim_hash,self.address_claim
			elif self.post_to_entangled == True and self.posted_claim_to_entangled == False:
				send_command = "STORE ENTANGLED " + self.address_claim_hash,self.address_claim
			else:
				send_command = "QUIT"
				self.done_posting = True
			client.sendCommand(send_command,None)
		
		elif resultL == "disconnect" and self.done_posting == True: # good disconnect
			self.session_terminated = True
			self.completion_callback(self.posted_key_to_server,self.posted_key_to_entangled,self.posted_claim_to_server,self.posted_claim_to_entangled,self.error_messages)

		elif resultL == "disconnect" or resultL == "connect failed" or client.connectionClosed == True:
			self.error_messages.append(self.post_server + ': ' + resultmsg)
			self.error_messages.extend(textdata)
			self.start_new_post_server()

		else: # command failed but still connected
			client.sendCommand("QUIT",None)

	def get_key_claims_for_address(self,server,email_address,isEntangled,callback,timeout):
		pass
		

	# Input can be either a list of keyids or an email address, not both
	# Returns a list of ( hash,data )
	# If an email address was provided the first entry will be the key claims
	def get_key_announcements(self,server,email_address,keyids,isEntangled,callback,timeout,validate_cert_callback):
		#DBGOUT#print "server",server
		#DBGOUT#print "email_address",email_address
		#DBGOUT#print "keyids",keyids
		#DBGOUT#print "isEntangled",isEntangled
		#DBGOUT#print "callback",callback
		#DBGOUT#print "timeout",timeout

		self.error_messages = [ ]
		self.server = server
		self.validate_cert_callback = validate_cert_callback
		self.email_address = email_address
		if keyids == None:
			self.keyids = [ ]
		else:
			self.keyids = keyids[0:]
		self.isEntangled = isEntangled
		self.completion_callback = callback
		self.timeout = timeout
		self.get_servers = self.server[7:].split(',') # skipping server=
		if len(self.get_servers) > 1:
			self.get_servers = re_order_servers(self.get_servers,self.use_exit_node,self.server_connection)

		self.session_terminated = False
		self.found_keys = [ ]
		self.found_claims = [ ]
		#DBGOUT#print "keyids = ",self.keyids
		#DBGOUT#print "emailadr = ",self.email_address
		self.start_new_get_server()

	def start_new_get_server(self):
		if len(self.get_servers) == 0:
			self.completion_callback(self.found_keys,self.found_claims,self.error_messages)
			return

		self.get_server = self.get_servers.pop(0)
		sockshost = None
		socksport = None

		if re_server_is_tor.match(self.get_server):
			if self.tor_proxy == None:
				self.error_messages.append("got tor server and no tor proxy configured")
				self.start_new_get_server()
				return
			sockshost,socksport = self.tor_proxy.rsplit(':',1)
		elif re_server_is_i2p.match(self.get_server):
			if self.i2p_proxy == None:
				self.error_messages.append("got i2p server and no i2p proxy configured")
				self.start_new_get_server()
				return
			sockshost,socksport = self.i2p_proxy.rsplit(':',1)
		elif self.use_exit_node == True:
			if self.tor_proxy == None:
				self.error_messages.append("got use exit node and no tor proxy configured")
				self.start_new_get_server()
				return
			sockshost,socksport = self.tor_proxy.rsplit(':',1)
		elif self.socks_proxy != None:
			sockshost,socksport = self.socks_proxy.rsplit(':',1)

		nethost,netport = self.get_server.rsplit(':',1)
		netport = int(netport)
		self.nethost = nethost
		self.netport = netport

		if socksport != None:
			socksport = int(socksport)

		self.done_with_target = False
		endpoint = client.getEndpoint(twisted.internet.reactor,nethost,netport,self.timeout,bindAddress=None,socksHost = sockshost,socksPort = socksport)
		#DBGOUT#if sockshost != None:
			#DBGOUT#self.logger.debug("Starting get key connection %s %i via socks %s %i",nethost,netport,sockshost,socksport)
		#DBGOUT#else:
			#DBGOUT#self.logger.debug("Starting get key connection %s %i direct",nethost,netport)
		clientProt = client.clientProtocol(self.get_client_completion_callback,None,self.timeout,logCallback = self.log_traffic_callback)
		clientProt.openConnection(endpoint)


	def get_client_completion_callback(self,client,context,command,resultmsg,textdata,bindata):
		resultL = resultmsg.lower()
		
		if self.session_terminated == True:
			return # ignore spurious message

		#DBGOUT#print "completion result",resultL
		if resultL == "connected" and self.validate_cert_callback != None:
			validate_result = self.validate_cert_callback(self.nethost,self.netport,client.serverCertificate)
			if validate_result == False: # This abort logic is not being used and has not been checked out.
				send_command = "QUIT"
				client.sendCommand(send_command,None)
				return	
				
		if resultL == "connected":
			self.send_next_get_query(client)

		elif resultL == "found":
			if self.email_address != None:
				self.found_claims.append( ( self.keyid,textdata ) )
				self.email_address = None
				self.keyids = self.extract_keyids_from_claims(textdata)
			else:
				self.found_keys.append( ( self.keyid,textdata ) )
			self.send_next_get_query(client)

		elif resultL == "not found":
			if self.email_address != None:
				self.email_address = None
				self.keyids = [ ]
			self.send_next_get_query(client)
			
		elif resultL == "disconnect" and self.email_address == None and len(self.keyids) == 0: # good disconnect
			self.session_terminated = True
			self.completion_callback(self.found_keys,self.found_claims,self.error_messages)

		elif resultL == "disconnect" or resultL == "connect failed" or client.connectionClosed == True:
			self.error_messages.append(self.get_server + ': ' + resultmsg)
			self.error_messages.extend(textdata)
			self.start_new_get_server()

	def send_next_get_query(self,client):
		if self.email_address != None:
			hasher = hashlib.new('sha1')
			hasher.update(self.email_address.lower())
			self.keyid = hasher.digest().encode('hex')
		elif len(self.keyids) == 0:
			client.sendCommand("QUIT",None)
			return
		else:
			self.keyid = self.keyids.pop(0)
		if self.isEntangled == True:
			send_command = "GET ENTANGLED " + self.keyid
		else:
			send_command = "GET SERVER " + self.keyid
		client.sendCommand(send_command,None)
		
	def extract_keyids_from_claims(self,textdata):
		keyids = [ ]
		for line in textdata:
			line = line.rstrip('\r\n')
			m = re_keyid.match(line)
			if m:
				keyids.append(m.group(1))
		return keyids

# EOF
