"""Saved, independent paper pages inside one persistent notebook."""

from copy import deepcopy
import hashlib
import json
import re
import uuid

from notesync.NotebookText import annotation_payload, prepare_text


def page_revision(page):
    content = {key: page.get(key) for key in ('strokes', 'texts', 'paper', 'aspect')}
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()[:16]


class NotebookPagesMixin:
    def _on_page_ink_command(self, data):
        """Drop delayed pen/undo commands belonging to another sheet of paper."""
        if data.get('documentId') != self.store.active_page['id']:
            return False
        payload = dict(data)
        payload.pop('documentId', None)
        self.web_server._handle_client_message(payload)
        return True

    def _get_web_status(self):
        status = super()._get_web_status()
        note = self.store.active
        pages = self.store.ensure_pages(note)
        active_id = note['activePageId']
        metadata = []
        for index, page in enumerate(pages):
            active = page['id'] == active_id
            strokes = self.controller.sketchbook_strokes if active else page['strokes']
            texts = getattr(self.controller, 'sketchbook_texts', page.get('texts', [])) if active else page.get('texts', [])
            metadata.append({'id': page['id'], 'index': index, 'strokeCount': len(strokes),
                             'textCount': len(texts), 'paper': page['paper'], 'aspect': page['aspect'],
                             'revision': page_revision(page)})
        current = next(index for index, page in enumerate(pages) if page['id'] == active_id)
        status.update(notebookId=note['id'], pageId=active_id, documentId=active_id,
                      pages=metadata, currentPage=current, totalPages=len(pages),
                      canRestorePage=bool(note.get('pageTrash')),
                      canPastePage=bool(getattr(self, '_page_clipboard', None)))
        return status

    def _page_preview(self, data):
        """Read a paper's vectors without changing the current editor or Undo."""
        reply = dict(type='note_page_preview_result', requestId=data.get('requestId'),
                     notebookId=self.store.active_id, pageId=data.get('pageId'), ok=False)
        try:
            if data.get('notebookId') != self.store.active_id:
                raise ValueError('ノートが切り替わりました。')
            page = next((p for p in self.store.ensure_pages(self.store.active)
                         if p['id'] == data.get('pageId')), None)
            if page is None:
                raise ValueError('ページが見つかりません。')
            content = dict(page)
            if page['id'] == self.store.active_page['id']:
                content.update(strokes=self.controller.serialized_ink(),
                               texts=self.controller.serialized_texts())
            texts = [annotation_payload(prepare_text(item, page['aspect']), page['aspect'])
                     for item in content.get('texts', [])]
            reply.update(ok=True, strokes=content['strokes'], texts=texts,
                         paper=page['paper'], aspect=page['aspect'], revision=page_revision(content))
        except (ValueError, TypeError) as exc:
            reply['message'] = str(exc)
        self.web_server.reply_to(data.get('_reply_client'), reply)
        return reply['ok']

    def _mutate_page(self, action, data):
        note = self.store.active
        pages = self.store.ensure_pages(note)
        self.store.sync_active_page()
        target_id = data.get('pageId', note['activePageId'])
        index = next((i for i, p in enumerate(pages) if p['id'] == target_id), None)
        if action == 'restore':
            trash = note.get('pageTrash', [])
            if not trash:
                raise ValueError('戻せるページ操作はありません。')
            entry = trash.pop()
            restored = entry['page']
            if entry['kind'] == 'clear':
                at = next((i for i, p in enumerate(pages) if p['id'] == restored['id']), None)
                if at is not None:
                    # Preserve any writing made since the clear as the next Undo.
                    trash.append(dict(kind='clear', index=at, page=deepcopy(pages[at])))
                    pages[at] = restored
                else:
                    pages.insert(min(entry['index'], len(pages)), restored)
            else:
                if len(pages) >= self.store.MAX_PAGES:
                    raise ValueError('ページ数の上限です。ノートを分けてください。')
                pages.insert(min(entry['index'], len(pages)), restored)
            note['activePageId'] = restored['id']
        else:
            if index is None:
                raise ValueError('ページが見つかりません。')
            target = pages[index]
            if action in ('copy', 'cut'):
                self._page_clipboard = deepcopy(target)
            if action == 'copy':
                return
            if action in ('add', 'paste'):
                if len(pages) >= self.store.MAX_PAGES:
                    raise ValueError('これ以上ページを追加できません。新しいノートを作ってください。')
                if action == 'paste':
                    if not getattr(self, '_page_clipboard', None):
                        raise ValueError('先にページをコピーしてください。')
                    page = deepcopy(self._page_clipboard)
                    page['id'] = uuid.uuid4().hex
                    for item in page.get('texts', []):
                        item['id'] = uuid.uuid4().hex
                else:
                    page = dict(id=uuid.uuid4().hex, strokes=[], texts=[],
                                paper=target['paper'], aspect=.75)
                pages.insert(index + 1, page)
                note['activePageId'] = page['id']
            elif action in ('delete', 'cut', 'clear'):
                if len(note.get('pageTrash', [])) >= self.store.MAX_PAGES:
                    raise ValueError('復元用のページが多いため、新しいノートを作ってください。')
                note.setdefault('pageTrash', []).append(dict(kind='clear' if action == 'clear' else 'delete',
                                                            index=index, page=deepcopy(target)))
                if action == 'clear':
                    target.update(strokes=[], texts=[])
                else:
                    pages.pop(index)
                    if not pages:
                        pages.append(dict(id=uuid.uuid4().hex, strokes=[], texts=[],
                                          paper=target['paper'], aspect=target['aspect']))
                    if note['activePageId'] == target_id:
                        note['activePageId'] = pages[min(index, len(pages) - 1)]['id']
            else:
                raise ValueError('このページ操作は利用できません。')
        self.store._mirror_page(note, self.store.active_page)

    def _page_result(self, data, ok, message=None):
        result = {'type': 'note_page_result', 'action': data.get('action'), 'requestId': data.get('requestId'),
                  'ok': ok, 'notebookId': self.store.active_id, 'pageId': self.store.active_page['id']}
        if message:
            result['message'] = message
        self.web_server.broadcast(result)
        self.web_server.broadcast(dict(self._get_web_status(), type='state_sync'))
        return ok

    def _on_notebook_command(self, data):
        if data.get('type') == 'note_page_preview':
            return self._page_preview(data)
        if data.get('type') != 'note_page':
            return super()._on_notebook_command(data)
        request_id = data.get('requestId')
        if request_id is not None and (not isinstance(request_id, str)
                                       or re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', request_id) is None):
            return self._page_result(data, False, 'ページ操作の識別子を確認してください。')
        if data.get('action') not in ('add', 'select', 'copy', 'cut', 'paste', 'delete', 'clear', 'restore'):
            return self._page_result(data, False, 'このページ操作は利用できません。')
        if data.get('documentId', self.store.active_page['id']) != self.store.active_page['id']:
            return self._page_result(data, False, 'ページが切り替わりました。もう一度操作してください。')
        if data['action'] == 'select' and not any(page['id'] == data.get('pageId')
                                                  for page in self.store.ensure_pages(self.store.active)):
            return self._page_result(data, False, 'ページが見つかりません。ノートを読み直してください。')
        self._library_finish_input()
        if not self.save_notebook():
            return self._page_result(data, False, getattr(self, '_notebook_save_error', None)
                                     or '今のページを保存できませんでした。保存先を確認してください。')
        previous_page_id = self.store.active_page['id']
        if data['action'] == 'select' and data['pageId'] == previous_page_id:
            return self._page_result(data, True)
        previous_notes = deepcopy(self.store.notes)
        previous_note_id = self.store.active_id
        previous_observed = dict(getattr(self, '_library_observed_signatures', {}))
        previous_clipboard = deepcopy(getattr(self, '_page_clipboard', None))
        try:
            if data['action'] == 'select':
                self.store.select_page(data['pageId'])
            else:
                self._mutate_page(data['action'], data)
            self._library_observe_changes()
            self._library_set_save_state('saving')
            if self.store.save() is False:
                raise OSError('notebook storage rejected the write')
        except (ValueError, TypeError, OSError) as exc:
            self.store.notes = previous_notes
            self.store.active_id = previous_note_id
            self._library_observed_signatures = previous_observed
            self._page_clipboard = previous_clipboard
            if isinstance(exc, OSError):
                self._library_save_failed()
                message = self._notebook_save_error
            else:
                self._library_set_save_state('saved')
                message = str(exc)
            return self._page_result(data, False, message)
        page = self.store.active_page
        # Copy and edits of another page must leave the active editor's Undo intact.
        same_content = (page['id'] == previous_page_id
                        and page['strokes'] == self.controller.serialized_ink()
                        and page.get('texts', []) == self.controller.serialized_texts())
        self._document_id = page['id']
        self.canvas.aspect, self.canvas.paper = page['aspect'], page['paper']
        if same_content:
            pass
        elif hasattr(self.controller, 'serialized_texts'):
            self.controller.load_ink(page['strokes'], page.get('texts', []))
        else:
            self.controller.load_ink(page['strokes'])
        self.canvas.update()
        getattr(self, '_update_page_label', lambda: None)()
        self._library_saved()
        return self._page_result(data, True)
