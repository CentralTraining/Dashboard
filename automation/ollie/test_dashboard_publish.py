import base64
import hashlib
import unittest
from dashboard_publish import SCRIPT, add_deadline_script, read_dashboard


class DashboardPublishTests(unittest.TestCase):
    def setUp(self):
        self.html = '<!doctype html><html><body><div id="loginScreen">' + ('x' * 12000) + '</div></body></html>'
        self.raw = self.html.encode()
        self.sha = hashlib.sha1(b'blob ' + str(len(self.raw)).encode() + b'\0' + self.raw).hexdigest()
        self.blob = {'encoding': 'base64', 'content': base64.b64encode(self.raw).decode()}
        self.metadata = {**self.blob, 'size': len(self.raw), 'sha': self.sha}

    def test_large_contents_response_loads_git_blob(self):
        metadata = {**self.metadata, 'encoding': 'none', 'content': ''}
        calls = []
        def load(sha):
            calls.append(sha)
            return self.blob
        self.assertEqual(read_dashboard(metadata, load), self.html)
        self.assertEqual(calls, [self.sha])

    def test_inline_contents_preserves_original(self):
        def unused(_):
            self.fail('Small files do not need an extra blob request')
        self.assertEqual(read_dashboard(self.metadata, unused), self.html)

    def test_empty_blob_cannot_be_published(self):
        metadata = {**self.metadata, 'encoding': 'none', 'content': ''}
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            read_dashboard(metadata, lambda _: {'encoding': 'base64', 'content': ''})

    def test_truncation_or_changed_content_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'size_mismatch'):
            read_dashboard({**self.metadata, 'size': len(self.raw) + 1}, None)
        altered = self.raw.replace(b'x', b'y')
        with self.assertRaisesRegex(ValueError, 'blob_mismatch'):
            read_dashboard({**self.metadata, 'content': base64.b64encode(altered).decode()}, None)

    def test_script_added_once_without_changing_original(self):
        updated = add_deadline_script(self.html)
        self.assertEqual(updated.replace(SCRIPT + '\n', ''), self.html)
        self.assertEqual(add_deadline_script(updated), updated)
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            add_deadline_script(SCRIPT)


if __name__ == '__main__':
    unittest.main()
