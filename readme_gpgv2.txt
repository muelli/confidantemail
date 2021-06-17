Confidant Mail version 0.26 supports GnuPG version 2.1.x, including the NIST
and Brainpool ECC keys. The main advantage of using GPG 2.1 is access to ECC
keys, which are more secure for a given key length than RSA keys.

GPG 2.1 insists on prompting for a passphrase on its own, and will not let
the calling application handle passphrases. Confidant Mail will detect the
GPG version and behave appropriately. If you want to use an autoclient
with version 2.1, you have to create the private key without a passphrase.

The Windows binaries still ship with GnuPG 1.4.19. I am unsure as to when I
should start shipping 2.1 versions. Right now that is not an option because
the latest version 2.1.2 has no Windows binary available. It should be here:
ftp://ftp.gnupg.org/gcrypt/binary/

I have tested a manually compiled version 2.1.2 on my Ubuntu Linux 14.04
machine successfully, and have also tested the Windows 2.1.1 binary.

-- Mike 2015-03-22
