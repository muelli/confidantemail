import sys
import datetime
import os
import find_gpg_homedir

pow_nbits_key = 24
pow_nmatches_key = 2
max_age_key = 2678400 # 31 days
renew_age_key = 604800 # 7 days

pow_nbits_data_server = 8
pow_nmatches_data_server = 2
pow_nbits_data_entangled = 20
pow_nmatches_data_entangled = 2
max_blocksize_server = 8388608
max_blocksize_entangled = 65536
max_msgsize_entangled = 8388608 # warn user if over

pow_nbits_message_server = 8
pow_nmatches_message_server = 2
pow_nbits_message_entangled = 20
pow_nmatches_message_entangled = 2

max_age_data = 864000 # ten days

# message requirement determined by user

max_age_message = 864000 # ten days

pow_nbits_ack_server = 16
pow_nmatches_ack_server = 2
pow_nbits_ack_entangled = 20
pow_nmatches_ack_entangled = 2
max_age_ack = 864000 # ten days
send_expire_ack = 259200 # three days

max_age_claim = 864000 # ten days

check_since_overlap = 86400 # one day
max_incremental_checks = 8
process_new_message_interval = 1000 # ms
check_send_ack_interval = 1000 # ms
check_for_acks_interval = 60.0 # sec
upgrade_check_server = 'latestversion.confidantmail.org'
upgrade_check_expected_version = 27
upgrade_check_duration = 60000
status_display_time = 10000 # ten seconds
software_version = '0.41' # D
max_insert_image_size = 1048576
help_file = os.path.dirname(os.path.realpath(sys.argv[0])) + os.sep + "help.zip"

if sys.platform == 'win32':
	gnupg_exename = 'gpg.exe'
	default_homedir = os.path.expandvars("$APPDATA") + os.sep + "confidantmail"
else:
	gnupg_exename = 'gpg'

gnupg_in_path,gnupg_path,gpgconf_path = find_gpg_homedir.find_gpg()
gnupg_is_v2,gnupg_version,libgcrypt_version = find_gpg_homedir.find_gpg_version(gnupg_path)
gpg_opts = [ "--personal-digest-preferences","SHA512,SHA384,SHA256","--cert-digest-algo","SHA512","--display-charset","utf-8" ]
if (sys.platform == 'darwin') and (gnupg_is_v2 == True):
	gpg_opts.append('--agent-program')
	gpg_opts.append(gnupg_path + '-agent')

def syspath_additions():
	runpath = sys.path[0]
	entangledpath = runpath + os.sep + 'entangled-0.1'
	pathlist = [ ]
	pathlist.append(entangledpath)
	return pathlist

sys.path.extend(syspath_additions())

class date_format:

	def localize_datetime(self,datetime_in):
		parsed_datetime = datetime.datetime.strptime(datetime_in,"%Y-%m-%dT%H:%M:%SZ")
		timestamp_out = (parsed_datetime - datetime.datetime(1970,1,1)).total_seconds()
		changed_datetime = datetime.datetime.fromtimestamp(timestamp_out)
		formatted_datetime = changed_datetime.strftime("%a %Y-%m-%d %I:%M:%S %p")
		return formatted_datetime

# EOF
