"""Silent periodic MCP snapshots. Capturing is distinct from model inference."""

import asyncio
from copy import deepcopy
import time


OBSERVATION_URI = 'notesync://observation/current'


class NotebookObserver:
    def __init__(self, client, interval_seconds=30, notify=None):
        self.client, self.interval_seconds, self.notify = client, interval_seconds, notify
        self.snapshot = None
        self.sequence = 0
        self._lock = asyncio.Lock()
        self._updated = asyncio.Condition()

    def _capture(self):
        metadata = self.client.call('get_note_status')
        previous = self.snapshot or {}
        unchanged = (previous.get('status') == 'ok'
                     and metadata['revision'] == previous.get('revision')
                     and metadata['page_id'] == previous.get('page_id'))
        result = dict(previous if unchanged else self.client.call('read_current_note'))
        result.update(status='ok', changed=not unchanged)
        context = self.client.call('read_note_context')
        if context.get('revision') != result['revision']:
            # Handwriting/page may change between these two independent reads.
            context = dict(status='changed_during_capture', fresh=False)
        result['context'] = context
        return result

    async def check(self):
        async with self._lock:
            try:
                result = await asyncio.to_thread(self._capture)
            except Exception:
                # No stale picture, raw upstream errors, connection tokens or keys.
                result = dict(status='error', error='ノートを取得できません。NoteSyncの接続を確認してください。')
            self.sequence += 1
            result.update(sequence=self.sequence, checked_at=round(time.time() * 1000),
                          interval_seconds=self.interval_seconds, silent=True,
                          source='server_snapshot', model_inference=False)
            async with self._updated:
                self.snapshot = result
                self._updated.notify_all()
        if self.notify is not None:
            await self.notify()
        return result

    async def run(self):
        while True:
            started = asyncio.get_running_loop().time()
            await self.check()
            elapsed = asyncio.get_running_loop().time() - started
            await asyncio.sleep(max(.01, self.interval_seconds - elapsed))

    async def read(self, wait_for_next=False):
        if self.snapshot is None:
            await self.check()
        if wait_for_next:
            sequence = self.sequence
            async with self._updated:
                try:
                    await asyncio.wait_for(self._updated.wait_for(lambda: self.sequence > sequence),
                                           timeout=self.interval_seconds + 5)
                except asyncio.TimeoutError:
                    pass
        return deepcopy(self.snapshot)
