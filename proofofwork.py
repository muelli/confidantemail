import hashlib

def generate_proof_of_work(data,nbits,nmatches):
	""" Returns a birthday-type proof of work string """
	if nmatches < 2:
		nmatches = 2
	nbytes = int((nbits+7)/8)
	wholebytes = int(nbits/8)
	extrabits = 8 - (nbits % 8)
	explen = 9*nmatches - 1
	mask = (0xff << extrabits) & 0xff
	#DBGOUT#print "proof of work: nbits = ",nbits,", nmatches=",nmatches,", data=", len(data)
	nonce = 0
	matches = { }
	keep_looking = True

	attempts = 0
	while keep_looking:
		hash = hashlib.new('sha256')
		nonce_txt = format(nonce,'09x')
		hash.update(nonce_txt)
		hash.update(data)
		dgst = hash.digest()
		if (nbytes == wholebytes):
			prefix = dgst[0:nbytes]
		else:
			prefix = dgst[0:wholebytes] + chr(ord(dgst[wholebytes]) & mask)
		if prefix not in matches:
			matches[prefix] = nonce_txt
		else:
			new_matches = matches[prefix] + "," + nonce_txt
			matches[prefix] = new_matches
			if len(new_matches) >= explen:
				keep_looking = False
			else:
				matches[prefix] = new_matches
		nonce = (nonce + 1) & 0xffffffff
#		if attempts % 10000 == 0:
#			print "proof of work: attempt ",attempts
		attempts +=1
	return ("bd,"+new_matches)
			
def verify_proof_of_work(data,proof_of_work):
	""" Returns number of bits of relatedness, and number of hashes found """
	n = -1
	max_nbits = 256
	unique_nonces = set() # prevent sneaky reuse
	for nonce in proof_of_work.split(','):
		if nonce in unique_nonces:
			continue
		unique_nonces.add(nonce)
		this_nbits = 0
		if ((nonce == 'bd') and (n < 0)):
			n = 0
		elif n == 0:
			hash = hashlib.new('sha256')
			hash.update(nonce)
			hash.update(data)
			lastdgst = hash.digest()
			n += 1
		elif n >= 1:
			hash = hashlib.new('sha256')
			hash.update(nonce)
			hash.update(data)
			thisdgst = hash.digest()
			i = 0
			while thisdgst[i] == lastdgst[i]:
				i += 1
				this_nbits += 8
			lastbyte = ord(lastdgst[i])
			thisbyte = ord(thisdgst[i])
			mask = 0x80
			while mask < 0xff:
				if thisbyte & mask == lastbyte & mask:
					this_nbits += 1
					mask = 0x80 + (mask >> 1)
				else:
					break	
			if this_nbits < max_nbits:
				max_nbits = this_nbits
			n += 1
		#DBGOUT#print n, nonce, max_nbits, this_nbits
	if n < 2:
		max_nbits = 0
	return max_nbits,n
		
