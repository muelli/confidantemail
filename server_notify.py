import logging
import traceback
import smtplib
import time
from email.mime.text import MIMEText
import os

class serverNotify:
	def __init__(self,homedir):
		self.logger = logging.getLogger(__name__)
		self.homedir = homedir
		self.notifyConfig = homedir + os.sep + 'notify.txt'
		self.configReadMtime = -1
		self.notifyByKeyid = dict()
		self.fromAddr = None
		self.smtpServer = 'localhost'
		self.smtpPort = 25
		self.smtpUser = None
		self.smtpPass = None
		self.readConfig()
#		print "init" # DEBUG

	def readConfig(self):
		lockFile = self.notifyConfig + '.lock'
		for i in range(10):
			if os.path.exists(lockFile):
				time.sleep(1)
			else:
				break		
		if os.path.exists(self.notifyConfig) == False:
#			print "no config file" # DEBUG
			return
		try:
			filestat = os.stat(self.notifyConfig)
		except IOError:
#			print "file read failed" # DEBUG
			return	
		if (self.configReadMtime >= 0) and (filestat.st_mtime == self.configReadMtime):
#			print "config up to date" # DEBUG
			return # up to date
		filehandle = open(self.notifyConfig,'rb')
		self.notifyByKeyid = dict()
		for line in filehandle:
			line = line.rstrip('\r\n\t ')
			if line == '' or line[0] == '#':
				continue
			elif line[0:9] == 'fromaddr=':
				self.fromAddr = line[9:]
			elif line[0:11] == 'smtpserver=':
				self.smtpServer = line[11:]
			elif line[0:9] == 'smtpport=':
				self.smtpPort = line[9:]
			elif line[0:9] == 'smtpuser=':
				self.smtpUser = line[9:]
			elif line[0:9] == 'smtppass=':
				self.smtpPass = line[9:]
			else:
				keyid,ntype,naddr = line.split(',',2)
				keyid = keyid.lower()
				self.notifyByKeyid[keyid] = ntype,naddr
		filehandle.close()
		self.configReadMtime = filestat.st_mtime
#		print "loaded config" # DEBUG

	def notifyRecipient(self,keyid):
		self.readConfig()
		if keyid not in self.notifyByKeyid:
#			print "no notification record" # DEBUG
			return
		ntype,naddr = self.notifyByKeyid[keyid]
#		print "ntype=",ntype,"naddr=",naddr # DEBUG
		if ntype == 'email' or ntype == 'smtp':
			self.logger.info("Notifying email address %s for keyid %s",naddr,keyid)
			try:
				self.notifyRecipientEmail(keyid,naddr)
			except Exception as exc:
				self.logger.info("Email notify exception: %s",traceback.format_exc())
		
	def notifyRecipientEmail(self,keyid,naddr):
#		print "fromAddr",self.fromAddr # DEBUG
#		print "smtpServer",self.smtpServer # DEBUG
#		print "smtpServer",self.smtpPort # DEBUG
#		print "smtpUser",self.smtpUser # DEBUG
#		print "smtpPass",self.smtpPass # DEBUG
		
		msg_subj = "You have new Confidant Mail"
		msg_txt = "You have new Confidant Mail"
		msg = MIMEText(msg_txt)
		msg['Subject'] = msg_subj
		msg['From'] = self.fromAddr
		msg['To'] = naddr
		smtp = smtplib.SMTP()
		smtp.set_debuglevel(0)
		smtp.connect(self.smtpServer,self.smtpPort)
		if self.smtpUser != None:
			smtp.login(self.smtpUser,self.smtpPass)
		smtp.sendmail(self.fromAddr,naddr,msg.as_string())
		smtp.quit()
		

#logging.basicConfig(level=logging.DEBUG,
#	format="%(asctime)s %(levelname)-5s %(name)-10s %(threadName)-10s %(message)s")
#
#sn = serverNotify('c:\\projects\\keymail\\server1')
#sn.notifyRecipient('1234')
#print "still running"

# EOF
