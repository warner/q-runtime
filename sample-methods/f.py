def call(args, power):
    log("I HAVE POWER!")
    log("a is %s" % args["a"])
    if "count" not in power.memory:
        power.memory["count"] = 0
    power.memory["count"] += 1
    log("counter is now %d" % power.memory["count"])
    return "ignored"

