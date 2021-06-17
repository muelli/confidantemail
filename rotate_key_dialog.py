import sys
import wx
import global_config
import rotate_key
import images2

id_rotate = 1
id_restore = 2
id_delback = 3
id_cancel = 4
id_help = 5

class RotateKeyFrame(wx.Frame):

	def __init__(self,parent,gpgpath,homedir,keyid_hex,passphrase,size,pos=None):
		self.parent = parent
		self.gpgpath = gpgpath
		self.homedir = homedir
		self.passphrase = passphrase
		self.keyid_hex = keyid_hex
		self.update_key = False

		title = 'Rotate Encryption Subkey'
		if pos == None:
			wx.Frame.__init__(self,parent,-1,title,size=size)
		else:
			wx.Frame.__init__(self,parent,-1,title,pos=pos,size=size)

		mainPanel = wx.Panel(self,-1,size=self.GetClientSize())
		panelSizer = wx.BoxSizer(wx.VERTICAL)
		panelSizer.Add(mainPanel,1,wx.ALL|wx.GROW,0)

		mainSizer = wx.BoxSizer(wx.VERTICAL)
		hsizer = wx.BoxSizer(wx.HORIZONTAL)
		self.textCtrl = wx.TextCtrl(mainPanel,-1,style = wx.TE_MULTILINE|wx.TE_READONLY)
		self.rotateButton = wx.Button(mainPanel,id_rotate,"Rotate Key")
		self.restoreButton = wx.Button(mainPanel,id_restore,"Restore Backup")
		self.delbackButton = wx.Button(mainPanel,id_delback,"Destroy Backup")
		self.cancelButton = wx.Button(mainPanel,id_cancel,"Cancel")
		self.helpButton = wx.Button(mainPanel,id_help,"Help")
		self.restoreButton.Disable()
		self.delbackButton.Disable()
		hsizer.Add(self.rotateButton,0,wx.ALL,5)
		hsizer.Add(self.restoreButton,0,wx.ALL,5)
		hsizer.Add(self.delbackButton,0,wx.ALL,5)
		hsizer.Add(self.cancelButton,0,wx.ALL,5)
		hsizer.Add(self.helpButton,0,wx.ALL,5)
		mainSizer.Add(self.textCtrl,1,wx.ALL|wx.GROW,1)
		mainSizer.Add(hsizer,0,wx.ALIGN_CENTER_HORIZONTAL)
		mainPanel.SetSizer(mainSizer)
		self.SetSizer(panelSizer)
		if sys.platform == 'darwin':
			hsizer.Layout()
			panelSizer.Layout()
			mainSizer.Layout()
		self.Bind(wx.EVT_BUTTON,self.OnRotateButton,self.rotateButton)
		self.Bind(wx.EVT_BUTTON,self.OnRestoreButton,self.restoreButton)
		self.Bind(wx.EVT_BUTTON,self.OnDelbackButton,self.delbackButton)
		self.Bind(wx.EVT_BUTTON,self.OnCancelButton,self.cancelButton)
		self.Bind(wx.EVT_BUTTON,self.OnHelpButton,self.helpButton)
		self.Bind(wx.EVT_CLOSE,self.OnClose)
		keyicon_bmp = images2.key_icon.GetBitmap()
		keyicon = wx.IconFromBitmap(keyicon_bmp)
		self.SetIcon(keyicon)

		self.rk = rotate_key.rotate_key(self.gpgpath,self.homedir,self.keyid_hex,self.OutputText)
		#self.textCtrl.AppendText("Home Directory: " + self.homeDir + "\n\n" + \
		self.textCtrl.AppendText( \
			"Your GPG key has an encryption subkey, which is used only for encrypting " + \
			"incoming messages to you. An adversary who obtains your private key, can recover " + \
			"all messages encrypted with that key. This action replaces your encryption subkey, " + \
			"without affecting your keyid or identitiy.\n" + \
			"\n" + \
			"The system retains one old encryption subkey, so after two rotations, you no longer " + \
			"have the private key for old messages. You can rotate your encryption subkey up to " + \
			"once a week without risk of losing email.\n" + \
			"\n" + \
			"To make sure you no longer have old keys, click [Rotate Key] and then [Destroy Backup].\n\n")
		self.rk.show_current_subkeys()
		self.textCtrl.AppendText( \
			"\nClick [Rotate Key] to proceed, [Help] for details, or [Cancel] to abort.\n")

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

	def OnRotateButton(self,event):
		self.rotateButton.Disable()
		wx.CallAfter(self.OnRotateButtonCont)

	def OnRotateButtonCont(self):
		result = self.rk.backup_try_key_rotation(self.passphrase)
		if result == True:
			self.OutputText("Click [Destroy Backup] to securely erase the backup.")
			self.OutputText("Click [Restore Backup] to undo the changes.")
			self.delbackButton.Enable()
			self.restoreButton.Enable()
			self.update_key = True
		self.OutputText("Click [Close] to exit.")
		self.cancelButton.SetLabel('Close')
		wx.CallAfter(self.SetFocus) # gpg 2.1.x passphrase prompt takes away focus

	def OnRestoreButton(self,event):
		self.delbackButton.Disable()
		self.restoreButton.Disable()
		self.rk.restore_gpg()
		self.OutputText("Click [Close] to exit.")

	def OnDelbackButton(self,event):
		self.delbackButton.Disable()
		self.restoreButton.Disable()
		self.rk.destroy_file(self.rk.gpgbackup)
		self.OutputText("Backup erased. Click [Close] to exit.")

	def OnCancelButton(self,event):
		self.OnClose(event)

	def OnHelpButton(self,event):
		self.helpcon = wx.html.HtmlHelpController(parentWindow = self)
 		wx.FileSystem.AddHandler(wx.ZipFSHandler())
		self.helpcon.AddBook(global_config.help_file,0)
		self.helpcon.DisplayContents()
		self.helpcon.Display("forward_secrecy.html")
		if global_config.resolution_scale_factor != 1.0:
			frame = self.helpcon.GetFrame()
			frameX,frameY = frame.GetSize()
			frameX *= global_config.resolution_scale_factor
			frameY *= global_config.resolution_scale_factor
			frame.SetSize( (frameX,frameY) )

	def OnClose(self,event):
		self.parent.rotateKeyDialog = None
		if self.update_key == True:
			wx.CallAfter(self.parent.OnPostKeyClick,None)
		self.Destroy()

# EOF
