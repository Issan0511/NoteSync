"""Private tablet downloads and additive notebook backup restoration."""

import base64
import binascii
import re
import uuid
from copy import deepcopy

from beamerplus.NotebookExports import (
    create_notebook_backup, parse_notebook_backup,
    image_to_png_bytes, images_to_pdf_bytes,
)


class NotebookFilesMixin:
    def _on_notebook_command(self, data):
        if data.get('type') != 'note_file':
            return super()._on_notebook_command(data)
        request_id = data.get('requestId')
        if not isinstance(request_id, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', request_id):
            return
        reply = dict(type='note_file_result', requestId=request_id, ok=False)
        client = data.get('_reply_client')
        try:
            self.controller.end_stroke()
            self._finish_erase()
            action = data.get('action')
            if action in ('attach', 'attachment_download', 'attachment_remove'):
                if data.get('documentId') != self._document_id:
                    raise ValueError('ノートが切り替わりました。もう一度操作してください。')
                from .NotebookStorage import label, sha, MAX_ATTACHMENT
                note = self.store.active
                if action == 'attachment_download':
                    name, raw = self.store.read_attachment(note, data.get('attachmentId'))
                    reply.update(ok=True, filename=name, mime='application/octet-stream',
                                 data=base64.b64encode(raw).decode(), saved=True)
                else:
                    if not self.save_notebook(): raise ValueError('ノートを保存できませんでした。')
                    before = deepcopy(note.get('attachments', []))
                    try:
                        if action == 'attach':
                            name = label(data.get('filename'), '添付資料')
                            encoded = data.get('data')
                            if not isinstance(encoded, str) or len(encoded) > 14 * 1024 * 1024: raise ValueError('添付資料は10MB以内です。')
                            raw = base64.b64decode(encoded, validate=True)
                            if not raw or len(raw) > MAX_ATTACHMENT: raise ValueError('添付資料は1個10MB以内です。')
                            item = dict(id=uuid.uuid4().hex, name=name, data=encoded, sha256=sha(raw), bytes=len(raw))
                            note.setdefault('attachments', []).append(item)
                        else:
                            identifier = data.get('attachmentId')
                            if not any(a['id'] == identifier for a in before): raise ValueError('添付資料がありません。')
                            note['attachments'] = [a for a in before if a['id'] != identifier]
                        if not self.save_notebook(): raise ValueError('添付資料を保存できませんでした。')
                    except (ValueError, OSError):
                        self.store.active['attachments'] = before
                        raise
                    reply.update(ok=True, saved=True)
                    self.web_server.broadcast(dict(self._get_web_status(), type='state_sync'))
            elif action == 'import':
                encoded = data.get('data')
                if not isinstance(encoded, str) or len(encoded) > 14 * 1024 * 1024:
                    raise ValueError('バックアップは10MB以内のファイルを選んでください。')
                try:
                    raw = base64.b64decode(encoded, validate=True)
                except (ValueError, binascii.Error) as exc:
                    raise ValueError('バックアップファイルを確認してください。') from exc
                imported = parse_notebook_backup(raw, existing_notes=self.store.notes)
                if not self.save_notebook():
                    raise ValueError('今のノートを保存できませんでした。保存先を確認してから取り込んでください。')
                previous = self.store.notes
                self.store.notes = imported['notes'] + previous
                if not self.save_notebook():
                    self.store.notes = previous
                    raise ValueError('取り込んだノートを保存できませんでした。元のノートは保持しています。')
                reply.update(ok=True, importedCount=len(imported['notes']))
                self.web_server.broadcast(dict(self._get_web_status(), type='state_sync'))
            elif action in ('png', 'pdf', 'backup', 'backup_all'):
                if data.get('documentId') != getattr(self, '_document_id', self.store.active_id):
                    raise ValueError('ノートが切り替わりました。もう一度書き出してください。')
                saved = self.save_notebook()
                title = self.store.active['title']
                filename = re.sub(r'[\x00-\x1f/\\:*?"<>|]', '_', title).strip('. ')[:80] or 'ノート'
                if action in ('backup', 'backup_all'):
                    selected = self.store.active_id if action == 'backup' else None
                    blob = create_notebook_backup(self.store.portable_notes(selected), active_id=self.store.active_id,
                                                 note_id=selected)
                    mime = 'application/json'
                    filename = (filename if action == 'backup' else 'SpenNotes-全ノート') + '.spennotes'
                else:
                    if action == 'png':
                        pages = self.store.ensure_pages(self.store.active)
                        target = next((p for p in pages if p['id'] == data.get('pageId', self.store.active_page['id'])), None)
                        if target is None:
                            raise ValueError('書き出すページが見つかりません。')
                        image = (self.render_current_page_image_with_sketch() if target['id'] == self.store.active_page['id']
                                 else self.render_notebook_page_image(target))
                        blob = image_to_png_bytes(image)
                        mime = 'image/png'
                        pages = self.store.ensure_pages(self.store.active)
                        index = next(i for i, page in enumerate(pages) if page['id'] == target['id'])
                        filename += f'-ページ{index + 1}'
                    else:
                        pages = self.store.ensure_pages(self.store.active)
                        blob = images_to_pdf_bytes((self.render_notebook_page_image(page) for page in pages), title=title)
                        mime = 'application/pdf'
                    filename += '.' + action
                reply.update(ok=True, saved=saved, filename=filename, mime=mime,
                             data=base64.b64encode(blob).decode('ascii'))
            else:
                raise ValueError('このファイル操作は利用できません。')
        except (ValueError, OSError, TypeError) as exc:
            reply['message'] = str(exc)
        self.web_server.reply_to(client, reply)
