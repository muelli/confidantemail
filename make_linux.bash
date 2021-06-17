#!/bin/bash
# make for linux

export LD_LIBRARY_PATH=/usr/local/lib

rm -rf build
python setup-linux.py build
uname -a | grep x86_64
if [ $? -eq 0 ]; then
	cd build/exe.linux-x86_64-2.7
	mv 'cryptography._Cryptography_cffi_4ee21876x41fb9936.so' '_Cryptography_cffi_4ee21876x41fb9936.x86_64-linux-gnu.so'
	mv 'cryptography._Cryptography_cffi_590da19fxffc7b1ce.so' '_Cryptography_cffi_590da19fxffc7b1ce.x86_64-linux-gnu.so'
	mv 'cryptography._Cryptography_cffi_8f86901cxc1767c5a.so' '_Cryptography_cffi_8f86901cxc1767c5a.x86_64-linux-gnu.so'
	cp ../../help.zip ../../confmail-signer-key.asc .
	( cd /usr ; tar cpf - share/hunspell ) | tar xvf -

else	
	cd build/exe.linux-i686-2.7
	mv 'cryptography._Cryptography_cffi_4ee21876x41fb9936.so' '_Cryptography_cffi_4ee21876x41fb9936.so'
	mv 'cryptography._Cryptography_cffi_590da19fxffc7b1ce.so' '_Cryptography_cffi_590da19fxffc7b1ce.so'
	mv 'cryptography._Cryptography_cffi_8f86901cxc1767c5a.so' '_Cryptography_cffi_8f86901cxc1767c5a.so'
	cp ../../help.zip ../../confmail-signer-key.asc .
	( cd /usr ; tar cpf - share/hunspell ) | tar xvf -
fi
