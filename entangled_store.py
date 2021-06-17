import hashlib
import re
import filestore
import pickle

class entangled_store(filestore.filestore):
	
	def finish_init(self,inputstore,storethread,valmerge):
		self.inputstore = inputstore
		self.storethread = storethread
		self.valmerge = valmerge

	def setItem(self, key, value, lastPublished, originallyPublished, originalPublisherID):
		""" Set the value of the (key, value) pair identified by C{key};
		this should set the "last published" value for the (key, value)
		pair to the current time
		"""
		if type(value) != str:
			return filestore.filestore.setItem(self, key, value, lastPublished, originallyPublished, originalPublisherID) # nodeState value

		keyH = key.encode('hex')
		outstr = "StoreType: entangled-incoming\nStoreKeyid: " + keyH + "\n" + \
			"Source: entangled\n" + \
			"LastPublished: " + str(lastPublished) + "\n" + \
			"OriginallyPublished: " + str(originallyPublished) + "\n" + \
			"OriginalPublisherID: " + originalPublisherID.encode("hex") + "\n"
		outstr += "DataType: string\n" + \
			"Data: " + str(len(value)) + "\n" + value
		hasher = hashlib.new('sha1')
		hasher.update(outstr)
		temphash = hasher.digest().encode('hex')	
		if not self.inputstore.exists(temphash):
			self.inputstore.store(temphash,outstr)
			self.storethread.submitKey(temphash)

	def realSetItem(self, key, value, lastPublished, originallyPublished, originalPublisherID):
		filestore.setItem(self, key, value, lastPublished, originallyPublished, originalPublisherID)

# EOF
