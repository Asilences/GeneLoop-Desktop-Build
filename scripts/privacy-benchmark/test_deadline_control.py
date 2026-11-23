from concurrent.futures import TimeoutError
import time
import unittest


class DeadlineControlTests(unittest.TestCase):
    def test_expired_job_is_unknown_and_pool_continues(self):
        from pebble import ProcessPool
        with ProcessPool(max_workers=1) as pool:
            slow = pool.schedule(time.sleep, args=(5,), timeout=.2)
            with self.assertRaises(TimeoutError):
                slow.result(timeout=10)
            self.assertEqual(pool.schedule(sum, args=([2, 3],)).result(timeout=10), 5)


if __name__ == '__main__':
    unittest.main()
