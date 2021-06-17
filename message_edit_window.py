import re
import wx
import wx.grid
import wx.richtext as rt
import wx._richtext # for EVT_RICHTEXT_CONSUMING_CHARACTER hack
import os
import sys
import images
import images2
import cStringIO
import enchant
import codecs
import hashlib
import zipfile
import multiprocessing
import pickle
import datetime
import folders
import global_config
import address_book
import message_list_window

re_keyid = re.compile("^.*\s\s*([0-9A-F]{40})\s*$|^\s*([0-9A-F]{40})\s*$",re.IGNORECASE)
re_hexkey = re.compile("^[0-9A-F]{40}$",re.IGNORECASE)
re_key_transport = re.compile("KeyTransport-([0123456789abcdef]{40}): (server=.*)$|KeyTransport-([0123456789abcdef]{40}): (entangled)$",re.IGNORECASE)
re_bracketed_email = re.compile(".*\s\s*<(\S*@\S*)>.*")
re_oneword = re.compile("^\W*(\w+)\W*$",re.UNICODE|re.LOCALE)
id_attach = 1
id_add_picture = 2
id_address_book = 3
id_send = 4
id_send_later = 5
id_edit = 6
id_save_draft = 7
id_archive = 8
id_delete = 9
id_cancel = 10
id_spell_next = 11
id_spell_prev = 12
id_spell_suggest = 13
id_smaller = 14
id_larger = 15
id_find = 16
id_hash_timer = 17
id_spell_enable_timer = 18
id_file_save_html = 101
id_file_page_setup = 102
id_file_print_preview = 103
id_file_print = 104

re_ack = re.compile("Ack-([0123456789abcdef]{40}): ([0123456789abcdef]{40})$",re.IGNORECASE)
re_datetime = re.compile("^DATE: (\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ)$",re.IGNORECASE)
re_imageformats = re.compile(".*\.bmp$|.*\.png$|.*\.jpg$|.*\.jpeg$|.*\.gif$|.*\.pcx$|.*\.pnm$|.*\.tif$|.*\.tiff$|.*\.tga$|.*\.iff$|.*\.xpm$|.*\.ico$|.*\.cur$|.*\.ani$",re.IGNORECASE)

# https://wiki.python.org/moin/EscapingHtml
html_escape_table = { "&": "&amp;", '"': "&quot;", "'": "&apos;", ">": "&gt;", "<": "&lt;", }
def html_escape(text):
	"""Produce entities within text."""
	return "".join(html_escape_table.get(c,c) for c in text)

class AddressGrid(wx.grid.Grid):
	def __init__(self,parent,topFrame,maxRowsToDisplay):
		self.parent = parent
		self.topFrame = topFrame
		self.gui = self.topFrame.gui
		self.maxRowsToDisplay = maxRowsToDisplay
		self.shiftDown = False
		self.enterPressed = False
		wx.grid.Grid.__init__(self,parent,-1)
		self.EnableDragColSize(False)
		self.EnableDragRowSize(False)
		self.CreateGrid(3,2)
		self.SetRowLabelAlignment(wx.ALIGN_RIGHT,wx.ALIGN_CENTRE)
		self.SetRowLabelValue(0,"From")
		self.SetCellValue(0,0,self.topFrame.parent.from_address)
		self.SetRowLabelValue(1,"To")
		self.SetCellValue(1,1,"+")
		self.SetCellAlignment(1,1,wx.ALIGN_CENTRE,wx.ALIGN_CENTRE)
		self.SetRowLabelValue(2,"Subject")
		self.SetCellAlignment(2,1,wx.ALIGN_CENTRE,wx.ALIGN_CENTRE)
		self.SetGridCursor(1,0)
		self.SetReadOnly(0,0,True)
		for i in range(3):
			self.SetReadOnly(i,1,True)
		self.HideColLabels()
		self.SetRowLabelSize(wx.grid.GRID_AUTOSIZE)
		self.Bind(wx.EVT_SIZE,self.OnResize)
		self.parent.Bind(wx.EVT_SPLITTER_SASH_POS_CHANGED,self.OnSashPosChanged)
		self.Bind(wx.grid.EVT_GRID_SELECT_CELL, self.OnSelectCell)
		self.Bind(wx.grid.EVT_GRID_CELL_CHANGED, self.OnCellChanged)
		self.Bind(wx.grid.EVT_GRID_LABEL_LEFT_CLICK, self.OnLabelClick)
		self.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)
		self.Bind(wx.EVT_KEY_UP, self.OnKeyUp)

	def OnResize(self,event):
		# derived from http://forums.wxwidgets.org/viewtopic.php?t=90
		# this resizes the entry field to fit the window
		clientSize = self.GetClientSize()
		windowWidth = clientSize.GetWidth()
		self.AutoSizeColumn(1)
		restWidth = self.GetRowLabelSize() + self.GetColSize(1)
		colWidth = windowWidth - restWidth
		if colWidth > 0:
			self.SetColSize(0,colWidth)

	def OnKeyUp(self, evt):
		kc = evt.GetKeyCode()
		if kc == wx.WXK_SHIFT:
			self.shiftDown = False

	def OnKeyDown(self, evt):
		kc = evt.GetKeyCode()
		self.enterPressed = False

		if kc == wx.WXK_SHIFT:
			self.shiftDown = True

		elif kc == wx.WXK_RETURN:
			self.shiftDown = False
			row = self.GetGridCursorRow()
			maxRow = self.GetNumberRows()
			if row < (maxRow - 1):
				self.enterPressed = True
				self.SetGridCursor(row,0) # force cell changed event
			else:
				self.topFrame.rtc.SetFocus()

		elif kc == wx.WXK_TAB:
			row = self.GetGridCursorRow()
			if self.shiftDown == True:
				if row > 0:
					self.SetGridCursor(row - 1,0)
			else:
				maxRow = self.GetNumberRows()
				if row < (maxRow - 1):
					self.SetGridCursor(row + 1,0)
				else:
					self.topFrame.rtc.SetFocus()

		else:
			self.shiftDown = False
			evt.Skip()

	def OnCellChanged(self,event):
		self.ValidateAfterCellChanged(event.GetRow())

	def ValidateAfterCellChanged(self,row):
		label = self.GetRowLabelValue(row)
		self.topFrame.SetStatusText("")	
		matchFound = False
		dupeFound = False
		if label == 'To' or label == 'Cc' or label == 'Bcc':
			address = self.GetCellValue(row,0)
			matches = self.ValidateAddress(address)
			#DBGOUT#print 'Address lookup',row,"adr",address,matches
			nm = len(matches)
			if nm == 0:
				self.topFrame.SetStatusText("No matches found. Use the Address Book to look up keys.")
			elif nm == 1:
				addr = matches[0]['uids'][0] + ' ' + (matches[0]['fingerprint'].lower())
				nr = self.GetNumberRows()
				for i in range(1,nr):
					label = self.GetRowLabelValue(i)
					value = self.GetCellValue(i,0)
					if (label == 'To' or label == 'Cc' or label == 'Bcc') and (value == addr): 
						msg = 'Duplicate address: ' + addr
						self.topFrame.SetStatusText(msg)	
						dupeFound = True
						break
				if dupeFound == False:
					self.SetCellValue(row,0,addr)
					matchFound = True
			else:
				msg = "Found %i addresses. Enter more text or use the Address Book." % nm
				self.topFrame.SetStatusText(msg)	

		# Give the user a new line if he pressed enter and matched
		if self.enterPressed == True and matchFound == True:
			self.enterPressed = False
			if (row - 1) < self.GetNumberRows():
				if self.GetRowLabelValue(row+1) == 'Subject':
					self.insertAddressRow(row)
					wx.CallAfter(self.SetGridCursor,row + 1,0)
					wx.CallAfter(self.EnableCellEditControl)

	def AdjustSash(self,getInitial = False):
		rowHeight = self.GetRowSize(0)
		rowsToDisplay = self.GetNumberRows()
		if rowsToDisplay > self.maxRowsToDisplay:
			rowsToDisplay = self.maxRowsToDisplay
		newSashPosition = rowsToDisplay * rowHeight
		if getInitial == True:
			return newSashPosition
		else:
			self.parent.SetSashPosition(newSashPosition)
			wx.CallAfter(self.ForceRefresh)

	def OnSashPosChanged(self,event):
		self.ForceRefresh()

	def InsertRowMoveLabels(self,row): # insert row does not move labels
		self.InsertRows(row + 1,1,False)
		r = self.GetNumberRows() - 1
		while r > row:
			self.SetRowLabelValue(r,self.GetRowLabelValue(r - 1))
			r -= 1

	def DeleteRowMoveLabels(self,row): # delete row does not move labels
		m = self.GetNumberRows() - 1
		r = row
		while r < m:
			self.SetRowLabelValue(r,self.GetRowLabelValue(r + 1))
			r += 1
		self.DeleteRows(row,1,False)

	def insertAddressRow(self,row):
		self.BeginBatch()
		self.InsertRowMoveLabels(row)
		self.SetCellValue(row + 1,1,"+")
		self.SetCellValue(row,1,"-")
		self.SetCellAlignment(row + 1,1,wx.ALIGN_CENTRE,wx.ALIGN_CENTRE)
		self.SetReadOnly(row + 1,1,True)
		self.EndBatch()
		self.AdjustSash()

	def OnSelectCell(self,event):
		sel = event.Selecting()
		row = event.GetRow()
		col = event.GetCol()
		#DBGOUT#print "Cell selected",sel,row,col
		if col == 1:
			value = self.GetCellValue(row,col)
			if value == '+': # add address
				self.insertAddressRow(row)
			elif value == '-': # remove address
				self.BeginBatch()
				self.DeleteRowMoveLabels(row)
				self.EndBatch()
				self.AdjustSash()

			elif value == 'A': # ack date
				popupWin = wx.PopupTransientWindow(self, style = wx.SIMPLE_BORDER)
				panel = wx.Panel(popupWin)
				msgstr = "Message received by\n" + self.GetCellValue(row,0) + "\non " + self.topFrame.date_formatter.localize_datetime(self.topFrame.ack_dates_by_row[row]) + "\nNote: acknowledgment date and time are not cryptographically authenticated."
				st = wx.StaticText(panel, -1, msgstr)
				sizer = wx.BoxSizer(wx.VERTICAL)
				sizer.Add(st, 0, wx.ALL, 5)
				panel.SetSizer(sizer)
				sizer.Fit(panel)
				sizer.Fit(popupWin)
				pos = event.GetPosition()
				pos = self.ClientToScreen(pos)
				pos.x += 20
				pos.y += 20
				popupWin.Position(pos,wx.DefaultSize)
				popupWin.Layout()
				popupWin.Popup()


	def OnLabelClick(self,event):
		row = event.GetRow()
		label = self.GetRowLabelValue(row)
		#DBGOUT#print "Label clicked",row,label
		if label == 'To':
			self.SetRowLabelValue(row,'Cc')
		elif label == 'Cc':
			self.SetRowLabelValue(row,'Bcc')
		elif label == 'Bcc':
			self.SetRowLabelValue(row,'To')

	def OnAttach(self,event):
		fileDialog = wx.FileDialog(self,message = "Select files to attach",
			style = wx.FD_OPEN | wx.FD_MULTIPLE)
		result = fileDialog.ShowModal()
		if result != wx.ID_OK:
			return
		existing_attachments = [ ]
		nRows = self.GetNumberRows()
		for i in range(nRows):
			label = self.GetRowLabelValue(i)
			value = self.GetCellValue(i,0)
			if label == 'Attach':
				existing_attachments.append(value)
		file_paths = fileDialog.GetPaths()
		row = self.GetNumberRows()
		self.BeginBatch()
		for fp in file_paths:
			if fp not in existing_attachments and os.path.isfile(fp):
				self.AppendRows(1)
				self.SetRowLabelValue(row,'Attach')
				self.SetCellValue(row,0,fp)
				self.SetReadOnly(row,0,True)
				self.SetCellValue(row,1,"-")
				self.SetCellAlignment(row,1,wx.ALIGN_CENTRE,wx.ALIGN_CENTRE)
				self.SetReadOnly(row,1,True)
				row += 1
		self.EndBatch()
#		self.parent.mainSizer.Layout() # Make it resize
		self.AdjustSash()
					
	def OnAddressBook(self,event):
		if self.topFrame.parent.openAddressBook != None:
			self.topFrame.parent.openAddressBook.Close()
		openAddressBook = address_book.AddressBookFrame(self.topFrame,self.topFrame.gui)
		self.topFrame.parent.openAddressBook = openAddressBook
		openAddressBook.Show()

	def ValidateAddress(self,address):
		addressL = address.lower()
		matches = [ ]
		if address == "":
			return matches
		# Exact keyid match or exact email match
		email = None
		keyid = None
		m = re_bracketed_email.match(addressL)
		if m:
			email = m.group(1).lower()
		m = re_keyid.match(addressL)
		if m:
			keyid = m.group(1)
			if keyid == None:
				keyid = m.group(2)
		if email != None or keyid != None:
			for key in self.gui.keyList:
				if 'noannounce' in key:
					continue
				if key['fingerprint'].lower() == keyid or key['adr'].lower() == email:
					matches.append(key)
					break
		# Substring email address match
		if len(matches) == 0:
			for key in self.gui.keyList:
				if 'noannounce' in key:
					continue
				if key['adr'].lower().find(addressL) >= 0:
					matches.append(key)
		# Substring name match
		if len(matches) == 0:
			for key in self.gui.keyList:
				if 'noannounce' in key:
					continue
				fnln = key['fn'] + ' ' + key['ln']
				if fnln.lower().find(addressL) >= 0:
					matches.append(key)
		# Substring keyid match
		if len(matches) == 0:
			for key in self.gui.keyList:
				if 'noannounce' in key:
					continue
				if key['fingerprint'].lower().find(addressL) >= 0:
					matches.append(key)
		return matches

class MessageEditFrame(wx.Frame):

	def __init__(self,parent,gui,title,draft_sent_hash = None,ds_from_folder = None,reply_forward_id = None,reply_forward_type = None,pos = None,size = None,addrBook = False):
		self.parent = parent
		self.gui = gui
		self.enchantDict = None
		if size == None:
			size = gui.edit_window_size
		if pos == None:
			wx.Frame.__init__(self,parent,-1,title,size=size)
		else:
			wx.Frame.__init__(self,parent,-1,title,pos=pos,size=size)
		self.already_clicked_close = False
		#self.refresh_key_list = False
		self.draft_sent_hash = draft_sent_hash
		self.reply_forward_id = reply_forward_id
		self.reply_forward_type = reply_forward_type
		self.ds_from_folder = ds_from_folder
		self.date_formatter = global_config.date_format()
		self.messageUniqueId = None
		self.isEditable = False
		self.findDialog = None
		sent_message = False
		if title[0:4] == 'Sent':
			sent_message = True
		#| wx.TB_HORZ_LAYOUT
		self.spell_enable_timer = wx.Timer(self,id = id_spell_enable_timer)
		self.spell_last_prev = False
		self.Bind(wx.EVT_TIMER,self.EnableSpellButtons,id = id_spell_enable_timer)

		self.toolbar = self.CreateToolBar( wx.TB_HORIZONTAL | wx.NO_BORDER | wx.TB_FLAT | wx.TB_TEXT )
		#tsize = (24,24)
		attach_bmp = images2.attach.GetBitmap()
		save_bmp = images2.save.GetBitmap()
		archive_bmp = images2.archive.GetBitmap()
		close_bmp = images2.closex.GetBitmap()
		delete_bmp = images2.trashcan.GetBitmap()
		abc_l_bmp = images2.abc_l.GetBitmap()
		abc_r_bmp = images2.abc_r.GetBitmap()
		abc_x_bmp = images2.abc_x.GetBitmap()
		send_bmp = images2.send.GetBitmap()
		contacts_bmp = images2.contacts.GetBitmap()
		addimage_bmp = images2.addimage.GetBitmap()
		composition_bmp = images2.composition.GetBitmap()
		smaller_bmp = images2.smaller.GetBitmap()
		larger_bmp = images2.larger.GetBitmap()
		find_bmp = images2.find.GetBitmap()
		if sent_message == True:
			self.toolbar.AddLabelTool(id_edit, "Edit", composition_bmp, shortHelp="Send again", longHelp="Send again with changes")
		else:
			self.toolbar.AddLabelTool(id_attach, "Attach", attach_bmp, shortHelp="Attach", longHelp="Attach a file")
			self.toolbar.AddLabelTool(id_add_picture, "Add Picture", addimage_bmp, shortHelp="Add Picture", longHelp="Add a picture")
			self.toolbar.AddLabelTool(id_address_book, "Address Book", contacts_bmp, shortHelp="Address Book", longHelp="Select or look up addresses")
			self.toolbar.AddLabelTool(id_send, "Send Msg", send_bmp, shortHelp="Send", longHelp="Send the message")
			self.toolbar.AddLabelTool(id_send_later, "Send Later", send_bmp, shortHelp="Send after a delay, or use 0 to proxy send immmediately", longHelp="Queue the message on the server to be sent later")
		self.toolbar.AddLabelTool(id_save_draft, "Save Draft", save_bmp, shortHelp="Save Draft", longHelp="Save to Drafts and Close")
		self.Bind(wx.EVT_TOOL,self.OnSaveDraftClick,id = id_save_draft)
		if sent_message == True:
			if self.ds_from_folder != folders.id_archive and self.ds_from_folder != folders.id_send_pending:
				self.toolbar.AddLabelTool(id_archive, "Archive", archive_bmp, shortHelp="Archive", longHelp="Move message to archive folder")
			if self.ds_from_folder != folders.id_deleted and self.ds_from_folder != folders.id_send_pending:
				self.toolbar.AddLabelTool(id_delete, "Delete", delete_bmp, shortHelp="Delete", longHelp="Delete this message")

			self.toolbar.AddLabelTool(id_cancel, "Close", close_bmp, shortHelp="Close", longHelp="Close this window")
		else:
			self.toolbar.AddLabelTool(id_cancel, "Cancel", close_bmp, shortHelp="Cancel", longHelp="Discard this message")
			self.toolbar.AddLabelTool(id_spell_prev, "Spell Prev", abc_l_bmp, shortHelp="Spell Prev", longHelp="Go to previous spelling error")
			self.toolbar.AddLabelTool(id_spell_next, "Spell Next", abc_r_bmp, shortHelp="Spell Next", longHelp="Go to next spelling error")
			self.toolbar.AddLabelTool(id_spell_suggest, "Spell Suggest", abc_x_bmp, shortHelp="Spell Suggest", longHelp="Suggest corrections for a misspelled word")
			self.Bind(wx.EVT_TOOL,self.OnSpellNextClick,id = id_spell_next)
			self.Bind(wx.EVT_TOOL,self.OnSpellPrevClick,id = id_spell_prev)
			self.Bind(wx.EVT_TOOL,self.OnSpellSuggestClick,id = id_spell_suggest)
		self.toolbar.AddLabelTool(id_smaller, "Smaller", smaller_bmp, shortHelp="Smaller", longHelp="Make text smaller without affecting the outgoing message")
		self.toolbar.AddLabelTool(id_larger, "Larger", larger_bmp, shortHelp="Larger", longHelp="Make text larger without affecting the outgoing message")
		self.toolbar.AddLabelTool(id_find, "Find", find_bmp, shortHelp="Find text", longHelp="Search for a string in the message")
		self.Bind(wx.EVT_TOOL,self.OnSmallerClick,id = id_smaller)
		self.Bind(wx.EVT_TOOL,self.OnLargerClick,id = id_larger)
		self.Bind(wx.EVT_TOOL,self.OnFindClick,id = id_find)
		if sent_message == True and self.ds_from_folder != folders.id_archive and self.ds_from_folder != folders.id_send_pending:
			self.Bind(wx.EVT_TOOL,self.OnArchiveClick,id = id_archive)
		if sent_message == True and self.ds_from_folder != folders.id_deleted and self.ds_from_folder != folders.id_send_pending:
			self.Bind(wx.EVT_TOOL,self.OnDeleteClick,id = id_delete)
		self.Bind(wx.EVT_TOOL,self.OnCancelClick,id = id_cancel)
		self.toolbar.Realize()

		keyicon_bmp = images2.key_icon.GetBitmap()
		keyicon = wx.IconFromBitmap(keyicon_bmp)
		self.SetIcon(keyicon)

		self.horizontalSplitter = wx.SplitterWindow(self,style = wx.SP_LIVE_UPDATE)
		self.mainSizer = wx.BoxSizer(wx.VERTICAL)
		self.addressGrid = AddressGrid(self.horizontalSplitter,self,8)
		self.bottomPanel = wx.Panel(self.horizontalSplitter)
		self.bottomPanel.SetSizer(self.mainSizer)
		self.initRtfEditor(sent_message)
		addressRowHeight = self.addressGrid.GetRowSize(0)
		numAddressRows = 3
		initialSashPosition = addressRowHeight * numAddressRows
		self.horizontalSplitter.SplitHorizontally(self.addressGrid,self.bottomPanel,initialSashPosition)
		self.addressGrid.OnResize(None)
		self.Bind(wx.EVT_CLOSE,self.OnClose)
		restore_message = False
		if sent_message == True:
			self.Bind(wx.EVT_TOOL,self.OnEditClick,id = id_edit)
		else:
			self.Bind(wx.EVT_TOOL,self.addressGrid.OnAttach,id = id_attach)
			self.Bind(wx.EVT_TOOL,self.OnAddPicture,id = id_add_picture)
			self.Bind(wx.EVT_TOOL,self.addressGrid.OnAddressBook,id = id_address_book)
			self.Bind(wx.EVT_TOOL,self.OnSendClick,id = id_send)
			self.Bind(wx.EVT_TOOL,self.OnSendLaterClick,id = id_send_later)

		if self.draft_sent_hash != None:
			found,saved_draft = self.parent.local_store.retrieve(self.draft_sent_hash)
			if found == True:
				sent_date,ack_dates = self.GetSentHeader(self.draft_sent_hash)
				wx.CallAfter(self.RestoreFromDraftOrSent,saved_draft,sent_date,ack_dates,sent_message)
				restore_message = True
			else:
				self.rtc.SetValue("This outgoing message is in the preparation queue, and cannot be viewed yet.")	
				self.rtc.SetEditable(False)
		elif self.reply_forward_id != None:
			wx.CallAfter(self.ReplyOrForwardMessage,self.reply_forward_id,self.reply_forward_type)
			restore_message = True
		self.state_hash = None
		if sent_message == False:
			if sent_message == False and restore_message == False and self.parent.template_message != None:
				wx.CallAfter(self.LoadTemplateAndMessage,self.parent.template_message,None)
			self.isEditable = True
			wx.CallAfter(self.addressGrid.EnableCellEditControl)
		if self.reply_forward_type == 'R' or self.reply_forward_type == 'RA':
			wx.CallAfter(self.rtc.SetFocus)
		else:
			wx.CallAfter(self.addressGrid.SetFocus)
		if sent_message == False:
			wx.CallAfter(self.StartHashTimer)
		if addrBook == True:
			wx.CallAfter(self.addressGrid.OnAddressBook,None)

	def StartHashTimer(self):
		# Hashing of content to detect changes needs to happen after rendering,
		# else it breaks rendering
		self.hash_timer = wx.Timer(self,id = id_hash_timer)
		self.Bind(wx.EVT_TIMER,self.SetStateHash,id = id_hash_timer)
		self.hash_timer.Start(1000,wx.TIMER_ONE_SHOT)

	def OnAddPicture(self,event):
		try:
			fileDialog = wx.FileDialog(self,message = "Select image file to insert",
				style = wx.FD_OPEN,
				wildcard = "Image files|*.bmp; *.gif; *.jpg; *.jpeg; *.png|BMP files (*.bmp)|*.bmp|GIF files (*.gif)|*.gif|PNG files (*.png)|*.png|JPG files (*.jpg)|*.jpg|JPEG files (*.jpeg)|*.jpeg|All files (*.*)|*.*")
				#wildcard = "Image files|*.bmp; *.gif; *.jpg; *.jpeg; *.pcx; *.png; *.pnm; *.tif; *.xpm; *.ico; *.cur; *.ani")
			result = fileDialog.ShowModal()
			if result != wx.ID_OK:
				return
			file_path = fileDialog.GetPath()
			#DBGOUT#print "add picture ",file_path
			filestat = os.stat(file_path)
			if filestat.st_size > global_config.max_insert_image_size:
				question = "Inserted pictures should be screen resolution. Inserting large pictures can make the message slow or impossible to open. It is preferable to attach rather than insert a large picture. Click Yes to insert the picture anyway, or No to cancel."
				answer = wx.MessageBox(question,"Large Image Confirmation",wx.YES_NO|wx.ICON_EXCLAMATION,self)
				if answer != wx.YES:
					return
			if re_imageformats.match(file_path) == None:
				question = "The file extension is not a recognized image type. Inserting non-image files can cause a crash. Click Yes to insert the file anyway, or No to cancel."
				answer = wx.MessageBox(question,"Unknown Image Format Confirmation",wx.YES_NO|wx.ICON_EXCLAMATION,self)
				if answer != wx.YES:
					return
			insertImage = wx.Image(file_path)
			self.rtc.WriteImage(insertImage)
		except Exception:
			return

	def InsertAddressesFromBook(self,toccbcc,recipients):
		existing_keys = set()
		row = 1
		for i in range(self.addressGrid.GetNumberRows()):
			label = self.addressGrid.GetRowLabelValue(i)
			if label != 'To' and label != 'Cc' and label != 'Bcc':
				continue
			value = self.addressGrid.GetCellValue(i,0)
			if value == None or value == '':
				continue
			row = i
			keyid = None
			m = re_keyid.match(value)
			if m:
				keyid = m.group(1)
				if keyid == None:
					keyid = m.group(2)
			if keyid != None:
				existing_keys.add(keyid.lower())

		self.addressGrid.BeginBatch()
		for rnam in recipients:
			keyid = None
			m = re_keyid.match(rnam)
			if m:
				keyid = m.group(1)
				if keyid == None:
					keyid = m.group(2)
			if keyid == None or keyid.lower() in existing_keys:
				continue
			self.addressGrid.InsertRowMoveLabels(row-1)
			if toccbcc == 'T':
				self.addressGrid.SetRowLabelValue(row,'To')
			elif toccbcc == 'C':
				self.addressGrid.SetRowLabelValue(row,'Cc')
			elif toccbcc == 'B':
				self.addressGrid.SetRowLabelValue(row,'Bcc')
			self.addressGrid.SetCellValue(row,0,rnam)
			self.addressGrid.SetCellValue(row,1,"-")
			self.addressGrid.SetCellAlignment(row,1,wx.ALIGN_CENTRE,wx.ALIGN_CENTRE)
			self.addressGrid.SetReadOnly(row,1,True)
			row += 1
		self.addressGrid.EndBatch()
		self.addressGrid.AdjustSash()

	def GetSentHeader(self,message_id):
		headername = self.parent.local_store.getPath(message_id) + '.HDR'
		#DBGOUT#print headername
		sent_date = None
		ack_dates = dict()
		try:
			fh = codecs.open(headername,'r','utf-8')
			headers = fh.read()
			fh.close()
		except IOError:
			return sent_date,ack_dates

		for line in headers.split('\n'):
			line = line.rstrip('\r\n')
			m = re_datetime.match(line)
			if m:
				sent_date = m.group(1)
			m = re_ack.match(line)
			if m:
				user = m.group(1).lower()
				hash = m.group(2)
				found,lines = self.parent.local_store.retrieve(hash)
				if found:
					for line2 in lines.split('\n'):
						line2 = line2.rstrip('\r')
						mm = re_datetime.match(line2)
						if mm:
							ack_dates[user] = mm.group(1)
		return sent_date,ack_dates

	def RestoreFromDraftOrSent(self,saved_draft,sent_date,ack_dates,sent_mode):
		recipients,recipients_full,attachments,reply_thread_id,forward_original_id,subject,body_text,body_html,body_xml,save_date = pickle.loads(saved_draft)

		if forward_original_id != None:
			self.reply_forward_id = forward_original_id
			self.reply_forward_type = 'FA'
		elif reply_thread_id != None:
			self.reply_forward_id = reply_thread_id
			self.reply_forward_type = 'R'
		if sent_date != None and sent_mode == True:
			self.ack_dates_by_row = dict()
		row = 1
		self.addressGrid.BeginBatch()
		for recip in recipients_full:
			rtyp = recip[0]
			rnam = recip[2:]
			self.addressGrid.InsertRowMoveLabels(row-1)
			if rtyp == 'T':
				self.addressGrid.SetRowLabelValue(row,'To')
			elif rtyp == 'C':
				self.addressGrid.SetRowLabelValue(row,'Cc')
			elif rtyp == 'B':
				self.addressGrid.SetRowLabelValue(row,'Bcc')
			self.addressGrid.SetCellValue(row,0,rnam)
			if sent_mode == True:
				keyid = None
				m = re_keyid.match(rnam)
				if m:
					keyid = m.group(1)
					if keyid == None:
						keyid = m.group(2)
				if keyid != None:
					keyidL = keyid.lower()
					if keyidL in ack_dates:
						self.addressGrid.SetCellValue(row,1,'A')
						self.ack_dates_by_row[row] = ack_dates[keyidL]
			else:
				self.addressGrid.SetCellValue(row,1,"-")
			self.addressGrid.SetCellAlignment(row,1,wx.ALIGN_CENTRE,wx.ALIGN_CENTRE)
			self.addressGrid.SetReadOnly(row,1,True)
			if sent_mode == True:
				self.addressGrid.SetReadOnly(row,0,True)
			row += 1
		if sent_mode == True:
			self.addressGrid.SetRowLabelValue(row,"Sent Date")
			if sent_date == None:
				self.addressGrid.SetCellValue(row,0,'None')
			else:
				self.addressGrid.SetCellValue(row,0,self.date_formatter.localize_datetime(sent_date))
			self.addressGrid.SetReadOnly(row,0,True)
			self.addressGrid.SetCellValue(row,1,"")
		subject_row = self.addressGrid.GetNumberRows() - 1
		if subject != None and subject != '':
			self.addressGrid.SetCellValue(subject_row,0,subject)
		if sent_mode == True:
			self.addressGrid.SetReadOnly(subject_row,0,True)

		row = self.addressGrid.GetNumberRows()
		for attach in attachments:
			self.addressGrid.AppendRows(1)
			self.addressGrid.SetRowLabelValue(row,'Attach')
			self.addressGrid.SetCellValue(row,0,attach)
			self.addressGrid.SetReadOnly(row,0,True)
			if sent_mode == False:
				self.addressGrid.SetCellValue(row,1,"-")
			self.addressGrid.SetCellAlignment(row,1,wx.ALIGN_CENTRE,wx.ALIGN_CENTRE)
			self.addressGrid.SetReadOnly(row,1,True)
			row += 1

		if sent_mode == False and self.parent.template_message != None:
			self.LoadTemplateAndMessage(self.parent.template_message,body_xml)
		else:
			buf = cStringIO.StringIO(body_xml)
			handler = wx.richtext.RichTextXMLHandler()
			handler.SetFlags(wx.richtext.RICHTEXT_HANDLER_INCLUDE_STYLESHEET)
			handler.LoadStream(self.rtc.GetBuffer(), buf)
			buf.close()
		self.addressGrid.EndBatch()
		self.addressGrid.AdjustSash()
		self.addressGrid.SetRowLabelSize(wx.grid.GRID_AUTOSIZE)
		if sent_mode == True:
			self.rtc.SetEditable(False)

	# Open to reply or forward, type = F, FA, R, RA
	def ReplyOrForwardMessage(self,messageId,replyOrForwardType):
		zipFilePath = self.parent.local_store.getPath(messageId) + '.ZIP'
		headerData = None
		messageXML = None
		messageText = None
		try:
			zipFile = zipfile.ZipFile(zipFilePath,'r')
		except (IOError,KeyError):
			return
		try:
			headerData = zipFile.read('HEADER.TXT').decode('utf-8')
			messageXML = zipFile.read('BODY.XML')
		except (IOError,KeyError):
			pass
		if messageXML == None:
			try:
				messageText = zipFile.read('BODY.TXT')
				messageText = messageText.decode('utf-8')
			except (IOError,KeyError):
				pass
		if headerData == None or (messageXML == None and messageText == None):
			return
		zipFile.close()

		origFrom = ''
		origDate = ''
		origSubject = ''
		outSubject = ''
		origTo = ''
		origCc = ''
		origFromList = [ ]
		origToList = [ ]
		origCcList = [ ]
		keysToGet = [ ]
		keyidFrom = None
		messageUniqueId = None
		for line in headerData.split('\n'):
			line = line.rstrip('\r\n')
			lineU = line.upper()
			if lineU[0:6] == 'FROM: ':
				origFrom = line + '\n'
				origFromList.append(line[6:])
				m = re_keyid.match(line[6:])
				if m:
					keyidFrom = m.group(1)
					if keyidFrom == None:
						keyidFrom = m.group(2)
			elif lineU[0:17] == 'MESSAGEUNIQUEID: ':
				m = re_keyid.match(line[17:])
				if m:
					messageUniqueId = m.group(1)
					if messageUniqueId == None:
						messageUniqueId = m.group(2)
			elif lineU[0:4] == 'TO: ':
				origTo += line + '\n'
				origToList.append(line[4:])
			elif lineU[0:4] == 'CC: ':
				origCc += line + '\n'
				origCcList.append(line[4:])
			elif re_datetime.match(line) != None:
				origDate = 'Date: ' + self.date_formatter.localize_datetime(line[6:]) + ' ' + self.date_formatter.get_tzoffset() + '\n'
			elif lineU[0:9] == 'SUBJECT: ':
				origSubject = line

		for line in headerData.split('\n'):
			m = re_key_transport.match(line)
			if m:
				if m.group(1) != None:
					ki = m.group(1)
					tr = m.group(2)
				else:
					ki = m.group(3)
					tr = m.group(4)
				if replyOrForwardType == 'RA' or ki.lower() == keyidFrom.lower():
					keysToGet.append( [ ki.lower(),tr ] )
		self.messageUniqueId = messageUniqueId
				
		#if replyOrForwardType == 'RA': # fetch keys of people being copied
		# check and fetch or renew keys of recipients
		keyidLookup = set()
		for ktg in keysToGet:
			keyid,transport = ktg
			#if keyid not in keyidLookup:
			#DBGOUT#print "get " + keyid + " from " + transport
			self.gui.to_agent_queue.put( [ 'EXP_KEY_SEARCH',True,True,transport, [ keyid ] ] )
	
		self.addressGrid.BeginBatch()
		if origFrom != '' and (replyOrForwardType == 'R' or replyOrForwardType == 'RA'):
			self.InsertAddressesFromBook('T',origFromList)		
		if replyOrForwardType == 'RA':
			self.InsertAddressesFromBook('T',origToList)	
			self.InsertAddressesFromBook('C',origCcList)		

		if replyOrForwardType == 'F' or replyOrForwardType == 'FA': 
			if origSubject[9:13].upper() == 'FW: ':
				outSubject = origSubject[9:]
			else:
				outSubject = 'FW: ' + origSubject[9:]
		elif replyOrForwardType == 'R' or replyOrForwardType == 'RA': 
			if origSubject[9:13].upper() == 'RE: ':
				outSubject = origSubject[9:]
			else:
				outSubject = 'RE: ' + origSubject[9:]

		subject_row = self.addressGrid.GetNumberRows() - 1
		if outSubject != None and outSubject != '':
			self.addressGrid.SetCellValue(subject_row,0,outSubject)

		self.addressGrid.EndBatch()
		self.addressGrid.AdjustSash()

		add_headers = '\nOriginal message:\n' + origFrom + origTo + origCc + origSubject + '\n' + origDate
		usedTemplate = False
		if messageXML != None and self.parent.template_message != None:
			self.LoadTemplateAndMessage(self.parent.template_message,messageXML,add_headers)
			usedTemplate = True
		elif messageXML != None:
			buf = cStringIO.StringIO(messageXML)
			handler = wx.richtext.RichTextXMLHandler()
			handler.SetFlags(wx.richtext.RICHTEXT_HANDLER_INCLUDE_STYLESHEET)
			handler.LoadStream(self.rtc.GetBuffer(), buf)
			buf.close()
		else:
			self.rtc.SetValue(messageText)
		if usedTemplate == False:
			self.rtc.SetCaretPosition(-1)
			self.rtc.WriteText('\n'+add_headers+'\n')
			self.rtc.SetCaretPosition(-1)

	def LoadTemplateAndMessage(self,templateId,message_xml,add_headers = None):
		if message_xml == None:
			message_xml = '</richtext>'
		found,saved_template = self.parent.local_store.retrieve(templateId.encode('hex'))
		if found == True:
			recipients,recipients_full,attachments,reply_thread_id,forward_original_id,subject,body_text,body_html,template_xml,save_date = pickle.loads(saved_template)
			body_xml1 = ''
			body_xml2 = ''
			for line in template_xml.split('\n'):
				if line[0:11] != '</richtext>':
					body_xml1 += line + '\n'
			if add_headers != None:
				body_xml1 += "<paragraphlayout textcolor=\"#000000\" fontpointsize=\"9\" fontfamily=\"70\" fontstyle=\"90\" fontweight=\"90\" fontunderlined=\"0\" fontface=\"Segoe UI\" alignment=\"1\" parspacingafter=\"0\" parspacingbefore=\"0\" linespacing=\"10\" margin-left=\"5,4098\" margin-right=\"5,4098\">\n"
				for line in add_headers.split('\n'):
					body_xml1 += \
						"    <paragraph>\n" + \
						"      <text textcolor=\"#000000\" bgcolor=\"#FFFFFF\" fontpointsize=\"10\" fontstyle=\"90\" "+ \
						"fontweight=\"90\" fontunderlined=\"0\" fontface=\"Times New Roman\">" + \
						html_escape(line) + "</text>\n" + \
						"    </paragraph>\n" 
				body_xml1 += '</paragraphlayout>'
			for line in message_xml.split('\n'):
				if line[0:18] != '<richtext version=' and line[0:14] != '<?xml version=':
					body_xml2 += line + '\n'
		else:
			body_xml1 = ''
			body_xml2 = message_xml
		buf = cStringIO.StringIO(body_xml1 + body_xml2)
		handler = wx.richtext.RichTextXMLHandler()
		handler.SetFlags(wx.richtext.RICHTEXT_HANDLER_INCLUDE_STYLESHEET)
		handler.LoadStream(self.rtc.GetBuffer(), buf)
		buf.close()

	def OnSendClick(self,event):
		self.rtc.SetFocus() # Force completion...
		wx.CallAfter(self.OnSendClickCont,False)

	def OnSendLaterClick(self,event):
		self.rtc.SetFocus() # Force completion...
		wx.CallAfter(self.OnSendClickCont,True)

	def OnSendClickCont(self,sendLater):
		self.addressGrid.SetFocus()  # of entries in progress
		self.gui.LoadKeyList() # in case keys changed/fetched
		# First validate the addresses
		keyidLookup = set()
		entangledKeys = set()
		for key in self.gui.keyList:
			if 'noannounce' not in key:
				keyidLookup.add(key['fingerprint'].lower())
				if key['ent'] == True:
					entangledKeys.add(key['fingerprint'].lower())
		numValid = 0
		estNumBytes = 0
		hasEntangled = 0
		for row in range(self.addressGrid.GetNumberRows()):
			label = self.addressGrid.GetRowLabelValue(row)
			value = self.addressGrid.GetCellValue(row,0)
			if label == 'Attach':
				try:
					filestat = os.stat(value)
					estNumBytes += filestat.st_size
				except Exception:
					self.addressGrid.SetGridCursor(row,0)
					self.SetStatusText("Attachment file missing: " + value)
					return
			if label != 'To' and label != 'Cc' and label != 'Bcc':
				continue
			if value == '':
				continue
			valid = False
			m = re_keyid.match(value)
			if m:
				keyid = m.group(1)
				if keyid == None:
					keyid = m.group(2)
				if keyid != None:
					keyidL = keyid.lower()
					if keyidL in keyidLookup:
						valid = True
						numValid += 1
						if keyidL in entangledKeys:
							hasEntangled += 1
			if valid == False:
				self.addressGrid.SetGridCursor(row,0)
				self.SetStatusText("Address not found.")
				return	
		if numValid == 0:
			self.SetStatusText("No recipient addresses entered.")
			return	
		# Large message over Entangled
		if hasEntangled > 0 and estNumBytes > global_config.max_msgsize_entangled:
			if hasEntangled > 1:
				question = "You are sending " + str(estNumBytes) + " bytes of attachments to " + str(hasEntangled) + " Entangled users.\nThis will be slow. Are you sure?"
			else:
				question = "You are sending " + str(estNumBytes) + " bytes of attachments to an Entangled user.\nThis will be slow. Are you sure?"
			answer = wx.MessageBox(question,"Large Message Confirmation",wx.YES_NO|wx.ICON_EXCLAMATION,self)
			if answer != wx.YES:
				return
		# Handle send later case
		if sendLater == True:
			dlg = wx.TextEntryDialog(self,message = "Enter number of hours to delay (max 72 hours; decimals are permitted)",caption = "Enter delay time")
			if dlg.ShowModal() != wx.ID_OK:
				dlg.Destroy()
				return
			delayHoursText = dlg.GetValue()
			dlg.Destroy()
			try:
				delayHours = float(delayHoursText)
			except ValueError:
				self.SetStatusText("Invalid delay time entered")
				return
			nowtime_obj = datetime.datetime.utcnow()
			sendtime_obj = nowtime_obj + datetime.timedelta(0,0,0,0,0,delayHours)
			sendtime = sendtime_obj.strftime("%Y-%m-%dT%H:%M:%SZ")
		else:
			sendtime = None

		# Package and send
		message_data = self.PackageMessage()
		for recip in message_data[0]: # check expired
			keyid = recip[2:]
			self.gui.to_agent_queue.put( [ 'EXP_KEY_SEARCH',True,True,None, [ keyid ] ] )
		pickled_message = pickle.dumps(message_data,pickle.HIGHEST_PROTOCOL)
		hasher = hashlib.new('sha1')
		hasher.update(pickled_message)
		save_hash = hasher.digest()
		save_hashH = save_hash.encode('hex')
		headers = self.parent.folder_store.extract_outgoing_message_headers(message_data,self.parent.from_address,save_hash,'S')
		#DBGOUT#print "Sending message, hash=" + save_hashH
		self.parent.prepmsgs.store(save_hashH,pickled_message)
		self.parent.local_store.store(save_hashH,pickled_message)
		if self.parent.outgoing_sync != None:
			self.parent.outgoing_sync.addChange( [ 'SendMsg',save_hash ] )
			self.parent.outgoing_sync.store(save_hashH,pickled_message)
		self.parent.folder_store.save_message(save_hash,headers)
		self.parent.folder_store.put_message_in_folder(folders.id_send_pending,save_hash,skip_sync = True)
		self.parent.folder_store.put_message_in_folder(folders.id_ack_pending,save_hash)
		if sendtime != None:
			filehandle = open(self.parent.prepmsgs.getPath(save_hashH) + '.EMBARGO','wb')
			filehandle.write('T:' + sendtime + "\n")
			filehandle.close()
		self.gui.to_agent_queue.put( [ 'ENCODE_SEND',save_hashH,False ] )
		self.parent.ProcessNewSend(headers)
		self.parent.CheckUpdateKey()
		if self.reply_forward_type == 'R' or self.reply_forward_type == 'RA':
			self.parent.messageList.ChangeMessageImage(self.reply_forward_id.decode('hex'),True,False)
		elif self.reply_forward_type == 'F' or self.reply_forward_type == 'FA':
			self.parent.messageList.ChangeMessageImage(self.reply_forward_id.decode('hex'),False,True)
		self.parent.folder_store.commit()
		self.already_clicked_close = True
		self.Close()
		wx.CallAfter(self.parent.ShowTemporaryStatus,'Message queued to send')

	def OnSaveDraftClick(self,event):
		self.rtc.SetFocus()          # Force completion...
		wx.CallAfter(self.OnSaveDraftClickCont)

	def OnSaveDraftClickCont(self):
		self.addressGrid.SetFocus()  # of entries in progress
		message_data = self.PackageMessage()
		pickled_message = pickle.dumps(message_data,pickle.HIGHEST_PROTOCOL)
		hasher = hashlib.new('sha1')
		hasher.update(pickled_message)
		save_hash = hasher.digest()
		save_hashH = save_hash.encode('hex')
		headers = self.parent.folder_store.extract_outgoing_message_headers(message_data,self.parent.from_address,save_hash,'D')
		#DBGOUT#print "Saving draft message, hash=" + save_hashH
		self.parent.local_store.store(save_hashH,pickled_message)
		if self.parent.outgoing_sync != None:
			self.parent.outgoing_sync.addChange( [ 'SaveDraft',save_hash ] )
			self.parent.outgoing_sync.store(save_hashH,pickled_message)
		self.parent.folder_store.save_message(save_hash,headers)
		self.parent.folder_store.put_message_in_folder(folders.id_drafts,save_hash)
		if self.draft_sent_hash != None and self.draft_sent_hash.decode('hex') != save_hash:
			self.parent.folder_store.put_message_in_folder(folders.id_deleted,self.draft_sent_hash.decode('hex'))
			self.parent.folder_store.delete_message_from_folder(folders.id_drafts,self.draft_sent_hash.decode('hex'))
		self.parent.ProcessNewDraft(headers)
		self.parent.folder_store.commit()
		self.already_clicked_close = True
		self.Close()
		wx.CallAfter(self.parent.ShowTemporaryStatus,'Message saved to Drafts')

	def OnEditClick(self,event):
		wx.CallAfter(self.parent.ReopenForEdit,self.draft_sent_hash,self.GetPosition(),self.GetSize())
		self.Close()

	def OnArchiveClick(self,event):
		if self.ds_from_folder == folders.id_inbox or self.ds_from_folder == folders.id_new_messages:
			ds_from_folders = [ folders.id_inbox,folders.id_new_messages ]
		else:
			ds_from_folders = [ self.ds_from_folder ]
		self.parent.MoveMessageToArchive(self.draft_sent_hash,ds_from_folders)
		self.OnCancelClick(event)

	def OnDeleteClick(self,event):
		if self.ds_from_folder == folders.id_inbox or self.ds_from_folder == folders.id_new_messages:
			ds_from_folders = [ folders.id_inbox,folders.id_new_messages ]
		else:
			ds_from_folders = [ self.ds_from_folder ]
		self.parent.DeleteMessageFromFolder(self.draft_sent_hash,ds_from_folders)
		self.OnCancelClick(event)

	def OnCancelClick(self,event):
		self.Close()

	# There is a bug where a short word pair (test case: v2 a) at the end of the line
	# gets treated as a single word. This is confirmed to be a problem with WordRight()
	# and does not occur with WordLeft()
	def OnSpellNextClick(self,event):
		self.SetStatusText("")	
		self.spell_last_prev = False
		if self.enchantDict == None:
			self.enchantDict = enchant.Dict(self.gui.spellcheckLanguage)
		pos1 = self.rtc.GetInsertionPoint()
		while True:
			res = self.rtc.WordRight()
			if res == False:
				lp = self.rtc.GetLastPosition()
				self.rtc.ShowPosition(lp)
				self.rtc.SetInsertionPoint(lp)
				self.toolbar.EnableTool(id_spell_next,False)
				self.spell_enable_timer.Start(2000,wx.TIMER_ONE_SHOT)
				self.SetStatusText("Spell check is at the end of the message")	
				break
			pos2 = self.rtc.GetInsertionPoint()
			wordRange = self.rtc.GetRange(pos1,pos2)
			m = re_oneword.match(wordRange)
			if m:
				word = m.group(1)
				#DBGOUT#print "res=",res,"pos1=",pos1,"pos2=",pos2,"wordrange=",wordRange,"word=",word
				m = re_hexkey.match(word)
				if m == None and self.enchantDict.check(word) == False:
					self.rtc.ShowPosition(pos2)
					if wordRange[0] <= ' ' and wordRange[-1] <= ' ':
						self.rtc.SetSelection(pos1 + 1,pos2 - 1)
					elif wordRange[-1] <= ' ':
						self.rtc.SetSelection(pos1,pos2 - 1)
					elif wordRange[0] <= ' ':
						self.rtc.SetSelection(pos1 + 1,pos2)
					else:
						self.rtc.SetSelection(pos1,pos2)
					break
			#DBGOUT#else:
				#DBGOUT#print "res=",res,"pos1=",pos1,"pos2=",pos2,"nonword=",wordRange
			pos1 = pos2

	def OnSpellPrevClick(self,event):
		self.SetStatusText("")	
		if self.enchantDict == None:
			self.enchantDict = enchant.Dict(self.gui.spellcheckLanguage)
		if self.spell_last_prev == True:
			res = self.rtc.WordLeft()
			self.spell_last_prev = False
		pos2 = self.rtc.GetInsertionPoint()
		while True:
			res = self.rtc.WordLeft()
			if res == False:
				self.rtc.ShowPosition(0)
				self.rtc.SetInsertionPoint(0)
				self.toolbar.EnableTool(id_spell_prev,False)
				self.spell_enable_timer.Start(2000,wx.TIMER_ONE_SHOT)
				self.spell_last_prev = False
				self.SetStatusText("Spell check is at the beginning of the message")	
				break
			pos1 = self.rtc.GetInsertionPoint()
			wordRange = self.rtc.GetRange(pos1,pos2)
			m = re_oneword.match(wordRange)
			if m:
				word = m.group(1)
				#DBGOUT#print "res=",res,"pos1=",pos1,"pos2=",pos2,"wordrange=",wordRange,"word=",word
				m = re_hexkey.match(word)
				if m == None and self.enchantDict.check(word) == False:
					self.rtc.ShowPosition(pos1)
					if wordRange[0] <= ' ' and wordRange[-1] <= ' ':
						self.rtc.SetSelection(pos1 + 1,pos2 - 1)
					elif wordRange[-1] <= ' ':
						self.rtc.SetSelection(pos1,pos2 - 1)
					elif wordRange[0] <= ' ':
						self.rtc.SetSelection(pos1 + 1,pos2)
					else:
						self.rtc.SetSelection(pos1,pos2)
					self.spell_last_prev = True
					break
			#DBGOUT#else:
				#DBGOUT#print "res=",res,"pos1=",pos1,"pos2=",pos2,"nonword=",wordRange
			pos2 = pos1

	def OnSpellSuggestClick(self,event):
		self.SetStatusText("")	
		selStart,selEnd = self.rtc.GetSelectionRange()
		selString = self.rtc.GetStringSelection()
		if selStart < 0 or selEnd < 0 or selString == None or selString == '':
			self.SetStatusText("Please select a word")	
			return
		if self.enchantDict == None:
			self.enchantDict = enchant.Dict(self.gui.spellcheckLanguage)
		suggestions = self.enchantDict.suggest(selString)
		#DBGOUT#print 'start',selStart,'end',selEnd,'str',selString,suggestions
		if len(suggestions) == 0:
			self.SetStatusText("No suggestions found")	
			return
		dlg = wx.SingleChoiceDialog(self,'Suggestions for: ' + selString,'Spelling Suggestions',
			suggestions,wx.CHOICEDLG_STYLE)
		if dlg.ShowModal() == wx.ID_OK:
			replacement = dlg.GetStringSelection()
			#DBGOUT#self.rtc.Replace(selStart,selEnd,replacement) # messes up the font
			self.rtc.DeleteSelection()
			self.rtc.SetInsertionPoint(selStart)
			self.rtc.WriteText(replacement)
		dlg.Destroy()

	def EnableSpellButtons(self,event):
		self.toolbar.EnableTool(id_spell_next,True)
		self.toolbar.EnableTool(id_spell_prev,True)

	def OnSmallerClick(self,event):
		#DBGOUT#print "old size x=",self.fontX," y=",self.fontY
		self.fontX = self.fontX * 0.9
		self.fontY = self.fontY * 0.9
		self.rtc.SetScale(self.fontX,self.fontY)
		#DBGOUT#print "new size x=",self.fontX," y=",self.fontY
	
	def OnLargerClick(self,event):
		#DBGOUT#print "old size x=",self.fontX," y=",self.fontY
		self.fontX = self.fontX * 1.1
		self.fontY = self.fontY * 1.1
		self.rtc.SetScale(self.fontX,self.fontY)
		#DBGOUT#print "new size x=",self.fontX," y=",self.fontY

	def OnFindClick(self,event):
		self.rtc.SetEditable(False)
		self.findText = self.rtc.GetValue()
		self.findTextLower = self.findText.lower()
		self.findLen = len(self.findText)
		self.findPos = -1
		self.findData = wx.FindReplaceData()
		self.findData.SetFlags(wx.FR_DOWN)
		self.findDialog = wx.FindReplaceDialog(self,self.findData,"Find")
		self.findDialog.Bind(wx.EVT_FIND, self.OnFind)
		self.findDialog.Bind(wx.EVT_FIND_NEXT, self.OnFind)
		self.findDialog.Bind(wx.EVT_FIND_CLOSE, self.OnFindClose)
		self.findDialog.Show()

	def OnFind(self,event):
		findString = self.findData.GetFindString()
		flags = self.findData.GetFlags()

		if self.findPos < 0:	
			if flags & wx.FR_DOWN:
				self.findPos = 0
			else:
				self.findPos = self.findLen
		if flags & wx.FR_MATCHCASE:
			findText = self.findText
		else:
			findString = findString.lower()
			findText = self.findTextLower
		if flags & wx.FR_DOWN:
			found = findText.find(findString,self.findPos)
			if found >= 0:
				self.findPos = found + 1
			else:
				self.findPos = found
		else:
			found = findText.rfind(findString,0,self.findPos)
			if found >= 0:
				self.findPos = found - 1
			else:
				self.findPos = found

		if flags & wx.FR_WHOLEWORD:
			notword = False
			if found > 0:
				if findText[found - 1].isalpha() == True:
					notword = True
			if found >= 0:
				endpoint = found + len(findString)
				if (endpoint < len(findText)) and (findText[endpoint].isalpha() == True):
					notword = True
			if notword == True:
				if found == 0:
					found = -1
					self.findPos = found
				else:
					return self.OnFind(event) # next one
		
		if found >= 0:
			self.rtc.ShowPosition(found)
			self.rtc.SetSelection(found,(found + len(findString)))
			x,y = self.rtc.PositionToXY(found)
			msg = "Found at line " + str(y+1) + ", offset " + str(x)
			self.SetStatusText(msg,0)
		else:
			self.rtc.SelectNone()
			self.SetStatusText("Not found",0)

	def OnFindClose(self,event):
		self.findDialog = None
		self.findText = None
		self.findTextLower = None
		self.SetStatusText("",0)
		if self.isEditable == True:
			self.rtc.SetEditable(True)

	def GetStateHash(self):
		recipients,recipients_full,attachments,reply_thread_id,forward_original_id,subject,body_text,body_html,body_xml,nowtime = self.PackageMessage()
		hash_data = recipients_full,attachments,subject,body_xml
		pickled_message = pickle.dumps(hash_data,pickle.HIGHEST_PROTOCOL)
		hasher = hashlib.new('sha1')
		hasher.update(pickled_message)
		return hasher.digest()

	def SetStateHash(self,event = None):
		self.state_hash = self.GetStateHash()

	# Generate list of recipients, subject, body, attachments
	def PackageMessage(self):
		recipients = []
		recipients_full = []
		attachments = []
		subject = ''
		forward_original_id = None
		reply_thread_id = None
		
		for i in range(self.addressGrid.GetNumberRows()):
			label = self.addressGrid.GetRowLabelValue(i)
			value = self.addressGrid.GetCellValue(i,0)
			if value == None or value == '':
				continue
			#DBGOUT#print i,label,value
			keyid = None
			m = re_keyid.match(value)
			if m:
				#DBGOUT#print "match",label,value,m.group(1)
				keyid = m.group(1)
				if keyid == None:
					keyid = m.group(2)
			if label == 'To':
				recipients_full.append('T:' + value)
 				if keyid != None:
					recipients.append('T:' + keyid)
			elif label == 'Cc':
				recipients_full.append('C:' + value)
 				if keyid != None:
					recipients.append('C:' + keyid)
			elif label == 'Bcc':
				recipients_full.append('B:' + value)
 				if keyid != None:
					recipients.append('B:' + keyid)
			elif label == 'Subject':
				subject = value
			elif label == 'Attach':
				attachments.append(value)

		if self.reply_forward_type == 'FA':
			forward_original_id = self.reply_forward_id
		elif self.reply_forward_type == 'R' or self.reply_forward_type == 'RA':
			reply_thread_id = self.messageUniqueId

		buf = cStringIO.StringIO()
		handler = wx.richtext.RichTextXMLHandler()
		handler.SetFlags(wx.richtext.RICHTEXT_HANDLER_INCLUDE_STYLESHEET)
		handler.SaveStream(self.rtc.GetBuffer(), buf)
		body_xml = buf.getvalue()
		
		buf = cStringIO.StringIO()
		handler = wx.richtext.RichTextHTMLHandler()
		handler.SaveStream(self.rtc.GetBuffer(), buf)
		body_html = buf.getvalue()
		body_text = self.rtc.GetValue()
		nowtime = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
		message_data = recipients,recipients_full,attachments,reply_thread_id,forward_original_id,subject,body_text,body_html,body_xml,nowtime
		return message_data

	def OnClose(self,event):
		if self.already_clicked_close == False and self.isEditable == True:
			new_state_hash = self.GetStateHash()
		if self.already_clicked_close == False and self.isEditable == True and new_state_hash != self.state_hash and event.CanVeto() == True:
			answer = wx.MessageBox("You have unsaved changes. Click Yes to save message to Drafts,\nNo to discard message, Cancel to continue editing.","Discard message?",wx.YES_NO|wx.CANCEL|wx.ICON_EXCLAMATION,self)
			if answer == wx.CANCEL:
				event.Veto()
				return
			elif answer == wx.YES:
				event.Veto()
				self.already_clicked_close = True
				wx.CallAfter(self.OnSaveDraftClick,None)
				return
		self.parent.openAddressBook = None
		self.Destroy()

# This rich text editor was stolen from the wxPython demo program!
# I did fix some bugs, specifically by replacing: 
# attr = wx.TextAttr()
# -- with --
# attr = rt.RichTextAttr()
# which was required to make the color, font, and indent widgets work.
#----------------- begin stolen code ----------------------------------

	def initRtfEditor(self,noToolBar = True):
		self.selectedColour = None
		self.selectedFontName = None
		self.selectedFontSize = None
		self.selectedFont = None
		self.MakeMenuBar()
		if noToolBar == False:
			self.MakeToolBar()
		self.CreateStatusBar()
		#self.SetStatusText("Welcome to wx.richtext.RichTextCtrl!")

		self.rtc = rt.RichTextCtrl(self.bottomPanel, style=wx.VSCROLL|wx.HSCROLL|wx.NO_BORDER);
		#wx.CallAfter(self.rtc.SetFocus)
		self.mainSizer.Add(self.rtc,1,wx.EXPAND,0)

		self.textAttr = rt.RichTextAttr()
		foundn,fontname = self.parent.folder_store.get_global('FONTNAME')
		founds,fontsize = self.parent.folder_store.get_global('FONTSIZE')
		if foundn == True and founds == True:
			self.SetFontStyle(fontColor=wx.Colour(0, 0, 0), fontBgColor=wx.Colour(255, 255, 255), fontFace=fontname, fontSize=int(fontsize), fontBold=False, fontItalic=False, fontUnderline=False)
	  		self.selectedFont = self.textAttr.GetFont()
		else:
			self.SetFontStyle(fontColor=wx.Colour(0, 0, 0), fontBgColor=wx.Colour(255, 255, 255), fontFace='Times New Roman', fontSize=10, fontBold=False, fontItalic=False, fontUnderline=False)
		self.fontX = 1.0 * self.gui.editorScaleFactor
		self.fontY = 1.0 * self.gui.editorScaleFactor
		self.rtc.SetScale(self.fontX,self.fontY)

		self.Bind(rt.EVT_RICHTEXT_RETURN,self.OnDropIndent) # indent used for replies, new lines not indented
		self.rtc.Bind(wx.EVT_SET_FOCUS,self.OnQueueSetFocus) # must set font here

		# EVT_RICHTEXT_CONSUMING_CHARACTER is an event that gives access to a
		# character _before_ it has been entered into the editor. I need that
		# so the first character of an entry gets the right color. As of
		# wxPython version 3.0.2.0, the wxPython maintainers have not passed
		# this event through from wxWindows C++ library to wxPython.
		#
		# I know from the source code that the consuming version's event number
		# is one more than the regular character event. This hack lets me get
		# access to the consuming version. Once wxPython is fixed, the hack
		# should be removed and replaced with rt.EVT_RICHTEXT_CONSUMING_CHARACTER
		EVT_RICHTEXT_CONSUMING_CHARACTER = wx.PyEventBinder((wx._richtext.wxEVT_COMMAND_RICHTEXT_CHARACTER + 1),1) # ugly hack
		self.Bind(EVT_RICHTEXT_CONSUMING_CHARACTER,self.OnConsumingCharacter)
		if sys.platform == 'win32': # fix delete for Windows only
			self.rtc.Bind(wx.EVT_CHAR_HOOK,self.OnCharHook)

	# This is to make the delete character to the right behavior work normally.
	# Wx Win32 understands delete of a selected block, but not delete to the right.
	def OnCharHook(self,evt): # for some reason EVT_KEY_DOWN does not get Delete key
		kc = evt.GetKeyCode()
		if kc == wx.WXK_DELETE:
			if self.rtc.HasSelection() == False:
				wx.CallAfter(self.OnDeleteRight,evt)
		evt.Skip()

	def OnDeleteRight(self,evt):
		ip = self.rtc.GetInsertionPoint()
		if ip < self.rtc.GetLastPosition():
			self.rtc.Delete(rt.RichTextRange(ip,ip+1))

	def OnConsumingCharacter(self,event):
		# This causes typed text to retain the selected color rather than that of
		# the surrounding text.
		if self.selectedColour != None:
			self.rtc.BeginTextColour(self.selectedColour)

	def SetFontStyle(self, fontColor = None, fontBgColor = None, fontFace = None, fontSize = None,
					 fontBold = None, fontItalic = None, fontUnderline = None):
	  if fontColor:
		 self.textAttr.SetTextColour(fontColor)
	  if fontBgColor:
		 self.textAttr.SetBackgroundColour(fontBgColor)
	  if fontFace:
		 self.textAttr.SetFontFaceName(fontFace)
	  if fontSize:
		 self.textAttr.SetFontSize(fontSize)
	  if fontBold != None:
		 if fontBold:
			self.textAttr.SetFontWeight(wx.FONTWEIGHT_BOLD)
		 else:
			self.textAttr.SetFontWeight(wx.FONTWEIGHT_NORMAL)
	  if fontItalic != None:
		 if fontItalic:
			self.textAttr.SetFontStyle(wx.FONTSTYLE_ITALIC)
		 else:
			self.textAttr.SetFontStyle(wx.FONTSTYLE_NORMAL)
	  if fontUnderline != None:
		 if fontUnderline:
			self.textAttr.SetFontUnderlined(True)
		 else:
			self.textAttr.SetFontUnderlined(False)
	  self.rtc.SetDefaultStyle(self.textAttr)

	def OnQueueSetFocus(self,evt):
		# wx.RichTextControl is broken. This is what I have to do to set a font.
		wx.CallAfter(self.OnSetFocus,evt)
		evt.Skip()

	def OnSetFocus(self,evt):
		if self.selectedFont != None:
			self.rtc.BeginFont(self.selectedFont)
			self.selectedFont = None

#	def OnURL(self, evt):
#		wx.MessageBox(evt.GetString(), "URL Clicked")
#		
#
#	def OnFileOpen(self, evt):
#		# This gives us a string suitable for the file dialog based on
#		# the file handlers that are loaded
#		wildcard, types = rt.RichTextBuffer.GetExtWildcard(save=False)
#		dlg = wx.FileDialog(self, "Choose a filename",
#							wildcard=wildcard,
#							style=wx.OPEN)
#		if dlg.ShowModal() == wx.ID_OK:
#			path = dlg.GetPath()
#			if path:
#				fileType = types[dlg.GetFilterIndex()]
#				self.rtc.LoadFile(path, fileType)
#		dlg.Destroy()
#
#		
#	def OnFileSave(self, evt):
#		if not self.rtc.GetFilename():
#			self.OnFileSaveAs(evt)
#			return
#		self.rtc.SaveFile()
#
#		
#	def OnFileSaveAs(self, evt):
#		wildcard, types = rt.RichTextBuffer.GetExtWildcard(save=True)
#
#		dlg = wx.FileDialog(self, "Choose a filename",
#							wildcard=wildcard,
#							style=wx.SAVE)
#		if dlg.ShowModal() == wx.ID_OK:
#			path = dlg.GetPath()
#			if path:
#				fileType = types[dlg.GetFilterIndex()]
#				ext = rt.RichTextBuffer.FindHandlerByType(fileType).GetExtension()
#				if not path.endswith(ext):
#					path += '.' + ext
#				self.rtc.SaveFile(path, fileType)
#		dlg.Destroy()
#		
#				
#	def OnFileViewHTML(self, evt):
#		# Get an instance of the html file handler, use it to save the
#		# document to a StringIO stream, and then display the
#		# resulting html text in a dialog with a HtmlWindow.
#		handler = rt.RichTextHTMLHandler()
#		handler.SetFlags(rt.RICHTEXT_HANDLER_SAVE_IMAGES_TO_MEMORY)
#		handler.SetFontSizeMapping([7,9,11,12,14,22,100])
#
#		import cStringIO
#		stream = cStringIO.StringIO()
#		if not handler.SaveStream(self.rtc.GetBuffer(), stream):
#			return
#
#		import wx.html
#		dlg = wx.Dialog(self, title="HTML", style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER)
#		html = wx.html.HtmlWindow(dlg, size=(500,400), style=wx.BORDER_SUNKEN)
#		html.SetPage(stream.getvalue())
#		btn = wx.Button(dlg, wx.ID_CANCEL)
#		sizer = wx.BoxSizer(wx.VERTICAL)
#		sizer.Add(html, 1, wx.ALL|wx.EXPAND, 5)
#		sizer.Add(btn, 0, wx.ALL|wx.CENTER, 10)
#		dlg.SetSizer(sizer)
#		sizer.Fit(dlg)
#
#		dlg.ShowModal()
#
#		handler.DeleteTemporaryImages()

	
	def OnFileExit(self, evt):
		self.Close(True)
	  
	def OnBold(self, evt):
		self.rtc.ApplyBoldToSelection()
		
	def OnItalic(self, evt): 
		self.rtc.ApplyItalicToSelection()
		
	def OnUnderline(self, evt):
		self.rtc.ApplyUnderlineToSelection()
		
	def OnAlignLeft(self, evt):
		self.rtc.ApplyAlignmentToSelection(wx.TEXT_ALIGNMENT_LEFT)
		
	def OnAlignRight(self, evt):
		self.rtc.ApplyAlignmentToSelection(wx.TEXT_ALIGNMENT_RIGHT)
		
	def OnAlignCenter(self, evt):
		self.rtc.ApplyAlignmentToSelection(wx.TEXT_ALIGNMENT_CENTRE)
		
	def OnIndentMore(self, evt):
		#attr = wx.TextAttr()
		attr = rt.RichTextAttr()
		attr.SetFlags(wx.TEXT_ATTR_LEFT_INDENT)
		ip = self.rtc.GetInsertionPoint()
		if ip > self.rtc.GetLastPosition():
			ip -= 1
		if self.rtc.GetStyle(ip, attr):
			r = rt.RichTextRange(ip, ip)
			if self.rtc.HasSelection():
				r = self.rtc.GetSelectionRange()

			attr.SetLeftIndent(attr.GetLeftIndent() + 100)
			attr.SetFlags(wx.TEXT_ATTR_LEFT_INDENT)
			self.rtc.SetStyle(r, attr)
	   
	def OnSelectAll(self, evt):
		self.rtc.SelectAll()

	def OnIndentLess(self, evt):
		#attr = wx.TextAttr()
		attr = rt.RichTextAttr()
		attr.SetFlags(wx.TEXT_ATTR_LEFT_INDENT)
		ip = self.rtc.GetInsertionPoint()
		if ip > self.rtc.GetLastPosition():
			ip -= 1
		if self.rtc.GetStyle(ip, attr):
			r = rt.RichTextRange(ip, ip)
			if self.rtc.HasSelection():
				r = self.rtc.GetSelectionRange()

		if attr.GetLeftIndent() >= 100:
			attr.SetLeftIndent(attr.GetLeftIndent() - 100)
			attr.SetFlags(wx.TEXT_ATTR_LEFT_INDENT)
			self.rtc.SetStyle(r, attr)

	def OnDropIndent(self,evt):
		attr = rt.RichTextAttr()
		attr.SetFlags(wx.TEXT_ATTR_LEFT_INDENT)
		ip = self.rtc.GetInsertionPoint()
		if self.rtc.GetStyle(ip, attr):
			r = rt.RichTextRange(ip, ip + 1)
			attr.SetLeftIndent(0)
			attr.SetFlags(wx.TEXT_ATTR_LEFT_INDENT)
			self.rtc.SetStyle(r, attr)
		
	def OnParagraphSpacingMore(self, evt):
		#attr = wx.TextAttr()
		attr = rt.RichTextAttr()
		attr.SetFlags(wx.TEXT_ATTR_PARA_SPACING_AFTER)
		ip = self.rtc.GetInsertionPoint()
		if self.rtc.GetStyle(ip, attr):
			r = rt.RichTextRange(ip, ip)
			if self.rtc.HasSelection():
				r = self.rtc.GetSelectionRange()

			attr.SetParagraphSpacingAfter(attr.GetParagraphSpacingAfter() + 20);
			attr.SetFlags(wx.TEXT_ATTR_PARA_SPACING_AFTER)
			self.rtc.SetStyle(r, attr)

		
	def OnParagraphSpacingLess(self, evt):
		#attr = wx.TextAttr()
		attr = rt.RichTextAttr()
		attr.SetFlags(wx.TEXT_ATTR_PARA_SPACING_AFTER)
		ip = self.rtc.GetInsertionPoint()
		if self.rtc.GetStyle(ip, attr):
			r = rt.RichTextRange(ip, ip)
			if self.rtc.HasSelection():
				r = self.rtc.GetSelectionRange()

			if attr.GetParagraphSpacingAfter() >= 20:
				attr.SetParagraphSpacingAfter(attr.GetParagraphSpacingAfter() - 20);
				attr.SetFlags(wx.TEXT_ATTR_PARA_SPACING_AFTER)
				self.rtc.SetStyle(r, attr)

		
	def OnLineSpacingSingle(self, evt): 
		#attr = wx.TextAttr()
		attr = rt.RichTextAttr()
		attr.SetFlags(wx.TEXT_ATTR_LINE_SPACING)
		ip = self.rtc.GetInsertionPoint()
		if self.rtc.GetStyle(ip, attr):
			r = rt.RichTextRange(ip, ip)
			if self.rtc.HasSelection():
				r = self.rtc.GetSelectionRange()

			attr.SetFlags(wx.TEXT_ATTR_LINE_SPACING)
			attr.SetLineSpacing(10)
			self.rtc.SetStyle(r, attr)
 
				
	def OnLineSpacingHalf(self, evt):
		#attr = wx.TextAttr()
		attr = rt.RichTextAttr()
		attr.SetFlags(wx.TEXT_ATTR_LINE_SPACING)
		ip = self.rtc.GetInsertionPoint()
		if self.rtc.GetStyle(ip, attr):
			r = rt.RichTextRange(ip, ip)
			if self.rtc.HasSelection():
				r = self.rtc.GetSelectionRange()

			attr.SetFlags(wx.TEXT_ATTR_LINE_SPACING)
			attr.SetLineSpacing(15)
			self.rtc.SetStyle(r, attr)

		
	def OnLineSpacingDouble(self, evt):
		#attr = wx.TextAttr()
		attr = rt.RichTextAttr()
		attr.SetFlags(wx.TEXT_ATTR_LINE_SPACING)
		ip = self.rtc.GetInsertionPoint()
		if self.rtc.GetStyle(ip, attr):
			r = rt.RichTextRange(ip, ip)
			if self.rtc.HasSelection():
				r = self.rtc.GetSelectionRange()

			attr.SetFlags(wx.TEXT_ATTR_LINE_SPACING)
			attr.SetLineSpacing(20)
			self.rtc.SetStyle(r, attr)


	def OnFont(self, evt):
		#if not self.rtc.HasSelection():
		#	return

		r = self.rtc.GetSelectionRange()
		fontData = wx.FontData()
		fontData.EnableEffects(False)
		#attr = wx.TextAttr()
		attr = rt.RichTextAttr()
		attr.SetFlags(wx.TEXT_ATTR_FONT)
		if self.rtc.GetStyle(self.rtc.GetInsertionPoint(), attr):
			fontData.SetInitialFont(attr.GetFont())

		dlg = wx.FontDialog(self, fontData)
		if dlg.ShowModal() == wx.ID_OK:
			fontData = dlg.GetFontData()
			font = fontData.GetChosenFont()
			if font:
				attr.SetFlags(wx.TEXT_ATTR_FONT)
				attr.SetFont(font)
				self.rtc.SetStyle(r, attr)
				if not self.rtc.HasSelection():
					self.rtc.BeginFont(font)
				self.selectedFontName = font.GetFaceName()
				self.selectedFontSize = font.GetPointSize()
		dlg.Destroy()

	def OnSetDefaultFont(self, evt):
		if self.selectedFontName != None and self.selectedFontSize != None:
			self.parent.folder_store.set_global('FONTNAME',self.selectedFontName)
			self.parent.folder_store.set_global('FONTSIZE',str(self.selectedFontSize))
			self.parent.folder_store.commit()

	def OnClearDefaultFont(self, evt):
		self.parent.folder_store.del_global('FONTNAME')
		self.parent.folder_store.del_global('FONTSIZE')
		self.parent.folder_store.commit()

	def OnColour(self, evt):
		colourData = wx.ColourData()
		#attr = wx.TextAttr()
		attr = rt.RichTextAttr()
		attr.SetFlags(wx.TEXT_ATTR_TEXT_COLOUR)
		if self.rtc.GetStyle(self.rtc.GetInsertionPoint(), attr):
			colourData.SetColour(attr.GetTextColour())

		dlg = wx.ColourDialog(self, colourData)
		if dlg.ShowModal() == wx.ID_OK:
			colourData = dlg.GetColourData()
			colour = colourData.GetColour()
			if colour:
				self.selectedColour = colour
				if not self.rtc.HasSelection():
					self.rtc.BeginTextColour(colour)
				else:
					r = self.rtc.GetSelectionRange()
					attr.SetFlags(wx.TEXT_ATTR_TEXT_COLOUR)
					attr.SetTextColour(colour)
					self.rtc.SetStyle(r, attr)
		dlg.Destroy()
		
	def OnUpdateBold(self, evt):
		evt.Check(self.rtc.IsSelectionBold())
	
	def OnUpdateItalic(self, evt): 
		evt.Check(self.rtc.IsSelectionItalics())
	
	def OnUpdateUnderline(self, evt): 
		evt.Check(self.rtc.IsSelectionUnderlined())
	
	def OnUpdateAlignLeft(self, evt):
		evt.Check(self.rtc.IsSelectionAligned(wx.TEXT_ALIGNMENT_LEFT))
		
	def OnUpdateAlignCenter(self, evt):
		evt.Check(self.rtc.IsSelectionAligned(wx.TEXT_ALIGNMENT_CENTRE))
		
	def OnUpdateAlignRight(self, evt):
		evt.Check(self.rtc.IsSelectionAligned(wx.TEXT_ALIGNMENT_RIGHT))

	
	def ForwardEvent(self, evt):
		# The RichTextCtrl can handle menu and update events for undo,
		# redo, cut, copy, paste, delete, and select all, so just
		# forward the event to it.
		self.rtc.ProcessEvent(evt)


	def MakeMenuBar(self):
		def doBind(item, handler, updateUI=None):
			self.Bind(wx.EVT_MENU, handler, item)
			if updateUI is not None:
				self.Bind(wx.EVT_UPDATE_UI, updateUI, item)
			
#		fileMenu = wx.Menu()
#		doBind( fileMenu.Append(-1, "&Open\tCtrl+O", "Open a file"),
#				self.OnFileOpen )
#		doBind( fileMenu.Append(-1, "&Save\tCtrl+S", "Save a file"),
#				self.OnFileSave )
#		doBind( fileMenu.Append(-1, "&Save As...\tF12", "Save to a new file"),
#				self.OnFileSaveAs )
#		fileMenu.AppendSeparator()
#		doBind( fileMenu.Append(-1, "&View as HTML", "View HTML"),
#				self.OnFileViewHTML)
#		fileMenu.AppendSeparator()
#		doBind( fileMenu.Append(-1, "E&xit\tCtrl+Q", "Quit this program"),
#				self.OnFileExit )
		
		fileMenu = wx.Menu()
		doBind( fileMenu.Append(id_file_save_html,"Save HTML..."),
				self.OnFileSaveHtml)
		doBind( fileMenu.Append(id_file_page_setup,"Page Setup..."),
				self.OnFilePageSetup)
		doBind( fileMenu.Append(id_file_print_preview,"Print Preview"),
				self.OnFilePrintPreview)
		doBind( fileMenu.Append(id_file_print,"Print..."),
				self.OnFilePrint)

		editMenu = wx.Menu()
		doBind( editMenu.Append(wx.ID_UNDO, "&Undo\tCtrl+Z"),
				self.ForwardEvent, self.ForwardEvent)
		doBind( editMenu.Append(wx.ID_REDO, "&Redo\tCtrl+Y"),
				self.ForwardEvent, self.ForwardEvent )
		editMenu.AppendSeparator()
		doBind( editMenu.Append(wx.ID_CUT, "Cu&t\tCtrl+X"),
				self.ForwardEvent, self.ForwardEvent )
		doBind( editMenu.Append(wx.ID_COPY, "&Copy\tCtrl+C"),
				self.ForwardEvent, self.ForwardEvent)
		doBind( editMenu.Append(wx.ID_PASTE, "&Paste\tCtrl+V"),
				self.ForwardEvent, self.ForwardEvent)
		doBind( editMenu.Append(wx.ID_CLEAR, "&Delete\tDel"),
				self.ForwardEvent, self.ForwardEvent)
		editMenu.AppendSeparator()
		doBind( editMenu.Append(wx.ID_SELECTALL, "Select A&ll\tCtrl+A"),
				self.ForwardEvent, self.ForwardEvent )
		
		#doBind( editMenu.AppendSeparator(),  )
		doBind( editMenu.Append(-1, "&Find...\tCtrl+F"), self.OnFindClick)
		#doBind( editMenu.Append(-1, "&Replace...\tCtrl+R"),  )

		formatMenu = wx.Menu()
		doBind( formatMenu.AppendCheckItem(-1, "&Bold\tCtrl+B"),
				self.OnBold, self.OnUpdateBold)
		doBind( formatMenu.AppendCheckItem(-1, "&Italic\tCtrl+I"),
				self.OnItalic, self.OnUpdateItalic)
		doBind( formatMenu.AppendCheckItem(-1, "&Underline\tCtrl+U"),
				self.OnUnderline, self.OnUpdateUnderline)
		formatMenu.AppendSeparator()
		doBind( formatMenu.AppendCheckItem(-1, "L&eft Align"),
				self.OnAlignLeft, self.OnUpdateAlignLeft)
		doBind( formatMenu.AppendCheckItem(-1, "&Centre"),
				self.OnAlignCenter, self.OnUpdateAlignCenter)
		doBind( formatMenu.AppendCheckItem(-1, "&Right Align"),
				self.OnAlignRight, self.OnUpdateAlignRight)
		formatMenu.AppendSeparator()
		doBind( formatMenu.Append(-1, "Indent &More"), self.OnIndentMore)
		doBind( formatMenu.Append(-1, "Indent &Less"), self.OnIndentLess)
		formatMenu.AppendSeparator()
		doBind( formatMenu.Append(-1, "Increase Paragraph &Spacing"), self.OnParagraphSpacingMore)
		doBind( formatMenu.Append(-1, "Decrease &Paragraph Spacing"), self.OnParagraphSpacingLess)
		formatMenu.AppendSeparator()
		doBind( formatMenu.Append(-1, "Normal Line Spacing"), self.OnLineSpacingSingle)
		doBind( formatMenu.Append(-1, "1.5 Line Spacing"), self.OnLineSpacingHalf)
		doBind( formatMenu.Append(-1, "Double Line Spacing"), self.OnLineSpacingDouble)
		formatMenu.AppendSeparator()
		doBind( formatMenu.Append(-1, "&Font..."), self.OnFont)
		doBind( formatMenu.Append(-1, "Set Font as Default"), self.OnSetDefaultFont)
		doBind( formatMenu.Append(-1, "Clear Default Font"), self.OnClearDefaultFont)
		
		mb = wx.MenuBar()
		mb.Append(fileMenu, "&File")
		mb.Append(editMenu, "&Edit")
		mb.Append(formatMenu, "F&ormat")
		self.SetMenuBar(mb)


	def MakeToolBar(self):
		def doBind(item, handler, updateUI=None):
			self.Bind(wx.EVT_TOOL, handler, item)
			if updateUI is not None:
				self.Bind(wx.EVT_UPDATE_UI, updateUI, item)
		
		#tbar = self.CreateToolBar()
		tbar = wx.ToolBar(self.bottomPanel,-1,style=wx.TB_HORIZONTAL)

#		doBind( tbar.AddTool(-1, images._rt_open.GetBitmap(),
#							shortHelpString="Open"), self.OnFileOpen)
#		doBind( tbar.AddTool(-1, images._rt_save.GetBitmap(),
#							shortHelpString="Save"), self.OnFileSave)
#		tbar.AddSeparator()
		doBind( tbar.AddTool(wx.ID_CUT, images._rt_cut.GetBitmap(),
							shortHelpString="Cut"), self.ForwardEvent, self.ForwardEvent)
		doBind( tbar.AddTool(wx.ID_COPY, images._rt_copy.GetBitmap(),
							shortHelpString="Copy"), self.ForwardEvent, self.ForwardEvent)
		doBind( tbar.AddTool(wx.ID_PASTE, images._rt_paste.GetBitmap(),
							shortHelpString="Paste"), self.ForwardEvent, self.ForwardEvent)
		tbar.AddSeparator()
		doBind( tbar.AddTool(wx.ID_UNDO, images._rt_undo.GetBitmap(),
							shortHelpString="Undo"), self.ForwardEvent, self.ForwardEvent)
		doBind( tbar.AddTool(wx.ID_REDO, images._rt_redo.GetBitmap(),
							shortHelpString="Redo"), self.ForwardEvent, self.ForwardEvent)
		tbar.AddSeparator()
		doBind( tbar.AddTool(-1, images._rt_bold.GetBitmap(), isToggle=True,
							shortHelpString="Bold"), self.OnBold, self.OnUpdateBold)
		doBind( tbar.AddTool(-1, images._rt_italic.GetBitmap(), isToggle=True,
							shortHelpString="Italic"), self.OnItalic, self.OnUpdateItalic)
		doBind( tbar.AddTool(-1, images._rt_underline.GetBitmap(), isToggle=True,
							shortHelpString="Underline"), self.OnUnderline, self.OnUpdateUnderline)
		tbar.AddSeparator()
		doBind( tbar.AddTool(-1, images._rt_alignleft.GetBitmap(), isToggle=True,
							shortHelpString="Align Left"), self.OnAlignLeft, self.OnUpdateAlignLeft)
		doBind( tbar.AddTool(-1, images._rt_centre.GetBitmap(), isToggle=True,
							shortHelpString="Center"), self.OnAlignCenter, self.OnUpdateAlignCenter)
		doBind( tbar.AddTool(-1, images._rt_alignright.GetBitmap(), isToggle=True,
							shortHelpString="Align Right"), self.OnAlignRight, self.OnUpdateAlignRight)
		tbar.AddSeparator()
		doBind( tbar.AddTool(-1, images2.select_all.GetBitmap(),
							shortHelpString="Select All"), self.OnSelectAll)
		doBind( tbar.AddTool(-1, images._rt_indentless.GetBitmap(),
							shortHelpString="Indent Less"), self.OnIndentLess)
		doBind( tbar.AddTool(-1, images._rt_indentmore.GetBitmap(),
							shortHelpString="Indent More"), self.OnIndentMore)
		tbar.AddSeparator()
		doBind( tbar.AddTool(-1, images._rt_font.GetBitmap(),
							shortHelpString="Font"), self.OnFont)
		doBind( tbar.AddTool(-1, images._rt_colour.GetBitmap(),
							shortHelpString="Font Colour"), self.OnColour)

		tbar.Realize()
		self.editToolbar = tbar
		self.mainSizer.Add(tbar,0,wx.EXPAND)

#----------------------- end stolen code ------------------------------

	def CreatePrintHTML(self):
		header = '<body>'
		for i in range(self.addressGrid.GetNumberRows()):
			if i != 0:
				header += "<br>\n"
			label = self.addressGrid.GetRowLabelValue(i)
			value = self.addressGrid.GetCellValue(i,0)
			if value == None or value == '':
				continue
			header += '<b>' + html_escape(label) + ':</b> ' + html_escape(value)
		header += "<hr>\n"

		buf = cStringIO.StringIO()
		handler = wx.richtext.RichTextHTMLHandler()
		handler.SaveStream(self.rtc.GetBuffer(), buf)
		body_html = buf.getvalue().decode('utf-8')
		body_html = body_html.replace('<body>',header,1)
		return body_html

	def OnFileSaveHtml(self,event):
		fileDialog = wx.FileDialog(self,message = "Save HTML as...", style = wx.FD_SAVE)
		result = fileDialog.ShowModal()
		if result != wx.ID_OK:
			return
		outPath = fileDialog.GetPath()
		try:
			fh = codecs.open(outPath,'w','utf-8')
			fh.write(self.CreatePrintHTML())
			fh.close()
		except IOError as exc:
			pass

	def OnFilePageSetup(self,event):
		self.parent.htmlPrinting.SetParentWindow(self)
		self.parent.htmlPrinting.PageSetup()

	def OnFilePrintPreview(self,event):
		body_html = self.CreatePrintHTML()
		self.parent.htmlPrinting.SetParentWindow(self)
		self.parent.htmlPrinting.PreviewText(body_html)

	def OnFilePrint(self,event):
		body_html = self.CreatePrintHTML()
		self.parent.htmlPrinting.SetParentWindow(self)
		self.parent.htmlPrinting.PrintText(body_html)

# EOF
