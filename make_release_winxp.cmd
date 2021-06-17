rem make a windows release
c:
cd \projects\keymail
rmdir/q/s build
if exist build goto fail1
python setup-xp.py build

rem move "build\exe.win32-2.7\cryptography._Cryptography_cffi_3a414503xe735153f.pyd" "build\exe.win32-2.7\_Cryptography_cffi_3a414503xe735153f.pyd"
rem move "build\exe.win32-2.7\cryptography._Cryptography_cffi_4ee21876x41fb9936.pyd" "build\exe.win32-2.7\_Cryptography_cffi_4ee21876x41fb9936.pyd"
rem move "build\exe.win32-2.7\cryptography._Cryptography_cffi_590da19fxffc7b1ce.pyd" "build\exe.win32-2.7\_Cryptography_cffi_590da19fxffc7b1ce.pyd"
rem move "build\exe.win32-2.7\cryptography._Cryptography_cffi_8f86901cxc1767c5a.pyd" "build\exe.win32-2.7\_Cryptography_cffi_8f86901cxc1767c5a.pyd"
xcopy C:\Python27\Lib\site-packages\_cffi_backend.pyd build\exe.win32-2.7\
xcopy "C:\Program Files\GNU\GnuPG\*.*" "build\exe.win32-2.7\" /s/e/c/h
del help.zip
cd help
zip ..\help.zip *.*
cd ..
copy help.zip "build\exe.win32-2.7\help.zip"
mkdir "build\exe.win32-2.7\enchant"
xcopy c:\python27\lib\site-packages\enchant "build\exe.win32-2.7\enchant" /s
mkdir "build\exe.win32-2.7\src"
copy address_book.py build\exe.win32-2.7\src
copy bypass_token.py build\exe.win32-2.7\src
copy changepass.py build\exe.win32-2.7\src
copy client.py build\exe.win32-2.7\src
copy client_agent.py build\exe.win32-2.7\src
copy config_chooser.py build\exe.win32-2.7\src
copy config_dialog.py build\exe.win32-2.7\src
copy daemon.py build\exe.win32-2.7\src
copy dequeue_dialog.py build\exe.win32-2.7\src
copy entangled_store.py build\exe.win32-2.7\src
copy fetchmail.py build\exe.win32-2.7\src
copy filelock.py build\exe.win32-2.7\src
copy filestore.py build\exe.win32-2.7\src
copy findpaths.py build\exe.win32-2.7\src
copy find_gpg_homedir.py build\exe.win32-2.7\src
copy flatstore.py build\exe.win32-2.7\src
copy folders.py build\exe.win32-2.7\src
copy global_config.py build\exe.win32-2.7\src
copy gnupg.py build\exe.win32-2.7\src
copy gui.py build\exe.win32-2.7\src
copy images.py build\exe.win32-2.7\src
copy images2.py build\exe.win32-2.7\src
copy keyannounce.py build\exe.win32-2.7\src
copy key_value_file.py build\exe.win32-2.7\src
copy message_edit_window.py build\exe.win32-2.7\src
copy message_list_window.py build\exe.win32-2.7\src
copy message_view_window.py build\exe.win32-2.7\src
copy postmessage.py build\exe.win32-2.7\src
copy proofofwork.py build\exe.win32-2.7\src
copy remote_dns_lookup.py build\exe.win32-2.7\src
copy repair_account.py build\exe.win32-2.7\src
copy rotate_key.py build\exe.win32-2.7\src
copy rotate_key_dialog.py build\exe.win32-2.7\src
copy search_dialog.py build\exe.win32-2.7\src
copy server.py build\exe.win32-2.7\src
copy server_send.py build\exe.win32-2.7\src
copy server_notify.py build\exe.win32-2.7\src
copy setup-linux.py build\exe.win32-2.7\src
copy setup-s.py build\exe.win32-2.7\src
copy setup.py build\exe.win32-2.7\src
copy setup-xp.py build\exe.win32-2.7\src
copy setup-macos.py build\exe.win32-2.7\src
copy showhelp.py build\exe.win32-2.7\src
copy storutil.py build\exe.win32-2.7\src
copy syncstore.py build\exe.win32-2.7\src
copy udp_protocol.py build\exe.win32-2.7\src
copy validate_merge.py build\exe.win32-2.7\src
copy autoclient_echo.py build\exe.win32-2.7\src
copy autoclient_fileserv.py build\exe.win32-2.7\src
copy autoclient_listserv.py build\exe.win32-2.7\src
copy autoclient_notify.py build\exe.win32-2.7\src
copy spec.odt build\exe.win32-2.7\src
copy confmail.nsi build\exe.win32-2.7\src
copy confmail.winxp.nsi build\exe.win32-2.7\src
copy make_release.cmd build\exe.win32-2.7\src
copy make_release_serv.cmd build\exe.win32-2.7\src
copy make_release_winxp.cmd build\exe.win32-2.7\src
copy make_release_macos.bash build\exe.win32-2.7\src
copy confmail-signer-key.asc build\exe.win32-2.7\src
cd "build\exe.win32-2.7"
zip -r ..\confmail-winpe.zip *.*
cd src
zip ..\..\confmail-src.zip *.*
cd ..
zip ..\confmail-src.zip help.zip
cd ..\..
zip build\confmail-src.zip keyicon.ico build-notes.txt readme_gpgv2.txt
zip -r build\confmail-src.zip entangled make_linux.bash
copy confmail.nsi build\exe.win32-2.7\
"\Program Files\NSIS\makensis.exe" c:\projects\keymail\build\exe.win32-2.7\confmail.nsi
move build\exe.win32-2.7\confmailinst.exe build\confmailinst-xp.exe
echo done
goto :eof

:fail1
echo error - build directory still exists after remove
goto :eof
