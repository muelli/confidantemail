import hashlib
import hmac
import datetime
import time
import os


class bypass_token:
	def __init__(self,token_file_path,get_random):
		self.token_file_path = token_file_path
		self.get_random = get_random

	def open_create_write_file(self):
		if os.path.isfile(self.token_file_path) == False:
			fh = open(self.token_file_path,'w')
			fh.write("# in/out,keyid,tokenhash,create_time,expire_time\n")
		else:
			fh = open(self.token_file_path,'a')
		return fh

	def get_outgoing_token(self,keyid,earliest_date):
		keyid_in = keyid.lower()
		result = None
	 	is_new = False
		now_time = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
		if os.path.isfile(self.token_file_path):
			fh = open(self.token_file_path,'r')
			for line in fh:
				line = line.rstrip('\r\n')
				inout,keyid,token_hash,create_time,expire_time = line.split(',')
				if inout == 'out' and keyid_in == keyid and \
				create_time >= earliest_date and \
				( expire_time == 'never' or expire_time > now_time ):
					result = token_hash + ',' + create_time + ',' + expire_time
			fh.close()
		if result == None:
			token_hash = self.get_random(20,keyid_in).encode('hex').lower()
			result = token_hash + ',' + now_time + ',never'
			fh = self.open_create_write_file()
			fh.write('out,' + keyid_in + ',' + result + "\n")
			fh.close()
			is_new = True
		return is_new,result

	def add_incoming_or_replicated_token(self,keyid,token,create_time,expire_time,inout_in = 'in'):
		keyid_in = keyid.lower()
		token_in = token.lower()
		match = False
		if os.path.isfile(self.token_file_path):
			fh = open(self.token_file_path,'r')
			for line in fh:
				line = line.rstrip('\r\n')
				inout,keyid,token_hash,create_time,expire_time = line.split(',')
				if inout == inout_in and keyid_in == keyid and token_in == token:
					match = True
			fh.close()
		if match == False:
			fh = self.open_create_write_file()
			fh.write(inout_in + ',' + keyid_in + ',' + token_in + ',' + create_time + ',' + expire_time + "\n")
			fh.close()

	def get_earliest_time(self):
		earliest_time = None
		if os.path.isfile(self.token_file_path) == True:
			fh = open(self.token_file_path,'r')
			for line in fh:
				line = line.rstrip('\r\n')
				inout,keyid,token_hash,create_time,expire_time = line.split(',')
				if inout == 'out' and \
				( earliest_time == None or earliest_time > create_time):
					earliest_time = create_time
			fh.close()
		if earliest_time == None:
			earliest_time = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
		return earliest_time

	def generate_bypass_hash(self,keyid,hashdata):
		keyid_in = keyid.lower()
		if os.path.isfile(self.token_file_path) == False:
			return None
		now_time = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
		chosen_hash = None
		chosen_time = None
		fh = open(self.token_file_path,'r')
		for line in fh:
			line = line.rstrip('\r\n')
			inout,keyid,token_hash,create_time,expire_time = line.split(',')
			if inout == 'in' and keyid_in == keyid and \
			create_time <= now_time and \
			( expire_time == 'never' or expire_time > now_time ) and \
			( chosen_time == None or chosen_time < create_time):
				chosen_time = create_time
				chosen_hash = token_hash		
		fh.close()
		if chosen_hash == None:
			return None
		else:
			return hmac.new(chosen_hash.decode('hex'),hashdata,hashlib.sha1).hexdigest().lower()

	def verify_bypass_hash(self,hashval,hashdata):
		if os.path.isfile(self.token_file_path) == False:
			return None
		hashval = hashval.lower()
		fh = open(self.token_file_path,'r')
		match = None
		now_time = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
		for line in fh:
			line = line.rstrip('\r\n')
			inout,keyid,token_hash,create_time,expire_time = line.split(',')
			if inout == 'out' and create_time <= now_time and \
			( expire_time == 'never' or expire_time > now_time ):
				testhash = hmac.new(token_hash.decode('hex'),hashdata,hashlib.sha1).hexdigest().lower()
				if testhash == hashval:
					match = keyid
		fh.close()
		return match

# EOF
