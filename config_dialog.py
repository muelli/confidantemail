import os
import wx
import time
import sys
import re
import codecs
import urlparse
#import traceback
import socket
import httplib
import datetime
import global_config
import proofofwork
import find_gpg_homedir
import gnupg
import images2

id_save = 1
id_save_open = 2
id_cancel = 3
id_load_defaults = 4
id_help = 5
id_change_gpg_dir = 6
id_paste_url_button = 7
id_get_config_button = 8
id_change_server_button = 9
id_disable_old = 10
id_new_key = 11
id_key_gen_timer = 12
id_setup = 13

poll_old_server_days = 12

re_keyid = re.compile("^(.*) ([0-9A-F]{40})$",re.IGNORECASE)
re_con_timeout = re.compile("^(\d\d*) sec")
re_resolution = re.compile("^([0-9]+)x([0-9]+)$",re.IGNORECASE)
re_blankorwhitespace = re.compile("^\s*$")
re_validate_server_list = re.compile("^[^:]+:\d+",re.IGNORECASE)
re_valid_dirname = re.compile("^[a-z0-9\-_\.]+$",re.IGNORECASE)
re_valid_url = re.compile("^https?://.*|^file://.*")
re_email_addr = re.compile("^(\S+@\S+\.\S+)$")

def SetCB(comboBox,val):
	items = comboBox.GetItems()
	i = 0
	n = -1
	for item in items:
		if val == item:
			n = i
			break
		i += 1
	if n >= 0:
		comboBox.SetSelection(n)

class IdentityPanel(wx.Panel):
	def __init__(self,parent,conf):
		self.conf = conf
		wx.Panel.__init__(self,parent,-1)
		vsizer = wx.BoxSizer(wx.VERTICAL)

		labelHomeDir = wx.StaticText(self,-1,"Home Dir")
		x,y = labelHomeDir.GetSize()
		self.textHomeDir = wx.TextCtrl(self,-1,"")
		self.textHomeDir.SetEditable(False)
		hsizer1 = wx.BoxSizer(wx.HORIZONTAL)
		hsizer1.Add(labelHomeDir,0,wx.ALL,3)
		hsizer1.Add(self.textHomeDir,1,wx.ALL|wx.GROW,3)
		labelGpgDir = wx.StaticText(self,-1,"GPG Dir",size=(x,-1),style=wx.ALIGN_RIGHT)
		self.textGpgDir = wx.TextCtrl(self,-1," ")
		self.textGpgDir.SetEditable(False)
		x2,y2 = self.textGpgDir.GetSize()
		#self.changeGpgDir = wx.Button(self,id_change_gpg_dir,"Change",size = (-1,y2))
		hsizer2 = wx.BoxSizer(wx.HORIZONTAL)
		hsizer2.Add(labelGpgDir,0,wx.ALL,3)
		hsizer2.Add(self.textGpgDir,1,wx.ALL|wx.GROW,3)
		#hsizer2.Add(self.changeGpgDir,0,wx.ALL,3)

		hsizer3 = wx.BoxSizer(wx.HORIZONTAL)
		labelGpgKey = wx.StaticText(self,-1,"GPG Key",size=(x,-1),style=wx.ALIGN_RIGHT)
		if sys.platform == 'darwin':
			self.chooseGpgKey = wx.ComboBox(self,-1,style = wx.CB_DROPDOWN|wx.CB_READONLY)
		else:
			self.chooseGpgKey = wx.ComboBox(self,-1,style = wx.CB_DROPDOWN|wx.CB_READONLY|wx.CB_SORT)
		hsizer3.Add(labelGpgKey,0,wx.ALL,3)
		hsizer3.Add(self.chooseGpgKey,1,wx.ALL|wx.GROW,3)

		hsizer4 = wx.BoxSizer(wx.HORIZONTAL)
		labelConfUrl = wx.StaticText(self,-1,"Remote Config URL",style=wx.ALIGN_RIGHT)
		hsizer4.Add(labelConfUrl,0,wx.ALL,3)
		self.textConfUrl = wx.TextCtrl(self,-1,"")
		hsizer4.Add(self.textConfUrl,1,wx.ALL|wx.GROW,3)
		x,y = self.textConfUrl.GetSize()

		hsizer5 = wx.BoxSizer(wx.HORIZONTAL)
		labelConfUrl2 = wx.StaticText(self,-1,"Remote Config",style=wx.ALIGN_RIGHT)
		hsizer5.Add(labelConfUrl2,0,wx.ALL,3)
		self.pasteUrlButton = wx.Button(self,id_paste_url_button,"Paste URL",size = (-1,y))
		hsizer5.Add(self.pasteUrlButton,0,wx.ALL,3)
		self.getConfigButton = wx.Button(self,id_get_config_button,"Get Config",size = (-1,y))
		hsizer5.Add(self.getConfigButton,0,wx.ALL,3)

		self.Bind(wx.EVT_BUTTON,self.OnPasteUrlButton,self.pasteUrlButton)
		self.Bind(wx.EVT_BUTTON,self.OnGetConfigButton,self.getConfigButton)

		hsizer9 = wx.BoxSizer(wx.HORIZONTAL)
		labelPrevSenderCost = wx.StaticText(self,-1,"Previous Anti-Junk Cost")
		x,y = labelPrevSenderCost.GetSize()
		self.prevChooseSenderCost = wx.ComboBox(self,-1,style = wx.CB_DROPDOWN|wx.CB_READONLY)
		self.prevChooseSenderCost.AppendItems(['Low','Medium','High','Max'])
		hsizer9.Add(labelPrevSenderCost,0,wx.ALL,3)
		hsizer9.Add(self.prevChooseSenderCost,0,wx.ALL,3)
		labelPrevMailslots = wx.StaticText(self,-1,"Previous incoming mailslots")
		x2,y = labelPrevMailslots.GetSize()
		self.prevChooseMailslots = wx.ComboBox(self,-1,style = wx.CB_DROPDOWN|wx.CB_READONLY)
		self.prevChooseMailslots.AppendItems(['2','4','8','16'])
		hsizer9.Add(labelPrevMailslots,0,wx.ALL,3)
		hsizer9.Add(self.prevChooseMailslots,0,wx.ALL,3)

		hsizer8 = wx.BoxSizer(wx.HORIZONTAL)
		labelSenderCost = wx.StaticText(self,-1,"Sender Anti-Junk Cost",size=(x,-1),style=wx.ALIGN_RIGHT)
		self.chooseSenderCost = wx.ComboBox(self,-1,style = wx.CB_DROPDOWN|wx.CB_READONLY)
		self.chooseSenderCost.AppendItems(['Low','Medium','High','Max'])
		self.chooseSenderCost.Bind(wx.EVT_COMBOBOX,self.OnChooseSenderCost)
		hsizer8.Add(labelSenderCost,0,wx.ALL,3)
		hsizer8.Add(self.chooseSenderCost,0,wx.ALL,3)
		labelMailslots = wx.StaticText(self,-1,"Incoming mailslots",size=(x2,-1),style=wx.ALIGN_RIGHT)
		self.chooseMailslots = wx.ComboBox(self,-1,style = wx.CB_DROPDOWN|wx.CB_READONLY)
		self.chooseMailslots.AppendItems(['2','4','8','16'])
		self.chooseMailslots.Bind(wx.EVT_COMBOBOX,self.OnChooseMailslots)
		hsizer8.Add(labelMailslots,0,wx.ALL,3)
		hsizer8.Add(self.chooseMailslots,0,wx.ALL,3)

		hsizer10 = wx.BoxSizer(wx.HORIZONTAL)
		labelOldEnd = wx.StaticText(self,-1,'Accept previous until',size=(x,-1),style=wx.ALIGN_RIGHT)
		self.chooseEndOldCostSlots = wx.GenericDatePickerCtrl(self, 
									   style = wx.TAB_TRAVERSAL | wx.DP_DROPDOWN
									   | wx.DP_SHOWCENTURY | wx.DP_ALLOWNONE )
		labelUseBypassTokens = wx.StaticText(self,-1,'Use bypass tokens')
		self.checkboxUseBypassTokens = wx.CheckBox(self,-1)
		hsizer10.Add(labelOldEnd,0,wx.ALL,3)
		hsizer10.Add(self.chooseEndOldCostSlots,0,wx.ALL,3)
		hsizer10.Add(labelUseBypassTokens,0,wx.ALL,3)
		hsizer10.Add(self.checkboxUseBypassTokens,0,wx.ALL,3)

		hsizer11 = wx.BoxSizer(wx.HORIZONTAL)
		labelPubServerList = wx.StaticText(self,-1,"Optional publish key server",style=wx.ALIGN_RIGHT)
		x,y = labelPubServerList.GetSize()
		self.textPubServerList = wx.TextCtrl(self,-1,"")
		hsizer11.Add(labelPubServerList,0,wx.ALL,3)
		hsizer11.Add(self.textPubServerList,1,wx.ALL|wx.GROW,3)
		hsizer12 = wx.BoxSizer(wx.HORIZONTAL)
		labelPubAuthKey = wx.StaticText(self,-1,"Optional publish key auth",size=(x,-1),style=wx.ALIGN_RIGHT)
		self.textPubAuthKey = wx.TextCtrl(self,-1,"")
		hsizer12.Add(labelPubAuthKey,0,wx.ALL,3)
		hsizer12.Add(self.textPubAuthKey,1,wx.ALL|wx.GROW,3)

		self.messageLine = wx.StaticText(self,-1,"")
		hsizer13 = wx.BoxSizer(wx.HORIZONTAL)
		hsizer13.Add(self.messageLine,1,wx.ALL|wx.GROW,3)

		vsizer.Add(hsizer1,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizer2,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizer3,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizer4,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizer5,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizer8,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizer9,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizer10,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizer11,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizer12,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizer13,0,wx.ALL|wx.GROW,0)
		self.SetSizer(vsizer)
		vsizer.Fit(self)

	def LoadKeys(self,set_keyid = None):
		if set_keyid != None:
			self.keyid = set_keyid
		keys = None
		if len(self.keyid) == 40:
			keyid = self.keyid.decode('hex')
		else:
			keyid = ''
		try:
			gpg = gnupg.GPG(gpgbinary = global_config.gnupg_path,options = global_config.gpg_opts,gnupghome = self.gpgDir)
			gpg.encoding = 'utf-8'
			keys = gpg.list_keys(secret = True)
		except Exception:
			pass
			#DBGOUT#print "unable to get keys"
		self.chooseGpgKey.Clear()
		if keys != None and len(keys) > 0:
			selkey = None
			keylist = [ ]
			for key in keys:
				keytext = key['uids'][0] + ' ' + (key['fingerprint'].lower())
				keylist.append(keytext)
				if key['fingerprint'].decode('hex') == keyid:
					selkey = keytext
				#DBGOUT#print selkey,self.keyid,key['fingerprint']
			self.chooseGpgKey.Clear()
			self.chooseGpgKey.AppendItems(keylist)
			if selkey != None:
				self.chooseGpgKey.SetStringSelection(selkey)
		else:
			self.chooseGpgKey.AppendItems(['No private keys found. Choose a different directory or create a key.'])
			self.chooseGpgKey.Select(0)

	def SetAll(self,conf):
		self.configDir = conf.configDir
		self.gpgDir = conf.gpgDir
		self.keyid = conf.keyid
		self.textHomeDir.SetValue(self.configDir)
		self.textGpgDir.SetValue(self.gpgDir)
		SetCB(self.chooseSenderCost,conf.antiJunkCost)
		SetCB(self.chooseMailslots,conf.incomingMailslots)
		SetCB(self.prevChooseSenderCost,conf.prevAntiJunkCost)
		SetCB(self.prevChooseMailslots,conf.prevIncomingMailslots)
		if conf.pubTransport.lower()[0:7] == 'server=':
			self.textPubServerList.SetValue(conf.pubTransport[7:])
		else:
			self.textPubServerList.SetValue(conf.pubTransport)
		self.textPubAuthKey.SetValue(conf.pubAuthKey)
		try:
			self.chooseEndOldCostSlots.SetValue(conf.endOldCostSlots)
		except ValueError:
			pass
		self.checkboxUseBypassTokens.SetValue(conf.useBypassTokens)
		self.UpdateSenderCostValues()
		self.LoadKeys()

	def GetAll(self,conf):
		self.UpdateSenderCostValues()
		conf.gpgDir = self.textGpgDir.GetValue()
		conf.keyid = self.chooseGpgKey.GetValue()
		conf.emailaddr = ""
		m = re_keyid.match(conf.keyid)
		if m:
			conf.emailaddr = m.group(1)
			conf.keyid = m.group(2)
		conf.antiJunkCost = self.chooseSenderCost.GetValue()
		conf.incomingMailslots = int(self.chooseMailslots.GetValue())
		conf.prevAntiJunkCost = self.prevChooseSenderCost.GetValue()
		conf.prevIncomingMailslots = int(self.prevChooseMailslots.GetValue())
		conf.powNbits = self.powNbits
		conf.powNmatches = self.powNmatches
		conf.prevPowNbits = self.prevPowNbits
		conf.prevPowNmatches = self.prevPowNmatches
		conf.endOldCostSlots = self.chooseEndOldCostSlots.GetValue()
		conf.pubTransport = self.textPubServerList.GetValue()
		conf.pubAuthKey = self.textPubAuthKey.GetValue()
		conf.useBypassTokens = self.checkboxUseBypassTokens.GetValue()
		
	def UpdateSenderCostValues(self):
		senderCost = self.chooseSenderCost.GetValue()
		if senderCost == 'Low':
			self.powNbits = 24
		if senderCost == 'Medium':
			self.powNbits = 32
		if senderCost == 'High':
			self.powNbits = 36
		if senderCost == 'Max':
			self.powNbits = 40
		self.powNmatches = 2

		prevSenderCost = self.prevChooseSenderCost.GetValue()
		if prevSenderCost == 'Low':
			self.prevPowNbits = 24
		if prevSenderCost == 'Medium':
			self.prevPowNbits = 32
		if prevSenderCost == 'High':
			self.prevPowNbits = 36
		if prevSenderCost == 'Max':
			self.prevPowNbits = 40
		self.prevPowNmatches = 2

	def OnChooseSenderCost(self,event):
		self.UpdateSenderCostValues()
		if self.prevPowNbits > self.powNbits or self.prevPowNmatches > self.powNmatches:
			senderCost = self.chooseSenderCost.GetValue()
			SetCB(self.prevChooseSenderCost,senderCost)
			self.UpdateSenderCostValues()
			self.UpdatePrevDate()
		wx.CallAfter(self.UpdateChooseSenderCost)

	def OnChooseMailslots(self,event):
		nMailslots = int(self.chooseMailslots.GetValue())
		prevNMailslots = int(self.prevChooseMailslots.GetValue())
		if nMailslots > prevNMailslots:
			SetCB(self.prevChooseMailslots,self.chooseMailslots.GetValue())
			self.UpdatePrevDate()

	def OnPasteUrlButton(self,event):
		self.textConfUrl.SetValue("")
		self.textConfUrl.Paste()

	def OnGetConfigButton(self,event):
		self.conf.fetchRemoteStatus = self.messageLine
		self.conf.fetchRemoteFinal = self.conf.fetchRemoteConfig4
		self.conf.fetchRemoteFail = None
		self.conf.fetchRemoteConfig(self.textConfUrl.GetValue())

	def UpdatePrevDate(self):
		self.chooseEndOldCostSlots.SetValue(wx.DateTime().SetToCurrent().__add__(wx.DateSpan(days=poll_old_server_days)))

	def UpdateChooseSenderCost(self):
		data = ''
		self.messageLine.SetLabel("Testing proof of work...")
		while len(data) < 256:
			data += str(time.time())
		startTime = time.time()	
		pow = proofofwork.generate_proof_of_work(data,self.powNbits,self.powNmatches)
		endTime = time.time()	
		timeRequired = endTime - startTime
		outstr = "Proof of work took %0.2f seconds" % timeRequired
		self.messageLine.SetLabel(outstr)

class NetworkPanel(wx.Panel):
	def __init__(self,parent,conf):
		wx.Panel.__init__(self,parent,-1)
		vsizer = wx.BoxSizer(wx.VERTICAL)

		hsizerS = wx.BoxSizer(wx.HORIZONTAL)
		labelServerAddr = wx.StaticText(self,-1,"Server list",style=wx.ALIGN_RIGHT)
		self.textServerList = wx.TextCtrl(self,-1,"")
		hsizerS.Add(labelServerAddr,0,wx.ALL,3)
		hsizerS.Add(self.textServerList,1,wx.ALL|wx.GROW,3)
		x,y = labelServerAddr.GetSize()

		hsizerAU = wx.BoxSizer(wx.HORIZONTAL)
		labelAuthKey = wx.StaticText(self,-1,"Auth key",size=(x,-1),style=wx.ALIGN_RIGHT)
		self.textAuthKey = wx.TextCtrl(self,-1,"")
		hsizerAU.Add(labelAuthKey,0,wx.ALL,3)
		hsizerAU.Add(self.textAuthKey,1,wx.ALL|wx.GROW,3)

		hsizerM = wx.BoxSizer(wx.HORIZONTAL)
		labelEmailSource = wx.StaticText(self,-1,"Preferred connection type")
		hsizerM.Add(labelEmailSource,0,wx.ALL,3)
		self.serverConnectionChooser = wx.ComboBox(self,-1,style = wx.CB_DROPDOWN|wx.CB_READONLY)
		self.serverConnectionChooser.AppendItems(['Direct','TOR','I2P'])
		hsizerM.Add(self.serverConnectionChooser,0,wx.ALL,3)
		labelRetrieveFrom = wx.StaticText(self,-1,"Retrieve email from")
		hsizerM.Add(labelRetrieveFrom,0,wx.ALL,3)
		self.chooseRetrieveFrom = wx.ComboBox(self,-1,style = wx.CB_DROPDOWN|wx.CB_READONLY)
		self.chooseRetrieveFrom.AppendItems(['Server','Entangled'])
		x,y = self.chooseRetrieveFrom.GetSize()
		hsizerM.Add(self.chooseRetrieveFrom,0,wx.ALL,3)
		self.changeServerButton = wx.Button(self,id_change_server_button,"Change",size = (-1,y))
		hsizerM.Add(self.changeServerButton,0,wx.ALL,3)
		self.Bind(wx.EVT_BUTTON,self.OnChangeServerButton,self.changeServerButton)

		hsizerOM = wx.BoxSizer(wx.HORIZONTAL)
		self.labelOldMode = wx.StaticText(self,-1,"Also poll previous location")
		self.chooseOldRetrieveFrom = wx.ComboBox(self,-1,style = wx.CB_DROPDOWN|wx.CB_READONLY)
		self.chooseOldRetrieveFrom.AppendItems(['none','Old server list','Entangled'])
		self.labelOldEnd = wx.StaticText(self,-1,'until')
		self.chooseEndPollOldDate = wx.GenericDatePickerCtrl(self, 
									   style = wx.TAB_TRAVERSAL | wx.DP_DROPDOWN
									   | wx.DP_SHOWCENTURY | wx.DP_ALLOWNONE )

		hsizerOM.Add(self.labelOldMode,0,wx.ALL,3)
		hsizerOM.Add(self.chooseOldRetrieveFrom,0,wx.ALL,3)
		hsizerOM.Add(self.labelOldEnd,0,wx.ALL,3)
		hsizerOM.Add(self.chooseEndPollOldDate,0,wx.ALL,3)

		hsizerPM = wx.BoxSizer(wx.HORIZONTAL)
		labelProxyMsgs1 = wx.StaticText(self,-1,'Proxy outgoing')
		hsizerPM.Add(labelProxyMsgs1,0,wx.ALL,3)
		self.checkboxProxyIP = wx.CheckBox(self,-1,'Direct IP')
		hsizerPM.Add(self.checkboxProxyIP,0,wx.ALL,3)
		self.checkboxProxyTOR = wx.CheckBox(self,-1,'TOR')
		hsizerPM.Add(self.checkboxProxyTOR,0,wx.ALL,3)
		self.checkboxProxyI2P = wx.CheckBox(self,-1,'I2P messages through server')
		hsizerPM.Add(self.checkboxProxyI2P,0,wx.ALL,3)

		hsizerEN = wx.BoxSizer(wx.HORIZONTAL)
		labelUseExitNode = wx.StaticText(self,-1,'Send all Direct IP via TOR exit nodes')
		hsizerEN.Add(labelUseExitNode,0,wx.ALL,3)
		self.checkboxUseExitNode = wx.CheckBox(self,-1)
		hsizerEN.Add(self.checkboxUseExitNode,0,wx.ALL,3)
		labelProxyDNS = wx.StaticText(self,-1,'Proxy DNS TXT lookups through server')
		hsizerEN.Add(labelProxyDNS,0,wx.ALL,3)
		self.checkboxProxyDNS = wx.CheckBox(self,-1)
		hsizerEN.Add(self.checkboxProxyDNS,0,wx.ALL,3)

		labelSocksAddr = wx.StaticText(self,-1,"Socks Proxy address",style=wx.ALIGN_RIGHT)
		x,y = labelSocksAddr.GetSize()

		hsizerOS = wx.BoxSizer(wx.HORIZONTAL)
		self.labelOldServerList = wx.StaticText(self,-1,"Old server list",size=(x,-1),style=wx.ALIGN_RIGHT)
		self.textOldServerList = wx.TextCtrl(self,-1,"")
		hsizerOS.Add(self.labelOldServerList,0,wx.ALL,3)
		hsizerOS.Add(self.textOldServerList,1,wx.ALL|wx.GROW,3)

		hsizerOAU = wx.BoxSizer(wx.HORIZONTAL)
		self.labelOldAuthKey = wx.StaticText(self,-1,"Old auth key",size=(x,-1),style=wx.ALIGN_RIGHT)
		self.textOldAuthKey = wx.TextCtrl(self,-1,"")
		hsizerOAU.Add(self.labelOldAuthKey,0,wx.ALL,3)
		hsizerOAU.Add(self.textOldAuthKey,1,wx.ALL|wx.GROW,3)

		hsizerADS = wx.BoxSizer(wx.HORIZONTAL)
		self.labelAltDNSServer = wx.StaticText(self,-1,"Alt DNS TXT server",size=(x,-1),style=wx.ALIGN_RIGHT)
		self.textAltDNSServer = wx.TextCtrl(self,-1,"")
		hsizerADS.Add(self.labelAltDNSServer,0,wx.ALL,3)
		hsizerADS.Add(self.textAltDNSServer,1,wx.ALL|wx.GROW,3)

		hsizerT = wx.BoxSizer(wx.HORIZONTAL)
		labelTorAddr = wx.StaticText(self,-1,"TOR Proxy address",size=(x,-1),style=wx.ALIGN_RIGHT)
		self.textTorAddr = wx.TextCtrl(self,-1,"")
		labelTorPort = wx.StaticText(self,-1,"port")
		self.textTorPort = wx.TextCtrl(self,-1,"",size=(80,-1))
		hsizerT.Add(labelTorAddr,0,wx.ALL,3)
		hsizerT.Add(self.textTorAddr,1,wx.ALL|wx.GROW,3)
		hsizerT.Add(labelTorPort,0,wx.ALL,3)
		hsizerT.Add(self.textTorPort,0,wx.ALL,3)

		hsizerI = wx.BoxSizer(wx.HORIZONTAL)
		labelI2PAddr = wx.StaticText(self,-1,"I2P Proxy address",size=(x,-1),style=wx.ALIGN_RIGHT)
		self.textI2PAddr = wx.TextCtrl(self,-1,"")
		labelI2PPort = wx.StaticText(self,-1,"port")
		self.textI2PPort = wx.TextCtrl(self,-1,"",size=(80,-1))
		hsizerI.Add(labelI2PAddr,0,wx.ALL,3)
		hsizerI.Add(self.textI2PAddr,1,wx.ALL|wx.GROW,3)
		hsizerI.Add(labelI2PPort,0,wx.ALL,3)
		hsizerI.Add(self.textI2PPort,0,wx.ALL,3)

		hsizerSO = wx.BoxSizer(wx.HORIZONTAL)
		self.textSocksAddr = wx.TextCtrl(self,-1,"")
		labelSocksPort = wx.StaticText(self,-1,"port")
		self.textSocksPort = wx.TextCtrl(self,-1,"",size=(80,-1))
		hsizerSO.Add(labelSocksAddr,0,wx.ALL,3)
		hsizerSO.Add(self.textSocksAddr,1,wx.ALL|wx.GROW,3)
		hsizerSO.Add(labelSocksPort,0,wx.ALL,3)
		hsizerSO.Add(self.textSocksPort,0,wx.ALL,3)

		hsizerTO = wx.BoxSizer(wx.HORIZONTAL)
		labelConnectTimeout = wx.StaticText(self,-1,"Connect timeout",size=(x,-1),style=wx.ALIGN_RIGHT)
		self.chooseConnectTimeout = wx.ComboBox(self,-1,style = wx.CB_DROPDOWN|wx.CB_READONLY)
		self.chooseConnectTimeout.AppendItems(['10 sec','15 sec','20 sec','30 sec','45 sec','60 sec','90 sec','120 sec'])
		hsizerTO.Add(labelConnectTimeout,0,wx.ALL,3)
		hsizerTO.Add(self.chooseConnectTimeout,0,wx.ALL,3)

		labelNewMessageCheck = wx.StaticText(self,-1,"New Message Check")
		self.chooseNewMessageCheck = wx.ComboBox(self,-1,style = wx.CB_DROPDOWN|wx.CB_READONLY)
		self.chooseNewMessageCheck.AppendItems(['Manual','Once per hour','Every 30 minutes','Every 15 minutes','Every 10 minutes','Every 5 minutes'])
		hsizerTO.Add(labelNewMessageCheck,0,wx.ALL,3)
		hsizerTO.Add(self.chooseNewMessageCheck,0,wx.ALL,3)

		vsizer.Add(hsizerS,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizerAU,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizerM,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizerOM,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizerPM,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizerEN,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizerOS,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizerOAU,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizerADS,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizerT,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizerI,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizerSO,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizerTO,0,wx.ALL|wx.GROW,0)
		self.SetSizer(vsizer)
		vsizer.Fit(self)

	def SetAll(self,conf):
		try:
			if conf.transport.lower() == 'entangled':
				saddr = conf.entangledServer
				server,addr = saddr.split('=')
				SetCB(self.chooseRetrieveFrom,'Entangled')
			elif conf.transport.lower()[0:7] == 'server=':
				saddr = conf.transport
				server,addr = saddr.split('=')
				SetCB(self.chooseRetrieveFrom,'Server')
			else:
				SetCB(self.chooseRetrieveFrom,'Server')
				addr = ''
			self.textServerList.SetValue(addr)
		except ValueError:
			pass

		try:
			if conf.oldTransport.lower() == 'entangled':
				SetCB(self.chooseOldRetrieveFrom,'Entangled')
			elif conf.oldTransport.lower()[0:7] == 'server=':
				saddr = conf.oldTransport
				server,addr = saddr.split('=')
				SetCB(self.chooseOldRetrieveFrom,'Old server list')
				self.textOldServerList.SetValue(addr)
			else:
				SetCB(self.chooseOldRetrieveFrom,'none')
		except ValueError:
			pass

		try:
			self.chooseEndPollOldDate.SetValue(conf.endPollOldDate)
		except ValueError:
			pass
		self.textAuthKey.SetValue(conf.authKey)
		self.textOldAuthKey.SetValue(conf.oldAuthKey)
		if conf.altDNSServer[0:7].lower() == 'server=':
			self.textAltDNSServer.SetValue(conf.altDNSServer[7:])
		else:
			self.textAltDNSServer.SetValue(conf.altDNSServer)

		try:
			saddr,port = conf.torProxy.rsplit(':',1)
			self.textTorAddr.SetValue(saddr)
			self.textTorPort.SetValue(port)
		except ValueError:
			pass

		try:
			saddr,port = conf.i2pProxy.rsplit(':',1)
			self.textI2PAddr.SetValue(saddr)
			self.textI2PPort.SetValue(port)
		except ValueError:
			pass

		try:
			saddr,port = conf.socksProxy.rsplit(':',1)
			self.textSocksAddr.SetValue(saddr)
			self.textSocksPort.SetValue(port)
		except ValueError:
			pass

		SetCB(self.serverConnectionChooser,conf.serverConnection)
		SetCB(self.chooseConnectTimeout,conf.connectionTimeout)
		SetCB(self.chooseNewMessageCheck,conf.newMessageCheck)

		self.checkboxProxyIP.SetValue(conf.proxyIP)
		self.checkboxProxyTOR.SetValue(conf.proxyTOR)
		self.checkboxProxyI2P.SetValue(conf.proxyI2P)
		self.checkboxUseExitNode.SetValue(conf.useExitNode)
		self.checkboxProxyDNS.SetValue(conf.proxyDNS)
			
	def GetAll(self,conf):
		conf.serverList = self.textServerList.GetValue()
		conf.serverConnection = self.serverConnectionChooser.GetValue()
		conf.chooseRetrieveFrom = self.chooseRetrieveFrom.GetValue()
		conf.endPollOldDate = self.chooseEndPollOldDate.GetValue()
		conf.oldServerList = self.textOldServerList.GetValue()
		conf.chooseOldRetrieveFrom = self.chooseOldRetrieveFrom.GetValue()
		conf.torAddr = self.textTorAddr.GetValue()
		conf.torPort = self.textTorPort.GetValue()
		conf.i2pAddr = self.textI2PAddr.GetValue()
		conf.i2pPort = self.textI2PPort.GetValue()
		conf.socksAddr = self.textSocksAddr.GetValue()
		conf.socksPort = self.textSocksPort.GetValue()
		conf.chooseConnectTimeout = self.chooseConnectTimeout.GetValue()
		conf.newMessageCheck = self.chooseNewMessageCheck.GetValue()
		if conf.serverList.lower()[0:7] == 'server=':
			conf.serverList = conf.serverList[7:]
		if conf.oldServerList.lower()[0:7] == 'server=':
			conf.oldServerList = conf.oldServerList[7:]

		conf.proxyIP = self.checkboxProxyIP.GetValue()
		conf.proxyTOR = self.checkboxProxyTOR.GetValue()
		conf.proxyI2P = self.checkboxProxyI2P.GetValue()
		conf.useExitNode = self.checkboxUseExitNode.GetValue()
		conf.proxyDNS = self.checkboxProxyDNS.GetValue()
		conf.authKey = self.textAuthKey.GetValue()
		conf.oldAuthKey = self.textOldAuthKey.GetValue()
		conf.altDNSServer = self.textAltDNSServer.GetValue()

	def OnChangeServerButton(self,event):
		self.textOldServerList.SetValue(self.textServerList.GetValue())
		self.textServerList.SetValue('')
		self.textOldAuthKey.SetValue(self.textAuthKey.GetValue())
		self.textAuthKey.SetValue('')
		endPollOldDate = wx.DateTime().SetToCurrent().__add__(wx.DateSpan(days=poll_old_server_days))
		self.chooseEndPollOldDate.SetValue(endPollOldDate)
		chooseRetrieveFrom = self.chooseRetrieveFrom.GetValue()
		if chooseRetrieveFrom == 'Server':
			self.chooseOldRetrieveFrom.SetValue('Old server list')
		else:
			self.chooseOldRetrieveFrom.SetValue('Entangled')
			self.chooseRetrieveFrom.SetValue('Server')
		self.changeServerButton.Disable()
		self.textServerList.SetFocus()

		

class UserInterfacePanel(wx.Panel):
	def __init__(self,parent,conf):
		wx.Panel.__init__(self,parent,-1)
		vsizer = wx.BoxSizer(wx.VERTICAL)

		labelAddrSize = wx.StaticText(self,-1,"Address Book Window Size",style=wx.ALIGN_RIGHT)
		x,y = labelAddrSize.GetSize()

		hsizerLS = wx.BoxSizer(wx.HORIZONTAL)
		labelListSize = wx.StaticText(self,-1,"Message List Window Size",size=(x,-1),style=wx.ALIGN_RIGHT)
		self.chooseListSize = wx.ComboBox(self,-1,style=wx.CB_DROPDOWN|wx.CB_READONLY)
		self.chooseListSize.AppendItems(['Small','Medium','Mwide','Portrait','Large','Custom'])
		self.ListSizeX = wx.TextCtrl(self,-1,"",size=(60,-1))
		labelListSizeSep = wx.StaticText(self,-1," x ")
		self.ListSizeY = wx.TextCtrl(self,-1,"",size=(60,-1))
		hsizerLS.Add(labelListSize,0,wx.ALL,3)
		hsizerLS.Add(self.chooseListSize,0,wx.ALL,3)
		hsizerLS.Add(self.ListSizeX,0,wx.ALL,3)
		hsizerLS.Add(labelListSizeSep,0,wx.ALL,3)
		hsizerLS.Add(self.ListSizeY,0,wx.ALL,3)
		self.chooseListSize.Bind(wx.EVT_COMBOBOX,self.OnChooseListSize)

		hsizerVS = wx.BoxSizer(wx.HORIZONTAL)
		labelViewSize = wx.StaticText(self,-1,"View Window Size",size=(x,-1),style=wx.ALIGN_RIGHT)
		self.chooseViewSize = wx.ComboBox(self,-1,style=wx.CB_DROPDOWN|wx.CB_READONLY)
		self.chooseViewSize.AppendItems(['Small','Medium','Portrait','Large','Custom'])
		self.ViewSizeX = wx.TextCtrl(self,-1,"",size=(60,-1))
		labelViewSizeSep = wx.StaticText(self,-1," x ")
		self.ViewSizeY = wx.TextCtrl(self,-1,"",size=(60,-1))
		hsizerVS.Add(labelViewSize,0,wx.ALL,3)
		hsizerVS.Add(self.chooseViewSize,0,wx.ALL,3)
		hsizerVS.Add(self.ViewSizeX,0,wx.ALL,3)
		hsizerVS.Add(labelViewSizeSep,0,wx.ALL,3)
		hsizerVS.Add(self.ViewSizeY,0,wx.ALL,3)
		self.chooseViewSize.Bind(wx.EVT_COMBOBOX,self.OnChooseViewSize)

		hsizerES = wx.BoxSizer(wx.HORIZONTAL)
		labelEditSize = wx.StaticText(self,-1,"Edit Window Size",size=(x,-1),style=wx.ALIGN_RIGHT)
		self.chooseEditSize = wx.ComboBox(self,-1,style=wx.CB_DROPDOWN|wx.CB_READONLY)
		self.chooseEditSize.AppendItems(['Small','Medium','Mwide','Portrait','Large','Custom'])
		self.EditSizeX = wx.TextCtrl(self,-1,"",size=(60,-1))
		labelEditSizeSep = wx.StaticText(self,-1," x ")
		self.EditSizeY = wx.TextCtrl(self,-1,"",size=(60,-1))
		hsizerES.Add(labelEditSize,0,wx.ALL,3)
		hsizerES.Add(self.chooseEditSize,0,wx.ALL,3)
		hsizerES.Add(self.EditSizeX,0,wx.ALL,3)
		hsizerES.Add(labelEditSizeSep,0,wx.ALL,3)
		hsizerES.Add(self.EditSizeY,0,wx.ALL,3)
		self.chooseEditSize.Bind(wx.EVT_COMBOBOX,self.OnChooseEditSize)

		hsizerAS = wx.BoxSizer(wx.HORIZONTAL)
		self.chooseAddrSize = wx.ComboBox(self,-1,style=wx.CB_DROPDOWN|wx.CB_READONLY)
		self.chooseAddrSize.AppendItems(['Small','Medium','Portrait','Large','Custom'])
		self.AddrSizeX = wx.TextCtrl(self,-1,"",size=(60,-1))
		labelAddrSizeSep = wx.StaticText(self,-1," x ")
		self.AddrSizeY = wx.TextCtrl(self,-1,"",size=(60,-1))
		hsizerAS.Add(labelAddrSize,0,wx.ALL,3)
		hsizerAS.Add(self.chooseAddrSize,0,wx.ALL,3)
		hsizerAS.Add(self.AddrSizeX,0,wx.ALL,3)
		hsizerAS.Add(labelAddrSizeSep,0,wx.ALL,3)
		hsizerAS.Add(self.AddrSizeY,0,wx.ALL,3)
		self.chooseAddrSize.Bind(wx.EVT_COMBOBOX,self.OnChooseAddrSize)

		hsizerSF = wx.BoxSizer(wx.HORIZONTAL)
		labelScaleFactor = wx.StaticText(self,-1,"Editor Scale Factor",size=(x,-1),style=wx.ALIGN_RIGHT)
		hsizerSF.Add(labelScaleFactor,0,wx.ALL,3)
		self.editorScaleFactor = wx.TextCtrl(self,-1,"",size=(60,-1))
		hsizerSF.Add(self.editorScaleFactor,0,wx.ALL,3)

		hsizerNM = wx.BoxSizer(wx.HORIZONTAL)
		labelNewMessage = wx.StaticText(self,-1,"New Message Notification",size=(x,-1),style=wx.ALIGN_RIGHT)
		self.chooseNewMessage = wx.ComboBox(self,-1,style=wx.CB_DROPDOWN|wx.CB_READONLY)
		self.chooseNewMessage.AppendItems(['None','Change Window Title','Show Tray Icon','Tray Icon and Window Title'])
		hsizerNM.Add(labelNewMessage,0,wx.ALL,3)
		hsizerNM.Add(self.chooseNewMessage,0,wx.ALL,3)

		hsizerFO = wx.BoxSizer(wx.HORIZONTAL)
		labelFieldOrder = wx.StaticText(self,-1,"Field Order",size=(x,-1),style=wx.ALIGN_RIGHT)
		self.chooseFieldOrder = wx.ComboBox(self,-1,style=wx.CB_DROPDOWN|wx.CB_READONLY)
		self.chooseFieldOrder.AppendItems( [ 'From Date Subject To', 'From Date To Subject',
  											 'From Subject Date To', 'From Subject To Date',
  											 'From To Date Subject', 'From To Subject Date',
  											 'Subject Date From To', 'Subject Date To From',
  											 'Subject From Date To', 'Subject From To Date',
  											 'Subject To Date From', 'Subject To From Date',
  											 'Date From Subject To', 'Date From To Subject',
  											 'Date Subject From To', 'Date Subject To From',
  											 'Date To From Subject', 'Date To Subject From',
  											 'To Date From Subject', 'To Date Subject From',
  											 'To From Date Subject', 'To From Subject Date',
  											 'To Subject Date From', 'To Subject From Date' ] )
		hsizerFO.Add(labelFieldOrder,0,wx.ALL,3)
		hsizerFO.Add(self.chooseFieldOrder,0,wx.ALL,3)

		hsizerSS = wx.BoxSizer(wx.HORIZONTAL)
		labelSaveSize = wx.StaticText(self,-1,"Save Field Widths",size=(x,-1),style=wx.ALIGN_RIGHT)
		self.chooseSaveSize = wx.ComboBox(self,-1,style=wx.CB_DROPDOWN|wx.CB_READONLY)
		self.chooseSaveSize.AppendItems( [ 'Off', 'Global','Incoming/Outgoing','Per Category' ] )
		hsizerSS.Add(labelSaveSize,0,wx.ALL,3)
		hsizerSS.Add(self.chooseSaveSize,0,wx.ALL,3)

		hsizerLA = wx.BoxSizer(wx.HORIZONTAL)
		labelSpellcheckLanguage = wx.StaticText(self,-1,"Spellcheck Language",size=(x,-1),style=wx.ALIGN_RIGHT)
		self.spellcheckLanguage = wx.ComboBox(self,-1,style=wx.CB_DROPDOWN|wx.CB_READONLY)
		self.spellcheckLanguage.AppendItems(['de_DE','en_AU','en_GB','en_US','fr_FR'])
		hsizerLA.Add(labelSpellcheckLanguage,0,wx.ALL,3)
		hsizerLA.Add(self.spellcheckLanguage,0,wx.ALL,3)

		hsizerFS = wx.BoxSizer(wx.HORIZONTAL)
		labelFolderSync = wx.StaticText(self,-1,"Sync Multiple Clients",size=(x,-1),style=wx.ALIGN_RIGHT)
		self.chooseFolderSync = wx.ComboBox(self,-1,style = wx.CB_DROPDOWN|wx.CB_READONLY)
		self.chooseFolderSync.AppendItems(['Off','Once per hour','Every 30 minutes','Every 15 minutes','Every 10 minutes','Every 5 minutes'])
		hsizerFS.Add(labelFolderSync,0,wx.ALL,3)
		hsizerFS.Add(self.chooseFolderSync,0,wx.ALL,3)

		hsizerCR = wx.BoxSizer(wx.HORIZONTAL)
		labelCloseOnReply = wx.StaticText(self,-1,"Close On Reply/Forward Message",size=(x,-1),style=wx.ALIGN_RIGHT)
		self.checkboxCloseOnReply = wx.CheckBox(self,-1,"Close original window")
		hsizerCR.Add(labelCloseOnReply,0,wx.ALL,3)
		hsizerCR.Add(self.checkboxCloseOnReply,0,wx.ALL,3)

		hsizerNV = wx.BoxSizer(wx.HORIZONTAL)
		labelNewVersionCheck = wx.StaticText(self,-1,"New Version Notification",size=(x,-1),style=wx.ALIGN_RIGHT)
		self.checkboxNewVersionCheck = wx.CheckBox(self,-1,"Check at program start")
		hsizerNV.Add(labelNewVersionCheck,0,wx.ALL,3)
		hsizerNV.Add(self.checkboxNewVersionCheck,0,wx.ALL,3)

		vsizer.Add(hsizerLS,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizerVS,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizerES,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizerAS,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizerSF,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizerNM,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizerFO,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizerSS,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizerLA,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizerFS,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizerCR,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizerNV,0,wx.ALL|wx.GROW,0)
		self.SetSizer(vsizer)
		vsizer.Fit(self)

	def SetAll(self,conf):
		
		m = re_resolution.match(conf.listWindowSize)
		if m:
			self.ListSizeX.SetValue(m.group(1))	
			self.ListSizeY.SetValue(m.group(2))	
			self.GetResolution(self.chooseListSize,self.ListSizeX,self.ListSizeY)

		m = re_resolution.match(conf.viewWindowSize)
		if m:
			self.ViewSizeX.SetValue(m.group(1))	
			self.ViewSizeY.SetValue(m.group(2))	
			self.GetResolution(self.chooseViewSize,self.ViewSizeX,self.ViewSizeY)

		m = re_resolution.match(conf.editWindowSize)
		if m:
			self.EditSizeX.SetValue(m.group(1))	
			self.EditSizeY.SetValue(m.group(2))	
			self.GetResolution(self.chooseEditSize,self.EditSizeX,self.EditSizeY)

		m = re_resolution.match(conf.addrWindowSize)
		if m:
			self.AddrSizeX.SetValue(m.group(1))	
			self.AddrSizeY.SetValue(m.group(2))	
			self.GetResolution(self.chooseAddrSize,self.AddrSizeX,self.AddrSizeY)

		SetCB(self.chooseNewMessage,conf.newMessageNotification)
		SetCB(self.chooseFieldOrder,conf.fieldOrder)
		SetCB(self.chooseSaveSize,conf.saveFieldSizes)
		self.checkboxCloseOnReply.SetValue(conf.closeOnReply)
		self.checkboxNewVersionCheck.SetValue(conf.newVersionCheck)
		SetCB(self.spellcheckLanguage,conf.spellcheckLanguage)
		SetCB(self.chooseFolderSync,conf.folderSync)
		self.editorScaleFactor.SetValue(conf.editorScaleFactor)

	def GetResolution(self,chooser,x,y):
		xv = x.GetValue()
		yv = y.GetValue()
		if xv == '640' and yv == '480':
			SetCB(chooser,'Small')
		elif xv == '800' and yv == '600':
			SetCB(chooser,'Medium')
		elif xv == '960' and yv == '600':
			SetCB(chooser,'Mwide')
		elif xv == '600' and yv == '800':
			SetCB(chooser,'Portrait')
		elif xv == '1024' and yv == '768':
			SetCB(chooser,'Large')
		else:
			SetCB(chooser,'Custom')

	def SetResolution(self,chooser,x,y):
		val = chooser.GetValue()
		if val == 'Small':
			x.SetValue('640')
			y.SetValue('480')
		elif val == 'Medium':
			x.SetValue('800')
			y.SetValue('600')
		elif val == 'Mwide':
			x.SetValue('960')
			y.SetValue('600')
		elif val == 'Portrait':
			x.SetValue('600')
			y.SetValue('800')
		elif val == 'Large':
			x.SetValue('1024')
			y.SetValue('768')
		elif val == 'Custom':
			pass

	def GetAll(self,conf):
		conf.AddrSizeY = self.AddrSizeY.GetValue()
		conf.AddrSizeX = self.AddrSizeX.GetValue()
		conf.EditSizeY = self.EditSizeY.GetValue()
		conf.EditSizeX = self.EditSizeX.GetValue()
		conf.ViewSizeY = self.ViewSizeY.GetValue()
		conf.ViewSizeX = self.ViewSizeX.GetValue()
		conf.ListSizeY = self.ListSizeY.GetValue()
		conf.ListSizeX = self.ListSizeX.GetValue()
		conf.newMessageNotification = self.chooseNewMessage.GetValue()
		conf.fieldOrder = self.chooseFieldOrder.GetValue()
		conf.saveFieldSizes = self.chooseSaveSize.GetValue()
		conf.closeOnReply = self.checkboxCloseOnReply.GetValue()
		conf.newVersionCheck = self.checkboxNewVersionCheck.GetValue()
		conf.spellcheckLanguage = self.spellcheckLanguage.GetValue()
		conf.folderSync = self.chooseFolderSync.GetValue()
		conf.editorScaleFactor = self.editorScaleFactor.GetValue()

	def OnChooseListSize(self,event):
		self.SetResolution(self.chooseListSize,self.ListSizeX,self.ListSizeY)

	def OnChooseViewSize(self,event):
		self.SetResolution(self.chooseViewSize,self.ViewSizeX,self.ViewSizeY)

	def OnChooseEditSize(self,event):
		self.SetResolution(self.chooseEditSize,self.EditSizeX,self.EditSizeY)

	def OnChooseAddrSize(self,event):
		self.SetResolution(self.chooseAddrSize,self.AddrSizeX,self.AddrSizeY)

class KeyGenerationPanel(wx.Panel):
	def __init__(self,parent,conf):
		self.conf = conf
		wx.Panel.__init__(self,parent,-1)
		vsizer = wx.BoxSizer(wx.VERTICAL)

		labelNewKeyPassphrase2 = wx.StaticText(self,-1,"Repeat passphrase",style=wx.ALIGN_RIGHT)
		x,y = labelNewKeyPassphrase2.GetSize()
		hsizer4 = wx.BoxSizer(wx.HORIZONTAL)
		labelNewKeyName = wx.StaticText(self,-1,"New Key Name",size=(x,-1),style=wx.ALIGN_RIGHT)
		self.textNewKeyName = wx.TextCtrl(self,-1,"")
		hsizer4.Add(labelNewKeyName,0,wx.ALL,3)
		hsizer4.Add(self.textNewKeyName,1,wx.ALL|wx.GROW,3)
		hsizer5 = wx.BoxSizer(wx.HORIZONTAL)
		labelNewKeyEmail = wx.StaticText(self,-1,"Email Address",size=(x,-1),style=wx.ALIGN_RIGHT)
		self.textNewKeyEmail = wx.TextCtrl(self,-1,"")
		hsizer5.Add(labelNewKeyEmail,0,wx.ALL,3)
		hsizer5.Add(self.textNewKeyEmail,1,wx.ALL|wx.GROW,3)
		hsizer6 = wx.BoxSizer(wx.HORIZONTAL)
		labelNewKeyComment = wx.StaticText(self,-1,"Key Comment",size=(x,-1),style=wx.ALIGN_RIGHT)
		self.textNewKeyComment = wx.TextCtrl(self,-1,"")
		hsizer6.Add(labelNewKeyComment,0,wx.ALL,3)
		hsizer6.Add(self.textNewKeyComment,1,wx.ALL|wx.GROW,3)

		hsizer7 = wx.BoxSizer(wx.HORIZONTAL)
		labelNewKeyPassphrase1 = wx.StaticText(self,-1,"Passphrase",size=(x,-1),style=wx.ALIGN_RIGHT)
		self.textNewKeyPassphrase1 = wx.TextCtrl(self,-1,"")
		if global_config.gnupg_is_v2 == True:
			self.textNewKeyPassphrase1.SetValue("Using GnuPG version 2")
			self.textNewKeyPassphrase1.Disable()
		hsizer7.Add(labelNewKeyPassphrase1,0,wx.ALL,3)
		hsizer7.Add(self.textNewKeyPassphrase1,1,wx.ALL|wx.GROW,3)

		hsizer8 = wx.BoxSizer(wx.HORIZONTAL)
		self.textNewKeyPassphrase2 = wx.TextCtrl(self,-1,"")
		if global_config.gnupg_is_v2 == True:
			self.textNewKeyPassphrase2.SetValue("Passphrase prompt will pop up.")
			self.textNewKeyPassphrase2.Disable()
		hsizer8.Add(labelNewKeyPassphrase2,0,wx.ALL,3)
		hsizer8.Add(self.textNewKeyPassphrase2,1,wx.ALL|wx.GROW,3)

		hsizer9 = wx.BoxSizer(wx.HORIZONTAL)
		labelNewKeyType = wx.StaticText(self,-1,"Type",size=(x,-1),style=wx.ALIGN_RIGHT)
		self.chooseNewKeyType = wx.ComboBox(self,-1,style = wx.CB_DROPDOWN|wx.CB_READONLY)
		if global_config.gnupg_is_v2 == True:
			self.chooseNewKeyType.AppendItems(['RSA','ECC','DSA/ELG'])
		else:
			self.chooseNewKeyType.AppendItems(['RSA','DSA/ELG'])
		self.chooseNewKeyType.Select(0)
		labelNewKeyBits = wx.StaticText(self,-1,"Bits")
		if sys.platform == 'darwin':
			self.chooseNewKeyBits = wx.ComboBox(self,-1,style = wx.CB_DROPDOWN|wx.CB_READONLY)
		else:
			self.chooseNewKeyBits = wx.ComboBox(self,-1,style = wx.CB_DROPDOWN|wx.CB_READONLY|wx.CB_SORT)
		if global_config.gnupg_is_v2 == True:
			self.chooseNewKeyBits.AppendItems(['1024','2048','3072','4096',
				"ECC NIST P-256","ECC NIST P-384","ECC NIST P-521",
				"ECC Brainpool P-256","ECC Brainpool P-384","ECC Brainpool P-512",
				"ECC Curve25519","ECC secp256k1" ])
		else:
			self.chooseNewKeyBits.AppendItems(['1024','2048','3072','4096'])
		self.chooseNewKeyBits.Select(2)

		x,y = self.textNewKeyName.GetSize()
		self.buttonNewKey = wx.Button(self,id_new_key,"Create",size = (-1,y))
		self.Bind(wx.EVT_COMBOBOX,self.OnChooseKeyType,self.chooseNewKeyType)
		self.Bind(wx.EVT_BUTTON,self.OnCreateKey,self.buttonNewKey)
		hsizer9.Add(labelNewKeyType,0,wx.ALL,3)
		hsizer9.Add(self.chooseNewKeyType,0,wx.ALL,3)
		hsizer9.Add(labelNewKeyBits,0,wx.ALL,3)
		hsizer9.Add(self.chooseNewKeyBits,0,wx.ALL,3)
		hsizer9.Add(self.buttonNewKey,0,wx.ALL,3)

		self.textErrorMessage = wx.StaticText(self,-1," ")	
		hsizer10 = wx.BoxSizer(wx.HORIZONTAL)
		hsizer10.Add(self.textErrorMessage,0,wx.ALL,3)

		vsizer.Add(hsizer4,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizer5,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizer6,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizer7,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizer8,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizer9,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizer10,0,wx.ALL|wx.GROW,0)
		self.SetSizer(vsizer)
		vsizer.Fit(self)

	def OnCreateKey(self,event):
		if sys.platform[0:5] == 'linux':
			self.textErrorMessage.SetLabel("Generating key, may take minutes...")
		else:
			self.textErrorMessage.SetLabel("Generating key...")
		self.tempKeygenTimer = wx.Timer(self,id = id_key_gen_timer)
		self.Bind(wx.EVT_TIMER,self.StartKeyGeneration,id = id_key_gen_timer)
		self.tempKeygenTimer.Start(100,wx.TIMER_ONE_SHOT)
		# timer was required to get message to display

	def OnChooseKeyType(self,event):
		keytype = self.chooseNewKeyType.GetValue()
		if keytype == 'ECC':
			self.textErrorMessage.SetLabel("Warning: ECC keys cannot communicate with GPG 1.4 users!")
		else:
			self.textErrorMessage.SetLabel(" ")

	def StartKeyGeneration(self,event):
		username = self.textNewKeyName.GetValue()
		email = self.textNewKeyEmail.GetValue()
		comment = self.textNewKeyComment.GetValue()
		passphrase1 = self.textNewKeyPassphrase1.GetValue()
		passphrase2 = self.textNewKeyPassphrase2.GetValue()
		keytype = self.chooseNewKeyType.GetValue()
		keybits = self.chooseNewKeyBits.GetValue()
		#DBGOUT#print "create key"
		#DBGOUT#print "u:  ",username
		#DBGOUT#print "e:  ",email
		#DBGOUT#print "c:  ",comment
		#DBGOUT#print "p1: ",passphrase1
		#DBGOUT#print "p2: ",passphrase2
		#DBGOUT#print "t:  ",keytype
		#DBGOUT#print "b:  ",keybits

		fault = None
		if re_blankorwhitespace.match(username):
			fault = "Username is missing"
			self.textNewKeyName.SetFocus()
		elif re_blankorwhitespace.match(email):
			fault = "Email is missing"
			self.textNewKeyEmail.SetFocus()
		elif re_email_addr.match(email) == None:
			fault = "Email is invalid, enter user@host.domain"
			self.textNewKeyEmail.SetFocus()
		elif re_blankorwhitespace.match(passphrase1):
			fault = "Passphrase is missing"
			self.textNewKeyPassphrase1.SetFocus()
		elif global_config.gnupg_is_v2 == False and passphrase1 != passphrase2:
			fault = "Passphrase mismatch"
			self.textNewKeyPassphrase2.SetFocus()
		elif keytype[0:3] != 'ECC' and keybits[0:3] == 'ECC':
			fault = 'This key type requires a 1024 bit or larger key'
			self.chooseNewKeyBits.SetFocus()
		elif keytype[0:3] == 'ECC' and keybits[0:3] != 'ECC':
			fault = 'Please select an ECC curve for ECC keys'
			self.chooseNewKeyBits.SetFocus()

		if fault != None:
			self.textErrorMessage.SetLabel(fault)
			return

		if global_config.gnupg_is_v2 == True:
			passphrase1 = '' # make it ask
		self.conf.DoKeyGeneration(username,email,comment,passphrase1,keytype,keybits)

	def CreateKeyError(self,errmsg):
		self.textErrorMessage.SetLabel(errmsg)

class ConfigDialogFrame(wx.Frame):

	def __init__(self,parent,size,configDir,pos=None,app = None):
		self.app = app
		title = 'Configuration'
		if pos == None:
			wx.Frame.__init__(self,parent,-1,title,size=size)
		else:
			wx.Frame.__init__(self,parent,-1,title,pos=pos,size=size)
		self.configDir = configDir	
		self.configFile = configDir + os.sep + "config.txt"
		self.keyUpdateFile = configDir + os.sep + "key_update_flag"

		underPanel = wx.Panel(self,-1,size=self.GetClientSize())
		underSizer = wx.BoxSizer(wx.VERTICAL)
		underSizer.Add(underPanel,1,wx.ALL|wx.GROW,0)

		self.notebook = wx.Notebook(underPanel,-1,size=self.GetClientSize(),style=wx.BK_DEFAULT)
		self.identityPanel = IdentityPanel(self.notebook,self)
		self.notebook.AddPage(self.identityPanel,'Identity')
		self.networkPanel = NetworkPanel(self.notebook,self)
		self.notebook.AddPage(self.networkPanel,'Network')
		self.userInterfacePanel = UserInterfacePanel(self.notebook,self)
		self.notebook.AddPage(self.userInterfacePanel,'User Interface')
		self.keyGenerationPanel = KeyGenerationPanel(self.notebook,self)
		self.notebook.AddPage(self.keyGenerationPanel,'Key Generation')

		keyicon_bmp = images2.key_icon.GetBitmap()
		keyicon = wx.IconFromBitmap(keyicon_bmp)
		self.SetIcon(keyicon)

		mainSizer = wx.BoxSizer(wx.VERTICAL)
		mainSizer.Add(self.notebook,1,wx.EXPAND|wx.ALL,1)
		hsizer = wx.BoxSizer(wx.HORIZONTAL)
		saveButton = wx.Button(underPanel,id_save,"Save")
		saveOpenButton = wx.Button(underPanel,id_save_open,"Save and Open")
		cancelButton = wx.Button(underPanel,id_cancel,"Cancel")
		defaultsButton = wx.Button(underPanel,id_load_defaults,"Load Defaults")
		helpButton = wx.Button(underPanel,id_help,"Help")
		hsizer.Add(saveButton,0,wx.ALL,5)
		hsizer.Add(saveOpenButton,0,wx.ALL,5)
		hsizer.Add(cancelButton,0,wx.ALL,5)
		hsizer.Add(defaultsButton,0,wx.ALL,5)
		hsizer.Add(helpButton,0,wx.ALL,5)
		mainSizer.Add(hsizer,0,wx.ALIGN_CENTER_HORIZONTAL)
		underPanel.SetSizer(mainSizer)
		self.SetSizer(underSizer)
		if sys.platform == 'darwin':
			hsizer.Layout()
			underSizer.Layout()
		self.Bind(wx.EVT_BUTTON,self.OnLoadDefaults,defaultsButton)
		self.Bind(wx.EVT_BUTTON,self.OnSave,saveButton)
		self.Bind(wx.EVT_BUTTON,self.OnSaveOpen,saveOpenButton)
		self.Bind(wx.EVT_BUTTON,self.OnCancel,cancelButton)
		self.Bind(wx.EVT_BUTTON,self.OnHelp,helpButton)

		self.LoadDefaults()
		self.LoadFromFile()
		self.PostLoadFixup()
		self.UpdatePanes()

	def UpdateAll(self):
		pass
	
	def OnLoadDefaults(self,event):
		self.LoadDefaults()
		self.PostLoadFixup()
		self.UpdatePanes()

	def LoadDefaults(self):
		self.gpgDir = self.configDir + os.sep + "gpg"
		self.antiJunkCost = 'Low'
		self.incomingMailslots = '4'
		self.powNbits = 24
		self.powNmatches = 2
		self.prevAntiJunkCost = ''
		self.prevIncomingMailslots = ''
		self.keyid = 'None'
		self.transport = ''
		self.oldTransport = ''
		self.entangledServer = ''
		self.serverList = ''
		self.authKey = ''
		self.serverConnection = 'Direct'
		self.nowDate = wx.DateTime().SetToCurrent()
		self.endPollOldDate = wx.DateTime().SetToCurrent().__add__(wx.DateSpan(days=poll_old_server_days))
		self.endOldCostSlots = wx.DateTime().SetToCurrent().__add__(wx.DateSpan(days=poll_old_server_days))
		self.useBypassTokens = True
		self.oldRetrieveFrom = 'none'
		self.oldServerList = ''
		self.oldAuthKey = ''
		self.altDNSServer = ''
		self.pubTransport = ''
		self.pubAuthKey = ''
		self.connectionTimeout = '15 sec'
		self.newMessageCheck = 'Manual'
		if sys.platform != 'win32' and sys.platform != 'darwin':
			self.listWindowSize = '960x600' # keep check/send on screen in Linux
			self.editWindowSize = '960x600'
		else:
			self.listWindowSize = '800x600'
			self.editWindowSize = '800x600'
		self.viewWindowSize = '800x600'
		self.addrWindowSize = '800x600'
		self.editorScaleFactor = '1.00'
		self.newMessageNotification = 'Change Window Title'
 		self.fieldOrder = 'From Subject Date To'
		self.saveFieldSizes = 'Incoming/Outgoing'
		self.spellcheckLanguage = 'en_US'
		self.closeOnReply = False
		self.newVersionCheck = True
		self.torProxy = ''
		self.torAddr = ''
		self.torPort = ''
		self.i2pProxy = ''
		self.i2pAddr = ''
		self.i2pPort = ''
		self.socksProxy = ''
		self.socksAddr = ''
		self.socksPort = ''
		self.proxyIP = False
		self.proxyTOR = False
		self.proxyI2P = False
		self.useExitNode = False
		self.proxyDNS = False
		self.folderSync = 'Off'

	def PostLoadFixup(self):
		if self.prevAntiJunkCost == '':
			self.prevAntiJunkCost = self.antiJunkCost
			self.prevPowNbits = self.powNbits
			self.prevPowNmatches = self.powNmatches
		if self.prevIncomingMailslots == '':
			self.prevIncomingMailslots = self.incomingMailslots
		
	def UpdatePanes(self):
		self.identityPanel.SetAll(self)
		self.networkPanel.SetAll(self)
		self.userInterfacePanel.SetAll(self)
	
	def SenderCostToName(self,cost):
		cost = int(cost)
		cost = int(cost)
		if cost >= 40:
			return 'Max'
		elif cost >= 36:
			return 'High'
		elif cost >= 32:
			return 'Medium'
		else:
			return 'Low'

	def LoadFromFile(self,netConfig = None):
		newMessageCheckNum = 0
		folderSyncNum = 0
		if netConfig == None:
			try:
				fh = codecs.open(self.configFile,'r','utf-8')
				configData = fh.read()
				fh.close()
			except Exception:
				return
		else:
			configData = netConfig
		for line in configData.split('\n'):
			line = line.rstrip('\r\n')
			lineL = line.lower()
			if lineL[0:7] == 'keyid: ' :
				self.keyid = line[7:]
			elif lineL[0:11] == 'mailboxes: ':
				mailboxes = line[11:]
				self.incomingMailslots = 0
				for i in mailboxes.split(','):
					self.incomingMailslots += 1
				self.incomingMailslots = str(self.incomingMailslots)
			elif lineL[0:16] == 'listwindowsize: ':
				self.listWindowSize = line[16:]
			elif lineL[0:16] == 'viewwindowsize: ':
				self.viewWindowSize = line[16:]
			elif lineL[0:16] == 'editwindowsize: ':
				self.editWindowSize = line[16:]
			elif lineL[0:16] == 'addrwindowsize: ':
				self.addrWindowSize = line[16:]
			elif lineL[0:19] == 'editorscalefactor: ':
				self.editorScaleFactor = line[19:]
			elif lineL[0:24] == 'newmessagenotification: ':
				self.newMessageNotification = line[24:]
			elif lineL[0:17] == 'newmessagecheck: ':
				newMessageCheckNum = int(line[17:])
			elif lineL[0:12] == 'foldersync: ':
				folderSyncNum = int(line[12:])
			elif lineL[0:12] == 'fieldorder: ':
				self.fieldOrder = line[12:]
			elif lineL[0:16] == 'savefieldsizes: ':
				self.saveFieldSizes = line[16:]
			elif lineL[0:20] == 'spellchecklanguage: ':
				self.spellcheckLanguage = line[20:]
			elif lineL == 'newversioncheck: true':
				self.newVersionCheck = True
			elif lineL == 'newversioncheck: false':
				self.newVersionCheck = False
			elif lineL == 'closeonreply: true':
				self.closeOnReply = True
			elif lineL == 'closeonreply: false':
				self.closeOnReply = False
			elif lineL[0:11] == 'transport: ':
				self.transport = line[11:]
			elif lineL[0:14] == 'oldtransport: ':
				self.oldTransport = line[14:]
			elif lineL[0:12] == 'oldauthkey: ':
				self.oldAuthKey = line[12:]
			elif lineL[0:14] == 'altdnsserver: ':
				self.altDNSServer = line[14:]
			elif lineL[0:14] == 'pubtransport: ':
				self.pubTransport = line[14:]
			elif lineL[0:12] == 'pubauthkey: ':
				self.pubAuthKey = line[12:]
			elif lineL[0:16] == 'endpollolddate: ':
				self.endPollOldDate.ParseFormat(line[16:],'%Y-%m-%d')
			elif lineL[0:17] == 'endoldcostslots: ':
				self.endOldCostSlots.ParseFormat(line[17:],'%Y-%m-%d')
			elif lineL == 'usebypasstokens: true':
				self.useBypassTokens = True
			elif lineL == 'usebypasstokens: false':
				self.useBypassTokens = False
			elif lineL[0:17] == 'entangledserver: ':
				self.entangledServer = line[17:]
			elif lineL[0:9] == 'authkey: ':
				self.authKey = line[9:]
			elif lineL[0:10] == 'torproxy: ':
				self.torProxy = line[10:]
			elif lineL[0:10] == 'i2pproxy: ':
				self.i2pProxy = line[10:]
			elif lineL[0:12] == 'socksproxy: ':
				self.socksProxy = line[12:]
			elif lineL == 'proxyip: true':
				self.proxyIP = True
			elif lineL == 'proxyip: false':
				self.proxyIP = False
			elif lineL == 'proxytor: true':
				self.proxyTOR = True
			elif lineL == 'proxytor: false':
				self.proxyTOR = False
			elif lineL == 'proxyi2p: true':
				self.proxyI2P = True
			elif lineL == 'proxyi2p: false':
				self.proxyI2P = False
			elif lineL == 'useexitnode: true':
				self.useExitNode = True
			elif lineL == 'useexitnode: false':
				self.useExitNode = False
			elif lineL == 'proxydns: true':
				self.proxyDNS = True
			elif lineL == 'proxydns: false':
				self.proxyDNS = False
			elif lineL[0:18] == 'serverconnection: ':
				self.serverConnection = line[18:]
			elif lineL[0:19] == 'senderproofofwork: ':
				bd,nb,nm = line[19:].split(',')
				self.powNbits = nb
				self.powNmatches = nm
				self.antiJunkCost = self.SenderCostToName(self.powNbits)
			elif lineL[0:23] == 'prevsenderproofofwork: ':
				bd,nb,nm = line[23:].split(',')
				self.prevPowNbits = nb
				self.prevPowNmatches = nm
				self.prevAntiJunkCost = self.SenderCostToName(self.prevPowNbits)
			elif lineL[0:15] == 'prevmailboxes: ':
				mailboxes = line[15:]
				self.prevIncomingMailslots = 0
				for i in mailboxes.split(','):
					self.prevIncomingMailslots += 1
				self.prevIncomingMailslots = str(self.prevIncomingMailslots)
			elif lineL[0:19] == 'connectiontimeout: ':
				self.connectionTimeout = line[19:] + ' sec'

		if self.endPollOldDate < self.nowDate:
			self.endPollOldDate = wx.DateTime().SetToCurrent().__add__(wx.DateSpan(days=poll_old_server_days))
			self.oldTransport = ''
		if self.endOldCostSlots < self.nowDate:
			self.endOldCostSlots = wx.DateTime().SetToCurrent().__add__(wx.DateSpan(days=poll_old_server_days))
			self.prevAntiJunkCost = ''
			self.prevIncomingMailslots = ''

		if newMessageCheckNum == 0:
			self.newMessageCheck = 'Manual'
		elif newMessageCheckNum <= 300:
			self.newMessageCheck = 'Every 5 minutes'
		elif newMessageCheckNum <= 600:
			self.newMessageCheck = 'Every 10 minutes'
		elif newMessageCheckNum <= 900:
			self.newMessageCheck = 'Every 15 minutes'
		elif newMessageCheckNum <= 1800:
			self.newMessageCheck = 'Every 30 minutes'
		else:
			self.newMessageCheck = 'Once per hour'

		if folderSyncNum == 0:
			self.folderSync = 'Off'
		elif folderSyncNum <= 300:
			self.folderSync = 'Every 5 minutes'
		elif folderSyncNum <= 600:
			self.folderSync = 'Every 10 minutes'
		elif folderSyncNum <= 900:
			self.folderSync = 'Every 15 minutes'
		elif folderSyncNum <= 1800:
			self.folderSync = 'Every 30 minutes'
		else:
			self.folderSync = 'Once per hour'

	def OnSave(self,event):
		isGood = self.CheckSettings()
		if isGood == True:
			self.SaveSettings()
			self.Destroy()

	def OnSaveOpen(self,event):
		isGood = self.CheckSettings()
		if isGood == True:
			if self.app != None:
				self.app.openAfterSave = True
			self.SaveSettings()
			self.Destroy()

	def OnCancel(self,event):
		self.Destroy()

	def OnHelp(self,event):
		self.helpcon = wx.html.HtmlHelpController(parentWindow = self)
 		wx.FileSystem.AddHandler(wx.ZipFSHandler())
		self.helpcon.AddBook(global_config.help_file,0)
		self.helpcon.DisplayContents()
		notebookPage = self.notebook.GetSelection()
		if notebookPage == 1:
			self.helpcon.Display("config_dialog_network.html")
		elif notebookPage == 2:
			self.helpcon.Display("config_dialog_user_interface.html")
		elif notebookPage == 3:
			self.helpcon.Display("client_setup_public.html") # TODO
		else:
			self.helpcon.Display("config_dialog_identity.html")

	def CheckSettings(self):
		self.identityPanel.GetAll(self)
		self.networkPanel.GetAll(self)
		self.userInterfacePanel.GetAll(self)
		if self.keyid == None or self.keyid == '' or self.keyid[0:21] == 'No private keys found':
			self.notebook.SetSelection(0) # Identity panel
			self.identityPanel.chooseGpgKey.SetFocus()
			wx.CallAfter(wx.MessageBox,"Please choose or create a key for your account.","No keyid selected",style = wx.ICON_EXCLAMATION)
			return False
		if self.serverList == None or re_validate_server_list.match(self.serverList) == None:
			self.notebook.SetSelection(1) # Network panel
			self.networkPanel.textServerList.SetFocus()
			wx.CallAfter(wx.MessageBox,"Please enter one or more host:port addresses","No servers entered",style = wx.ICON_EXCLAMATION)
			return False
		return True

	def SaveSettings(self): # assumes Check above just called to fetch values!
		m = re_con_timeout.match(self.chooseConnectTimeout)
		connectTimeout = m.group(1)
		if self.newMessageCheck == 'Once per hour':
			newMessageCheck = '3600'
		elif self.newMessageCheck == 'Every 30 minutes':
			newMessageCheck = '1800'
		elif self.newMessageCheck == 'Every 15 minutes':
			newMessageCheck = '900'
		elif self.newMessageCheck == 'Every 10 minutes':
			newMessageCheck = '600'
		elif self.newMessageCheck == 'Every 5 minutes':
			newMessageCheck = '300'
		else:
			newMessageCheck = '0'

		if self.folderSync == 'Once per hour':
			folderSync = '3600'
		elif self.folderSync == 'Every 30 minutes':
			folderSync = '1800'
		elif self.folderSync == 'Every 15 minutes':
			folderSync = '900'
		elif self.folderSync == 'Every 10 minutes':
			folderSync = '600'
		elif self.folderSync == 'Every 5 minutes':
			folderSync = '300'
		else:
			folderSync = '0'

		if os.path.exists(self.configFile + '.5'): # keep some backups
			os.unlink(self.configFile + '.5')
		if os.path.exists(self.configFile + '.4'):
			os.rename(self.configFile + '.4',self.configFile + '.5')
		if os.path.exists(self.configFile + '.3'):
			os.rename(self.configFile + '.3',self.configFile + '.4')
		if os.path.exists(self.configFile + '.2'):
			os.rename(self.configFile + '.2',self.configFile + '.3')
		if os.path.exists(self.configFile + '.1'):
			os.rename(self.configFile + '.1',self.configFile + '.2')
		if os.path.exists(self.configFile):
			os.rename(self.configFile,self.configFile + '.1')

		cfile = codecs.open(self.configFile,'w','utf-8')
		saveFileTime = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
		cfile.write('SaveTime: ' + saveFileTime + '\n')
		cfile.write('Keyid: ' + self.keyid.upper() + '\n')
		cfile.write('EmailAddress: ' + self.emailaddr + '\n')
		cfile.write('SenderProofOfWork: bd,' + str(self.powNbits) + ',' + str(self.powNmatches) + '\n')
		cfile.write('PrevSenderProofOfWork: bd,' + str(self.prevPowNbits) + ',' + str(self.prevPowNmatches) + '\n')
		mailslots = ''
		for i in range(self.incomingMailslots):
			if mailslots == '':
				mailslots = str(i)
			else:
				mailslots += ',' + str(i)
		cfile.write('Mailboxes: ' + mailslots + '\n')
		mailslots = ''
		for i in range(self.prevIncomingMailslots):
			if mailslots == '':
				mailslots = str(i)
			else:
				mailslots += ',' + str(i)
		cfile.write('PrevMailboxes: ' + mailslots + '\n')
		if self.chooseRetrieveFrom == 'Entangled':
			cfile.write('Transport: entangled\n')
		else:
			cfile.write('Transport: server=' + self.serverList + '\n')
		cfile.write('AuthKey: ' + self.authKey + '\n')
		cfile.write('EntangledServer: server=' + self.serverList + '\n')
		cfile.write('ServerConnection: ' + self.serverConnection + '\n')
		cfile.write('EndPollOldDate: ' + self.endPollOldDate.Format('%Y-%m-%d') + '\n')
		cfile.write('EndOldCostSlots: ' + self.endOldCostSlots.Format('%Y-%m-%d') + '\n')
		if self.chooseOldRetrieveFrom == 'Entangled':
			cfile.write('OldTransport: entangled\n')
		elif self.chooseOldRetrieveFrom == 'Old server list':
			cfile.write('OldTransport: server=' + self.oldServerList + '\n')
		if self.torAddr != '':
			cfile.write('TorProxy: ' + self.torAddr + ':' + self.torPort + '\n')
		if self.i2pAddr != '':
			cfile.write('I2PProxy: ' + self.i2pAddr + ':' + self.i2pPort + '\n')
		if self.socksAddr != '':
			cfile.write('SocksProxy: ' + self.socksAddr + ':' + self.socksPort + '\n')
		if self.oldAuthKey != '':
			cfile.write('OldAuthKey: ' + self.oldAuthKey + '\n')
		if self.altDNSServer != '':
			cfile.write('AltDNSServer: server=' + self.altDNSServer + '\n')
		if self.pubTransport != '' and self.pubAuthKey != '':
			cfile.write('PubTransport: server=' + self.pubTransport + '\n')
			cfile.write('PubAuthKey: ' + self.pubAuthKey + '\n')
		if self.useBypassTokens == True:
			cfile.write('UseBypassTokens: True\n')
		else:
			cfile.write('UseBypassTokens: False\n')
		cfile.write('ConnectionTimeout: ' + connectTimeout + '\n')
		cfile.write('NewMessageCheck: ' + newMessageCheck + '\n')
		cfile.write('FolderSync: ' + folderSync + '\n')

		cfile.write('ListWindowSize: %sx%s\n' % (self.ListSizeX,self.ListSizeY))
		cfile.write('EditWindowSize: %sx%s\n' % (self.EditSizeX,self.EditSizeY))
		cfile.write('ViewWindowSize: %sx%s\n' % (self.ViewSizeX,self.ViewSizeY))
		cfile.write('AddrWindowSize: %sx%s\n' % (self.AddrSizeX,self.AddrSizeY))
		cfile.write('EditorScaleFactor: ' + self.editorScaleFactor + '\n')
		cfile.write('NewMessageNotification: ' + self.newMessageNotification + '\n')
		cfile.write('FieldOrder: ' + self.fieldOrder + '\n')
		cfile.write('SaveFieldSizes: ' + self.saveFieldSizes + '\n')
		cfile.write('SpellcheckLanguage: ' + self.spellcheckLanguage + '\n')
		if self.closeOnReply == True:
			cfile.write('CloseOnReply: True\n')
		else:
			cfile.write('CloseOnReply: False\n')
		if self.newVersionCheck == True:
			cfile.write('NewVersionCheck: True\n')
		else:
			cfile.write('NewVersionCheck: False\n')
		if self.proxyIP == True:
			cfile.write('ProxyIP: True\n')
		else:
			cfile.write('ProxyIP: False\n')
		if self.proxyTOR == True:
			cfile.write('ProxyTOR: True\n')
		else:
			cfile.write('ProxyTOR: False\n')
		if self.proxyI2P == True:
			cfile.write('ProxyI2P: True\n')
		else:
			cfile.write('ProxyI2P: False\n')
		if self.useExitNode == True:
			cfile.write('UseExitNode: True\n')
		else:
			cfile.write('UseExitNode: False\n')
		if self.proxyDNS == True:
			cfile.write('ProxyDNS: True\n')
		else:
			cfile.write('ProxyDNS: False\n')
		cfile.close()
		sfile = open(self.keyUpdateFile,'w')
		sfile.write(saveFileTime + '\n')
		sfile.close()

	def DoKeyGeneration(self,username,email,comment,passphrase,keytype,keybits):
		if keytype == 'DSA/ELG':
			gpg_kt = 'DSA'
			gpg_skt = 'ELG-E'
			gpg_curve = None
		elif keytype == 'ECC':
			gpg_kt = 'ecdsa'
			gpg_skt = 'ecdh'
			gpg_curve = 'nistp384'
			if keybits == 'ECC NIST P-256':
				gpg_curve = 'nistp256'
			elif keybits == 'ECC NIST P-384':
				gpg_curve = 'nistp384'
			elif keybits == 'ECC NIST P-521':
				gpg_curve = 'nistp521'
			elif keybits == 'ECC Brainpool P-256':
				gpg_curve = 'brainpoolP256r1'
			elif keybits == 'ECC Brainpool P-384':
				gpg_curve = 'brainpoolP384r1'
			elif keybits == 'ECC Brainpool P-512':
				gpg_curve = 'brainpoolP512r1'
			elif keybits == 'ECC Curve25519':
				gpg_curve = 'Ed25519' # cipher/ecc-curves.c
			elif keybits == 'ECC secp256k1':
				gpg_curve = 'secp256k1' # cipher/ecc-curves.c
		else:
			gpg_kt = 'RSA'
			gpg_skt = 'RSA'
			gpg_curve = None
		try:
			if os.path.isdir(self.gpgDir) == False:
				os.mkdir(self.gpgDir)
			if sys.platform == 'darwin' and global_config.gnupg_is_v2 == True:
				try:
					find_gpg_homedir.macos_fix_pinentry(global_config.gnupg_path,self.gpgDir)
				except Exception:
					pass
			gpg = gnupg.GPG(gpgbinary = global_config.gnupg_path,options = global_config.gpg_opts,gnupghome = self.gpgDir)
			gpg.encoding = 'utf-8'
			if gpg_curve != None:
				input_data = gpg.gen_key_input(Key_Type = gpg_kt,Key_Curve = gpg_curve, Name_Real = username, Name_Comment = comment, Name_Email = email, Subkey_Type = gpg_skt, Subkey_Curve = gpg_curve, passphrase = passphrase)
			else:
				input_data = gpg.gen_key_input(Key_Type = gpg_kt,Key_Length = keybits, Name_Real = username, Name_Comment = comment, Name_Email = email, Subkey_Type = gpg_skt, Subkey_Length = keybits, passphrase = passphrase)
			key = gpg.gen_key(input_data)
		except Exception as e:
			#print traceback.format_exc()
			self.keyGenerationPanel.CreateKeyError(str(e))
			return

		self.keyGenerationPanel.textErrorMessage.SetLabel("Key generation complete")
		if key.fingerprint == None:
			self.identityPanel.LoadKeys(None)
		else:
			self.identityPanel.LoadKeys(key.fingerprint.lower())
		self.notebook.SetSelection(0) # Identity panel

	def fetchRemoteConfig(self,url):
		urlp = urlparse.urlparse(url)
		#DBGOUT#print urlp
		if urlp.scheme != u'http' and urlp.scheme != u'https' and urlp.scheme != u'file':
			self.fetchRemoteStatus.SetLabel("Invalid URL")
			if self.fetchRemoteFail != None:
				self.fetchRemoteFail()
		else:
			self.fetchRemoteStatus.SetLabel("Retrieving configuration")
			wx.CallAfter(self.fetchRemoteConfig2,url,urlp)

	def fetchRemoteConfig2(self,url,urlp):
		# Socks support for TAILS and WHONIX
		self.defaultSocket = None
		usingTails = False
		usingWhonix = False
		socks_server = None
		if 'SOCKS5_SERVER' in os.environ:
			socks_server = os.environ['SOCKS5_SERVER']
		elif 'SOCKS_SERVER' in os.environ:
			socks_server = os.environ['SOCKS_SERVER']
		if ('WHONIX' in os.environ) and (os.environ['WHONIX'] == '1') and os.path.exists("/usr/share/whonix"):
			usingWhonix = True
			import socks
			self.defaultSocket = socket.socket
			socks_host = '127.0.0.1'
			socks_port = 9150 # Not in any env var
			socks.set_default_proxy(socks.SOCKS5,socks_host,socks_port)
			socket.socket = socks.socksocket
		elif socks_server != None:
			if 'TAILS_WIKI_SUPPORTED_LANGUAGES' in os.environ and ( 'USERNAME' in os.environ and os.environ['USERNAME'] == 'amnesia' ):
				usingTails = True
			import socks
			self.defaultSocket = socket.socket
			socks_host,socks_port = socks_server.split(':')
			socks_port = int(socks_port)
			socks.set_default_proxy(socks.SOCKS5,socks_host,socks_port)
			socket.socket = socks.socksocket
		# End socks support

		if urlp.query == '':
			upath = urlp.path
		else:
			upath = urlp.path + '?' + urlp.query
		try:
			if urlp.scheme == u'file':
				if sys.platform == 'win32':
					upath = upath.replace('/',os.sep)
				res = codecs.open(upath,'r','utf-8')
				con = None
			else:
				if urlp.scheme == u'https':
					con = httplib.HTTPSConnection(urlp.netloc)
				else:
					con = httplib.HTTPConnection(urlp.netloc)
				headers = dict()
				userAgent = 'CONFIDANT MAIL ' + global_config.software_version
				# Inform the server so Tails-specific configuration can be sent down
				# Necessary because non-SOCKS connections don't work in Tails
				if usingTails:
					userAgent += ' ON TAILS'
				elif usingWhonix:
					userAgent += ' ON WHONIX'
				headers['User-Agent'] = userAgent
				con.request('GET',upath,None,headers)
				res = con.getresponse()
				self.fetchRemoteStatus.SetLabel('Got ' + str(res.status) + ' ' + res.reason)
			wx.CallAfter(self.fetchRemoteConfig3,url,urlp,con,res)
		except Exception as e:
			self.fetchRemoteStatus.SetLabel(str(e))
			if self.fetchRemoteFail != None:
				self.fetchRemoteFail()

	def fetchRemoteConfig3(self,url,urlp,con,res):
		time.sleep(0.5)
		#DBGOUT#print res.status,res.reason
		body = res.read()
		if con == None:
			res.close()
		else:
			con.close()
		if self.defaultSocket != None: # put normal socket back
			socket.socket = self.defaultSocket
		#DBGOUT#print len(body),body
		gotBegin = False
		gotEnd = False
		configData = ''
		for line in body.split('\n'):
			line = line.rstrip('\r\n')
			if line == '#BEGIN_CONFIG#' and gotBegin == False and gotEnd == False: 
				gotBegin = True
			if line == '#END_CONFIG#' and gotBegin == True and gotEnd == False: 
				gotEnd = True
			if gotBegin == True and gotEnd == False:
				configData += line + '\n'
		if gotBegin == True and gotEnd == True:
			wx.CallAfter(self.fetchRemoteFinal,configData)
		else:
			self.fetchRemoteStatus.SetLabel('Failed to parse remote configuration data')
			if self.fetchRemoteFail != None:
				self.fetchRemoteFail()
			
	def fetchRemoteConfig4(self,configData):
		time.sleep(0.5)
		self.identityPanel.GetAll(self)
		self.networkPanel.GetAll(self)
		self.userInterfacePanel.GetAll(self)
		self.LoadFromFile(configData)
		self.PostLoadFixup()
		self.UpdatePanes()
		self.fetchRemoteStatus.SetLabel('Remote configuration sucessful; check settings and click Save')

class EasyDialogFrame(ConfigDialogFrame):
	def __init__(self,parent,size,baseDir,pos=None,app = None):
		self.app = app
		title = 'Easy Setup'
		if pos == None:
			wx.Frame.__init__(self,parent,-1,title,size=size)
		else:
			wx.Frame.__init__(self,parent,-1,title,pos=pos,size=size)
		self.baseDir = baseDir	

		mainPanel = wx.Panel(self,-1,size=self.GetClientSize())
		panelSizer = wx.BoxSizer(wx.VERTICAL)
		panelSizer.Add(mainPanel,1,wx.ALL|wx.GROW,0)
		vsizer = wx.BoxSizer(wx.VERTICAL)

		labelConfUrl = wx.StaticText(mainPanel,-1,"Remote Config URL",style=wx.ALIGN_RIGHT)
		x,y = labelConfUrl.GetSize()

		hsizer2 = wx.BoxSizer(wx.HORIZONTAL)
		labelDirMsgBlank = wx.StaticText(mainPanel,-1,"",size=(x,-1),style=wx.ALIGN_RIGHT)
		labelDirMsg = wx.StaticText(mainPanel,-1,"Account directory name on disk, or leave blank for default")
		hsizer2.Add(labelDirMsgBlank,0,wx.ALL,3)
		hsizer2.Add(labelDirMsg,0,wx.ALL,3)

		hsizer3 = wx.BoxSizer(wx.HORIZONTAL)
		labelDirName = wx.StaticText(mainPanel,-1,"Directory Name",size=(x,-1),style=wx.ALIGN_RIGHT)
		self.textDirName = wx.TextCtrl(mainPanel,-1,"")
		hsizer3.Add(labelDirName,0,wx.ALL,3)
		hsizer3.Add(self.textDirName,1,wx.ALL|wx.GROW,3)

		hsizer4 = wx.BoxSizer(wx.HORIZONTAL)
		labelNewKeyName = wx.StaticText(mainPanel,-1,"Your Name",size=(x,-1),style=wx.ALIGN_RIGHT)
		self.textNewKeyName = wx.TextCtrl(mainPanel,-1,"")
		hsizer4.Add(labelNewKeyName,0,wx.ALL,3)
		hsizer4.Add(self.textNewKeyName,1,wx.ALL|wx.GROW,3)

		hsizer4a = wx.BoxSizer(wx.HORIZONTAL)
		labelAdrMsgBlank = wx.StaticText(mainPanel,-1,"",size=(x,-1),style=wx.ALIGN_RIGHT)
		labelAdrMsg = wx.StaticText(mainPanel,-1,"You can use any email address you currently have.")
		hsizer4a.Add(labelAdrMsgBlank,0,wx.ALL,3)
		hsizer4a.Add(labelAdrMsg,0,wx.ALL,3)

		hsizer5 = wx.BoxSizer(wx.HORIZONTAL)
		labelNewKeyEmail = wx.StaticText(mainPanel,-1,"Email Address",size=(x,-1),style=wx.ALIGN_RIGHT)
		self.textNewKeyEmail = wx.TextCtrl(mainPanel,-1,"")
		hsizer5.Add(labelNewKeyEmail,0,wx.ALL,3)
		hsizer5.Add(self.textNewKeyEmail,1,wx.ALL|wx.GROW,3)

		hsizer5a = wx.BoxSizer(wx.HORIZONTAL)
		labelComMsgBlank = wx.StaticText(mainPanel,-1,"",size=(x,-1),style=wx.ALIGN_RIGHT)
		labelComMsg = wx.StaticText(mainPanel,-1,"Comment for your GPG key, or leave blank")
		hsizer5a.Add(labelComMsgBlank,0,wx.ALL,3)
		hsizer5a.Add(labelComMsg,0,wx.ALL,3)

		hsizer6 = wx.BoxSizer(wx.HORIZONTAL)
		labelNewKeyComment = wx.StaticText(mainPanel,-1,"Key Comment",size=(x,-1),style=wx.ALIGN_RIGHT)
		self.textNewKeyComment = wx.TextCtrl(mainPanel,-1,"")
		hsizer6.Add(labelNewKeyComment,0,wx.ALL,3)
		hsizer6.Add(self.textNewKeyComment,1,wx.ALL|wx.GROW,3)

		hsizer7a = wx.BoxSizer(wx.HORIZONTAL)
		labelPasMsg1Blank = wx.StaticText(mainPanel,-1,"",size=(x,-1),style=wx.ALIGN_RIGHT)
		labelPasMsg1 = wx.StaticText(mainPanel,-1,"Passphrase protects your private key. If you lose it, you will")
		hsizer7a.Add(labelPasMsg1Blank,0,wx.ALL,3)
		hsizer7a.Add(labelPasMsg1,0,wx.ALL,3)

		hsizer7b = wx.BoxSizer(wx.HORIZONTAL)
		labelPasMsg2Blank = wx.StaticText(mainPanel,-1,"",size=(x,-1),style=wx.ALIGN_RIGHT)
		labelPasMsg2 = wx.StaticText(mainPanel,-1,"have to create a new key. Use several words, case sensitive.")
		hsizer7b.Add(labelPasMsg2Blank,0,wx.ALL,3)
		hsizer7b.Add(labelPasMsg2,0,wx.ALL,3)

		hsizer7 = wx.BoxSizer(wx.HORIZONTAL)
		labelNewKeyPassphrase1 = wx.StaticText(mainPanel,-1,"Passphrase",size=(x,-1),style=wx.ALIGN_RIGHT)
		self.textNewKeyPassphrase1 = wx.TextCtrl(mainPanel,-1,"")
		hsizer7.Add(labelNewKeyPassphrase1,0,wx.ALL,3)
		hsizer7.Add(self.textNewKeyPassphrase1,1,wx.ALL|wx.GROW,3)
		if global_config.gnupg_is_v2 == True:
			self.textNewKeyPassphrase1.SetValue("Using GnuPG version 2")
			self.textNewKeyPassphrase1.Disable()

		hsizer8 = wx.BoxSizer(wx.HORIZONTAL)
		labelNewKeyPassphrase2 = wx.StaticText(mainPanel,-1,"Repeat passphrase",size=(x,-1),style=wx.ALIGN_RIGHT)
		self.textNewKeyPassphrase2 = wx.TextCtrl(mainPanel,-1,"")
		hsizer8.Add(labelNewKeyPassphrase2,0,wx.ALL,3)
		hsizer8.Add(self.textNewKeyPassphrase2,1,wx.ALL|wx.GROW,3)
		if global_config.gnupg_is_v2 == True:
			self.textNewKeyPassphrase2.SetValue("Passphrase prompt will pop up.")
			self.textNewKeyPassphrase2.Disable()

		hsizer9 = wx.BoxSizer(wx.HORIZONTAL)
		labelUrlMsgBlank1 = wx.StaticText(mainPanel,-1,"",size=(x,-1),style=wx.ALIGN_RIGHT)
		labelUrlMsg1 = wx.StaticText(mainPanel,-1,"You should have received the Remote Config URL from your mail")
		hsizer9.Add(labelUrlMsgBlank1,0,wx.ALL,3)
		hsizer9.Add(labelUrlMsg1,0,wx.ALL,3)

		hsizer10 = wx.BoxSizer(wx.HORIZONTAL)
		labelUrlMsgBlank2 = wx.StaticText(mainPanel,-1,"",size=(x,-1),style=wx.ALIGN_RIGHT)
		labelUrlMsg2 = wx.StaticText(mainPanel,-1,"service provider when you signed up. Copy and Paste it in below.")
		hsizer10.Add(labelUrlMsgBlank2,0,wx.ALL,3)
		hsizer10.Add(labelUrlMsg2,0,wx.ALL,3)

		hsizer11 = wx.BoxSizer(wx.HORIZONTAL)
		hsizer11.Add(labelConfUrl,0,wx.ALL,3)
		self.textConfUrl = wx.TextCtrl(mainPanel,-1,"")
		hsizer11.Add(self.textConfUrl,1,wx.ALL|wx.GROW,3)
		x2,y = self.textConfUrl.GetSize()
		self.pasteUrlButton = wx.Button(mainPanel,id_paste_url_button,"<-- Paste",style = wx.BU_EXACTFIT,size = (-1,y) )
		self.Bind(wx.EVT_BUTTON,self.OnPasteUrlButton,self.pasteUrlButton)
		hsizer11.Add(self.pasteUrlButton,0,wx.ALL,3)

		self.textErrorMessage = wx.StaticText(mainPanel,-1,"Watch this line during setup. Status updates appear here.")	
		hsizer12 = wx.BoxSizer(wx.HORIZONTAL)
		hsizer12.Add(self.textErrorMessage,0,wx.ALL,3)
	
		hsizer13 = wx.BoxSizer(wx.HORIZONTAL)
		self.setupButton = wx.Button(mainPanel,id_setup,"Setup Account")
		hsizer13.Add(self.setupButton,0,wx.ALL,3)
		self.cancelButton = wx.Button(mainPanel,id_cancel,"Cancel")
		hsizer13.Add(self.cancelButton,0,wx.ALL,3)
		self.Bind(wx.EVT_BUTTON,self.OnSetup,self.setupButton)
		self.Bind(wx.EVT_BUTTON,self.OnCancel,self.cancelButton)

		vsizer.Add(hsizer2,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizer3,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizer4,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizer4a,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizer5,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizer5a,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizer6,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizer7a,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizer7b,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizer7,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizer8,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizer9,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizer10,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizer11,0,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizer12,1,wx.ALL|wx.GROW,0)
		vsizer.Add(hsizer13,0,wx.ALIGN_CENTER_HORIZONTAL,0)
		mainPanel.SetSizer(vsizer)
		self.SetSizer(panelSizer)

		keyicon_bmp = images2.key_icon.GetBitmap()
		keyicon = wx.IconFromBitmap(keyicon_bmp)
		self.SetIcon(keyicon)

		if sys.platform == 'darwin':
			panelSizer.Layout()

	def OnPasteUrlButton(self,event):
		self.textConfUrl.SetValue("")
		self.textConfUrl.Paste()

	def DeleteAfterFailure(self):
		self.setupButton.Enable()
		try:
			if os.path.exists(self.gpgDir):
				for filename in os.listdir(self.gpgDir):
					filepath = self.gpgDir + os.sep + filename
					if os.path.exists(filepath):
						os.unlink(filepath)
				os.rmdir(self.gpgDir)
			os.rmdir(self.configDir)
		except Exception as exc:
			pass

	def OnSetup(self,event):
		self.setupButton.Disable()
		dirname = self.textDirName.GetValue()
		username = self.textNewKeyName.GetValue()
		email = self.textNewKeyEmail.GetValue()
		comment = self.textNewKeyComment.GetValue()
		passphrase1 = self.textNewKeyPassphrase1.GetValue()
		passphrase2 = self.textNewKeyPassphrase2.GetValue()
		confurl = self.textConfUrl.GetValue()

		if dirname.rstrip(' ') == '':
			dirname = username.rstrip(' ').replace(' ','_').replace("'",'_').lower()
			self.textDirName.SetValue(dirname)
		fault = None
		if re_valid_dirname.match(dirname) == None:
			if dirname == '':
				fault = "Directory name is missing"
			else:
				fault = "Directory name is invalid, use letters and numbers only"
			self.textDirName.SetFocus()
		elif re_blankorwhitespace.match(username):
			fault = "Username is missing"
			self.textNewKeyName.SetFocus()
		elif re_blankorwhitespace.match(email):
			fault = "Email is missing"
			self.textNewKeyEmail.SetFocus()
		elif re_email_addr.match(email) == None:
			fault = "Email is invalid, enter user@host.domain"
			self.textNewKeyEmail.SetFocus()
		elif re_blankorwhitespace.match(passphrase1):
			fault = "Passphrase is missing"
			self.textNewKeyPassphrase1.SetFocus()
		elif global_config.gnupg_is_v2 == False and passphrase1 != passphrase2:
			fault = "Passphrase mismatch"
			self.textNewKeyPassphrase2.SetFocus()
		elif re_valid_url.match(confurl) == None:
			if confurl == '':
				fault = "Remote config URL is missing"
			else:
				fault = "Remote config URL is invalid"
			self.textConfUrl.SetFocus()
		else:
			configDir = self.baseDir + os.sep + dirname
			try:
				os.rmdir(configDir) # pass on empty dir
			except Exception as exc:
				pass
			if os.path.exists(configDir) == True:
				fault = "Directory already exists"
				self.textDirName.SetFocus()
			else:
				try:
					os.mkdir(configDir)
				except Exception as exc:
					fault = "Cannot make directory: " + exc.strerror	

		if fault != None:
			self.textErrorMessage.SetLabel(fault)
			self.setupButton.Enable()
			return
		else:
			self.configDir = configDir
			self.gpgDir = self.configDir + os.sep + "gpg"
			self.configFile = configDir + os.sep + "config.txt"
			self.keyUpdateFile = configDir + os.sep + "key_update_flag"

		self.fetchRemoteStatus = self.textErrorMessage
		self.fetchRemoteFinal = self.OnSetupGenKey
		self.fetchRemoteFail = self.DeleteAfterFailure
		self.textErrorMessage.SetLabel("Fetching remote configuration")
		self.tempKeygenTimer = wx.Timer(self,id = id_key_gen_timer)
		self.Bind(wx.EVT_TIMER,self.OnSetupFetchRemote,id = id_key_gen_timer)
		self.tempKeygenTimer.Start(500,wx.TIMER_ONE_SHOT)

	def OnSetupFetchRemote(self,event):
		self.fetchRemoteConfig(self.textConfUrl.GetValue())

	def OnSetupGenKey(self,configData):
		self.configData = configData
		if sys.platform[0:5] == 'linux':
			self.textErrorMessage.SetLabel("Generating key, may take minutes...")
		else:
			self.textErrorMessage.SetLabel("Generating key...")
		self.tempKeygenTimer = wx.Timer(self,id = id_key_gen_timer)
		self.Bind(wx.EVT_TIMER,self.StartKeyGeneration,id = id_key_gen_timer)
		self.tempKeygenTimer.Start(100,wx.TIMER_ONE_SHOT)
		# timer was required to get message to display

	def StartKeyGeneration(self,event):
		username = self.textNewKeyName.GetValue()
		email = self.textNewKeyEmail.GetValue()
		self.emailaddr = username + ' <' + email + '>'
		comment = self.textNewKeyComment.GetValue()
		passphrase = self.textNewKeyPassphrase1.GetValue()
		gpg_kt = 'RSA'
		keybits = '3072'
		try:
			if os.path.isdir(self.gpgDir) == False:
				os.mkdir(self.gpgDir)
			if sys.platform == 'darwin' and global_config.gnupg_is_v2 == True:
				try:
					find_gpg_homedir.macos_fix_pinentry(global_config.gnupg_path,self.gpgDir)
				except Exception:
					pass
			gpg = gnupg.GPG(gpgbinary = global_config.gnupg_path,options = global_config.gpg_opts,gnupghome = self.gpgDir)
			gpg.encoding = 'utf-8'
			input_data = gpg.gen_key_input(key_type = gpg_kt,key_length = keybits, name_real = username,
				name_comment = comment, name_email = email, subkey_length = keybits, passphrase = passphrase)
			key = gpg.gen_key(input_data)
			self.keyidEasySetup = key.fingerprint.lower()
		except Exception as e:
			self.textErrorMessage.SetLabel("Key generation failed: " + str(e))
			self.DeleteAfterFailure()
			return
		self.textErrorMessage.SetLabel("Key generation complete")
		self.tempKeygenTimer = wx.Timer(self,id = id_key_gen_timer)
		self.Bind(wx.EVT_TIMER,self.CompleteSetup1,id = id_key_gen_timer)
		self.tempKeygenTimer.Start(500,wx.TIMER_ONE_SHOT)

	def CompleteSetup1(self,event):
		self.LoadDefaults()
		self.incomingMailslots = int(self.incomingMailslots)
		self.LoadFromFile(self.configData)
		self.keyid = self.keyidEasySetup
		self.chooseConnectTimeout = self.connectionTimeout
		self.chooseRetrieveFrom = 'Server'
		self.serverList = self.entangledServer[7:] # assumes server=
		self.chooseOldRetrieveFrom = 'none'
		m = re_resolution.match(self.listWindowSize)
		if m:
			self.ListSizeX = m.group(1)	
			self.ListSizeY = m.group(2)	
		m = re_resolution.match(self.viewWindowSize)
		if m:
			self.ViewSizeX = m.group(1)	
			self.ViewSizeY = m.group(2)	
		m = re_resolution.match(self.editWindowSize)
		if m:
			self.EditSizeX = m.group(1)	
			self.EditSizeY = m.group(2)	
		m = re_resolution.match(self.addrWindowSize)
		if m:
			self.AddrSizeX = m.group(1)	
			self.AddrSizeY = m.group(2)	
		try:
			self.torAddr,self.torPort = self.torProxy.rsplit(':',1)
		except ValueError:
			pass
		try:
			self.i2pAddr,self.i2pPort = self.i2pProxy.rsplit(':',1)
		except ValueError:
			pass
		try:
			self.socksAddr,self.socksPort = self.socksProxy.rsplit(':',1)
		except ValueError:
			pass
		self.PostLoadFixup()
		self.fetchRemoteStatus.SetLabel('Remote configuration sucessful')
		self.tempKeygenTimer = wx.Timer(self,id = id_key_gen_timer)
		self.Bind(wx.EVT_TIMER,self.CompleteSetup2,id = id_key_gen_timer)
		self.tempKeygenTimer.Start(500,wx.TIMER_ONE_SHOT)

	def CompleteSetup2(self,event):
		if self.app != None:
			self.app.openAfterSave = True
			self.app.easySetupPath = self.configDir
		self.SaveSettings()
		self.Destroy()

class RunApp(wx.App):
	def __init__(self,homedir,pos = None):
		self.openAfterSave = False
		self.easySetupPath = None
		self.homedir = homedir
		self.pos = pos
		wx.App.__init__(self, redirect=False)

	def OnInit(self):
		if self.homedir[0:13] == '/\EASYSETUP\/':
			self.frame = EasyDialogFrame(None,[ 640,600 ],self.homedir[13:],pos = self.pos,app = self)
		else:
			self.frame = ConfigDialogFrame(None,[ 640,600 ],self.homedir,pos = self.pos,app = self)
		self.frame.Show()
		self.SetTopWindow(self.frame)
		return True

# EOF
