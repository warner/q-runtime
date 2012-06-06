// node --harmony_weakmaps
//"use strict";

// for some reason, this 'const' is rejected in strict mode
const crypto = require("crypto");

function Power() {}

function old_experiment() {
    function makeCounter() {
        var value = 0;
        return {next: function() { value += 1; return value; },
                toString: function() { return this.next(); }
               };
    }
    var counter = makeCounter();

    var v = {foo: 123,
             toJSON: function() { return 'bar'+counter.next(); }
            };
    console.log(JSON.stringify(v));
    console.log(JSON.stringify(v));

    var x = {foo: 123,
             x1: "magic, replace me"
            };
    var evil = {foo: 123,
                _special: "haha, turning a swissnum into a Reference"
               };
    function replacer(propname, oldvalue) {
        //console.log("replace", propname, oldvalue, this);
        if (propname == "x1")
            return {_special: "swissnum"};
        if (propname == "_special")
            throw "_special is forbidden";
        return oldvalue;
    }
    //console.log(JSON.stringify(x, replacer));

    var o = {foo: 1, p: new Power() };

    function safe_serialize(obj) {
        // generate this randomly each time
        var token = "i6edzesaedxdb7x2a4ot6252r4suwdt6ctv4quw4b4zt6pmwjlfa";
        var placeholder = "_special_"+token;
        var r = function(propname, oldvalue) {
            //console.log("replace", propname, oldvalue, this);
            if (propname == "x1") {
                var newvalue = {};
                newvalue[placeholder] = "swissnum";
                return newvalue;
            }
            if (propname == "_special")
                throw "_special is forbidden";
            return oldvalue;
        };
        return JSON.stringify(obj, r).replace(RegExp(placeholder,"g"),
                                              "_special");
    }
    console.log(safe_serialize(x));
    // this should throw
    //console.log(safe_serialize(evil));

    var v2 = new WeakMap();
    // note: the WeakMap API is .set(k,v) and .get(k). But since WeakMaps are
    // objects too, you can set normal properties on them with m[name]=v . Such
    // properties are not weakly held. Enumeration (and JSON.stringify) only
    // looks at normal properties, not the weakly-held ones.
    v2[counter] = 123;
    console.log(JSON.stringify(v2));
    console.log(JSON.stringify(v2));
    console.log(counter);
    console.log(counter);
}
//old_experiment();

function Labeler() {
    var et = WeakMap();
    var count = 0;
    return Object.freeze({
      label: function(obj) {
        var result = et.get(obj);
        if (result) { return result; }
        et.set(obj, ++count);
        return count;
      }
    });
};

function experiment() {
    console.log("START EXPERIMENT");
    var makeClid = Labeler();
    var clist = new WeakMap();
    function Power() {
        var swissnum = makeClid.label(this);
        console.log("creating Power", swissnum);
        //console.log(this, swissnum);
        clist.set(this, swissnum);
    };

    var o = {foo: 1, p: new Power(), q: new Power() };

    function serialize_power(obj) {
        // generate this randomly each time
        var token = crypto.randomBytes(16).toString("hex");
        var placeholder = "_special_"+token;
        var r = function(propname, oldvalue) {
            //console.log("replace", propname, oldvalue, this);
            if (oldvalue instanceof Power) {
                var newvalue = {};
                newvalue[placeholder] = clist.get(oldvalue);
                return newvalue;
            }
            if (propname == "_special")
                throw "_special is forbidden";
            return oldvalue;
        };
        return JSON.stringify(obj, r).replace(RegExp(placeholder,"g"),
                                              "_special");
    }
    console.log(serialize_power(o));

    var evil = {foo: 123, p: new Power(), q: {_special: "forged"} };
    
    try {
        console.log("serializing evil", evil);
        var s =  serialize_power(evil);
        console.log(" bad, evil passed", s);
    } catch (e) {
        console.log(" good, evil prevented:", e);
    }
}

experiment();

