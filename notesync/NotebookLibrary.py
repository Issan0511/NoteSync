"""Transactional notebook library operations and explicit save status.

The window supplies its existing save/status/command methods as ``*_legacy``
hooks. Keeping this mixin separate lets notebook storage and MCP integrations
continue to share the same controller and notebook store.
"""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import re
import uuid


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def _signature(note):
    excluded = {'createdAt', 'updatedAt', 'activePageId'}
    if note.get('pages'):
        excluded.update(('strokes', 'texts', 'paper', 'aspect'))
    content = {key: value for key, value in note.items() if key not in excluded}
    return hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def _title(value, default='無題のノート'):
    if not isinstance(value, str):
        raise ValueError('ノートの名前を文字で入力してください。')
    return value.strip()[:120] or default


class NotebookLibraryMixin:
    """Add safe notebook changes without replacing the host's ink/MCP logic.

    Call ``_init_notebook_library`` after loading/importing the store, before the
    window loads its active note into the controller. It also fills missing
    metadata on notes subsequently added by an import service.
    """

    def _init_notebook_library(self):
        initialized = getattr(self, '_library_initialized', False)
        stamp = _now()
        if not initialized:
            try:
                stamp = datetime.fromtimestamp(self.store.path.stat().st_mtime, timezone.utc).isoformat(
                    timespec='milliseconds').replace('+00:00', 'Z')
            except OSError:
                pass
        for note in self.store.notes:
            if not note.get('createdAt'):
                note['createdAt'] = stamp
            if not note.get('updatedAt'):
                note['updatedAt'] = note['createdAt']
            note.setdefault('deletedAt', None)
        if initialized:
            return
        live = [note for note in self.store.notes if not note.get('deletedAt')]
        if not live:
            note = self.store.new_note()
            note.update(createdAt=stamp, updatedAt=stamp, deletedAt=None)
        elif not any(note['id'] == self.store.active_id for note in live):
            self.store.active_id = live[0]['id']
        self._library_initialized = True
        self._library_saved_signatures = {note['id']: _signature(note) for note in self.store.notes}
        self._library_observed_signatures = dict(self._library_saved_signatures)
        self._notebook_save_state = 'saved' if self.store.path.exists() else 'dirty'
        self._notebook_saved_at = stamp if self.store.path.exists() else None
        self._notebook_save_error = None
        self._library_save_checkpoints = []

    def _library_broadcast(self, message):
        server = getattr(self, 'web_server', None)
        if server is not None:
            server.broadcast(message)

    def _library_document_id(self):
        return getattr(self, '_document_id', self.store.active_id)

    def _library_set_save_state(self, state, message=None, *, save_checkpoints=None):
        self._notebook_save_state = state
        self._notebook_save_error = message if state == 'error' else None
        labels = {'dirty': '未保存の変更', 'saving': '保存中…', 'saved': '保存済み',
                  'error': '保存できません。変更はこの画面に保持しています'}
        label = getattr(self, 'save_label', None)
        if label is not None:
            label.setText(labels[state])
        payload = {'type': 'note_save_state', 'state': state, 'noteId': self._library_document_id(),
                   'notebookId': self.store.active_id,
                   'inkRevision': getattr(self.controller, 'ink_revision', 0),
                   'savedAt': self._notebook_saved_at,
                   'saveCheckpoints': list(save_checkpoints or [])}
        if message:
            payload['message'] = message
        self._library_broadcast(payload)

    def _library_capture_active(self):
        note = self.store.active
        note['strokes'] = self.controller.serialized_ink()
        if hasattr(self.controller, 'serialized_texts'):
            note['texts'] = self.controller.serialized_texts()
        if hasattr(self.store, 'sync_active_page'):
            self.store.sync_active_page()

    def _library_observe_changes(self):
        changed = False
        self._init_notebook_library()
        for note in self.store.notes:
            if hasattr(self.store, 'sync_active_page'):
                self.store.sync_active_page(note)
            signature = _signature(note)
            if self._library_observed_signatures.get(note['id']) != signature:
                note['updatedAt'] = _now()
                self._library_observed_signatures[note['id']] = signature
                changed = True
        return changed

    def _ink_changed(self, *args):
        self._init_notebook_library()
        self._library_capture_active()
        if not self._library_observe_changes():
            return
        legacy = getattr(self, '_ink_changed_legacy', None)
        if legacy:
            legacy(*args)
        self._library_set_save_state('dirty')

    def _library_saved(self):
        self._notebook_saved_at = _now()
        self._library_saved_signatures = {note['id']: _signature(note) for note in self.store.notes}
        self._library_observed_signatures = dict(self._library_saved_signatures)
        document_id = self._library_document_id()
        checkpoints = [request_id for note_id, request_id in self._library_save_checkpoints
                       if note_id == document_id]
        self._library_set_save_state('saved', save_checkpoints=checkpoints)
        self._library_broadcast({'type': 'note_saved', 'state': 'saved', 'noteId': document_id,
                                 'notebookId': self.store.active_id,
                                 'inkRevision': getattr(self.controller, 'ink_revision', 0),
                                 'savedAt': self._notebook_saved_at, 'saveCheckpoints': checkpoints})
        self._library_save_checkpoints = [(note_id, request_id)
                                          for note_id, request_id in self._library_save_checkpoints
                                          if note_id != document_id]

    def _library_save_failed(self):
        message = 'PCへの保存に失敗しました。変更を保持しているので、保存先を確認して再試行してください。'
        self._library_set_save_state('error', message)
        self._library_broadcast({'type': 'note_error', 'message': message,
                                 'noteId': self._library_document_id()})

    def save_notebook(self, *args):
        """Save a snapshot; explicit library actions finish pen gestures first.

        Autosave can run during a long eraser gesture. It must not split that
        gesture's undo transaction, so input finalization belongs to the action
        wrapper rather than this timer-compatible method.
        """
        self._init_notebook_library()
        self._library_capture_active()
        before = deepcopy(self.store.notes)
        previous_observed = dict(self._library_observed_signatures)
        self._library_observe_changes()
        self._library_set_save_state('saving')
        try:
            result = self._save_notebook_legacy()
        except (OSError, ValueError, TypeError):
            result = False
        if result is False:
            self.store.notes = before
            self._library_observed_signatures = previous_observed
            self._library_save_failed()
            return False
        self._library_saved()
        return True

    def library_metadata(self):
        """Return all notes, including recoverable trash, without reading ink files."""
        self._init_notebook_library()
        metadata = []
        for note in self.store.notes:
            active = note['id'] == self.store.active_id
            pages = self.store.ensure_pages(note) if hasattr(self.store, 'ensure_pages') else [note]
            selected = note.get('activePageId', note['id'])
            stroke_count = sum(len(self.controller.sketchbook_strokes) if active and page.get('id') == selected
                               else len(page.get('strokes', [])) for page in pages)
            text_count = sum(len(getattr(self.controller, 'sketchbook_texts', [])) if active and page.get('id') == selected
                             else len(page.get('texts', [])) for page in pages)
            metadata.append({'id': note['id'], 'title': note['title'], 'paper': note.get('paper', 'plain'),
                             'course': note.get('course', '未分類'),
                             'attachments': [{k: a.get(k) for k in ('id', 'name', 'bytes', 'sha256')}
                                             for a in note.get('attachments', [])],
                             'aspect': note.get('aspect', 4 / 3), 'strokeCount': stroke_count,
                             'textCount': text_count, 'pageCount': len(pages), 'createdAt': note['createdAt'],
                             'updatedAt': note['updatedAt'], 'deletedAt': note.get('deletedAt')})
        return metadata

    def _get_web_status(self):
        self._init_notebook_library()
        status = self._get_web_status_legacy()
        status.update(notes=self.library_metadata(), activeId=self.store.active_id,
                      saveState=self._notebook_save_state, savedAt=self._notebook_saved_at,
                      saveError=self._notebook_save_error)
        return status

    def _library_finish_input(self):
        self.controller.end_stroke()
        self._finish_erase()
        timer = getattr(self, 'save_timer', None)
        if timer is not None:
            timer.stop()

    def _library_load_active(self, previous_id):
        note = self.store.active
        self._document_id = self.store.active_page['id'] if hasattr(self.store, 'active_page') else note['id']
        self.canvas.aspect = note.get('aspect', 4 / 3)
        self.canvas.paper = note.get('paper', 'plain')
        if previous_id != note['id']:
            if hasattr(self.controller, 'serialized_texts'):
                self.controller.load_ink(note['strokes'], note.get('texts', []))
            else:
                self.controller.load_ink(note['strokes'])
        self.title_label.setText(note['title'])
        self.canvas.update()
        if hasattr(self, '_update_page_label'):
            self._update_page_label()

    def _library_find(self, identifier, *, allow_deleted=False):
        note = next((note for note in self.store.notes if note['id'] == identifier), None)
        if note is None or note.get('deletedAt') and not allow_deleted:
            raise ValueError('ノートが見つかりません。ノート一覧を更新してください。')
        return note

    def _library_mutate(self, action, data):
        identifier = data.get('id', self.store.active_id)
        if action == 'new':
            from .NotebookStorage import label
            self.store.new_note(_title(data.get('title', '新しいノート')))['course'] = label(data.get('course'))
        elif action == 'select':
            self.store.active_id = self._library_find(identifier)['id']
        elif action == 'duplicate':
            source = self._library_find(identifier)
            note = deepcopy(source)
            stamp = _now()
            note.update(id=uuid.uuid4().hex, title=_title(data.get('title', source['title'] + ' のコピー')),
                        createdAt=stamp, updatedAt=stamp, deletedAt=None)
            note.pop('importTag', None)
            if source.get('attachments'):
                import base64
                for item in note['attachments']:
                    _, raw = self.store.read_attachment(source, item['id'])
                    item['data'] = base64.b64encode(raw).decode()
                    item['id'] = uuid.uuid4().hex
                    item.pop('file', None)
            if hasattr(self.store, 'ensure_pages'):
                pages = self.store.ensure_pages(note)
                selected = note['activePageId']
                page_ids = {}
                for index, page in enumerate(pages):
                    old_id = page['id']
                    page['id'] = note['id'] if index == 0 else uuid.uuid4().hex
                    page_ids[old_id] = page['id']
                    if old_id == selected:
                        note['activePageId'] = page['id']
                    for item in page.get('texts', []):
                        item['id'] = uuid.uuid4().hex
                for entry in note.get('pageTrash', []):
                    page = entry['page']
                    page['id'] = page_ids.setdefault(page['id'], uuid.uuid4().hex)
                    for item in page.get('texts', []):
                        item['id'] = uuid.uuid4().hex
                selected_page = next(page for page in pages if page['id'] == note['activePageId'])
                note.update({key: selected_page[key] for key in ('strokes', 'texts', 'paper', 'aspect')})
            else:
                for item in note.get('texts', []):
                    item['id'] = uuid.uuid4().hex
            self.store.notes.insert(0, note)
            self.store.active_id = note['id']
        elif action == 'trash':
            note = self._library_find(identifier)
            note['deletedAt'] = _now()
            if identifier == self.store.active_id:
                live = next((candidate for candidate in self.store.notes if not candidate.get('deletedAt')), None)
                if live is None:
                    self.store.new_note()
                else:
                    self.store.active_id = live['id']
        elif action == 'restore':
            note = self._library_find(identifier, allow_deleted=True)
            if not note.get('deletedAt'):
                raise ValueError('このノートはゴミ箱に入っていません。')
            note['deletedAt'] = None
        elif action == 'rename':
            self._library_find(identifier)['title'] = _title(data.get('title'))
        elif action == 'course':
            from .NotebookStorage import label
            self._library_find(identifier)['course'] = label(data.get('course'))
        elif action == 'paper' and data.get('paper') in ('plain', 'ruled', 'grid'):
            self._library_find(identifier)['paper'] = data['paper']
        else:
            raise ValueError('このノート操作は利用できません。')

    def _library_result(self, action, data, ok, message=None):
        result = {'type': 'note_library_result', 'action': action, 'requestId': data.get('requestId'),
                  'ok': ok, 'activeId': self.store.active_id}
        if message:
            result['message'] = message
        self._library_broadcast(result)
        self._library_broadcast(dict(self._get_web_status(), type='state_sync'))
        return ok

    def _on_notebook_command(self, data):
        if (data.get('type') == 'note_paper' and 'documentId' in data
                and data['documentId'] != self._library_document_id()):
            return self._library_result('paper', data, False, 'ページが切り替わりました。もう一度用紙を選んでください。')
        if data.get('type') == 'note_save_checkpoint':
            self._init_notebook_library()
            request_id = data.get('requestId')
            if (not isinstance(request_id, str) or re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', request_id) is None
                    or data.get('documentId') != self._library_document_id()):
                return False
            checkpoint = (self._library_document_id(), request_id)
            if checkpoint not in self._library_save_checkpoints:
                self._library_save_checkpoints.append(checkpoint)
                self._library_save_checkpoints = self._library_save_checkpoints[-64:]
            self.save_timer.start()
            return True
        aliases = {'note_new': 'new', 'note_select': 'select', 'note_title': 'rename',
                   'note_paper': 'paper', 'note_save': 'save'}
        kind = data.get('type')
        if kind == 'note_library':
            action = data.get('action')
        elif kind in aliases:
            action = aliases[kind]
        else:
            return self._on_notebook_command_legacy(data)
        self._init_notebook_library()
        if action not in ('new', 'select', 'duplicate', 'trash', 'restore', 'rename', 'course', 'paper', 'save'):
            return self._library_result(action, data, False, 'このノート操作は利用できません。')
        self._library_finish_input()
        if not self.save_notebook():
            return self._library_result(action, data, False, self._notebook_save_error)
        if action == 'save':
            return self._library_result(action, data, True)
        previous_id = self.store.active_id
        previous_notes = deepcopy(self.store.notes)
        previous_observed = dict(self._library_observed_signatures)
        try:
            self._library_mutate(action, data)
            self._library_observe_changes()
            self._library_set_save_state('saving')
            # Persist the candidate library before loading its active note. The
            # controller still holds the old note until the atomic write works.
            if self.store.save() is False:
                raise OSError('notebook storage rejected the write')
        except (OSError, ValueError, TypeError) as exc:
            self.store.notes = previous_notes
            self.store.active_id = previous_id
            self._library_observed_signatures = previous_observed
            if isinstance(exc, OSError):
                self._library_save_failed()
                message = self._notebook_save_error
            else:
                self._library_set_save_state('saved')
                message = str(exc)
            return self._library_result(action, data, False, message)
        self._library_load_active(previous_id)
        self._library_saved()
        return self._library_result(action, data, True)
