import logging
import string
import re
import random
import OpenSSL
import twisted.protocols.basic
import twisted.internet.protocol
import twisted.internet.reactor
import twisted.internet.ssl
import twisted.internet.endpoints
import client

re_server_is_tor = re.compile('.*\.onion:\d+$',re.IGNORECASE)
re_server_is_i2p = re.compile('.*\.i2p:\d+$',re.IGNORECASE)

def re_order_servers(server_list,anon_first,server_connection):
	s_in = [ ]
	s_tor = [ ]
	s_i2p = [ ]
	s_dir = [ ]	
	s_out = [ ]
	s_in.extend(server_list)
	random.shuffle(s_in)
	for server in s_in:
		if re_server_is_tor.match(server):
			s_tor.append(server)
		elif re_server_is_i2p.match(server):
			s_i2p.append(server)
		else:
			s_dir.append(server)
	if server_connection == 'I2P':
		s_out.extend(s_i2p)	
		s_out.extend(s_tor)	
		s_out.extend(s_dir)	
	elif anon_first == True or server_connection == 'TOR':
		s_out.extend(s_tor)	
		s_out.extend(s_dir)	
		s_out.extend(s_i2p)	
	else:
		s_out.extend(s_dir)	
		s_out.extend(s_tor)	
		s_out.extend(s_i2p)	
	return s_out

class remote_dns_lookup:
	def __init__(self,server_list,tor_proxy,i2p_proxy,socks_proxy,use_exit_node,server_connection,timeout,log_traffic_callback,validate_cert_callback,userhash = None,authkey = None):
		self.server_list = server_list
		self.tor_proxy = tor_proxy
		self.i2p_proxy = i2p_proxy
		self.socks_proxy = socks_proxy
		self.use_exit_node = use_exit_node
		self.server_connection = server_connection
		self.timeout = timeout
		self.validate_cert_callback = validate_cert_callback
		self.userhash = userhash
		self.authkey = authkey
		self.logger = logging.getLogger(__name__)
		self.error_messages = [ ]
		self.log_traffic_callback = log_traffic_callback

	def lookup(self,lookups,callback,multiple):
		self.lookups = lookups
		self.multiple = multiple
		self.lookups_result = dict()
		self.lookup_pending = None
		self.callback = callback
		self.lookup_servers = self.server_list[7:].split(',') # skipping server=
		if len(self.lookup_servers) > 1:
			self.lookup_servers = re_order_servers(self.lookup_servers,self.use_exit_node,self.server_connection)
		self.session_terminated = False
		self.next_lookup_server()

	def next_lookup_server(self):
		if len(self.lookup_servers) == 0:
			self.logger.debug("Unable to perform all DNS TXT lookups")
			self.error_messages.append("Unable to perform all DNS TXT lookups")
		
			self.session_terminated = True
			self.lookup_finalize()
			return

		self.lookup_server = self.lookup_servers.pop(0)
		sockshost = None
		socksport = None
		if re_server_is_tor.match(self.lookup_server):
			if self.tor_proxy == None:
				self.error_messages.append("got tor server and no tor proxy configured")
				self.next_lookup_server()
				return
			sockshost,socksport = self.tor_proxy.rsplit(':',1)
		elif re_server_is_i2p.match(self.lookup_server):
			if self.i2p_proxy == None:
				self.error_messages.append("got i2p server and no i2p proxy configured")
				self.next_lookup_server()
				return
			sockshost,socksport = self.i2p_proxy.rsplit(':',1)
		elif self.use_exit_node == True:
			if self.tor_proxy == None:
				self.error_messages.append("got use exit node and no tor proxy configured")
				self.next_lookup_server()
				return
			sockshost,socksport = self.tor_proxy.rsplit(':',1)
		elif self.socks_proxy != None:
			sockshost,socksport = self.socks_proxy.rsplit(':',1)
		else:
			nethost,netport = self.lookup_server.rsplit(':',1)
			netport = int(netport)

		if socksport != None:
			socksport = int(socksport)

		nethost,netport = self.lookup_server.rsplit(':',1)
		netport = int(netport)
		self.nethost = nethost
		self.netport = netport

		endpoint = client.getEndpoint(twisted.internet.reactor,nethost,netport,self.timeout,bindAddress=None,socksHost = sockshost,socksPort = socksport)
		if sockshost != None:
			self.logger.debug("Starting connection %s %i via socks %s %i",nethost,netport,sockshost,socksport)
		else:
			self.logger.debug("Starting connection %s %i direct",nethost,netport)

		clientProt = client.clientProtocol(self.lookup_completion_callback,None,self.timeout,logCallback = self.log_traffic_callback)
		clientProt.openConnection(endpoint,userhash = self.userhash,authkey = self.authkey)

	def send_next_lookup(self,client):
		if len(self.lookups) == 0:
			send_command = "QUIT"
		else:
			if self.lookup_pending == None:
				self.lookup_pending = self.lookups.pop(0)
			send_command = "DNS TXT " + self.lookup_pending
			send_command = send_command.encode('utf-8')
		self.logger.debug("sending lookup " + send_command)
		self.logger.debug("sending lookup " + str(type(send_command)) + " " + send_command.encode("hex"))
		client.sendCommand(send_command,None)
		self.logger.debug("back from sending lookup " + send_command)

	def process_received_lookup(self,textdata):
		for line in textdata:
			lineL = line.lower()
			if lineL[0:5] == 'txt: ':
				if self.multiple == True:
					if self.lookup_pending not in self.lookups_result:
						self.lookups_result[self.lookup_pending] = [ ]
					self.lookups_result[self.lookup_pending].append(line[5:])
				else:
					self.lookups_result[self.lookup_pending] = line[5:]
					break
		
	def lookup_finalize(self):
		self.callback(self.lookups_result,self.error_messages)
		
	def lookup_completion_callback(self,client,context,command,resultmsg,textdata,bindata):
		resultL = resultmsg.lower()
		if self.session_terminated == True:
			return # ignore spurious message

		#DBGOFF#print "lookup completion result",resultL,textdata
		if resultL == "connected" and self.validate_cert_callback != None:
			validate_result = self.validate_cert_callback(self.nethost,self.netport,client.serverCertificate)
			if validate_result == False: # This abort logic is not being used and has not been checked out.
				send_command = "QUIT"
				client.sendCommand(send_command,None)
				return	

		if resultL == "connected": # new connection
			self.send_next_lookup(client)
		elif resultL == "found": # got result
			self.process_received_lookup(textdata)
			self.lookup_pending = None
			self.send_next_lookup(client)
		elif resultL == "not found": # got no result
			self.lookup_pending = None
			self.send_next_lookup(client)
		elif resultL == "failed": # server does not permit
			self.error_messages.append("Server " + self.lookup_server + " does not permit DNS TXT")
			send_command = "QUIT"
			client.sendCommand(send_command,None)
		elif resultL == "disconnect" or resultL == "connect failed" or client.connectionClosed == True:
			if self.lookup_pending == None and len(self.lookups) == 0:
				self.logger.debug("Done with all lookups")
				self.session_terminated = True
				self.lookup_finalize()
			else:
				self.next_lookup_server()
		else: # unknown but still connected
			client.sendCommand("QUIT",None)



# EOF


