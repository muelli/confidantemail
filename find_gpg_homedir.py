import os
import sys
import subprocess
import re

# returns in_path,gpg_path
def find_gpg():
	if sys.platform == 'win32':
		in_path,gpgpath,gpgconfpath = find_gpg_windows()
		# Removed due to gnupg.py v0.37
		#if gpgpath != None and gpgpath.find(' ') >= 0:
		#	gpgpath = '"' + gpgpath + '"'
	elif sys.platform == 'darwin':
		in_path,gpgpath,gpgconfpath = find_gpg_macos()
	else:
		in_path,gpgpath,gpgconfpath = find_gpg_unix()
	return in_path,gpgpath,gpgconfpath

def find_gpg_windows():
	try:
		for line in os.environ['PATH'].split(os.pathsep):
			gpgpath = line + os.sep + 'gpg.exe'
			gpgconfpath = line + os.sep + 'gpgconf.exe'
			if not os.path.isfile(gpgconfpath):
				gpgconfpath = None
			if os.path.isfile(gpgpath):
				return True,gpgpath,gpgconfpath
	except Exception:
		pass

	try:
		# Look for local copy in the install directory first
		program_path = os.path.dirname(os.path.realpath(sys.argv[0]))
		program_path_bin = program_path + os.sep + 'bin'

		#for line in [ program_path,'c:\\Program Files (x86)\\GnuPG.v2\\bin','C:\\Program Files\\GNU\\GnuPG',program_path_bin,'C:\\Program Files (x86)\\GNU\\GnuPG\\bin','C:\\Program Files\\GNU\\GnuPG\\bin' ]:
		#for line in [ program_path,'C:\\Program Files (x86)\\GNU\\GnuPG','C:\\Program Files\\GNU\\GnuPG','C:\\Program Files (x86)\\GnuPG\\bin','C:\\Program Files\\GnuPG\\bin',program_path_bin,'C:\\Program Files (x86)\\GNU\\GnuPG\\bin','C:\\Program Files\\GNU\\GnuPG\\bin' ]:
		for line in [ program_path,program_path_bin,'C:\\Program Files (x86)\\GNU\\GnuPG','C:\\Program Files\\GNU\\GnuPG','C:\\Program Files (x86)\\GnuPG\\bin','C:\\Program Files\\GnuPG\\bin','C:\\Program Files (x86)\\GNU\\GnuPG\\bin','C:\\Program Files\\GNU\\GnuPG\\bin' ]:
			gpgpath = line + os.sep + 'gpg.exe'
			gpgconfpath = line + os.sep + 'gpgconf.exe'
			if not os.path.isfile(gpgconfpath):
				gpgconfpath = None
			if os.path.isfile(gpgpath):
				return False,gpgpath,gpgconfpath
	except Exception:
		pass

	return False,None,None

def find_gpg_macos():
	try:
		program_path = os.path.dirname(os.path.realpath(sys.argv[0]))
		bin_path = program_path + os.sep + 'bin'
		search_paths = [ program_path,bin_path,'_NOT_IN_PATH_' ]
		search_paths.append(os.environ['PATH'].split(os.pathsep))
		inpath = True
		for line in search_paths:
			if line == '_NOT_IN_PATH_':
				inpath = False
			gpgpath = line + os.sep + 'gpg'
			gpgconfpath = line + os.sep + 'gpgconf'
			if not os.path.isfile(gpgconfpath):
				gpgconfpath = None
			if os.path.isfile(gpgpath):
				return inpath,gpgpath,gpgconfpath
	except Exception:
		pass
	return False,None,None

def find_gpg_unix():
	try:
		for line in os.environ['PATH'].split(os.pathsep):
			gpgpath = line + os.sep + 'gpg2'
			gpgconfpath = line + os.sep + 'gpgconf'
			if not os.path.isfile(gpgconfpath):
				gpgconfpath = None
			if os.path.isfile(gpgpath):
				return True,gpgpath,gpgconfpath
			gpgpath = line + os.sep + 'gpg'
			if os.path.isfile(gpgpath):
				return True,gpgpath,gpgconfpath
	except Exception:
		pass
	return False,None,None

# This is the homedir for Confidant Mail files. It is unrelated to GPG.
def find_default_homedir():
	appdata = None
	if sys.platform == 'win32':
		varname = 'APPDATA'
	else:
		varname = 'HOME'
	if varname in os.environ:
		basedir = os.environ[varname]
	if basedir != None and os.path.exists(basedir):
		homedir = basedir + os.sep + 'confidantmail'
		if os.path.exists(homedir):
			return homedir
		else:
			try:
				os.mkdir(homedir)
			except Exception:
				pass
			if os.path.exists(homedir):
				return homedir
			else:
				return None
	else:
		return None
			
def find_gpg_version(gpgpath):
	isv2 = False
	gpgver = ""
	libgver = ""
	try:
		cmdline = [ gpgpath,"--version" ]
		if sys.platform == 'win32':
			# http://stackoverflow.com/questions/7006238/how-do-i-hide-the-console-when-i-use-os-system-or-subprocess-call/7006424#7006424
			CREATE_NO_WINDOW = 0x08000000
			cmdh = subprocess.Popen(cmdline,bufsize=16384,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,shell = False,creationflags = CREATE_NO_WINDOW)
		else:
			cmdh = subprocess.Popen(cmdline,bufsize=16384,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,shell = False)
		cmdh.stdin.close() # undefined stdin -> Windows fails
		gpgver_o = cmdh.stdout.read()
		cmdh.stdout.close()
		for line in gpgver_o.split('\n'):
			line = line.rstrip("\r\n")
			if (line[0:15] == 'gpg (GnuPG) 2.1') or (line[0:15] == 'gpg (GnuPG) 2.2'):
				isv2 = True
				gpgver = line[12:]
			elif line[0:15] == 'gpg (GnuPG) 1.4':
				isv2 = False
				gpgver = line[12:]
			elif line[0:10] == 'libgcrypt ':
				libgver = line[10:]
	except Exception:
		pass
	return isv2,gpgver,libgver

# Debian uses version 1.4.18-7+deb8u2 which is patched for CVE-2016-6313
# This returns True if it detects such a patched version, False otherwise
def check_gpg_version_special_case():
	re_acceptable_version = re.compile("^1\.4\.16-1ubuntu2\.4|^1\.4\.16-[2-9]ubuntu|^1\.4\.18-7\+deb8u2|^1\.4\.18-[8-9]\+deb|^1\.4\.20-1ubuntu3\.1|^1\.4\.20-[2-9]ubuntu")
	dpkg_query = '/usr/bin/dpkg-query';
	cmdline = [ dpkg_query,'-s','gnupg' ];
	if sys.platform[0:5] != 'linux':
		return False
	if os.path.exists(dpkg_query) == False:
		return False
	cmdh = subprocess.Popen(cmdline,bufsize=16384,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,shell = False)
	cmdh.stdin.close() # undefined stdin -> Windows fails
	gpgver_o = cmdh.stdout.read()
	cmdh.stdout.close()
	for line in gpgver_o.split('\n'):
		line = line.rstrip("\r\n")
		if line[0:9] == 'Version: ':
			if re_acceptable_version.match(line[9:]):
				return True
	return False

def check_libgcrypt_version_special_case():
	re_acceptable_version = re.compile("^1\.6\.2-4ubuntu2\.1|^1\.6\.2-4|^1\.6\.3-2|^1\.6\.3-2\+deb8u2|^1\.6\.3-2\+deb8u4|^1\.6\.5-2|^1\.6\.5-2ubuntu0\.2|^1\.6\.6.*|^1\.6\.[789].*|^1\.7\.2-2|^1\.7\.2-2ubuntu1|^1\.7\.3.*|^1\.7\.[456789].*")
	dpkg_query = '/usr/bin/dpkg-query';
	cmdline = [ dpkg_query,'-s','libgcrypt20' ];
	if sys.platform[0:5] != 'linux':
		return False
	if os.path.exists(dpkg_query) == False:
		return False
	cmdh = subprocess.Popen(cmdline,bufsize=16384,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,shell = False)
	cmdh.stdin.close() # undefined stdin -> Windows fails
	gpgver_o = cmdh.stdout.read()
	cmdh.stdout.close()
	for line in gpgver_o.split('\n'):
		line = line.rstrip("\r\n")
		if line[0:9] == 'Version: ':
			if re_acceptable_version.match(line[9:]):
				return True
	return False

# MacOS needs the gpg-config edited to use the GUI pinentry, otherwise you
# cannot unlock the GPG key (gpg2 only).
def macos_fix_pinentry(gnupg_path,gnupg_homedir):
	pinentry_path = re.sub("/bin/gpg$","/pinentry-mac/0.9.4/pinentry-mac.app/Contents/MacOS/pinentry-mac",gnupg_path)
	scdaemon_path = re.sub("/bin/gpg$","/libexec/scdaemon",gnupg_path)
	gpg_config = gnupg_homedir + os.sep + 'gpg-agent.conf'
	addline1 = "# CM_LEAVE_ALONE=NO <--- change to YES to prevent further modification"
	addline2 = 'pinentry-program "' + pinentry_path + '"'
	addline3 = 'scdaemon-program "' + scdaemon_path + '"'
	config_text = None
	re_leave_alone = re.compile("^# CM_LEAVE_ALONE=.*")
	re_leave_alone_yes = re.compile("^# CM_LEAVE_ALONE=[yY][eE][sS].*")
	re_pinentry_program = re.compile("^\s*pinentry-program .*")
	re_scdaemon_program = re.compile("^\s*scdaemon-program .*")
	need_to_write = True
	found1 = False
	found2 = False
	found3 = False
	try:
		config_file = open(gpg_config,'r')
		config_text = config_file.read()
		config_file.close()
	except IOError:
		pass
	config_text_out = list()
	if config_text != None:
		for line in config_text.split("\n"):
			line = line.rstrip("\r\n")
			if re_leave_alone_yes.match(line):
				need_to_write = False
				break
			elif re_leave_alone.match(line):
				found1 = True
			elif line == addline2:
				found2 = True
			elif line == addline3:
				found3 = True
			elif re_pinentry_program.match(line):
				config_text_out.append('#CM# ' + line)
			elif re_scdaemon_program.match(line):
				config_text_out.append('#CM# ' + line)
			else:
				config_text_out.append(line)
	config_text_out.append(addline1)
	config_text_out.append(addline2)
	config_text_out.append(addline3)
	if found1 and found2 and found3:
		need_to_write = False
	if need_to_write == True:
		config_file = open(gpg_config,'w')
		for line in config_text_out:
			config_file.write(line + '\n')
		config_file.close()
	return True	



# EOF
