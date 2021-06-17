# fixups for mac build

# export PATH=/usr/local/bin:${PATH}
# export LD_LIBRARY_PATH=/usr/local/lib

rm -rf build
if [ -d build ]; then
	echo "oops build directory was not deleted"
	exit 1
fi

python setup-macos.py bdist_mac

# cp /usr/local/lib/python2.7/site-packages/cryptography/_Cryptography_cffi_2a871178xb3816a41.so build/Confidant\ Mail-0.43.app/Contents/MacOS/_Cryptography_cffi_2a871178xb3816a41.so
# cp /usr/local/lib/python2.7/site-packages/cryptography/_Cryptography_cffi_4ee21876x41fb9936.so build/Confidant\ Mail-0.43.app/Contents/MacOS/_Cryptography_cffi_4ee21876x41fb9936.so
# cp /usr/local/lib/python2.7/site-packages/cryptography/_Cryptography_cffi_590da19fxffc7b1ce.so build/Confidant\ Mail-0.43.app/Contents/MacOS/_Cryptography_cffi_590da19fxffc7b1ce.so
# cp /usr/local/lib/python2.7/site-packages/cryptography/_Cryptography_cffi_8f86901cxc1767c5a.so build/Confidant\ Mail-0.43.app/Contents/MacOS/_Cryptography_cffi_8f86901cxc1767c5a.so
cp /usr/local/lib/python2.7/site-packages/_cffi_backend.so ./build/exe.macosx-10.9-x86_64-2.7/
cp /usr/local/lib/python2.7/site-packages/_cffi_backend.so ./build/Confidant\ Mail-0.43.app/Contents/MacOS/

mkdir build/Confidant\ Mail-0.43.app/Contents/MacOS/enchant
cp \
/usr/local/lib/python2.7/site-packages/enchant/lib/enchant/libenchant_ispell.so \
/usr/local/lib/python2.7/site-packages/enchant/lib/enchant/libenchant_myspell.so \
build/Confidant\ Mail-0.43.app/Contents/MacOS/enchant
cp -r /usr/local/lib/python2.7/site-packages/enchant/share \
build/Confidant\ Mail-0.43.app/Contents/MacOS/


cp \
/usr/local/lib/python2.7/site-packages/enchant/lib/libenchant.1.dylib \
/usr/local/lib/python2.7/site-packages/enchant/lib/libenchant.1.dylib \
/usr/local/lib/python2.7/site-packages/enchant/lib/libglib-2.0.0.dylib \
/usr/local/lib/python2.7/site-packages/enchant/lib/libgmodule-2.0.0.dylib \
/usr/local/lib/python2.7/site-packages/enchant/lib/libiconv.2.dylib \
/usr/local/lib/python2.7/site-packages/enchant/lib/libintl.8.dylib \
build/Confidant\ Mail-0.43.app/Contents/MacOS

rm build/Confidant\ Mail-0.43.app/Contents/MacOS/libwx_baseu-3.0.dylib
rm build/Confidant\ Mail-0.43.app/Contents/MacOS/libwx_baseu_xml-3.0.dylib
rm build/Confidant\ Mail-0.43.app/Contents/MacOS/libwx_osx_cocoau_adv-3.0.dylib
rm build/Confidant\ Mail-0.43.app/Contents/MacOS/libwx_osx_cocoau_core-3.0.dylib
rm build/Confidant\ Mail-0.43.app/Contents/MacOS/libwx_osx_cocoau_html-3.0.dylib

cp /usr/local/Cellar/openssl/1.0.2l/lib/libcrypto.1.0.0.dylib \
  /usr/local/Cellar/openssl/1.0.2l/lib/libssl.1.0.0.dylib \
  build/Confidant\ Mail-0.43.app/Contents/MacOS/

cp help.zip \
  build/Confidant\ Mail-0.43.app/Contents/MacOS/

( cd /usr/local/Cellar/gnupg/2.1.21 ; tar cf - bin share libexec ) | \
( cd build/Confidant\ Mail-0.43.app/Contents/MacOS ; tar xf - )

( cd /usr/local/Cellar ; tar cf - pinentry-mac ) | \
( cd build/Confidant\ Mail-0.43.app/Contents/MacOS ; tar xf - )

( cd /usr/local/Cellar/wxmac/3.0.2/lib ; tar cf - . ) | \
( cd build/Confidant\ Mail-0.43.app/Contents/MacOS ; tar xf - )

( cd /usr/local/Cellar/libgcrypt/1.7.7/lib ; tar cf - *.dylib ) | \
( cd build/Confidant\ Mail-0.43.app/Contents/MacOS ; tar xf - )

( cd /usr/local/Cellar/libksba/1.3.5/lib ; tar cf - *.dylib ) | \
( cd build/Confidant\ Mail-0.43.app/Contents/MacOS ; tar xf - )

( cd /usr/local/Cellar/libgpg-error/1.27/lib ; tar cf - *.dylib ) | \
( cd build/Confidant\ Mail-0.43.app/Contents/MacOS ; tar xf - )

( cd /usr/local/Cellar/libassuan/2.4.3_1/lib ; tar cf - *.dylib ) | \
( cd build/Confidant\ Mail-0.43.app/Contents/MacOS ; tar xf - )

( cd /usr/local/Cellar/npth/1.5/lib ; tar cf - *.dylib ) | \
( cd build/Confidant\ Mail-0.43.app/Contents/MacOS ; tar xf - )

( cd /usr/local/Cellar/gettext/0.19.8.1/lib ; tar cf - *.dylib ) | \
( cd build/Confidant\ Mail-0.43.app/Contents/MacOS ; tar xf - )

( cd /usr/local/Cellar/libusb/1.0.21/lib ; tar cf - *.dylib ) | \
( cd build/Confidant\ Mail-0.43.app/Contents/MacOS ; tar xf - )

cp help.zip build/Confidant\ Mail-0.43.app/Contents/MacOS/ 

( cd build/Confidant\ Mail-0.43.app/Contents/MacOS ; ln -s . lib )

for fn in \
  build/Confidant\ Mail-0.43.app/Contents/MacOS/bin/gpg \
  build/Confidant\ Mail-0.43.app/Contents/MacOS/bin/gpgconf \
  build/Confidant\ Mail-0.43.app/Contents/MacOS/bin/gpg-agent \
  build/Confidant\ Mail-0.43.app/Contents/MacOS/bin/gpg-connect-agent \
  build/Confidant\ Mail-0.43.app/Contents/MacOS/libexec/scdaemon \
  build/Confidant\ Mail-0.43.app/Contents/MacOS/libgcrypt.20.dylib \
  build/Confidant\ Mail-0.43.app/Contents/MacOS/libassuan.0.dylib \
  build/Confidant\ Mail-0.43.app/Contents/MacOS/libksba.8.dylib \
  build/Confidant\ Mail-0.43.app/Contents/MacOS/libgpg-error.0.dylib \
; do
sudo install_name_tool -change /usr/local/opt/gettext/lib/libintl.8.dylib @executable_path/../libintl.8.dylib "${fn}"
sudo install_name_tool -change /usr/local/opt/sqlite/lib/libsqlite3.0.dylib @executable_path/../libsqlite3.0.dylib "${fn}"
sudo install_name_tool -change /usr/local/opt/libgcrypt/lib/libgcrypt.20.dylib @executable_path/../libgcrypt.20.dylib "${fn}"
sudo install_name_tool -change /usr/local/opt/libgpg-error/lib/libgpg-error.0.dylib @executable_path/../libgpg-error.0.dylib "${fn}"
sudo install_name_tool -change /usr/local/opt/libassuan/lib/libassuan.0.dylib @executable_path/../libassuan.0.dylib "${fn}"
sudo install_name_tool -change /usr/local/opt/npth/lib/libnpth.0.dylib @executable_path/../libnpth.0.dylib "${fn}"
sudo install_name_tool -change /usr/local/opt/libusb/lib/libusb-1.0.0.dylib @executable_path/../libusb-1.0.0.dylib "${fn}"
sudo install_name_tool -change /usr/local/opt/libksba/lib/libksba.8.dylib @executable_path/../libksba.8.dylib "${fn}"
done


# EOF
