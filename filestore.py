# Tree file store with update logic

import os
import os.path
import re
import logging
import global_config
from entangled import kademlia
import cPickle as pickle

class filestore(kademlia.datastore.DataStore):

	def __init__(self,root_path):
		self.root_path = root_path
		self.logger = logging.getLogger(__name__)
		# Bushiness of the tree
		self.l1 = 0
		self.l2 = 2
		self.l3 = 2
		self.l4 = 4
		self.nonhexreg = re.compile("[^0123456789abcdefABCDEF]")
		if os.path.exists(self.root_path) == False:
			raise IOError('Filestore root path not found')
		self.logger.debug('Filestore opened with root path %s',self.root_path)

	def getPath(self,key,makedirs = True):
		path1 = self.root_path + os.sep + (key[self.l1:self.l2].upper())
		if os.path.exists(path1) == False and makedirs == True:
			os.mkdir(path1)
		path2 = path1 + os.sep + (key[self.l3:self.l4].upper())
		if os.path.exists(path2) == False and makedirs == True:
			os.mkdir(path2)
		filepath = path2 + os.sep + (key.upper())
		return filepath
	
	def getLockfile(self,key,makedirs = True):
		path1 = self.root_path + os.sep + (key[self.l1:self.l2].upper())
		if os.path.exists(path1) == False and makedirs == True:
			os.mkdir(path1)
		path2 = path1 + os.sep + (key[self.l3:self.l4].upper())
		if os.path.exists(path2) == False and makedirs == True:
			os.mkdir(path2)
		filepath = path2 + os.sep + 'LOCKFILE'
		return filepath
	
	def store(self,key,data):
		key = re.sub(self.nonhexreg,"",key.upper())
		self.logger.debug('Filestore store key %s',key)
		filepath = self.getPath(key)
		filehandle = open(filepath,'wb')
		filehandle.write(data)
		filehandle.close()
	
	def storeList(self,key,data):
		key = re.sub(self.nonhexreg,"",key.upper())
		self.logger.debug('Filestore store key %s',key)
		filepath = self.getPath(key)
		filehandle = open(filepath,'wb')
		for line in data:
			filehandle.write(line + '\n')
		filehandle.close()
	
	def retrieve(self,key):
		key = re.sub(self.nonhexreg,"",key.upper())
		self.logger.debug('Filestore retrieve key %s',key)
		filepath = self.getPath(key,False)
		try:
			self.logger.debug("File name: " + filepath)
			filehandle = open(filepath,'rb')
			data = filehandle.read()
			filehandle.close()
		except IOError:
			return False,None
		return True,data

	def retrieveHeaders(self,key):
		key = re.sub(self.nonhexreg,"",key.upper())
		self.logger.debug('Filestore retrieve key %s headers',key)
		filepath = self.getPath(key,False)
		try:
			self.logger.debug("File name: " + filepath)
			filehandle = open(filepath,'rb')
			data = [ ]
			for line in filehandle:
				line = line.rstrip('\r\n')
				data.append(line)
				if line[0:6] == 'Data: ': break
			filehandle.close()
		except IOError:
			return False,None
		return True,data

	def retrieveHeadersEntangled(self,key): # skip first data if Entangled - used by storutil
		skipData = False
		key = re.sub(self.nonhexreg,"",key.upper())
		self.logger.debug('Filestore retrieve key %s headers',key)
		filepath = self.getPath(key,False)
		try:
			self.logger.debug("File name: " + filepath)
			filehandle = open(filepath,'rb')
			data = [ ]
			for line in filehandle:
				line = line.rstrip('\r\n')
				data.append(line)
				if line == 'Source: entangled':
					skipData = True
				if line[0:6] == 'Data: ':
					if skipData == True:
						skipData = False
						data.pop()
						continue
					else:
						break
			filehandle.close()
		except IOError:
			return False,None
		return True,data

	def exists(self,key):
		key = re.sub(self.nonhexreg,"",key.upper())
		self.logger.debug('Filestore check-exists key %s',key)
		filepath = self.getPath(key,False)
		try:
			result = os.path.exists(filepath)
		except IOError:
			return False
		return result

	# entangled compatible functions
	# Interface for classes implementing physical storage (for data
	# published via the "STORE" RPC) for the Kademlia DHT
	# @note: This provides an interface for a dict-like object
	def keys(self):
		""" Return a list of the keys in this data store """
		self.logger.debug('Filestore keys() called')
		keylist = [ ]
		for l1 in os.listdir(self.root_path):
			l1path = self.root_path + os.sep + l1
			if os.path.isdir(l1path):
				for l2 in os.listdir(l1path):
					l2path = l1path + os.sep + l2
					for l3 in os.listdir(l2path):
						if l3 == 'LOCKFILE':
							continue
						l3path = l2path + os.sep + l3
						if os.path.isfile(l3path) and len(l3) == 40:
							keylist.append(l3.decode('hex'))
		return keylist

	def lastPublished(self, key):
		""" Get the time the C{(key, value)} pair identified by C{key}
		was last published """
		found,data = self.retrieveHeaders(key.encode("hex"))
		if found == False: raise KeyError,key
		for line in data:
			line = line.rstrip('\r\n')
			if line[0:15] == 'LastPublished: ':
				return long(line[15:])
		raise KeyError,key

	def originalPublisherID(self, key):
		""" Get the original publisher of the data's node ID

		@param key: The key that identifies the stored data
		@type key: str

		@return: Return the node ID of the original publisher of the
		C{(key, value)} pair identified by C{key}.
		"""
		found,data = self.retrieveHeaders(key.encode("hex"))
		if found == False: raise KeyError,key
		for line in data:
			line = line.rstrip('\r\n')
			if line[0:21] == 'OriginalPublisherID: ':
				return line[21:].decode("hex")
		raise KeyError,key

	def originalPublishTime(self, key):
		""" Get the time the C{(key, value)} pair identified by C{key}
		was originally published """
		found,data = self.retrieveHeaders(key.encode("hex"))
		if found == False: raise KeyError,key
		for line in data:
			line = line.rstrip('\r\n')
			if line[0:21] == 'OriginallyPublished: ':
				return long(line[21:])
		raise KeyError,key

	def setItem(self, key, value, lastPublished, originallyPublished, originalPublisherID):
		""" Set the value of the (key, value) pair identified by C{key};
		this should set the "last published" value for the (key, value)
		pair to the current time
		"""
		outstr = "Source: entangled\n" + \
			"LastPublished: " + str(lastPublished) + "\n" + \
			"OriginallyPublished: " + str(originallyPublished) + "\n" + \
			"OriginalPublisherID: " + originalPublisherID.encode("hex") + "\n"
		if type(value) == str:
			outstr += "DataType: string\n" + \
				"Data: " + str(len(value)) + "\n" + value
				
		else:
			datastr = pickle.dumps(value, pickle.HIGHEST_PROTOCOL)
			outstr += "DataType: pickle\n" + \
				"Data: " + str(len(datastr)) + "\n" + datastr
		self.store(key.encode("hex"),outstr)

	def __getitem__(self, key):
		""" Get the value identified by C{key} """
		keyh = key.encode("hex").upper()
		self.logger.debug('Filestore getitem key %s',keyh)
		filepath = self.getPath(keyh,False)
		pickled = False
		try:
			self.logger.debug("File name: " + filepath)
			filehandle = open(filepath,'rb')
			data = [ ]
			while True:
				line = filehandle.readline()
				if not line: break
				if line[0:16] == 'DataType: pickle':
					pickled = True
				if line[0:6] == 'Data: ': break
			data = filehandle.read()
			if pickled:
				data = pickle.loads(data)
			filehandle.close()
		except IOError:
			raise KeyError,key
		return data

	def __setitem__(self, key, value):
		""" Convenience wrapper to C{setItem}; this accepts a tuple in the
		format: (value, lastPublished, originallyPublished, originalPublisherID) """
		self.setItem(key, *value)

	def __delitem__(self, key):
		""" Delete the specified key (and its value) """
		pass # not going to do deletes

# EOF
