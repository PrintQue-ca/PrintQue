import asyncio
import logging
import aiohttp
import functools
import random

async def retry_async(func, max_retries=3, initial_backoff=1, max_backoff=30):
    """
    Execute an async function with retry logic and exponential backoff

    Args:
        func: The async function to call
        max_retries: Maximum number of retries
        initial_backoff: Initial backoff time in seconds
        max_backoff: Maximum backoff time in seconds

    Returns:
        The result of the async function
    """
    backoff = initial_backoff

    for attempt in range(max_retries + 1):  # +1 because we count the first attempt
        try:
            if attempt > 0:
                logging.debug(f"Retry attempt {attempt}/{max_retries} with backoff {backoff:.2f}s")
            return await func()
        except (aiohttp.ClientError, asyncio.TimeoutError, ConnectionError) as e:
            if attempt == max_retries:
                logging.error(f"Failed after {max_retries} retries: {str(e)}")
                raise

            # Add jitter to prevent thundering herd problem
            jitter = random.uniform(0.8, 1.2)
            sleep_time = min(backoff * jitter, max_backoff)

            logging.warning(f"Attempt {attempt+1}/{max_retries} failed: {str(e)}. Retrying in {sleep_time:.2f}s...")
            await asyncio.sleep(sleep_time)
            backoff *= 2
        except Exception as e:
            # Handle other exceptions that shouldn't be retried
            logging.error(f"Non-retryable error occurred: {str(e)}")
            raise

def with_event_loop_retry(max_attempts=3):
    """Decorator to retry operations if event loop issues occur"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except RuntimeError as e:
                    if "Event loop is closed" in str(e) and attempt < max_attempts - 1:
                        logging.warning(f"Event loop closed, recreating (attempt {attempt+1}/{max_attempts})")
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    else:
                        raise
        return wrapper
    return decorator
