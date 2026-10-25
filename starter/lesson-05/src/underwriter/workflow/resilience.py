"""Per-node timeout, retry and failure policy for the workflow graph (lesson 5).

Every node in the graph runs through `run_node`, with its own NodePolicy:

    timeout_s     wall-clock budget for one attempt
    max_attempts  attempts in total (1 = no retry)
    on_failure    what the graph does when the last attempt fails:
                  "escalate"  stop and send the case to a human (WORKFLOW_ERROR)
                  "degrade"   carry on without this node's output, and say so
                  "fallback"  the node supplies a safe default itself

Only transient errors are retried: timeouts and TransientNodeError. A ValueError is
a bug, and retrying a bug only hides it.

Node faults rehearse each failure on demand (refused when APP_ENV=production):

    NODE_FAULTS="policy=error"        # raises a non-transient error
    NODE_FAULTS="income=transient"    # fails the first attempt only, retry succeeds
    NODE_FAULTS="analyze=hang"        # runs past its timeout

A timed-out attempt's thread can't be killed in Python; it finishes in the
background and its result is thrown away. Lesson 8 moves the I/O to asyncio, where
cancellation is real.

You build this module in this lesson. Its public API, behaviour and exact messages
are in lessons/05-agentic-workflows/SPEC.md; the tests are the answer key.
"""
