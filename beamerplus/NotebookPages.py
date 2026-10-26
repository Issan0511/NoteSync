"""Saved, independent paper pages inside one persistent notebook."""

from copy import deepcopy
import re


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
                             'textCount': len(texts), 'paper': page['paper'], 'aspect': page['aspect']})
        current = next(index for index, page in enumerate(pages) if page['id'] == active_id)
        status.update(notebookId=note['id'], pageId=active_id, documentId=active_id,
                      pages=metadata, currentPage=current, totalPages=len(pages))
        return status

    def _page_result(self, data, ok, message=None):
        result = {'type': 'note_page_result', 'action': data.get('action'), 'requestId': data.get('requestId'),
                  'ok': ok, 'notebookId': self.store.active_id, 'pageId': self.store.active_page['id']}
        if message:
            result['message'] = message
        self.web_server.broadcast(result)
        self.web_server.broadcast(dict(self._get_web_status(), type='state_sync'))
        return ok

    def _on_notebook_command(self, data):
        if data.get('type') != 'note_page':
            return super()._on_notebook_command(data)
        request_id = data.get('requestId')
        if request_id is not None and (not isinstance(request_id, str)
                                       or re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', request_id) is None):
            return self._page_result(data, False, 'ページ操作の識別子を確認してください。')
        if data.get('action') not in ('add', 'select'):
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
        try:
            if data['action'] == 'add':
                self.store.new_page()
            else:
                self.store.select_page(data['pageId'])
            self._library_observe_changes()
            self._library_set_save_state('saving')
            if self.store.save() is False:
                raise OSError('notebook storage rejected the write')
        except (ValueError, TypeError, OSError) as exc:
            self.store.notes = previous_notes
            self.store.active_id = previous_note_id
            self._library_observed_signatures = previous_observed
            if isinstance(exc, OSError):
                self._library_save_failed()
                message = self._notebook_save_error
            else:
                self._library_set_save_state('saved')
                message = str(exc)
            return self._page_result(data, False, message)
        page = self.store.active_page
        self._document_id = page['id']
        self.canvas.aspect, self.canvas.paper = page['aspect'], page['paper']
        if hasattr(self.controller, 'serialized_texts'):
            self.controller.load_ink(page['strokes'], page.get('texts', []))
        else:
            self.controller.load_ink(page['strokes'])
        self.canvas.update()
        getattr(self, '_update_page_label', lambda: None)()
        self._library_saved()
        return self._page_result(data, True)
