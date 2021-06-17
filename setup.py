# Windows cx_freeze builder

# To make this work:
# in src\cryptography\hazmat\bindings\utils.py
# add: import os
# in: ffi.verifier = Verifier(
# change:
# tmpdir='',
# to:
# tmpdir=os.path.dirname(os.path.realpath(sys.argv[0])),
#
# copy in these files and rename them:
#
# move "build\exe.win32-2.7\cryptography._Cryptography_cffi_3a414503xe735153f.pyd" "build\exe.win32-2.7\_Cryptography_cffi_3a414503xe735153f.pyd"
# move "build\exe.win32-2.7\cryptography._Cryptography_cffi_590da19fxffc7b1ce.pyd" "build\exe.win32-2.7\_Cryptography_cffi_590da19fxffc7b1ce.pyd"
# move "build\exe.win32-2.7\cryptography._Cryptography_cffi_8f86901cxc1767c5a.pyd" "build\exe.win32-2.7\_Cryptography_cffi_8f86901cxc1767c5a.pyd"
# without these changes you are basically doomed.

# -*- coding: utf-8 -*-
from cx_Freeze import setup, Executable
 
buildOptions = dict(
packages = [ "os", "twisted.internet.ssl", 
         "twisted.internet", "cryptography", "OpenSSL", "dbhash", "pycparser" ],
include_files = [ ],
excludes = ['pdb', 'doctest', 'unittest',
'audio', 'pydoc', 'difflib', 'PIL',
'tcl', 'ttk', 'xmllib',
'xml', 'xmlrpc',
'Tkinter', 'encoding'],
includes = ["OpenSSL.crypto"])
 
gui = Executable('config_chooser.py', targetName = "confidantmail.exe",
icon = 'keyicon.ico', base = 'Win32GUI')
#)
#icon = 'static\logo.ico', base = 'Win32GUI')
 
setup(
name = "Confidant Mail",
version = "0.2",
description = "Confidant Mail",
author = 'Mike Ingle',
executables = [gui],
options = dict(build_exe = buildOptions)) 


# pyd files under C:\Python27\lib\site-packages\cryptography-0.7.dev1-py2.7-win32.egg\cryptography\hazmat\bindings\__pycache__

