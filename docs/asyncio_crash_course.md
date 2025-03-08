# Asynchronous Python programming

Async IO is a single-threaded, single-process design: it uses cooperative multitasking

Python’s async model is built around concepts such as coroutines, callbacks, events, transports, protocols, and futures

A coroutine is a function that can suspend its execution before reaching return

Coroutines that contain synchronous calls block other coroutines and tasks from running

A coroutine is function declared with `async def`
- Using `await` and/or `return` creates a coroutine function. To call a coroutine function, you must `await` it to get its results
- Using `yield` creates an asynchronous generator, which you iterate over with `async for`

The keyword `await` passes function control back to the event loop -- "goto to next work item"

Using `asyncio.Queue()` allows for N-producers to add their output to M consumers

Use `create_task()` to start the execution of a coroutine object, be sure to `await` it

You can think of the Event Loop as something like a `while True` loop that monitors coroutines, taking feedback on what's idle, and looking around for things that can be executed in the meantime

Coroutines should use try/finally blocks to robustly perform clean-up logic, when caught explicitly, `asyncio.CancelledError` should be propagated to support `timeout()`

Using `sleep(0)` provides an optimized path to allow other tasks to run, useful in long-running functions to avoid blocking the event loop for the full duration of the function call

- https://realpython.com/python-async-features/
- https://realpython.com/async-io-python/
- https://dev-kit.io/blog/python/asyncio-design-patterns

## Interesting APIs

- run()
  - Create event loop, run a coroutine, close the loop, and return any results
- create_task()
  - Start an asyncio Task, then return it for later await-ing
- timeout()
  - Run a task with a timeout
- shield()
  - Shield from cancellation
- to_thread()
  - Move a synchronous blocking call from an async function to the thread pool
- sleep()
  - Yield execution back to the async runloop
- run_coroutine_threadsafe()
  - Schedule a task from a synchronous call into an asyncio loop
- PriorityQueue()
  - A Queue that retrieves entries in priority order (lowest first).
- create_subprocess_exec()
  - On Windows, subprocesses are provided by `ProactorEventLoop` only (default), `SelectorEventLoop` has no subprocess support
  - https://docs.python.org/3.11/library/asyncio-platforms.html#windows
  - `aiomqtt` requires `SelectorEventLoop`
- Event
  - Notify multiple asyncio tasks that some event has happened.
- Condition
  - Wait for some event to happen and then get exclusive access to a shared resource.
- get_running_loop()
