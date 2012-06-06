
class InnerReference:
    def __init__(self, turn):
        self._turn = turn
    def sendOnly(self, args):
        return self._turn.sendOnly(self, args)
    def call(self, args):
        return self._turn.local_sync_call(self, args)

class NativePower:
    def __init__(self, f):
        self.f = f
    def __call__(self, *args, **kwargs):
        return self.f(*args, **kwargs)
