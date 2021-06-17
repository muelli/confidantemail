# Cross-platform basic whole file locking - why doesn't Python include this?

import sys

if sys.platform == 'win32':
	is_windows = True
	import msvcrt
else:
	is_windows = False
	import fcntl

class filelock:
	def __init__(self,filename,create = True):
		self.filename = filename
		if create == True:
			self.filehandle = open(filename,"a")
		else:
			self.filehandle = open(filename,"r")
		self.filedesc = self.filehandle.fileno()
		self.is_locked = False

	def lock_wait(self):
		if is_windows == True:
			while True:
				try:
					res = msvcrt.locking(self.filedesc,msvcrt.LK_LOCK,16)
					self.is_locked = True
					break
				except IOError:
					pass
		else:
			fcntl.lockf(self.filedesc,fcntl.LOCK_EX)
			self.is_locked = True

	def lock_nowait(self):
		if is_windows == True:
			try:
				res = msvcrt.locking(self.filedesc,msvcrt.LK_NBLCK,16)
				self.is_locked = True
			except IOError:
				pass
			return self.is_locked
		else:
			try:
				fcntl.lockf(self.filedesc,fcntl.LOCK_EX|fcntl.LOCK_NB)
				self.is_locked = True
			except IOError:
				pass
			return self.is_locked
	
	def unlock(self):
		if is_windows == True:
			if self.is_locked == True:
				msvcrt.locking(self.filedesc,msvcrt.LK_UNLCK,16)
				self.is_locked = False
		else:
			if self.is_locked == True:
				fcntl.lockf(self.filedesc,fcntl.LOCK_UN)
				self.is_locked = False

	def unlock_close(self):
		self.unlock()
		if self.filehandle != None:
			self.filehandle.close()
			self.filehandle = None

	def __del__(self):
		self.unlock_close()
				
#OFF#import sys
#OFF#import time
#OFF#print "opening"
#OFF#fl = filelock("test.dat",True)
#OFF#print "locking file"
#OFF#fl.lock_wait()
#OFF##print fl.lock_nowait()
#OFF#print "file locked, press enter"
#OFF#sys.stdin.readline()
#OFF#print "unlocking file"
#OFF#fl.unlock()
#OFF#time.sleep(3)

# EOF
