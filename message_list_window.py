import logging
import re
import os
import sys
import wx
import wx.lib.mixins.listctrl as listmix
import wx.html
import images
import images2
import datetime
import time
import hashlib
import struct
import pickle
import zipfile
import codecs
import multiprocessing
import global_config
import filestore
import flatstore
import global_config
import gnupg
import folders
import changepass
import message_view_window
import message_edit_window
import dequeue_dialog
import search_dialog
import rotate_key_dialog
import random

id_new_button = 1
id_open_button = 2
id_open_txt_button = 3
id_reply_button = 4
id_reply_all_button = 5
id_forward_button = 6
id_forward_all_button = 7
id_archive_button = 8
id_delete_button = 9
id_check_send_button = 10
id_post_key_button = 11
id_post_key_timer = 12
id_check_agent_timer = 13
id_check_new_messages_timer = 14
id_process_new_messages_timer = 15
id_check_send_ack_timer = 16
id_popup_show_cat = 17
id_popup_cut = 18
id_popup_copy = 19
id_popup_paste = 20
id_popup_archive = 21
id_popup_delete = 22
id_popup_open = 23
id_popup_open_txt = 24
id_popup_open_rt = 25
id_popup_reply = 26
id_popup_reply_all = 27
id_popup_fwd_txt = 28
id_popup_fwd_all = 29
id_popup_mark_read = 30
id_popup_mark_unread = 31
id_popup_set_template = 32
id_popup_unset_template = 33
id_popup_delete_refetch = 34
id_popup_color_black = 35
id_popup_color_blue = 36
id_popup_color_cyan = 37
id_popup_color_green = 38
id_popup_color_yellow = 39
id_popup_color_light_grey = 40
id_popup_color_red = 41
id_new_category = 42
id_delete_category = 43
id_rename_category = 44
id_clear_status_timer = 45
id_file_exit = 101
id_edit_cut = 201
id_edit_copy = 202
id_edit_paste = 203
id_edit_select_all = 204
id_edit_select_none = 205
id_edit_select_keyword = 206
id_edit_deselect_keyword = 207
id_edit_drag_copies = 208
id_edit_drag_moves = 209
id_actions_full_get = 301
id_actions_copy_my_addr = 302
id_actions_new_version_check = 303
id_actions_view_certs = 304
id_actions_change_passphrase = 305
id_actions_dequeue_bad_messages = 306
id_actions_sync_folders = 307
id_actions_rotate_key = 308
id_actions_throttle_out = 309
id_help_help = 401
id_help_about = 402

re_ack = re.compile("Ack-([0123456789abcdef]{40}): ([0123456789abcdef]{40})$",re.IGNORECASE)
re_strip_last_category = re.compile("^(.*)\x00[^\x00]+$")
re_folder_sync_message = re.compile("^_FOLDER_SYNC_MESSAGE_([0123456789abcdef]{40})$",re.IGNORECASE)

class MessageListCtrl(wx.ListCtrl, listmix.ListCtrlAutoWidthMixin, listmix.ColumnSorterMixin):
	def __init__(self,parent,list_frame):
		self.list_frame = list_frame
		self.gui = self.list_frame.gui
		self.dateformat = global_config.date_format()
		self.regularFontObj = None
		self.boldFontObj = None
		self.listFields = [ ]
		i = 0
		for f in self.gui.fieldOrder.split(' '):
			if f == 'From':
				self.listFields.append( ( 'From','FR' ) )
			elif f == 'To':
				self.listFields.append( ( 'To','RE' ) )
			elif f == 'Subject':
				self.listFields.append( ( 'Subject','SU' ) )
			elif f == 'Date':
				self.listFields.append( ( 'Date','DA' ) )
				self.defaultSortIndex = i
			i += 1
		self.defaultSortDir = 0
		self.lastSortState = self.defaultSortIndex,self.defaultSortDir
		self.il = wx.ImageList(16, 16)
		self.sm_up = self.il.Add(images.SmallUpArrow.GetBitmap())
		self.sm_dn = self.il.Add(images.SmallDnArrow.GetBitmap())
		self.arrow_rf = self.il.Add(images2.arrow_rf.GetBitmap())
		self.arrow_r = self.il.Add(images2.arrow_r.GetBitmap())
		self.arrow_f = self.il.Add(images2.arrow_f.GetBitmap())
		self.template = self.il.Add(images2.template.GetBitmap())
		wx.ListCtrl.__init__(self,parent,style = wx.LC_REPORT|wx.LC_HRULES|wx.LC_VRULES)
       
		self.SetImageList(self.il, wx.IMAGE_LIST_SMALL)
		listmix.ListCtrlAutoWidthMixin.__init__(self)
		listmix.ColumnSorterMixin.__init__(self, len(self.listFields))
		self.rowMessageIds = [ ]
		self.numRows = 0
		n = 0
		for fld in self.listFields:
			title,hfld = fld
			self.InsertColumn(n,title)
			n += 1
		self.InsertColumn(n,"") # blank one
		self.Bind(wx.EVT_LIST_ITEM_ACTIVATED,self.OnActivateRow)
		self.Bind(wx.EVT_LIST_BEGIN_DRAG,self.OnBeginDrag)
		self.Bind(wx.EVT_LIST_ITEM_RIGHT_CLICK,self.OnRightClick)
		self.Bind(wx.EVT_KEY_DOWN,self.list_frame.OnKeyDown)
		if self.gui.saveFieldSizes != 'Off':
			self.Bind(wx.EVT_LIST_COL_END_DRAG,self.OnResizeCol)

	# Used by the ColumnSorterMixin, see wx/lib/mixins/listctrl.py
	def GetSortImages(self):
		return (self.sm_dn, self.sm_up)

    # Used by the ColumnSorterMixin, see wx/lib/mixins/listctrl.py
	def GetListCtrl(self):
		return self

	def InsertRecord(self,header):
		itemDataLine = [ ]
		c = 0
		for fld in self.listFields:
			title,hfld = fld
			if hfld not in header:
				val = ''
			else:
				val = header[hfld]
			if hfld == 'FR':
				hash,name = val
				vo = name
				if vo == None:
					vo = ''
				itemDataLine.append(vo.lower().encode('utf-8'))	
			elif hfld == 'DA':
				vo = self.dateformat.localize_datetime(val)
				if vo == None:
					vo = ''
				itemDataLine.append(val)	
			elif hfld == 'SU':
				vo = val
				if vo == None:
					vo = ''
				itemDataLine.append(vo.lower().encode('utf-8'))	
			elif hfld == 'RE':
				vo = ''
				first = True
				for rec in val:
					if first == True:
						first = False
					else:
						vo += ','
					typ,hash,name = rec
					vo = name
				itemDataLine.append(vo.lower().encode('utf-8'))	
			
			if c == 0:
				if 'RPL' in header and 'FWD' in header:
					listIndex = self.InsertImageStringItem(c,vo,self.arrow_rf)
				elif 'RPL' in header:
					listIndex = self.InsertImageStringItem(c,vo,self.arrow_r)
				elif 'FWD' in header:
					listIndex = self.InsertImageStringItem(c,vo,self.arrow_f)
				elif header['ID'] == self.list_frame.template_message:
					listIndex = self.InsertImageStringItem(c,vo,self.template)
				else:
					listIndex = self.InsertStringItem(c,vo)
				self.SetItemData(listIndex,self.numRows)
			else:
				self.SetStringItem(listIndex,c,vo)
			c += 1
		if 'NEW' in header:
			if self.regularFontObj == None:
				self.regularFontObj = self.GetFont()
				self.boldFontObj = self.GetFont().Bold()
			self.SetItemFont(listIndex,self.boldFontObj)
		if 'CLR' in header:
			item = self.GetItem(listIndex)
			item.SetTextColour(header['CLR'])
			self.SetItem(item)
		self.itemDataMap[self.numRows] = itemDataLine
		self.rowMessageIds.append(header['ID'])
		self.numRows += 1

	def ChangeMessageImage(self,messageid,replied,forwarded):
		i = 0
		found,header = self.list_frame.folder_store.get_message(messageid)
		if found == False:
			return
		if replied == True:
			header['RPL'] = True
		if forwarded == True:
			header['FWD'] = True
		self.list_frame.folder_store.save_message(messageid,header)
		for id in self.rowMessageIds:
			if id == messageid:
				itemIndex = self.FindItemData(-1,i)
				if 'RPL' in header and 'FWD' in header:
					self.SetItemImage(itemIndex,self.arrow_rf,self.arrow_rf)
				elif 'FWD' in header:
					self.SetItemImage(itemIndex,self.arrow_f,self.arrow_f)
				elif 'RPL' in header:
					self.SetItemImage(itemIndex,self.arrow_r,self.arrow_r)
				break
			i += 1

	def LoadFolder(self,folder):
		self.rowMessageIds = [ ]
		if self.numRows > 0:
			self.DeleteAllItems()
		self.itemDataMap = dict()
		self.numRows = 0
		for header in folder:
			self.InsertRecord(header)
		widths = self.GetColSizes()
		if widths != None: 
			for i in range(len(self.listFields)):
				self.SetColumnWidth(i,widths[i])
		elif len(folder) == 0:
			for i in range(len(self.listFields)):
				self.SetColumnWidth(i,100)
		else:
			for i in range(len(self.listFields)):
				self.SetColumnWidth(i, wx.LIST_AUTOSIZE)

		sortIndex,sortDir = self.GetSortState()
		if sortIndex < 0:
			sortIndex = self.defaultSortIndex
			sortDir = self.defaultSortDir
		self.SortListItems(sortIndex,sortDir)

	def SaveColSizePrefix(self,fallback = False):
		if self.gui.saveFieldSizes == 'Global':
			return 'COLSIZE_ALL'
		elif self.gui.saveFieldSizes == 'Incoming/Outgoing':
			pathsplit = self.list_frame.current_folder_path.split('\x00',1)
			toplevel = pathsplit[0]
			if toplevel == folders.id_sent_messages or toplevel == folders.id_send_pending or \
			   toplevel == folders.id_ack_pending or toplevel == folders.id_drafts:
				return 'COLSIZE_OUT'
			else:
				return 'COLSIZE_IN'
		elif self.gui.saveFieldSizes == 'Per Category':
			if fallback == True:
				pathsplit = self.list_frame.current_folder_path.split('\x00',1)
				toplevel = pathsplit[0].encode('utf-8')
				return 'COLSIZE_' + toplevel
			else:
				return 'COLSIZE_' + (self.list_frame.current_folder_path.replace('\x00','/').encode('utf-8'))

	def GetColSizes(self):
		if self.gui.saveFieldSizes != 'Off':
			found,widths = self.list_frame.folder_store.get_global(self.SaveColSizePrefix())
			if found:
				return pickle.loads(widths)
			elif self.gui.saveFieldSizes == 'Per Category':
				found,widths = self.list_frame.folder_store.get_global(self.SaveColSizePrefix(True))
				if found:
					return pickle.loads(widths)
		return None

	def OnResizeCol(self,event):
		widths = [ ]
		for i in range(len(self.listFields)):
			widths.append(self.GetColumnWidth(i))	
		self.list_frame.folder_store.set_global(self.SaveColSizePrefix(),pickle.dumps(widths,pickle.HIGHEST_PROTOCOL))

	def OnActivateRow(self,event):
		row = event.GetData()
		itemIndex = self.FindItemData(-1,row)
		messageId = self.rowMessageIds[row]
		self.OpenMessageById(messageId,deBold = itemIndex)
		#DBGOUT#print "activate",row,messageId.encode('hex')

	def OpenMessageById(self,messageId,reopen = False,pos = None,size = None,textOnly = False,deBold = None,forceRich = False):
		#DBGOUT#print "OpenMessageById",messageId.encode('hex'),reopen,textOnly
		found,headers = self.list_frame.folder_store.get_message(messageId)
		if found == True and headers['TY'] == 'O':
			title = 'Unknown message'
			try:
				if reopen == True:
					title = 'Resend message: ' + headers['SU']
				elif headers['ST'] == 'D':
					title = 'Draft message: ' + headers['SU']
				elif headers['ST'] == 'S':
					title = 'Sent message: ' + headers['SU']
			except KeyError:
				pass
			if pos != None and size != None:
				frame = message_edit_window.MessageEditFrame(self.list_frame,self.gui,title,draft_sent_hash = \
					messageId.encode('hex'),ds_from_folder = self.list_frame.current_folder_path, pos = pos,size = size)
			else:
				frame = message_edit_window.MessageEditFrame(self.list_frame,self.gui,title,draft_sent_hash = \
					messageId.encode('hex'),ds_from_folder = self.list_frame.current_folder_path)
			frame.Show()
			self.list_frame.newMessageFrames.append(frame)
		elif found == True and headers['TY'] == 'I':
			folders_containing = self.list_frame.folder_store.get_folders_containing_message(messageId)
			if folders.id_new_messages in folders_containing:
				if len(folders_containing) == 1:
					self.list_frame.folder_store.put_message_in_folder(folders.id_inbox,messageId) # don't lose message
				self.list_frame.folder_store.delete_message_from_folder(folders.id_new_messages,messageId)
				self.list_frame.folder_store.commit()
				self.list_frame.ClearNewMessageNotification()
			frame = message_view_window.MessageViewFrame(self.list_frame,messageId.encode('hex'),self.list_frame.current_folder_path,textOnly = textOnly,forceRich = forceRich)
			frame.Show()
			self.list_frame.newMessageFrames.append(frame)
		elif found == True and headers['TY'] == 'S':
			frame = message_view_window.MessageViewFrame(self.list_frame,messageId.encode('hex'),self.list_frame.current_folder_path,headers)
			frame.Show()
			self.list_frame.newMessageFrames.append(frame)
		if deBold != None and self.regularFontObj != None:
			self.SetItemFont(deBold,self.regularFontObj)
	
	def OnBeginDrag(self,event):
		#DBGOUT#print "got begin drag"
		selectedList = [ ]
		selectedList.append(self.list_frame.current_folder_path)
		selected = -1
		while True:
			selected = self.GetNextItem(selected,state = wx.LIST_STATE_SELECTED)
			if selected < 0:
				break
			selectedList.append(self.rowMessageIds[self.GetItemData(selected)])
		listContainer = wx.CustomDataObject('message list ' + self.list_frame.from_address)
		listContainer.SetData(pickle.dumps(selectedList,pickle.HIGHEST_PROTOCOL))
		dropSource = wx.DropSource(self)
		dropSource.SetData(listContainer)
		res = dropSource.DoDragDrop(flags=wx.Drag_AllowMove)

	def OnRightClick(self,event):
		row = event.GetData()
		self.rclickMessageId = self.rowMessageIds[row]
		self.rclickPosition = event.GetPosition()
		found,headers = self.list_frame.folder_store.get_message(self.rclickMessageId)
		self.rclickHeaders = headers
		if found == True and headers['TY'] == 'O':
			self.DisplayOutgoingMessageMenu()
		elif found == True and headers['TY'] == 'I':
			self.DisplayIncomingMessageMenu()
		elif found == True and headers['TY'] == 'S':
			self.DisplaySystemMessageMenu()

	def DisplayOutgoingMessageMenu(self):
		outgoingMessageMenu = wx.Menu()
		outgoingMessageMenu.Append(id_popup_show_cat,"Show All Categories")	
		self.Bind(wx.EVT_MENU,self.ShowAllCategories,id = id_popup_show_cat)
		outgoingMessageMenu.Append(id_popup_cut,"Cut")
		self.Bind(wx.EVT_MENU,self.list_frame.OnEditCut,id = id_popup_cut)
		outgoingMessageMenu.Append(id_popup_copy,"Copy")
		self.Bind(wx.EVT_MENU,self.list_frame.OnEditCopy,id = id_popup_copy)
		outgoingMessageMenu.Append(id_popup_paste,"Paste")
		self.Bind(wx.EVT_MENU,self.list_frame.OnEditPaste,id = id_popup_paste)
		if self.list_frame.current_folder_path != folders.id_archive:
			outgoingMessageMenu.Append(id_popup_archive,"Archive")
			self.Bind(wx.EVT_MENU,self.list_frame.OnArchiveClick,id = id_popup_archive)
		outgoingMessageMenu.Append(id_popup_delete,"Delete")
		self.Bind(wx.EVT_MENU,self.list_frame.OnDeleteClick,id = id_popup_delete)
		outgoingMessageMenu.Append(id_popup_open,"Open")
		self.Bind(wx.EVT_MENU,self.list_frame.OnOpenClick,id = id_popup_open)
		if self.rclickMessageId == self.list_frame.template_message:
			outgoingMessageMenu.Append(id_popup_unset_template,"Disable Template")
			self.Bind(wx.EVT_MENU,self.list_frame.OnUnsetTemplateClick,id = id_popup_unset_template)
		elif self.list_frame.current_folder_path == folders.id_drafts:
			outgoingMessageMenu.Append(id_popup_set_template,"Set as Template")
			self.Bind(wx.EVT_MENU,self.list_frame.OnSetTemplateClick,id = id_popup_set_template)
		outgoingMessageMenu.AppendSeparator()
		outgoingMessageMenu.Append(id_popup_color_black,"Black")
		self.Bind(wx.EVT_MENU,self.OnSetColorBlack,id = id_popup_color_black)
		outgoingMessageMenu.Append(id_popup_color_red,"Red")
		self.Bind(wx.EVT_MENU,self.OnSetColorRed,id = id_popup_color_red)
		outgoingMessageMenu.Append(id_popup_color_green,"Green")
		self.Bind(wx.EVT_MENU,self.OnSetColorGreen,id = id_popup_color_green)
		outgoingMessageMenu.Append(id_popup_color_blue,"Blue")
		self.Bind(wx.EVT_MENU,self.OnSetColorBlue,id = id_popup_color_blue)
		outgoingMessageMenu.Append(id_popup_color_cyan,"Cyan")
		self.Bind(wx.EVT_MENU,self.OnSetColorCyan,id = id_popup_color_cyan)
		outgoingMessageMenu.Append(id_popup_color_yellow,"Yellow")
		self.Bind(wx.EVT_MENU,self.OnSetColorYellow,id = id_popup_color_yellow)
		outgoingMessageMenu.Append(id_popup_color_light_grey,"Light Grey")
		self.Bind(wx.EVT_MENU,self.OnSetColorLightGrey,id = id_popup_color_light_grey)

		self.PopupMenu(outgoingMessageMenu)
		outgoingMessageMenu.Destroy()
	
	def DisplayIncomingMessageMenu(self):
		incomingMessageMenu = wx.Menu()
		incomingMessageMenu.Append(id_popup_show_cat,"Show All Categories")	
		self.Bind(wx.EVT_MENU,self.ShowAllCategories,id = id_popup_show_cat)
		incomingMessageMenu.Append(id_popup_cut,"Cut")
		self.Bind(wx.EVT_MENU,self.list_frame.OnEditCut,id = id_popup_cut)
		incomingMessageMenu.Append(id_popup_copy,"Copy")
		self.Bind(wx.EVT_MENU,self.list_frame.OnEditCopy,id = id_popup_copy)
		incomingMessageMenu.Append(id_popup_paste,"Paste")
		self.Bind(wx.EVT_MENU,self.list_frame.OnEditPaste,id = id_popup_paste)
		if self.list_frame.current_folder_path != folders.id_archive:
			incomingMessageMenu.Append(id_popup_archive,"Archive")
			self.Bind(wx.EVT_MENU,self.list_frame.OnArchiveClick,id = id_popup_archive)
		incomingMessageMenu.Append(id_popup_delete,"Delete")
		self.Bind(wx.EVT_MENU,self.list_frame.OnDeleteClick,id = id_popup_delete)
		if self.list_frame.current_folder_path == folders.id_deleted:
			incomingMessageMenu.Append(id_popup_delete_refetch,"Delete and allow refetch")	
			self.Bind(wx.EVT_MENU,self.DeleteRefetch,id = id_popup_delete_refetch)
		incomingMessageMenu.AppendSeparator()
		incomingMessageMenu.Append(id_popup_open,"Open")
		self.Bind(wx.EVT_MENU,self.list_frame.OnOpenClick,id = id_popup_open)
		incomingMessageMenu.Append(id_popup_open_txt,"Open Text")
		self.Bind(wx.EVT_MENU,self.list_frame.OnOpenTxtClick,id = id_popup_open_txt)
		incomingMessageMenu.Append(id_popup_open_rt,"Open Rich Text")
		self.Bind(wx.EVT_MENU,self.list_frame.OnOpenRTClick,id = id_popup_open_rt)
		incomingMessageMenu.Append(id_popup_reply,"Reply")
		self.Bind(wx.EVT_MENU,self.list_frame.OnReplyClick,id = id_popup_reply)
		incomingMessageMenu.Append(id_popup_reply_all,"Reply All")
		self.Bind(wx.EVT_MENU,self.list_frame.OnReplyAllClick,id = id_popup_reply_all)
		incomingMessageMenu.Append(id_popup_fwd_txt,"Forward Text")
		self.Bind(wx.EVT_MENU,self.list_frame.OnForwardClick,id = id_popup_fwd_txt)
		incomingMessageMenu.Append(id_popup_fwd_all,"Forward All")
		self.Bind(wx.EVT_MENU,self.list_frame.OnForwardAllClick,id = id_popup_fwd_all)
		incomingMessageMenu.Append(id_popup_mark_read,"Mark as Read")
		self.Bind(wx.EVT_MENU,self.list_frame.OnMarkRead,id = id_popup_mark_read)
		incomingMessageMenu.Append(id_popup_mark_unread,"Mark as Unread")
		self.Bind(wx.EVT_MENU,self.list_frame.OnMarkUnread,id = id_popup_mark_unread)
		incomingMessageMenu.AppendSeparator()
		incomingMessageMenu.Append(id_popup_color_black,"Black")
		self.Bind(wx.EVT_MENU,self.OnSetColorBlack,id = id_popup_color_black)
		incomingMessageMenu.Append(id_popup_color_red,"Red")
		self.Bind(wx.EVT_MENU,self.OnSetColorRed,id = id_popup_color_red)
		incomingMessageMenu.Append(id_popup_color_green,"Green")
		self.Bind(wx.EVT_MENU,self.OnSetColorGreen,id = id_popup_color_green)
		incomingMessageMenu.Append(id_popup_color_blue,"Blue")
		self.Bind(wx.EVT_MENU,self.OnSetColorBlue,id = id_popup_color_blue)
		incomingMessageMenu.Append(id_popup_color_cyan,"Cyan")
		self.Bind(wx.EVT_MENU,self.OnSetColorCyan,id = id_popup_color_cyan)
		incomingMessageMenu.Append(id_popup_color_yellow,"Yellow")
		self.Bind(wx.EVT_MENU,self.OnSetColorYellow,id = id_popup_color_yellow)
		incomingMessageMenu.Append(id_popup_color_light_grey,"Light Grey")
		self.Bind(wx.EVT_MENU,self.OnSetColorLightGrey,id = id_popup_color_light_grey)

		self.PopupMenu(incomingMessageMenu)
		incomingMessageMenu.Destroy()

	def DisplaySystemMessageMenu(self):
		systemMessageMenu = wx.Menu()
		systemMessageMenu.Append(id_popup_show_cat,"Show All Categories")	
		self.Bind(wx.EVT_MENU,self.ShowAllCategories,id = id_popup_show_cat)
		systemMessageMenu.Append(id_popup_cut,"Cut")
		self.Bind(wx.EVT_MENU,self.list_frame.OnEditCut,id = id_popup_cut)
		systemMessageMenu.Append(id_popup_copy,"Copy")
		self.Bind(wx.EVT_MENU,self.list_frame.OnEditCopy,id = id_popup_copy)
		systemMessageMenu.Append(id_popup_paste,"Paste")
		self.Bind(wx.EVT_MENU,self.list_frame.OnEditPaste,id = id_popup_paste)
		systemMessageMenu.Append(id_popup_delete,"Delete")
		self.Bind(wx.EVT_MENU,self.list_frame.OnDeleteClick,id = id_popup_delete)
		systemMessageMenu.Append(id_popup_open,"Open")
		self.Bind(wx.EVT_MENU,self.list_frame.OnOpenClick,id = id_popup_open)
		systemMessageMenu.AppendSeparator()
		systemMessageMenu.Append(id_popup_color_black,"Black")
		self.Bind(wx.EVT_MENU,self.OnSetColorBlack,id = id_popup_color_black)
		systemMessageMenu.Append(id_popup_color_red,"Red")
		self.Bind(wx.EVT_MENU,self.OnSetColorRed,id = id_popup_color_red)
		systemMessageMenu.Append(id_popup_color_green,"Green")
		self.Bind(wx.EVT_MENU,self.OnSetColorGreen,id = id_popup_color_green)
		systemMessageMenu.Append(id_popup_color_blue,"Blue")
		self.Bind(wx.EVT_MENU,self.OnSetColorBlue,id = id_popup_color_blue)
		systemMessageMenu.Append(id_popup_color_cyan,"Cyan")
		self.Bind(wx.EVT_MENU,self.OnSetColorCyan,id = id_popup_color_cyan)
		systemMessageMenu.Append(id_popup_color_yellow,"Yellow")
		self.Bind(wx.EVT_MENU,self.OnSetColorYellow,id = id_popup_color_yellow)
		systemMessageMenu.Append(id_popup_color_light_grey,"Light Grey")
		self.Bind(wx.EVT_MENU,self.OnSetColorLightGrey,id = id_popup_color_light_grey)

		self.PopupMenu(systemMessageMenu)
		systemMessageMenu.Destroy()

	def ShowAllCategories(self,event):
		#DBGOUT#print "show all categories"
		folders = self.list_frame.folder_store.get_folders_containing_message(self.rclickMessageId)
		folders.sort()
		folderListText = 'Message ID: ' + self.rclickMessageId.encode('hex') + '\n\n'
		if self.rclickHeaders['TY'] == 'I':
			folderListText += 'Incoming message in folders:\n'
		elif self.rclickHeaders['TY'] == 'O':
			folderListText += 'Outgoing message in folders:\n'
		elif self.rclickHeaders['TY'] == 'S':
			folderListText += 'System message in folders:\n'
		n = len(folders)
		i = 0	
		for folder in folders:
			folder = folder.replace('\x00','/')
			i += 1
			if i < n:
				folderListText += folder + '\n'
			else:
				folderListText += folder

		popupWin = wx.PopupTransientWindow(self, style = wx.SIMPLE_BORDER)
		panel = wx.Panel(popupWin)
		st = wx.StaticText(panel, -1, folderListText)
		sizer = wx.BoxSizer(wx.VERTICAL)
		sizer.Add(st, 0, wx.ALL, 5)
		panel.SetSizer(sizer)
		sizer.Fit(panel)
		sizer.Fit(popupWin)
		pos = self.ClientToScreen(self.rclickPosition)
		popupWin.Position(pos,wx.DefaultSize)
		popupWin.Layout()
		popupWin.Popup()

	def DeleteRefetch(self,event):
		self.list_frame.OnDeleteClick(event,True)

	def OnSetColorBlack(self,event):
		self.list_frame.OnSetColorCommon(event,wx.BLACK)

	def OnSetColorBlue(self,event):
		self.list_frame.OnSetColorCommon(event,wx.BLUE)

	def OnSetColorCyan(self,event):
		self.list_frame.OnSetColorCommon(event,wx.Colour(0,0x80,0x80))

	def OnSetColorGreen(self,event):
		self.list_frame.OnSetColorCommon(event,wx.GREEN)

	def OnSetColorYellow(self,event):
		self.list_frame.OnSetColorCommon(event,wx.Colour(0x80,0x80,0))

	def OnSetColorLightGrey(self,event):
		self.list_frame.OnSetColorCommon(event,wx.Colour(0x80,0x80,0x80))

	def OnSetColorRed(self,event):
		self.list_frame.OnSetColorCommon(event,wx.RED)


class MessageListDropTarget(wx.DropTarget):
	def __init__(self,tree):
		wx.DropTarget.__init__(self)
		self.tree = tree
		self.list_frame = self.tree.list_frame
		self.composite = wx.DataObjectComposite()
		self.listContainer = wx.CustomDataObject('message list ' + self.list_frame.from_address)
		self.composite.Add(self.listContainer)
		self.SetDataObject(self.composite)
		
	def OnDrop(self,x,y):
		return True

	def GetReceivedFormatAndId(self):
		format = self.composite.GetReceivedFormat()
		formatType = format.GetType()
		try:
			formatId = format.GetId() # May throw exception on unknown formats
		except:
			formatId = None
		return formatType, formatId

	def OnData(self,x,y,result):
		self.GetData()
		formatType,formatId = self.GetReceivedFormatAndId()
		if formatId != 'message list ' + self.list_frame.from_address:
			return None
		messageList = pickle.loads(self.listContainer.GetData())
		fromFolder = messageList.pop(0)
		item_id,flags = self.tree.HitTest(wx.Point(x,y))
		if item_id != None:
			item = self.tree.GetItemData(item_id)
			if item != None:
				toFolder = item.GetData()
				#DBGOUT#print "got drop onto",x,y,item,flags,toFolder
				self.list_frame.DragCopyMove(messageList,toFolder,fromFolder)
				return wx.DragCopy
	

class FolderTree(wx.TreeCtrl):
	def __init__(self,parent,list_frame):
		self.list_frame = list_frame
		wx.TreeCtrl.__init__(self,parent,-1,wx.DefaultPosition,wx.DefaultSize)
		dropTarget = MessageListDropTarget(self)
		self.SetDropTarget(dropTarget)
		self.Bind(wx.EVT_TREE_SEL_CHANGED, self.OnSelChanged, self)
		self.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self.OnActivate, self)
		self.Bind(wx.EVT_TREE_ITEM_MENU, self.OnTreeItemMenu, self)
		self.LoadTree(False)

	def LoadTree(self,deleteAll = True):
		if deleteAll == True:
			self.DeleteAllItems()
		self.folders_by_path = dict()
		folder_list = self.list_frame.folder_store.get_folder_list()
		folder_list.sort()
		self.root = self.AddRoot("Mail categories")
		for folder in folder_list:
			folder_split = folder.rsplit('\x00',1)
			if len(folder_split) == 1:
				folder_obj = self.AppendItem(self.root,folder,data = wx.TreeItemData(folder)) # data will be path
			else:
				parent_obj = self.folders_by_path[folder_split[0]]
				folder_obj = self.AppendItem(parent_obj,folder_split[1],data = wx.TreeItemData(folder))
			self.folders_by_path[folder] = folder_obj
		self.Expand(self.root)

	def OnActivate(self,event):
		pass
		#DBGOUT#print "activate",event
		
	def OnSelChanged(self,event):
		item = event.GetItem()
		item_data = self.GetItemData(item)
		if item_data != None:
			folder_path = item_data.GetData()
			if folder_path in self.folders_by_path:
				#DBGOUT#print "select",item,folder_path
				self.list_frame.OpenMailFolder(folder_path)

	def OnTreeItemMenu(self,event):
		self.treeMenuItem = event.GetItem()
		predefined_folder = False
		if self.treeMenuItem == self.root:
			predefined_folder = True
		else:
			folder_path = self.GetItemData(self.treeMenuItem).GetData()
			if folder_path in folders.predefined_folders:
				predefined_folder = True
		treeMenu = wx.Menu()
		treeMenu.Append(id_new_category,"New Category")
		self.Bind(wx.EVT_MENU,self.OnNewCategory,id = id_new_category)
		if predefined_folder == False:
			treeMenu.Append(id_delete_category,"Delete Category")
			self.Bind(wx.EVT_MENU,self.OnDeleteCategory,id = id_delete_category)
			treeMenu.Append(id_rename_category,"Rename Category")
			self.Bind(wx.EVT_MENU,self.OnRenameCategory,id = id_rename_category)
		self.PopupMenu(treeMenu)
		treeMenu.Destroy()
		
	def OnNewCategory(self,event):
		if self.treeMenuItem == self.root:
			message = "New Top-Level Category"
		else:
			folder_path = self.GetItemData(self.treeMenuItem).GetData()
			message = "New Category Under " + folder_path.replace('\x00','/')
		dlg = wx.TextEntryDialog(self,message,'Create New Category','')
		if dlg.ShowModal() != wx.ID_OK:
			dlg.Destroy()
			return
		new_cat = dlg.GetValue()
		if new_cat == '':
			return
		if self.treeMenuItem == self.root:
			new_path = new_cat
		else:
			new_path = folder_path + '\x00' + new_cat
		dlg.Destroy()
		self.list_frame.folder_store.check_add_folder(new_path)
		self.list_frame.folder_store.commit()
		self.LoadTree()

	def OnDeleteCategory(self,event):
		if self.treeMenuItem == self.root:
			return
		folder_path = self.GetItemData(self.treeMenuItem).GetData()
		if folder_path in folders.predefined_folders:
			return
		subfolder_check = folder_path + '\x00'
		subfolder_check_len = len(subfolder_check)
		num_subfolders = 0
		for subfolder in self.folders_by_path:
			if subfolder[0:subfolder_check_len] == subfolder_check:
				num_subfolders += 1
		if num_subfolders > 0:
			if num_subfolders == 1:
				message = "Folder cannot be deleted because it has a subfolder. Delete the subfolder first."
			else:
				message = "Folder cannot be deleted because it has subfolders. Delete the subfolders first."
			dlg = wx.MessageDialog(self,message,caption="Cannot delete folder",style = wx.ICON_ERROR|wx.OK|wx.CENTRE)
			dlg.ShowModal()
			dlg.Destroy()
			return
		folder_contents = self.list_frame.folder_store.get_messages_in_folder(folder_path)
		if len(folder_contents) == 0:
			message = "Delete empty folder " + folder_path.replace('\x00','/') + "?"
		else:
			message = "Delete " + folder_path.replace('\x00','/') + " and move messages to Deleted?"
		dlg = wx.MessageDialog(self,message,"Delete folder?",style = wx.YES_NO|wx.CENTRE|wx.ICON_QUESTION)
		if dlg.ShowModal() != wx.ID_YES:
			dlg.Destroy()
			return
		dlg.Destroy()

		messages_to_delete = self.list_frame.folder_store.get_messages_in_folder(folder_path)
		for message in messages_to_delete:
			folders_containing = self.list_frame.folder_store.get_folders_containing_message(message)
			if folder_path not in folders_containing:
				continue # should not happen
			if len(folders_containing) == 1: # only in this folder
				self.list_frame.folder_store.put_message_in_folder(folders.id_deleted,message)
			self.list_frame.folder_store.delete_message_from_folder(folder_path,message)
		self.list_frame.folder_store.delete_folder(folder_path)
		self.list_frame.folder_store.commit()
		del self.folders_by_path[folder_path]
		self.Delete(self.treeMenuItem)
		
	def OnRenameCategory(self,event):
		if self.treeMenuItem == self.root:
			return
		folder_path = self.GetItemData(self.treeMenuItem).GetData()
		if folder_path in folders.predefined_folders:
			return
		message = "New Name For Category " + folder_path.replace('\x00','/')
		dlg = wx.TextEntryDialog(self,message,'Rename Category','')
		if dlg.ShowModal() != wx.ID_OK:
			dlg.Destroy()
			return
		new_cat = dlg.GetValue()
		if new_cat == '':
			return
		m = re_strip_last_category.match(folder_path)
		if m:
			new_path = m.group(1) + '\x00' + new_cat
		else:
			new_path = new_cat
		dlg.Destroy()
		self.list_frame.folder_store.rename_folder(folder_path,new_path)
		self.list_frame.folder_store.commit()
		folder_obj = self.folders_by_path[folder_path]
		del self.folders_by_path[folder_path]
		self.folders_by_path[new_path] = folder_obj
		self.SetItemText(self.treeMenuItem,new_cat)
		self.SetItemData(self.treeMenuItem,wx.TreeItemData(new_path))

class MessageListFrame(wx.Frame):
	def __init__(self,parent,title,gui):
		self.gui = gui
		self.logger = logging.getLogger(__name__)
		self.title = title
		self.newMessageNotificationActive = False
		wx.Frame.__init__(self,parent,-1,title,size=gui.list_window_size)
		self.current_folder_path = None
		self.openAddressBook = None
		self.statusBar = self.CreateStatusBar(2)
		self.statusBar.SetStatusWidths( [-1,int(global_config.resolution_scale_factor * 200) ] )
		self.newMessageFrames = [ ]
		self.homedir = self.gui.homedir
		self.checkSendAckActive = False
		self.lastCheckSendAck = 0.0
		self.lastCheckSendDate = None
		self.numIncrementalChecks = 0
		self.checkSendButtonEnabled = True
		self.sentToCheck = None
		self.acksToCheck = None
		self.dragMoves = False
		self.pasteCut = False
		self.pasteFromFolder = None
		self.pasteList = None
		self.passphraseEntered = False
		self.keyRotatePending = False
		self.newMessagePending = False
		self.passphrase = None
		self.trayIcon = None
		self.searchDialogOpen = False
		self.rotateKeyDialog = None
		self.htmlPrinting = wx.html.HtmlEasyPrinting(parentWindow = self)
		if self.gui.client_agent_message != None:
			self.Bind(self.gui.EVT_CLIENT_AGENT_MESSAGE,self.OnClientAgentMessage)
		self.client_keyid = self.gui.client_keyid
		self.client_keyid_hex = self.gui.client_keyid_hex.lower()
		self.newMessageNotification = self.gui.newMessageNotification
		self.gpg_homedir = self.homedir + os.sep + 'gpg'
		self.gpg = gnupg.GPG(gpgbinary = global_config.gnupg_path,options = global_config.gpg_opts,verbose = False,gnupghome = self.gpg_homedir)
		self.gpg.encoding = 'utf-8'
		self.gpg_tempdir = self.homedir + os.sep + 'tempkeys'
		self.tempkeys = flatstore.flatstore(self.gpg_tempdir)
		self.temp_gpg = gnupg.GPG(gpgbinary = global_config.gnupg_path,options = global_config.gpg_opts,verbose = False,gnupghome = self.gpg_tempdir)
		self.temp_gpg.encoding = 'utf-8'
		self.key_update_file = self.homedir + os.sep + "key_update_flag"
		if os.path.exists(self.key_update_file):
			self.key_update_required = True
		else:
			self.key_update_required = False
		self.passphrase = None
		self.from_address = self.gui.from_address
		self.from_address_name = self.gui.from_address_name
		self.prepmsgs = self.gui.prepmsgs
		self.complete_store = self.gui.complete_store
		self.local_store = self.gui.local_store
		self.folder_store = self.gui.folder_store
		self.outgoing_sync = self.gui.outgoing_sync
		self.folder_store.get_messages_in_folder(folders.id_send_pending) # preload slack
		self.folder_store.get_messages_in_folder(folders.id_ack_pending) # preload slack
		self.client_agent_good = True
		self.statusBar.SetStatusText("Agent Starting",1)

		self.check_agent_timer = wx.Timer(self,id = id_check_agent_timer)
		self.Bind(wx.EVT_TIMER,self.OnCheckAgentTimer,id = id_check_agent_timer)
		self.check_agent_timer.Start(60000,wx.TIMER_CONTINUOUS)
		self.post_key_timer = wx.Timer(self,id = id_post_key_timer)
		self.Bind(wx.EVT_TIMER,self.OnPostKeyTimer,id = id_post_key_timer)
		self.process_new_messages_timer = wx.Timer(self,id = id_process_new_messages_timer)
		self.Bind(wx.EVT_TIMER,self.ProcessNewMessages,id = id_process_new_messages_timer)
		self.check_send_ack_timer = wx.Timer(self,id = id_check_send_ack_timer)
		self.Bind(wx.EVT_TIMER,self.CheckSendAck,id = id_check_send_ack_timer)
		self.clearStatusTimer = wx.Timer(self,id = id_clear_status_timer)
		self.Bind(wx.EVT_TIMER,self.OnClearStatusTimer,id = id_clear_status_timer)
		self.Bind(wx.EVT_CLOSE,self.OnClose)
		found,self.template_message = self.folder_store.get_global('TEMPLATE')

		self.new_message_check_interval = self.gui.newMessageCheck
		if self.new_message_check_interval > 0:
			self.check_new_messages_timer = wx.Timer(self,id = id_check_new_messages_timer)
			self.Bind(wx.EVT_TIMER,self.OnCheckSendTimer,id = id_check_new_messages_timer)
			self.check_new_messages_timer.Start((1000 * self.new_message_check_interval),wx.TIMER_CONTINUOUS)

		fileMenu = wx.Menu()
		fileMenu.Append(id_file_exit,"&Exit")
		editMenu = wx.Menu()
		editMenu.Append(id_edit_cut,"&Cut","Cut selected messages to the clipboard")
		editMenu.Append(id_edit_copy,"C&opy","Copy selected messages to the clipboard")
		editMenu.Append(id_edit_paste,"&Paste","Move or copy messages to the current category")
		editMenu.AppendSeparator()
		editMenu.Append(id_edit_select_all,"Select &All","Select all messages in the current category")
		editMenu.Append(id_edit_select_none,"Select &None","Clear selection")
		editMenu.Append(id_edit_select_keyword,"Select by &Keyword...","Search and select")
		editMenu.Append(id_edit_deselect_keyword,"&Deselect by Keyword...","Search and deselect")
		editMenu.AppendSeparator()
		editMenu.Append(id_edit_drag_copies,"Drag Co&pies","Set drag and drop to make a copy",wx.ITEM_RADIO)
		editMenu.Append(id_edit_drag_moves,"Drag &Moves","Set drag and drop to move messages",wx.ITEM_RADIO)
		actionsMenu = wx.Menu()
		actionsMenu.Append(id_actions_full_get,"Full &Get","Look for all messages regardless of date or proof of work")
		actionsMenu.Append(id_actions_copy_my_addr,"Copy My &Address","Put my From address on the clipboard")
		actionsMenu.Append(id_actions_new_version_check,"New &Version Check","Check for software upgrade")
		actionsMenu.Append(id_actions_view_certs,"View Server &Certs","View server certificates")
		actionsMenu.Append(id_actions_change_passphrase,"Change &Passphrase...","Change the key passphrase")
		actionsMenu.Append(id_actions_dequeue_bad_messages,"&Dequeue Bad Messages...","Remove pending messages that are causing errors")
		if self.outgoing_sync != None:
			actionsMenu.Append(id_actions_sync_folders,"&Send Folder Sync","Send pending folder changes")
			self.folder_sync_file = self.homedir + os.sep + "folder_sync_time.txt"
		actionsMenu.Append(id_actions_rotate_key,"&Rotate Encryption Subkey...","Change your encryption key for forward secrecy")
		actionsMenu.Append(id_actions_throttle_out,"&Throttle Outbound...","Reduce outgoing bandwidth",wx.ITEM_CHECK)
		self.actionsMenu = actionsMenu
		helpMenu = wx.Menu()
		helpMenu.Append(id_help_help,"&Help","View manual")
		helpMenu.Append(id_help_about,"&About")
		menuBar = wx.MenuBar()
		menuBar.Append(fileMenu,"&File")
		menuBar.Append(editMenu,"&Edit")
		menuBar.Append(actionsMenu,"&Actions")
		menuBar.Append(helpMenu,"&Help")
		self.SetMenuBar(menuBar)
		self.Bind(wx.EVT_MENU,self.OnClose,id = id_file_exit)
		self.Bind(wx.EVT_MENU,self.OnEditCut,id = id_edit_cut)
		self.Bind(wx.EVT_MENU,self.OnEditCopy,id = id_edit_copy)
		self.Bind(wx.EVT_MENU,self.OnEditPaste,id = id_edit_paste)
		self.Bind(wx.EVT_MENU,self.OnEditSelectAll,id = id_edit_select_all)
		self.Bind(wx.EVT_MENU,self.OnEditSelectNone,id = id_edit_select_none)
		self.Bind(wx.EVT_MENU,self.OnEditSelectKeyword,id = id_edit_select_keyword)
		self.Bind(wx.EVT_MENU,self.OnEditDeselectKeyword,id = id_edit_deselect_keyword)
		self.Bind(wx.EVT_MENU,self.OnEditDragCopies,id = id_edit_drag_copies)
		self.Bind(wx.EVT_MENU,self.OnEditDragMoves,id = id_edit_drag_moves)
		self.Bind(wx.EVT_MENU,self.OnActionsFullGet,id = id_actions_full_get)
		self.Bind(wx.EVT_MENU,self.OnActionsCopyMyAddr,id = id_actions_copy_my_addr)
		self.Bind(wx.EVT_MENU,self.OnActionsNewVersionCheck,id = id_actions_new_version_check)
		self.Bind(wx.EVT_MENU,self.OnActionsViewCerts,id = id_actions_view_certs)
		self.Bind(wx.EVT_MENU,self.OnActionsChangePassphrase,id = id_actions_change_passphrase)
		self.Bind(wx.EVT_MENU,self.OnActionsDequeueBadMessages,id = id_actions_dequeue_bad_messages)
		if self.outgoing_sync != None:
			self.Bind(wx.EVT_MENU,self.OnActionsSyncFolders,id = id_actions_sync_folders)
		self.Bind(wx.EVT_MENU,self.OnActionsRotateKey,id = id_actions_rotate_key)
		self.Bind(wx.EVT_MENU,self.OnActionsThrottleOut,id = id_actions_throttle_out)
		self.Bind(wx.EVT_MENU,self.OnHelpHelp,id = id_help_help)
		self.Bind(wx.EVT_MENU,self.OnHelpAbout,id = id_help_about)

		#| wx.TB_HORZ_LAYOUT
		toolbar = self.CreateToolBar( wx.TB_HORIZONTAL | wx.NO_BORDER | wx.TB_FLAT | wx.TB_TEXT )
		#tsize = (24,24)
		new_bmp = images2.composition.GetBitmap()
		getmail_bmp = images2.getmail.GetBitmap()
		post_key_bmp = images2.post_key.GetBitmap()
		open_bmp = images2.open.GetBitmap()
		reply_bmp = images2.reply.GetBitmap()
		replyall_bmp = images2.replyall.GetBitmap()
		forward_bmp = images2.forward.GetBitmap()
		archive_bmp = images2.archive.GetBitmap()
		delete_bmp = images2.trashcan.GetBitmap()
		toolbar.AddLabelTool(id_new_button, "New Msg", new_bmp, shortHelp="New/Addr", longHelp="Compose a new message; right-click for Address Book")
		toolbar.AddLabelTool(id_open_button, "Open Msg", open_bmp, shortHelp="Open Message", longHelp="Open message with rich text")
		toolbar.AddLabelTool(id_open_txt_button, "Open Txt", open_bmp, shortHelp="Open Text Only", longHelp="Open untrusted message text-only")
		toolbar.AddLabelTool(id_reply_button, "Reply", reply_bmp, shortHelp="Reply", longHelp="Reply to sender only")
		toolbar.AddLabelTool(id_reply_all_button, "Reply All", replyall_bmp, shortHelp="Reply All", longHelp="Reply to all recipients")
		toolbar.AddLabelTool(id_forward_button, "Fwd Text", forward_bmp, shortHelp="Forward Text", longHelp="Forward the message text only")
		toolbar.AddLabelTool(id_forward_all_button, "Fwd All", forward_bmp, shortHelp="Forward All", longHelp="Forward the message, attachments, and signature")
		toolbar.AddLabelTool(id_archive_button, "Archive", archive_bmp, shortHelp="Archive", longHelp="Archive selected messages")
		toolbar.AddLabelTool(id_delete_button, "Delete", delete_bmp, shortHelp="Delete", longHelp="Delete selected messages")
		toolbar.AddLabelTool(id_check_send_button, "Check/Send", getmail_bmp, shortHelp="Check Mail", longHelp="Check for new incoming mail and send any pending mail")
		toolbar.AddLabelTool(id_post_key_button, "Post Key", post_key_bmp, shortHelp="Post Key", longHelp="Post GPG key to server and Entangled")

		self.Bind(wx.EVT_TOOL,self.OnNewMessageClick,id = id_new_button)
		self.Bind(wx.EVT_TOOL_RCLICKED,self.OnNewMessageRightClick,id = id_new_button)
		self.Bind(wx.EVT_TOOL,self.OnOpenClick,id = id_open_button)
		self.Bind(wx.EVT_TOOL,self.OnOpenTxtClick,id = id_open_txt_button)
		self.Bind(wx.EVT_TOOL,self.OnReplyClick,id = id_reply_button)
		self.Bind(wx.EVT_TOOL,self.OnReplyAllClick,id = id_reply_all_button)
		self.Bind(wx.EVT_TOOL,self.OnForwardClick,id = id_forward_button)
		self.Bind(wx.EVT_TOOL,self.OnForwardAllClick,id = id_forward_all_button)
		self.Bind(wx.EVT_TOOL,self.OnCheckSendClick,id = id_check_send_button)
		self.Bind(wx.EVT_TOOL,self.OnPostKeyClick,id = id_post_key_button)
		self.Bind(wx.EVT_TOOL,self.OnArchiveClick,id = id_archive_button)
		self.Bind(wx.EVT_TOOL,self.OnDeleteClick,id = id_delete_button)
		toolbar.Realize()
		self.toolbar = toolbar

		self.verticalSplitter = wx.SplitterWindow(self,style = wx.SP_LIVE_UPDATE)
		self.folderTree = FolderTree(self.verticalSplitter,self)
		self.messageList = MessageListCtrl(self.verticalSplitter,self)
		self.verticalSplitter.Bind(wx.EVT_SPLITTER_SASH_POS_CHANGED,self.OnResizeSplitter)

		found,sashpos = self.folder_store.get_global("SASHPOS")
		if found:
			sashpos = int(sashpos)
		else:
			sashpos = int(200 * global_config.resolution_scale_factor)
		self.verticalSplitter.SplitVertically(self.folderTree,self.messageList,sashpos)

		self.folderTree.SelectItem(self.folderTree.folders_by_path[folders.id_inbox])

		keyicon_bmp = images2.key_icon.GetBitmap()
		keyicon = wx.IconFromBitmap(keyicon_bmp)
		self.SetIcon(keyicon)

		self.new_messages_to_process = self.complete_store.keys_by_date()
		if len(self.new_messages_to_process) > 0:
			self.non_sync_messages_processed = 0
			self.process_new_messages_timer.Start(global_config.process_new_message_interval,wx.TIMER_ONE_SHOT)

	def ShowTemporaryStatus(self,message):
		self.SetStatusText(message,0)
		self.clearStatusTimer.Start(global_config.status_display_time,wx.TIMER_ONE_SHOT)

	def OnNewMessageRightClick(self,event):
		return self.OnNewMessageClick(event,addrBookMode = True)

	def OnNewMessageClick(self,event,addrBookMode = False):
		if self.local_store.exists(self.client_keyid_hex) == False: # key never posted
			# Do not let user get to the address book without posting the key
			self.gui.to_agent_queue.put( [ 'POST_KEY', True,True ] )
			if self.passphraseEntered == False:
				self.newMessagePending = True
				return
		frame = message_edit_window.MessageEditFrame(self,self.gui,"New Message",None,addrBook = addrBookMode)
		frame.Show()
		self.newMessageFrames.append(frame)

	def CheckUpdateKey(self):
		update_key = False
		posting_date = ""
		found,announce_message = self.local_store.retrieveHeaders(self.client_keyid_hex)
		if found == True:
			for line in announce_message:
				if line[0:6].upper() == "DATE: " and posting_date == "":
					posting_date = line[6:]
			if posting_date == "":
				update_key = True
			else:
				posting_datetime = datetime.datetime.strptime(posting_date,"%Y-%m-%dT%H:%M:%SZ")
				current_datetime = datetime.datetime.utcnow()
				announcement_age = current_datetime - posting_datetime
				ageS = announcement_age.total_seconds()
				if ageS >= global_config.renew_age_key:
					update_key = True
		else:
			update_key = True
		if self.key_update_required == True:
			update_key = True
		if update_key == True:
			self.gui.to_agent_queue.put( [ 'POST_KEY', True,True ] )
		
	def OnEditCut(self,event):
		self.pasteCut = True
		self.EditCutCopyCommon()

	def OnEditCopy(self,event):
		self.pasteCut = False
		self.EditCutCopyCommon()

	def EditCutCopyCommon(self):
		selectedList = [ ]
		selected = -1
		while True:
			selected = self.messageList.GetNextItem(selected,state = wx.LIST_STATE_SELECTED)
			if selected < 0:
				break
			selectedList.append(self.messageList.rowMessageIds[self.messageList.GetItemData(selected)])
		if len(selectedList) > 0:
			self.pasteList = selectedList
			self.pasteFromFolder = self.current_folder_path

	def OnEditPaste(self,event):
		if self.pasteList != None and self.pasteFromFolder != None and self.pasteCut != None:
			for message in self.pasteList:
				self.folder_store.put_message_in_folder(self.current_folder_path,message)
				if self.pasteCut == True:
					self.folder_store.delete_message_from_folder(self.pasteFromFolder,message)
			self.folder_store.commit()
			self.OpenMailFolder(self.current_folder_path)
			if len(self.pasteList) == 1 and self.pasteCut == True:
				message = "Moved one message to "
			elif len(self.pasteList) > 1 and self.pasteCut == True:
				message = "Moved " + str(len(self.pasteList)) + " messages to "
			elif len(self.pasteList) == 1 and self.pasteCut == False:
				message = "Copied one message to "
			else: # if len(self.pasteList) > 1 and self.pasteCut == False:
				message = "Copied " + str(len(self.pasteList)) + " messages to "
 			message += self.current_folder_path.replace('\x00','/')
			self.ShowTemporaryStatus(message)
		self.pasteList = None
		self.pasteFromFolder = None
		self.pasteCut = None

	def OnEditDragCopies(self,event):
		self.dragMoves = False

	def OnEditDragMoves(self,event):
		self.dragMoves = True

	def OnEditSelectAll(self,event):
		#DBGOUT#print "select all"	
		numSelected = 0
		selected = -1
		while True:
			selected = self.messageList.GetNextItem(selected)
			if selected < 0:
				break
			self.messageList.Select(selected,1)
			numSelected += 1
		wx.CallAfter(self.messageList.SetFocus)
		if numSelected == 1:
			message = "Selected one message"
		elif numSelected > 1:
			message = "Selected " + str(numSelected) + " messages"
		if numSelected >= 1:
			self.ShowTemporaryStatus(message)

	def OnEditSelectNone(self,event):
		selected = -1
		while True:
			selected = self.messageList.GetNextItem(selected)
			if selected < 0:
				break
			self.messageList.Select(selected,0)
		wx.CallAfter(self.messageList.SetFocus)

	def OnEditSelectKeyword(self,event):
		if self.searchDialogOpen == False:
			self.searchDialogOpen = True
			self.searchDialog = search_dialog.SearchDialogFrame(self,"Search and select messages",callback = self.OnSelectKeyword)
			self.searchDialog.Show()
		else:
			self.searchDialog.SetFocus()

	def OnEditDeselectKeyword(self,event):
		if self.searchDialogOpen == False:
			self.searchDialogOpen = True
			self.searchDialog = search_dialog.SearchDialogFrame(self,"Search and deselect messages",callback = self.OnDeselectKeyword)
			self.searchDialog.Show()
		else:
			self.searchDialog.SetFocus()

	def OnSelectKeyword(self,searchText,checkboxFrom,checkboxTo,checkboxSubject,
			checkboxBody,checkboxCase,checkboxRegex,isClosed):
		if isClosed == True:
			self.searchDialogOpen = False
			self.messageList.SetFocus()
		else:
			self.OnSelDesKeywordCommon(searchText,checkboxFrom,checkboxTo,
				checkboxSubject,checkboxBody,checkboxCase,checkboxRegex,False)

	def OnDeselectKeyword(self,searchText,checkboxFrom,checkboxTo,checkboxSubject,
			checkboxBody,checkboxCase,checkboxRegex,isClosed):
		if isClosed == True:
			self.searchDialogOpen = False
			self.messageList.SetFocus()
		else:
			self.OnSelDesKeywordCommon(searchText,checkboxFrom,checkboxTo,
				checkboxSubject,checkboxBody,checkboxCase,checkboxRegex,True)

	def OnSelDesKeywordCommon(self,searchText,checkboxFrom,checkboxTo,checkboxSubject,
			checkboxBody,checkboxCase,checkboxRegex,deselectMode):
		if searchText == '':
			self.ShowTemporaryStatus('Search field was empty')
			return
		if checkboxRegex == True:
			try:
				if checkboxCase == False:
					searchRegex = re.compile(searchText)
				else:
					searchRegex = re.compile(searchText,re.IGNORECASE)
			except Exception as exc:
				self.ShowTemporaryStatus('Bad regex: ' + str(exc))
				return
		elif checkboxCase == False:
			searchTextL = searchText.lower()

		fromField = -1
		toField = -1
		suField = -1
		i = 0
		for f in self.messageList.listFields:
			title,abbr = f
			if abbr == 'FR':
				fromField = i
			elif abbr == 'TO':
				toField = i
			elif abbr == 'SU':
				suField = i
			i += 1
	
		thisitem = -1
		matchingRows = [ ]
		numMatching = 0
		totalRows = self.messageList.GetItemCount()
		searchedRows = 0
		lastDisplayTime = 0

		if ((checkboxBody == True) and (totalRows >= 100)) or (totalRows >= 1000):
			displayProgress = True
		else:
			displayProgress = False

		if displayProgress == True:
			title = "Search Progress"
			message = "Searched " + str(searchedRows) + " of " + str(totalRows) + " messages, " + str(numMatching) + " matched"
			searchProgressDialog = wx.GenericProgressDialog(title,message,totalRows,parent = self,style = wx.PD_CAN_ABORT|wx.PD_AUTO_HIDE)
			searchProgressDialog.Show()

		while True:
			thisitem = self.messageList.GetNextItem(thisitem,state = wx.LIST_STATE_DONTCARE)
			if thisitem < 0:
				break
			thisrow = self.messageList.itemDataMap[self.messageList.GetItemData(thisitem)]
			matches = False
			if checkboxFrom == True:
				if checkboxRegex == True:
					if searchRegex.search(thisrow[fromField].decode('utf-8')):
						matches = True
				elif checkboxCase == False:
					if thisrow[fromField].decode('utf-8').lower().find(searchTextL) >= 0:
						matches = True
				else:
					if thisrow[fromField].decode('utf-8').find(searchText) >= 0:
						matches = True

			if matches == False and checkboxTo == True:
				if checkboxRegex == True:
					if searchRegex.search(thisrow[toField].decode('utf-8')):
						matches = True
				elif checkboxCase == False:
					if thisrow[toField].decode('utf-8').lower().find(searchTextL) >= 0:
						matches = True
				else:
					if thisrow[toField].decode('utf-8').find(searchText) >= 0:
						matches = True

			if matches == False and checkboxSubject == True:
				if checkboxRegex == True:
					if searchRegex.search(thisrow[suField].decode('utf-8')):
						matches = True
				elif checkboxCase == False:
					if thisrow[suField].decode('utf-8').lower().find(searchTextL) >= 0:
						matches = True
				else:
					if thisrow[suField].decode('utf-8').find(searchText) >= 0:
						matches = True

			if matches == False and checkboxBody == True:
				bodytext = ''
				try:
					messageId = self.messageList.rowMessageIds[self.messageList.GetItemData(thisitem)]
					found,headers = self.folder_store.get_message(messageId)
					if found == True and headers['TY'] == 'O':
						found,messagedata = self.local_store.retrieve(messageId.encode('hex'))
						if found == True:
							recipients,recipients_full,attachments,reply_thread_id,forward_original_id,subject,bodytext,body_html,body_xml,save_date = pickle.loads(messagedata)
					elif found == True and headers['TY'] == 'I':
						zipFilePath = self.local_store.getPath(messageId.encode('hex')) + '.ZIP'
						zipFile = zipfile.ZipFile(zipFilePath,'r')
						bodytext = zipFile.read('BODY.TXT').decode('utf-8')
						zipFile.close()
					elif found == True and headers['TY'] == 'S':
						bodytext = headers['TX']
				except Exception:
					pass

				if checkboxRegex == True:
					if searchRegex.search(bodytext):
						matches = True
				elif checkboxCase == False:
					if bodytext.lower().find(searchTextL) >= 0:
						matches = True
				else:
					if bodytext.find(searchText) >= 0:
						matches = True

			if matches == True:
				matchingRows.append(thisitem)
				numMatching += 1

			searchedRows += 1
			if displayProgress == True and ((searchedRows == totalRows) or ((searchedRows % 10) == 0)):
				nowTime = time.time()
				if (searchedRows == totalRows) or ((nowTime - lastDisplayTime) >= 1.0):
					lastDisplayTime = nowTime
					message = "Searched " + str(searchedRows) + " of " + str(totalRows) + " messages, " + str(numMatching) + " matched"
					cont,junk = searchProgressDialog.Update(searchedRows,message)
					if cont == False:
						searchProgressDialog.Destroy()
						break

		searchProgressDialog = None
		if deselectMode == True:
			msg = 'Deselected '
		else:
			msg = 'Selected '
		if len(matchingRows) == 1:
			msg += 'one message '
		else:
			msg += str(len(matchingRows)) + ' messages'
			
		if deselectMode == True:
			for row in matchingRows:
				self.messageList.SetItemState(row,0,wx.LIST_STATE_SELECTED)
		else:
			for row in matchingRows:
				self.messageList.SetItemState(row,wx.LIST_STATE_SELECTED,wx.LIST_STATE_SELECTED)
		self.ShowTemporaryStatus(msg)
		self.searchDialog.SetFocus()

	def OnSetTemplateClick(self,event):
		if self.messageList.rclickMessageId != self.template_message:
			self.template_message = self.messageList.rclickMessageId
			self.folder_store.set_global('TEMPLATE',self.template_message)
			self.folder_store.commit()
			self.OpenMailFolder(self.current_folder_path)
			
	def OnUnsetTemplateClick(self,event):
		if self.messageList.rclickMessageId == self.template_message:
			self.template_message = None
			self.folder_store.del_global('TEMPLATE')
			self.folder_store.commit()
			self.OpenMailFolder(self.current_folder_path)

	def OnOpenClick(self,event):
		return self.OnOpenCommon(event,False)

	def OnOpenTxtClick(self,event):
		return self.OnOpenCommon(event,True)

	def OnOpenRTClick(self,event):
		return self.OnOpenCommon(event,False,True)

	def OnOpenCommon(self,event,textOnly,forceRich = False):
		#DBGOUT#print "open"
		selectedList = [ ]
		selected = -1
		i = 0
		while i < 20:
			selected = self.messageList.GetNextItem(selected,state = wx.LIST_STATE_SELECTED)
			if selected < 0:
				break
			messageId = self.messageList.rowMessageIds[self.messageList.GetItemData(selected)]
			self.messageList.OpenMessageById(messageId,textOnly = textOnly,deBold = selected,forceRich = forceRich)
			i += 1

	def OnKeyDown(self,event):
		kc = event.GetKeyCode()
		if kc == wx.WXK_DELETE:
			return self.OnDeleteClick(event)
		elif kc == wx.WXK_F1:
			return self.OnHelpClick(event)
		else:
			event.Skip()

	def OnDeleteClick(self,event,allow_refetch = False):
		#DBGOUT#print "delete"
		selectedList = [ ]
		selected = -1
		while True:
			selected = self.messageList.GetNextItem(selected,state = wx.LIST_STATE_SELECTED)
			if selected < 0:
				break
			selectedList.append(self.messageList.rowMessageIds[self.messageList.GetItemData(selected)])

		if self.current_folder_path == folders.id_deleted and len(selectedList) > 0:
			# If deleting a message from Deleted that has been copied back elsewhere, no need to confirm
			need_confirm = 0
			for message in selectedList:
				folders_containing = self.folder_store.get_folders_containing_message(message)
				if len(folders_containing) == 1 and folders.id_deleted in folders_containing:
					need_confirm += 1
			if need_confirm > 0:	
				if len(selectedList) == 1:
					message = "Permanently delete selected message?"
				elif len(selectedList) == need_confirm:
					message = "Permanently delete " + str(need_confirm) + " messages?"
				else:
					message = "Permanently delete " + str(need_confirm) + " of " + str(len(selectedList)) + " selected messages?"
				dlg = wx.MessageDialog(self,message,"Confirm permanent delete",style = wx.YES_NO|wx.CENTRE|wx.ICON_QUESTION)
				if dlg.ShowModal() != wx.ID_YES:
					dlg.Destroy()
					return
				dlg.Destroy()

			for message in selectedList:
				folders_containing = self.folder_store.get_folders_containing_message(message)
				if len(folders_containing) == 1 and folders.id_deleted in folders_containing:
					if allow_refetch == True:
						delok = self.folder_store.delete_all_files_for_message(message,allow_refetch = True)
					else:
						delok = self.folder_store.delete_all_files_for_message(message)
					if delok == False:
						wx.CallAfter(wx.MessageBox,"The message file is open. Please close the viewing window and try again.","Delete failed",style = wx.ICON_EXCLAMATION)
						return
				self.folder_store.delete_message_from_folder(self.current_folder_path,message)
			self.folder_store.commit()
			self.OpenMailFolder(self.current_folder_path)

		elif self.current_folder_path == folders.id_send_pending and len(selectedList) > 0:
			for message in selectedList:
				folders_containing = self.folder_store.get_folders_containing_message(message)
				if len(folders_containing) == 2 and folders.id_send_pending in folders_containing \
												and folders.id_ack_pending in folders_containing:
					self.folder_store.delete_all_files_for_message(message,outgoing_pending_only = True)
					self.folder_store.put_message_in_folder(folders.id_deleted,message)
					self.folder_store.delete_message_from_folder(folders.id_ack_pending,message)
				elif len(folders_containing) == 1 and folders.id_send_pending in folders_containing:
					self.folder_store.delete_all_files_for_message(message,outgoing_pending_only = True)
					self.folder_store.put_message_in_folder(folders.id_deleted,message)
				self.folder_store.delete_message_from_folder(self.current_folder_path,message)
			self.folder_store.commit()
			self.OpenMailFolder(self.current_folder_path)

		elif len(selectedList) > 0:
			for message in selectedList:
				folders_containing = self.folder_store.get_folders_containing_message(message)
				if self.current_folder_path not in folders_containing:
					continue # should not happen
				if len(folders_containing) == 1: # only in this folder
					self.folder_store.put_message_in_folder(folders.id_deleted,message)
				elif self.current_folder_path == folders.id_inbox and len(folders_containing) == 2 and \
						folders.id_inbox in folders_containing and folders.id_new_messages in folders_containing:
					# as a special case, delete from inbox also deletes from new messages
					self.folder_store.put_message_in_folder(folders.id_deleted,message)
					self.folder_store.delete_message_from_folder(folders.id_new_messages,message)
				self.folder_store.delete_message_from_folder(self.current_folder_path,message)
			self.folder_store.commit()
			self.OpenMailFolder(self.current_folder_path)

		if len(selectedList) > 0:
			if len(selectedList) == 1:
				message = "Deleted one message"
			else:
				message = "Deleted " + str(len(selectedList)) + " messages"
			self.ShowTemporaryStatus(message)

	def OnArchiveClick(self,event,allow_refetch = False):
		selectedList = [ ]
		selected = -1
		while True:
			selected = self.messageList.GetNextItem(selected,state = wx.LIST_STATE_SELECTED)
			if selected < 0:
				break
			selectedList.append(self.messageList.rowMessageIds[self.messageList.GetItemData(selected)])
		if self.current_folder_path == folders.id_inbox or self.current_folder_path == folders.id_new_messages:
			fromFolders = [ folders.id_inbox,folders.id_new_messages ]
		else:
			fromFolders = [ self.current_folder_path ]
		self.MoveMessagesToArchive(selectedList,fromFolders)

	def MoveMessagesToArchive(self,messageIds,fromFolders):
		archive_existed = self.folder_store.check_exist_folder(folders.id_archive)
		if archive_existed == False:
			self.folder_store.check_add_folder(folders.id_archive)
		for messageId in messageIds:
			folders_containing = self.folder_store.get_folders_containing_message(messageId)
			self.folder_store.put_message_in_folder(folders.id_archive,messageId)
			for fromFolder in fromFolders:
				if fromFolder == folders.id_archive:
					continue
				self.folder_store.delete_message_from_folder(fromFolder,messageId)
		self.folder_store.commit()
		if archive_existed == False:
			self.folderTree.LoadTree()
		if self.current_folder_path in fromFolders or self.current_folder_path == folders.id_archive:
			self.OpenMailFolder(self.current_folder_path) # refresh

	def DeleteMessageFromFolder(self,messageIdHex,fromFolders):
		messageId = messageIdHex.decode('hex')
		folders_containing = self.folder_store.get_folders_containing_message(messageId)
		for fromFolder in fromFolders:
			if fromFolder == folders.id_deleted:
				continue # not deleting permanently here
			if fromFolder not in folders_containing:
				continue # should not happen
			if len(folders_containing) == 1: # only in this folder
				self.folder_store.put_message_in_folder(folders.id_deleted,messageId)
			self.folder_store.delete_message_from_folder(fromFolder,messageId)
			folders_containing.remove(fromFolder)
		self.folder_store.commit()
		if self.current_folder_path in fromFolders or self.current_folder_path == folders.id_deleted:
			self.OpenMailFolder(self.current_folder_path) # refresh

	def OnHelpClick(self,event):
		self.helpcon = wx.html.HtmlHelpController(parentWindow = self)
 		wx.FileSystem.AddHandler(wx.ZipFSHandler())
		self.helpcon.AddBook(global_config.help_file,0)
		self.helpcon.DisplayContents()
		self.helpcon.Display("message_list.html")
		if global_config.resolution_scale_factor != 1.0:
			frame = self.helpcon.GetFrame()
			frameX,frameY = frame.GetSize()
			frameX *= global_config.resolution_scale_factor
			frameY *= global_config.resolution_scale_factor
			frame.SetSize( (frameX,frameY) )

	def OpenMailFolder(self,folder_path):
		self.current_folder_path = folder_path
		messageIds = self.folder_store.get_messages_in_folder(folder_path)
		folderHeaders = [ ]
		for m in messageIds:
			found,header = self.folder_store.get_message(m)
			if found == True:
				if self.folder_store.is_message_in_folder(folders.id_new_messages,m) == True:
					header['NEW'] = True
				folderHeaders.append(header)
		self.messageList.LoadFolder(folderHeaders)

	def OnReplyClick(self,event):			
		self.ReplyForwardCommon('R','Reply')

	def OnReplyAllClick(self,event):			
		self.ReplyForwardCommon('RA','Reply')

	def OnForwardClick(self,event):			
		self.ReplyForwardCommon('F','Forward')

	def OnForwardAllClick(self,event):			
		self.ReplyForwardCommon('FA','Forward')

	def ReplyForwardCommon(self,rftype,title):
		selected = -1
		while True:
			selected = self.messageList.GetNextItem(selected,state = wx.LIST_STATE_SELECTED)
			if selected < 0:
				break
			messageId = self.messageList.rowMessageIds[self.messageList.GetItemData(selected)].encode('hex')
			found,headers = self.folder_store.get_message(messageId.decode('hex'))
			if found == True and headers['TY'] == 'I':
				frame = message_edit_window.MessageEditFrame(self,self.gui,title,reply_forward_id = messageId,reply_forward_type = rftype)
				frame.Show()
			elif found == True and headers['TY'] == 'O':
				self.messageList.OpenMessageById(messageId.decode('hex'),reopen = True,textOnly = False)
			elif found == True and headers['TY'] == 'S':
				self.messageList.OpenMessageById(messageId.decode('hex'),textOnly = False)

	def OnMarkRead(self,event):
		selected = -1
		changed = False
		while True:
			selected = self.messageList.GetNextItem(selected,state = wx.LIST_STATE_SELECTED)
			if selected < 0:
				break
			messageId = self.messageList.rowMessageIds[self.messageList.GetItemData(selected)]
			if self.folder_store.is_message_in_folder(folders.id_new_messages,messageId) == True:
				changed = True
				if self.folder_store.is_message_in_folder(folders.id_inbox,messageId) == False:
					self.folder_store.put_message_in_folder(folders.id_inbox,messageId)
				self.folder_store.delete_message_from_folder(folders.id_new_messages,messageId)
				self.messageList.SetItemFont(selected,self.messageList.regularFontObj)
		if changed == True:
			self.folder_store.commit()

	def OnMarkUnread(self,event):
		selected = -1
		changed = False
		while True:
			selected = self.messageList.GetNextItem(selected,state = wx.LIST_STATE_SELECTED)
			if selected < 0:
				break
			messageId = self.messageList.rowMessageIds[self.messageList.GetItemData(selected)]
			if self.folder_store.is_message_in_folder(folders.id_new_messages,messageId) == False:
				changed = True
				self.folder_store.put_message_in_folder(folders.id_new_messages,messageId)
				self.messageList.SetItemFont(selected,self.messageList.boldFontObj)
		if changed == True:
			self.folder_store.commit()

	def OnSetColorCommon(self,event,color):
		selected = -1
		changed = False
		while True:
			selected = self.messageList.GetNextItem(selected,state = wx.LIST_STATE_SELECTED)
			if selected < 0:
				break
			messageId = self.messageList.rowMessageIds[self.messageList.GetItemData(selected)]
			item = self.messageList.GetItem(selected)
			item.SetTextColour(color)
			self.messageList.SetItem(item)
			found,header = self.folder_store.get_message(messageId)
			if found == False:
				continue
			header['CLR'] = color
			self.folder_store.save_message(messageId,header)
			if self.outgoing_sync != None:
				self.outgoing_sync.addChange( [ 'SetColor',messageId,color ] )
			changed = True
		if changed == True:
			self.folder_store.commit()

	def DragCopyMove(self,messageList,toFolder,fromFolder):
		for message in messageList:
			self.folder_store.put_message_in_folder(toFolder,message)
			if self.dragMoves == True:
				#DBGOUT#print "moving ",message.encode('hex')
				self.folder_store.delete_message_from_folder(fromFolder,message)
				#DBGOUT#print "Delete "+message.encode('hex')+" from "+fromFolder
			#DBGOUT#else:
				#DBGOUT#print "copying ",message.encode('hex')
		self.folder_store.commit()
		if self.dragMoves == True or toFolder == folders.id_new_messages:
			self.OpenMailFolder(self.current_folder_path)
		if len(messageList) == 1 and self.dragMoves == True:
			message = "Moved one message to "
		elif len(messageList) > 1 and self.dragMoves == True:
			message = "Moved " + str(len(messageList)) + " messages to "
		elif len(messageList) == 1 and self.dragMoves == False:
			message = "Copied one message to "
		else: # if len(messageList) > 1 and self.dragMoves == False:
			message = "Copied " + str(len(messageList)) + " messages to "
 		message += toFolder.replace('\x00','/')
		self.ShowTemporaryStatus(message)

	def AskForPassphrase(self):
		dlg = wx.PasswordEntryDialog(self,'Enter Passphrase','Key Passphrase','')
		if dlg.ShowModal() != wx.ID_OK:
			self.gui.to_agent_queue.put( [ 'PASSPHRASE_REFUSED' ] )
			dlg.Destroy()
			return
		passphrase = dlg.GetValue()
		dlg.Destroy()
		self.gui.to_agent_queue.put( [ 'SET_PASSPHRASE', passphrase ] )
		self.passphrase = passphrase

	def CheckSentMessage(self,messageId):
		folder_list = self.folder_store.get_folders_containing_message(messageId)
		if folders.id_send_pending not in folder_list:
			return
		messageIdH = messageId.encode('hex')
		#DBGOUT#print "check if "+messageIdH+" has been sent"
		headername = self.local_store.getPath(messageIdH) + '.HDR'
		try:
			fh = open(headername,'r')
			headers = fh.read()
			fh.close()
		except IOError:
			#DBGOUT#print "unable to read file "+headername
			return	
		blocksExist = False
		for line in headers.split('\n'):
			line = line.rstrip('\r\n')
			lineU = line.upper()
			if lineU[0:11] == 'DATABLOCK: ':
				blockId = lineU[11:]
				blocksExist = blocksExist | self.gui.outbox_store.exists(blockId)
			elif lineU[0:15] == 'ANNOUNCEBLOCK: ':
				blockId = lineU[15:]
				blocksExist = blocksExist | self.gui.outbox_store.exists(blockId)
		if blocksExist == False:
			if folders.id_sent_messages not in folder_list:
				self.folder_store.put_message_in_folder(folders.id_sent_messages,messageId)
				#DBGOUT#print "putting message "+messageIdH+" in sent folder"
			self.folder_store.delete_message_from_folder(folders.id_send_pending,messageId)
			self.folder_store.commit()
			if self.current_folder_path == folders.id_send_pending or self.current_folder_path == folders.id_sent_messages or self.current_folder_path == folders.id_ack_pending:
				self.OpenMailFolder(self.current_folder_path)
			#DBGOUT#print "message has been sent",folder_list
		#DBGOUT#else:
			#DBGOUT#print "message has not been sent"
	
	def GetAcksForMessage(self,messageId):
		messageIdH = messageId.encode('hex')
		headername = self.local_store.getPath(messageIdH) + '.HDR'
		#DBGOUT#print "check if",type(messageId),len(messageId),messageIdH,"has been acked, file=",headername
		ackHashes = set()
		try:
			fh = open(headername,'r')
			headers = fh.read()
			fh.close()
		except IOError:
			return ackHashes
		blocksExist = False
		for line in headers.split('\n'):
			line = line.rstrip('\r\n')
			m = re_ack.match(line)
			if m:
				ackHashes.add(m.group(2).decode('hex'))
		return ackHashes
		
	# Do all the file I/O piecemeal so as to not slow down the GUI
	def CheckSendAck(self,event): # timer event entry
		if self.sentToCheck != None and len(self.sentToCheck) > 0:
			messageId = self.sentToCheck.pop(0)
			self.CheckSentMessage(messageId)
			if len(self.sentToCheck) == 0:
				self.sentToCheck = None
			self.check_send_ack_timer.Start(global_config.check_send_ack_interval,wx.TIMER_ONE_SHOT)
		elif self.acksToCheck != None and len(self.acksToCheck) > 0:
			if self.ackHashes == None:
				self.ackHashes = set()
				self.ackHashesByMessageId = dict()
				self.acksWeHave = set()
			messageId = self.acksToCheck.pop(0)
			ackHashes = self.GetAcksForMessage(messageId)
			self.ackHashes.update(ackHashes)
			self.ackHashesByMessageId[messageId] = ackHashes
			for ackHash in ackHashes:
				if self.local_store.exists(ackHash.encode('hex')) == True:
					self.acksWeHave.add(ackHash)
			self.check_send_ack_timer.Start(global_config.check_send_ack_interval,wx.TIMER_ONE_SHOT)
		elif self.acksToCheck != None and len(self.acksToCheck) == 0:
			self.acksToCheck = None
			if self.ackHashes != None and len(self.ackHashes) > 0:
				self.gui.to_agent_queue.put( [ 'ACK_SEARCH', list(self.ackHashes) ] )
			else:
				self.checkSendAckActive = False
		else:
			self.checkSendAckActive = False
			
	# Finalize in one step when the client agent returns the list
	def ProcessAcksFound(self,acksFound):
		#DBGOUT#print "acks found",acksFound
		#DBGOUT#print "acks we have",self.acksWeHave
		self.acksWeHave.update(acksFound)
		#DBGOUT#print "new acks we have",self.acksWeHave
		changesMade = False
		for messageId in self.ackHashesByMessageId.keys():
			#DBGOUT#print "message",messageId,self.ackHashesByMessageId[messageId]
			if self.ackHashesByMessageId[messageId].issubset(self.acksWeHave):
				#DBGOUT#print "got all acks for this one!"

				folders_containing = self.folder_store.get_folders_containing_message(messageId)
				if len(folders_containing) == 1:
					self.folder_store.put_message_in_folder(folders.id_sent_messages,messageId) # don't lose message
				self.folder_store.delete_message_from_folder(folders.id_ack_pending,messageId,skip_sync = True)
				changesMade = True
		if changesMade == True:
			self.folder_store.commit()
			if self.current_folder_path == folders.id_ack_pending:
				self.OpenMailFolder(self.current_folder_path)
		self.checkSendAckActive = False

	def CheckSendPending(self,hasErrors):
		if self.checkSendAckActive != True:
			#DBGOUT#print "Check send pending"
			self.checkSendAckActive = True
			self.sentToCheck = self.folder_store.get_messages_in_folder(folders.id_send_pending)
			self.acksToCheck = None
			self.ackHashes = None
			self.check_send_ack_timer.Start(global_config.check_send_ack_interval,wx.TIMER_ONE_SHOT)
			if hasErrors == False:
				self.ShowTemporaryStatus("Message send completed")

	def StartCheckAckIfDue(self):
		if self.checkSendAckActive != True:
			nowtime = time.time()
			if nowtime - self.lastCheckSendAck >= global_config.check_for_acks_interval:
				self.lastCheckSendAck = nowtime
				#DBGOUT#print "Check send pending and ack pending"
				self.checkSendAckActive = True
				self.sentToCheck = self.folder_store.get_messages_in_folder(folders.id_send_pending)
				self.acksToCheck = self.folder_store.get_messages_in_folder(folders.id_ack_pending)
				#DBGOUT#print "acksToCheck=",self.acksToCheck
				self.ackHashes = None
				self.check_send_ack_timer.Start(global_config.check_send_ack_interval,wx.TIMER_ONE_SHOT)

	# This method normally displays an upgrade notice in the status text at the bottom of the window.
	# However, I have added an option to display a pop-up message box. This will only be used if
	# there is a major security flaw. I don't like annoying upgrade nags, but I think the option
	# is necessary in case of emergency. -- Mike
	def NewVersionCheckResult(self,status,message):
		if status == True and message == None:
			return
		if status == False:
			message = 'New version check failed'
		showPopup = False
		if message[0:6] == 'POPUP ':
			message = message[6:]
			wx.CallAfter(wx.MessageBox,message,"Security Warning: Upgrade Required",style = wx.ICON_EXCLAMATION)
		self.SetStatusText(message,0)
		self.clearStatusTimer.Start(global_config.upgrade_check_duration,wx.TIMER_ONE_SHOT)
	
	def OnClearStatusTimer(self,event):
		self.SetStatusText("",0)

	def PostSystemMessage(self,message):
		pickled_message = pickle.dumps(message,pickle.HIGHEST_PROTOCOL)
		message_hash = message['ID']
		message['RE'] = [ ( 'T',self.client_keyid_hex,self.from_address_name ) ]
		message['TY'] = 'S'
		self.folder_store.save_message(message_hash,message)
		self.folder_store.put_message_in_folder(folders.id_system_messages,message_hash,skip_sync = True)
		self.folder_store.commit()
		if self.current_folder_path == folders.id_system_messages:
			self.OpenMailFolder(self.current_folder_path) # refresh
		statusline = 'System Message: ' + message['SU']
		self.ShowTemporaryStatus(statusline)

	def OnClientAgentMessage(self,event): # this is bound from gui.py startup
		# event.cmd and event.args
		#DBGOUT#print "got client agent message",event.cmd,event.args,"time",time.time()
		self.client_agent_good = True
		if event.cmd == 'SET_STATUS_LINE':
			if event.args[0] != None:
				self.SetStatusText(event.args[0],0)
			if event.args[1] != None:
				self.SetStatusText(event.args[1],1)
		elif event.cmd == 'ENABLE_CHECK_SEND':
			self.EnableCheckSend(event.args[0])
		elif event.cmd == 'NEW_MESSAGES':
			self.messageList.lastSortState = self.messageList.GetSortState()
			#DBGOUT#print 'sort state: ',self.messageList.lastSortState
			self.new_messages_to_process = self.complete_store.keys_by_date()
			if len(self.new_messages_to_process) == 1:
				self.ShowTemporaryStatus('Received one new message')
			elif len(self.new_messages_to_process) > 1:
				self.ShowTemporaryStatus('Received ' + str(len(self.new_messages_to_process))  + ' new messages')
			self.non_sync_messages_processed = 0
			self.process_new_messages_timer.Start(global_config.process_new_message_interval,wx.TIMER_ONE_SHOT)
		elif event.cmd == 'NEW_FORWARDED_ORIGINAL':
			self.ProcessNewForwardedOriginal(event.args[0])
		elif event.cmd == 'OPEN_MESSAGE': # used after forwarded original
			self.OpenMessageFromAgent(event.args[0])
		elif event.cmd == 'POST_SYSTEM_MESSAGE':
			self.PostSystemMessage(event.args[0])	
		elif event.cmd == 'AGENT_NEW_KEYS':
			self.gui.LoadKeyList()
		elif event.cmd == 'CHECK_SEND_PENDING':
			self.CheckSendPending(event.args[0])
		elif event.cmd == 'ACK_SEARCH_RESULTS':
			self.ProcessAcksFound(event.args[0])
		elif event.cmd == 'SET_AB_STATUS_LINE' or event.cmd == 'AB_KEY_SEARCH_DONE' \
		  or event.cmd == 'AB_KEY_FOUND' or event.cmd == 'AB_KEY_IMP_DEL_DONE' \
		  or event.cmd == 'AB_REF_KEY_SEARCH_DONE':
			if self.openAddressBook != None:
				self.openAddressBook.OnClientAgentMessage(event)
		elif event.cmd == 'POST_KEY_RESULTS':
			if self.key_update_required == True and event.args[0] == True and event.args[1] == True and event.args[2] == True and event.args[3] == True:
				self.key_update_required = False
				if os.path.exists(self.key_update_file):
					os.unlink(self.key_update_file)
			self.gui.LoadKeyList()
		elif event.cmd == 'SET_PASSPHRASE_GOOD':
			self.passphraseEntered = True
			if self.keyRotatePending == True:
				self.keyRotatePending = False
				wx.CallAfter(self.OnActionsRotateKey,None)
			if self.newMessagePending == True:
				self.newMessagePending = False
				wx.CallAfter(self.OnNewMessageClick,None)
		elif event.cmd == 'SET_PASSPHRASE_FAIL':
			self.AskForPassphrase()
		elif event.cmd == 'PASSPHRASE_REQUIRED':
			self.AskForPassphrase()
		elif event.cmd == 'NEW_VERSION_CHECK_RESULT':
			self.NewVersionCheckResult(event.args[0],event.args[1])
		elif event.cmd == 'SYNC_BYPASS_TOKEN':
			if self.outgoing_sync != None:
				self.outgoing_sync.addChange( [ 'SyncBypassToken',event.args[0] ] )

	def OnCheckAgentTimer(self,event):
		if self.client_agent_good == True:
			self.client_agent_good = False
		else:
			self.SetStatusText("Agent Down",1)

	def OnActionsFullGet(self,event):
		self.numIncrementalChecks = 0
		self.lastCheckSendDate = None
		self.OnCheckSendClick(event,True)

	def OnActionsCopyMyAddr(self,event):
		if wx.TheClipboard.Open() == True:
			wx.TheClipboard.SetData(wx.TextDataObject(self.gui.from_address))
			wx.TheClipboard.Close()

	def OnActionsNewVersionCheck(self,event):
		self.gui.to_agent_queue.put( [ 'NEW_VERSION_CHECK',True ] )

	def OnActionsViewCerts(self,event):
		showServers = set()
		if self.gui.transport != None and self.gui.transport[0:7] == "server=":
			for s in self.gui.transport[7:].split(","):
				showServers.add(s)
		if self.gui.oldTransport != None and self.gui.oldTransport[0:7] == "server=":
			for s in self.gui.oldTransport[7:].split(","):
				showServers.add(s)
		if self.gui.pubTransport != None and self.gui.pubTransport[0:7] == "server=":
			for s in self.gui.pubTransport[7:].split(","):
				showServers.add(s)
		if self.gui.entangled_server != None and self.gui.entangled_server[0:7] == "server=":
			for s in self.gui.entangled_server[7:].split(","):
				showServers.add(s)
		showServers = list(showServers)
		showServers.sort()
		output = ""
		for s in showServers:
			hasher = hashlib.new('sha1')
			hasher.update(s)
			server_hash = hasher.digest().encode('hex')
			found,cert_desc = self.local_store.retrieve(server_hash)
			if found:
				output += cert_desc + "\n"
			else:
				output += "Certificate for server " + s + " not found\n\n"
		cvf = CertViewFrame(self,output)

	def OnActionsChangePassphrase(self,event):
		if global_config.gnupg_is_v2 == False:
			dlg = wx.PasswordEntryDialog(self,'Enter Old Passphrase','Change Key Passphrase','')
			if dlg.ShowModal() != wx.ID_OK:
				dlg.Destroy()
				return
			old_passphrase = dlg.GetValue()
			dlg.Destroy()
	
			dlg = wx.PasswordEntryDialog(self,'Enter New Passphrase','Change Key Passphrase','')
			if dlg.ShowModal() != wx.ID_OK:
				dlg.Destroy()
				return
			new_passphrase_1 = dlg.GetValue()
			dlg.Destroy()
	
			dlg = wx.PasswordEntryDialog(self,'Confirm New Passphrase','Change Key Passphrase','')
			if dlg.ShowModal() != wx.ID_OK:
				dlg.Destroy()
				return
			new_passphrase_2 = dlg.GetValue()
			dlg.Destroy()
	
			if new_passphrase_1 == '':
				wx.MessageBox("New passphrase cannot be blank","Passphrase change failed",style = wx.ICON_EXCLAMATION)
				return
	
			if new_passphrase_1 != new_passphrase_2:
				wx.MessageBox("Passphrase and confirmation did not match","Passphrase change failed",style = wx.ICON_EXCLAMATION)
				return
		else: # GnuPG v2 prompts on its own
			old_passphrase = 'none'
			new_passphrase_1 = 'none'	
		gnupg_path = global_config.gnupg_path.lstrip('"').rstrip('"') # does not work with quotes
		change_pass = changepass.changepass()
		status,msgtext = change_pass.change_passphrase(
			gnupg_path,
			self.gpg_homedir,
			self.client_keyid_hex,
			old_passphrase,
			new_passphrase_1)

		if status == True:
			wx.MessageBox(msgtext,"Passphrase change successful",style = wx.ICON_EXCLAMATION)
			if global_config.gnupg_is_v2 == False:
				self.gui.to_agent_queue.put( [ 'SET_PASSPHRASE', new_passphrase_1 ] )
				self.passphrase = new_passphrase_1
		else:
			wx.MessageBox(msgtext,"Passphrase change failed",style = wx.ICON_EXCLAMATION)

	def OnActionsDequeueBadMessages(self,event):
		self.dequeue_dialog = dequeue_dialog.DequeueDialogFrame(self,self.GetSize(),self.homedir)
		self.dequeue_dialog.Show()

	def OnActionsThrottleOut(self,event):
		if self.actionsMenu.IsChecked(id_actions_throttle_out) == False: # after
			self.ShowTemporaryStatus("Outbound bandwidth limit removed")
			self.gui.to_agent_queue.put( [ 'THROTTLE_OUTBOUND', None ] )
		else:
			dlg = wx.TextEntryDialog(self,message = "Enter outbound bandwidth limit in kilobytes per second",caption = "Throttle outbound bandwidth")
			if dlg.ShowModal() != wx.ID_OK:
				outboundBandwidthText = None
			else:
				outboundBandwidthText = dlg.GetValue()
			dlg.Destroy()
			outboundBandwidth = None
			if outboundBandwidthText != None and outboundBandwidthText != '':
				try:
					outboundBandwidth = int(outboundBandwidthText)
					if outboundBandwidth <= 0:
						outboundBandwidth = 1
				except ValueError:
					outboundBandwidth = None
					self.ShowTemporaryStatus("Invalid bandwidth value entered")
			if outboundBandwidth == None:
				self.actionsMenu.Check(id_actions_throttle_out,False)
			else:
				self.ShowTemporaryStatus("Outbound bandwidth limited to " + str(outboundBandwidth) + " KB/sec")
				self.gui.to_agent_queue.put( [ 'THROTTLE_OUTBOUND', outboundBandwidth ] )

	def CheckDoSyncFolders(self):
		doSync = False
		try:
			filehandle = open(self.folder_sync_file,'r')
			synctime_str = filehandle.read().rstrip('\r\n')
			filehandle.close()
			synctime = datetime.datetime.strptime(synctime_str,"%Y-%m-%dT%H:%M:%SZ")
			current_datetime = datetime.datetime.utcnow()
			sync_elapsed = current_datetime - synctime
			if sync_elapsed.total_seconds() > self.gui.folderSync:
				doSync = True
		except Exception:
			doSync = True
		if doSync == True:
			self.OnActionsSyncFolders(None)

	def OnActionsSyncFolders(self,event):
		if self.outgoing_sync.checkForSendlog() == False:
			self.outgoing_sync.rotateChangelog()
		self.gui.to_agent_queue.put( [ 'SEND_FOLDER_CHANGES',self.from_address ] )
		filehandle = open(self.folder_sync_file,'w')
		filehandle.write(datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ") + "\n")
		filehandle.close()

	def OnActionsRotateKey(self,event):
		if self.rotateKeyDialog == None:	
			if global_config.gnupg_is_v2 == False and self.passphrase == None:
				self.keyRotatePending = True
				self.AskForPassphrase()
				return
			self.rotateKeyDialog = rotate_key_dialog.RotateKeyFrame(self,global_config.gnupg_path,
				self.homedir,self.client_keyid_hex,self.passphrase,[ int(global_config.resolution_scale_factor*640),int(global_config.resolution_scale_factor*540) ])
			self.rotateKeyDialog.Show()
		else:
			self.rotateKeyDialog.SetFocus()

	def OnHelpHelp(self,event):
		self.helpcon = wx.html.HtmlHelpController(parentWindow = self)
 		wx.FileSystem.AddHandler(wx.ZipFSHandler())
		self.helpcon.AddBook(global_config.help_file,0)
		self.helpcon.DisplayContents()
		self.helpcon.Display("introduction.html")
		if global_config.resolution_scale_factor != 1.0:
			frame = self.helpcon.GetFrame()
			frameX,frameY = frame.GetSize()
			frameX *= global_config.resolution_scale_factor
			frameY *= global_config.resolution_scale_factor
			frame.SetSize( (frameX,frameY) )

	def OnHelpAbout(self,event):
		info = wx.AboutDialogInfo()
		info.Name = "Confidant Mail"
		info.Version = global_config.software_version
		info.Copyright = "GNU Public License"
		info.WebSite = "https://www.confidantmail.org"
		info.Developers = [ "Mike Ingle <mike@confidantmail.org> d2b89e6f95e72e26e0c917d02d1847dfecfcd0c2","inglem@pobox.com" ]
		info.License = "GNU Public License"
		info.Description = "Uses GNU Privacy Guard and Entangled"
		wx.AboutBox(info)

	def OnCheckSendClick(self,event,full_get = False):
		self.CheckUpdateKey()
		if self.checkSendButtonEnabled == True:
			if self.numIncrementalChecks >= global_config.max_incremental_checks:
				self.numIncrementalChecks = 0
				self.lastCheckSendDate = None
			else:
				self.numIncrementalChecks += 1
			self.gui.to_agent_queue.put( [ 'CHECK_SEND',self.lastCheckSendDate,full_get ] )
			self.toolbar.EnableTool(id_check_send_button,False)
			self.checkSendButtonEnabled = False

	def OnCheckSendTimer(self,event):
		self.OnCheckSendClick(event)

	def OnPostKeyClick(self,event):
		self.toolbar.EnableTool(id_post_key_button,False)
		self.post_key_timer.Start(30000,wx.TIMER_ONE_SHOT)
		self.gui.to_agent_queue.put( [ 'POST_KEY', True,True ] )

	def OnPostKeyTimer(self,event):
		self.toolbar.EnableTool(id_post_key_button,True)

	def EnableCheckSend(self,checkSendGood):
		self.toolbar.EnableTool(id_check_send_button,True)
		self.checkSendButtonEnabled = True
		self.StartCheckAckIfDue()
		if checkSendGood == True:
			self.lastCheckSendDate = (datetime.datetime.utcnow() - datetime.timedelta(0,global_config.check_since_overlap)).strftime("%Y-%m-%dT%H:%M:%SZ")
		if self.outgoing_sync != None:
			self.CheckDoSyncFolders()

	def ProcessFolderSyncMessage(self,new_message,headers):
		if self.outgoing_sync == None: # Not in replication mode
			return False # user will see message
		m = re_folder_sync_message.match(headers['SU'])
		if m == None:
			return False
		if self.client_keyid_hex.upper() != m.group(1):
			return False
		if len(headers['RE']) != 1: # expecting one recipient
			return False
		r_t,r_id,r_n = headers['RE'][0]
		if r_id != self.client_keyid:
			return

		sigFilePath = self.local_store.getPath(new_message.encode('hex')) + '.SIG'
		fh = codecs.open(sigFilePath,'r','utf-8')
		sigData = fh.read()
		fh.close()
		sigGotValid = False
		sigKeyMatch = False
		for line in sigData.split('\n'):
			line = line.rstrip('\r\n')
			if line == 'Valid: True':
				sigGotValid = True
			elif line[0:13] == 'Fingerprint: ':
				sigFingerprint = line[13:].lower()
				if sigFingerprint == self.client_keyid_hex:
					sigKeyMatch = True
			elif line[0:19] == 'PubkeyFingerprint: ': # subkey signing case
				pkFingerprint = line[19:].lower()
				if pkFingerprint == self.client_keyid_hex:
					sigKeyMatch = True
		if sigGotValid == False or sigKeyMatch == False:
			return False

		zip_path = self.local_store.getPath(new_message.encode('hex')) + '.ZIP'
		zip = zipfile.ZipFile(zip_path,'r')

		refreshTree = False
		refreshList = False	
		changelog_fh = zip.open('_sendlog.dat','r')
		self.folder_store.disable_sync()
		while True:
			len_buf = changelog_fh.read(4)
			if len(len_buf) < 4:
				break
			record_len, = struct.unpack('I',len_buf)
			record_buf = changelog_fh.read(record_len)
			if len(record_buf) < record_len:
				break
			record = pickle.loads(record_buf)
			if record[0] == 'SaveDraft' or record[0] == 'SendMsg':
				msgkey = record[1].encode('hex').upper()
				msg_fh = zip.open('_' + msgkey)
				msg = msg_fh.read()
				msg_fh.close()
				if record[0] == 'SaveDraft':
					state = 'D'
				else:
					state = 'S'
					try:
						hdr_fh = zip.open('_' + msgkey + '.HDR')
						hdr = hdr_fh.read()
						hdr_fh.close()
						hdr_fh = open(self.local_store.getPath(msgkey) + '.HDR','wb')
						hdr_fh.write(hdr)
						hdr_fh.close()
					except Exception:
						pass
				headers = self.folder_store.extract_outgoing_message_headers(pickle.loads(msg),self.from_address,record[1],state)
				self.local_store.store(msgkey,msg)
				self.folder_store.save_message(record[1],headers)
			elif record[0] == 'AddCat':
				self.folder_store.check_add_folder(record[1])
				refreshTree = True
			elif record[0] == 'DelCat':
				if record[1] in folders.predefined_folders:
					continue
				subfolder_check = record[1] + '\x00'
				subfolder_check_len = len(subfolder_check)
				num_subfolders = 0
				for subfolder in self.folderTree.folders_by_path:
					if subfolder[0:subfolder_check_len] == subfolder_check:
						num_subfolders += 1
				if num_subfolders > 0:
					continue # should not happen
				folder_contents = self.folder_store.get_messages_in_folder(record[1])
				if len(folder_contents) > 0:
					continue
				self.folder_store.delete_folder(record[1])
				refreshTree = True
			elif record[0] == 'RenCat':
				if record[1] in folders.predefined_folders:
					continue
				self.folder_store.rename_folder(record[1],record[2])
				refreshTree = True
			elif record[0] == 'AddMsg':
				if self.folder_store.message_exists(record[2]):
					self.folder_store.put_message_in_folder(record[1],record[2])
					if self.current_folder_path == record[1] or ( self.current_folder_path == folders.id_inbox and record[1] == folders.id_new_messages):
						refreshList = True
			elif record[0] == 'DelMsg':
				if record[1] == folders.id_deleted:
					continue # we do not permanently delete here
				folders_containing = self.folder_store.get_folders_containing_message(record[2])
				if record[1] not in folders_containing:
					continue # should not happen
				if len(folders_containing) == 1: # only in this folder
					self.folder_store.put_message_in_folder(folders.id_deleted,record[2])
				self.folder_store.delete_message_from_folder(record[1],record[2])
				if self.current_folder_path == record[1] or ( self.current_folder_path == folders.id_inbox and record[1] == folders.id_new_messages):
					refreshList = True
			elif record[0] == 'SetColor':
				found,header = self.folder_store.get_message(record[1])
				if found == False:
					continue
				header['CLR'] = record[2]
				self.folder_store.save_message(record[1],header)
				for id in self.messageList.rowMessageIds:
					if record[1] == id:
						refreshList = True
						break
			elif record[0] == 'SyncBypassToken':
				self.gui.to_agent_queue.put( [ 'SYNC_BYPASS_TOKEN', record[1] ] )
		changelog_fh.close()
		self.folder_store.enable_sync()
		self.folder_store.commit()

		if refreshTree == True:
			self.folderTree.LoadTree()
		if refreshList == True:
			self.OpenMailFolder(self.current_folder_path) # refresh

		return True

	def ProcessNewMessages(self,event):
		# Avoid showing new message notification if the only new messages are folder sync messages.
		if len(self.new_messages_to_process) == 0 and self.non_sync_messages_processed > 0:
			if self.newMessageNotification == 'Change Window Title' or self.newMessageNotification == 'Tray Icon and Window Title':
				self.SetTitle('New Messages: ' + self.title)
				self.newMessageNotificationActive = True
			if self.newMessageNotification == 'Show Tray Icon' or self.newMessageNotification == 'Tray Icon and Window Title':
				self.ShowTrayIcon()
				self.newMessageNotificationActive = True
			sortIndex,sortDir = self.messageList.lastSortState
			if sortIndex >= 0:
				self.messageList.SortListItems(sortIndex,sortDir)
			return
		elif len(self.new_messages_to_process) == 0:
			return
		new_message = self.new_messages_to_process[0]
		self.new_messages_to_process = self.new_messages_to_process[1:]
		#DBGOUT#print "processing new message: ",new_message.encode('hex')
		if self.folder_store.message_exists(new_message) == False:
			found,headers = self.folder_store.extract_incoming_message_headers(new_message)
			if found == True:
				is_folder_sync_message = self.ProcessFolderSyncMessage(new_message,headers)
			if found == True and is_folder_sync_message == True:
				self.complete_store.__delitem__(new_message.encode('hex'))
				self.folder_store.delete_all_files_for_message(new_message,force_incoming = True)
			elif found == True:
				#DBGOUT#print found,headers
				self.non_sync_messages_processed += 1
				self.folder_store.save_message(new_message,headers)
				self.folder_store.put_message_in_folder(folders.id_new_messages,new_message,skip_sync = True)
				self.folder_store.put_message_in_folder(folders.id_inbox,new_message,skip_sync = True)
				if self.current_folder_path == folders.id_inbox or self.current_folder_path == folders.id_new_messages:
					headers['NEW'] = True
					self.messageList.InsertRecord(headers)
				self.folder_store.commit()
				self.complete_store.__delitem__(new_message.encode('hex'))
		else:
			self.complete_store.__delitem__(new_message.encode('hex'))
		self.process_new_messages_timer.Start(global_config.process_new_message_interval,wx.TIMER_ONE_SHOT)

	def ProcessNewForwardedOriginal(self,new_message):
		#DBGOUT#print "processing new forwarded original: ",new_message.encode('hex')
		if self.folder_store.message_exists(new_message) == False:
			found,headers = self.folder_store.extract_incoming_message_headers(new_message)
			if found:
				#DBGOUT#print found,headers
				self.folder_store.save_message(new_message,headers)
				self.folder_store.put_message_in_folder(folders.id_forwarded_originals,new_message)
				if self.current_folder_path == folders.id_forwarded_originals:
					self.messageList.InsertRecord(headers)

	def OpenMessageFromAgent(self,messageId):
		self.messageList.OpenMessageById(messageId)

	def ProcessNewDraft(self,headers):
		if self.current_folder_path == folders.id_drafts:
			self.messageList.InsertRecord(headers)

	def ProcessNewSend(self,headers):
		if self.current_folder_path == folders.id_send_pending:
			self.messageList.InsertRecord(headers)

	def ReopenForEdit(self,messageId,pos,size):
		#DBGOUT#print "reopen for edit",messageId
		self.messageList.OpenMessageById(messageId.decode('hex'),reopen=True,pos=pos,size=size)

	def ClearNewMessageNotification(self):
		if self.newMessageNotificationActive == True:
			if self.newMessageNotification == 'Change Window Title' or self.newMessageNotification == 'Tray Icon and Window Title':
				self.SetTitle(self.title)
			if self.newMessageNotification == 'Show Tray Icon' or self.newMessageNotification == 'Tray Icon and Window Title':
				self.RemoveTrayIcon()
			self.newMessageNotificationActive = False

	def ShowTrayIcon(self):
		if self.trayIcon == None:
			self.trayIcon = wx.TaskBarIcon()
			newmail_bmp = images2.newmail.GetBitmap()
			newmail_icon = wx.IconFromBitmap(newmail_bmp)
			self.trayIcon.SetIcon(newmail_icon,"New Mail")
			self.trayIcon.Bind(wx.EVT_TASKBAR_LEFT_DOWN,self.TrayIconClicked)

	def TrayIconClicked(self,event):
		self.RemoveTrayIcon()
		self.Restore()
		
	def RemoveTrayIcon(self):
		if self.trayIcon != None:
			self.trayIcon.Destroy()
			self.trayIcon = None
	
	def OnResizeSplitter(self,event):
		self.folder_store.set_global("SASHPOS",str(self.verticalSplitter.GetSashPosition()))

	def OnClose(self,event):
		self.RemoveTrayIcon()
		self.gui.acceptingEvents = False
		self.Destroy()

class CertViewFrame(wx.Frame):
	def __init__(self,parent,text):
		self.parent = parent
		self.title = "View Certs"
		wx.Frame.__init__(self,self.parent,-1,self.title,size=self.parent.gui.addr_window_size)
		self.mainSizer = wx.BoxSizer(wx.VERTICAL)
		self.textCtrl = wx.TextCtrl(self, style=wx.HSCROLL|wx.TE_MULTILINE|wx.TE_READONLY)
		self.mainSizer.Add(self.textCtrl,1,wx.EXPAND,0)
		self.textCtrl.SetValue(text)
		self.Show()
	
class RunApp(wx.App):
	def __init__(self,gui):
		self.gui = gui
		wx.App.__init__(self, redirect=False)

	def OnInit(self):
		self.frame = MessageListFrame(None,self.gui.from_address + ' - Confidant Mail',self.gui)
		self.frame.SetStatusText("",0)
		self.frame.Show()
		self.SetTopWindow(self.frame)
		return True

if __name__ == "__main__":
	app = RunApp(None,None)
	app.MainLoop()

# EOF
