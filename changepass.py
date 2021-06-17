import subprocess
import logging
import time
import sys
import os
import traceback
import global_config

# This is a pain to do and the gnupg extension does not include it!

# thank you http://eyalarubas.com/python-subproc-nonblock.html
from threading import Thread
from Queue import Queue, Empty

class NonBlockingStreamReader:

	def __init__(self, stream):
		'''
		stream: the stream to read from.
				Usually a process' stdout or stderr.
		'''
		self._s = stream
		self._q = Queue()

		def _populateQueue(stream, queue):
			'''
			Collect lines from 'stream' and put them in 'quque'.
			'''
			while True:
				line = stream.readline()
				if line:
					line = line.rstrip('\r\n')
					queue.put(line)
				else:
					queue.put('## EOF ##')
					break
		self._t = Thread(target = _populateQueue,
				args = (self._s, self._q))
		self._t.daemon = True
		self._t.start() #start collecting lines from the stream

	def readline(self, timeout = None):
		try:
			return self._q.get(block = timeout is not None,
					timeout = timeout)
		except Empty:
			return None

class changepass:

	def __init__(self):
		self.logger = logging.getLogger(__name__)

	def change_passphrase(self,gpgpath,homedir,keyid,oldpass,newpass):
		#self.logger.debug("called: %s,%s,%s,%s,%s",gpgpath,homedir,keyid,oldpass,newpass)

		cmdline = [ gpgpath, '--homedir', homedir, '--no-sk-comment',
			'--status-fd', '1', '--no-tty', '--command-fd', '0',
			'--edit-key', keyid, 'passwd' ]
		try:
			if sys.platform == 'win32':
				# http://stackoverflow.com/questions/7006238/how-do-i-hide-the-console-when-i-use-os-system-or-subprocess-call/7006424#7006424
				CREATE_NO_WINDOW = 0x08000000
				cmdh = subprocess.Popen(cmdline,bufsize=16384,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,shell = False,creationflags = CREATE_NO_WINDOW)
			else:
				cmdh = subprocess.Popen(cmdline,bufsize=16384,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,shell = False)
			output = NonBlockingStreamReader(cmdh.stdout)
	
			if global_config.gnupg_is_v2 == False:
				got_expected = False
				while True:
					line = output.readline(10)
					if line == None:
						break
					#self.logger.debug("%s",line)
					if line.find('passphrase.enter') >= 0:
						got_expected = True
						break
		
				if got_expected == False:
					cmdh.stdin.close()
					cmdh.wait()
					return False,'GPG did not ask for passphrase'
					
				#self.logger.debug("sending old passphrase")
				cmdh.stdin.write(oldpass.encode('utf-8') + '\n')
				cmdh.stdin.flush()
		
				got_badpass = False
				got_expected = False
				while True:
					line = output.readline(10)
					if line == None:
						break
					#self.logger.debug("%s",line)
					if line.find('BAD_PASSPHRASE') >= 0:
						got_badpass = True
						break
					if line.find('GOOD_PASSPHRASE') >= 0:
						got_expected = True
						break
		
				if got_badpass == True:
					cmdh.stdin.close()
					cmdh.wait()
					return False,'Old passphrase is incorrect'
					
				if got_expected == False: 
					cmdh.stdin.close()
					cmdh.wait()
					return False,'Unknown GPG passphrase error'
					
				#self.logger.debug("sending new passphrase")
				cmdh.stdin.write(newpass.encode('utf-8') + '\n')
				cmdh.stdin.flush()
	
			got_expected = False
			while True:
				line = output.readline(10)
				if line == None:
					break
				#self.logger.debug("%s",line)
				if line.find('keyedit.prompt') >= 0:
					got_expected = True
					break
	
			if got_expected == False:
				cmdh.stdin.close()
				cmdh.wait()
				return False,'GPG did not accept new passphrase'
				
			#self.logger.debug("sending quit")
			cmdh.stdin.write('quit\n')
			cmdh.stdin.flush()
	
			if global_config.gnupg_is_v2 == False:
				got_expected = False
				while True:
					line = output.readline(10)
					if line == None:
						break
					#self.logger.debug("%s",line)
					if line.find('keyedit.save.okay') >= 0:
						got_expected = True
						break
		
				if got_expected == False:
					cmdh.stdin.close()
					cmdh.wait()
					return False,'GPG did not prompt to save'
					
				#self.logger.debug("sending yes")
				cmdh.stdin.write('yes\n')
				cmdh.stdin.flush()
	
			got_expected = False
			while True:
				line = output.readline(10)
				if line == None:
					break
				#self.logger.debug("%s",line)
				if line.find('## EOF ##') >= 0:
					got_expected = True
					break
	
			cmdh.wait()
			return True,'Passphrase was successfully changed'
	
		except Exception as exc:
			#self.logger.debug("Exception: %s",traceback.format_exc())
			try:
				cmdh.kill()
			except Exception:
				pass
			return False,"Exception thrown, run with -debug to see it"	


# EOF
