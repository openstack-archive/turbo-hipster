import testtools


class TestNothing(testtools.TestCase):
    def test_at_least_once(self):
        self.assertTrue(True)
