import functools
import random
import time

from django.db import OperationalError, connections, transaction

from .db_errors import is_retryable

DEFAULT_RETRIES = 3


def transactional(func=None, *, retries=DEFAULT_RETRIES, using=None):
    """Executa a função em uma transação, repetindo-a em deadlock (40P01) ou falha de serialização (40001).

    `retries` é o número de repetições após a primeira execução (retries=3 → até 4
    execuções). Dentro de uma transação externa não há repetição possível (a externa
    já está abortada): a função roda em um savepoint e o erro sobe ao chamador.
    """

    def decorator(target):
        @functools.wraps(target)
        def wrapper(*args, **kwargs):
            connection = connections[using] if using else connections["default"]

            if connection.in_atomic_block:
                with transaction.atomic(using=using):
                    return target(*args, **kwargs)

            attempt = 1
            while True:
                try:
                    with transaction.atomic(using=using):
                        return target(*args, **kwargs)
                except OperationalError as exc:
                    if not is_retryable(exc) or attempt > retries:
                        raise
                    time.sleep(random.uniform(0.01, 0.05) * attempt)
                    attempt += 1

        return wrapper

    return decorator(func) if func is not None else decorator
