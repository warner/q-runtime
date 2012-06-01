import os, base64

def make_nonce():
    return base64.b32encode(os.urandom(32)).strip("=").lower()
