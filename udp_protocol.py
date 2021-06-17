import sys
import twisted.internet.reactor
import entangled.kademlia.protocol
from entangled.kademlia import encoding,msgformat
from socket import SOL_SOCKET,SO_RCVBUF,SO_SNDBUF

class CustomKademliaProtocol(entangled.kademlia.protocol.KademliaProtocol):

	def __init__(self, node, msgEncoder=encoding.Bencode(), msgTranslator=msgformat.DefaultFormat()):	
		#DBGOUT#print "custom protocol init"
		entangled.kademlia.protocol.KademliaProtocol.__init__(self,node,msgEncoder,msgTranslator)

	def setNode(self,node):
		self._node = node
		#DBGOUT#print "set node"

	def setBuffer(self):
		required_buf = 262144
		sndbuf = self.transport.socket.getsockopt(SOL_SOCKET,SO_SNDBUF)
		rcvbuf = self.transport.socket.getsockopt(SOL_SOCKET,SO_RCVBUF)
		if rcvbuf < required_buf:
			self.transport.socket.setsockopt(SOL_SOCKET,SO_RCVBUF,required_buf)
		if sndbuf < required_buf:
			self.transport.socket.setsockopt(SOL_SOCKET,SO_SNDBUF,required_buf)
		sndbuf = self.transport.socket.getsockopt(SOL_SOCKET,SO_SNDBUF)
		rcvbuf = self.transport.socket.getsockopt(SOL_SOCKET,SO_RCVBUF)
		#DBGOUT#print "sndbuf =",sndbuf
		#DBGOUT#print "rcvbuf =",rcvbuf


