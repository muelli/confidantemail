# Flat file store for working queues and the like

import os
import os.path
import re
import logging
import pickle
import global_config

re_datetime = re.compile("^DATE: (\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ)$",re.IGNORECASE)

class flatstore:

	def __init__(self,root_path):
		self.root_path = root_path
		self.logger = logging.getLogger(__name__)
		self.nonhexreg = re.compile("[^0123456789abcdefABCDEF]")
		if os.path.exists(self.root_path) == False:
			raise IOError('Flatstore root path not found')
		self.logger.debug('Flatstore opened with root path %s',self.root_path)

	def getPath(self,key):
		key = re.sub(self.nonhexreg,"",key.upper())
		self.logger.debug('Flatstore store key %s',key)
		filepath = self.root_path + os.sep + (key.upper())
		return filepath
	
	def store(self,key,data):
		key = re.sub(self.nonhexreg,"",key.upper())
		self.logger.debug('Flatstore store key %s',key)
		filepath = self.root_path + os.sep + (key.upper())
		filehandle = open(filepath,'wb')
		filehandle.write(data)
		filehandle.close()
	
	def storePickle(self,key,data):
		key = re.sub(self.nonhexreg,"",key.upper())
		self.logger.debug('Flatstore store pickle key %s',key)
		filepath = self.root_path + os.sep + (key.upper())
		filehandle = open(filepath,'wb')
		pickle.dump(data,filehandle,pickle.HIGHEST_PROTOCOL)
		filehandle.close()
	
	def storeList(self,key,data):
		key = re.sub(self.nonhexreg,"",key.upper())
		self.logger.debug('Flatstore store key %s',key)
		filepath = self.root_path + os.sep + (key.upper())
		filehandle = open(filepath,'wb')
		for line in data:
			filehandle.write(line + '\n')
		filehandle.close()
	
	def retrieve(self,key):
		key = re.sub(self.nonhexreg,"",key.upper())
		self.logger.debug('Flatstore retrieve key %s',key)
		filepath = self.root_path + os.sep + (key.upper())
		try:
			self.logger.debug("File name: " + filepath)
			filehandle = open(filepath,'rb')
			data = filehandle.read()
			filehandle.close()
		except IOError:
			return False,None
		return True,data

	def retrievePickle(self,key):
		key = re.sub(self.nonhexreg,"",key.upper())
		self.logger.debug('Flatstore retrieve pickle key %s',key)
		filepath = self.root_path + os.sep + (key.upper())
		try:
			self.logger.debug("File name: " + filepath)
			filehandle = open(filepath,'rb')
			data = pickle.load(filehandle)
			filehandle.close()
		except IOError:
			return False,None
		return True,data

	def retrieveHeaders(self,key):
		key = re.sub(self.nonhexreg,"",key.upper())
		self.logger.debug('Flatstore retrieve key %s headers',key)
		filepath = self.root_path + os.sep + (key.upper())
		try:
			self.logger.debug("File name: " + filepath)
			filehandle = open(filepath,'rb')
			data = [ ]
			for line in filehandle:
				line = line.rstrip('\r\n').rstrip('\r')
				lineL = line.lower()
				data.append(line)
				if lineL[0:6] == 'data: ': break
			filehandle.close()
		except IOError:
			return False,None
		return True,data

	def exists(self,key):
		key = re.sub(self.nonhexreg,"",key.upper())
		self.logger.debug('Flatstore check-exists key %s',key)
		filepath = self.root_path + os.sep + (key.upper())
		try:
			result = os.path.exists(filepath)
		except IOError:
			return False
		return result

	def keys(self):
		""" Return a list of the keys in this data store """
		self.logger.debug('Flatstore keys() called')
		keylist = [ ]
		for l1 in os.listdir(self.root_path):
			l1path = self.root_path + os.sep + l1
			if os.path.isfile(l1path) and len(l1) == 40:
				keylist.append(l1.decode('hex'))
		return keylist

	def sort_compare_date(self,a,b):
		if a[1] < b[1]:
			return -1
		elif a[1] == b[1]:
			return 0
		else:
			return 1

	def keys_by_date(self):
		""" Return a list of the keys in this data store, sorted by the date field """
		self.logger.debug('Flatstore keys_by_date() called')
		keylist = [ ]
		ktlist = [ ]
		for key in self.keys():
			found,headers = self.retrieveHeaders(key.encode('hex'))
			if found == False:
				continue
			m = None
			for hdr in headers:
				m = re_datetime.match(hdr)
				if m:
					kd = key,m.group(1)
					ktlist.append(kd)
					break	
			if m == None:
				kd = key,'0000'
				ktlist.append(kd)
		ktlist.sort(self.sort_compare_date)
		for key,tuple in ktlist:
			keylist.append(key)
		return keylist

	def __delitem__(self, key):
		""" Delete the specified key (and its value) """
		key = re.sub(self.nonhexreg,"",key.upper())
		self.logger.debug('Flatstore delete key %s',key)
		filepath = self.root_path + os.sep + (key.upper())
		if os.path.isfile(filepath):
			os.unlink(filepath)

# EOF
