# Display html help file on a notebook page

import wx
import wx.html

class Apage(wx.html.HtmlHelpWindow):
    helpfile = 'help.zip'
    helpfile = 'help/help.hhp'
    def __init__(self, parent):
        wx.html.HtmlHelpWindow.__init__(self, parent, -1)
        self.helpcontrol = wx.html.HtmlHelpController(style=wx.html.HF_EMBEDDED)
        self.helpcontrol.SetHelpWindow(self)
        wx.FileSystem.AddHandler(wx.ZipFSHandler())     # add the Zip filesystem
        self.helpcontrol.AddBook(self.helpfile, 1)
        self.helpcontrol.DisplayContents()

class Aframe(wx.Frame):
    def __init__(self):
        wx.Frame.__init__(self, None, -1, 'Help viewer', size=(500,500))
        self.v = Apage(parent=self)


if __name__ == '__main__':
    app = wx.PySimpleApp()
    Aframe().Show()
    app.MainLoop() 

