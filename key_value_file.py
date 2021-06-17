import sys
import os
import re
import global_config
import anydbm
import struct
import pickle
import hashlib

# Logging will be added to this

re_logfile = re.compile("^log.([0-9]{7})$",re.IGNORECASE)
max_log_len = (1024*16)

# Return current log file if it has an end mark, else return next log file, and log to replay
def next_log_number(log_path):
	commit_number = 0	
	extend_file = False
	replay_log = None
	log_num = -1
	for fn in os.listdir(log_path):
		m = re_logfile.match(fn)
		if m:
			n = int(m.group(1))
			if n > log_num:
				log_num = n
	if log_num == -1:
		return log_path + os.sep + 'log.0000000',commit_number,extend_file,replay_log
	log_file = log_path + os.sep + ('log.%07i' % log_num)
	fh = open(log_file,'rb')
	fh.seek(0,os.SEEK_END)
	flen = fh.tell()
	log_num += 1 # assume using next log
	if (flen >= 28) and (flen < max_log_len):
		fh.seek(-28,os.SEEK_CUR)
		buf = fh.read(28)
		hasher = hashlib.new('sha1')
		hasher.update(buf[0:8])
		log_hash = hasher.digest()
		#DBGOUT#print "flen buf",flen,len(buf)
		if (len(buf) == 28) and (log_hash == buf[8:]):
			log_num -= 1 # using existing log
			commit_number, = struct.unpack('I',buf[0:4])
			commit_number += 1
			extend_file = True
		else:
			replay_log = log_file
	fh.close()
	log_file = log_path + os.sep + ('log.%07i' % log_num)
	#DBGOUT#print "log = ",log_file, "commit = ",commit_number
	return log_file,commit_number,extend_file,replay_log
		
def replay_log_entry(dbmfile,entry_str):
	change_list = pickle.loads(entry_str)
	for key,value in change_list:
		if value == None and key in dbmfile:
			del dbmfile[key]
		else:
			dbmfile[key] = value
	return len(change_list)

def replay_log_file(file_path,log_file_name,output_command = None):
	dbmfile = anydbm.open(file_path,'c')
	logfile = open(log_file_name,'rb')
	last_commit_number = -1
	commit_number = -1
	num_changes = 0
	num_tx = 0
	num_seeks = 0
	max_print_seeks = 100
	while True:
		file_pos = logfile.tell()
		header_buf = logfile.read(8)
		if len(header_buf) < 8:
			break
		
		last_commit_number = commit_number
		commit_number,entry_len = struct.unpack('II',header_buf)
		if entry_len > 67108864 or entry_len < 0: # size limit
			data_buf = ''
		else:
			data_buf = logfile.read(entry_len)
		if len(data_buf) < entry_len:
			file_pos += 1
			logfile.seek(file_pos)
			num_seeks += 1
			if (output_command != None) and (num_seeks <= max_print_seeks):
				output_command("data_buf read overflow, seeking +1")
			continue
		saved_hash = logfile.read(20)
		if len(saved_hash) < 20:
			file_pos += 1
			logfile.seek(file_pos)
			num_seeks += 1
			if (output_command != None) and (num_seeks <= max_print_seeks):
				output_command("saved_hash read overflow, seeking +1")
			continue
		hasher = hashlib.new('sha1')
		hasher.update(header_buf)
		hasher.update(data_buf)
		check_hash = hasher.digest()
		#DBGOUT#print 'num=',commit_number,'len=',entry_len
		#DBGOUT#print '   saved hash=',saved_hash.encode('hex')
		#DBGOUT#print '   check hash=',check_hash.encode('hex')
		if entry_len > 0:
			if saved_hash == check_hash:
				num_changes += replay_log_entry(dbmfile,data_buf)	
				num_tx += 1
			else:
				file_pos += 1
				logfile.seek(file_pos)
				num_seeks += 1
				if (output_command != None) and (num_seeks <= max_print_seeks):
					output_command("hash mismatch at num="+str(commit_number)+" moving to "+str(file_pos))
	logfile.close()
	dbmfile.close()
	return num_tx,num_changes
	
class key_value_file:
	def __init__(self,file_path,log_path):
		self.file_path = file_path
		self.log_file_name,self.commit_number,extend_file,replay_log = next_log_number(log_path)
		if replay_log != None:
			replay_log_file(file_path,replay_log)
		if extend_file == True:
			self.logfile = open(self.log_file_name,'ab')
		else:
			self.logfile = open(self.log_file_name,'wb')
		self.pending_changes = [ ]
		self.pending_cache = dict()
		self.dbmfile = anydbm.open(file_path,'c')

	def __del__(self):
		if self.dbmfile != None:
			#DBGOUT#print "key value file closed at exit"
			self.dbmfile.close()
			self.logfile.close()

	def close(self):
		#DBGOUT#print "key value file closed explicitly"
		self.commit()
		log_header = struct.pack('II',self.commit_number,0) # close marker
		hasher = hashlib.new('sha1')
		hasher.update(log_header)
		log_hash = hasher.digest()
		self.logfile.write(log_header + log_hash)
		self.logfile.flush()
		self.dbmfile.close()
		self.logfile.close()
		self.dbmfile = None
		self.logfile = None

	def commit(self):
		#DBGOUT#print "commit"
		if len(self.pending_changes) == 0:
			return
		log_entry = pickle.dumps(self.pending_changes,pickle.HIGHEST_PROTOCOL)
		entry_len = len(log_entry)
		log_header = struct.pack('II',self.commit_number,entry_len)
		hasher = hashlib.new('sha1')
		hasher.update(log_header)
		hasher.update(log_entry)
		log_hash = hasher.digest()
		self.logfile.write(log_header + log_entry + log_hash)
		self.logfile.flush()
		for key,value in self.pending_changes:
			if value == None and key in self.dbmfile:
				del self.dbmfile[key]
			else:
				self.dbmfile[key] = value
		self.dbmfile.sync()
		self.commit_number += 1
		self.pending_changes = [ ]
		self.pending_cache = dict()
	
	def set(self,key,value):
		#DBGOUT#print "key value: set",key,key.encode('hex')," -> ",value.encode('hex')
		self.pending_changes.append( (key,value) )
		self.pending_cache[key] = value

	def get(self,key):
		if key in self.pending_cache:
			cached_entry = self.pending_cache[key]
			if cached_entry == None:
				return False,None
			else:
				return True,cached_entry
		elif key in self.dbmfile:
			return True,self.dbmfile[key]
		else:
			return False,None

	def exists(self,key):
		if key in self.pending_cache:
			if self.pending_cache[key] == None:
				return False
			else:
				return True
		elif key in self.dbmfile:
			return True
		else:
			return False

	def delete(self,key):
		if self.exists(key) == True:
			self.pending_changes.append( (key,None) )
		self.pending_cache[key] = None

	def pickle(self,key,value):
		#DBGOUT#print "key value: pickle",key,key.encode('hex')," -> ",value
		self.set(key,pickle.dumps(value,pickle.HIGHEST_PROTOCOL))

	def unpickle(self,key):
		found,value = self.get(key)
		if found == True:
			return True,pickle.loads(value)
		else:
			return False,None

#DBGOUT#if __name__ == "__main__":
	#DBGOUT#print "dbm file = " + sys.argv[1]," log file = ",sys.argv[2]
	#DBGOUT#replay_log_file(sys.argv[1],sys.argv[2])


# EOF
