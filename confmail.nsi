; confmail.nsi
;
; This script is based on example1.nsi, but it remember the directory, 
; has uninstall support and (optionally) installs start menu shortcuts.
;
; It will install confmail.nsi into a directory that the user selects,

;--------------------------------

; The name of the installer
Name "Confidant Mail"

; The file to write
OutFile "confmailinst.exe"

; The default installation directory
InstallDir $PROGRAMFILES\Confmail

; Registry key to check for directory (so if you install again, it will 
; overwrite the old one automatically)
InstallDirRegKey HKLM "Software\ConfidantMail" "Install_Dir"

; Request application privileges for Windows Vista
RequestExecutionLevel admin

;--------------------------------

; Pages

Page components
Page directory
Page instfiles

UninstPage uninstConfirm
UninstPage instfiles

;--------------------------------
; Check for running process
Function .onInit
  FindProcDLL::FindProc "confidantmail.exe"
  IntCmp $R0 1 0 notRunning
    MessageBox MB_OK|MB_ICONEXCLAMATION "Confidant Mail is running. Please close it before upgrading." /SD IDOK
    Abort
  notRunning:
FunctionEnd

;--------------------------------

; The stuff to install
Section "Confidant Mail (required)"

  SectionIn RO
  
  ; Set output path to the installation directory.
  SetOutPath $INSTDIR
  
  ; Put files there
  File "_bsddb.pyd"
  File "_cffi_backend.pyd"
  File "cryptography.hazmat.bindings._constant_time.pyd"
  File "cryptography.hazmat.bindings._openssl.pyd"
  File "cryptography.hazmat.bindings._padding.pyd"
  File "zope.interface._zope_interface_coptimizations.pyd"
  Delete "$INSTDIR\_Cryptography_cffi_3a414503xe735153f.pyd"
  Delete "$INSTDIR\_Cryptography_cffi_4ee21876x41fb9936.pyd"
  Delete "$INSTDIR\_Cryptography_cffi_590da19fxffc7b1ce.pyd"
  Delete "$INSTDIR\_Cryptography_cffi_8f86901cxc1767c5a.pyd"
  File "_ctypes.pyd"
  File "_hashlib.pyd"
  File "_multiprocessing.pyd"
  File "_socket.pyd"
  File "_sqlite3.pyd"
  File "_ssl.pyd"
  File "bz2.pyd"
  File "confidantmail.exe"
  File "gpg.exe"
  File "gpgkeys_curl.exe"
  File "gpgkeys_finger.exe"
  File "gpgkeys_hkp.exe"
  File "gpgkeys_ldap.exe"
  File "gpgsplit.exe"
  File "gpgv.exe"
  File "help.zip"
  File "iconv.dll"
  File "library.zip"
  File "python27.dll"
  File "pywintypes27.dll"
  File "select.pyd"
  File "sqlite3.dll"
  File "twisted.internet.iocpreactor.iocpsupport.pyd"
  File "unicodedata.pyd"
  File "uninst-gnupg.exe"
  File "win32api.pyd"
  File "win32console.pyd"
  File "win32event.pyd"
  File "win32file.pyd"
  File "win32gui.pyd"
  File "win32pipe.pyd"
  File "win32process.pyd"
  File "win32security.pyd"
  File "wx._controls_.pyd"
  File "wx._core_.pyd"
  File "wx._gdi_.pyd"
  File "wx._grid.pyd"
  File "wx._html.pyd"
  File "wx._misc_.pyd"
  File "wx._richtext.pyd"
  File "wx._windows_.pyd"
  File "wxbase30u_net_vc90.dll"
  File "wxbase30u_vc90.dll"
  File "wxbase30u_xml_vc90.dll"
  File "wxmsw30u_adv_vc90.dll"
  File "wxmsw30u_core_vc90.dll"
  File "wxmsw30u_html_vc90.dll"
  File "wxmsw30u_richtext_vc90.dll"
  SetOutPath $INSTDIR\Doc
  File "Doc\COPYING.LIB.txt"
  File "Doc\COPYING.txt"
  File "Doc\gnupg.man"
  File "Doc\gpg.man"
  File "Doc\gpgv.man"
  File "Doc\NEWS.txt"
  File "Doc\README-W32.txt"
  File "Doc\README.iconv.txt"
  File "Doc\README.txt"
  SetOutPath $INSTDIR\gnupg.nls
  File "gnupg.nls\be.mo"
  File "gnupg.nls\ca.mo"
  File "gnupg.nls\cs.mo"
  File "gnupg.nls\da.mo"
  File "gnupg.nls\de.mo"
  File "gnupg.nls\el.mo"
  File "gnupg.nls\en@boldquot.mo"
  File "gnupg.nls\en@quot.mo"
  File "gnupg.nls\eo.mo"
  File "gnupg.nls\es.mo"
  File "gnupg.nls\et.mo"
  File "gnupg.nls\fi.mo"
  File "gnupg.nls\fr.mo"
  File "gnupg.nls\gl.mo"
  File "gnupg.nls\hu.mo"
  File "gnupg.nls\id.mo"
  File "gnupg.nls\it.mo"
  File "gnupg.nls\ja.mo"
  File "gnupg.nls\nb.mo"
  File "gnupg.nls\nl.mo"
  File "gnupg.nls\pl.mo"
  File "gnupg.nls\pt.mo"
  File "gnupg.nls\pt_BR.mo"
  File "gnupg.nls\ro.mo"
  File "gnupg.nls\ru.mo"
  File "gnupg.nls\sk.mo"
  File "gnupg.nls\sv.mo"
  File "gnupg.nls\tr.mo"
  File "gnupg.nls\uk.mo"
  File "gnupg.nls\zh_CN.mo"
  File "gnupg.nls\zh_TW.mo"

  SetOutPath $INSTDIR\enchant
  File "enchant\__init__.pyc"
  File "enchant\_enchant.pyc"
  File "enchant\errors.pyc"
  File "enchant\iconv.dll"
  File "enchant\intl.dll"
  File "enchant\libenchant-1.dll"
  File "enchant\libglib-2.0-0.dll"
  File "enchant\libgmodule-2.0-0.dll"
  File "enchant\pypwl.pyc"
  File "enchant\tests.pyc"
  File "enchant\utils.pyc"
  SetOutPath $INSTDIR\enchant\checker
  File "enchant\checker\__init__.pyc"
  File "enchant\checker\CmdLineChecker.pyc"
  File "enchant\checker\GtkSpellCheckerDialog.pyc"
  File "enchant\checker\tests.pyc"
  File "enchant\checker\wxSpellCheckerDialog.pyc"
  SetOutPath $INSTDIR\enchant\lib
  SetOutPath $INSTDIR\enchant\lib\enchant
  File "enchant\lib\enchant\libenchant_ispell.dll"
  File "enchant\lib\enchant\libenchant_myspell.dll"
  File "enchant\lib\enchant\README.txt"
  SetOutPath $INSTDIR\enchant\share
  SetOutPath $INSTDIR\enchant\share\enchant
  SetOutPath $INSTDIR\enchant\share\enchant\myspell
  File "enchant\share\enchant\myspell\de_DE.aff"
  File "enchant\share\enchant\myspell\de_DE.dic"
  File "enchant\share\enchant\myspell\en_AU.aff"
  File "enchant\share\enchant\myspell\en_AU.dic"
  File "enchant\share\enchant\myspell\en_GB.aff"
  File "enchant\share\enchant\myspell\en_GB.dic"
  File "enchant\share\enchant\myspell\en_US.aff"
  File "enchant\share\enchant\myspell\en_US.dic"
  File "enchant\share\enchant\myspell\fr_FR.aff"
  File "enchant\share\enchant\myspell\fr_FR.dic"
  File "enchant\share\enchant\myspell\README.txt"
  SetOutPath $INSTDIR\enchant\tokenize
  File "enchant\tokenize\__init__.pyc"
  File "enchant\tokenize\en.pyc"
  File "enchant\tokenize\tests.pyc"

  SetOutPath $INSTDIR\src
  File "src\address_book.py"
  File "src\bypass_token.py"
  File "src\changepass.py"
  File "src\client.py"
  File "src\client_agent.py"
  File "src\config_chooser.py"
  File "src\config_dialog.py"
  File "src\daemon.py"
  File "src\dequeue_dialog.py"
  File "src\entangled_store.py"
  File "src\fetchmail.py"
  File "src\filelock.py"
  File "src\filestore.py"
  File "src\find_gpg_homedir.py"
;  File "src\findpaths.py"
  File "src\flatstore.py"
  File "src\folders.py"
  File "src\global_config.py"
  File "src\gnupg.py"
  File "src\gui.py"
  File "src\images.py"
  File "src\images2.py"
  File "src\key_value_file.py"
  File "src\keyannounce.py"
  File "src\message_edit_window.py"
  File "src\message_list_window.py"
  File "src\message_view_window.py"
  File "src\postmessage.py"
  File "src\proofofwork.py"
  File "src\remote_dns_lookup.py"
  File "src\repair_account.py"
  File "src\rotate_key.py"
  File "src\rotate_key_dialog.py"
  File "src\search_dialog.py"
  File "src\server.py"
  File "src\server_notify.py"
  File "src\server_send.py"
  File "src\setup-s.py"
  File "src\setup.py"
  File "src\setup-xp.py"
  File "src\showhelp.py"
  File "src\storutil.py"
  File "src\syncstore.py"
  File "src\udp_protocol.py"
  File "src\validate_merge.py"
  File "src\autoclient_echo.py"
  File "src\autoclient_fileserv.py"
  File "src\autoclient_listserv.py"
  File "src\autoclient_notify.py"
  File "src\confmail-signer-key.asc"
  
  ; Write the installation path into the registry
  WriteRegStr HKLM SOFTWARE\ConfidantMail "Install_Dir" "$INSTDIR"
  
  ; Write the uninstall keys for Windows
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Confmail" "DisplayName" "Confidant Mail"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Confmail" "Publisher" "Mike Ingle"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Confmail" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Confmail" "NoModify" 1
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Confmail" "NoRepair" 1
  WriteUninstaller "uninstall.exe"
  
SectionEnd

; Optional section (can be disabled by the user)
Section "Start Menu Shortcuts"
  CreateDirectory "$SMPROGRAMS\Confidant Mail"
  CreateShortCut "$SMPROGRAMS\Confidant Mail\Uninstall.lnk" "$INSTDIR\uninstall.exe" "" "$INSTDIR\uninstall.exe" 0
  CreateShortCut "$SMPROGRAMS\Confidant Mail\Confidant Mail.lnk" "$INSTDIR\confidantmail.exe" "" "$INSTDIR\confidantmail.exe" 0
SectionEnd

; Optional section (can be disabled by the user)
Section "Desktop Shortcut"
  CreateShortCut "$DESKTOP\Confidant Mail.lnk" "$INSTDIR\confidantmail.exe" "" "$INSTDIR\confidantmail.exe" 0
SectionEnd



;--------------------------------

; Uninstaller

Section "Uninstall"
  
  ; Remove registry keys
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Confmail"
  DeleteRegKey HKLM SOFTWARE\ConfidantMail

  ; Remove files and uninstaller
  Delete "$INSTDIR\confmail.nsi"
  Delete "$INSTDIR\uninstall.exe"
  Delete "$INSTDIR\_bsddb.pyd"
  Delete "$INSTDIR\_cffi_backend.pyd"
  Delete "$INSTDIR\_Cryptography_cffi_3a414503xe735153f.pyd"
  Delete "$INSTDIR\_Cryptography_cffi_4ee21876x41fb9936.pyd"
  Delete "$INSTDIR\_Cryptography_cffi_590da19fxffc7b1ce.pyd"
  Delete "$INSTDIR\_Cryptography_cffi_8f86901cxc1767c5a.pyd"
  Delete "$INSTDIR\cryptography.hazmat.bindings._constant_time.pyd"
  Delete "$INSTDIR\cryptography.hazmat.bindings._openssl.pyd"
  Delete "$INSTDIR\cryptography.hazmat.bindings._padding.pyd"
  Delete "$INSTDIR\zope.interface._zope_interface_coptimizations.pyd"
  Delete "$INSTDIR\_ctypes.pyd"
  Delete "$INSTDIR\_hashlib.pyd"
  Delete "$INSTDIR\_multiprocessing.pyd"
  Delete "$INSTDIR\_socket.pyd"
  Delete "$INSTDIR\_sqlite3.pyd"
  Delete "$INSTDIR\_ssl.pyd"
  Delete "$INSTDIR\bz2.pyd"
  Delete "$INSTDIR\confidantmail.exe"
  Delete "$INSTDIR\gpg.exe"
  Delete "$INSTDIR\gpgkeys_curl.exe"
  Delete "$INSTDIR\gpgkeys_finger.exe"
  Delete "$INSTDIR\gpgkeys_hkp.exe"
  Delete "$INSTDIR\gpgkeys_ldap.exe"
  Delete "$INSTDIR\gpgsplit.exe"
  Delete "$INSTDIR\gpgv.exe"
  Delete "$INSTDIR\help.zip"
  Delete "$INSTDIR\iconv.dll"
  Delete "$INSTDIR\lextab.py"
  Delete "$INSTDIR\library.zip"
  Delete "$INSTDIR\python27.dll"
  Delete "$INSTDIR\pywintypes27.dll"
  Delete "$INSTDIR\select.pyd"
  Delete "$INSTDIR\sqlite3.dll"
  Delete "$INSTDIR\twisted.internet.iocpreactor.iocpsupport.pyd"
  Delete "$INSTDIR\unicodedata.pyd"
  Delete "$INSTDIR\uninst-gnupg.exe"
  Delete "$INSTDIR\win32api.pyd"
  Delete "$INSTDIR\win32console.pyd"
  Delete "$INSTDIR\win32event.pyd"
  Delete "$INSTDIR\win32file.pyd"
  Delete "$INSTDIR\win32gui.pyd"
  Delete "$INSTDIR\win32pipe.pyd"
  Delete "$INSTDIR\win32process.pyd"
  Delete "$INSTDIR\win32security.pyd"
  Delete "$INSTDIR\wx._controls_.pyd"
  Delete "$INSTDIR\wx._core_.pyd"
  Delete "$INSTDIR\wx._gdi_.pyd"
  Delete "$INSTDIR\wx._grid.pyd"
  Delete "$INSTDIR\wx._html.pyd"
  Delete "$INSTDIR\wx._misc_.pyd"
  Delete "$INSTDIR\wx._richtext.pyd"
  Delete "$INSTDIR\wx._windows_.pyd"
  Delete "$INSTDIR\wxbase30u_net_vc90.dll"
  Delete "$INSTDIR\wxbase30u_vc90.dll"
  Delete "$INSTDIR\wxbase30u_xml_vc90.dll"
  Delete "$INSTDIR\wxmsw30u_adv_vc90.dll"
  Delete "$INSTDIR\wxmsw30u_core_vc90.dll"
  Delete "$INSTDIR\wxmsw30u_html_vc90.dll"
  Delete "$INSTDIR\wxmsw30u_richtext_vc90.dll"
  Delete "$INSTDIR\yacctab.py"
  Delete "$INSTDIR\Doc\COPYING.LIB.txt"
  Delete "$INSTDIR\Doc\COPYING.txt"
  Delete "$INSTDIR\Doc\gnupg.man"
  Delete "$INSTDIR\Doc\gpg.man"
  Delete "$INSTDIR\Doc\gpgv.man"
  Delete "$INSTDIR\Doc\NEWS.txt"
  Delete "$INSTDIR\Doc\README-W32.txt"
  Delete "$INSTDIR\Doc\README.iconv.txt"
  Delete "$INSTDIR\Doc\README.txt"
  Delete "$INSTDIR\gnupg.nls\be.mo"
  Delete "$INSTDIR\gnupg.nls\ca.mo"
  Delete "$INSTDIR\gnupg.nls\cs.mo"
  Delete "$INSTDIR\gnupg.nls\da.mo"
  Delete "$INSTDIR\gnupg.nls\de.mo"
  Delete "$INSTDIR\gnupg.nls\el.mo"
  Delete "$INSTDIR\gnupg.nls\en@boldquot.mo"
  Delete "$INSTDIR\gnupg.nls\en@quot.mo"
  Delete "$INSTDIR\gnupg.nls\eo.mo"
  Delete "$INSTDIR\gnupg.nls\es.mo"
  Delete "$INSTDIR\gnupg.nls\et.mo"
  Delete "$INSTDIR\gnupg.nls\fi.mo"
  Delete "$INSTDIR\gnupg.nls\fr.mo"
  Delete "$INSTDIR\gnupg.nls\gl.mo"
  Delete "$INSTDIR\gnupg.nls\hu.mo"
  Delete "$INSTDIR\gnupg.nls\id.mo"
  Delete "$INSTDIR\gnupg.nls\it.mo"
  Delete "$INSTDIR\gnupg.nls\ja.mo"
  Delete "$INSTDIR\gnupg.nls\nb.mo"
  Delete "$INSTDIR\gnupg.nls\nl.mo"
  Delete "$INSTDIR\gnupg.nls\pl.mo"
  Delete "$INSTDIR\gnupg.nls\pt.mo"
  Delete "$INSTDIR\gnupg.nls\pt_BR.mo"
  Delete "$INSTDIR\gnupg.nls\ro.mo"
  Delete "$INSTDIR\gnupg.nls\ru.mo"
  Delete "$INSTDIR\gnupg.nls\sk.mo"
  Delete "$INSTDIR\gnupg.nls\sv.mo"
  Delete "$INSTDIR\gnupg.nls\tr.mo"
  Delete "$INSTDIR\gnupg.nls\uk.mo"
  Delete "$INSTDIR\gnupg.nls\zh_CN.mo"
  Delete "$INSTDIR\gnupg.nls\zh_TW.mo"
  Delete "$INSTDIR\src\address_book.py"
  Delete "$INSTDIR\src\bypass_token.py"
  Delete "$INSTDIR\src\changepass.py"
  Delete "$INSTDIR\src\client.py"
  Delete "$INSTDIR\src\client_agent.py"
  Delete "$INSTDIR\src\config_chooser.py"
  Delete "$INSTDIR\src\config_dialog.py"
  Delete "$INSTDIR\src\daemon.py"
  Delete "$INSTDIR\src\dequeue_dialog.py"
  Delete "$INSTDIR\src\entangled_store.py"
  Delete "$INSTDIR\src\fetchmail.py"
  Delete "$INSTDIR\src\filelock.py"
  Delete "$INSTDIR\src\filestore.py"
  Delete "$INSTDIR\src\find_gpg_homedir.py"
  Delete "$INSTDIR\src\findpaths.py"
  Delete "$INSTDIR\src\flatstore.py"
  Delete "$INSTDIR\src\folders.py"
  Delete "$INSTDIR\src\global_config.py"
  Delete "$INSTDIR\src\gnupg.py"
  Delete "$INSTDIR\src\gui.py"
  Delete "$INSTDIR\src\images.py"
  Delete "$INSTDIR\src\images2.py"
  Delete "$INSTDIR\src\key_value_file.py"
  Delete "$INSTDIR\src\keyannounce.py"
  Delete "$INSTDIR\src\message_edit_window.py"
  Delete "$INSTDIR\src\message_list_window.py"
  Delete "$INSTDIR\src\message_view_window.py"
  Delete "$INSTDIR\src\postmessage.py"
  Delete "$INSTDIR\src\proofofwork.py"
  Delete "$INSTDIR\src\remote_dns_lookup.py"
  Delete "$INSTDIR\src\repair_account.py"
  Delete "$INSTDIR\src\rotate_key.py"
  Delete "$INSTDIR\src\rotate_key_dialog.py"
  Delete "$INSTDIR\src\search_dialog.py"
  Delete "$INSTDIR\src\server.py"
  Delete "$INSTDIR\src\server_notify.py"
  Delete "$INSTDIR\src\server_send.py"
  Delete "$INSTDIR\src\setup-s.py"
  Delete "$INSTDIR\src\setup.py"
  Delete "$INSTDIR\src\setup-xp.py"
  Delete "$INSTDIR\src\showhelp.py"
  Delete "$INSTDIR\src\storutil.py"
  Delete "$INSTDIR\src\syncstore.py"
  Delete "$INSTDIR\src\udp_protocol.py"
  Delete "$INSTDIR\src\validate_merge.py"
  Delete "$INSTDIR\src\autoclient_echo.py"
  Delete "$INSTDIR\src\autoclient_fileserv.py"
  Delete "$INSTDIR\src\autoclient_listserv.py"
  Delete "$INSTDIR\src\autoclient_notify.py"
  Delete "$INSTDIR\src\confmail-signer-key.asc"

  Delete "$INSTDIR\enchant\__init__.pyc"
  Delete "$INSTDIR\enchant\_enchant.pyc"
  Delete "$INSTDIR\enchant\checker\__init__.pyc"
  Delete "$INSTDIR\enchant\checker\CmdLineChecker.pyc"
  Delete "$INSTDIR\enchant\checker\GtkSpellCheckerDialog.pyc"
  Delete "$INSTDIR\enchant\checker\tests.pyc"
  Delete "$INSTDIR\enchant\checker\wxSpellCheckerDialog.pyc"
  Delete "$INSTDIR\enchant\errors.pyc"
  Delete "$INSTDIR\enchant\iconv.dll"
  Delete "$INSTDIR\enchant\intl.dll"
  Delete "$INSTDIR\enchant\libenchant-1.dll"
  Delete "$INSTDIR\enchant\libglib-2.0-0.dll"
  Delete "$INSTDIR\enchant\libgmodule-2.0-0.dll"
  Delete "$INSTDIR\enchant\pypwl.pyc"
  Delete "$INSTDIR\enchant\tests.pyc"
  Delete "$INSTDIR\enchant\utils.pyc"
  Delete "$INSTDIR\enchant\lib\enchant\libenchant_ispell.dll"
  Delete "$INSTDIR\enchant\lib\enchant\libenchant_myspell.dll"
  Delete "$INSTDIR\enchant\lib\enchant\README.txt"
  Delete "$INSTDIR\enchant\share\enchant\myspell\de_DE.aff"
  Delete "$INSTDIR\enchant\share\enchant\myspell\de_DE.dic"
  Delete "$INSTDIR\enchant\share\enchant\myspell\en_AU.aff"
  Delete "$INSTDIR\enchant\share\enchant\myspell\en_AU.dic"
  Delete "$INSTDIR\enchant\share\enchant\myspell\en_GB.aff"
  Delete "$INSTDIR\enchant\share\enchant\myspell\en_GB.dic"
  Delete "$INSTDIR\enchant\share\enchant\myspell\en_US.aff"
  Delete "$INSTDIR\enchant\share\enchant\myspell\en_US.dic"
  Delete "$INSTDIR\enchant\share\enchant\myspell\fr_FR.aff"
  Delete "$INSTDIR\enchant\share\enchant\myspell\fr_FR.dic"
  Delete "$INSTDIR\enchant\share\enchant\myspell\README.txt"
  Delete "$INSTDIR\enchant\tokenize\__init__.pyc"
  Delete "$INSTDIR\enchant\tokenize\en.pyc"
  Delete "$INSTDIR\enchant\tokenize\tests.pyc"
  Delete "$INSTDIR\enchant\CmdLineChecker.pyc"
  Delete "$INSTDIR\enchant\GtkSpellCheckerDialog.pyc"
  Delete "$INSTDIR\enchant\wxSpellCheckerDialog.pyc"

  ; Remove shortcuts, if any
  Delete "$SMPROGRAMS\Confidant Mail\*.*"
  Delete "$DESKTOP\Confidant Mail.lnk"

  ; Remove directories used
  RMDir "$SMPROGRAMS\Confidant Mail"
  RMDir "$INSTDIR\Doc"
  RMDir "$INSTDIR\gnupg.nls"
  RMDir "$INSTDIR\src"
  RMDir "$INSTDIR\enchant\lib\enchant"
  RMDir "$INSTDIR\enchant\lib"
  RMDir "$INSTDIR\enchant\checker"
  RMDir "$INSTDIR\enchant\share\enchant\myspell"
  RMDir "$INSTDIR\enchant\share\enchant"
  RMDir "$INSTDIR\enchant\share"
  RMDir "$INSTDIR\enchant\tokenize"
  RMDir "$INSTDIR\enchant"
  RMDir "$INSTDIR"

SectionEnd

; EOF
