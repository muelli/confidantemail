# tray icon: http://stackoverflow.com/questions/6389580/quick-and-easy-trayicon-with-python

import re
import wx
import wx.grid
import wx.richtext as rt
import wx.html
import wx.lib.newevent
import images
import images2
import os
import cStringIO
import hashlib
import zipfile
import thread
import codecs
import threading
import time
import pickle
import datetime
import logging
import folders
import filestore
import global_config
import message_edit_window

re_keyid = re.compile("^.*\s\s*([0-9A-F]{40})\s*$|^\s*([0-9A-F]{40})\s*$",re.IGNORECASE)
re_remove_bytes = re.compile("^(.*) \([0-9,]+ bytes\)$")
re_chop_filename_backslash = re.compile("^(.+)\\\\[^\\\\]*$")
re_chop_filename_slash = re.compile("^(.+)/[^/]*$")
re_check_date = re.compile("^(CheckDate: )(\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ)$",re.IGNORECASE)
re_forwarded = re.compile("^ForwardedMessageId: ([0123456789abcdef]{40})$",re.IGNORECASE)
re_name_email = re.compile("^(.*) <([^>]+)>$")

id_reply = 1
id_reply_all = 2
id_forward = 3
id_forward_all = 4
id_show_original = 5
id_delete = 6
id_archive = 7
id_cancel = 8
id_detach_one = 9
id_detach_checked = 10
id_detach_all = 11
id_smaller = 12
id_larger = 13
id_find = 14
id_reenable_show_original_timer = 15

id_file_save_html = 101
id_file_page_setup = 102
id_file_print_preview = 103
id_file_print = 104
id_edit_find = 105

def StripBytesLabel(instr):
	m = re_remove_bytes.match(instr)
	if m:
		return m.group(1)
	else:
		return instr

html_escape_table = { "&": "&amp;", '"': "&quot;", "'": "&apos;", ">": "&gt;", "<": "&lt;", }

def html_escape(text):
	"""Produce entities within text."""
	return "".join(html_escape_table.get(c,c) for c in text)

saveAttachThreadEvent,EVT_SAVE_ATTACH_THREAD = wx.lib.newevent.NewEvent()

class AddressGrid(wx.grid.Grid):
	def __init__(self,parent,topFrame,maxRowsToDisplay,systemMessageMode = False):
		self.parent = parent
		self.topFrame = topFrame
		self.dateformat = global_config.date_format()
		self.maxRowsToDisplay = maxRowsToDisplay
		self.SaveAttachProgressDialog = None
		self.SaveAttachCancel = threading.Event()
		wx.grid.Grid.__init__(self,parent,-1)
		self.EnableDragColSize(False)
		self.EnableDragRowSize(False)
		self.EnableEditing(False)
		self.BeginBatch()
		if systemMessageMode == True:
			numRows = 4
		else:
			numRows = 4 + len(topFrame.toAddrs) + len(topFrame.ccAddrs) + len(topFrame.attachments)
		self.CreateGrid(numRows,1)
		self.SetRowLabelAlignment(wx.ALIGN_RIGHT,wx.ALIGN_CENTRE)
		self.SetRowLabelValue(0,"From")
		self.SetCellValue(0,0,self.topFrame.fromAddr)
		self.SetRowLabelValue(1,"Subject")
		self.SetCellValue(1,0,self.topFrame.subject)
		self.SetRowLabelValue(2,"Sent Date")
		self.SetCellValue(2,0,self.dateformat.localize_datetime(self.topFrame.sentDate))
		if systemMessageMode == True:
			i = 3
		else:
			self.SetRowLabelValue(3,"Signature")
			self.SetCellValue(3,0,topFrame.sigStatus)
			i = 4
		for recip in self.topFrame.toAddrs:
			self.SetRowLabelValue(i,"To")
			self.SetCellValue(i,0,recip)
			i += 1
		for recip in self.topFrame.ccAddrs:
			self.SetRowLabelValue(i,"Cc")
			self.SetCellValue(i,0,recip)
			i += 1
		for attach in self.topFrame.attachments:
			filename,file_size = attach
			self.SetRowLabelValue(i,"File")
			self.SetCellValue(i,0,filename + ' (' + format(file_size,',d') + ' bytes)')
			i += 1

		self.EndBatch()
		wx.CallAfter(self.AdjustSash)
		self.SetSelectionMode(wx.grid.Grid.SelectRows)
		self.HideColLabels()
		self.SetRowLabelSize(wx.grid.GRID_AUTOSIZE)
		self.Bind(wx.EVT_SIZE,self.OnResize)
		self.parent.Bind(wx.EVT_SPLITTER_SASH_POS_CHANGED,self.OnSashPosChanged)
		self.Bind(wx.grid.EVT_GRID_CELL_LEFT_CLICK,self.OnLeftClickCell)
		self.Bind(wx.grid.EVT_GRID_CELL_LEFT_DCLICK,self.OnDoubleClickCell)
		self.Bind(wx.grid.EVT_GRID_CELL_RIGHT_CLICK,self.OnRightClickCell)
		self.Bind(EVT_SAVE_ATTACH_THREAD,self.SaveAttachUpdate)


	def OnResize(self,event):
		# derived from http://forums.wxwidgets.org/viewtopic.php?t=90
		# this resizes the entry field to fit the window
		clientSize = self.GetClientSize()
		windowWidth = clientSize.GetWidth()
		restWidth = self.GetRowLabelSize()
		colWidth = windowWidth - restWidth
		#DBGOUT#print "sizes",clientSize,windowWidth,restWidth,colWidth
		if colWidth > 0:
			self.SetColSize(0,colWidth)

	def AdjustSash(self,getInitial = False):
		rowHeight = self.GetRowSize(0)
		rowsToDisplay = self.GetNumberRows()
		if rowsToDisplay > self.maxRowsToDisplay:
			rowsToDisplay = self.maxRowsToDisplay
		#DBGOUT#print rowHeight,rowsToDisplay,"blah"
		newSashPosition = rowsToDisplay * rowHeight
		if getInitial == True:
			return newSashPosition
		else:
			self.parent.SetSashPosition(newSashPosition)
			wx.CallAfter(self.ForceRefresh)
	
	def OnSashPosChanged(self,event):
		self.ForceRefresh()
		#DBGOUT#print "Sash was moved to",self.parent.GetSashPosition()

	def OnDoubleClickCell(self,event):
		clickedRow = event.GetRow()
		rowLabel = self.GetRowLabelValue(clickedRow)
		if rowLabel == 'File':
			self.clickedRow = clickedRow
			self.selectedRows = [ ]
			fileNames = [ ]
			fileNames.append(StripBytesLabel(self.GetCellValue(self.clickedRow,0)))
			self.SaveAttachCommon(fileNames,False)

	def OnLeftClickCell(self,event):
		clickedRow = event.GetRow()
		rowLabel = self.GetRowLabelValue(clickedRow)
		if rowLabel == 'Signature':
			self.DisplaySignature(event)
		else:
			event.Skip()

	def OnRightClickCell(self,event):
		clickedRow = event.GetRow()
		selectedRows = self.GetSelectedRows()
		rowLabel = self.GetRowLabelValue(clickedRow)
		if rowLabel == 'Signature':
			self.DisplaySignature(event)
			return
		if rowLabel != 'File':
			return
		fileName = StripBytesLabel(self.GetCellValue(clickedRow,0))
		self.clickedRow = clickedRow
		self.selectedRows = selectedRows
		detachFilesMenu = wx.Menu()
		detachFilesMenu.Append(id_detach_one,"Save " + fileName)
		self.Bind(wx.EVT_MENU,self.OnSaveOneAttach,id = id_detach_one)
		if len(selectedRows) > 0:
			detachFilesMenu.Append(id_detach_checked,"Save Selected Attachments")
			self.Bind(wx.EVT_MENU,self.OnSaveSelAttach,id = id_detach_checked)
		detachFilesMenu.Append(id_detach_all,"Save All Attachments")
		self.Bind(wx.EVT_MENU,self.OnSaveAllAttach,id = id_detach_all)
		self.PopupMenu(detachFilesMenu)
		detachFilesMenu.Destroy()
		
	def OnSaveOneAttach(self,event,bg = False):
		fileNames = [ ]
		fileNames.append(StripBytesLabel(self.GetCellValue(self.clickedRow,0)))
		self.SaveAttachCommon(fileNames,bg)

	def OnSaveSelAttach(self,event,bg = False):
		fileNames = [ ]
		for i in self.selectedRows:
			fileNames.append(StripBytesLabel(self.GetCellValue(i,0)))
		self.SaveAttachCommon(fileNames,bg)
			
	def OnSaveAllAttach(self,event,bg = False):
		fileNames = [ ]
		for i in range(self.GetNumberRows()):
			label = self.GetRowLabelValue(i)
			if label == 'File':
				fileNames.append(StripBytesLabel(self.GetCellValue(i,0)))
		self.SaveAttachCommon(fileNames,bg)

	def SaveAttachCommon(self,filenames,bg):
		n = len(filenames)
		if n == 0:
			return
		elif n == 1:
			label = "Save attached file "+filenames[0]
			filenameStr = filenames[0]
		else:
			label = "Save "+str(n)+" attached files"
			filenameStr = "MULTIPLE FILES"
		fileDialog = wx.FileDialog(self,message = label, style = wx.FD_SAVE, defaultFile = filenameStr)
		result = fileDialog.ShowModal()
		if result != wx.ID_OK:
			return
		outPath = fileDialog.GetPath()
		saveAttachList = [ ]
		if n == 1:
			saveAttachList.append( (filenames[0],outPath) )
		else:
			if os.sep == '\\':
				m = re_chop_filename_backslash.match(outPath)
				if m:
					outPath = m.group(1)				
			else:
				m = re_chop_filename_slash.match(outPath)
				if m:
					outPath = m.group(1)				
			for fn in filenames:
				outFile = outPath + os.sep + fn
				saveAttachList.append( (fn,outFile) )

		nExist =0
		existList = ''
		for filepair in saveAttachList:
			zipPath,outPath = filepair
			if os.path.exists(outPath):
				nExist += 1
				if nExist > 1:
					existList = existList + "\n" + outPath
				else:
					existList = outPath	
		if nExist > 0:
			if nExist > 1:
				message = "Files exist:\n" + existList + "\nDo you want to replace them?"	
			else:
				message = "File exists:\n" + existList + "\nDo you want to replace it?"	
			dlg = wx.MessageDialog(self,message,"Confirm overwrite",wx.YES_NO|wx.CENTRE|wx.ICON_EXCLAMATION)
			if dlg.ShowModal() != wx.ID_YES:
				dlg.Destroy()
				return
			else:
				dlg.Destroy()
					
		totalSize = long(0)
		self.topFrame.openZipIfClosed()
		for member in self.topFrame.zipFile.infolist():
			#DBGOUT#print member.filename,filenames
			if member.filename[1:] in filenames:
				totalSize += member.file_size

		if bg == False:
			if n == 1:
				title = "Saving Attachment"
			else:
				title = "Saving Attachments"
			message = "Saving " + saveAttachList[0][0]
			scaleFactor = int(totalSize / 32768) # dialog does not seem to like numbers over 64K
			if scaleFactor == 0:
				scaleFactor = 1
			reportSize = int(totalSize/scaleFactor) + 1
			self.SaveAttachProgressDialog = wx.GenericProgressDialog(title,message,reportSize,parent = self.topFrame,style = wx.PD_CAN_ABORT|wx.PD_AUTO_HIDE)
			self.SaveAttachProgressDialog.Show()
			self.SaveAttachCancel.clear()
			thread.start_new_thread(self.SaveAttachThread,(n,totalSize,scaleFactor,saveAttachList))
			
	def SaveAttachUpdate(self,event):
		bytesSaved = event.args[0]
		scaleFactor = event.args[1]
		currentFileName = event.args[2]
		isDone = event.args[3]
		reportSaved = int(bytesSaved/scaleFactor) # progress bar wants an int
		if isDone == True:
			reportSaved += 1
		if self.SaveAttachProgressDialog != None:
			cont,junk = self.SaveAttachProgressDialog.Update(reportSaved,"Saving " + currentFileName)
			if cont == False:
				self.SaveAttachCancel.set()
				self.SaveAttachProgressDialog.Destroy()
				self.SaveAttachProgressDialog = None
	
	def SaveAttachThread(self,numFiles,totalSize,scaleFactor,saveAttachList):
		bytesWritten = long(0)
		chunkSize = 262144
		lastUpdate = 0.0
		for filepair in saveAttachList:
			zipPath,outPath = filepair
			ifd = self.topFrame.zipFile.open('_'+zipPath,'r')
			ofd = open(outPath,'wb')
			while True:
				buf = ifd.read(chunkSize)
				if len(buf) == 0:
					break
				ofd.write(buf)
				bytesWritten += len(buf)
				nowTime = time.time()
				if nowTime - lastUpdate > 1.0: # sending these too fast causes a failure
					lastUpdate = nowTime	
					evt = saveAttachThreadEvent(args = [ bytesWritten,scaleFactor,zipPath,False ] )
					wx.PostEvent(self,evt)
				if self.SaveAttachCancel.isSet() == True:
					break
				if len(buf) < chunkSize:
					break
			ifd.close()
			ofd.close()
			if self.SaveAttachCancel.isSet() == True:
				os.unlink(outPath)
				break
		if self.SaveAttachCancel.isSet() == False:
			evt = saveAttachThreadEvent(args = [ totalSize,scaleFactor,zipPath,False ] )
			wx.PostEvent(self,evt)
			time.sleep(1)
			evt = saveAttachThreadEvent(args = [ totalSize,scaleFactor,zipPath,True ] )
			wx.PostEvent(self,evt)

	def DisplaySignature(self,event):
		popupWin = wx.PopupTransientWindow(self, style = wx.SIMPLE_BORDER)
		panel = wx.Panel(popupWin)
		st = wx.StaticText(panel, -1, self.topFrame.sigData.rstrip('\r\n'))
		sizer = wx.BoxSizer(wx.VERTICAL)
		sizer.Add(st, 0, wx.ALL, 5)
		panel.SetSizer(sizer)
		sizer.Fit(panel)
		sizer.Fit(popupWin)
		pos = event.GetPosition()
		pos = self.ClientToScreen(pos)
		popupWin.Position(pos,wx.DefaultSize)
		popupWin.Layout()
		popupWin.Popup()
		
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

class MessageViewFrame(wx.Frame):

	def __init__(self,parent,messageId,fromFolder,systemMessage = None,textOnly = False,forceRich = False):
		self.parent = parent
		self.gui = self.parent.gui
		self.zipFile = None
		self.messageId = messageId
		self.fromFolder = fromFolder
		self.textOnly = textOnly
		self.dateformat = global_config.date_format()
		self.sigStatus = "Error, signature check not performed!"
		self.fromAddr = 'No from address'
		self.subject = 'No subject'
		self.sentDate = 'No date'
		self.toAddrs = [ ]
		self.ccAddrs = [ ]
		self.attachments = [ ]
		self.fontX = 1.0 * self.gui.editorScaleFactor
		self.fontY = 1.0 * self.gui.editorScaleFactor
		self.htmlWindow = None
		self.rtc = None
		if systemMessage != None:
			self.initSystemMessage(systemMessage)
			return
		self.filePath = self.parent.local_store.getPath(messageId)
		self.zipFilePath = self.filePath + '.ZIP'
		self.sigFilePath = self.filePath + '.SIG'
		self.fontSize = 10
		self.forwardedMessageId = None
		self.findDialog = None
		self.untrustedMessage = False

		self.zipFile = zipfile.ZipFile(self.zipFilePath,'r')
		self.headerData = self.zipFile.read('HEADER.TXT').decode('utf-8')
		fh = codecs.open(self.sigFilePath,'r','utf-8')
		sigData = fh.read()
		fh.close()

		for line in self.headerData.split('\n'):
			line = line.rstrip('\r\n')
			lineU = line.upper()
			if lineU[0:6] == 'FROM: ':
				self.fromAddr = line[6:]
			elif lineU[0:9] == 'SUBJECT: ':
				self.subject = line[9:]
			elif lineU[0:4] == 'TO: ':
				self.toAddrs.append(line[4:])
			elif lineU[0:4] == 'CC: ':
				self.ccAddrs.append(line[4:])
			elif lineU[0:6] == 'DATE: ':
				self.sentDate = line[6:]
			else:
				m = re_forwarded.match(line)
				if m:
					self.forwardedMessageId = m.group(1).upper()

		self.sigData = ""	
		sigGotValid = False
		sigKeyMatch = False
		fromKeyid = ""
		m = re_keyid.match(self.fromAddr)
		if m:
			fromKeyid = m.group(1).upper()
			if fromKeyid == None or fromKeyid == '':
				fromKeyid = m.group(2).upper()
		for line in sigData.split('\n'):
			line = line.rstrip('\r\n')
			m = re_check_date.match(line)
			if m:
				self.sigData += m.group(1) + self.dateformat.localize_datetime(m.group(2)) + ' [' + m.group(2) + ']' + '\n'
			else:
				self.sigData += line + '\n'
			#DBGOUT#print line
			if line == 'Valid: True':
				sigGotValid = True
			elif line[0:13] == 'Fingerprint: ':
				sigFingerprint = line[13:].upper()
				if sigFingerprint == fromKeyid:
					sigKeyMatch = True
			elif line[0:19] == 'PubkeyFingerprint: ': # subkey signing case
				pkFingerprint = line[19:].upper()
				if pkFingerprint == fromKeyid:
					sigKeyMatch = True
					sigFingerprint = pkFingerprint
		if sigKeyMatch == False:
			self.sigData += "From line fingerprint does not match signature fingerprint.\n" + \
				"This may be a forgery attempt.\n"
			self.untrustedMessage = True
				
		#DBGOUT#print sigGotValid,sigKeyMatch
		if sigGotValid == True and sigKeyMatch == True:
			sigFingerprintL = sigFingerprint.lower()
			self.sigStatus = "Good signature from "	+ sigFingerprintL
			# Code below catches the case where from address of the message
			# does not match the address in the key. Display address in the key.
			address = ""
			for key in self.gui.keyList:
				address = ""
				if key['fingerprint'] == sigFingerprint:
					username = key['uids'][0]
					m = re_name_email.match(username)
					if m:
						username = m.group(1)
						address = m.group(2)
					expSigStr = username + ' <' + address + '> ' + sigFingerprintL
					if expSigStr != self.fromAddr:
						self.sigStatus = "Good signature from "	+ expSigStr
					break
			# Now look for key collision, someone may be using a bogus key
			addressL = address.lower()
			for key in self.gui.keyList:
				if key['fingerprint'] != sigFingerprint:
					col_username = key['uids'][0]
					col_address = ""
					m = re_name_email.match(col_username)
					if m:
						col_username = m.group(1)
						col_address = m.group(2)
					if col_address.lower() == addressL:
						self.sigStatus = "Good signature with key collision, click for details"
						self.sigData += 'Keys ' + key['fingerprint'] + "\nand " + \
							sigFingerprint + "\nhave the same email address " + address + "\n" + \
							"One of these may be a forged key. Delete the forged key\n" + \
							"from your Address Book to make this message go away.\n"
						self.untrustedMessage = True
		else:
			self.sigStatus = "BAD SIGNATURE! Click for details"
			self.untrustedMessage = True

		if self.untrustedMessage == True and forceRich == False:
			textOnly = True # avoid opening untrusted message Rich Text which might enable an exploit against Wx

		for member in self.zipFile.infolist():
			if member.filename[0] == '_':
				filename = member.filename[1:]
				file_size = member.file_size
				self.attachments.append( (filename,file_size) )
				#DBGOUT#print 'attachment',member.filename,member.file_size
		wx.Frame.__init__(self,parent,-1,self.subject,size=self.parent.gui.view_window_size)
		self.statusBar = self.CreateStatusBar(1)

		self.menuBar = wx.MenuBar()
		fileMenu = wx.Menu()
		fileMenu.Append(id_file_save_html,"Save HTML...")
		fileMenu.Append(id_file_page_setup,"Page Setup...")
		fileMenu.Append(id_file_print_preview,"Print Preview")
		fileMenu.Append(id_file_print,"Print...")
		self.menuBar.Append(fileMenu,"&File")

		editMenu = wx.Menu()
		editMenu.Append(wx.ID_COPY, "&Copy\tCtrl+C")
		editMenu.Append(wx.ID_SELECTALL, "Select A&ll\tCtrl+A")
		editMenu.Append(id_edit_find, "&Find...\tCtrl+F")
		self.menuBar.Append(editMenu,"&Edit")

		self.SetMenuBar(self.menuBar)
		self.Bind(wx.EVT_MENU,self.OnFileSaveHtml,id = id_file_save_html)
		self.Bind(wx.EVT_MENU,self.OnFilePageSetup,id = id_file_page_setup)
		self.Bind(wx.EVT_MENU,self.OnFilePrintPreview,id = id_file_print_preview)
		self.Bind(wx.EVT_MENU,self.OnFilePrint,id = id_file_print)
		self.Bind(wx.EVT_MENU,self.ForwardEvent,id = wx.ID_COPY)
		self.Bind(wx.EVT_MENU,self.ForwardEvent,id = wx.ID_SELECTALL)
		self.Bind(wx.EVT_MENU,self.OnFindClick,id = id_edit_find)

		#| wx.TB_HORZ_LAYOUT
		toolbar = self.CreateToolBar( wx.TB_HORIZONTAL | wx.NO_BORDER | wx.TB_FLAT | wx.TB_TEXT )
		tsize = (24,24)
		new_bmp = images2.composition.GetBitmap()
		reply_bmp = images2.reply.GetBitmap()
		replyall_bmp = images2.replyall.GetBitmap()
		forward_bmp = images2.forward.GetBitmap()
		smaller_bmp = images2.smaller.GetBitmap()
		larger_bmp = images2.larger.GetBitmap()
		find_bmp = images2.find.GetBitmap()
		archive_bmp = images2.archive.GetBitmap()
		delete_bmp = images2.trashcan.GetBitmap()
		close_bmp = images2.closex.GetBitmap()
		toolbar.AddLabelTool(id_reply, "Reply", reply_bmp, shortHelp="Reply", longHelp="Reply to sender only")
		toolbar.AddLabelTool(id_reply_all, "Reply All", replyall_bmp, shortHelp="Reply All", longHelp="Reply to all recipients")
		toolbar.AddLabelTool(id_forward, "Fwd Text", forward_bmp, shortHelp="Forward Text", longHelp="Forward the message text only")
		toolbar.AddLabelTool(id_forward_all, "Fwd All", forward_bmp, shortHelp="Forward All", longHelp="Forward the message, attachments, and signature")
		if self.forwardedMessageId != None:
			toolbar.AddLabelTool(id_show_original, "Show Original", forward_bmp, shortHelp="Show Original Message", longHelp="Show the forwarded message with signature")
		toolbar.AddLabelTool(id_smaller, "Smaller", smaller_bmp, shortHelp="Smaller", longHelp="Make text smaller")
		toolbar.AddLabelTool(id_larger, "Larger", larger_bmp, shortHelp="Larger", longHelp="Make text larger")
		toolbar.AddLabelTool(id_find, "Find", find_bmp, shortHelp="Find text", longHelp="Search for a string in the message")
		if self.fromFolder != folders.id_archive:
			toolbar.AddLabelTool(id_archive, "Archive", archive_bmp, shortHelp="Archive", longHelp="Move message to archive folder")
		if self.fromFolder != folders.id_deleted:
			toolbar.AddLabelTool(id_delete, "Delete", delete_bmp, shortHelp="Delete", longHelp="Delete this message")
		toolbar.AddLabelTool(id_cancel, "Close", close_bmp, shortHelp="Close", longHelp="Close this window")
		toolbar.Realize()
		self.toolbar = toolbar
		self.reenableShowOriginalTimer = wx.Timer(self,id = id_reenable_show_original_timer)
		self.Bind(wx.EVT_TOOL,self.OnReplyClick,id = id_reply)
		self.Bind(wx.EVT_TOOL,self.OnReplyAllClick,id = id_reply_all)
		self.Bind(wx.EVT_TOOL,self.OnForwardClick,id = id_forward)
		self.Bind(wx.EVT_TOOL,self.OnForwardAllClick,id = id_forward_all)
		if self.forwardedMessageId != None:
			self.Bind(wx.EVT_TOOL,self.OnShowOriginalClick,id = id_show_original)
		self.Bind(wx.EVT_TOOL,self.OnSmallerClick,id = id_smaller)
		self.Bind(wx.EVT_TOOL,self.OnLargerClick,id = id_larger)
		self.Bind(wx.EVT_TOOL,self.OnFindClick,id = id_find)
		if self.fromFolder != folders.id_archive:
			self.Bind(wx.EVT_TOOL,self.OnArchiveClick,id = id_archive)
		if self.fromFolder != folders.id_deleted:
			self.Bind(wx.EVT_TOOL,self.OnDeleteClick,id = id_delete)
		self.Bind(wx.EVT_TOOL,self.OnCancelClick,id = id_cancel)
		self.Bind(wx.EVT_TIMER,self.OnReenableShowOriginalTimer,id = id_reenable_show_original_timer)

		self.horizontalSplitter = wx.SplitterWindow(self,style = wx.SP_LIVE_UPDATE)
		self.mainSizer = wx.BoxSizer(wx.VERTICAL)
		self.addressGrid = AddressGrid(self.horizontalSplitter,self,8)
		self.bottomPanel = wx.Panel(self.horizontalSplitter)
		self.bottomPanel.SetSizer(self.mainSizer)

		bodyXml = None
		bodyHtml = None
		bodyText = ''
		if textOnly == False:
			try:
				bodyXml = self.zipFile.read('BODY.XML')
			except (IOError,KeyError):
				pass
			if bodyXml == None:
				try:
					bodyHtml = self.zipFile.read('BODY.HTML')
					bodyHtml = bodyHtml.decode('utf-8')
				except (IOError,KeyError):
					pass
		if bodyXml == None and bodyHtml == None:
			try:
				bodyText = self.zipFile.read('BODY.TXT')
				bodyText = bodyText.decode('utf-8')
				if self.untrustedMessage == True and forceRich == False:
					bodyText = "Untrusted message opened text-only. To force Rich Text, use\nOpen Rich Text from the message list right-click menu.\n" + \
						"________________________________________________________________________________\n\n" + bodyText
			except (IOError,KeyError):
				pass
		wx.CallAfter(self.initCont,bodyHtml,bodyXml,bodyText)

	# This avoids some bugs (let it render before filling in the text) and also causes the window to appear
	# before the rendering delay, so the user is not left wondering if his click registered.
	def initCont(self,bodyHtml,bodyXml,bodyText):
		if bodyHtml != None:
			self.htmlWindow = wx.html.HtmlWindow(self.bottomPanel, style = wx.VSCROLL|wx.HSCROLL|wx.NO_BORDER)
			self.htmlWindow.SetPage(bodyHtml)
			self.bodyHtml = bodyHtml # for printing
			self.mainSizer.Add(self.htmlWindow,1,wx.EXPAND,0)
		else:
			self.rtc = rt.RichTextCtrl(self.bottomPanel, style=wx.VSCROLL|wx.HSCROLL|wx.NO_BORDER);
			self.rtc.SetScale(self.fontX,self.fontY)
			if bodyXml != None:
				buf = cStringIO.StringIO(bodyXml)
				handler = wx.richtext.RichTextXMLHandler()
				handler.SetFlags(wx.richtext.RICHTEXT_HANDLER_INCLUDE_STYLESHEET)
				handler.LoadStream(self.rtc.GetBuffer(), buf)
				buf.close()
			else:
				self.rtc.SetValue(bodyText)
			self.rtc.SetEditable(False)
			self.mainSizer.Add(self.rtc,1,wx.EXPAND,0)
		initialSashPosition = self.addressGrid.AdjustSash(getInitial = True)
		self.horizontalSplitter.SplitHorizontally(self.addressGrid,self.bottomPanel,initialSashPosition)

	def ForwardEvent(self, evt):
		# The RichTextCtrl can handle menu and update events for undo,
		# redo, cut, copy, paste, delete, and select all, so just
		# forward the event to it.
		self.rtc.ProcessEvent(evt)

	def openZipIfClosed(self):
		if self.zipFile == None:
			self.zipFile = zipfile.ZipFile(self.zipFilePath,'r')

	def initSystemMessage(self,systemMessage):
		hash,self.fromAddr = systemMessage['FR']
		self.toAddrs.append(self.parent.gui.from_address)
		self.subject = systemMessage['SU']
		self.sentDate = systemMessage['DA']
		wx.Frame.__init__(self,self.parent,-1,self.subject,size=self.parent.gui.view_window_size)
		toolbar = self.CreateToolBar( wx.TB_HORIZONTAL | wx.NO_BORDER | wx.TB_FLAT | wx.TB_TEXT )
		tsize = (24,24)
		smaller_bmp = images2.smaller.GetBitmap()
		larger_bmp = images2.larger.GetBitmap()
		delete_bmp = images2.trashcan.GetBitmap()
		close_bmp = images2.closex.GetBitmap()
		toolbar.AddLabelTool(id_smaller, "Smaller", smaller_bmp, shortHelp="Smaller", longHelp="Make text smaller")
		toolbar.AddLabelTool(id_larger, "Larger", larger_bmp, shortHelp="Larger", longHelp="Make text larger")
		toolbar.AddLabelTool(id_delete, "Delete", delete_bmp, shortHelp="Delete", longHelp="Delete this message")
		toolbar.AddLabelTool(id_cancel, "Close", close_bmp, shortHelp="Close", longHelp="Close this window")
		toolbar.Realize()
		self.toolbar = toolbar
		self.Bind(wx.EVT_TOOL,self.OnSmallerClick,id = id_smaller)
		self.Bind(wx.EVT_TOOL,self.OnLargerClick,id = id_larger)
		self.Bind(wx.EVT_TOOL,self.OnDeleteClick,id = id_delete)
		self.Bind(wx.EVT_TOOL,self.OnCancelClick,id = id_cancel)
		self.horizontalSplitter = wx.SplitterWindow(self,style = wx.SP_LIVE_UPDATE)
		self.mainSizer = wx.BoxSizer(wx.VERTICAL)
		self.addressGrid = AddressGrid(self.horizontalSplitter,self,8,True)
		self.bottomPanel = wx.Panel(self.horizontalSplitter)
		self.bottomPanel.SetSizer(self.mainSizer)
		bodyText = systemMessage['TX']
		self.rtc = rt.RichTextCtrl(self.bottomPanel, style=wx.VSCROLL|wx.HSCROLL|wx.NO_BORDER);
		self.rtc.SetScale(self.fontX,self.fontY)
		self.rtc.SetValue(bodyText)
		self.rtc.SetEditable(False)
		self.mainSizer.Add(self.rtc,1,wx.EXPAND,0)
		initialSashPosition = self.addressGrid.AdjustSash(getInitial = True)
		self.horizontalSplitter.SplitHorizontally(self.addressGrid,self.bottomPanel,initialSashPosition)
		
	def OnReplyClick(self,event):
		title = "Reply"
		frame = message_edit_window.MessageEditFrame(self.parent,self.parent.gui,title,reply_forward_id = self.messageId,reply_forward_type = 'R')
		frame.Show()
		if self.gui.closeOnReply == True:
			wx.CallAfter(self.Close)

	def OnReplyAllClick(self,event):
		title = "Reply"
		frame = message_edit_window.MessageEditFrame(self.parent,self.parent.gui,title,reply_forward_id = self.messageId,reply_forward_type = 'RA')
		frame.Show()
		if self.gui.closeOnReply == True:
			wx.CallAfter(self.Close)

	def OnForwardClick(self,event):
		title = "Forward"
		frame = message_edit_window.MessageEditFrame(self.parent,self.parent.gui,title,reply_forward_id = self.messageId,reply_forward_type = 'F')
		frame.Show()
		if self.gui.closeOnReply == True:
			wx.CallAfter(self.Close)

	def OnForwardAllClick(self,event):
		title = "Forward"
		frame = message_edit_window.MessageEditFrame(self.parent,self.parent.gui,title,reply_forward_id = self.messageId,reply_forward_type = 'FA')
		frame.Show()
		if self.gui.closeOnReply == True:
			wx.CallAfter(self.Close)

	def OnShowOriginalClick(self,event):
		have_good_message = False

		hasher = hashlib.new('sha1')
		hasher.update(self.forwardedMessageId.decode("hex"))
		hasher.update(self.messageId.decode("hex"))
		hasher.update(self.gui.client_keyid)
		local_fwd_id = hasher.digest()
		local_fwd_id_hex = local_fwd_id.encode("hex")
		fwd_sig_path = self.gui.local_store.getPath(local_fwd_id_hex) + '.SIG'
		if os.path.exists(fwd_sig_path) == True:
			fh = open(fwd_sig_path,'r')
			sig_data = fh.read()
			fh.close()
			for line in sig_data.split('\n'):
				line = line.rstrip('\r\n')
				if line == 'Valid: True':
					have_good_message = True
					break

		if have_good_message == True: # only if message exists with good signature
			self.parent.messageList.OpenMessageById(local_fwd_id)
		else:
			self.toolbar.EnableTool(id_show_original,False)
			self.reenableShowOriginalTimer.Start(5000,wx.TIMER_ONE_SHOT)
			self.zipFile.close()
			self.zipFile = None # Zip is opened exclusive, have to close it for client agent
			self.gui.to_agent_queue.put( [ 'PREP_FWD_MSG',self.messageId,True,False ] )

	def OnReenableShowOriginalTimer(self,event):
			self.toolbar.EnableTool(id_show_original,True)

	def OnSmallerClick(self,event):
		if self.htmlWindow != None:
			if self.fontSize > 1:
				self.fontSize -= 1
			self.htmlWindow.SetStandardFonts(self.fontSize)
		else:
			#DBGOUT#fontSize = self.rtc.GetFontScale()
			#DBGOUT#print "old size x=",self.fontX," y=",self.fontY
			self.fontX = self.fontX * 0.9
			self.fontY = self.fontY * 0.9
			self.rtc.SetScale(self.fontX,self.fontY)
			#DBGOUT#print "new size x=",self.fontX," y=",self.fontY
	
	def OnLargerClick(self,event):
		if self.htmlWindow != None:
			self.fontSize += 1
			self.htmlWindow.SetStandardFonts(self.fontSize)
		else:
			#DBGOUT#print "old size x=",self.fontX," y=",self.fontY
			self.fontX = self.fontX * 1.1
			self.fontY = self.fontY * 1.1
			self.rtc.SetScale(self.fontX,self.fontY)
			#DBGOUT#print "new size x=",self.fontX," y=",self.fontY

	def OnFindClick(self,event):
		if self.htmlWindow != None:
			wx.MessageBox("Find is not currently supported on HTML messages.","Unsupported operation",style = wx.ICON_EXCLAMATION)
			return
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

	def __del__(self):
		if self.zipFile != None:
			self.zipFile.close()
			self.zipFile = None
			#DBGOUT#print "zip file closed"

	def OnArchiveClick(self,event):
		if self.fromFolder == folders.id_inbox or self.fromFolder == folders.id_new_messages:
			fromFolders = [ folders.id_inbox,folders.id_new_messages ]
		else:
			fromFolders = [ self.fromFolder ]
		messageIdBin = self.messageId.decode("hex")
		self.parent.MoveMessagesToArchive( [ messageIdBin ],fromFolders)
		self.OnCancelClick(event)

	def OnDeleteClick(self,event):
		if self.fromFolder == folders.id_inbox or self.fromFolder == folders.id_new_messages:
			fromFolders = [ folders.id_inbox,folders.id_new_messages ]
		else:
			fromFolders = [ self.fromFolder ]
		self.parent.DeleteMessageFromFolder(self.messageId,fromFolders)
		self.OnCancelClick(event)

	def OnCancelClick(self,event):
		if self.zipFile != None:
			self.zipFile.close()
			self.zipFile = None
		self.Close()

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

		if self.htmlWindow != None:
			body_html = self.bodyHtml
		else:
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
		if os.path.exists(outPath):
			message = "File exists:\n" + outPath + "\nDo you want to replace it?"	
			dlg = wx.MessageDialog(self,message,"Confirm overwrite",wx.YES_NO|wx.CENTRE|wx.ICON_EXCLAMATION)
			if dlg.ShowModal() != wx.ID_YES:
				dlg.Destroy()
				return
			else:
				dlg.Destroy()
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
