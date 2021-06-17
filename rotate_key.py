import sys
import traceback
import subprocess
import logging
import datetime
import time
import os
import zipfile
import global_config

# thank you http://eyalarubas.com/python-subproc-nonblock.html
from threading import Thread
from Queue import Queue, Empty

class NonBlockingStreamReader:

	def __init__(self, stream):
		'''
		stream: the stream to read from.
				Usually a process' stdout or stderr.
		'''
		self._s = stream
		self._q = Queue()

		def _populateQueue(stream, queue):
			'''
			Collect lines from 'stream' and put them in 'queue'.
			'''
			while True:
				line = stream.readline()
				if line:
					line = line.rstrip('\r\n')
					queue.put(line)
				else:
					queue.put('## EOF ##')
					break
					#raise UnexpectedEndOfStream
		self._t = Thread(target = _populateQueue,
				args = (self._s, self._q))
		self._t.daemon = True
		self._t.start() #start collecting lines from the stream

	def readline(self, timeout = None):
		try:
			return self._q.get(block = timeout is not None,
					timeout = timeout)
		except Empty:
			return None
#class UnexpectedEndOfStream(Exception): pass

f_validity = 1
f_keylen = 2
f_keyalg = 3
f_keyid = 4
f_credate = 5
f_expdate = 6
f_cap = 11
f_curve = 16

# Due to the way revkey works (key X where X is an offset, followed by the
# revkey command with no parameter) it is quite easy to revoke the entire key
# instead of the subkey, by providing an invalid offset. It is therefore
# necessary to back up the keyring, check the results, and restore the
# keyring if it got messed up.

class rotate_key:

	def __init__(self,gpgpath,homedir,keyid,output):
		self.logger = logging.getLogger(__name__)
		self.gpgpath = gpgpath
		self.homedir = homedir
		self.gpghome = homedir + os.sep + 'gpg'
		self.gpgbackup = homedir + os.sep + 'gpgbak.zip'
		self.keyid = keyid.lower()
		self.OutputText = output

	def backup_gpg(self):
		zipobj = zipfile.ZipFile(self.gpgbackup,'w')	
		rlen = len(self.gpghome) + 1
		for root,dirs,files in os.walk(self.gpghome):
			for f in files:
				fpath = root + os.sep + f
				if os.path.isfile(fpath):
					subpath = root[rlen:] + os.sep + f
					zipobj.write(fpath,subpath)
		zipobj.close()

	def catalog_backup(self):
		zipobj = zipfile.ZipFile(self.gpgbackup,'r')
		self.OutputText("Backup contents:")
		for f in zipobj.infolist():
			if f.file_size > 0: # no point showing the empty lockfiles
				self.OutputText("%s, %i bytes, modified %04i-%02i-%02i %02i:%02i:%02i" % (f.filename,f.file_size,
					f.date_time[0],f.date_time[1],f.date_time[2],f.date_time[3],f.date_time[4],f.date_time[5]))
		zipobj.close()

	def restore_gpg(self):
		try:
			zipobj = zipfile.ZipFile(self.gpgbackup,'r')
			zipobj.extractall(self.gpghome)
			zipobj.close()
			self.OutputText("GPG keyring restored from backup")
		except Exception as exc:
			self.logger.debug("Exception: %s",traceback.format_exc())
			self.OutputText("Exception in restore: " + str(exc))
			self.OutputText("You need to manually restore the backup " + self.gpgbackup + " to the directory " + self.gpghome)
			return False
		return True

	def destroy_file(self,filepath):
		wipev1 = "\xaa"
		wipev2 = "\x55"
		for i in range(9):
			wipev1 = wipev1 + wipev1
			wipev2 = wipev2 + wipev2
		fp = open(filepath, "r+")
		for i in range((os.path.getsize(filepath) / 512) + 16):
			fp.write(wipev1)
		fp.flush()
		fp.seek(0)
		for i in range((os.path.getsize(filepath) / 512) + 16):
			fp.write(wipev2)
		fp.flush()
		fp.close()
		os.unlink(filepath)

	def get_subkey_ids(self,keyid):
		cur_enc_sk = [ ]
		rev_enc_sk = [ ]
		cur_withdate = [ ]
		rev_withdate = [ ]
		keyalg_prev = None
		keylen_prev = None
		keycurve_prev = None
		keyalg = None
		keylen = None
		keycurve = None
		subkey_to_offset = dict()
		cmdline =  [ self.gpgpath,'--homedir',self.gpghome,'--list-keys','--with-fingerprint','--with-colons' ]
		if sys.platform == 'win32':
			# http://stackoverflow.com/questions/7006238/how-do-i-hide-the-console-when-i-use-os-system-or-subprocess-call/7006424#7006424
			CREATE_NO_WINDOW = 0x08000000
			cmdh = subprocess.Popen(cmdline,bufsize=16384,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,shell = False,creationflags = CREATE_NO_WINDOW)
		else:
			cmdh = subprocess.Popen(cmdline,bufsize=16384,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,shell = False)
		cmdh.stdin.close() # undefined stdin -> Windows fails
		output = cmdh.stdout.read()
		cmdh.stdout.close()

		this_key = False
		offset = 0
		#print "Looking for " + keyid
		lastLine = ""
		for line in output.split('\n'):
			lineL = line.lower()
			#print this_key,line
			# Fix below for GPG 2.1.15 which emits a fpr after each subkey
			if lineL[0:4] == 'fpr:' and lastLine[0:4] == 'pub:':
				if lineL.find(keyid) >= 0:
					this_key = True
				else:
					this_key = False
			elif lineL[0:4] == 'pub:':
				fields = lineL.split(':')
				keylen_prev = fields[f_keylen]
				keyalg_prev = fields[f_keyalg]
				if len(fields) >= (f_curve + 1):
					keycurve_prev = fields[f_curve]
				#print "got len and alg and curve",keylen_prev,keyalg_prev,keycurve_prev
			if this_key == False:
				lastLine = lineL
				continue
			if keylen_prev != None and keylen == None:
				keylen = keylen_prev
				keyalg = keyalg_prev
				keycurve = keycurve_prev
				#print "copied len and alg and curve",keylen,keyalg,keycurve
			if lineL[0:4] == 'sub:':
				fields = lineL.split(':')
				credate = fields[f_credate]
				if credate.find('-') < 0: # numeric timestamp
					credate = datetime.datetime.fromtimestamp(long(credate)).strftime("%Y-%m-%d")
				offset += 1
				subkey_to_offset[fields[f_keyid]] = offset
				#print 'subkey ' + fields[f_keyid] + ' val ' + fields[f_validity] + ' cap ' + fields[f_cap]
				if fields[f_validity] != 'r' and fields[f_cap].find('e') >= 0:
					cur_enc_sk.append(fields[f_keyid])
					cur_withdate.append( (fields[f_keyid],credate) )
				elif fields[f_validity] == 'r' and fields[f_cap].find('e') >= 0:
					rev_enc_sk.append(fields[f_keyid])
					rev_withdate.append( (fields[f_keyid],credate) )
			lastLine = lineL
		return cur_enc_sk,rev_enc_sk,cur_withdate,rev_withdate,subkey_to_offset,keyalg,keylen,keycurve

	def add_revoke_delete_subkeys(self,keyid,sk_add,sk_add_algo,sk_add_size,sk_add_curve,sk_rev,sk_del,passphrase):
		cmdline = [ self.gpgpath, '--homedir', self.gpghome, '--no-sk-comment',
			'--status-fd', '1', '--no-tty', '--command-fd', '0',
			'--expert', '--edit-key', keyid ]
		try:
			if sys.platform == 'win32':
				# http://stackoverflow.com/questions/7006238/how-do-i-hide-the-console-when-i-use-os-system-or-subprocess-call/7006424#7006424
				si = subprocess.STARTUPINFO()
				si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
				cmdh = subprocess.Popen(cmdline,bufsize=16384,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,shell = False,startupinfo = si)
			else:
				cmdh = subprocess.Popen(cmdline,bufsize=16384,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,shell = False)
			output = NonBlockingStreamReader(cmdh.stdout)
			failure = None	

			if sk_rev != None and len(sk_rev) > 0:
				self.OutputText('Revoking old encryption subkey')
			while sk_rev != None and len(sk_rev) > 0:
				rev_keyid = sk_rev.pop(0)	
				got_expected = False
				passphrase_tried = False
				iter_limit = 100
				while True:
					iter_limit -= 1
					if iter_limit <= 0:
						break
					line = output.readline(10)
					if line == None:
						failure = 'REV timeout'
						break
					self.logger.debug("%s",line)
					if line.find('keyedit.prompt') >= 0:
						if got_expected == True:
							cmdh.stdin.write('\n') # no op to force another prompt for next time
							cmdh.stdin.flush()
							break	
						if rev_keyid != None:
							cmdh.stdin.write('key ' + str(rev_keyid) + '\n')
							#print 'key ' + str(rev_keyid) + '';
							rev_keyid = None
						else:
							cmdh.stdin.write('revkey\n')
							#print 'revkey';
						cmdh.stdin.flush()
					elif line.find('passphrase.enter') >= 0:
						if passphrase_tried == True:
							failure = 'REV passphrase failed'
							break
						cmdh.stdin.write(passphrase.encode('utf-8') + '\n')
						#print passphrase.encode('utf-8') + '';
						cmdh.stdin.flush()
						passphrase_tried = True
					elif line.find('keyedit.revoke.subkey.okay') >= 0:
						cmdh.stdin.write('yes\n')
						#print 'yes';
						cmdh.stdin.flush()
					elif line.find('ask_revocation_reason.code') >= 0:
						cmdh.stdin.write('2\n')
						#print '2';
						cmdh.stdin.flush()
					elif line.find('ask_revocation_reason.text') >= 0:
						cmdh.stdin.write('\n')
						#print '';
						cmdh.stdin.flush()
					elif line.find('ask_revocation_reason.okay') >= 0:
						cmdh.stdin.write('yes\n')
						#print 'yes';
						cmdh.stdin.flush()
						got_expected = True
					elif line.find('## EOF ##') >= 0:
						break
				if got_expected == False:
					failure = 'REV unknown'
					break
			
			if failure != None:
				cmdh.kill()
				return False,failure

			if sk_del != None and len(sk_del) > 0:
				self.OutputText('Deleting revoked encryption subkey')
			while sk_del != None and len(sk_del) > 0:
				del_keyid = sk_del.pop(0)	
				got_expected = False
				passphrase_tried = False
				iter_limit = 100
				while True:
					iter_limit -= 1
					if iter_limit <= 0:
						break
					line = output.readline(10)
					if line == None:
						failure = 'DEL timeout'
						break
					self.logger.debug("%s",line)
					if line.find('keyedit.prompt') >= 0:
						if got_expected == True:
							cmdh.stdin.write('\n') # no op to force another prompt for next time
							cmdh.stdin.flush()
							break	
						if del_keyid != None:
							cmdh.stdin.write('key ' + str(del_keyid) + '\n')
							#print 'key ' + str(del_keyid) + '';
							del_keyid = None
						else:
							cmdh.stdin.write('delkey\n')
							#print 'delkey';
						cmdh.stdin.flush()
					elif line.find('passphrase.enter') >= 0:
						if passphrase_tried == True:
							failure = 'DEL passphrase failed'
							break
						cmdh.stdin.write(passphrase.encode('utf-8') + '\n')
						#print passphrase.encode('utf-8') + '';
						cmdh.stdin.flush()
						passphrase_tried = True
					elif line.find('keyedit.remove.subkey.okay') >= 0:
						cmdh.stdin.write('yes\n')
						#print 'yes';
						cmdh.stdin.flush()
						got_expected = True
					elif line.find('## EOF ##') >= 0:
						break
				if got_expected == False:
					failure = 'DEL unknown'
					break

			if failure != None:
				cmdh.kill()
				return False,failure

			while sk_add > 0:
				self.OutputText('Creating new encryption subkey')
				got_expected = False
				passphrase_tried = False
				iter_limit = 100
				while True:
					iter_limit -= 1
					if iter_limit <= 0:
						break
					line = output.readline(20)
					if line == None:
						failure = 'ADD timeout'
						break
					self.logger.debug("%s",line)
					if line.find('keyedit.prompt') >= 0:
						cmdh.stdin.write('addkey\n')
						#print 'addkey';
						cmdh.stdin.flush()
					elif line.find('passphrase.enter') >= 0:
						if passphrase_tried == True:
							failure = 'ADD passphrase failed'
							break
						cmdh.stdin.write(passphrase.encode('utf-8') + '\n')
						#print passphrase.encode('utf-8') + '';
						cmdh.stdin.flush()
						passphrase_tried = True
					elif line.find('keygen.algo') >= 0:
						cmdh.stdin.write(sk_add_algo + '\n')
						#print sk_add_algo + '';
						cmdh.stdin.flush()
					elif line.find('keygen.size') >= 0:
						cmdh.stdin.write(sk_add_size + '\n')
						#print sk_add_size + '';
						cmdh.stdin.flush()
					elif line.find('keygen.curve') >= 0:
						cmdh.stdin.write(sk_add_curve + '\n')
						#print sk_add_curve + '';
						cmdh.stdin.flush()
					elif line.find('keygen.valid') >= 0:
						cmdh.stdin.write('0\n')
						#print '0';
						cmdh.stdin.flush()
					elif line.find('PROGRESS') >= 0:
						iter_limit += 1 # ElG exceeds otherwise
					elif line.find('KEY_CREATED') >= 0:
						got_expected = True
						sk_add -= 1
						break
					elif line.find('## EOF ##') >= 0:
						break
				if got_expected == False:
					failure = 'ADD unknown'
					break
	
			if failure != None:
				cmdh.kill()
				return False,failure

			self.OutputText('Saving changes')
			iter_limit = 100
			got_expected = True
			while True:
				iter_limit -= 1
				if iter_limit <= 0:
					break
				line = output.readline(10)
				if line == None:
					failure = 'DEL timeout'
					break
				self.logger.debug("%s",line)
				if line.find('keyedit.prompt') >= 0:
					cmdh.stdin.write('quit\n')
					#print 'quit';
					cmdh.stdin.flush()
				elif line.find('keyedit.save.okay') >= 0:
					cmdh.stdin.write('yes\n')
					#print 'yes';
					cmdh.stdin.flush()
				elif line.find('## EOF ##') >= 0:
					got_expected = True
					break
				
			if failure != None:
				cmdh.kill()
				return False,failure

			self.OutputText('Done updating key')
			return True,None

		except Exception as exc:
			self.logger.debug("Exception: %s",traceback.format_exc())
			try:
				cmdh.kill()
			except Exception as exc2:
				self.logger.debug("Exception2: %s",traceback.format_exc())
				pass
			return False,"Exception thrown: " + str(exc)

	def keyalg_convert(self,keyalg,keycurve):
		keyalg_text = 'None'
		keyalg_gen = None
		keycurve_gen = None
		if keyalg == '1':
			keyalg_text = 'RSA'
			keyalg_gen = '6'
		elif keyalg == '17':
			keyalg_text = 'ElGamal'
			keyalg_gen = '5'
		elif (keyalg == '19' or keyalg == '22') and keycurve != None:
			keyalg_gen = '12'
			keyalg_text = 'ECC ' + keycurve
			if keycurve == 'nistp256':
				keycurve_gen = '2'
			elif keycurve == 'nistp384':
				keycurve_gen = '3'
			elif keycurve == 'nistp521':
				keycurve_gen = '4'
			elif keycurve == 'brainpoolp256r1':
				keycurve_gen = '5'
			elif keycurve == 'brainpoolp384r1':
				keycurve_gen = '6'
			elif keycurve == 'brainpoolp512r1':
				keycurve_gen = '7'
			elif keycurve == 'ed25519':
				keycurve_gen = '1'
			elif keycurve == 'secp256k1':
				keycurve_gen = '9'
		#print "alg",keyalg,"curve",len(keycurve),keycurve,keycurve_gen,(keycurve == 'ed25519')
		return keyalg_text,keyalg_gen,keycurve_gen

	def show_current_subkeys(self): # return date of active subkey
		cur_enc_sk_before,rev_enc_sk_before,cur_withdate,rev_withdate,subkey_to_offset,keyalg,keylen,keycurve = self.get_subkey_ids(self.keyid)
		keyalg_text,keyalg_gen,keycurve_gen = self.keyalg_convert(keyalg,keycurve)

		latest_subkey_date = None
		self.OutputText("Current encryption subkeys:")
		for key,credate in cur_withdate:
			if latest_subkey_date == None or latest_subkey_date < credate:
				latest_subkey_date = credate
			self.OutputText(key + ' (active, created ' + credate + ')')
		for key,credate in rev_withdate:
			self.OutputText(key + ' (revoked, created ' + credate + ')')
		if len(cur_withdate) == 0 and len(rev_withdate) == 0:
			self.OutputText("No subkeys found")
		if latest_subkey_date != None:
			key_age = (datetime.datetime.now() - \
				datetime.datetime.strptime(latest_subkey_date,"%Y-%m-%d")).days
			if key_age == 0:
				self.OutputText("Key last changed today")
			elif key_age == 1:
				self.OutputText("Key last changed yesterday")
			else:
				self.OutputText("Key last changed " + str(key_age) + " days ago")
			if key_age < (global_config.renew_age_key / 86400):
				self.OutputText("Warning: this key was recently changed. If you change it again now, you could be unable to decrypt some incoming email.")

	def do_key_rotation(self,passphrase):
		cur_enc_sk_before,rev_enc_sk_before,cur_withdate,rev_withdate,subkey_to_offset,keyalg,keylen,keycurve = self.get_subkey_ids(self.keyid)
		keyalg_text,keyalg_gen,keycurve_gen = self.keyalg_convert(keyalg,keycurve)

		self.OutputText("Subkeys before rotation:")
		revkeys = [ ]
		for sk in cur_enc_sk_before:
			self.OutputText(sk + ' (active, to revoke)')
			revkeys.append(subkey_to_offset[sk])
		delkeys = [ ]
		for sk in rev_enc_sk_before:
			self.OutputText(sk + ' (revoked, to delete)')
			delkeys.append(subkey_to_offset[sk])
		self.OutputText('Key algorithm ' + keyalg_text + ', length ' + keylen)

		if len(cur_enc_sk_before) == 0:
			self.OutputText("No current encryption subkey, creating one")

		delkeys.sort()
		delkeys.reverse() # delete highest first or order gets messed up
		result,explanation = self.add_revoke_delete_subkeys(self.keyid,1,keyalg_gen,keylen,keycurve_gen,revkeys,delkeys,passphrase)
		if result == False:
			self.OutputText(explanation)
			return False
		cur_enc_sk_after,rev_enc_sk_after,cur_withdate,rev_withdate,subkey_to_offset,keyalg,keylen,keycurve = self.get_subkey_ids(self.keyid)
		keyalg_text,keyalg_gen,keycurve_gen = self.keyalg_convert(keyalg,keycurve)

		self.OutputText("\nSubkeys after rotation:")
		for sk in cur_enc_sk_after:
			self.OutputText(sk + ' (active)')
		for sk in rev_enc_sk_after:
			self.OutputText(sk + ' (revoked)')
		self.OutputText('Key algorithm ' + keyalg_text + ', length ' + keylen)
		if keyalg_gen == None or keylen == None:
			self.OutputText("Failed, unable to get key algorithm")
			return False
 		if len(cur_enc_sk_after) == 0:
			self.OutputText("Failed, no current encryption subkey found")
			return False
 		if (set(rev_enc_sk_after) >= set(cur_enc_sk_before)) == False:
			self.OutputText("Failed, not all existing subkeys were revoked")
			return False
		self.OutputText("Successfully rotated encryption subkey.")
		return True
		
	def backup_try_key_rotation(self,passphrase):
		self.OutputText("Backing up " + self.gpghome + ' to\n' + self.gpgbackup)
		try:
			self.backup_gpg()
			self.catalog_backup()
			self.OutputText("")
		except Exception as exc:
			self.logger.debug("Exception: %s",traceback.format_exc())
			self.OutputText("Exception thrown in backup: " + str(exc))
			return False
		try:
			result = self.do_key_rotation(passphrase)
			if result == False:
				self.restore_gpg()
				return False
		except Exception as exc:
			self.logger.debug("Exception: %s",traceback.format_exc())
			self.OutputText("Exception thrown: " + str(exc))
			self.restore_gpg()
			return False
		return True

	def remove_old_revoked_keys(self,keyid,passphrase = None):
		try:
			keyid = keyid.lower()
			cur_enc_sk,rev_enc_sk,cur_withdate,rev_withdate,subkey_to_offset,keyalg,keylen,keycurve = self.get_subkey_ids(keyid)
			newest_revoked_key = None	
			newest_revoked_date = None	
			for key,rev_credate in rev_withdate:
				if newest_revoked_date == None or newest_revoked_date < rev_credate:
					newest_revoked_key = key
					newest_revoked_date = rev_credate
			delkeys = [ ]
			for key in rev_enc_sk:
				if key != newest_revoked_key:
					delkeys.append(subkey_to_offset[key])
			delkeys.sort()
			delkeys.reverse() # delete highest first or order gets messed up
	
			if newest_revoked_key != None and len(delkeys) > 0:
				result,explanation = self.add_revoke_delete_subkeys(keyid,0,None,None,None,[ ],delkeys,passphrase)
				return result,explanation
			else:
				return True,'Nothing to delete'
		except Exception as exc:
			return False,str(exc)

# EOF
