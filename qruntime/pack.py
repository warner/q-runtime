
import json
from twisted.python import log
from .util import makeid
from .common import InnerReference, NativePower

class _PowerEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, NativePower) and self._power_packing._allow_native:
            p = self._power_packing
            name = p._turn.get_swissnum_for_object(obj)
            return {p._nonce: "native", "swissnum": name}
        if isinstance(obj, InnerReference):
            p = self._power_packing
            refid = p._turn.get_swissnum_for_object(obj)
            return {p._nonce: "reference", "swissnum": refid}
        return json.JSONEncoder.default(self, obj)
    def _iterencode_dict(self, dct, markers=None):
        # prevent dicts with keys named "__power__". The nonce-based defense
        # we have here is driven by Javascript's JSON.stringify which makes
        # it easy to prohibit specific key names. In python, we could do this
        # by overriding _iterencode_dict. There's not a lot of point, though,
        # since python code is unconfined anyways (they could just
        # monkeypatch us to remove this check, etc).
        if "__power__" in dct:
            raise ValueError("forbidden __power__ in serializing data")
        return json.JSONEncoder._iterencode_dict(self, dct, markers)

class _Packing:
    def __init__(self, turn, allow_native, allow_memory):
        self._turn = turn
        self._allow_native = allow_native
        self._allow_memory = allow_memory
        # we translate _nonce into "__power__" when we're done, and otherwise
        # prohibit "__power__" as a property name. This prevents inner code
        # from turning swissnums into references by submitting tricky data
        # for serialization.
        self._nonce = "__power_%s__" % makeid()
        self._enc = _PowerEncoder()
        self._enc._power_packing = self

    def _build_fake_memory(self, old_memory):
        memid = self._turn.put_memory(old_memory)
        return {self._nonce: "memory", "swissnum": memid}

    def _pack(self, child_power):
        if self._allow_memory:
            # we handle a top-level Memory object by pretending that the
            # original data contains a {__power__:memory} dict. We must
            # modify a copy, not the original.
            child_power, old_child_power = {}, child_power
            for k in old_child_power: # shallow copy
                if k == "memory":
                    old_memory = old_child_power[k]
                    if old_memory is not None:
                        child_power[k] = self._build_fake_memory(old_memory)
                else:
                    child_power[k] = old_child_power[k]

        return self._enc.encode(child_power).replace(self._nonce, "__power__")

def pack_power(turn, child_power):
    # updates turn.swissnums, turn.native_powers, and turn.memories . Returns
    # inner_power.
    p = _Packing(turn, allow_native=True, allow_memory=True)
    return p._pack(child_power)

def pack_memory(turn, child_power):
    # updates turn.swissnums . Returns data. You need to update turn.memories
    p = _Packing(turn, allow_native=False, allow_memory=False)
    return p._pack(child_power)

def pack_args(turn, child_power):
    # updates turn.swissnums . Returns inner_power.
    p = _Packing(turn, allow_native=False, allow_memory=False)
    return p._pack(child_power)

class Unpacking:
    def __init__(self, turn, allow_native, allow_memory):
        self.turn = turn
        self._allow_native = allow_native
        self._allow_memory = allow_memory

    def unpack(self, power_json):
        # create the inner object. Adds anything necessary to the Turn
        def hook(dct):
            if "__power__" not in dct:
                return dct
            ptype = dct["__power__"]
            if ptype == "native" and self._allow_native:
                name = dct["swissnum"]
                return self.turn.get_native_power(name)
            if ptype == "memory":
                if not self._allow_memory:
                    raise ValueError("only one Memory per Power")
                self._allow_memory = False
                memid = dct["swissnum"]
                return self.turn.get_memory(memid) # data
            if ptype == "reference":
                refid = tuple(dct["swissnum"])
                return self.turn.get_reference(refid) # InnerReference
            raise ValueError("unknown power type '%s'" % (ptype,))
        try:
            unpacked = json.loads(power_json, object_hook=hook)
        except:
            log.msg("unpack_power exception, power_json='%s'" % power_json)
            raise
        return unpacked

def unpack_power(turn, power_json):
    # updates turn.swissnums, turn.native_powers, and turn.memories . Returns
    # inner_power.
    up = Unpacking(turn, allow_native=True, allow_memory=True)
    return up.unpack(power_json)

def unpack_memory(turn, power_json):
    # updates turn.swissnums . Returns data. You need to update turn.memories
    up = Unpacking(turn, allow_native=False, allow_memory=False)
    return up.unpack(power_json)

def unpack_args(turn, power_json):
    # updates turn.swissnums . Returns inner_power.
    up = Unpacking(turn, allow_native=False, allow_memory=False)
    return up.unpack(power_json)


def list_authorities(power_json, is_args):
    authorities = set()
    def hook(dct):
        power_type = dct.get("__power__")
        if power_type is not None:
            if power_type in ("native", "memory") and is_args:
                raise ValueError("bad power type in args '%s'" % (power_type,))
            swissnum = dct["swissnum"]
            if isinstance(swissnum, list): # refid
                swissnum = tuple(swissnum)
            authorities.add( (power_type, swissnum) )
        return dct
    json.loads(power_json, object_hook=hook) # results ignored
    return authorities
