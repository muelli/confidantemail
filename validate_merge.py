# "\Program Files (x86)\GNU\GnuPG\gpg.exe" --homedir c:\projects\confidantmail\clients\client1\gpg --list-keys --with-key-data 6ce255b3

import gnupg
import keyannounce
import global_config
import datetime
import logging
import re
import hashlib
import proofofwork

re_datetime = re.compile("^DATE: (\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ)$",re.IGNORECASE)
re_data = re.compile("^DATA: ([1-9][0-9]*)$",re.IGNORECASE)
re_pow = re.compile("^PROOFOFWORK: (bd,[0-9a-f]+(,[0-9a-f]+)+)$",re.IGNORECASE)
re_type = re.compile("^TYPE: (.+)$",re.IGNORECASE)
re_mh = re.compile("^MESSAGEHASH: ([0123456789abcdef]{40})$",re.IGNORECASE)
re_hash = re.compile("^HASH: ([0123456789abcdef]{40})$",re.IGNORECASE)
re_keyid = re.compile("^KEYID: ([0123456789abcdef]{40})$",re.IGNORECASE)
re_db = re.compile("^DATABLOCK: ([0123456789abcdef]{40})$",re.IGNORECASE)
re_rec = re.compile("^RECIPIENT: ([0123456789abcdef]{40})$",re.IGNORECASE)
re_mbx = re.compile("^MAILBOX: (\S+)$",re.IGNORECASE)
re_address = re.compile("^ADDRESS: (\S+)$",re.IGNORECASE)

class validate_merge:

	def __init__(self,gnupg,pgpkey = None,max_age_key_server = None,max_age_data_server = None,max_age_message_server = None,max_age_ack_server = None,max_age_claim_server = None):
		self.gnupg = gnupg
		self.logger = logging.getLogger(__name__)
		if pgpkey != None:
			self.pgpkey = pgpkey
		else:
			self.pgpkey = keyannounce.keyannounce(gnupg,None,None,None,False,False,False,False,'Direct',None)
		self.check_key_sigs = True
		self.update_current_datetime()

		if max_age_key_server == None:
			self.max_age_key_server = global_config.max_age_key
		else:
			self.max_age_key_server = max_age_key_server
		if max_age_data_server == None:
			self.max_age_data_server = global_config.max_age_data
		else:
			self.max_age_data_server = max_age_data_server
		if max_age_message_server == None:
			self.max_age_message_server = global_config.max_age_message
		else:
			self.max_age_message_server = max_age_message_server
		if max_age_ack_server == None:
			self.max_age_ack_server = global_config.max_age_ack
		else:
			self.max_age_ack_server = max_age_ack_server
		if max_age_claim_server == None:
			self.max_age_claim_server = global_config.max_age_claim
		else:
			self.max_age_claim_server = max_age_claim_server

	def update_current_datetime(self):
		self.current_datetime = datetime.datetime.utcnow()
	
	def extract_headers_data(self,block):
		lines = [ ]
		type = None
		date = None
		age = None
		pow = None
		data = None
		skip_blanks = True
		if block != None:
			for line in block.split('\n'):
				line = line.replace('\r','')
				if line == "-----BEGIN PGP SIGNED MESSAGE-----":
					skip_blanks = False # do not delete blank lines in signed message, or signature will fail
				if skip_blanks == True and line == "":
					continue
				lines.append(line)

				match = re_pow.match(line)
				if match:
					pow = match.group(1)
					continue

				match = re_datetime.match(line)
				if match and date == None:
					date = match.group(1)
					posting_datetime = datetime.datetime.strptime(date,"%Y-%m-%dT%H:%M:%SZ")
					age = self.current_datetime - posting_datetime
					continue

				match = re_type.match(line)
				if match and type == None:
					type = match.group(1)
					continue

				match = re_data.match(line)
				if match:
					ndata = int(match.group(1))
					dofs = len(block) - ndata
					if dofs > 0:
						data = block[dofs:]
					break

		return lines,type,date,age,pow,data

	def validate_message_announcement(self,key,lines,is_entangled,pow_nbits_req = None,pow_nmatches_req = None,ignore_expire = False):
		powblock = ""
		date = ""
		posting_datetime = ""
		pow = ""
		type = ""
		dbs = ""
		rec = ""
		mh = ""
		mbx = ""
		age = None
		if pow_nbits_req == None:
			pow_nbits_req = global_config.pow_nbits_message_server
		if pow_nmatches_req == None:
			pow_nmatches_req = global_config.pow_nmatches_message_server
		if is_entangled == True:
			max_age_message = global_config.max_age_message
		else:
			max_age_message = self.max_age_message_server

		for line in lines:
			match = re_datetime.match(line)
			if match:
				date = match.group(1)
				posting_datetime = datetime.datetime.strptime(date,"%Y-%m-%dT%H:%M:%SZ")
				age = self.current_datetime - posting_datetime
				continue
			match = re_pow.match(line)
			if match:
				pow = match.group(1)
				continue
			match = re_type.match(line)
			if match:
				type = match.group(1)
				continue
			match = re_mh.match(line)
			if match:
				mh = match.group(1).decode("hex")
				continue
			match = re_db.match(line)
			if match:
				dbs += match.group(1).decode("hex")
				continue
			match = re_rec.match(line)
			if match:
				rec = match.group(1).decode("hex")
				continue
			match = re_mbx.match(line)
			if match:
				mbx = match.group(1)
				continue
		powblock = rec + mh + date + dbs
		pow_nbits,pow_nmatches = proofofwork.verify_proof_of_work(powblock,pow)
		if pow_nbits < pow_nbits_req or pow_nmatches < pow_nmatches_req:
			return False,posting_datetime,rec,"Message proof of work no good"
		hash = hashlib.new('sha1')
		hash.update(mbx + rec)
		postkey = hash.digest()
		if (key != None) and (postkey != key):
			return False,posting_datetime,rec,"Posting key hash invalid"
		if ((ignore_expire == False) and (age == None or age.total_seconds() > max_age_message)):
			return False,posting_datetime,rec,"Message expired"
		return True,posting_datetime,rec,None
		
	def validate_address_claim(self,key,lines,is_entangled,posting_userhash = None):
		powblock = ""
		date = ""
		posting_datetime = ""
		pow = ""
		type = ""
		keyid = ""
		keyidH = ""
		address = ""
		age = None
		if is_entangled == True:
			max_age_claim = global_config.max_age_claim
		else:
			max_age_claim = self.max_age_claim_server
		for line in lines:
			match = re_datetime.match(line)
			if match:
				date = match.group(1)
				posting_datetime = datetime.datetime.strptime(date,"%Y-%m-%dT%H:%M:%SZ")
				age = self.current_datetime - posting_datetime
				continue
			match = re_pow.match(line)
			if match:
				pow = match.group(1)
				continue
			match = re_type.match(line)
			if match:
				type = match.group(1)
				continue
			match = re_keyid.match(line)
			if match:
				keyidH = match.group(1)
				keyid = keyidH.decode("hex")
				continue
			match = re_address.match(line)
			if match:
				address = match.group(1)
				continue
		powblock = date + keyid + address
		pow_nbits,pow_nmatches = proofofwork.verify_proof_of_work(powblock,pow)
		if pow_nbits < global_config.pow_nbits_key or pow_nmatches < global_config.pow_nmatches_key:
			return False,posting_datetime,"Claim proof of work no good"
		hash = hashlib.new('sha1')
		hash.update(address)
		postkey = hash.digest()
		if postkey != key:
			return False,posting_datetime,"Claim posting key hash invalid"
		if age == None or age.total_seconds() > max_age_claim:
			return False,posting_datetime,"Claim expired"

		if posting_userhash != None and keyidH.lower() != posting_userhash.lower():
			return False,posting_datetime,"Key does not match logged in user hash"

		return True,posting_datetime,None
		
	def split_message_announcements(self,key,lines,is_entangled):
		announcements = { }
		dates = { }
		mh = None
		an = [ ]
		recip = None
		for line in lines:
			lineL = line.lower()
			if lineL == 'nextmessage':
				if mh != None:
					isgood,date,recip,reason = self.validate_message_announcement(key,an,is_entangled)
					if isgood == False:
						self.logger.debug("Message announcement " + key.encode("hex") + " bad: " + reason)
					else:
						announcements[mh] = an
						dates[mh] = date
					an = [ ]
					mh = None
				continue	
			match = re_mh.match(line)
			if match:
				mh = match.group(1).decode("hex")
			an.append(line)
		if mh != None:
			isgood,date,recip,reason = self.validate_message_announcement(key,an,is_entangled)
			if isgood == False:
				self.logger.debug("Message announcement " + key.encode("hex") + " bad: " + reason)
			else:
				announcements[mh] = an
				dates[mh] = date
		return announcements,dates,recip

	def split_address_claims(self,key,lines,is_entangled,posting_userhash = None):
		claims = { }
		dates = { }
		ki = None
		ac = [ ]
		for line in lines:
			lineL = line.lower()
			if lineL == 'nextclaim':
				if ki != None:
					isgood,date,reason = self.validate_address_claim(key,ac,is_entangled,posting_userhash)
					if isgood == False:
						self.logger.debug("Address claim " + key.encode("hex") + " bad: " + reason)
					else:
						claims[ki] = ac
						dates[ki] = date
					ac = [ ]
					ki = None
				continue	
			match = re_keyid.match(line)
			if match:
				ki = match.group(1).decode("hex")
			ac.append(line)
		if ki != None:
			isgood,date,reason = self.validate_address_claim(key,ac,is_entangled,posting_userhash)
			if isgood == False:
				self.logger.debug("Address claim " + key.encode("hex") + " bad: " + reason)
			else:
				claims[ki] = ac
				dates[ki] = date
		return claims,dates
		
	def validate_acknowledgment(self,key,lines,is_entangled):
		powblock = ""
		pow = ""
		date = ""
		type = ""
		hash = ""
		age = None
		if is_entangled == True:
			max_age_ack = global_config.max_age_ack
		else:
			max_age_ack = self.max_age_ack_server
		for line in lines:
			match = re_type.match(line)
			if match:
				type = match.group(1)
				continue
			match = re_hash.match(line)
			if match:
				hash = match.group(1).decode("hex")
				continue
			match = re_datetime.match(line)
			if match:
				date = match.group(1)
				posting_datetime = datetime.datetime.strptime(date,"%Y-%m-%dT%H:%M:%SZ")
				age = self.current_datetime - posting_datetime
				continue
			match = re_pow.match(line)
			if match:
				pow = match.group(1)
				continue

		powblock = date + hash
		pow_nbits,pow_nmatches = proofofwork.verify_proof_of_work(powblock,pow)
		if ((is_entangled == True and ( pow_nbits < global_config.pow_nbits_ack_entangled or pow_nmatches < global_config.pow_nmatches_ack_entangled)) or
			(is_entangled == False and ( pow_nbits < global_config.pow_nbits_ack_server or pow_nmatches < global_config.pow_nmatches_ack_server))):
			return False,"Acknowledgment proof of work no good"
		hasher = hashlib.new('sha1')
		hasher.update(hash)
		ack = hasher.digest()
		if ack != key:
			return False,"Acknowledgment hash invalid"
		if age == None or age.total_seconds() > max_age_ack:
			#DBGOUT#print "Expired:",age,age.total_seconds(),global_config.max_age_ack
			return False,"Acknowledgment expired"
		return True,None

	# Returns the data to save, or None if nothing should be saved
	# old_block can be None if this is a new key
	# Return is data-to-save,errmsg
	def validate_merge(self,key,old_block,new_block,is_entangled,posting_userhash = None):
		if is_entangled == True:
			max_age_key = global_config.max_age_key
			max_age_data = global_config.max_age_data
		else:
			max_age_key = self.max_age_key_server
			max_age_data = self.max_age_data_server
		self.update_current_datetime()
		keyH = key.encode("hex")

		if old_block != None and old_block == new_block:
			return None,None,"Block unchanged"

		old_lines,old_type,old_date,old_age,old_pow,old_data = self.extract_headers_data(old_block)
		new_lines,new_type,new_date,new_age,new_pow,new_data = self.extract_headers_data(new_block)

		if new_type == 'key-announcement':
			isValid,keyid,age,isexp,errmsg,status = self.pgpkey.verify_key_announcement_message(new_block,global_config.pow_nbits_key,global_config.pow_nmatches_key)
			#DBGOUT#print "returned age ",age,ageS,"new age",new_age,"old age",old_age
			keyid = keyid.lower()
			if old_type != None and old_type != new_type:
				return None,None,"Type mismatch"	
			if isValid != True:
				return None,None,"Key verification failed: " + errmsg
			ageS = age.total_seconds()
			self.gnupg.delete_keys(keyid,False) # prevent subkeys from accumulating
			if keyH.lower() != keyid.lower():
				return None,None,"Key does not match hash"
			if posting_userhash != None and keyH.lower() != posting_userhash.lower():
				return None,None,"Key does not match logged in user hash"
			if ageS >= max_age_key or isexp == True:
				return None,None,"Key expired"
			if old_type == None:
				return new_block,None,"New key"
			if age < old_age:
				return new_block,None,"Updated key"
			return None,None,"Key not newer"

		elif new_type == 'data':
			if new_data == None:
				return None,None,"No data"
			hash = hashlib.new('sha1')
			hash.update(new_data)
			expkey = hash.digest()
			if ((is_entangled == True and len(new_data) > global_config.max_blocksize_entangled) or
				(is_entangled == False and len(new_data) > global_config.max_blocksize_server)):
				return None,None,"Data block too long"
			if key != expkey:
				return None,None,"Data hash did not match key"
			if old_age != None and old_age <= new_age:
				return None,None,"Data not newer"
			if new_age.total_seconds() > max_age_data:
				return None,None,"Data block expired"
			pow_nbits,pow_nmatches = proofofwork.verify_proof_of_work(new_date + new_data,new_pow)
			if ((is_entangled == True and ( pow_nbits < global_config.pow_nbits_data_entangled or pow_nmatches < global_config.pow_nmatches_data_entangled)) or
				(is_entangled == False and ( pow_nbits < global_config.pow_nbits_data_server or pow_nmatches < global_config.pow_nmatches_data_server))):
				return None,None,"Proof of work invalid"
			return new_block,None,"Data block good"

		elif new_type == 'message-announcement':
			new_msgs,new_dates,new_recip = self.split_message_announcements(key,new_lines,is_entangled)
			old_msgs = { }
			done_msgs = { }
			outblock = ""
			first = True
			if new_type == old_type:
				old_msgs,old_dates,old_recip = self.split_message_announcements(key,old_lines,is_entangled)
			#DBGOUT#print "new_msgs",len(new_msgs)
			#DBGOUT#print "old_msgs",len(old_msgs)
			for msg in new_msgs.keys():
				if old_msgs == None or msg not in old_msgs or new_dates[msg] > old_dates[msg]:
					done_msgs[msg] = 1
					if first:
						first = False
					else:
						outblock += "NextMessage\n"
					for line in new_msgs[msg]:
						outblock += line + "\n"	
			for msg in old_msgs.keys():
				if msg not in done_msgs:
					if first:
						first = False
					else:
						outblock += "NextMessage\n"
					for line in old_msgs[msg]:
						outblock += line + "\n"	
			if outblock == "":
				return None,None,"No good messages"
			return outblock,new_recip,"Good messages"

		elif new_type == 'address-claim':
			new_claims,new_dates = self.split_address_claims(key,new_lines,is_entangled,posting_userhash)
			old_claims = { }
			done_claims = { }
			outblock = ""
			first = True
			if new_type == old_type:
				old_claims,old_dates = self.split_address_claims(key,old_lines,is_entangled)
			#DBGOUT#print "new_claims",len(new_claims)
			#DBGOUT#print "old_claims",len(old_claims)
			for claim in new_claims.keys():
				if old_claims == None or claim not in old_claims or new_dates[claim] > old_dates[claim]:
					done_claims[claim] = 1
					if first:
						first = False
					else:
						outblock += "NextClaim\n"
					for line in new_claims[claim]:
						outblock += line + "\n"	
			for claim in old_claims.keys():
				if claim not in done_claims:
					if first:
						first = False
					else:
						outblock += "NextClaim\n"
					for line in old_claims[claim]:
						outblock += line + "\n"	
			if outblock == "":
				return None,None,"No good claims"
			return outblock,None,"Good claims"

		elif new_type == 'acknowledgment' or new_type == 'acknowledgement':
			isValid,errmsg = self.validate_acknowledgment(key,new_lines,is_entangled)
			if isValid == False:
				return None,None,errmsg
			if old_age != None and old_age <= new_age:
				return None,None,"Acknowledgment not newer"
			return new_block,None,"Acknowledgment good"

		n = 0
		for l in new_lines:
			n += 1
			#DBGOUT#print n,l
		#DBGOUT#print "new_type",new_type
		#DBGOUT#print "new_date",new_date
		#DBGOUT#print "new_age",new_age
		#DBGOUT#print "new_pow",new_pow
		#DBGOUT#if new_data != None:
			#DBGOUT#print "new_data",len(new_data),new_data[0:64].encode("hex")
		return None,None,None	

# EOF
