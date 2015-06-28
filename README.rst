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

Persistence
-----------

Every program (including the root) is effectively loaded from scratch for
each delivered message. To provide Waterken-style checkpoint semantics, given
our language's lack of orthogonal persistence, we cannot rely upon state
stored in RAM (or anywhere outside of the checkpoint). To guarantee
deterministic execution, we must not even look at such state: the program
must be shut down after every message. (In practice, the root-power.js module
gets to do whatever it wants, but if it wants to provide checkpointing and
determinism, it needs to follow these rules).

So the only way to hold persistent data is for the root program to use
external storage (disk or database), and to grant (limited) access to
subprograms. You might think of this as granting a database view to a
subprogram, or offering a "set_state()" function which can only modify a row
dedicated to a particular client (distinguished by looking at the particular
key which signed the client message).
