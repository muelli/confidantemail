# Macos cx_freeze builder

# To make this work:
# in src/cryptography/hazmat/bindings/utils.py
# in def Verifier(
# change:
# tmpdir=os.path.dirname(os.path.realpath(sys.argv[0])),
#
# without these changes you are basically doomed.

# cp /usr/local/lib/python2.7/site-packages/cryptography/_Cryptography_cffi_2a871178xb3816a41.so build/exe.macosx-10.9-x86_64-2.7/_Cryptography_cffi_2a871178xb3816a41.so
# cp /usr/local/lib/python2.7/site-packages/cryptography/_Cryptography_cffi_4ee21876x41fb9936.so build/exe.macosx-10.9-x86_64-2.7/_Cryptography_cffi_4ee21876x41fb9936.so
# cp /usr/local/lib/python2.7/site-packages/cryptography/_Cryptography_cffi_590da19fxffc7b1ce.so build/exe.macosx-10.9-x86_64-2.7/_Cryptography_cffi_590da19fxffc7b1ce.so
# cp /usr/local/lib/python2.7/site-packages/cryptography/_Cryptography_cffi_8f86901cxc1767c5a.so build/exe.macosx-10.9-x86_64-2.7/_Cryptography_cffi_8f86901cxc1767c5a.so
# cp \
# /usr/local/lib/python2.7/site-packages/enchant/lib/enchant/libenchant_ispell.so \
# /usr/local/lib/python2.7/site-packages/enchant/lib/enchant/libenchant_myspell.so \
# /usr/local/lib/python2.7/site-packages/enchant/lib/libenchant.1.dylib \
# build/exe.macosx-10.9-x86_64-2.7/

# ln -s . lib
# cp /usr/local/lib/python2.7/site-packages/enchant/lib/*dylib .

# -*- coding: utf-8 -*-
from cx_Freeze import setup, Executable
 
buildOptions = dict(
packages = [ "os", "twisted.internet.ssl", 
         "twisted.internet", "cryptography", "OpenSSL", "dbhash",
	 "pycparser","enchant","gdbm" ],
include_files = [ ],
excludes = ['pdb', 'doctest', 'unittest',
'audio', 'pydoc', 'difflib', 'PIL',
'tcl', 'ttk', 'xmllib',
'xml', 'xmlrpc',
'Tkinter', 'encoding'],
includes = ["OpenSSL.crypto"],
namespace_packages =  ['zope'],
)
 
gui = Executable('config_chooser.py', targetName = "confidantmail",
icon = 'keyicon.icns' )
#)
#icon = 'static\logo.ico', base = 'Win32GUI')
 
setup(
name = "Confidant Mail",
version = "0.45",
description = "Confidant Mail",
author = 'Mike Ingle',
executables = [gui],
options = dict(build_exe = buildOptions)) 


# pyd files under C:\Python27\lib\site-packages\cryptography-0.7.dev1-py2.7-win32.egg\cryptography\hazmat\bindings\__pycache__

