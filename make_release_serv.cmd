rem make a windows release
c:
cd \projects\keymail
rmdir/q/s build\exe.win32-2.7
if exist build\exe.win32-2.7 goto fail1
python setup-s.py build
rem move "build\exe.win32-2.7\cryptography._Cryptography_cffi_3a414503xe735153f.pyd" "build\exe.win32-2.7\_Cryptography_cffi_3a414503xe735153f.pyd"
move "build\exe.win32-2.7\cryptography._Cryptography_cffi_4ee21876x41fb9936.pyd" "build\exe.win32-2.7\_Cryptography_cffi_4ee21876x41fb9936.pyd"
move "build\exe.win32-2.7\cryptography._Cryptography_cffi_590da19fxffc7b1ce.pyd" "build\exe.win32-2.7\_Cryptography_cffi_590da19fxffc7b1ce.pyd"
move "build\exe.win32-2.7\cryptography._Cryptography_cffi_8f86901cxc1767c5a.pyd" "build\exe.win32-2.7\_Cryptography_cffi_8f86901cxc1767c5a.pyd"
xcopy "C:\Program Files (x86)\GNU\GnuPG\*.*" "build\exe.win32-2.7\" /s/e/c/h
mkdir "build\exe.win32-2.7\src"
xcopy *.py "build\exe.win32-2.7\src"
xcopy spec.odt "build\exe.win32-2.7\src"
cd "build\exe.win32-2.7"
zip -r ..\confmail-server-winpe.zip *.*
cd ..\..
echo done
goto :eof

:fail1
echo error - build directory still exists after remove
goto :eof
