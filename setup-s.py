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
 
gui = Executable('server.py', targetName = "confserv.exe",
)
#base = 'Win32GUI')
#icon = 'static\logo.ico', base = 'Win32GUI')
 
setup(
name = "Confidant Mail Server",
version = "0.2",
description = "Confidant Mail Server",
author = 'Mike Ingle',
executables = [gui],
options = dict(build_exe = buildOptions)) 


# pyd files under C:\Python27\lib\site-packages\cryptography-0.7.dev1-py2.7-win32.egg\cryptography\hazmat\bindings\__pycache__

