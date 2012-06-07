Q-Runtime: A Confined-Code Execution Server
===========================================

* Brian Warner, https://github.com/warner/qruntime

This is an experiment in safe remote-object execution. Inspired by the E Vat,
the Waterken server, the ref_send library, my own Foolscap library, and the
use-cases presented by Tahoe-LAFS.

It might turn out to be a horrible idea. At best, it will probably converge
to provide some subset of the features of E and Waterken, plus some annoying
restrictions that make programming in it feel awkward. That's ok too.

This contains both Python and Javascript implementations (using Twisted and
node.js respectively). Only the Javascript version provides execution safety
(via Caja and startSES.js). The Python version is useful for other things,
but not to run stranger's code safely.

What Is It?
-----------

A server that can execute other people's code safely.

The 'qrt' tool lets you create one or more Vats, which are each a server that
has its own base directory. The Vat contains a bunch of "objects", each of
which is a piece of code (implementing a single method) that gets access to
some "power". This Power can include persistent storage (named "Memory"),
"references" to other objects (eventual-send messages to remote objects, both
eventual-send and immediate-call to local objects), access to specific native
functions (like a clock, and the ability to create new objects), and static
data parameters (useful to distinguish between multiple instances of the same
class, i.e. multiple Objects using similar Power). The Memory can contain
object references and static data.

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
unforgeably identifier for each, then can send messages at them from afar,
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
termination ben those limits are exceeded).

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

As the function runs, any ``Reference``s it holds (either received from the
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
 o.call(args)
 Q.call(args)

 # Python
 o.call(args)

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
This gives the child no power (not even memory). The only side-effects that
the child will be able to cause will be through messages sent to it. This is
like the DeepFrozen auditor in E.

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
