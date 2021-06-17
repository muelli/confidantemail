# Linux cx_freeze builder

# To make this work:
# in src\cryptography\hazmat\bindings\utils.py
# add: import os
# in: ffi.verifier = Verifier(
# change:
# tmpdir='',
# to:
# tmpdir=os.path.dirname(os.path.realpath(sys.argv[0])),
#
# Then copy in:
# _Cryptography_cffi_4ee21876x41fb9936.so
# _Cryptography_cffi_590da19fxffc7b1ce.so
# _Cryptography_cffi_8f86901cxc1767c5a.so
#
# from /usr/local/lib/python2.7/dist-packages/cryptography/
# If they have anything before the _ remove it.
# then rename like: (64 bit)
# mv 'cryptography._Cryptography_cffi_4ee21876x41fb9936.so' '_Cryptography_cffi_4ee21876x41fb9936.x86_64-linux-gnu.so'
# mv 'cryptography._Cryptography_cffi_590da19fxffc7b1ce.so' '_Cryptography_cffi_590da19fxffc7b1ce.x86_64-linux-gnu.so'
# mv 'cryptography._Cryptography_cffi_8f86901cxc1767c5a.so' '_Cryptography_cffi_8f86901cxc1767c5a.x86_64-linux-gnu.so'
#
# (32 bit)
# mv 'cryptography._Cryptography_cffi_4ee21876x41fb9936.so' '_Cryptography_cffi_4ee21876x41fb9936.so'
# mv 'cryptography._Cryptography_cffi_590da19fxffc7b1ce.so' '_Cryptography_cffi_590da19fxffc7b1ce.so'
# mv 'cryptography._Cryptography_cffi_8f86901cxc1767c5a.so' '_Cryptography_cffi_8f86901cxc1767c5a.so'
#
# without these changes you are basically doomed.
#
# If file names change, use the strace command to figure out what the program is trying
# to load, and rename accordingly.

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
includes = ["OpenSSL.crypto"],
)
# may need:
# namespace_packages =  ['zope'],
 
gui = Executable('config_chooser.py', targetName = "confidantmail",
icon = 'keyicon.ico' )
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

