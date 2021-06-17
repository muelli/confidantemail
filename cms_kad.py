# Confidant Mail Server Keep-Alive Daemon
# 
# This program was written as a result of a couple of production downtime
# incidents. In one case the Server Store Thread stopped due to a corrupt
# message; in another case, due to an out-of-memory error. Messages piled up
# in the input queue until I discovered the problem and restarted the server.
# 
# The keep-alive daemon is written for Unix-style operating systems only. It
# periodically tests the server, restarts it if it is down, and alerts the
# owner by SMTP email. The daemon also checks disk space and can automatically
# run the prune operation if the disk is nearly full.
# 
# The server has a new SELFTEST command for use by the daemon. SELFTEST should
# return PASS; if it does not, the server needs a restart. The CM server has
# three major parts: the incoming-connection handler, the Server Store thread
# which validates and files incoming blocks, and the Server Send event which
# sends out blocks to other servers for replication and server relayed sending.
# 
# The PASS response from SELFTEST actually comes from the Server Store thread;
# therefore, if the thread is down, the PASS will not appear. The logic also
# checks to make sure the Server Send event ran recently.
# 
# The keep-alive daemon checks for the PASS response and also checks the input
# queue to make sure files are not accumulating. There should be no files more
# than a few minutes old in the input queue; if there are, something is wrong.
# 
# The daemon also checks the remote server in a replication pair. If one
# server is down entirely, the other server will detect this and send an
# email. By default, the remote server has to fail three times in a row to
# generate an alert.
# 
# The keep-alive daemon respawns itself after every iteration. This way no bad
# state or resource leaks can accumulate and bring it down. The keep-alive
# daemon will start the CM server if it is not running, so your server startup
# script should run the keepalive daemon and let the daemon start the CM
# server at boot.
# 
# This program is used on my servers and works fine so far. It is not
# particularly neat or well-tested at the moment. Use at your own risk.
# You will need to configure the parameters below for your servers.
#
# v0.01 original
# v0.02 fix a file descriptor leak
# v0.03 fix a bug in remote failures

import logging
import string
import re
import sys
import os
import fcntl
import subprocess
import traceback
import stat
import time
import smtplib
import atexit
import signal
import twisted.protocols.basic
import twisted.internet.protocol
import twisted.internet.reactor
import twisted.internet.endpoints
from email.mime.text import MIMEText
import daemon
import client

# Change UID at start, if run as root (Use same UID as CM server)
run_as_uid = 1000
#run_as_gid = 1000
run_as_gid = None

# Local and remote hosts and ports for CM servers.
# Remote server can be null for single server configuration
local_server_host = "localhost"
local_server_port = 8082
remote_server_host = "s1.confidantmail.org"
remote_server_port = 8082

# Path to input queue and server start directory
server_input_queue = "/home/mikei/confidantmail/server2/inputqueue"
start_dir = "/home/mikei/confidantmail"

# Command to start CM server, run from start_dir
start_command = "python server.py -homedir /home/mikei/confidantmail/server2 -daemon -logfile /home/mikei/confidantmail/server2.log -pidfile /home/mikei/confidantmail/server2.pid -logtraffic"

# Seconds' delay after cms_kad initial start, for server to stabilize
kad_start_delay_sec = 120

# Frequency of polling CM servers (seconds)
poll_interval_sec = 300

# Max age in seconds for input queue files, older causes restart
inputqueue_old_sec = 600

# Waiting time for CM server poll
poll_timeout_sec = 10

# Not used
pause_after_restart_sec = 60

# Delay after alert and restart, to avoid excessive emailing
pause_after_email_sec = 3600

# Alert on this number of remote server failures in a row
alert_remote_failures = 3

# Command to check filesystems, you can check all or specify
#filesystem_check_command = [ '/bin/df','/dev/xvda1' ]
filesystem_check_command = [ '/bin/df' ]

# Max acceptable space used (percent full), more causes prune
filesystem_prune_pct = 85

# Prune command to run when disk full
filesystem_prune_command = "python storutil.py -homedir /home/ubuntu/confidantmail/server2 -prune-entangled -prune-localstore 2>&1"

# Limit on how often filesystem is pruned (seconds)
filesystem_prune_maxfreq = 28800

# Not used
respawn_kad_count = 1

# Command to respawn keepalive daemon. Parameters are passed back in.
respawn_kad_command = [ "/usr/bin/python","python","cms_kad.py" ]

# CM server PID file, for killing server
pid_file = "/home/mikei/confidantmail/server2.pid"

# Regular expression to detect running server
re_detect_running = re.compile('.*python.*server\.py.*confidantmail.*')

# Logfile for keepalive daemon
kad_logfile = "/home/mikei/confidantmail/keepalive.log"

# Pidfile for keepalive daemon
kad_pidfile = "/home/mikei/confidantmail/keepalive.pid"

# Parameters for your SMTP email server, for alerting
smtp_server = '127.0.0.1'
smtp_port = 25
smtp_port = 587
smtp_user = None
smtp_pass = None
smtp_fromaddr = 'xxxxxx@confidantmail.org'
smtp_toaddr = 'xxxxxx@pobox.com'

# Name for alerting, local and remote
smtp_notify_name_local = 's2.confidantmail.org'
smtp_notify_name_remote = 's1.confidantmail.org'

# Touching this file causes a test email to be sent
smtp_test_flag_file = '/home/mikei/confidantmail/test.smtp.warning'

# Set your logging level, move desired level to the end
log_level = logging.INFO
log_level = logging.WARN
log_level = logging.DEBUG


class cms_kad:

	def __init__(self, local_server_host, local_server_port, remote_server_host,
remote_server_port, server_input_queue, start_dir, start_command,
poll_interval_sec, inputqueue_old_sec, poll_timeout_sec, pause_after_restart_sec,
pause_after_email_sec, filesystem_check_command, filesystem_prune_pct,
filesystem_prune_command, filesystem_prune_maxfreq, respawn_kad_count,
respawn_kad_command, pid_file, smtp_server, smtp_port, smtp_user,
smtp_pass, smtp_notify_name_local, smtp_notify_name_remote, smtp_fromaddr,
smtp_toaddr, smtp_test_flag_file, re_detect_running, iter_count,
last_filesystem_prune, alert_remote_failures, current_remote_failures):
		self.logger = logging.getLogger("daemon")
		self.local_server_host = local_server_host
		self.local_server_port = local_server_port
		self.remote_server_host = remote_server_host
		self.remote_server_port = remote_server_port
		self.server_input_queue = server_input_queue
		self.start_dir = start_dir
		self.start_command = start_command
		self.poll_interval_sec = poll_interval_sec
		self.inputqueue_old_sec = inputqueue_old_sec
		self.poll_timeout_sec = poll_timeout_sec
		self.pause_after_restart_sec = pause_after_restart_sec
		self.pause_after_email_sec = pause_after_email_sec
		self.filesystem_check_command = filesystem_check_command
		self.filesystem_prune_pct = filesystem_prune_pct
		self.filesystem_prune_command = filesystem_prune_command
		self.filesystem_prune_maxfreq = filesystem_prune_maxfreq
		self.respawn_kad_count = respawn_kad_count
		self.respawn_kad_command = respawn_kad_command
		self.pid_file = pid_file
		self.smtp_server = smtp_server
		self.smtp_port = smtp_port
		self.smtp_user = smtp_user
		self.smtp_pass = smtp_pass
		self.smtp_notify_name_local = smtp_notify_name_local
		self.smtp_notify_name_remote = smtp_notify_name_remote
		self.smtp_fromaddr = smtp_fromaddr
		self.smtp_toaddr = smtp_toaddr
		self.smtp_test_flag_file = smtp_test_flag_file
		self.re_detect_running = re_detect_running
		self.iter_count = iter_count
		self.last_filesystem_prune = last_filesystem_prune
		self.alert_remote_failures = alert_remote_failures
		self.current_remote_failures = current_remote_failures

	def traffic_log_writer(self,typ,data):
		if self.logger != None:
			self.logger.info('C%s %s',typ,data)

	def connect_check_local_server(self):
		clientProt = client.clientProtocol(self.client_completion_callback,None,self.poll_timeout_sec,logCallback = self.traffic_log_writer)
		endpoint = client.getEndpoint(twisted.internet.reactor,self.local_server_host,self.local_server_port,self.poll_timeout_sec,bindAddress=None,socksHost = None,socksPort = None)
		clientProt.openConnection(endpoint)

	def connect_check_remote_server(self):
		clientProt = client.clientProtocol(self.client_completion_callback,None,self.poll_timeout_sec,logCallback = self.traffic_log_writer)
		endpoint = client.getEndpoint(twisted.internet.reactor,self.remote_server_host,self.remote_server_port,self.poll_timeout_sec,bindAddress=None,socksHost = None,socksPort = None)
		clientProt.openConnection(endpoint)

	def client_completion_callback(self,client,context,command,resultmsg,textdata,bindata):
		if self.local_connect_test_done == True:
			self.logger.debug("Remote client result: %s %s",resultmsg,textdata)
		else:
			self.logger.debug("Local client result: %s %s",resultmsg,textdata)
		resultL = resultmsg.lower()
		if resultL == "connected":
			client.sendCommand("SELFTEST",None)
		elif resultL == "found":
			if ((type(textdata) == list) and (len(textdata) == 1) and (textdata[0] == 'PASS')):
				if self.local_connect_test_done == True:
					self.remote_connect_test_good = True
				else:
					self.local_connect_test_good = True
			client.sendCommand("QUIT",None)
		elif resultL == "disconnect" or resultL == "receive timeout" or resultL == "connect failed":
			if self.local_connect_test_done == True:
				twisted.internet.reactor.callLater(1,twisted.internet.reactor.stop)
			elif self.remote_server_host == None:
				self.local_connect_test_done = True
				self.remote_connect_test_good = True
				twisted.internet.reactor.callLater(1,twisted.internet.reactor.stop)
			else:
				self.local_connect_test_done = True
				self.connect_check_remote_server()

	def run_connect_test(self):
		self.local_connect_test_good = False
		self.remote_connect_test_good = False
		self.local_connect_test_done = False
		twisted.internet.reactor.callLater(2,self.connect_check_local_server)
		twisted.internet.reactor.run()
		self.logger.debug("Done with connect test")

	def detect_old_files(self,checkdir,max_age_s):
		nowtime = time.time()
		for fn in os.listdir(checkdir):
			fp = checkdir + os.sep + fn
			try:
				fst = os.stat(fp)
			except OSError: # file disappeared
				continue	
			age_s = nowtime - fst.st_mtime
			if age_s >= max_age_s:
				return True
		return False

	def look_for_running_process(self,pid_file):
		if os.path.isfile(pid_file) == False:
			return None
		try:
			fh = open(pid_file,'r')
			pidno = fh.read().strip(" \r\n")
			fh.close()
		except IOError:
			return None
		procpath = "/proc/" + pidno + "/cmdline"
		try:
			fh = open(procpath,'r')
			cmdline = fh.read().replace("\000"," ")
			fh.close()
		except IOError:
			return None
		if self.re_detect_running.match(cmdline):
			return pidno
		else:
			return None

	def kill_start_process(self):
		pidno = self.look_for_running_process(self.pid_file)
		if pidno != None:
			self.logger.warn('Sending SIGHUP to ' + pidno)
			os.kill(int(pidno),signal.SIGHUP)
			time.sleep(3)
			pidno = self.look_for_running_process(self.pid_file)
			if pidno != None:
				self.logger.error('Sending SIGKILL to ' + pidno)
				os.kill(int(pidno),signal.SIGKILL)
				time.sleep(3)
		self.logger.warn("Starting Confidant Mail server")
		os.system(self.start_command)
		time.sleep(5)
		pidno = self.look_for_running_process(self.pid_file)
		if pidno == None:
			self.logger.error("Process failed to start")
		else:
			self.logger.warn("New Confidant Mail server pid=" + pidno)		

	def send_email_alert(self,msg_txt,msg_subj = None):
		if msg_subj == None:
			msg_subj = "CM server problem on " + self.smtp_notify_name_local
		try:
			msg = MIMEText(msg_txt)
			msg['Subject'] = msg_subj
			msg['From'] = self.smtp_fromaddr
			msg['To'] = self.smtp_toaddr
			smtp = smtplib.SMTP()
			smtp.set_debuglevel(0)
			smtp.connect(self.smtp_server,self.smtp_port)
			if self.smtp_user != None:
				smtp.login(self.smtp_user,self.smtp_pass)
			smtp.sendmail(self.smtp_fromaddr,self.smtp_toaddr,msg.as_string())
			smtp.quit()
		except Exception as exc:
			self.logger.error('Failed to send SMTP: ' + traceback.format_exc())

	def alert_and_restart(self,old_files_detected):
		alertmsg = ""
		if self.local_connect_test_good == False:
			alertmsg += "Connect test failed\n"
		if old_files_detected == True:
			alertmsg += "Old files detected in input queue\n"
		if alertmsg != "":
			alertmsg += "Restarting CM server\n"
			self.send_email_alert(alertmsg)
			self.kill_start_process()
			time.sleep(self.pause_after_email_sec)

	def check_free_space(self):
		re_find_pct = re.compile(".* ([0-9]+)% .*")
		pct_full = None
		free_space_str = ''
		try:
			free_space_str = subprocess.check_output(self.filesystem_check_command).decode('utf-8')
			for line in free_space_str.split('\n'):
				match = re_find_pct.match(line)
				if match:
					this_pct_full = int(match.group(1))
					if (pct_full == None) or (pct_full < this_pct_full):
						pct_full = this_pct_full
		except Exception as exc:
			free_space_str = 'Failed to call df: ' + traceback.format_exc()
		return pct_full,free_space_str

	def check_fix_free_space(self):
		prune_ran = False
		pct_full,free_space_str = self.check_free_space()
		if pct_full >= self.filesystem_prune_pct:
			prune_ran = True
			prune_output = ""
			try:
				prune_obj = subprocess.Popen(self.filesystem_prune_command,stdout = subprocess.PIPE,shell = True)
				prune_output = prune_obj.communicate()[0]
			except Exception as exc:
				prune_output = 'Prune command failed to run: ' + traceback.format_exc()
			pct_full_after,free_space_str_after = self.check_free_space()	
			msg_txt = "Disk usage before pruning:\n" + free_space_str + "\nDisk usage after pruning:\n" + free_space_str_after + "\nPrune output:\n" + prune_output
			if pct_full >= self.filesystem_prune_pct:
				self.send_email_alert("Warning: disk full even after pruning!\n\n" + msg_txt)
			else:
				self.send_email_alert(msg_txt,"CM auto-prune run on " + self.smtp_notify_name_local)
		return prune_ran

	def run_keepalive(self):
		while True:
			self.logger.info("Begin test # " + str(self.iter_count))
			self.run_connect_test()
			if self.local_connect_test_good == False:
				self.logger.warn("Connect test failed")
			old_files_detected = self.detect_old_files(self.server_input_queue,self.inputqueue_old_sec)
			if old_files_detected == True:
				self.logger.warn("Old files detected in input queue")
			if (self.local_connect_test_good == False) or (old_files_detected == True):
				self.alert_and_restart(old_files_detected)

			if self.remote_connect_test_good == False:
				self.current_remote_failures += 1
				if self.current_remote_failures == self.alert_remote_failures:
					msg_subj = "CM remote server problem on " + self.smtp_notify_name_remote
					msg_body = "Server " + self.smtp_notify_name_local + " unable to successfully test " + self.smtp_notify_name_remote,msg_subj
					self.send_email_alert(msg_body,msg_subj)
			else:
				self.current_remote_failures = 0
			nowtime = time.time()
			if (nowtime - self.last_filesystem_prune) > self.filesystem_prune_maxfreq:
				if self.check_fix_free_space() == True:
					self.logger.warn("Filesystem prune ran")
					self.last_filesystem_prune = nowtime

			if os.path.isfile(self.smtp_test_flag_file):
				try:
					os.unlink(self.smtp_test_flag_file)
					self.send_email_alert("Testing cms_kad.py alerts")
				except Exception as exc:
					self.logger.error("Unable to test SMTP: " + traceback.format_exc())

			time.sleep(self.poll_interval_sec)
			self.iter_count += 1
			self.logger.debug("About to respawn at test count " +  str(self.iter_count))	
			rkc = self.respawn_kad_command[0:]
			rkc.append('respawn')
			rkc.append(str(self.iter_count))
			rkc.append(str(int(self.last_filesystem_prune)))
			rkc.append(str(self.current_remote_failures))
			for fd in range(3,10):
				try: # system call below prevents a file descriptor leak
					fcntl.fcntl(fd,fcntl.F_SETFD,fcntl.FD_CLOEXEC)
				except IOError:
					pass
			while True:
				os.execv(rkc[0],rkc[1:])
				self.logger.error("Respawn failed, will keep trying, but this is not good")
				time.sleep(120)


######################################## main ########################################
os.chdir(start_dir)
#logging.basicConfig(level=log_level,format="%(asctime)s %(levelname)-5s %(name)-10s %(threadName)-10s %(message)s")
logging.basicConfig(level=log_level,format="%(asctime)s %(levelname)-5s %(message)s")
logger = logging.getLogger("startup")
if (len(sys.argv) >= 3) and (sys.argv[1] == 'respawn'):
	iter_count = int(sys.argv[2])
	last_filesystem_prune = int(sys.argv[3])
	current_remote_failures = int(sys.argv[4])
	logger.info("Respawning at test count " + str(iter_count))
else:
	if os.getuid() == 0:
		if (run_as_uid != None):
			os.setuid(run_as_uid)
			os.seteuid(run_as_uid)
		if (run_as_gid != None):
			os.setgid(run_as_gid)
			os.setegid(run_as_gid)
	iter_count = 0
	last_filesystem_prune = 0
	current_remote_failures = 0
	daemon = daemon.Daemon(kad_pidfile,stdout = kad_logfile,stderr = kad_logfile)
	daemon.daemonize()
	os.chdir(start_dir)
	time.sleep(kad_start_delay_sec)
	logger.info("Confidant Mail Server Keep Alive Daemon startup")

instance = cms_kad(local_server_host, local_server_port, remote_server_host,
remote_server_port, server_input_queue, start_dir, start_command, poll_interval_sec,
inputqueue_old_sec, poll_timeout_sec, pause_after_restart_sec, pause_after_email_sec,
filesystem_check_command, filesystem_prune_pct, filesystem_prune_command,
filesystem_prune_maxfreq, respawn_kad_count, respawn_kad_command,
pid_file, smtp_server, smtp_port, smtp_user, smtp_pass, smtp_notify_name_local,
smtp_notify_name_remote, smtp_fromaddr, smtp_toaddr, smtp_test_flag_file,
re_detect_running, iter_count, last_filesystem_prune, alert_remote_failures,
current_remote_failures)

instance.run_keepalive()

# EOF
