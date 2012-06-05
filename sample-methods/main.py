def call(args, power):
    memory = power["memory"]
    log("I HAVE POWER!")
    #log("a is %s" % args["a"])
    log("memory is %r" % (memory,))
    if "counter" not in memory:
        memory["counter"] = 0
    memory["counter"] += 1
    log("counter is now %d" % memory["counter"])
    return "ignored"

