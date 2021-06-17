import os
import sys

# returns in_path,gpg_path
def find_gpg():
	if sys.platform == 'win32':
		return find_gpg_windows()
	else:
		return find_gpg_unix()

def find_gpg_windows():
	try:
		for line in os.environ['PATH'].split(os.pathsep):
			gpgpath = line + os.sep + 'gpg.exe'
			if os.path.isfile(gpgpath):
				return True,gpgpath
	except Exception:
		pass

	try:
		for line in [ 'C:\\Program Files (x86)\\GNU\\GnuPG','C:\\Program Files\\GNU\\GnuPG' ]:
			gpgpath = line + os.sep + 'gpg.exe'
			if os.path.isfile(gpgpath):
				return False,gpgpath
	except Exception:
		pass

	return False,None

def find_gpg_unix():
	try:
		for line in os.environ['PATH'].split(os.pathsep):
			gpgpath = line + os.sep + 'gpg'
			if os.path.isfile(gpgpath):
				return True,gpgpath
	except Exception:
		pass
	return False,None

print find_gpg()

