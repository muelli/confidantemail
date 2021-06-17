import logging
import random
import time
import re
import wx
import wx.lib.mixins.listctrl as listmix
import images
import images2
import global_config
import filestore
import flatstore
import gnupg

id_to = 1
id_cc = 2
id_bcc = 3
id_view = 4
id_refetch = 5
id_delete = 6
id_import = 7
id_close = 8
id_key_entry = 9
id_start_search = 10
id_clear_search = 11
id_help = 12
id_specific_server = 13
id_resize_timer = 14

re_name_email = re.compile("^(.*) <([^>]+)>$")
re_key_split = re.compile("[ ,\t\r\n]+")
re_email_addr_1 = re.compile("^.*<(\S+@\S+\.\S+)>.*$")
re_email_addr_2 = re.compile("^(\S+@\S+\.\S+)$")
re_keyid = re.compile("^[^0-9A-F]*([0-9A-F]{40})[^0-9A-F]*$|^.*[^0-9A-F]+([0-9A-F]{40})[^0-9A-F]+.*$|^[^0-9A-F]*([0-9A-F]{40})[^0-9A-F]+.*$|^.*[^0-9A-F]+([0-9A-F]{40})[^0-9A-F]*$",re.IGNORECASE)
re_specific_server = re.compile("^.+:[0-9]+$")

class KeyListCtrl(wx.ListCtrl, listmix.ListCtrlAutoWidthMixin, listmix.ColumnSorterMixin):
	def __init__(self,parent):
		self.parent = parent
		self.gui = self.parent.gui
		self.sortCol = 'adr'
		self.il = wx.ImageList(16, 16)
		self.sm_up = self.il.Add(images.SmallUpArrow.GetBitmap())
		self.sm_dn = self.il.Add(images.SmallDnArrow.GetBitmap())
		wx.ListCtrl.__init__(self,parent,style = wx.LC_REPORT|wx.LC_HRULES|wx.LC_VRULES)
		self.SetImageList(self.il, wx.IMAGE_LIST_SMALL)
		listmix.ListCtrlAutoWidthMixin.__init__(self)
		self.numRows = 0
		self.InsertColumn(0,"Key ID")
		self.InsertColumn(1,"Name")
		self.InsertColumn(2,"Address")
		self.InsertColumn(3,"Bits")
		self.InsertColumn(4,"Trust")
		self.Bind(wx.EVT_LIST_ITEM_ACTIVATED,self.parent.OnActivateRow)
		listmix.ColumnSorterMixin.__init__(self, 5)
		self.RefreshKeyList()

	def RefreshKeyList(self):
		keyList = self.parent.keyList
		selList = self.parent.importedKeyIds
		self.itemDataMap = dict()
		nr = self.GetItemCount()
		if nr > 0:
			self.DeleteAllItems()
		i = 0
		firstSel = None
		for key in keyList:
			if 'noannounce' in key:
				continue
			username = key['uids'][0]
			address = ""
			m = re_name_email.match(username)
			if m:
				username = m.group(1)
				address = m.group(2)
				
			fingerprint = key['fingerprint']
			listIndex = self.InsertStringItem(i,fingerprint)
			self.SetStringItem(listIndex,1,username)
			self.SetStringItem(listIndex,2,address)
			self.SetStringItem(listIndex,3,key['length'])
			self.SetStringItem(listIndex,4,key['trust'])
			itemDataLine = [ ]
			itemDataLine.append(fingerprint)
			itemDataLine.append(username.lower())
			itemDataLine.append(address.lower())
			itemDataLine.append(key['length'])
			itemDataLine.append(key['trust'])
			itemDataLine.append(username) # for inserting
			itemDataLine.append(address) # for inserting
			self.SetItemData(listIndex,i)
			self.itemDataMap[i] = itemDataLine
			if fingerprint.lower() in selList:
				self.SetItemState(listIndex,wx.LIST_STATE_SELECTED,wx.LIST_STATE_SELECTED)
				if firstSel == None:
					firstSel = listIndex
			i += 1
		self.SetColumnWidth(0, wx.LIST_AUTOSIZE)
		self.SetColumnWidth(1, wx.LIST_AUTOSIZE)
		self.SetColumnWidth(2, wx.LIST_AUTOSIZE)
		self.SetColumnWidth(3, wx.LIST_AUTOSIZE)
		self.SetColumnWidth(4, wx.LIST_AUTOSIZE)
		sortIndex,sortDir = self.GetSortState()
		if sortIndex < 0:
			sortIndex = 2 # address
			sortDir = 1 # up
		self.SortListItems(sortIndex,sortDir)
		if firstSel != None:
			firstSel = self.GetFirstSelected() # moved after sort
			if firstSel >= 0:
				self.EnsureVisible(firstSel) # if user imported a key, show it to him
		#DBGOUT#print "done loading"

	# Used by the ColumnSorterMixin, see wx/lib/mixins/listctrl.py
	def GetSortImages(self):
		return (self.sm_dn, self.sm_up)

    # Used by the ColumnSorterMixin, see wx/lib/mixins/listctrl.py
	def GetListCtrl(self):
		return self

class AddToMessageButtons(wx.Panel):
    def __init__(self, parent):
		self.parent = parent
		wx.Panel.__init__(self, parent, -1)
		self.box = wx.StaticBox(self,-1,"User List Options")
		self.sizer = wx.StaticBoxSizer(self.box,wx.VERTICAL)
		self.toButton = wx.Button(self,id_to,"To -->")
		self.ccButton = wx.Button(self,id_cc,"Cc -->")
		self.bccButton = wx.Button(self,id_bcc,"Bcc -->")
		self.importButton = wx.Button(self,id_import,"Import")
		self.viewButton = wx.Button(self,id_view,"View")
		self.refetchButton = wx.Button(self,id_refetch,"Refetch")
		self.deleteButton = wx.Button(self,id_delete,"Delete")
		self.closeButton = wx.Button(self,id_close,"Close")
		self.importButton.Disable()
		self.sizer.Add(self.toButton, 0, wx.TOP|wx.LEFT, 5)
		self.sizer.Add(self.ccButton, 0, wx.TOP|wx.LEFT, 5)
		self.sizer.Add(self.bccButton, 0, wx.TOP|wx.LEFT, 5)
		self.sizer.Add(self.importButton, 0, wx.TOP|wx.LEFT, 5)
		self.sizer.Add(self.viewButton, 0, wx.TOP|wx.LEFT, 5)
		self.sizer.Add(self.refetchButton, 0, wx.TOP|wx.LEFT, 5)
		self.sizer.Add(self.deleteButton, 0, wx.TOP|wx.LEFT, 5)
		self.sizer.Add(self.closeButton, 0, wx.TOP|wx.LEFT, 5)
		self.SetSizer(self.sizer)
		self.Bind(wx.EVT_BUTTON,self.parent.OnTo,self.toButton)
		self.Bind(wx.EVT_BUTTON,self.parent.OnCC,self.ccButton)
		self.Bind(wx.EVT_BUTTON,self.parent.OnBCC,self.bccButton)
		self.Bind(wx.EVT_BUTTON,self.parent.OnClose,self.closeButton)
		self.Bind(wx.EVT_BUTTON,self.parent.OnImport,self.importButton)
		self.Bind(wx.EVT_BUTTON,self.parent.OnView,self.viewButton)
		self.Bind(wx.EVT_BUTTON,self.parent.OnDelete,self.deleteButton)
		self.Bind(wx.EVT_BUTTON,self.parent.OnRefetch,self.refetchButton)

class PasteBox(wx.Panel):
    def __init__(self, parent):
		wx.Panel.__init__(self, parent, -1)
		self.box = wx.StaticBox(self,-1,"Paste Key IDs or Email Addresses to Look Up")
		self.sizer = wx.StaticBoxSizer(self.box,wx.VERTICAL)
		self.keyEntry = wx.TextCtrl(self,id_key_entry,"",style = wx.TE_MULTILINE)
		self.sizer.Add(self.keyEntry, 1, wx.EXPAND, 10)
		self.SetSizer(self.sizer)

class SelectSearchTargets(wx.Panel):
    def __init__(self, parent):
		self.parent = parent
		wx.Panel.__init__(self, parent, -1)
		self.box = wx.StaticBox(self,-1,"Locations to Search")
		self.sizer = wx.StaticBoxSizer(self.box,wx.VERTICAL)
		self.searchEntangled = wx.CheckBox(self,-1,"Entangled")
		self.searchEntangled.SetValue(True)
		self.searchDNS = wx.CheckBox(self,-1,"DNS")
		self.searchDNS.SetValue(True)
		self.searchSpecific = wx.CheckBox(self,-1,"Specific Server")
		self.buttonSizer = wx.BoxSizer(wx.HORIZONTAL)
		self.startSearchButton = wx.Button(self,id_start_search,"Start Search")
		self.clearSearchButton = wx.Button(self,id_clear_search,"Clear Search")
		self.helpButton = wx.Button(self,id_help,"Help")
		self.specificServer = wx.TextCtrl(self,id_specific_server,"")
		self.sizer.Add(self.searchEntangled, 0, wx.TOP|wx.LEFT, 5)
		self.sizer.Add(self.searchDNS, 0, wx.TOP|wx.LEFT, 5)
		self.sizer.Add(self.searchSpecific, 0, wx.TOP|wx.LEFT, 5)
		self.sizer.Add(self.specificServer, 0, wx.TOP|wx.LEFT|wx.GROW, 5)
		self.buttonSizer.Add(self.startSearchButton, 0, wx.TOP|wx.LEFT, 5)
		self.buttonSizer.Add(self.clearSearchButton, 0, wx.TOP|wx.LEFT, 5)
		self.buttonSizer.Add(self.helpButton, 0, wx.TOP|wx.LEFT, 5)
		self.sizer.Add(self.buttonSizer, 0, wx.TOP|wx.LEFT, 0)
		self.Bind(wx.EVT_BUTTON,self.parent.OnStartSearch,self.startSearchButton)
		self.Bind(wx.EVT_BUTTON,self.parent.OnClearSearch,self.clearSearchButton)
		self.Bind(wx.EVT_BUTTON,self.parent.OnHelp,self.helpButton)
		self.SetSizer(self.sizer)

class AddressBookFrame(wx.Frame):

	def __init__(self,parent,gui):
		self.gui = gui
		self.keyList = self.gui.keyList
		self.parent = parent
		self.importedKeyIds = set()
		
		wx.Frame.__init__(self,parent,-1,'Address Book',size=gui.addr_window_size)
		self.statusBar = self.CreateStatusBar(1)
		self.topSizer = wx.BoxSizer(wx.HORIZONTAL)
		self.keyListCtrl = KeyListCtrl(self)
		self.topSizer.Add(self.keyListCtrl,1,wx.EXPAND|wx.ALL,0)
		self.addToMessageButtons = AddToMessageButtons(self)
		self.topSizer.Add(self.addToMessageButtons,0,wx.EXPAND|wx.ALL,0)

		self.bottomSizer = wx.BoxSizer(wx.HORIZONTAL)
		self.pasteBox = PasteBox(self)
		self.bottomSizer.Add(self.pasteBox,1,wx.EXPAND|wx.ALL,0)
		self.selectTargets = SelectSearchTargets(self)
		self.bottomSizer.Add(self.selectTargets,1,wx.EXPAND|wx.ALL,0)

		self.mainSizer = wx.BoxSizer(wx.VERTICAL)
		self.mainSizer.Add(self.topSizer,5,wx.EXPAND|wx.ALL,0)
		self.mainSizer.Add(self.bottomSizer,3,wx.EXPAND|wx.ALL,0)
		self.SetSizer(self.mainSizer)

		self.Bind(wx.EVT_CLOSE,self.OnClose)
		self.lastSearchUpdate = 0.0
		self.lastSearchUpdateSkipped = False
		self.viewImportMode = False

		keyicon_bmp = images2.key_icon.GetBitmap()
		keyicon = wx.IconFromBitmap(keyicon_bmp)
		self.SetIcon(keyicon)

	def OnTo(self,event):
		self.addRecipients('T')

	def OnCC(self,event):
		self.addRecipients('C')

	def OnBCC(self,event):
		self.addRecipients('B')

	def OnRefetch(self,event):
		selected = -1
		keyList = [ ]
		while True:
			selected = self.keyListCtrl.GetNextItem(selected,state = wx.LIST_STATE_SELECTED)
			if selected < 0:
				break
			row = self.keyListCtrl.GetItemData(selected)
			keyList.append(self.keyListCtrl.itemDataMap[row][0].lower().encode('ascii','ignore'))
		if len(keyList) > 0:
			searchCommand = [ 'REF_KEY_SEARCH',keyList ]
			self.gui.to_agent_queue.put(searchCommand)
			self.addToMessageButtons.refetchButton.Disable()

	def LoadKeyList(self,useTempKeys):
		if useTempKeys == True:
			self.keyList = self.gui.temp_gpg.list_keys()
		else:
			self.keyList = self.gui.gpg.list_keys()
		for key in self.keyList:
			if useTempKeys == False:
				keyid = key['fingerprint']
				found,data = self.gui.local_store.retrieve(keyid)
				if found == False:
					key['noannounce'] = True # don't display keys we don't have announce for
			
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
		self.keyListCtrl.RefreshKeyList()

	def addRecipients(self,toccbcc):
		selectedList = [ ]
		selected = -1
		while True:
			selected = self.keyListCtrl.GetNextItem(selected,state = wx.LIST_STATE_SELECTED)
			if selected < 0:
				break
			selectedList.append(self.keyListCtrl.GetItemData(selected))

		recipients = [ ]
		for row in selectedList:
			keyid = self.keyListCtrl.itemDataMap[row][0].lower()
			name = self.keyListCtrl.itemDataMap[row][5]
			address = self.keyListCtrl.itemDataMap[row][6]
			adr_out = ''
			if name != None:
				adr_out += name
			if address != None:
				adr_out += ' <' + address + '>'
			adr_out += ' ' + keyid
			recipients.append(adr_out)
		self.parent.InsertAddressesFromBook(toccbcc,recipients)

	def DisplayNewFoundKey(self,keyid):
		nowTime = time.time()
		if (nowTime - self.lastSearchUpdate) >= 2.0:
			self.LoadKeyList(True)
			self.lastSearchUpdate = time.time()
			self.lastSearchUpdateSkipped = False
		else:
			self.lastSearchUpdateSkipped = True

	def OnStartSearch(self,event):
		self.lastSearchUpdateSkipped = False
		keyText = self.pasteBox.keyEntry.GetValue()
		keyListIn = re_key_split.split(keyText)
		keyList = [ ]
		keyListStr = ''
		for keyIn in keyListIn:	
			#DBGOUT#print "*",keyIn
			keyOut = None
			m = re_email_addr_1.match(keyIn)
			if m:
				keyOut = m.group(1)
			else:
				m = re_email_addr_2.match(keyIn)
				if m:
					keyOut = m.group(1)
					l = len(keyOut) - 1
					if keyOut[0] == '<' and keyOut[l] == '>':
						keyOut = keyOut[1:l]
				else:
					m = re_keyid.match(keyIn)
					if m:
						keyOut = m.group(1)
						if keyOut == None or keyOut == '':
							keyOut = m.group(2)
						if keyOut == None or keyOut == '':
							keyOut = m.group(3)
						if keyOut == None or keyOut == '':
							keyOut = m.group(4)
					if keyOut != None:
						keyOut = keyOut.decode('hex').encode('hex') # Strip out Unicode in the hex string
			if keyOut != None:
				keyOutL = keyOut.lower()
				if keyOutL not in keyList:
					keyList.append(keyOutL)	
					keyListStr += keyOut + "\n"
		self.pasteBox.keyEntry.SetValue(keyListStr)

		if len(keyList) == 0:
			self.SetStatusText('Please paste or type one or more key ids or email addresses.')
			self.pasteBox.keyEntry.SetFocus()
			return

		optSearchEntangled = self.selectTargets.searchEntangled.GetValue()
		optSearchDNS = self.selectTargets.searchDNS.GetValue()
		optSearchSpecific = self.selectTargets.searchSpecific.GetValue()
		optSpecificServer = None
		if optSearchSpecific == True:
			optSpecificServer = self.selectTargets.specificServer.GetValue()
			if optSpecificServer == '' or re_specific_server.match(optSpecificServer) == None:
				optSpecificServer = None
				self.SetStatusText('Please enter server-name:port-number to search a Specific Server',0)
				self.selectTargets.specificServer.SetFocus()
				return
			elif optSpecificServer.lower()[0:7] != 'server=':
				optSpecificServer = 'server='+optSpecificServer

		if (optSearchEntangled == True or optSearchDNS == True or optSpecificServer != None) and len(keyList) > 0:
			searchCommand = [ 'AB_KEY_SEARCH',optSearchEntangled,optSearchDNS,optSpecificServer,keyList ]
			self.gui.to_agent_queue.put(searchCommand)
			self.keyListCtrl.DeleteAllItems()
			self.addToMessageButtons.toButton.Disable()
			self.addToMessageButtons.ccButton.Disable()
			self.addToMessageButtons.bccButton.Disable()
			self.addToMessageButtons.importButton.Enable()
			self.addToMessageButtons.refetchButton.Disable()
			self.addToMessageButtons.deleteButton.Disable()
			self.selectTargets.startSearchButton.Disable()
			self.selectTargets.startSearchButton.Disable()
			self.viewImportMode = True
		else:
			self.SetStatusText('No locations selected. Check at least one of Entangled, DNS, or Specific Server.',0)
		#DBGOUT#print keyListStr

	def OnClearSearch(self,event):
		self.addToMessageButtons.toButton.Enable()
		self.addToMessageButtons.ccButton.Enable()
		self.addToMessageButtons.bccButton.Enable()
		self.addToMessageButtons.importButton.Disable()
		self.addToMessageButtons.refetchButton.Enable()
		self.addToMessageButtons.deleteButton.Enable()
		self.selectTargets.startSearchButton.Enable()
		self.selectTargets.startSearchButton.Enable()
		self.LoadKeyList(False)
		self.viewImportMode = False

	def OnHelp(self,event):
		self.helpcon = wx.html.HtmlHelpController(parentWindow = self)
 		wx.FileSystem.AddHandler(wx.ZipFSHandler())
		self.helpcon.AddBook(global_config.help_file,0)
		self.helpcon.DisplayContents()
		self.helpcon.Display("address_book.html")
		if global_config.resolution_scale_factor != 1.0:
			frame = self.helpcon.GetFrame()
			frameX,frameY = frame.GetSize()
			frameX *= global_config.resolution_scale_factor
			frameY *= global_config.resolution_scale_factor
			frame.SetSize( (frameX,frameY) )

	def OnImport(self,event):
		nr = self.keyListCtrl.GetItemCount()
		if nr == 0:
			return
		selected = -1
		keyids = [ ]
		while True:
			selected = self.keyListCtrl.GetNextItem(selected,state = wx.LIST_STATE_SELECTED)
			if selected < 0:
				break
			row = self.keyListCtrl.GetItemData(selected)
			keyid = self.keyListCtrl.itemDataMap[row][0].lower()
			keyids.append(keyid)
			self.importedKeyIds.add(keyid)
		if len(keyids) > 0:
			importCommand = [ 'AB_KEY_IMPORT',keyids ]
			self.gui.to_agent_queue.put(importCommand)

	def OnActivateRow(self,event): # from the ListCtrl
		if self.viewImportMode == True:
			self.OnImport(event)
		else:
			self.addRecipients('T')
			self.OnClose(event)

	def OnView(self,event):
		#DBGOUT#print "OnView"
		nr = self.keyListCtrl.GetItemCount()
		if nr == 0:
			return
		selected = -1
		keyids = [ ]
		while True:
			selected = self.keyListCtrl.GetNextItem(selected,state = wx.LIST_STATE_SELECTED)
			if selected < 0:
				break
			row = self.keyListCtrl.GetItemData(selected)
			keyids.append(self.keyListCtrl.itemDataMap[row][0].lower())

		if len(keyids) == 0:
			return

		textOut = ''
		for keyid in keyids:
			keyidL = keyid.lower()
			if self.viewImportMode == True:
				found,lines = self.gui.tempkeys.retrieveHeaders(keyid)
			else:
				found,lines = self.gui.local_store.retrieveHeaders(keyid)
			if found == False:
				continue

			copyOn = False
			textOut += "Keyid: " + keyid + "\n"
			for line in lines:
				line = line.decode('utf-8')
				if copyOn == False and line == '':
					copyOn = True
				elif copyOn == True and line == '':
					break
				elif copyOn == True:
					textOut += line + "\n"
			for keydata in self.gui.keyList:
				if keydata['fingerprint'].lower() == keyidL:
					for k in [ 'expires','subkeys','ownertrust','algo','trust' ]:
						if k in keydata:
							textOut += k + ': ' + str(keydata[k]) + "\n"
					break
			textOut += "\n"	

		kvf = KeyViewFrame(self,textOut)

	def OnDelete(self,event):
		nr = self.keyListCtrl.GetItemCount()
		if nr == 0:
			return
		selected = -1
		keyids = [ ]
		while True:
			selected = self.keyListCtrl.GetNextItem(selected,state = wx.LIST_STATE_SELECTED)
			if selected < 0:
				break
			row = self.keyListCtrl.GetItemData(selected)
			keyids.append(self.keyListCtrl.itemDataMap[row][0].lower())
		if len(keyids) > 0:
			if len(keyids) == 1:
				message = "Delete selected public key?"
			else:
				message = "Delete " + str(len(keyids)) + " public keys?"
			answer = wx.MessageBox(message,"Confirm delete",wx.YES_NO|wx.ICON_EXCLAMATION,self)
			if answer == wx.YES:
				deleteCommand = [ 'AB_KEY_DELETE',keyids ]
				self.gui.to_agent_queue.put(deleteCommand)

	def OnClientAgentMessage(self,event): # this is pass thru from list window
		if event.cmd == 'SET_AB_STATUS_LINE':
			self.SetStatusText(event.args[0],0)
		elif event.cmd == 'AB_KEY_FOUND':
			self.DisplayNewFoundKey(event.args[0])
		elif event.cmd == 'AB_KEY_SEARCH_DONE':
			self.selectTargets.startSearchButton.Enable()
			if self.lastSearchUpdateSkipped == True:
				self.LoadKeyList(True)
		elif event.cmd == 'AB_KEY_IMP_DEL_DONE':
			self.OnClearSearch(None)
			self.importedKeyIds = set() # reset
			self.gui.keyList = self.keyList # the one time when we replace the global one
		elif event.cmd == 'AB_REF_KEY_SEARCH_DONE':
			self.addToMessageButtons.refetchButton.Enable()

	def OnClose(self,event):
		#DBGOUT#print "Closing address book"
		self.parent.parent.openAddressBook = None
		self.Destroy()
		
class KeyViewFrame(wx.Frame):
	def __init__(self,parent,text):
		self.parent = parent
		self.title = "View Keys"
		wx.Frame.__init__(self,self.parent,-1,self.title,size=self.parent.gui.addr_window_size)
		self.mainSizer = wx.BoxSizer(wx.VERTICAL)
		self.textCtrl = wx.TextCtrl(self, style=wx.HSCROLL|wx.TE_MULTILINE|wx.TE_READONLY)
		self.mainSizer.Add(self.textCtrl,1,wx.EXPAND,0)
		self.textCtrl.SetValue(text)
		self.Show()




# EOF
