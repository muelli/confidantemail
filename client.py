import logging
import string
import re
import struct
import OpenSSL
import twisted.protocols.basic
import twisted.internet.protocol
import twisted.internet.reactor
import twisted.internet.ssl
import twisted.internet.endpoints

re_greeting = re.compile("^.*CONFIDANT MAIL SERVER PROTOCOL [0-9]+ READY$",re.IGNORECASE)
re_busy_greeting = re.compile("^.*CONFIDANT MAIL SERVER PROTOCOL [0-9]+ BUSY$",re.IGNORECASE)
re_data = re.compile("^DATA: ([1-9][0-9]*)$",re.IGNORECASE)
re_ipv4 = re.compile("^(\d+)\.(\d+)\.(\d+)\.(\d+)$",re.IGNORECASE)
throttle_send_freq = 0.2 # interval (fractional seconds) between sends in throttle mode

# Create a standardized endpoint used in all client calls
def getEndpoint(reactor, host, port, timeout=30, bindAddress=None, socksHost=None,socksPort=None):
	if socksHost != None:
		timeout = timeout * 2; # allow extra time for SOCKS setup; experience shows this is needed
		endpoint = twisted.internet.endpoints.clientFromString(reactor,"tcp:" + \
			   twisted.internet.endpoints.quoteStringArgument(socksHost) + ":" + \
			   str(socksPort) + ":timeout=" + str(timeout))
		endpoint.realHost = host
		endpoint.realPort = port
		endpoint.socksHost = socksHost
		endpoint.socksPort = socksPort
		endpoint.socksEndpoint = True
	else:
		endpoint = twisted.internet.endpoints.clientFromString(reactor,"tcp:" + \
			   twisted.internet.endpoints.quoteStringArgument(host) + ":" + \
			   str(port) + ":timeout=" + str(timeout))
		endpoint.realHost = host
		endpoint.realPort = port
		endpoint.socksEndpoint = False
	return endpoint

class ClientTLSContext(twisted.internet.ssl.ClientContextFactory):
    isClient = 1
    def getContext(self):
        return OpenSSL.SSL.Context(OpenSSL.SSL.TLSv1_2_METHOD)

class clientProtocol(twisted.protocols.basic.LineReceiver):
	def __init__(self,callback,context,timeout,logCallback = None):
		self.logger = logging.getLogger(__name__)
		self.command = "CONNECT"
		self.completionCallback = callback
		self.completionContext = context
		self.timeout = timeout
		self.timeoutRemaining = timeout
		self.timeoutInterval = 5
		self.connectionClosed = False
		self.receiveLineCallback = None
		self.textdata = [ ]
		self.bindata = None
		self.socksConnecting = 0
		self.serverCertificate = None
		self.logCallback = logCallback
		self.inBinarySend = False
		twisted.internet.reactor.callLater(self.timeoutInterval,self.timeoutCheck)

	def changeCallback(self,callback):
		self.completionCallback = callback

	def loggedWrite(self,data):
		if self.logCallback != None:
			for line in data.split('\n'):
				line = line.rstrip('\r\n')
				if line != '':
					self.logCallback('>',line)
		self.transport.write(data)

	def openConnection(self,endpoint,skipTLS = False,userhash = None,authkey = None):
		if self.logCallback != None:
			if endpoint.socksEndpoint:
				self.logCallback('C',"Connecting to socks proxy %s port %i for host %s port %i" % (endpoint.socksHost,endpoint.socksPort,endpoint.realHost,endpoint.realPort))
			else:
				self.logCallback('C',"Connecting directly to host %s port %i" % (endpoint.realHost,endpoint.realPort))
		self.endpoint = endpoint
		self.skipTLS = skipTLS
		self.userhash = userhash
		self.authkey = authkey
		self.session = twisted.internet.endpoints.connectProtocol(endpoint,self)
		self.session.addErrback(self.connectFailed)
	
	def connectionMade(self):
		self.inBinarySend = False
		if self.endpoint.socksEndpoint:
			if self.logCallback != None:
				self.logCallback('C',"Connected to socks proxy %s port %i for host %s port %i" % (self.endpoint.socksHost,self.endpoint.socksPort,self.endpoint.realHost,self.endpoint.realPort))
			# socks5 login with no authentication
			socksLogin = struct.pack('>BBB',5,1,0)
			self.setRawMode()
			self.socksConnecting = 1
			self.bindata = ""
			self.transport.write(socksLogin)
			self.expbytes = 2 # length of expected socks reply
			self.timeoutRemaining = self.timeout
			self.logger.debug("sending socks auth")
		else:
			if self.logCallback != None:
				self.logCallback('C',"Connected directly to host %s port %i" % (self.endpoint.realHost,self.endpoint.realPort))
			self.receiveLineCallback = self.greetingReceived
			self.timeoutRemaining = self.timeout
			 #DBGOUT#self.logger.debug("Connected to server")
	
	def socksReply1Received(self):
		if self.bindata[1] != '\x00': # failed to accept no auth
			self.logger.debug("socks proxy auth failed")
			self.connectFailed("socks proxy auth failed " + self.bindata[0:2].encode('hex'))
			return

		m = re_ipv4.match(self.endpoint.realHost)
		if m:
			b1 = int(m.group(1))
			b2 = int(m.group(2))
			b3 = int(m.group(3))
			b4 = int(m.group(4))
			socksConnectRequest = struct.pack('>BBBBBBBBH',5,1,0,1,b1,b2,b3,b4,self.endpoint.realPort)
		else:
			realHostU = self.endpoint.realHost.encode('utf-8')
			socksConnectRequest = struct.pack('>BBBBB',5,1,0,3,len(realHostU)) + realHostU + struct.pack('>H',self.endpoint.realPort)

		self.logger.debug("sending socks connect string " + socksConnectRequest.encode('hex'))
		self.socksConnecting = 2
		self.bindata = ""
		self.transport.write(socksConnectRequest)
		self.expbytes = 3 # length of expected socks reply
		self.timeoutRemaining = self.timeout


	def socksReply2Received(self):
		self.logger.debug("socks reply received: " + self.bindata.encode('hex'))
		if self.bindata[1] == '\x00': # success
			#DBGOUT#self.logger.debug("socks proxy connection successful")
			self.setLineMode(self.bindata[self.expbytes:])
			self.socksConnecting = 0
			self.receiveLineCallback = self.greetingReceived
			self.timeoutRemaining = self.timeout
			self.bindata = None
			self.expbytes = 0
		else:
			self.logger.debug("socks proxy connection failed")
			self.connectFailed("socks proxy connect failed " + self.bindata[1].encode('hex'))

	def lineReceived(self,line):
		#DBGOUT#self.logger.debug("Received: "+line)
		if self.logCallback != None:
			self.logCallback('<',line)
		self.timeoutRemaining = self.timeout
		self.receiveLineCallback(line)

	def greetingReceived(self,line):
		match = re_greeting.match(line)
		if match:
			#DBGOUT#self.logger.debug("Received server greeting banner")
			self.textdata.append(line)
			if self.skipTLS == True:
				self.completionCallback(self,self.completionContext,self.command,"CONNECTED",self.textdata,self.bindata)
			else:
				#DBGOUT#self.logger.debug("Sending TLS setup")
				self.loggedWrite("STARTTLS\r\n")
				self.receiveLineCallback = self.tlsProceedReceived
			return

		match = re_busy_greeting.match(line)
		if match:
			#DBGOUT#self.logger.debug("Got BUSY greeting")
			self.connectFailed("Server busy")

	def tlsProceedReceived(self,line):
		if line.upper() == 'PROCEED':
			ctx = ClientTLSContext()
			self.transport.startTLS(twisted.internet.ssl.CertificateOptions(method = OpenSSL.SSL.TLSv1_2_METHOD))
			self.receiveLineCallback = self.tlsDoneReceived

	def tlsDoneReceived(self,line):
		if line.upper() == 'ENCRYPTED':
			self.serverCertificate = self.transport.getPeerCertificate()
			#DBGOUT#self.logger.debug("Server cert typeof " + str(type(self.serverCertificate)) +
#				" text " + str(self.serverCertificate) + 
# 				" type "+ str(self.serverCertificate.get_signature_algorithm()) +
# 				" subject " + str(self.serverCertificate.get_subject()) +
# 				" sn " + str(self.serverCertificate.get_serial_number()) +
# 				" digest " + str(self.serverCertificate.digest('sha1')) +
# 				" notBefore " + str(self.serverCertificate.get_notBefore()) +
# 				" notAfter " + str(self.serverCertificate.get_notAfter())
#				)
				
			if self.userhash == None or self.authkey == None:
				self.completionCallback(self,self.completionContext,self.command,"CONNECTED",self.textdata,self.bindata)
			else:
				self.loggedWrite("LOGIN " + self.userhash + " " + self.authkey + "\r\n")
				self.receiveLineCallback = self.loginResponseReceived

	def loginResponseReceived(self,line):
		if line.upper() == 'DONE':
			self.completionCallback(self,self.completionContext,self.command,"CONNECTED",self.textdata,self.bindata)
		else:
			self.connectFailed("Login failed")

	def sendCommand(self,command,context,throttle_kbps = None):
		self.command = command
		self.completionContext = context
		self.timeoutRemaining = self.timeout
		self.textdata = [ ]
		self.bindata = None

		if type(self.command) == str:
			#DBGOUT#self.logger.debug("Command: %s",self.command)	
			if self.logCallback != None:
				self.logCallback('>',self.command)
			self.sendLine(self.command)
			self.receiveLineCallback = self.receiveGetFirstLine
		elif type(self.command) == tuple:
			#DBGOUT#self.logger.debug("Command: %s",self.command[0])	
			self.receiveLineCallback = self.receiveStoreResult
			if len(self.command) == 2:
				if self.command[1] == None: # no text body, for REPLOGIN
					if self.logCallback != None:
						self.logCallback('>',self.command[0])
					self.sendLine(self.command[0])
				else:
					self.loggedWrite(self.command[0] + "\r\n" + \
						self.command[1].replace("\r","").replace("\n","\r\n") + \
						"EndBlock\r\n")
			else:
				self.loggedWrite(self.command[0] + "\r\n" + \
					self.command[1].replace("\r","").replace("\n","\r\n") + \
					"Data: " + str(len(self.command[2])) + "\r\n")
				self.inBinarySend = True
				if throttle_kbps == None:
					self.transport.write(self.command[2]) # Not logging data
				else:
					self.throttle_kbps = throttle_kbps
					self.throttle_block = self.command[2]
					self.throttle_blocksize = int(self.throttle_kbps * 1024 * throttle_send_freq)
					self.throttle_ptr = 0
					self.sendThrottled()

	def sendThrottled(self):
		if (len(self.throttle_block) - self.throttle_ptr) <= self.throttle_blocksize:					
			self.transport.write(self.throttle_block[self.throttle_ptr:])
			self.throttle_block = None
		else:
			endptr = self.throttle_ptr + self.throttle_blocksize
			self.transport.write(self.throttle_block[self.throttle_ptr:endptr])
			self.throttle_ptr = endptr
			twisted.internet.reactor.callLater(throttle_send_freq,self.sendThrottled)
			
	def receiveStoreResult(self,line):
		self.inBinarySend = False
		self.completionCallback(self,self.completionContext,self.command,line,self.textdata,self.bindata)
		#DBGOUT#self.logger.debug("Got store result: "+line)
	
	def receiveGetFirstLine(self,line):
		self.textdata = [ ]
		lineU = line.upper()
		if lineU == 'NOT FOUND' or lineU == 'INVALID COMMAND' or lineU == 'FAILED':
			#DBGOUT#self.logger.debug("Got not found: "+line)
			self.completionCallback(self,self.completionContext,self.command,line,self.textdata,self.bindata)
		else:
			self.receiveLineCallback = self.receiveGetNextLine
			self.receiveGetNextLine(line)
	
	def receiveGetNextLine(self,line):
		lineU = line.upper()
		if lineU[0:9] == 'PADDING: ':
			return
		if lineU == 'ENDBLOCK':
			#DBGOUT#self.logger.debug("Got line only reply")
			self.completionCallback(self,self.completionContext,self.command,"FOUND",self.textdata,self.bindata)
			return
		# if data
		match = re_data.match(line)
		if match:
			self.textdata.append(line)
			self.expbytes = int(match.group(1))
			#DBGOUT#self.logger.debug("raw mode enabled %i",self.expbytes)
			self.bindata = ""
			self.setRawMode()
			return
			
		# default response
		self.textdata.append(line)

	def rawDataReceived(self,data):
		self.timeoutRemaining = self.timeout
		self.bindata += data
		#DBGOUT#self.logger.debug("raw received %i %i",len(data),len(self.bindata))
		if len(self.bindata) >= self.expbytes:
			if self.socksConnecting == 1:
				self.socksReply1Received()
			elif self.socksConnecting == 2:
				self.socksReply2Received()
			else:
				self.setLineMode(self.bindata[self.expbytes:])
				self.bindata = self.bindata[0:self.expbytes]
				#DBGOUT#self.logger.debug("Got line and data reply")
				self.completionCallback(self,self.completionContext,self.command,"FOUND",self.textdata,self.bindata)

	def connectionLost(self,reason):
		self.inBinarySend = False
		if type(reason) != str:
			reason = str(reason)
		self.logger.debug("Connection closed: %s",reason)
		if self.connectionClosed == False:
			self.textdata.append(reason)
			self.connectionClosed = True
			self.completionCallback(self,self.completionContext,self.command,"DISCONNECT",self.textdata,self.bindata)

	def timeoutCheck(self):
		#DBGOUT#self.logger.debug("timeout check %i",self.timeoutRemaining)
		if self.connectionClosed == True:
			# timeout after closed
			return
		if self.timeoutRemaining <= 0:
			self.transport.abortConnection()
			self.connectionClosed = True
			self.completionCallback(self,self.completionContext,self.command,"RECEIVE TIMEOUT",self.textdata,self.bindata)
		else:
			if self.inBinarySend == False:
				self.timeoutRemaining -= self.timeoutInterval
			twisted.internet.reactor.callLater(self.timeoutInterval,self.timeoutCheck)
	
	def connectFailed(self,reason):
		self.inBinarySend = False
		if type(reason) != str:
			reason = str(reason)
		self.textdata.append(reason)
		self.connectionClosed = True
		self.completionCallback(self,self.completionContext,self.command,"CONNECT FAILED",self.textdata,self.bindata)


# EOF
