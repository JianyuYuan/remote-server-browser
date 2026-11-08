import unittest
from remote_browser import format_size, parent_path

class BrowserTests(unittest.TestCase):
    def test_sizes(self):
        self.assertEqual(format_size(1024), '1.0 KB')
        self.assertEqual(format_size(12), '12 B')

    def test_parent(self):
        self.assertEqual(parent_path('/home/user/'), '/home')
        self.assertEqual(parent_path('/'), '/')

if __name__ == '__main__':
    unittest.main()
