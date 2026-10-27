"""Silent server checks must not become annotations or claims of model awareness."""

import asyncio
import base64
from copy import deepcopy
from contextlib import suppress
import unittest

from notesync.NotebookObservation import NotebookObserver


class FakeClient:
    def __init__(self):
        self.calls = []
        self.metadata = dict(note_id='note', page_id='page', revision='1')
        self.context_revision = None
        self.failure = False

    def call(self, operation):
        self.calls.append(operation)
        if self.failure:
            raise ValueError('private-upstream-error')
        if operation == 'get_note_status':
            return deepcopy(self.metadata)
        if operation == 'read_current_note':
            return dict(self.metadata, image=base64.b64encode(b'png').decode())
        if operation == 'read_note_context':
            return dict(self.metadata, revision=self.context_revision or self.metadata['revision'], fresh=True)
        raise AssertionError('An observation may not write or navigate: ' + operation)


class ObservationTests(unittest.IsolatedAsyncioTestCase):
    async def test_unchanged_ink_reuses_picture_but_refreshes_transcription(self):
        client = FakeClient()
        observer = NotebookObserver(client)
        first = await observer.check()
        self.assertTrue(first['silent'])
        self.assertFalse(first['model_inference'])
        self.assertEqual(first['interval_seconds'], 30)
        second = await observer.check()
        self.assertFalse(second['changed'])
        self.assertEqual(second['sequence'], first['sequence'] + 1)
        self.assertEqual(client.calls.count('read_current_note'), 1)
        self.assertEqual(client.calls.count('read_note_context'), 2)
        client.metadata.update(page_id='second-page', revision='2')
        third = await observer.check()
        self.assertTrue(third['changed'])
        self.assertEqual(third['page_id'], 'second-page')
        self.assertEqual(client.calls.count('read_current_note'), 2)

    async def test_inconsistent_context_and_connection_failure_are_not_fresh_snapshots(self):
        client = FakeClient()
        observer = NotebookObserver(client)
        client.context_revision = 'changed-in-between'
        result = await observer.check()
        self.assertFalse(result['context']['fresh'])
        self.assertEqual(result['context']['status'], 'changed_during_capture')
        client.failure = True
        failed = await observer.check()
        self.assertEqual(failed['status'], 'error')
        self.assertNotIn('image', failed)
        self.assertNotIn('private-upstream-error', repr(failed))

    async def test_timer_next_check_notifications_and_disconnect_cancellation(self):
        client, notifications = FakeClient(), []

        async def notify():
            notifications.append(True)

        observer = NotebookObserver(client, interval_seconds=.03, notify=notify)
        await observer.check()
        first_sequence = observer.sequence
        task = asyncio.create_task(observer.run())
        try:
            result = await asyncio.wait_for(observer.read(wait_for_next=True), timeout=1)
            self.assertGreater(result['sequence'], first_sequence)
            self.assertGreaterEqual(len(notifications), 2)
            result['page_id'] = 'caller-mutated-copy'
            self.assertEqual(observer.snapshot['page_id'], 'page')
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        count = len(client.calls)
        await asyncio.sleep(.05)
        self.assertEqual(len(client.calls), count)
