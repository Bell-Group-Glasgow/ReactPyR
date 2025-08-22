"""
This implementation is mostly copied from asyncio.tasks (Python 3.8) while making the necessary changes.

:copyright: 2021 Nándor Mátravölgyi
:license: Apache2, see LICENSE for more details.
"""
import sys
from asyncio import CancelledError, ensure_future, TimeoutError

try:
    from asyncio import get_running_loop
except ImportError:  # pragma: no cover
    from asyncio import get_event_loop as get_running_loop
from functools import partial


def _release_waiter(waiter, *args):  # copied from from asyncio.tasks
    if not waiter.done():
        waiter.set_result(None)


def _handle_cancelling_with_inner_completion(loop, fut, fut_result, res_exception, race_handler):
    if race_handler:
        try:
            race_handler(fut_result, res_exception)
        except Exception as e:
            loop.call_exception_handler({"message": "wait_for2 race_handler failed", "exception": e, "future": fut})
    raise CancelledWithResultError(fut_result, res_exception)


async def _cancel_and_wait2(fut, loop, cancelling, race_handler):
    """
    The builtin implementation of _cancel_and_wait is made in a way to ensure cancellation of it will always be
    possible, at the cost of ensuring that the wrapped future shall terminate inside it.

    The documentation says that
        - "If a timeout occurs, it cancels the task and raises asyncio.TimeoutError."
        - "The function will wait until the future is actually cancelled"
    , but their combination will result in undocumented behaviour:
        If a timeout occurs and the inner future is cancelled, then cancelling the waiter will instantly cancel
        it and the inner future may still be running, which does not fulfill the second promise.

    This implementation will prioritize cancellation or the result of the inner future dynamically as it makes sense.
    """
    if not cancelling:
        # We need to detect explicit cancellations so the good-case value returning will not be used.
        waiter = loop.create_future()
        cb = partial(_release_waiter, waiter)
        fut.add_done_callback(cb)
        fut.cancel()
        try:
            await waiter
        except CancelledError:
            cancelling = True  # explicitly cancelling the inner from now on
        finally:
            fut.remove_done_callback(cb)
    else:
        fut.cancel()
    # At this point there's no benefit of wrapping the future with a waiter since we're cancelling it?
    try:
        fut_result = await fut
        if not cancelling:
            return fut_result
    except CancelledError as exc:
        if cancelling:
            raise exc
        raise TimeoutError() from exc
    except Exception as exc:
        if not cancelling:
            raise exc
        fut_result = exc
        res_exception = True
    else:
        res_exception = False
    # The waiting construct is already being cancelled, we need to discard/handle the inner future's
    # result here to adhere to the cancellation request.
    _handle_cancelling_with_inner_completion(loop, fut, fut_result, res_exception, race_handler)


class CancelledWithResultError(CancelledError):
    def __init__(self, result, exc):
        super(CancelledWithResultError, self).__init__(result, exc)

    @property
    def result(self):
        return self.args[0]

    @property
    def is_exception(self):
        return self.args[1]


async def wait_for(fut, timeout, *, loop=None, race_handler=None):
    """
    Alternate implementation of asyncio.wait_for() based on the version from Python 3.8. It handles simultaneous
    cancellation of wait and completion of future differently and consistently across python versions 3.6+.

    Builtin asyncio.wait_for() behaviours:
        Python 3.6, 3.7 and PyPy3:
            Cancellation of wait_for could lose the completed future's result.
        Python 3.8+:
            Cancellation of wait_for could lose the cancellation request.

    Whenever waiting for a future's result the user expects to either have the future completed or cancelled.
    Unfortunately due to technical details there is a chance that both will happen simultaneously. The builtin version
    of asyncio.wait_for() shipped with Python either handles one or the other only. If losing the future's result or
    ignoring the cancellation is critical to the application it may not be suitable for use.

    Using this implementation, in case both conditions occur at the same time a subclassed CancelledError will be
    raised which also contains the result of the future. The caller code must catch this exception and handle the
    result if it is important. Otherwise it can be used the same way as the builtin wait_for.

    If the caller prefers to handle the race-condition with a callback, the `race_handler` argument may be provided.
    It will be called with the result of the future when the waiter task is being cancelled. Even if this is provided,
    the special error will be raised in the place of a normal CancelledError.

    Additionally, this implementation will inherit the behaviour of the inner future when it comes to ignoring
    cancellation. The builtin version prefers to always be cancellable, even if that means the wrapped future may
    not be terminated with it. (behaviour of builtin _cancel_and_wait) This behaviour is also improved in
    timeout-cancel edge cases, where the builtin would not wait for the termination of the inner future if the
    waiter was cancelled after timeout handling had already started. This is more consistent as the inner future
    must always be stopped for it to return.

    NOTE: CancelledWithResultError is limited to the coroutine wait_for is invoked from!
    If this wait_for is wrapped in tasks those will not propagate the special exception, but raise their own
    CancelledError instances.
    """
    if loop is None:
        loop = get_running_loop()
    elif sys.version_info >= (3, 10):  # pragma: no cover
        raise RuntimeError("loop parameter has been dropped since Python 3.10")

    if timeout is None:
        return await fut

    if timeout <= 0:
        fut = ensure_future(fut, loop=loop)

        if fut.done():
            return fut.result()

        return await _cancel_and_wait2(fut, loop, False, race_handler)

    waiter = loop.create_future()
    timeout_handle = loop.call_later(timeout, _release_waiter, waiter)
    cb = partial(_release_waiter, waiter)
    fut = ensure_future(fut, loop=loop)
    fut.add_done_callback(cb)

    try:
        try:
            await waiter
        except CancelledError:
            if fut.done():
                try:
                    fut_result = fut.exception()
                except CancelledError:
                    raise  # inner future was also cancelled
                if fut_result is None:
                    fut_result = fut.result()
                    res_exception = False
                else:
                    res_exception = True
                _handle_cancelling_with_inner_completion(loop, fut, fut_result, res_exception, race_handler)
            fut.remove_done_callback(cb)
            await _cancel_and_wait2(fut, loop, True, race_handler)

        if fut.done():
            return fut.result()
        else:
            fut.remove_done_callback(cb)
            return await _cancel_and_wait2(fut, loop, False, race_handler)
    finally:
        timeout_handle.cancel()
