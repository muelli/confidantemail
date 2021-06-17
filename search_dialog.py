import wx

id_search_button = 1
id_cancel_button = 2

class SearchDialogFrame(wx.Frame):

	def __init__(self,parent,title,pos = None,callback = None):
		self.callback = callback
		wx.Frame.__init__(self,parent,-1,title,pos=pos)
		mainPanel = wx.Panel(self,-1,size=self.GetClientSize())
		panelSizer = wx.BoxSizer(wx.VERTICAL)
		panelSizer.Add(mainPanel,1,wx.ALL|wx.GROW,0)

		mainSizer = wx.BoxSizer(wx.VERTICAL)

		hsizer1 = wx.BoxSizer(wx.HORIZONTAL)
		labelSearchText = wx.StaticText(mainPanel,-1,"Search Text")
		hsizer1.Add(labelSearchText,0,wx.ALL,3)
		self.searchText = wx.TextCtrl(mainPanel,-1,"")
		hsizer1.Add(self.searchText,1,wx.ALL|wx.GROW,3)	
		
		hsizer2 = wx.BoxSizer(wx.HORIZONTAL)
		labelSearch = wx.StaticText(mainPanel,-1,"Search ")
		hsizer2.Add(labelSearch,0,wx.ALL,3)
		self.checkboxFrom = wx.CheckBox(mainPanel,-1,'From')
		hsizer2.Add(self.checkboxFrom,0,wx.ALL,3)
		self.checkboxTo = wx.CheckBox(mainPanel,-1,'To')		
		hsizer2.Add(self.checkboxTo,0,wx.ALL,3)
		self.checkboxSubject = wx.CheckBox(mainPanel,-1,'Subject')		
		hsizer2.Add(self.checkboxSubject,0,wx.ALL,3)
		self.checkboxBody = wx.CheckBox(mainPanel,-1,'Body')		
		hsizer2.Add(self.checkboxBody,0,wx.ALL,3)
		self.checkboxFrom.SetValue(True)
		self.checkboxTo.SetValue(True)
		self.checkboxSubject.SetValue(True)
		self.checkboxCase = wx.CheckBox(mainPanel,-1,'Case Sensitive')		
		hsizer2.Add(self.checkboxCase,0,wx.ALL,3)
		self.checkboxRegex = wx.CheckBox(mainPanel,-1,'Regex')		
		hsizer2.Add(self.checkboxRegex,0,wx.ALL,3)
		x,y = self.searchText.GetSize()
		self.searchButton = wx.Button(mainPanel,id_search_button,"Search",size=(-1,y))
		hsizer2.Add(self.searchButton,0,wx.ALL,3)
		self.cancelButton = wx.Button(mainPanel,id_cancel_button,"Close",size=(-1,y))
		hsizer2.Add(self.cancelButton,0,wx.ALL,3)
		self.Bind(wx.EVT_BUTTON,self.OnSearchButton,self.searchButton)
		self.Bind(wx.EVT_BUTTON,self.OnCancelButton,self.cancelButton)
		self.Bind(wx.EVT_CLOSE,self.OnClose)

		mainSizer.Add(hsizer1,0,wx.ALL|wx.GROW,0)
		mainSizer.Add(hsizer2,0,wx.ALL|wx.GROW,0)
		mainPanel.SetSizer(mainSizer)

		self.SetSizer(panelSizer)
		mainSizer.Fit(self)

	def OnSearchButton(self,event):
		if self.callback != None:
			wx.CallAfter(self.callback,self.searchText.GetValue(),self.checkboxFrom.GetValue(),
				self.checkboxTo.GetValue(),self.checkboxSubject.GetValue(),
				self.checkboxBody.GetValue(),self.checkboxCase.GetValue(),
				self.checkboxRegex.GetValue(),False)

	def OnCancelButton(self,event):
		if self.callback != None:
			wx.CallAfter(self.callback,None,None,None,None,None,None,None,True)
		self.callback = None
		self.Destroy()

	def OnClose(self,event):
		if self.callback != None:
			wx.CallAfter(self.callback,None,None,None,None,None,None,None,True)
		self.callback = None
		self.Destroy()

#class RunApp(wx.App):
#	def __init__(self):
#		wx.App.__init__(self)
#
#	def OnInit(self):
#		self.frame = SearchDialogFrame(None,"Search Test",None)
#		self.frame.Show()
#		self.SetTopWindow(self.frame)
#		return True
#
#if __name__ == "__main__":
#	app = RunApp();
#	app.MainLoop()

# EOF
