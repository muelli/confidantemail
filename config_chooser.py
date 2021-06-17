import sys
import logging
import os
import platform

# This fixes a dynamic linking problem on the MacOS cx_Freeze build #
# It has to be done here before the import of wx #
if sys.platform == 'darwin' and \
	os.path.basename(sys.executable).lower() != 'python' and \
	'DYLD_FALLBACK_LIBRARY_PATH' not in os.environ:
	os.environ['DYLD_FALLBACK_LIBRARY_PATH'] = os.path.dirname(sys.executable)
	os.execv(sys.executable,sys.argv) # did not work otherwise
# End MacOS fix #

import codecs
import wx
import wx.lib.mixins.listctrl as listmix
import re
import multiprocessing
import global_config
import gui
import config_dialog
import repair_account
import find_gpg_homedir
import images2

id_easy_setup = 1
id_open = 2
id_config = 3
id_new = 4
id_repair = 5
id_cancel = 6
id_help = 7

class ChooserListCtrl(wx.ListCtrl, listmix.ListCtrlAutoWidthMixin):
	def __init__(self,parent):
		self.parent = parent
		wx.ListCtrl.__init__(self,parent,style = wx.LC_REPORT|wx.LC_HRULES|wx.LC_VRULES|wx.LC_SINGLE_SEL)
		listmix.ListCtrlAutoWidthMixin.__init__(self)
		self.numRows = 0
		self.InsertColumn(0,"Directory")
		self.InsertColumn(1,"Email Address")

class ChooserDialogFrame(wx.Frame):

	def __init__(self,parent,size,baseDir,pos=None,account_already_open = False):
		if account_already_open == True:
			wx.MessageBox("Account is already open","Error",style = wx.ICON_EXCLAMATION)

		title = 'Choose an Account - Confidant Mail'
		if pos == None:
			wx.Frame.__init__(self,parent,-1,title,size=size)
		else:
			wx.Frame.__init__(self,parent,-1,title,pos=pos,size=size)

		self.baseDir = baseDir	
		self.addressList = [ ]

		mainPanel = wx.Panel(self,-1,size=self.GetClientSize())
		panelSizer = wx.BoxSizer(wx.VERTICAL)
		panelSizer.Add(mainPanel,1,wx.ALL|wx.GROW,0)
		self.statusBar = self.CreateStatusBar(1)
		mainSizer = wx.BoxSizer(wx.VERTICAL)
		hsizer = wx.BoxSizer(wx.HORIZONTAL)
		self.chooserList = ChooserListCtrl(mainPanel)
		easySetupButton = wx.Button(mainPanel,id_easy_setup,"Easy Setup",style = wx.BU_EXACTFIT)
		openButton = wx.Button(mainPanel,id_open," Open ",style = wx.BU_EXACTFIT)
		configButton = wx.Button(mainPanel,id_config,"Configure",style = wx.BU_EXACTFIT)
		newButton = wx.Button(mainPanel,id_new,"New Account",style = wx.BU_EXACTFIT)
		repairButton = wx.Button(mainPanel,id_repair,"Repair",style = wx.BU_EXACTFIT)
		cancelButton = wx.Button(mainPanel,id_cancel,"Cancel",style = wx.BU_EXACTFIT)
		helpButton = wx.Button(mainPanel,id_help,"Help",style = wx.BU_EXACTFIT)
		hsizer.Add(easySetupButton,0,wx.ALL,3)
		hsizer.Add(openButton,0,wx.ALL,3)
		hsizer.Add(configButton,0,wx.ALL,3)
		hsizer.Add(newButton,0,wx.ALL,3)
		hsizer.Add(repairButton,0,wx.ALL,3)
		hsizer.Add(cancelButton,0,wx.ALL,3)
		hsizer.Add(helpButton,0,wx.ALL,3)
		mainSizer.Add(self.chooserList,1,wx.ALL|wx.GROW,1)
		mainSizer.Add(hsizer,0,wx.ALIGN_CENTER_HORIZONTAL)
		mainPanel.SetSizer(mainSizer)
		self.SetSizer(panelSizer)
		self.Bind(wx.EVT_BUTTON,self.OnEasySetup,easySetupButton)
		self.Bind(wx.EVT_BUTTON,self.OnOpen,openButton)
		self.Bind(wx.EVT_BUTTON,self.OnConfig,configButton)
		self.Bind(wx.EVT_BUTTON,self.OnRepair,repairButton)
		self.Bind(wx.EVT_BUTTON,self.OnNewAccount,newButton)
		self.Bind(wx.EVT_BUTTON,self.OnCancel,cancelButton)
		self.Bind(wx.EVT_BUTTON,self.OnHelp,helpButton)
		self.chooserList.Bind(wx.EVT_LIST_ITEM_ACTIVATED,self.OnActivateRow)
		self.Bind(wx.EVT_CLOSE,self.OnClose)

		keyicon_bmp = images2.key_icon.GetBitmap()
		keyicon = wx.IconFromBitmap(keyicon_bmp)
		self.SetIcon(keyicon)
		if sys.platform == 'win32' and platform.platform().find("Windows-XP") < 0 \
				and platform.platform().find("Windows-Vista") < 0:
			# fix the taskbar icon, http://qt-project.org/forums/viewthread/28752
			import ctypes
			myappid = 'Confidant Mail'
			ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

		if (baseDir == None) or (os.path.exists(baseDir) == False) \
							 or (os.path.isfile(baseDir) == True):
			self.statusBar.SetStatusText('No home directory specified or found.')
			newButton.Disable()
		else:
			self.statusBar.SetStatusText('Home directory: ' + self.baseDir,0)
			self.loadAddressList()
		if global_config.gnupg_path == None:
			wx.CallAfter(self.gnupgWarning)
		else:
			self.checkSafeGpgVersion()

	# GPG version check for CVE-2016-6313
	def checkSafeGpgVersion(self):
		msg = ""
		if global_config.gnupg_version >= '1.4.000' and global_config.gnupg_version < '1.4.21' and \
			find_gpg_homedir.check_gpg_version_special_case() == False:
			msg = "Found GPG version " + global_config.gnupg_version
		if global_config.gnupg_version >= '2.1.000' and (
			global_config.gnupg_version < '2.1.15' or global_config.libgcrypt_version < '1.7.3' ) and \
			find_gpg_homedir.check_libgcrypt_version_special_case() == False:
			msg = "Found GPG version " + global_config.gnupg_version + " with libgcrypt " + global_config.libgcrypt_version
		if msg != "":
			msg += ", which has security vulnerability CVE-2016-6313. This is a buggy cryptographic random number generator, and could weaken message security. Please upgrade to GPG 1.4.21 or later, or to GPG 2.1.15 with libgcrypt 1.7.3 or later."
			wx.CallAfter(wx.MessageBox,msg,"Security Warning",style = wx.ICON_EXCLAMATION)

	def loadAddressList(self):
		i = 0
		self.addressList = [ ]
		dirs =  os.listdir(self.baseDir)
		dirs.sort()
		for l1 in dirs:
			cpath = self.baseDir + os.sep + l1
			if os.path.isdir(cpath):
				emailAddress = self.getEmailAddress(cpath)
				listIndex = self.chooserList.InsertStringItem(i,cpath)
				self.chooserList.SetStringItem(listIndex,1,emailAddress)
				self.chooserList.SetItemData(listIndex,i)
				self.addressList.append( ( cpath,emailAddress ) )
				i += 1
		self.chooserList.SetColumnWidth(0, wx.LIST_AUTOSIZE)
		self.chooserList.SetColumnWidth(1, wx.LIST_AUTOSIZE)

	def gnupgWarning(self):
		wx.MessageBox("GNU Privacy Guard (" + global_config.gnupg_exename + ") was not found, and the program will not work without it. Click Cancel and install GnuPG before proceeding.","Error",style = wx.ICON_EXCLAMATION)

	def getEmailAddress(self,cpath):
		configFile = cpath + os.sep + "config.txt"
		if os.path.isfile(configFile) == False:
			return "Undefined"
		try:
			fh = codecs.open(configFile,'r','utf-8')
			configData = fh.read()
			fh.close()
		except Exception:
			return "Config file read failure"

		for line in configData.split('\n'):
			line = line.rstrip('\r\n')
			lineL = line.lower()
			if lineL[0:14] == 'emailaddress: ':
				return line[14:]
		return "Undefined"

	def OnOpen(self,event):
		itemno = self.chooserList.GetFirstSelected()
		#DBGOUT#print "open",itemno
		if itemno >= 0:
			self.ItemSelected(itemno)

	def OnActivateRow(self,event):
		itemno = event.GetData()
		#DBGOUT#print "activate",itemno
		if itemno >= 0:
			self.ItemSelected(itemno)

	def ItemSelected(self,itemno):
		cpath,emailAddress = self.addressList[itemno]
		if emailAddress == "Undefined":
			self.app.EditAccount(cpath)
			self.Close()
		else:
			self.app.OpenAccount(cpath)
			self.Close()

	def OnConfig(self,event):
		itemno = self.chooserList.GetFirstSelected()
		if itemno >= 0:
			cpath,emailAddress = self.addressList[itemno]
			self.app.EditAccount(cpath)
			self.Close()

	def OnRepair(self,event):
		itemno = self.chooserList.GetFirstSelected()
		if itemno >= 0:
			cpath,emailAddress = self.addressList[itemno]
			self.app.RepairAccount(cpath)
			self.Close()

	def OnNewAccount(self,event):
		dlg = wx.TextEntryDialog(self,'Enter Directory Name','New Account','')
		if dlg.ShowModal() != wx.ID_OK:
			dlg.Destroy()
			return
		new_dir = dlg.GetValue()
		if new_dir == '':
			return
		cpath = self.baseDir + os.sep + new_dir
		if os.path.exists(cpath) == True:
			wx.MessageBox("Directory already exists","Error",style = wx.ICON_EXCLAMATION)
			return
		try:
			os.mkdir(cpath)
		except Exception as exc:
			wx.MessageBox("Cannot make directory: " + exc.strerror,"Error",style = wx.ICON_EXCLAMATION)
			return

		self.app.EditAccount(cpath)
		self.Close()

	def OnEasySetup(self,event):
		cpath = '/\EASYSETUP\/' + self.baseDir
		self.app.EditAccount(cpath)
		self.Close()

	def OnCancel(self,event):
		self.OnClose(event)
		
	def OnHelp(self,event):
		self.helpcon = wx.html.HtmlHelpController(parentWindow = self)
 		wx.FileSystem.AddHandler(wx.ZipFSHandler())
		self.helpcon.AddBook(global_config.help_file,0)
		self.helpcon.DisplayContents()
		self.helpcon.Display("config_chooser.html")

	def OnClose(self,event):
		#DBGOUT#print "close"
		self.Destroy()

class RunApp(wx.App):
	def __init__(self,homedir,open_subdir,log_traffic,log_debug,account_already_open = False):
		self.open_account_path = None
		self.edit_account_path = None
		self.repair_account_path = None
		self.account_already_open = account_already_open
		self.homedir = homedir
		self.open_subdir = open_subdir
		self.log_traffic = log_traffic
		self.log_debug = log_debug
		wx.App.__init__(self, redirect=False)

	def OnInit(self):
		self.frame = ChooserDialogFrame(None,[ 720,540 ],self.homedir,account_already_open = self.account_already_open)
		self.frame.app = self
		self.frame.Show()
		self.SetTopWindow(self.frame)
		self.chooserPos = self.frame.GetPosition()
		return True

	def OpenAccount(self,open_account_path):
		self.open_account_path = open_account_path

	def EditAccount(self,edit_account_path):
		self.edit_account_path = edit_account_path

	def RepairAccount(self,repair_account_path):
		self.repair_account_path = repair_account_path

if __name__ == "__main__":

	multiprocessing.freeze_support()
	homedir = None
	open_subdir = None
	log_traffic = False
	log_debug = False
	cmdline = sys.argv[1:]
	n = 0
	while n < len(cmdline):
		cmd = cmdline[n]
		#DBGOUT#print n,cmd
		if cmd == '-homedir':
			n += 1
			homedir = cmdline[n]
			n += 1
		elif cmd == '-open':
			n += 1
			open_subdir = cmdline[n]
			n += 1
		elif cmd == '-logtraffic':
			log_traffic = True
			n += 1
		elif cmd == '-debug':
			log_debug = True
			n += 1
		else:
			print "unknown: ",cmd
			n += 1

	if homedir == None:
		homedir = find_gpg_homedir.find_default_homedir()

	accountAlreadyOpen = False
	if open_subdir != None and os.path.exists(homedir + os.sep + open_subdir + os.sep + 'config.txt') == True:
		open_account_path = homedir + os.sep + open_subdir
		guiobj = gui.gui()
		gui_params = [ 'gui.py','-homedir', open_account_path,'-chooser' ]
		if log_debug == True:
			gui_params.append('-debug')
		if log_traffic == True:
			gui_params.append('-logtraffic')
		res = guiobj.main(gui_params)
		guiobj = None
		if res == 'INUSE':
			accountAlreadyOpen = True
		else:
			sys.exit(0)

	openAfterSave = False
	while True:
		app = RunApp(homedir,open_subdir,log_traffic,log_debug,accountAlreadyOpen)
		app.MainLoop()
		if app.open_account_path != None:
			#DBGOUT#logging.basicConfig(level=logging.DEBUG, 
       			#DBGOUT#format="%(asctime)s %(levelname)-5s %(name)-10s %(threadName)-10s %(message)s")
			guiobj = gui.gui()
			gui_params = [ 'gui.py','-homedir', app.open_account_path,'-chooser' ]
			if log_debug == True:
				gui_params.append('-debug')
			if log_traffic == True:
				gui_params.append('-logtraffic')
			res = guiobj.main(gui_params)
			if res == 'INUSE':
				accountAlreadyOpen = True
				app = None
			else:
				sys.exit(0)
		elif app.edit_account_path != None:
			edit_account_path = app.edit_account_path
			cdlg = config_dialog.RunApp(app.edit_account_path,pos = app.chooserPos)
			cdlg.MainLoop()
			openAfterSave = cdlg.openAfterSave
			easySetupPath = cdlg.easySetupPath
			app.edit_account_path = None
			cdlg = None
			app = None
			if openAfterSave == True:
				#DBGOUT#logging.basicConfig(level=logging.DEBUG, 
       				#DBGOUT#format="%(asctime)s %(levelname)-5s %(name)-10s %(threadName)-10s %(message)s")
				if easySetupPath != None:
					edit_account_path = easySetupPath
				guiobj = gui.gui()
				gui_params = [ 'gui.py','-homedir', edit_account_path,'-chooser' ]
				if log_debug == True:
					gui_params.append('-debug')
				if log_traffic == True:
					gui_params.append('-logtraffic')
				res = guiobj.main(gui_params)
				if res == 'INUSE':
					accountAlreadyOpen = True
				else:
					sys.exit(0)
		elif app.repair_account_path != None:
			rdlg = repair_account.RunApp(app.repair_account_path,pos = app.chooserPos)
			rdlg.MainLoop()
			app.repair_account_path = None
			rdlg = None
			app = None
		else:
			sys.exit(0)
	

# EOF
