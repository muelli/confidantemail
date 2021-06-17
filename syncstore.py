# Sync store is a flat store with a running log for folder operations

import os
import os.path
import re
import struct
import pickle
import global_config
import flatstore
import gc
import time

class syncstore(flatstore.flatstore):

	def __init__(self,root_path,write_log):
		flatstore.flatstore.__init__(self,root_path)
		self.logfilePath = root_path + os.sep + 'changelog.dat'
		self.logfileProcPath = root_path + os.sep + 'sendlog.dat'
		if write_log == True: # GUI side
			self.logfile = open(self.logfilePath,'ab')

	def addChange(self,change_record):
		log_entry = pickle.dumps(change_record,pickle.HIGHEST_PROTOCOL)
		entry_len = len(log_entry)
		log_header = struct.pack('I',entry_len)
		self.logfile.write(log_header + log_entry)

	def flush(self):
		self.logfile.flush()

	def addFlushChange(self,change_record):
		self.addChange(change_record)
		self.logfile.flush()

	def checkForSendlog(self):
		if os.path.exists(self.logfileProcPath) == False:
			return False
		filestat = os.stat(self.logfileProcPath)
		if filestat.st_size > 0:
			return True
		else:
			return False
			
	def rotateChangelog(self):	
		# Note: I cannot just rename the logfile here.
		# Windows thinks it's locked even after I close it. Not sure why.
		self.logfile.close()
		readlog = open(self.logfilePath,'rb')
		writelog = open(self.logfileProcPath,'wb')
		while True:
			copybuf = readlog.read(262144)
			if len(copybuf) == 0:
				break
			writelog.write(copybuf)
		readlog.close()
		writelog.close()
		self.logfile = open(self.logfilePath,'wb')
		self.logfile.truncate(0)
		
	def getSendList(self):
		numRecs = 0
		sendFiles = [ ]
		self.readlogfile = open(self.logfileProcPath,'rb')
		while True:
			len_buf = self.readlogfile.read(4)
			if len(len_buf) < 4:
				break
			record_len, = struct.unpack('I',len_buf)
			record_buf = self.readlogfile.read(record_len)
			if len(record_buf) < record_len:
				break
			record = pickle.loads(record_buf)
			numRecs += 1
			if record[0] == 'SaveDraft' or record[0] == 'SendMsg':
				sendFiles.append(record[1])
		self.readlogfile.close()
		return numRecs,sendFiles

	def clearSendList(self):
		numRecs,sendFiles = self.getSendList()
		for fn in sendFiles:
			delpath = self.root_path + os.sep + (fn.encode('hex').upper())
			if os.path.isfile(delpath):
				os.unlink(delpath)
		procfile = open(self.logfileProcPath,'wb')
		procfile.truncate(0)
		procfile.close()
	
	def close(self):
		self.logfile.close()
		self.logfile = None

# EOF
