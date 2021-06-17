import sys
import logging
import os
import wx
import wx.lib.mixins.listctrl as listmix
import datetime
import re
import flatstore
import filestore
import global_config
import gui
import config_dialog
import repair_account
import images2

id_view = 1
id_delete = 2
id_delban = 3
id_close = 4
id_help = 5

re_db = re.compile("^DATABLOCK: ([0123456789abcdef]{40})$",re.IGNORECASE)

class DequeueListCtrl(wx.ListCtrl, listmix.ListCtrlAutoWidthMixin):
	def __init__(self,parent):
		self.parent = parent
		wx.ListCtrl.__init__(self,parent,style = wx.LC_REPORT|wx.LC_HRULES|wx.LC_VRULES)
		listmix.ListCtrlAutoWidthMixin.__init__(self)
		self.numRows = 0
		self.InsertColumn(0,"Directory")
		self.InsertColumn(1,"Type")
		self.InsertColumn(2,"Date/Time")
		self.InsertColumn(3,"Message ID")

class MessageViewFrame(wx.Frame):
	def __init__(self,parent,text):
		self.parent = parent
		self.title = "View Messages"
		wx.Frame.__init__(self,self.parent,-1,self.title,size=self.parent.windowSize)
		self.mainSizer = wx.BoxSizer(wx.VERTICAL)
		self.textCtrl = wx.TextCtrl(self, style=wx.HSCROLL|wx.TE_MULTILINE|wx.TE_READONLY)
		self.mainSizer.Add(self.textCtrl,1,wx.EXPAND,0)
		self.textCtrl.SetValue(text)
		keyicon_bmp = images2.key_icon.GetBitmap()
		keyicon = wx.IconFromBitmap(keyicon_bmp)
		self.SetIcon(keyicon)
		self.Show()

class DequeueDialogFrame(wx.Frame):

	def __init__(self,parent,size,homedir,pos=None):
		title = 'Dequeue Bad Messages'
		if pos == None:
			wx.Frame.__init__(self,parent,-1,title,size=size)
		else:
			wx.Frame.__init__(self,parent,-1,title,pos=pos,size=size)

		self.homedir = homedir	

		mainPanel = wx.Panel(self,-1,size=self.GetClientSize())
		panelSizer = wx.BoxSizer(wx.VERTICAL)
		panelSizer.Add(mainPanel,1,wx.ALL|wx.GROW,0)

		self.statusBar = self.CreateStatusBar(1)
		mainSizer = wx.BoxSizer(wx.VERTICAL)
		hsizer = wx.BoxSizer(wx.HORIZONTAL)
		self.chooserList = DequeueListCtrl(mainPanel)
		self.viewButton = wx.Button(mainPanel,id_view,"View")
		self.deleteButton = wx.Button(mainPanel,id_delete,"Delete")
		self.delbanButton = wx.Button(mainPanel,id_delban,"Delete and Ban")
		self.closeButton = wx.Button(mainPanel,id_close,"Close")
		self.helpButton = wx.Button(mainPanel,id_help,"Help")
		hsizer.Add(self.viewButton,0,wx.ALL,5)
		hsizer.Add(self.deleteButton,0,wx.ALL,5)
		hsizer.Add(self.delbanButton,0,wx.ALL,5)
		hsizer.Add(self.closeButton,0,wx.ALL,5)
		hsizer.Add(self.helpButton,0,wx.ALL,5)
		mainSizer.Add(self.chooserList,1,wx.ALL|wx.GROW,1)
		mainSizer.Add(hsizer,0,wx.ALIGN_CENTER_HORIZONTAL)
		mainPanel.SetSizer(mainSizer)
		self.SetSizer(panelSizer)
		keyicon_bmp = images2.key_icon.GetBitmap()
		keyicon = wx.IconFromBitmap(keyicon_bmp)
		self.SetIcon(keyicon)
		self.Bind(wx.EVT_BUTTON,self.OnView,self.viewButton)
		self.Bind(wx.EVT_BUTTON,self.OnDelete,self.deleteButton)
		self.Bind(wx.EVT_BUTTON,self.OnDelban,self.delbanButton)
		self.Bind(wx.EVT_BUTTON,self.OnCloseButton,self.closeButton)
		self.Bind(wx.EVT_BUTTON,self.OnHelp,self.helpButton)
		self.Bind(wx.EVT_CLOSE,self.OnClose)
		self.windowSize = self.GetSize()

		self.prepmsgs = flatstore.flatstore(self.homedir + os.sep + "prepmsgs")
		self.complete_store = flatstore.flatstore(self.homedir + os.sep + "complete")
		self.incomplete_store = flatstore.flatstore(self.homedir + os.sep + "incomplete")
		self.outbox_store = flatstore.flatstore(self.homedir + os.sep + "outbox")
		self.local_store = filestore.filestore(self.homedir + os.sep + "localstore")

		self.loadMessageList()

	def getFileDate(self,filepath):
		try:
			statf = os.stat(filepath)
			filedate = statf.st_mtime
			dtobj = datetime.datetime.fromtimestamp(filedate)
			dtstr = dtobj.strftime("%a %Y-%m-%d %I:%M:%S %p")
			return dtstr
		except Exception:
			return 'unknown'

	def loadMessageList(self):
		self.messageList = [ ]

		for filename in self.prepmsgs.keys():
			filename = filename.encode('hex').upper()
			filedate = self.getFileDate(self.prepmsgs.getPath(filename))
			self.messageList.append( ("prepmsgs","Outgoing prep",filedate,filename) )
		for filename in self.complete_store.keys():
			filename = filename.encode('hex').upper()
			filedate = self.getFileDate(self.complete_store.getPath(filename))
			self.messageList.append( ("complete","Incoming complete",filedate,filename) )
		for filename in self.incomplete_store.keys():
			filename = filename.encode('hex').upper()
			filedate = self.getFileDate(self.incomplete_store.getPath(filename))
			self.messageList.append( ("incomplete","Incoming incomplete",filedate,filename) )
		for filename in self.outbox_store.keys():
			filename = filename.encode('hex').upper()
			filedate = self.getFileDate(self.outbox_store.getPath(filename))
			self.messageList.append( ("outbox","Outgoing complete",filedate,filename) )

		self.chooserList.DeleteAllItems()
		i = 0
		for line in self.messageList:
			dir,type,filedate,filename = line
			listIndex = self.chooserList.InsertStringItem(i,dir)
			self.chooserList.SetStringItem(listIndex,1,type)
			self.chooserList.SetStringItem(listIndex,2,filedate)
			self.chooserList.SetStringItem(listIndex,3,filename)
			self.chooserList.SetItemData(listIndex,i)
			i += 1
		
		if len(self.messageList) == 0:
			listIndex = self.chooserList.InsertStringItem(0,'-')
			self.chooserList.SetStringItem(listIndex,1,'-')
			self.chooserList.SetStringItem(listIndex,2,'-')
			self.chooserList.SetStringItem(listIndex,3,'No queued messages found')
			self.viewButton.Disable()
			self.deleteButton.Disable()
			self.delbanButton.Disable()
		
		self.chooserList.SetColumnWidth(0, wx.LIST_AUTOSIZE)
		self.chooserList.SetColumnWidth(1, wx.LIST_AUTOSIZE)
		self.chooserList.SetColumnWidth(2, wx.LIST_AUTOSIZE)
		self.chooserList.SetColumnWidth(3, wx.LIST_AUTOSIZE)

	def GetSelectedRows(self):
		nr = self.chooserList.GetItemCount()
		if nr == 0:
			return
		selected = -1
		selectedRows = [ ]
		while True:
			selected = self.chooserList.GetNextItem(selected,state = wx.LIST_STATE_SELECTED)
			if selected < 0:
				break
			row = self.chooserList.GetItemData(selected)
			selectedRows.append(row)
		return selectedRows

	def OnView(self,event):
		selectedRows = self.GetSelectedRows()
		if len(selectedRows) == 0:
			return

		textOut = unicode()
		for row in selectedRows:
			dir,type,filedate,filename = self.messageList[row]
			textOut += filename + ' in ' + dir + ' modified ' + filedate + '\n'
			if dir == 'incomplete':
				found,lines = self.incomplete_store.retrieveHeaders(filename)
			elif dir == 'complete':
				found,lines = self.complete_store.retrieveHeaders(filename)
			elif dir == 'outbox':
				found,lines = self.outbox_store.retrieveHeaders(filename)
			if (dir == 'incomplete' or dir == 'complete' or dir == 'outbox') and found == True:
				for line in lines:
					textOut += line.decode('utf-8') + '\n'
				textOut += '\n'
			if dir == 'prepmsgs':
				found,message = self.prepmsgs.retrievePickle(filename)
				if found == True:
					recipients,recipients_full,attachments,reply_thread_id,forward_original_id,subject,body_text,body_html,body_xml,nowtime = message
					for rec in recipients_full:
						if rec[0] == 'T':
							textOut += 'To: ' + rec[2:].decode('utf-8') + '\n'
						elif rec[0] == 'C':
							textOut += 'Cc: ' + rec[2:].decode('utf-8') + '\n'
						elif rec[0] == 'B':
							textOut += 'Bcc: ' + rec[2:].decode('utf-8') + '\n'
						else:
							textOut += rec.decode('utf-8') + '\n'
					textOut += 'Subject: ' + subject.decode('utf-8') + '\n'
					textOut += '\n'

		mvf = MessageViewFrame(self,textOut)


	def OnDelete(self,event):
		selectedRows = self.GetSelectedRows()
		if len(selectedRows) == 0:
			return
		elif len(selectedRows) == 1:
			message = "Incoming messages will be re-downloaded. Delete selected message?"
		else:
			message = "Incoming messages will be re-downloaded. Delete " + str(len(selectedRows)) + " selected messages?"
		answer = wx.MessageBox(message,"Confirm delete",wx.YES_NO|wx.ICON_EXCLAMATION,self)
		if answer == wx.YES:
			self.DeleteDelbanCommon(selectedRows,False)	

	def OnDelban(self,event):
		selectedRows = self.GetSelectedRows()
		if len(selectedRows) == 0:
			return
		elif len(selectedRows) == 1:
			message = "Incoming messages will not be re-downloaded. Delete selected message?"
		else:
			message = "Incoming messages will not be re-downloaded. Delete " + str(len(selectedRows)) + " selected messages?"
		answer = wx.MessageBox(message,"Confirm delete",wx.YES_NO|wx.ICON_EXCLAMATION,self)
		if answer == wx.YES:
			self.DeleteDelbanCommon(selectedRows,True)	

	def DeleteIncomingMessage(self,filename,lines,banMode):
		for line in lines:
			m = re_db.match(line)
			if m:
				delhash = m.group(1)
				delpath = self.local_store.getPath(delhash)
				if os.path.exists(delpath):
					os.unlink(delpath)
		delpath = self.local_store.getPath(filename)
		if os.path.exists(delpath):
			os.unlink(delpath)
		if banMode == True:
			filehandle = open(delpath + '.DEL','w')
			filehandle.write(datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ") + '\n')
			filehandle.close()

	def DeleteDelbanCommon(self,selectedRows,banMode):
		for row in selectedRows:
			dir,type,filedate,filename = self.messageList[row]
			if dir == 'incomplete':
				found,lines = self.incomplete_store.retrieveHeaders(filename)
				if found == True:
					self.DeleteIncomingMessage(filename,lines,banMode)
					self.incomplete_store.__delitem__(filename)
			elif dir == 'complete':
				found,lines = self.complete_store.retrieveHeaders(filename)
				if found == True:
					self.DeleteIncomingMessage(filename,lines,banMode)
					self.complete_store.__delitem__(filename)
			elif dir == 'outbox':
				self.outbox_store.__delitem__(filename)
			elif dir == 'prepmsgs':
				self.prepmsgs.__delitem__(filename)
		self.loadMessageList()

	def OnCloseButton(self,event):
		self.OnClose(event)
		
	def OnHelp(self,event):
		self.helpcon = wx.html.HtmlHelpController(parentWindow = self)
 		wx.FileSystem.AddHandler(wx.ZipFSHandler())
		self.helpcon.AddBook(global_config.help_file,0)
		self.helpcon.DisplayContents()
		self.helpcon.Display("config_chooser.html")

	def OnClose(self,event):
		self.Destroy()

# EOF
