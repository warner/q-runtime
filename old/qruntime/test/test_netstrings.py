import unittest

from ..netstring import make_netstring, split_netstrings

class Netstring(unittest.TestCase):
    def test_create(self):
        self.failUnlessEqual(make_netstring("abc"), "3:abc,")
    def test_split(self):
        a1 = make_netstring("abc")
        a2 = make_netstring("def")
        a3 = make_netstring("")
        a4 = make_netstring(":,")
        a5 = make_netstring("ghi")
        self.failUnlessEqual(split_netstrings(a1+a2+a3+a4+a5),
                             ["abc", "def", "", ":,", "ghi"])
    def test_leftover(self):
        self.failUnlessRaises(ValueError,
                              split_netstrings, "3:abc,extra")
