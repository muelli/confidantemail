import sys
import logging
import os
import shutil
import wx
import wx.lib.mixins.listctrl as listmix
import re
import global_config
import gui
import config_dialog
import anydbm
import struct
import folders
import pickle
import hashlib
import filelock
import key_value_file
import images2

id_check = 1
id_repair = 2
id_cancel = 3
	
re_logfile = re.compile("^log.([0-9]{7})$",re.IGNORECASE)

class RepairFrame(wx.Frame):

	def __init__(self,parent,size,homeDir,pos=None):
		title = 'Repair Index File'
		if pos == None:
			wx.Frame.__init__(self,parent,-1,title,size=size)
		else:
			wx.Frame.__init__(self,parent,-1,title,pos=pos,size=size)

		self.homeDir = homeDir	
		self.addressList = [ ]

		mainPanel = wx.Panel(self,-1,size=self.GetClientSize())
		panelSizer = wx.BoxSizer(wx.VERTICAL)
		panelSizer.Add(mainPanel,1,wx.ALL|wx.GROW,0)

		mainSizer = wx.BoxSizer(wx.VERTICAL)
		hsizer = wx.BoxSizer(wx.HORIZONTAL)
		self.textCtrl = wx.TextCtrl(mainPanel,-1,style = wx.TE_MULTILINE|wx.TE_READONLY)
		self.checkButton = wx.Button(mainPanel,id_check,"Check")
		self.repairButton = wx.Button(mainPanel,id_repair,"Repair")
		self.cancelButton = wx.Button(mainPanel,id_cancel,"Cancel")
		hsizer.Add(self.checkButton,0,wx.ALL,5)
		hsizer.Add(self.repairButton,0,wx.ALL,5)
		hsizer.Add(self.cancelButton,0,wx.ALL,5)
		mainSizer.Add(self.textCtrl,1,wx.ALL|wx.GROW,1)
		mainSizer.Add(hsizer,0,wx.ALIGN_CENTER_HORIZONTAL)
		mainPanel.SetSizer(mainSizer)
		self.SetSizer(panelSizer)
		if sys.platform == 'darwin':
			hsizer.Layout()
			panelSizer.Layout()
			mainSizer.Layout()
		self.Bind(wx.EVT_BUTTON,self.OnCheck,self.checkButton)
		self.Bind(wx.EVT_BUTTON,self.OnRepair,self.repairButton)
		self.Bind(wx.EVT_BUTTON,self.OnCancel,self.cancelButton)
		self.Bind(wx.EVT_CLOSE,self.OnClose)
		keyicon_bmp = images2.key_icon.GetBitmap()
		keyicon = wx.IconFromBitmap(keyicon_bmp)
		self.SetIcon(keyicon)

		hasher = hashlib.new('sha1')
		hasher.update('CONFIDANTMAIL')
		hasher.update(self.homeDir.lower())
		#self.singleInstanceName = '.' + hasher.digest().encode('hex')
		#self.singleInstanceChecker = wx.SingleInstanceChecker(self.singleInstanceName)
		lock_file_path = self.homeDir + os.sep + 'LOCKFILE'
		self.singleInstanceChecker = filelock.filelock(lock_file_path,True)

		self.textCtrl.AppendText("Home Directory: " + self.homeDir + "\n\n" + \
		"The Folder Index file keeps track of messages and the folders they are " + \
		"stored in. This is a random-access file and can become corrupted, so the " + \
		"system keeps a transaction log of changes in the order they were " +
		"performed.\n\n" + \
		"The Check function verifies the indexes and links in the Folder Index, " + \
		"without changing anything. " +
		"The Repair function replays all of the transaction log entries, and then "
		"copies all of the message headers and folder links into a new Folder Index "
		"file. This should restore the Folder Index if it has been damaged.\n\n")

		if self.singleInstanceChecker.lock_nowait() == False:
			self.textCtrl.AppendText( \
			"This account is open. Please click Cancel, close the running instance," + \
			" and try again.")
			self.checkButton.Disable()
			self.repairButton.Disable()
		else:
			self.textCtrl.AppendText( \
			"Press Check to verify the integrity of the Folder Index, Repair to " +
			"rebuild the Folder Index, or Cancel to abort.")

		# window size check and fix
		xo,yo = size
		xr,yr = mainSizer.ComputeFittingWindowSize(self)
		if xo < xr or yo < yr:
			xn = int(1.1 * xr) if xr > xo else xo
			yn = int(1.1 * yr) if yr > yo else yo
			self.SetSize( (xn,yn) )
		# window size check and fix

	def OutputText(self,str):
		self.textCtrl.AppendText(str + "\n")

	def OnCheck(self,event):
		self.checkButton.Disable()
		self.repairButton.Disable()
		self.textCtrl.AppendText("\n\n")
		wx.CallAfter(self.RunCheck)

	def OnRepair(self,event):
		self.checkButton.Disable()
		self.repairButton.Disable()
		self.textCtrl.AppendText("\n\n")
		self.cancelButton.SetLabel("Close")
		wx.CallAfter(self.RunRebuild)

	def RunCheck(self):
		rfi = RepairFolderIndex(self.homeDir,self.OutputText)
		rfi.checkFolderStructure()
		self.checkButton.Enable()
		self.repairButton.Enable()

	def RunRebuild(self):
		rfi = RepairFolderIndex(self.homeDir,self.OutputText)
		rfi.generateLogList()
		rfi.rebuildFolderIndex()

	def OnCancel(self,event):
		self.OnClose(event)
		
	def OnClose(self,event):
		self.singleInstanceChecker.unlock_close()
		self.singleInstanceChecker = None
		self.Destroy()

class RepairFolderIndex:
	def __init__(self,user_path,output):
		self.user_path = user_path
		self.log_path = user_path + os.sep + "txlogs"
		self.output = output

	def generateLogList(self):
		self.first_log = -1
		self.last_log = -1
		self.num_logs = 0
		self.is_contiguous = True
		self.log_list = [ ]
		logpath_dir = os.listdir(self.log_path)
		logpath_dir.sort()
		for fn in logpath_dir:
			m = re_logfile.match(fn)
			if m:
				self.log_list.append(fn)
				n = int(m.group(1))
				self.num_logs += 1
				if (n-1) != self.last_log:
					self.is_contiguous = False
				if self.first_log < 0:
					self.first_log = n
				self.last_log = n
		self.output("Num logs = %i, range = %i - %i" % (self.num_logs,self.first_log,self.last_log))
		if self.is_contiguous == True:
			self.output("Logs are contiguous from zero")
		else:
			self.output("Logs are not contiguous from zero")

	def rebuildFolderIndex(self):
		folder_index = self.user_path + os.sep + "folder_index"
		temp_folder_index = self.user_path + os.sep + "folder_index.temp"
		new_folder_index = self.user_path + os.sep + "folder_index.rebuild"
		txlogs = self.user_path + os.sep + "txlogs"
		new_txlogs = self.user_path + os.sep + "txlogs.new"
		i = 1
		while True:
			old_folder_index = self.user_path + os.sep + "folder_index.%i" % i
			if os.path.exists(old_folder_index) == False:
				break
			i += 1
		if os.path.exists(new_txlogs):
			i = 1
			while True:
				old_txlogs = self.user_path + os.sep + "txlogs.%i" % i
				if os.path.exists(old_txlogs) == False:
					break
				i += 1
			self.output("Renaming %s\nto %s" % (new_txlogs,old_txlogs))
			os.rename(new_txlogs,old_txlogs)
		self.output("Old folder index = " + old_folder_index)	
		if os.path.exists(temp_folder_index):
			self.output("Deleting " + temp_folder_index)
			os.unlink(temp_folder_index)
		if self.is_contiguous == False:
			nKeys = 0
			try:
				nKeys = self.copyFolderIndex(folder_index,temp_folder_index)
				self.output("Copied %i keys from old to new folder index" % (nKeys))
			except Exception as exc:
				self.output("Copy keys returned " + str(exc))

		for logfile in self.log_list:
			logfile_path = self.log_path + os.sep + logfile
			self.output("Replaying " + logfile)
			num_tx,num_changes = key_value_file.replay_log_file(temp_folder_index,logfile_path,self.output)
			self.output("Replayed %i transactions and %i changes" % (num_tx,num_changes))
		if not os.path.exists(new_txlogs):
			os.mkdir(new_txlogs)
		self.output("Done replaying log files, performing logical rebuild")
		self.logicalRebuild(temp_folder_index,new_folder_index,new_txlogs)
		self.output("Deleting temporary file %s" % temp_folder_index)
		os.unlink(temp_folder_index)
		if os.path.exists(folder_index):
			self.output("Renaming %s\nto %s" % (folder_index,old_folder_index))
			os.rename(folder_index,old_folder_index)
		self.output("Renaming %s\nto %s" % (new_folder_index,folder_index))
		os.rename(new_folder_index,folder_index)
		i = 1
		while True:
			old_txlogs = self.user_path + os.sep + "txlogs.%i" % i
			if os.path.exists(old_txlogs) == False:
				break
			i += 1
		self.output("Renaming %s\nto %s" % (txlogs,old_txlogs))
		os.rename(txlogs,old_txlogs)
		self.output("Renaming %s\nto %s" % (new_txlogs,txlogs))
		os.rename(new_txlogs,txlogs)
		self.output("Rebuild done")

	def copyFolderIndex(self,oldFile,newFile):
		oldDbmFile = anydbm.open(oldFile,'c')
		newDbmFile = anydbm.open(newFile,'c')
		keyList = oldDbmFile.keys()
		nKeys = 0
		for key in keyList:
			newDbmFile[key] = oldDbmFile[key]
			nKeys += 1
		oldDbmFile.close()	
		newDbmFile.close()	
		return nKeys	
	
	def checkFolderStructure(self):
		folder_index = self.user_path + os.sep + "folder_index"
		dbmFile = anydbm.open(folder_index,'r')
		nKeys = 0
		nErrors = 0
		for key in dbmFile.keys():
			typ = key[0]
			if typ == 'E':
				msgid = dbmFile[key]
				#print "Got E" + key[1:].encode('hex') + ' = ' + msgid.encode('hex')
				hrec = 'H' + key[1:5] + msgid
				if hrec not in dbmFile:
					#print "Corresponding H record is missing!"
					self.output("E record " + key[1:].encode('hex') + " missing corresponding H record")
					nErrors += 1
				elif dbmFile[hrec] != key[5:10]:
					self.output("E record " + key[1:].encode('hex') + " does not match index of corresponding H record")
					nErrors += 1
				mrec = 'M' + msgid
				if mrec not in dbmFile:
					#print "Corresponding M record is missing!"
					self.output("E record " + key[1:].encode('hex') + " missing corresponding M record")
					nErrors += 1
				frec = 'F' + msgid
				if frec not in dbmFile:
					#print "Corresponding F record is missing!"
					self.output("E record " + key[1:].encode('hex') + " missing corresponding F record")
					nErrors += 1
				else:
					fn, = struct.unpack("I",key[1:5])
					fldrs = pickle.loads(dbmFile[frec])
					if fn not in fldrs:
						#print "Message missing from F record for folder",fn,fldrs,'!'
						foldersS = ''
						for fx in fldrs:
							if len(foldersS) > 0:
								foldersS += ','
							foldersS += str(fx)
						self.output("E record " + key[1:].encode('hex') + " has inconsistent F record, missing folder " + str(fn)+", has "+foldersS)
						nErrors += 1
				irec = 'I' + key[1:5]
				if irec not in dbmFile:
					self.output("I record for folder "+str(fn)+" is "+str(irn)+" is missing")
					nErrors += 1
					#print "Corresponding I record is missing!"
				else:
					irn = pickle.loads(dbmFile[irec])
					ern, = struct.unpack("I",key[5:10])
					if irn < ern:
						#print "I record for folder",fn,"is",irn,"less than",ern,"!"
						self.output("I record for folder "+str(fn)+" is "+str(irn)+" less than "+str(ern))
						nErrors += 1
			elif type == 'H':
				fn = dbmFile[key]
				#print "Got H" + key[1:].encode('hex') + ' = ' + fn.encode('hex')
				erec = 'E' + key[1:5] + fn
				if erec not in dbmFile:
					self.output("H record "+key[1:].encode('hex')+" missing corresponding E record")
					nErrors += 1
					#print "Corresponding E record is missing!"
				elif dbmFile[erec] != href[5:20]:
					self.output("H record "+key[1:].encode('hex')+" does not match corresponding E record")
					nErrors += 1
				mrec = 'M' + key[5:]
				if mrec not in dbmFile:
					self.output("H record "+key[1:].encode('hex')+" missing corresponding M record")
					nErrors += 1
					#print "Corresponding M record is missing!"
			elif typ == 'M':
				#print "Got message " + typ + key[1:].encode('hex')
				msgid = key[1:]
				frec = 'F' + msgid
				if frec not in dbmFile:
					self.output("M record "+key[1:].encode('hex')+" missing F record")
					nErrors += 1
					#print "No folder list for message!"
				else:
					fldrs = pickle.loads(dbmFile[frec])
					#print "Message in folders ",fldrs
					for folder in fldrs:
						hrec = 'H' + struct.pack('I',folder) + key[1:]
						if hrec not in dbmFile:
							self.output("M record "+key[1:].encode('hex')+" missing H record for folder "+str(folder))
							nErrors += 1
							#print "H record for folder %i is missing!" % folder
						else:
							erec = 'E' + struct.pack('I',folder) + dbmFile[hrec]
							if erec not in dbmFile:
								self.output("M record "+key[1:].encode('hex')+" missing E record for folder "+str(folder))
								nErrors += 1
								#print "E record for folder %i is missing!" % folder
							else:
								if dbmFile[erec] != key[1:]:
									self.output("M record "+key[1:].encode('hex')+" E record for folder "+str(folder)+ " does not match message ID")
									nErrors += 1
									#print "E record in folder %i does not match message id!"
			if ((nKeys > 0) and (nKeys % 10000 == 0)):
				self.output("Processing key = %i, errors = %i" % (nKeys,nErrors) )
			nKeys += 1
		self.output("Total keys = %i, errors = %i" % (nKeys,nErrors) )
		if nErrors > 0:
			self.output("This folder index has errors and should be rebuilt.")
		else:
			self.output("This folder index appears to be good.")
		dbmFile.close()
		return nKeys,nErrors
		
	def logicalRebuild(self,oldFile,newFile,newTxLogs):
		dbmFile = anydbm.open(oldFile,'c')
		newFolders = folders.folders(newFile,newTxLogs,None,None)
		self.output("Pass 1 - adding folders")
		high_folder_number = 0
		folder_map = dict()
		if "xF" in dbmFile:
			high_folder_number = pickle.loads(dbmFile['xF'])
		if high_folder_number < 1024:
			high_folder_number = 1024
		for i in range(high_folder_number):
			arec = 'A' + struct.pack('I',i)
			if arec in dbmFile:
				try:
					folder = pickle.loads(dbmFile[arec])
					folderP = folder.replace('\x00','/')
					self.output("Found folder %i: %s" % (i,folderP))
					folder_map[i] = folder
					newFolders.check_add_folder_recurse(folder)
				except Exception:
					self.output("Corrupt folder record " + str(i) + ": " + str(exc))
		nKeys = 0
		nMessages = 0
		self.output("\nPass 2 - copying messages")
		for key in dbmFile.keys():
			typ = key[0]
			if typ == 'M':
				recovered = False
				try:
					msgdata = pickle.loads(dbmFile[key])
					newFolders.save_message(key[1:],msgdata)
					nMessages += 1
					recovered = True
				except Exception as exc:
					self.output("Message M" + key[1:].encode('hex') + " is corrupt, discarding: " + str(exc))
				if recovered == True:
					filed = False
					try:
						fldrs = pickle.loads(dbmFile['F' + key[1:]])
						for f in fldrs:
							if f in folder_map:
								newFolders.put_message_in_folder(folder_map[f],key[1:])
								filed = True
					except Exception as exc:
						self.output("Folder list extraction threw " + str(exc))
					if filed == False:
						self.output("Message M" + key[1:].encode('hex') + " has no folder list, placing in Deleted")
						newFolders.put_message_in_folder(folders.id_deleted,key[1:])
			elif typ == 'g':
				newFolders.set_global(key[1:],dbmFile[key])
			nKeys += 1
			if (nMessages % 100 == 0):
				newFolders.commit()
			if (nKeys % 10000 == 0):
				self.output("Processing key = %i, messages = %i" % (nKeys,nMessages))
		self.output("Total keys = %i, total messages = %i" % (nKeys,nMessages))
		newFolders.commit()
		dbmFile.close()
		newFolders.close()
	
#class RunApp(wx.App):
#	def __init__(self,argv):
#		self.argv = argv
#		self.open_account_path = None
#		self.edit_account_path = None
#		wx.App.__init__(self, redirect=False)
#
#	def OnInit(self):
#		
#		cmdline = self.argv[1:]
#		self.homedir = None
#
#		n = 0
#		while n < len(cmdline):
#			cmd = cmdline[n]
#			#DBGOUT#print n,cmd
#			if cmd == '-homedir':
#				n += 1
#				self.homedir = cmdline[n]
#				n += 1
#
#		if self.homedir == None:
#			self.homedir = global_config.default_homedir
#			self.homedir = "c:\\projects\\confidantmail\\clients\\client2"
#
#		if os.path.exists(self.homedir) == False:
#			os.mkdir(self.homedir)
#
#		self.frame = RepairFrame(None,[ 640,540 ],self.homedir)
#		self.frame.app = self
#		self.frame.Show()
#		self.SetTopWindow(self.frame)
#		self.chooserPos = self.frame.GetPosition()
#		return True

#def conout(string):
#	print string

#if __name__ == "__main__":
#	rfi = RepairFolderIndex("c:\\projects\\confidantmail\\clients\\client1",conout)
#	rfi.checkFolderStructure("c:\\projects\\confidantmail\\clients\\client1\\folder_index")
#	rfi.logicalRebuild("c:\\projects\\confidantmail\\clients\\client1\\folder_index","c:\\projects\\confidantmail\\clients\\client1\\folder_index_new","c:\\projects\\confidantmail\\clients\\client1\\txlogs.new")
#	#rfi.generateLogList()
#	#rfi.rebuildFolderIndex()
#	sys.exit(0)

class RunApp(wx.App):
	def __init__(self,homedir,pos = None):
		self.homedir = homedir
		self.pos = pos
		wx.App.__init__(self, redirect=False)

	def OnInit(self):
		self.frame = RepairFrame(None,[ int(global_config.resolution_scale_factor*640),int(global_config.resolution_scale_factor*540) ],self.homedir,pos = self.pos)
		self.frame.Show()
		self.SetTopWindow(self.frame)
		return True


# EOF
