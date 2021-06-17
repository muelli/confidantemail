import os
import os.path
import logging
import zipfile
import re
import struct
import random
import codecs
import datetime
import global_config
import twisted.protocols.basic
import twisted.internet.protocol
import twisted.internet.reactor
import twisted.internet.endpoints
import gnupg
import proofofwork
import hashlib
import client
import bypass_token

re_isolate_filename = re.compile('^.*[\\\/]([^\\\/]+)$')
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

class postmessage:

	def __init__(self,gnupg,outbox_store,entangled_server,tor_proxy,i2p_proxy,socks_proxy,proxy_ip,proxy_tor,proxy_i2p,use_exit_node,server_connection,timeout,log_traffic_callback):
		self.gnupg = gnupg
		self.logger = logging.getLogger(__name__)
		self.update_timestamp()
		self.outbox_store = outbox_store
		self.tor_proxy = tor_proxy # address:port
		self.i2p_proxy = i2p_proxy # address:port
		self.socks_proxy = socks_proxy # address:port
		self.proxy_ip = proxy_ip # boolean should we proxy direct-ip via server?
		self.proxy_tor = proxy_tor # boolean should we proxy tor via server?
		self.proxy_i2p = proxy_i2p # boolean should we proxy i2p via server?
		self.use_exit_node = use_exit_node
		self.server_connection = server_connection
		self.proxy_send_mode = False
		self.timeout = timeout
		self.entangled_server = entangled_server
		self.plaintext_file = 'PLAINTXT.ZIP'
		self.ciphertext_file = 'ENCRYPTED.PGP'
		self.signature_file = 'DETACHED.SIG'
		self.temp_file = 'PLAINTXT.DAT'
		self.header_file = 'HEADER.TXT'
		self.log_traffic_callback = log_traffic_callback
		self.throttle_kbps = None
		self.shutdown_flag = False

	def update_timestamp(self):
		self.nowtime = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

	def sign_encrypt_zipfile(self,infile,outfile,sigfile,tempfile,recipkeys,signkey,passphrase,blocksize,status_callback):
		status_callback('Signature')
		infh = open(infile,'rb')
		result = self.gnupg.sign_file(infh,keyid = signkey,
			binary = True,passphrase = passphrase,detach = True)
		infh.close()
		signature_data = result.data
		if len(signature_data) == 0:
			raise IOError,"GPG encrypt/sign failed"

		outfh = open(sigfile,'wb')
		outfh.write(signature_data)
		outfh.close()

		status_callback('File Merge')
		chunkSize = 262144
		infh = open(infile,'rb')
		outfh = open(tempfile,'wb')
		outfh.write(struct.pack('>h',len(signature_data))) # 16 bit big endian
		outfh.write(signature_data)
		while True:
			buf = infh.read(chunkSize)
			if len(buf) == 0:
				break
			outfh.write(buf)
			if len(buf) < chunkSize:
				break
		outfh.close()
		infh.close()

		status_callback('Encrypt')
		infh = open(tempfile,'rb')
		result = self.gnupg.encrypt_file(infh,recipkeys,
			always_trust = True,armor = False,output = outfile,symmetric = False)
		if result.ok == False:
			raise IOError,"GPG encrypt/sign failed"
		infh.close()

		infh = open(outfile,'rb')
		hash = hashlib.new('sha1')
		outlen = 0
		piece_hashes = [ ]
		status_callback('Hash Blocks')
		while True:
			inblock = infh.read(blocksize)
			if len(inblock) == 0:
				break
			outlen += len(inblock)
			hash.update(inblock)
			piece_hash = hashlib.new('sha1')
			piece_hash.update(inblock)
			piece_hashes.append(piece_hash.digest())
			if len(inblock) < blocksize:
				break
		infh.close()
		message_hash = hash.digest()
		return result,message_hash,outlen,piece_hashes

	def make_data_block(self,message_hash,infile,blocksize,blocknum,pow_nbits,pow_nmatches,embargo):
		last_block = False
		infh = open(infile,'rb')
		infh.seek(blocksize * blocknum)
		inblock = infh.read(blocksize)
		if inblock < blocksize:
			last_block = True
		else:
			testbyte = infh.read(1)
			if len(testbyte) < 1:
				last_block = True
		infh.close()
		
		hash = hashlib.new('sha1')
		hash.update(inblock)
		blockhash = hash.digest()

		pow = proofofwork.generate_proof_of_work(self.nowtime + inblock,pow_nbits,pow_nmatches)	
		outblock = ""
		if embargo != None:
			outblock += "Embargo: " + embargo + "\n"
		outblock += "Type: data\n" + \
			"Date: " + self.nowtime + "\n" + \
			"Version: 1\n" + \
			"ProofOfWork: " + pow + "\n" + \
			"Data: " + str(len(inblock)) + "\n" + \
			inblock
			#inblock.encode("hex")
		return blockhash,outblock,last_block
		
	def make_message_announcement(self,message_hash,hash_prefix,piece_hashes,recipient,pow_nbits,pow_nmatches,pow_nbits_global,pow_nmatches_global,embargo,disable_server_notify,bypasstoken):
		powblock = recipient + message_hash + self.nowtime 
		for ph in piece_hashes:
			powblock += ph
		btoken = None
		if bypasstoken != None:
			btoken = bypasstoken.generate_bypass_hash(recipient.encode("hex"),powblock)
		if btoken != None:
			proof_of_work = proofofwork.generate_proof_of_work(powblock,pow_nbits_global,pow_nmatches_global)
		else:
			proof_of_work = proofofwork.generate_proof_of_work(powblock,pow_nbits,pow_nmatches)
		outblock = ""
		if embargo != None:
			outblock += "Embargo: " + embargo + "\n"
		outblock += "Type: message-announcement\n" + \
			"Date: " + self.nowtime + "\n" + \
			"Version: 1\n" + \
			"Recipient: " + recipient.encode("hex") + "\n" + \
			"Mailbox: " + hash_prefix + "\n" + \
			"ProofOfWork: " + proof_of_work + "\n"
		if disable_server_notify == True:
			outblock += "ServerNotify: False\n"
		if btoken != None:
			outblock += "BypassToken: " + btoken + "\n"
		for ph in piece_hashes:
			outblock += "DataBlock: " + ph.encode("hex") + "\n"
		outblock += "MessageHash: " + message_hash.encode("hex") + "\n"
		return outblock
		
	def generate_ack(self,recip,encrypted,bypasstoken,bypasstoken_earliest,random_function):
		hash = hashlib.new('sha1')
		hash.update(self.nowtime)
		hash.update(random_function(20))
		hash.update(recip)
		ack_resp = hash.digest()
		hash = hashlib.new('sha1')
		hash.update(ack_resp)
		ack_req = hash.digest()

		if bypasstoken != None and bypasstoken_earliest != None:
			is_new,btoken = bypasstoken.get_outgoing_token(recip.encode("hex"),bypasstoken_earliest)
			ack_resp = 'ack=' + ack_resp.encode("hex").lower() + "|" + "bt=" + btoken
			encrypted = True

		if encrypted == True:
			reciplist = [ ]
			reciplist.append(recip.encode("hex"))
			result = self.gnupg.encrypt(ack_resp,reciplist,always_trust = True,armor = False)
			if result.ok == False:
				raise IOError,"GPG encrypt of acknowledgment failed"
			if bypasstoken != None and bypasstoken_earliest != None and is_new == True:
				return True,ack_req,result.data,btoken
			else:
				return True,ack_req,result.data,None
		else:
			return False,ack_req,ack_resp,None

	def encode_message(self,local_store,content_dir,sender,sender_transport, \
			recipients,attachments,reply_thread_id,forward_original_id,subject, \
			embargo_time,embargo_user,custom_from,passphrase,status_callback, \
			bypasstoken,disable_server_notify,random_function):
		#DBGOUT#self.logger.debug("Looking up keys")
		self.update_timestamp()
		public_keys = self.gnupg.list_keys()
		sender_hex = sender.encode("hex")
		sent_to_self = False
		announce_hashes = [ ]	
		data_hashes = [ ]	
		bypass_tokens = [ ]
			
		status_callback('Create Header')
		keymap = { }
		uidmap = { }
		powmap = { }
		mbxmap = { }
		transmap = { }
		transmap_all = { }
		for key in public_keys:
			keyid = key['fingerprint'].decode("hex")
#			print "keyid",keyid.encode("hex")
#			print keyid.encode("hex") + " " + key['uids'][0]
			keymap[keyid] = key
			uidmap[keyid] = key['uids'][0]

		if custom_from == None:
			fromuid = uidmap[sender]
		else:
			fromuid = custom_from
		header_path = content_dir + os.sep + self.header_file
		header = codecs.open(header_path,'w','utf-8')
		header.write("From: " + fromuid + " " + sender_hex + "\n")

		recipients_hex = [ ]
		data_blocksize = global_config.max_blocksize_server
		pow_nbits_datablock = global_config.pow_nbits_data_server
		pow_nmatches_datablock = global_config.pow_nmatches_data_server

		if len(recipients) > 1:
			encrypt_acks = True
		else:
			encrypt_acks = False

		for recipIn in recipients:
			recip_type,recipH = recipIn.lower().split(':',1)
			recip = recipH.decode("hex")
			recipients_hex.append(recipH)
			if sender_hex == recipH:
				sent_to_self = True
			if recip not in uidmap:
				raise KeyError,recipH
			if recip_type == 't':
				recip_type = 'To: '
			elif recip_type == 'c':
				recip_type = 'Cc: '
			elif recip_type == 'b':
				recip_type = 'Bcc: '
			header.write(recip_type + uidmap[recip] + " " + recipH + "\n")
			found,keyannounce = local_store.retrieveHeaders(recipH)
			bypasstoken_earliest = None
			if found == False:
				raise KeyError,recipH
			for line in keyannounce:
				lineL = line.lower()
				if lineL[0:22] == "senderproofofwork: bd,":
					powmap[recip] = lineL[22:]
				elif lineL[0:11] == "transport: ":
					transmap[recip] = lineL[11:]
					if recipH != embargo_user: # not sending to this one
						transmap_all[lineL[11:]] = True
					if lineL[11:20] == "entangled":
						# Entangled has a shorter blocksize and higher proof of work, so use if any non-server recipients
						data_blocksize = global_config.max_blocksize_entangled
						pow_nbits_datablock = global_config.pow_nbits_data_entangled
						pow_nmatches_datablock = global_config.pow_nmatches_data_entangled
				elif lineL[0:11] == "mailboxes: ":
					mbxmap[recip] = line[11:]
				elif lineL[0:21] == "bypasstokenaccepted: ":
					bypasstoken_earliest = line[21:]
			header.write("KeyTransport-"+recipH + ": " + transmap[recip] + "\n")

			is_encrypted,ack_req,ack_resp,bypass_token = self.generate_ack(recip,encrypt_acks,bypasstoken,bypasstoken_earliest,random_function)
			if bypass_token != None:
				bypass_tokens.append(recipH + ',' + bypass_token)
			if is_encrypted == True:
				ack_path = content_dir + os.sep + "ACK_" + recipH.upper() + ".PGP"
			else:
				ack_path = content_dir + os.sep + "ACK_" + recipH.upper() + ".BIN"
			ack_file = open(ack_path,'wb')
			ack_file.write(ack_resp)
			ack_file.close()
			header.write("Ack-" + recipH + ": " + ack_req.encode("hex") + "\n")
			
		header.write("MessageUniqueId: " + random_function(20,subject.encode('utf-8') + recipH.encode('utf-8')).encode('hex') + "\n")
		if forward_original_id != None:
			header.write("ForwardedMessageId: " + forward_original_id + "\n")
		if reply_thread_id != None:
			header.write("ReplyThreadId: " + reply_thread_id + "\n")
		header.write("Subject: " + subject + "\n")
		header.write("Date: " + self.nowtime + "\n")
		if sent_to_self == False:
			header.write("KeyTransport-" + sender_hex + ": " + sender_transport + "\n")
		header.close()
		transport_all = ""
		for trans in transmap_all.keys():
			transport_all += "Post-To: " + trans + "\n"

		#DBGOUT#self.logger.debug("Generating message")
		#DBGOUT#self.logger.debug("Creating zipfile of %s",content_dir)
		files_to_send = os.listdir(content_dir)
		
		zipfile_name = content_dir + os.sep + self.plaintext_file	
		zip_out = zipfile.ZipFile(zipfile_name,'w',zipfile.ZIP_STORED,True)
		status_callback('Create Zip')
		for fn in files_to_send:
			if fn == self.plaintext_file or fn == self.ciphertext_file or \
			   fn == self.signature_file or fn == self.temp_file:
				continue
			fp = content_dir + os.sep + fn
			if os.path.isfile(fp):
				pass #DBGOUT#self.logger.debug("Inserting file %s as %s",fp,fn)
				zip_out.write(fp,fn)
		n_attach = len(attachments)
		i_attach = 1
		for fp in attachments:
			if os.path.isfile(fp) == False:
				# This really should not happen, the UI checks for a missing file,
				# but skip it rather than blowing up like we used to.
				continue
			status_callback('Attach %i of %i' % (i_attach,n_attach))
			i_attach += 1
			m = re_isolate_filename.match(fp)
			if m:
				fn = '_'+m.group(1)
				zip_out.write(fp,fn)
				pass #DBGOUT#self.logger.debug("Inserting attachment %s as %s",fp,fn)
			if self.shutdown_flag == True:
				zip_out.close()
				os.unlink(zipfile_name)
				return None,None,None,None
		if forward_original_id != None:
			status_callback('Forward Original')
			originalZipName = forward_original_id.upper() + '.ZIP'
			originalDtsName = forward_original_id.upper() + '.DTS'
			originalZipPath = local_store.getPath(originalZipName)
			originalDtsPath = local_store.getPath(originalDtsName)
			zip_out.write(originalZipPath,originalZipName)
			zip_out.write(originalDtsPath,originalDtsName)
		zip_out.close()
		pass #DBGOUT#self.logger.debug("Done creating zipfile")		
		
		plaintext_path = content_dir + os.sep + self.plaintext_file
		ciphertext_path = content_dir + os.sep + self.ciphertext_file
		signature_path = content_dir + os.sep + self.signature_file
		temp_path = content_dir + os.sep + self.temp_file

		result,message_hash,outlen,piece_hashes = \
			self.sign_encrypt_zipfile(plaintext_path,ciphertext_path, \
			signature_path,temp_path,recipients_hex,sender_hex,passphrase, \
			data_blocksize,status_callback)
		#DBGOUT#print "result",result
		pass #DBGOUT#self.logger.debug("Done encrypting zipfile")		

		for recipIn in recipients:
			recip_is_entangled = False
			recip_type,recipH = recipIn.lower().split(':',1)
			if recipH == embargo_user: # not sending to this one
				continue
			recip = recipH.decode("hex")
			try:
				pow_nbits,pow_nmatches = powmap[recip].split(',')
				pow_nbits = int(pow_nbits)
				pow_nmatches = int(pow_nmatches)
			except (KeyError,ValueError):
				raise KeyError,"No ProofOfWork for" + recipH
			try:
				if transmap[recip].lower() == 'entangled':
					recip_is_entangled = True
				post_to = "Post-To: " + transmap[recip] + "\n"
			except (KeyError,ValueError):
				raise KeyError,"No Transport for" + recipH
			try:
				mbxprefixes = mbxmap[recip].rstrip('\r\n\t').split(',')
			except (KeyError,ValueError):
				raise KeyError,"No Mailboxes for" + recipH
			if recip_is_entangled:
				pow_nbits_global = global_config.pow_nbits_message_entangled
				pow_nmatches_global = global_config.pow_nmatches_message_entangled
				if pow_nbits < global_config.pow_nbits_message_entangled:
					pow_nbits = global_config.pow_nbits_message_entangled
				if pow_nmatches < global_config.pow_nmatches_message_entangled:
					pow_nmatches = global_config.pow_nmatches_message_entangled
			else:
				pow_nbits_global = global_config.pow_nbits_message_server
				pow_nmatches_global = global_config.pow_nmatches_message_server
				if pow_nbits < global_config.pow_nbits_message_server:
					pow_nbits = global_config.pow_nbits_message_server
				if pow_nmatches < global_config.pow_nmatches_message_server:
					pow_nmatches = global_config.pow_nmatches_message_server
			usembx = random.choice(mbxprefixes)
			#DBGOUT#print "mbxprefixes = " + str(mbxprefixes) + " using " + usembx
			hash = hashlib.new('sha1')
			pass #DBGOUT#self.logger.debug("using string for hash: " + (usembx + recip).encode('hex'))
			hash.update(usembx + recip)
			post_hash = hash.digest()
			outblock = self.make_message_announcement(message_hash,usembx,piece_hashes,recip,pow_nbits,pow_nmatches,pow_nbits_global,pow_nmatches_global,embargo_time,disable_server_notify,bypasstoken)
			outblock = post_to + outblock
			post_hash_hex = post_hash.encode("hex")
			found,existing_block = self.outbox_store.retrieve(post_hash_hex)
			if found:
				outblock = existing_block + "NextMessage\n" + outblock
			self.outbox_store.store(post_hash_hex,outblock)
			announce_hashes.append(post_hash_hex)

		blocknum = 0
		last_block = False
		while last_block == False and self.shutdown_flag == False:
			status_callback('Data Block %i' % (blocknum + 1))
			blockhash,outblock,last_block = self.make_data_block(message_hash,ciphertext_path,data_blocksize,blocknum,pow_nbits_datablock,pow_nmatches_datablock,embargo_time)
			blockhashH = blockhash.encode('hex')
			#DBGOUT#print "write block "+str(blocknum)+" blocknum " + blockhashH
			outblock = transport_all + outblock
			self.outbox_store.store(blockhashH,outblock)
			data_hashes.append(blockhashH)
			blocknum += 1

		if self.shutdown_flag == True:
			for fn in announce_hashes:
				self.outbox_store.__delitem__(fn)
			for fn in data_hashes:
				self.outbox_store.__delitem__(fn)
			return None,None,None,None

		return header_path,announce_hashes,data_hashes,bypass_tokens
		
	def make_acknowledgment(self,transport,ack_hash):
		self.update_timestamp()
		hasher = hashlib.new('sha1')
		hasher.update(ack_hash)
		ack_key = hasher.digest().encode('hex').lower()
		powblock = self.nowtime + ack_hash
		if transport.lower() == 'entangled':
			pow_nbits = global_config.pow_nbits_ack_entangled
			pow_nmatches = global_config.pow_nmatches_ack_entangled
		else:
			pow_nbits = global_config.pow_nbits_ack_server
			pow_nmatches = global_config.pow_nmatches_ack_server
		pow = proofofwork.generate_proof_of_work(powblock,pow_nbits,pow_nmatches)	
		outblock = "Post-To: " + transport + "\n" + \
			"Type: acknowledgment\n" + \
			"Date: " + self.nowtime + "\n" + \
			"Version: 1\n" + \
			"ProofOfWork: " + pow + "\n" + \
			"Hash: " + ack_hash.encode('hex') + "\n"
		self.outbox_store.store(ack_key,outblock)

	def generate_posting_list(self):
		post_targets_nondata = { }
		post_targets = { }
		post_blocks = { }
		current_datetime = datetime.datetime.utcnow()
		blocks_to_send = self.outbox_store.keys()
		for key in blocks_to_send:
			keyH = key.encode("hex")
			found,headers = self.outbox_store.retrieveHeaders(keyH)
			if found == False:
				pass #DBGOUT#self.logger.debug("Block not found: %s",keyH)
				self.error_messages.append("Block not found: " + keyH)
				continue
			post_to = [ ]
			is_data = False
			is_ack = False
			block_date = None
			embargo = False
			for line in headers:
				lineL = line.lower()
				if lineL[0:9] == 'embargo: ':
					embargo = True
			for line in headers:
				lineL = line.lower()
				if lineL[0:9] == 'post-to: ':
					if embargo == True:
						post_to.append('embargo:' + line[9:])
					else:
						post_to.append(line[9:])
				elif lineL == 'type: data':
					is_data = True
				elif lineL == 'type: acknowledgment':
					is_ack = True
				elif lineL[0:6] == 'date: ':
					block_date = line[6:]

			if is_ack == True:
				posting_datetime = datetime.datetime.strptime(block_date,"%Y-%m-%dT%H:%M:%SZ")
				ageS = (current_datetime - posting_datetime).total_seconds()
				if ageS > global_config.send_expire_ack:
					self.logger.debug("Expired unsent ack %s date %s age %i sec",keyH,block_date,ageS)
					self.outbox_store.__delitem__(keyH) # expire unsent acknowledgment
					continue

			for target in post_to:
				if is_data:
					if target not in post_targets:
						post_targets[target] = [ ]
					post_targets[target].append(key)
				else:
					if target not in post_targets_nondata:
						post_targets_nondata[target] = [ ]
					post_targets_nondata[target].append(key)
				if key not in post_blocks:
					post_blocks[key] = set()
				post_blocks[key].add(target)
		for target in post_targets_nondata.keys():
			if target not in post_targets:
				post_targets[target] = [ ]
			post_targets[target].extend(post_targets_nondata[target])
		self.post_targets_dict = post_targets
		self.post_targets_list = post_targets.keys()
		self.post_blocks_dict = post_blocks

	# Returns command tuple if there is one, None if empty
	def generate_next_post_key(self,post_target):
		if self.shutdown_flag == True:
			self.logger.debug("Shutdown commanded")
			return None,None

		key_list = self.post_targets_dict[post_target]
		if len(key_list) == 0:
			return None,None
		self.status_callback('Send Block '+str(len(key_list)))

		key = key_list.pop(0)
		keyH = key.encode("hex")

		found,block = self.outbox_store.retrieve(keyH)
		if found == False:
			pass #DBGOUT#self.logger.debug("Block not found: %s",keyH)
			self.error_messages.append("Block not found: " + keyH)
			return self.generate_next_post_key(post_target)

		text = ""
		data = None
		embargo = None
		while block != "":
			line,rest = block.split("\n",1)
			lineL = line.lower()
			if lineL[0:6] == 'data: ':
				data = rest
				break
			elif lineL[0:9] == 'post-to: ':
				if self.proxy_send_mode == True:
					text += line.replace("\r","") + "\r\n"
				block = rest	
			elif lineL[0:9] == 'embargo: ':
				embargo = line[9:]
				block = rest	
			else:
				text += line.replace("\r","") + "\r\n"
				block = rest	

		# Implement different types of store here
		post_targetL = post_target.lower()
		if data == None:
			if embargo != None:
				send_data = "STORE PROXY " + keyH + " AFTER " + embargo,text
			elif post_targetL == "entangled":
				send_data = "STORE ENTANGLED " + keyH,text
			elif self.proxy_send_mode == True:
				send_data = "STORE PROXY " + keyH,text
			else:
				send_data = "STORE SERVER " + keyH,text
		else:
			if embargo != None:
				send_data = "STORE PROXY " + keyH + " AFTER " + embargo,text,data
			elif post_targetL == "entangled":
				send_data = "STORE ENTANGLED " + keyH,text,data
			elif self.proxy_send_mode == True:
				send_data = "STORE PROXY " + keyH,text,data
			else:
				send_data = "STORE SERVER " + keyH,text,data

		return key,send_data

	def post_client_completion_callback(self,client,context,command,resultmsg,textdata,bindata):
		resultL = resultmsg.lower()
		
		if self.session_terminated == True:
			return # ignore spurious message

		#DBGOUT#print "completion result",resultL,self.done_with_target

		if resultL == "connected" and self.validate_cert_callback != None:
			validate_result = self.validate_cert_callback(self.nethost,self.netport,client.serverCertificate)
			if validate_result == False: # This abort logic is not being used and has not been checked out.
				send_command = "QUIT"
				client.sendCommand(send_command,None)
				return	

		if resultL == "connected": # new connection
			if self.command_pending != None:
				key,next_tuple = self.command_pending
				pass #DBGOUT#self.logger.debug("Scheduling first pending key " + key.encode("hex"))
			else:
				key,next_tuple = self.generate_next_post_key(self.post_target)
				if key == None:
					if self.shutdown_flag == False:
						self.error_messages.append("Got no key after connect, this should not happen")
					self.done_with_target = True
					self.command_pending = None
					client.sendCommand("QUIT",None)
				else:
					self.command_pending = key,next_tuple
					pass #DBGOUT#self.logger.debug("Scheduling first new key " + key.encode("hex"))
					client.sendCommand(next_tuple,None,throttle_kbps = self.throttle_kbps)

		elif resultL == "done": # good response
			prev_key,prev_tuple = self.command_pending
			self.command_pending = None
			if prev_key not in self.posted_blocks_dict:
				self.posted_blocks_dict[prev_key] = set()
			self.posted_blocks_dict[prev_key].add(self.post_target)

			key,next_tuple = self.generate_next_post_key(self.post_target)
			if key == None:
				pass #DBGOUT#self.logger.debug("No more keys, sent quit")
				self.done_with_target = True
				client.sendCommand("QUIT",None)
			else:
				self.command_pending = key,next_tuple
				pass #DBGOUT#self.logger.debug("Scheduling first new key " + key.encode("hex"))
				client.sendCommand(next_tuple,None,throttle_kbps = self.throttle_kbps)
				
		elif resultL == "disconnect" and self.done_with_target == True: # good disconnect
			self.start_new_target()
			
		elif resultL == "disconnect" or resultL == "connect failed" or client.connectionClosed == True:
			self.error_messages.append(self.post_server + ': ' + resultmsg)
			self.error_messages.extend(textdata)
			#DBGOUT#print "start new server after connect failure/hangup"
			self.start_new_server()

		else: # command failed but still connected
			# without done_with_target, so we connect to a new server
			client.sendCommand("QUIT",None)

	def start_new_server(self):
		if self.shutdown_flag == True or len(self.post_servers) == 0:
			#DBGOUT#print "start new target after start new server"
			if self.shutdown_flag == False:
				self.error_messages.append("Ran out of servers posting message")
			self.start_new_target()
			return

		self.post_server = self.post_servers.pop(0)
		self.proxy_send_mode = False
		sockshost = None
		socksport = None

		if re_server_is_tor.match(self.post_server):
			if self.proxy_tor == True:
				self.proxy_send_mode = True
			else:
				if self.tor_proxy == None:
					self.error_messages.append("got tor server and no tor proxy configured")
					self.start_new_server()
					return
				sockshost,socksport = self.tor_proxy.rsplit(':',1)
		elif re_server_is_i2p.match(self.post_server):
			if self.proxy_i2p == True:
				self.proxy_send_mode = True
			else:
				if self.i2p_proxy == None:
					self.error_messages.append("got i2p server and no i2p proxy configured")
					self.start_new_server()
					return
				sockshost,socksport = self.i2p_proxy.rsplit(':',1)
		elif self.proxy_ip == True:
			self.proxy_send_mode = True
		elif self.use_exit_node == True:
			if self.tor_proxy == None:
				self.error_messages.append("got use exit node and no tor proxy configured")
				self.start_new_server()
				return
			sockshost,socksport = self.tor_proxy.rsplit(':',1)
		elif self.socks_proxy != None:
			sockshost,socksport = self.socks_proxy.rsplit(':',1)

		if self.post_target.lower()[0:8] == 'embargo:':
			self.proxy_send_mode = True

		if self.proxy_send_mode == True:
			if len(self.proxy_servers) == 0:
				self.proxy_servers = self.entangled_server[7:].split(',')
			proxy_via = self.proxy_servers.pop(0)
			nethost,netport = proxy_via.rsplit(':',1)
			netport = int(netport)

			if re_server_is_tor.match(proxy_via):
				if self.tor_proxy == None:
					self.error_messages.append("got tor proxy via server and no tor proxy configured")
					self.start_new_server()
					return
				sockshost,socksport = self.tor_proxy.rsplit(':',1)
			elif re_server_is_i2p.match(proxy_via):
				if self.i2p_proxy == None:
					self.error_messages.append("got i2p proxy via server and no i2p proxy configured")
					self.start_new_server()
					return
				sockshost,socksport = self.i2p_proxy.rsplit(':',1)
			elif self.use_exit_node == True:
				if self.tor_proxy == None:
					self.error_messages.append("got tor exit node proxy via server and no tor proxy configured")
					self.start_new_server()
					return
				sockshost,socksport = self.tor_proxy.rsplit(':',1)
		else:
			nethost,netport = self.post_server.rsplit(':',1)
			netport = int(netport)

		if socksport != None:
			socksport = int(socksport)
		self.nethost = nethost
		self.netport = netport

		self.done_with_target = False
		endpoint = client.getEndpoint(twisted.internet.reactor,nethost,netport,self.timeout,bindAddress=None,socksHost = sockshost,socksPort = socksport)
		if sockshost != None:
			pass #DBGOUT#self.logger.debug("Starting connection %s %i via socks %s %i",nethost,netport,sockshost,socksport)
		else:
			pass #DBGOUT#self.logger.debug("Starting connection %s %i direct",nethost,netport)
		clientProt = client.clientProtocol(self.post_client_completion_callback,None,self.timeout,logCallback = self.log_traffic_callback)
		clientProt.openConnection(endpoint)

	def start_new_target(self):
		if self.shutdown_flag == True or len(self.post_targets_list) == 0:
			self.end_posting_message()
			return

		self.post_target = self.post_targets_list.pop(0)
		postTargetL = self.post_target.lower()
		if postTargetL == 'entangled' or postTargetL[0:8] == 'embargo:':
			self.post_servers = self.entangled_server[7:].split(',') # skipping server=
		else:
			self.post_servers = self.post_target[7:].split(',') # skipping server=
		if len(self.post_servers) > 1:
			self.post_servers = re_order_servers(self.post_servers,self.use_exit_node,self.server_connection)
		self.command_pending = None
		#DBGOUT#print "start new server in start new target",self.post_servers
		self.start_new_server()

	def update_posting_list(self,block,posting_list):
		while block != "":
			line,rest = block.split("\n",1)
			lineL = line.lower()
			if lineL[0:9] != 'post-to: ':
				break
			block = rest
		new_list = ""
		for target in posting_list:
			new_list += "Post-To: " + target + "\n"
		result = new_list + block
		return result

	def end_posting_message(self):
		self.session_terminated = True
		#DBGOUT#print "All targets sent"
		#DBGOUT#print "Blocks to post"
		for key in self.post_blocks_dict.keys():
			line = key.encode("hex") + ": "
			for target in self.post_blocks_dict[key]:
				line += target + ";"
			#DBGOUT#print line
		#DBGOUT#print "Blocks posted"
		for key in self.posted_blocks_dict.keys():
			line = key.encode("hex") + ": "
			for target in self.posted_blocks_dict[key]:
				line += target + ";"
			#DBGOUT#print line
		#DBGOUT#print "Blocks NOT posted"
		for key in self.posted_blocks_dict.keys():
			line = key.encode("hex") + ": "
			targets_not_posted = self.post_blocks_dict[key].difference(self.posted_blocks_dict[key])
			for target in targets_not_posted:
				line += target + ";"
			#DBGOUT#print line

		for key in self.post_blocks_dict.keys():
			keyH = key.encode("hex")
			if key not in self.posted_blocks_dict:
				targets_not_posted = self.post_blocks_dict[key]
			else:
				targets_not_posted = self.post_blocks_dict[key].difference(self.posted_blocks_dict[key])
			if len(targets_not_posted) == 0: # all are posted
				#DBGOUT#print "Deleting key " + keyH
				self.outbox_store.__delitem__(keyH)
			elif targets_not_posted == self.post_blocks_dict[key]: # none are posted
				pass
				#DBGOUT#print "Leaving key " + keyH + " unchanged"
			else:
				#DBGOUT#print "Rewriting key " + keyH
				found,block = self.outbox_store.retrieve(keyH)
				if found == False:
					continue # should not happen
				block = self.update_posting_list(block,targets_not_posted)
				self.outbox_store.store(keyH,block)
				#for line in block.split("\n"):
				#	if line[0:6].lower() == "data: ":
				#		break
				#	print line
				#print ""
				
		self.completion_callback(self.error_messages)

	def start_post_message(self,callback,validate_cert_callback,status_callback):
		self.update_timestamp()
		self.completion_callback = callback
		self.validate_cert_callback = validate_cert_callback
		self.status_callback = status_callback
		self.session_terminated = False
		self.posted_blocks_dict = { }
		self.generate_posting_list()
		self.error_messages = [ ]
		self.proxy_servers = [ ]
		#DBGOUT#print "start post message",self.post_targets_list
		self.start_new_target()

	def set_throttle(self,throttle_kbps):
		self.throttle_kbps = throttle_kbps

	def shutdown(self):
		self.shutdown_flag = True			


# EOF
