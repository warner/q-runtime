
function makeCounter() {
    var value = 0;
    return {next: function() {
                value += 1;
                return value;
                } };
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

