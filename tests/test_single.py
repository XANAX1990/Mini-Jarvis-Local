import uuid

from jarvis import single


def test_second_acquire_of_same_name_is_refused_until_released():
    name = f"Local\\JarvisTest-{uuid.uuid4()}"
    first = single.acquire(name)
    assert first
    assert single.acquire(name) is None  # already held
    single.release(first)
    again = single.acquire(name)  # free again after release
    assert again
    single.release(again)


def test_different_names_do_not_conflict():
    a = single.acquire(f"Local\\JarvisTest-{uuid.uuid4()}")
    b = single.acquire(f"Local\\JarvisTest-{uuid.uuid4()}")
    assert a and b
    single.release(a)
    single.release(b)
