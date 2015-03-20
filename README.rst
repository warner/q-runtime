Q-Runtime: A Confined-Code Execution Server
===========================================

* Brian Warner, https://github.com/warner/qruntime

This is an experiment in safe remote-object execution. Inspired by the E Vat,
the Waterken server, the ref_send library, my own Foolscap library, and the
use-cases presented by Tahoe-LAFS.

It might turn out to be a horrible idea. At best, it will probably converge
to provide some subset of the features of E and Waterken, plus some annoying
restrictions that make programming in it feel awkward. That's ok too.

This contains a Javascript implementation, using node.js, providing execution
safety via Caja and startSES.js.

What Is It?
-----------

A server that can execute other people's code safely, by running "program
chains" delivered to a network socket.

If you own the server, you can run whatever programs you like. You can also
delegate limited subsets of this power to other people, using a program to
express what the limitations are.

The 'qrt' tool lets you create Vat, which is a server with a base directory.
Each Vat is configured with a root public key, a listening port, and a root
"power.js" file. It also contains a memory store and a program cache.

Each "program" is a string, containing a Node.js-style javascript module,
defining a "main" function that takes a single argument and returns a Promise
for its result. In this module, you can call require() like regular Node.js
programs, but you cannot import system modules: see below for the limitations
of require() and what you can actually do with it.

A "program chain" is a list of programs, each with some number of signatures.
The first program is the "root program", and must be signed by the root key.
The root program has the ability to check the signature of the next program
in the list, and the ability to evaluate and execute its code. By selectively
granting and denying the sub-program access to powerful objects, the root
program provides limited power to the author of the sub-program. The
sub-program can perform this same attenuation to the next program in the
list.

The "root power", provided to a root program, is defined by a regular Node.js
module named "root-power.js", configured in the Vat. This module can use a
fully-functional require() to access system functions, import other modules,
etc. The properties that it exports will be frozen and made available to any
root programs in the "arguments.power" property.

Program chains are effectively executed by concatenating the list of signed
programs into a big string, then writing the whole string into the Vat's
network port. (in practice, some hashing and caching is used to improve
performance, see below for details). The "qrt" tool provides conveniences for
invoking programs by name on a specific vat.

If Alice runs the server, she can configure the root public verifying key to
be whatever she likes, which generally means she knows the root private
signing key and gets to write root programs.

If Alice wants to give a little bit of power to Bob, she creates a new
keypair ("bobkey"), then writes a root program which:

* creates an object which encapsulates the limited power she wants to grant
* asks the system to check the next program in the chain is signed by bobkey
* asks the system to evaluate the next program, yielding a callable function
* invoke the function, passing the limited power object to it

She then signs this root program with her root key, and gives Bob a copy of
the signed root program and the private bobkey.

When Bob wants to exercise this power, he writes his own program (which does
something with the limited-power object it gets), signs it with bobkey,
appends it to the signed root program he got from Alice, and sends the
concatenated pair to the server.

If Bob wants to give an even-more-limited subset of power to Carol, he
repeats the process. Carol will deliver a message that contains three signed
programs concatenated together: Alice's root program, Bob's program, and
Carol's program.

Limiting require()
------------------

At runtime, programs can use a limited form of require(). It uses the same
property names as a normal module (i.e. "module" and "exports"), but uses a
different mapping from require(NAME) to the code that gets loaded. This
mapping prevents require() from providing any sort of power to the caller:
require() is just like a simple string-interpolation with some improved
scoping behavior.

The NAME that require() accepts is required to be the hash of some string of
code. The module loader looks in the program cache for a string with the same
hash, then evaluates it in the usual "module"/"exports" way, and deep-freezes
the result. Modules can deep-freeze their exports object at the end of the
file to improve performance (allowing the loader to share the module object
between callers), but callers cannot tell this is happening. Two different
programs cannot communicate by loading the same module.

(TODO: shared modules may be necessary to enable class-membership tests)

"qrt" provides a build tool that will take a directory of modules (including
a "main.js" entry point) and a node_modules-like import tree, and create a
bundle of hashed modules with rewritten require() statements suitable for
execution in this environment. This allows your code to include
human-readable module names and use tools like NPM to manage modules, while
still obeying the execution rules.

Caching Hashed Programs
-----------------------

Since many program chains will share a common prefix, the invocation protocol
is designed to avoid redundant copies. The protocol refers to programs by
their hash, and delivers the actual program bodies in a separate message.

The core program-chain invocation message is a serialized list of
(programhash, signatures..) tuples. Each programhash is a 32-byte SHA256 hash
of the program text. Each signature contains the 32-byte Ed25519 public
verifying key and the 64-byte signature of the programhash.

The invocation message is generally preceeded by an interactive delivery of
program bodies. The caller can give a list of programhashes to the server and
ask which ones it does not already have. The caller can then preemptively
supply program bodies to the server, which caches them for later use (index
by hash). If the program-chain references a programhash that the server does
not have in the cache, the invocation will fail, with a list of the missing
programs. The caller can supply these program bodies and try again.

A caller which expects to use the server a lot should keep track of which
programs the server already has, and preemptively supply the ones that it
missing. For the common case of executing a small set of program-chain
prefixes (e.g. "methods") with a variety of suffixes (e.g. "arguments"), each
invocation should require only a single message that mostly consists of
unique argument data.

Other Old Stuff
---------------

(maybe out-of-date)

The Vat contains a bunch of "objects", each of which is a piece of code
(implementing a single method) that gets access to some "power". This Power
can include persistent storage (named "Memory"), "references" to other
objects (eventual-send messages to remote objects, both eventual-send and
immediate-call to local objects), access to specific native functions (like a
clock, and the ability to create new objects), and static data parameters
(useful to distinguish between multiple instances of the same class, i.e.
multiple Objects using similar Power). The Memory can contain object
references and static data.

When invoking an object, the caller provides an "arguments" object that can
contain static data and References.

All messages and side-effects are checkpointed: like Waterken, vats which are
terminated in the middle of a message (power failure, etc) will restart from
the most recent checkpoint and atomically re-execute any queued messages.
During each message-handling Turn, state changes and outbound messages are
accumulated until the Turn completes, then are stored in a single atomic
commit.

Outbound messages are sent using ref_send's "try forever" approach. Messages
are encrypted and authenticated using djb's NACL crypto library. Each Vat is
identified by a public key, and messages are individually encrypted with
sequential nonces. Messages are delivered over HTTP to the target Vat, but
future work may include relays or DHT-style delivery schemes.

In essence, you install little bundles of code into the Vat, and get back an
unforgeable identifier for each, then can send messages at them from afar,
and they'll get executed. The code can remember previous messages and send
out new ones.

Safety
------

This runtime aims to provide object-capability security. That means the
Objects created in a Vat can only be invoked by their creator (the code that
called make_object()) or by someone who is given a reference to the object by
someone who already has a reference. No matter what the object's code does,
its effects on the outside world will be limited to the references that it
has been given.

It also aims to provide safe consistency of data, by checkpointing the state
of the Vat after each message is processed. This enables clean recovery from
out-of-band failures (crashes), as long as the disk itself is not
compromised.

Javascript vs Python
--------------------

I'm building both Python and Javascript implementations. I think better in
Python, so I'm working out the ideas there. But Python is too friendly to be
confined (at least not without losing most of its soul).

Javascript benefits from the excellent work of the Google Caja team. By
running the object code in an initSES/startSES-generated environment, and
using Object.freeze() and closure-protected private state in the references
handed to it, hostile JS code can be safely run in a confined sandbox. (As
usual, the hostile code can still DoS the Vat with an infinite loop: future
extensions could have code purchase compute cycles ahead of time and suffer
termination when those limits are exceeded).

Note that this project targets ES5-Strict -compliant JS engines, and will
probably want some Harmony features like WeakMaps and Proxies. It remains to
be seen what sort of compatibility hurdles this will cause.

Since Javascript is the ultimate target of this project, some of the
interfaces have been designed for JS at the expense of Python. In particular,
the "power" argument is a python-dictionary/JS-object, so JS can access
power.memory.foo quite naturally, but Python code must use a verbose
power["memory"]["foo"].

The python entry point is ./bin/qrt . The JS entry point is TBD, maybe "npm
qrt".

Dependencies
------------

For Python, this needs Twisted and python-nacl. For Javascript, it will need
Node.js, the as-yet-unwritten js-nacl bindings, and some subset of the
Caja/es-lab code (perhaps just an embedded copy of startSES.js).

How To Get Started
------------------

The tool is not yet ready for users. Developers who want to hack might not be
killed immediately by the following:

* install twisted, python-nacl
* ./bin/qrt create-node ./NODE1 ; ./bin/qrt create-node ./NODE2
* ./bin/qrt start NODE1 ; ./bin/qrt start NODE2
* ./bin/qrt gossip NODE1 NODE2  # (populates nodes with each others' URLs)
* ./bin/qrt install NODE1 sample-methods  # returns QRID
* ./bin/qrt send -d NODE2 QRID ARGSJSON # sends message from node2 to node1

The 'install' command will add objects to NODE1, and return an invocation
identifier. The 'send' command will tell one node to send a message to an
object (which might be in the same vat, or in a remote one).

Communication Channels
----------------------

Messages are boxed (encrypted and authenticated), and stored in a database
until the remote node has acknowledged receipt, then forgotten. The boxed
messages are sent in HTTP POST request bodies, and a boxed ACK is returned in
the HTTP response body. Failed message sends are retried later.

Each boxed message and response uses a new nonce, implemented with a stored
pairwise (vatA-vatB) counter. Out-of-sequence messages are ACKed and ignored
when they are old (either retransmits from a recovering sender, or replay
attacks from an attacker), or logged and ignored when they are too new
(indicating deeper confusion; this part needs more thought).

Object Invocation
-----------------

Each "object" in this system is a (code, power) tuple. The Power object can
contain one Memory object (always as the ``memory`` property, so
``power.memory`` in JS and ``power['memory']`` in Python).

The code is required to provide a single function, which will be invoked as
f(args, power). These functions can have no persistent state beyond the
'power.memory' argument. An object's code will thus look like::

 # Javascript
 function(args, power) { ... }
 
 # Python
 def call(args, power):
   ...

The Javascript code is further required to be SES-compliant (and thus
ES5-Strict-compliant). By restricting the code to a single function
expression, we deny it local state, and the SES environment prevents access
to global state. Then ensures determinism, confinement, and correct recovery
from a checkpoint (i.e. the checkpoint contains all state that can influence
future behavior). It is not feasible to confine Python code, but the same
guidelines should be followed as good practice.

Each Turn processes a single message sent from elsewhere (maybe local, maybe
remote) delivered to a specific local object. The message contains the
serialized ``args`` object from the caller. Both ``args`` and ``memory`` can
contain anything JSON-serializeable, plus "References" that point to other
objects.

As the function runs, any ``Reference`` it holds (either received from the
caller in ``args``, from its creator in ``power``, or from a previous
incarnation of itself in ``power.memory``) can be used to send messages to
other objects. These objects might live in the same Vat, or on some remote
Vat. It can always do "eventual-send" calls to these objects, like::

 # Javscript
 o.sendOnly(args)    # safe on real References, but local 'o' might not be
 Q.sendOnly(o, args) # always safe
 
 # Python
 o.sendOnly(args)

The eventual-send is guaranteed to execute in a subsequent Turn of the event
loop, so it can never raise an exception or cause side-effects that are
visible to the current object. In the current version, eventual-send calls do
not return anything (Promises will be implemented later, and use ``o.send``
instead of ``o.sendOnly``).

When the ``Reference`` points to something in the same Vat, the caller can
instead choose to do an immediate-call. These behave like normal
synchronous/blocking function calls, with the usual re-entrancy hazards
thereof. They can also return values::

 # Javascript
 results = o.call(args)
 results = Q.call(o, args)

 # Python
 results = o.call(args)

Immediate calls can also accept non-JSON-serializable arguments, like
functions. Invoking ``call()`` on a remote object will throw an error.

Non-``Reference`` based authority (i.e. local platform services) are
represented by ``NativePower`` objects, which are called like normal
synchronous functions. These are delivered as properties of the ``power``
argument, and may be withheld by the object creator. The only such power
defined so far is ``make_object()``, which takes code and power, and returns
a new object ``Reference``.

Creating Objects
----------------

::

 # Python
 ref = power.make_object(code, newpower)

Objects are created by other objects, when they invoke the ``make_object``
native power. This takes a string of code (defining a single function, as
described above), and a description of the power that the new object is
supposed to receive each time it is invoked. We say that the "parent object"
creates a "child object".

The simplest power that a parent can grant to its new child is ``power``,
i.e. the parent's full power, including its ``memory`` object. This
effectively makes the child into a clone of the parent but running different
code: you could then think of parent and child as two different methods of
the same JS or Python object (both have access to the same state, but do
different things with it).

The other simple power to grant is an empty object (or ``None`` in python).
This gives the child no power (not even memory). The only way for the child
to affect the world is if you pass it an argument that contains power, or if
you act upon the value it returns. This is like the DeepFrozen auditor in E.

Other forms of power can be granted by passing other things as the second
argument of ``make_object``. ``newpower`` is parsed to figure out what the
child should be given upon each invocation. Any ``NativePower`` objects
passed as top-level properties of ``newpower`` will be granted to the child.
Any static data or ``Reference`` at any level of the ``newpower`` object will
appear in the same position in the child's ``power`` argument.

``newpower.memory`` is treated specially. There are three cases:

* ``newpower.memory === power.memory``: this signals that the child should
  have the same Memory slot as the parent: any changes made by the child will
  be reflected in the parent (the next time the parent is invoked). Note that
  this compares object identity, not merely contents.
* ``newpower.memory == undefined``: this withholds persistent state from the
  child. Since Memory cannot be provided any other way (in arguments, or
  other places in Power), this prevents the child from having any
  side-effects except by sending messages over references passed into
  ``args``, or by returning values when invoked.
* ``newpower.memory == {other}``: this creates a new Memory object, unique to
  the child, populating it with ``other`` as the initial contents.

All other static data in ``newpower`` is simply serialized and provided in
the same form in the child's ``power``.

A convenience function named ``add`` is provided in the child's environment,
to make it easy to construct ``newpower`` with controlled variations of the
parent's power::

 newpower = add(power, {memory: {}})  // new empty memory
 newpower = add(power, {memory: null}) // forbid memory
 newpower = add(power, {stuff: "foo"}) // static data




Future Work
-----------

* HTTP integration: serve regular HTTP (by allowing objects to register as
  handlers for various URL prefixes)
* HTML integration: build HTML on the server side, give handlers control over
  DIVs and SPANs but not the ability to serve raw HTML/JS, preventing objects
  from getting control over browser origin authority.
* JS integration: similar, but wrap outbound HTML in the Caja verifier,
  enabling objects to execute confined code on the browser that gets specific
  powers but does not get full control over the DOM or the origin.
* Billing: buy CPU time and memory on commodity object servers with Bitcoin
