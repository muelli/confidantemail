import sys
import os
import subprocess
import multiprocessing
import logging
import thread
import re
import codecs
import find_gpg_homedir
import gnupg
import global_config
import filelock
import folders
import hashlib
import flatstore
import filestore
import syncstore
import client
import client_agent
import message_list_window
import twisted.internet.reactor
import wx
import wx.lib.newevent

re_name_email = re.compile("^(.*) <([^>]+)>$")
re_resolution = re.compile("^(....)WindowSize: ([0-9]+)x([0-9]+)$",re.IGNORECASE)

class gui:

	def LoadKeyList(self):
		self.keyList = self.gpg.list_keys()
		for key in self.keyList:
			keyid = key['fingerprint']
			key['ent'] = False
			found,data = self.local_store.retrieveHeaders(keyid)
			if found == False:
				key['noannounce'] = True # don't display keys we don't have announce for
			else:
				for line in data:
					lineL = line.lower()
					if lineL == 'transport: entangled':
						key['ent'] = True
			m = re_name_email.match(key['uids'][0])
			if m:
				key['adr'] = m.group(2)
				nsp = m.group(1).split(' ',1)
				if len(nsp) == 1:
					key['fn'] = nsp[0]
					key['ln'] = nsp[0]
				else:
					key['fn'] = nsp[0]
					key['ln'] = nsp[1]
			else:
				key['adr'] = key['uids'][0]
				key['fn'] = key['uids'][0]
				key['ln'] = key['uids'][0]


#0 {'dummy': u'', 'keyid': u'59231A1B42EADCA2', 'expires': u'', 'subkeys': [[u'BCA34296639D64F6', u'e']], 'length': u'2048', 'ownertrust': u'u', 'algo': u'1', 'fingerprint': u'36D769F124785AD14E821A2159231A1B42EADCA2', 'date': u'1391547656', 'trust': u'u', 'type': u'pub', 'uids': [u'Mike Test <miketest@pobox.com>']}
	def agent_receive_thread(self):
		#DBGOUT#print "agent receive thread up"
		while True:
			message = self.from_agent_queue.get()
			msg_cmd = message[0]
			msg_args = message[1:]
			if msg_cmd == 'TERMINATE':
				break
			evt = self.client_agent_message(cmd = msg_cmd,args = msg_args)
			if self.acceptingEvents == True:
				wx.PostEvent(self.message_list.frame,evt)
	
	def kill_gpg_agent(self,gpg_homedir):
		if sys.platform == 'darwin': # Darwin cannot find gpg-connect-agent via gpgconf due to global path dependencies
			gpgca_path = re.sub("/gpgconf$","/gpg-connect-agent",global_config.gpgconf_path)
			cmdline = [ gpgca_path,'--homedir',gpg_homedir,'KILLAGENT' ]
		else:	
			cmdline = [ global_config.gpgconf_path,'--homedir',gpg_homedir,'--kill','gpg-agent' ]
		if sys.platform == 'win32':
			# http://stackoverflow.com/questions/7006238/how-do-i-hide-the-console-when-i-use-os-system-or-subprocess-call/7006424#7006424
			CREATE_NO_WINDOW = 0x08000000
			cmdh = subprocess.Popen(cmdline,bufsize=16384,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,shell = False,creationflags = CREATE_NO_WINDOW)
		else:
			cmdh = subprocess.Popen(cmdline,bufsize=16384,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,shell = False)
		cmdh.stdin.close() # undefined stdin -> Windows fails
		output = cmdh.stdout.read()
		cmdh.stdout.close()

	def main(self,argv):
		cmdline = argv[1:]
		if len(cmdline) == 0:
			#DBGOUT#print "Usage: python gui.py -homedir /path"
			sys.exit(1)
		
		self.homedir = None
		calledFromChooser = False
		logDebug = False
		logAllTraffic = False

		n = 0
		while n < len(cmdline):
			cmd = cmdline[n]
			#print n,cmd
			if cmd == '-homedir':
				n += 1
				self.homedir = cmdline[n]
				n += 1
			elif cmd == '-chooser':
				calledFromChooser = True
				n += 1
			elif cmd == '-debug':
				logDebug = True
				n += 1
			elif cmd == '-logtraffic':
				logAllTraffic = True
				n += 1

		if ( sys.platform == 'win32' or sys.platform == 'darwin' ) and sys.executable.lower().find("python") < 0:
			isPythonw = True
			logFile = self.homedir + os.sep + "guierror.log"
		else:
			isPythonw = False

		if logDebug == True:
			if isPythonw == True:
				logging.basicConfig(level=logging.DEBUG,filename = logFile,
        			format="%(asctime)s %(levelname)-5s %(name)-10s %(threadName)-10s %(message)s")
			else:
				logging.basicConfig(level=logging.DEBUG,
        			format="%(asctime)s %(levelname)-5s %(name)-10s %(threadName)-10s %(message)s")
		else:
			if isPythonw == True:
				logging.basicConfig(level=logging.INFO,filename = logFile,
        			format="%(asctime)s %(levelname)-5s %(name)-10s %(threadName)-10s %(message)s")
			else:
				logging.basicConfig(level=logging.INFO,
        			format="%(asctime)s %(levelname)-5s %(name)-10s %(threadName)-10s %(message)s")
			
#		hasher = hashlib.new('sha1')
#		hasher.update('CONFIDANTMAIL')
#		hasher.update(self.homedir.lower())
#		self.singleInstanceName = '.' + hasher.digest().encode('hex')
#		self.singleInstanceChecker = wx.SingleInstanceChecker(self.singleInstanceName)
#		if self.singleInstanceChecker.IsAnotherRunning():
#			if calledFromChooser == True:
#				return('INUSE')
#			else:
#				#DBGOUT#print "Account already open"
#				sys.exit(2)
		# The approach above is not reliable on Linux, using filelock.py instead
		lock_file_path = self.homedir + os.sep + 'LOCKFILE'
		self.singleInstanceChecker = filelock.filelock(lock_file_path,True)
		if self.singleInstanceChecker.lock_nowait() == False:
			if calledFromChooser == True:
				return('INUSE')
			else:
				#DBGOUT#print "Account already open"
				sys.exit(2)

		config_file_path = self.homedir + os.sep + 'config.txt'
		config_file_handle = codecs.open(config_file_path,'r','utf-8')
		config_data = config_file_handle.read()
		config_file_handle.close()

		self.torProxy = None
		self.i2pProxy = None
		self.socksProxy = None
		self.proxyIP = False
		self.proxyTOR = False
		self.proxyI2P = False
		self.useExitNode = False
		self.newMessageCheck = 0
		self.newMessageNotification = 'None'
		self.folderSync = 0
		self.fieldOrder = 'From Subject Date To'
		self.spellcheckLanguage = 'en_US'
		self.closeOnReply = False
		self.acceptingEvents = True
		self.editorScaleFactor = '1.00'
		self.saveFieldSizes = 'Incoming/Outgoing' # Off, Global, Incoming/Outgoing, Per Category
		self.oldTransport = None
		self.pubTransport = None

		for line in config_data.split('\n'):
			line = line.encode('utf-8')
			line = line.rstrip('\r\n')
			lineL = line.lower()
			m = re_resolution.match(line)
			if m:
				mt = m.group(1).lower()
				x = int(m.group(2))
				y = int(m.group(3))
				if mt == 'list':
					self.list_window_size = [ x,y ]
				elif mt == 'edit':
					self.edit_window_size = [ x,y ]
				elif mt == 'view':
					self.view_window_size = [ x,y ]
				elif mt == 'addr':
					self.addr_window_size = [ x,y ]
			elif lineL[0:19] == 'editorscalefactor: ':
				self.editorScaleFactor = line[19:]
			elif lineL[0:24] == 'newmessagenotification: ':
				self.newMessageNotification = line[24:]
			elif lineL[0:7] == 'keyid: ' :
				self.client_keyid_hex = line[7:]
				self.client_keyid = self.client_keyid_hex.decode("hex")
			elif lineL[0:10] == 'torproxy: ':
				self.torProxy = line[10:]
			elif lineL[0:10] == 'i2pproxy: ':
				self.i2pProxy = line[10:]
			elif lineL[0:12] == 'socksproxy: ':
				self.socksProxy = line[12:]
			elif lineL[0:12] == 'fieldorder: ':
				self.fieldOrder = line[12:]
			elif lineL[0:16] == 'savefieldsizes: ':
				self.saveFieldSizes = line[16:]
			elif lineL == 'proxyip: true':
				self.proxyIP = True
			elif lineL == 'proxytor: true':
				self.proxyTOR = True
			elif lineL == 'useexitnode: true':
				self.useExitNode = True
			elif lineL[0:17] == 'newmessagecheck: ':
				self.newMessageCheck = int(line[17:])
			elif lineL[0:12] == 'foldersync: ':
				self.folderSync = int(line[12:])
			elif lineL == 'closeonreply: true':
				self.closeOnReply = True
			elif lineL[0:20] == 'spellchecklanguage: ':
				self.spellcheckLanguage = line[20:]
			elif lineL[0:11] == 'transport: ':
				self.transport = line[11:]
			elif lineL[0:14] == 'oldtransport: ':
				self.oldTransport = line[14:]
			elif lineL[0:14] == 'pubtransport: ':
				self.pubTransport = line[14:]
			elif lineL[0:17] == 'entangledserver: ':
				self.entangled_server = line[17:]

		try:
			self.editorScaleFactor = float(self.editorScaleFactor)
		except Exception:
			self.editorScaleFactor = 1.0

		make_subdirs = [ 'complete', 'content', 'incomplete', 'localstore',
				'outbox', 'prepmsgs', 'tempkeys', 'txlogs' ]
		if self.folderSync > 0:
			make_subdirs.append('syncstore')
		for subdir in make_subdirs:
			cspath = self.homedir + os.sep + subdir
			if not os.path.exists(cspath):
				os.mkdir(cspath)

		gpg_homedir = self.homedir + os.sep + 'gpg'
		# Fix the gpg-config if necessary
		if sys.platform == 'darwin' and global_config.gnupg_is_v2 == True:
			try:
				find_gpg_homedir.macos_fix_pinentry(global_config.gnupg_path,gpg_homedir)
			except Exception:
				pass
		self.gpg = gnupg.GPG(gpgbinary = global_config.gnupg_path,verbose = False,options = global_config.gpg_opts,gnupghome = gpg_homedir)
		self.gpg.encoding = 'utf-8'
		self.gpg_tempdir = self.homedir + os.sep + 'tempkeys'
		self.tempkeys = flatstore.flatstore(self.gpg_tempdir)
		self.temp_gpg = gnupg.GPG(gpgbinary = global_config.gnupg_path,verbose = False,options = global_config.gpg_opts,gnupghome = self.gpg_tempdir)
		self.temp_gpg.encoding = 'utf-8'
	
		self.passphrase = None

		self.from_address = None
		self.from_address_name = None
		private_keys = self.gpg.list_keys(True)
		mykey = self.client_keyid_hex.lower()
		for key in private_keys:
			if key['fingerprint'].lower() == mykey:
				self.from_address = key['uids'][0] + ' ' + mykey
				self.from_address_name = key['uids'][0]
				break
	 	if self.from_address == None:
			raise KeyError('My private key not found')
	
		self.prepmsgs = flatstore.flatstore(self.homedir + os.sep + "prepmsgs")
		self.complete_store = flatstore.flatstore(self.homedir + os.sep + "complete")
		self.outbox_store = flatstore.flatstore(self.homedir + os.sep + "outbox")
		self.local_store = filestore.filestore(self.homedir + os.sep + "localstore")
		if self.folderSync > 0:
			self.outgoing_sync = syncstore.syncstore(self.homedir + os.sep + "syncstore",True)
		else:
			self.outgoing_sync = None
		self.folder_store = folders.folders(self.homedir + os.sep + "folder_index",self.homedir + os.sep + "txlogs",self.local_store,self.outbox_store,self.outgoing_sync)
		self.LoadKeyList()
		self.client_agent_message,self.EVT_CLIENT_AGENT_MESSAGE = wx.lib.newevent.NewEvent()
		self.to_agent_queue = multiprocessing.Queue()
		self.from_agent_queue = multiprocessing.Queue()
		self.message_list = message_list_window.RunApp(self)
		self.client_agent_process = multiprocessing.Process(target=client_agent.process_run, args = [ self.homedir,self.to_agent_queue,self.from_agent_queue,logDebug,logAllTraffic ] )
		self.client_agent_process.start()
		thread.start_new_thread(self.agent_receive_thread,())
	
		self.message_list.MainLoop()
		self.to_agent_queue.put( [ "TERMINATE" ] )
		self.folder_store.commit()
		self.folder_store.close()
		# Kill the gpg agent on the way out, so we don't leave the key in memory
		if global_config.gnupg_is_v2 == True and global_config.gpgconf_path != None:
			try:
				self.kill_gpg_agent(gpg_homedir)
			except Exception:
				pass


if __name__ == "__main__":
	#DBGOUT#logging.basicConfig(level=logging.DEBUG, 
       	#DBGOUT#format="%(asctime)s %(levelname)-5s %(name)-10s %(threadName)-10s %(message)s")
	guiobj = gui()
	guiobj.main(sys.argv)
	sys.exit(0)

# EOF
