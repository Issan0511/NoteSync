"""Plain text annotations shared by the notebook, image export, and MCP."""

from dataclasses import asdict, dataclass, field, replace
from functools import lru_cache
import math
import re
import unicodedata
import uuid
from xml.etree import ElementTree as ET

from PySide6.QtCore import QByteArray, QPointF, QRectF
from PySide6.QtGui import QColor, QFont, QTransform
from PySide6.QtSvg import QSvgRenderer

from notesync.InkModel import TextItem
from notesync.NotebookMath import render_math_svg


@dataclass
class NoteText(TextItem):
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    format: str = 'auto'
    transform: list[float] | None = None

    def bounds(self, aspect):
        return text_bounds(self, aspect)


def _number(value, lower, upper):
    if type(value) not in (int, float) or not math.isfinite(value) or not lower <= value <= upper:
        raise ValueError('文字の位置・大きさを確認してください。座標は0〜1で指定します。')
    return float(value)


def character_width(char):
    if unicodedata.combining(char):
        return 0
    return 1 if unicodedata.east_asian_width(char) in ('W', 'F') else .65


def text_base_bounds(item, aspect):
    layout = annotation_layout(item.text, item.size, item.color, item.norm_x, aspect, item.format)
    if layout:
        ratio = item.size * .0015
        return {'x': item.norm_x, 'y': item.norm_y,
                'width': layout.width * ratio * min(1, 1 / aspect),
                'height': layout.height * ratio * min(1, aspect)}
    lines = item.text.split('\n')
    ratio = item.size * .0015
    return {'x': item.norm_x, 'y': item.norm_y,
            'width': max(sum(character_width(c) for c in line) for line in lines) * ratio * min(1, 1 / aspect),
            'height': len(lines) * ratio * 1.45 * min(1, aspect)}


def text_bounds(item, aspect):
    bounds = text_base_bounds(item, aspect)
    matrix = getattr(item, 'transform', None)
    if not matrix:
        return bounds
    a, b, c, d, e, f = matrix
    corners = [(a*x+c*y+e, b*x+d*y+f)
               for x in (bounds['x'], bounds['x']+bounds['width'])
               for y in (bounds['y'], bounds['y']+bounds['height'])]
    left, top = min(p[0] for p in corners), min(p[1] for p in corners)
    return dict(x=left, y=top, width=max(p[0] for p in corners)-left,
                height=max(p[1] for p in corners)-top)


def validate_text_transform(value):
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 6:
        raise ValueError('文字の移動・拡大データを確認してください。')
    matrix = [_number(v, -64, 64) for v in value]
    if abs(matrix[0]*matrix[3]-matrix[1]*matrix[2]) < 1e-8:
        raise ValueError('文字が小さすぎます。もう少し大きくしてください。')
    return None if matrix == [1, 0, 0, 1, 0, 0] else matrix


def transform_note_text(item, matrix, aspect):
    a, b, c, d, e, f = matrix
    p, q, r, s, t, u = item.transform or [1, 0, 0, 1, 0, 0]
    composed = [a*p+c*q, b*p+d*q, a*r+c*s, b*r+d*s, a*t+c*u+e, b*t+d*u+f]
    result = replace(item, transform=validate_text_transform(composed))
    bounds = text_bounds(result, aspect)
    for coordinate in (bounds['x'], bounds['y'], bounds['x']+bounds['width'], bounds['y']+bounds['height']):
        _number(coordinate, -4, 5)
    return result


@dataclass(frozen=True)
class AnnotationLayout:
    svg: str
    width: float
    height: float


_MATH_PART = re.compile(r'\$\$(.+?)\$\$|\\\[(.+?)\\\]|\\\((.+?)\\\)|(?<!\\)\$(?!\$)([^$\n]+?)(?<!\\)\$', re.S)
_SVG_NS = 'http://www.w3.org/2000/svg'


def _annotation_parts(text, text_format):
    if text_format == 'text':
        return [(False, text, False)]
    if text_format == 'latex':
        stripped = text.strip()
        match = _MATH_PART.fullmatch(stripped)
        return [(True, next(group for group in match.groups() if group is not None) if match else stripped, True)]
    result, start = [], 0
    for match in _MATH_PART.finditer(text):
        if match.start() > start:
            result.append((False, text[start:match.start()], False))
        result.append((True, next(group for group in match.groups() if group is not None),
                       match.group(1) is not None or match.group(2) is not None))
        start = match.end()
    if start < len(text):
        result.append((False, text[start:], False))
    return result


@lru_cache(maxsize=64)
def annotation_layout(text, size, color, x, aspect, text_format='auto'):
    """Lay out mixed Japanese text/TeX once, in units of the annotation font size."""
    parts = _annotation_parts(text, text_format)
    if not any(is_math for is_math, _, _ in parts):
        return None
    if len(parts) > 65:
        raise ValueError('一度に書き込む数式が多すぎます。注釈を分けてください。')
    font = 32.0
    available = (.98 - x) / (size * .0015 * min(1, 1 / aspect)) * font
    if available < font * .5:
        raise ValueError('右端に近すぎます。書き込む位置を左へ移してください。')
    rows, row, cursor = [], [], 0.0

    def newline(force=False):
        nonlocal row, cursor
        if row or force:
            rows.append(row)
        row, cursor = [], 0.0

    for is_math, value, display in parts:
        if is_math:
            rendered = render_math_svg(value, size=font, color=color, inline=not display)
            scale = min(1, available / rendered.width)
            if scale < .35:
                raise ValueError('数式が長すぎます。改行するか、数式を分けてください。')
            width = rendered.width * scale
            if display or cursor + width > available:
                newline()
            row.append(('math', cursor, rendered, scale))
            cursor += width
            if display:
                newline()
        else:
            for char in value:
                if char == '\n':
                    newline(force=True)
                    continue
                width = character_width(char) * font
                if cursor + width > available and row:
                    newline()
                if width > available:
                    raise ValueError('右端に近すぎます。書き込む位置を左へ移してください。')
                if row and row[-1][0] == 'text':
                    kind, left, content, run_width = row[-1]
                    row[-1] = (kind, left, content + char, run_width + width)
                else:
                    row.append(('text', cursor, char, width))
                cursor += width
    newline()
    root = ET.Element('svg', {'xmlns': _SVG_NS})
    top, right = 0.0, 0.0
    for row in rows:
        ascent = max([font] + [value.baseline * scale for kind, _, value, scale in row if kind == 'math'])
        descent = max([font * .45] + [(value.height - value.baseline) * scale for kind, _, value, scale in row if kind == 'math'])
        baseline = top + ascent
        for kind, left, value, scale in row:
            if kind == 'text':
                node = ET.SubElement(root, 'text', {'x': str(left), 'y': str(baseline), 'font-size': str(font),
                                                  'font-family': 'sans-serif', 'fill': color})
                node.text = value
                right = max(right, left + scale)
            else:
                node = ET.fromstring(value.svg)
                view_left = float(node.attrib['viewBox'].split()[0])
                # Qt's SVG Tiny renderer skips nested <svg>. Flatten the math
                # paths into a group, keeping their true y=0 math baseline.
                group = ET.SubElement(root, 'g', {'transform':
                    f'translate({left - view_left * scale},{baseline}) scale({scale})'})
                group.extend(list(node))
                right = max(right, left + value.width * scale)
        top += ascent + descent
    width, height = max(1, right), max(1, top)
    root.attrib.update(width=str(width), height=str(height), viewBox=f'0 0 {width} {height}')
    svg = ET.tostring(root, encoding='unicode')
    if len(svg.encode('utf-8')) > 512 * 1024:
        raise ValueError('注釈の数式が複雑すぎます。短い注釈に分けてください。')
    return AnnotationLayout(svg, width / font, height / font)


def annotation_payload(item, aspect):
    result = asdict(item)
    result.update(bounds=text_bounds(item, aspect), baseBounds=text_base_bounds(item, aspect))
    layout = annotation_layout(item.text, item.size, item.color, item.norm_x, aspect, item.format)
    if layout:
        result.update(renderedSvg=layout.svg, renderedWidth=layout.width, renderedHeight=layout.height)
    return result


def prepare_text(data, aspect=4 / 3):
    text = data.get('text')
    if not isinstance(text, str) or not text.strip() or len(text) > 2000:
        raise ValueError('書き込む文字を1〜2000文字で指定してください。')
    text = text.replace('\r\n', '\n').replace('\r', '\n').replace('\t', '    ').strip()
    if any(unicodedata.category(c) == 'Cc' and c != '\n' for c in text):
        raise ValueError('文字に使用できない制御文字が含まれています。')
    x = _number(data.get('norm_x'), 0, .98)
    y = _number(data.get('norm_y'), 0, .98)
    size = data.get('size', 18)
    if type(size) is not int or not 6 <= size <= 48:
        raise ValueError('文字の大きさは6〜48で指定してください。標準は18です。')
    color = data.get('color', '#3478dc')
    if not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
        raise ValueError('文字色は #3478dc のような形式で指定してください。')
    identifier = data.get('id', uuid.uuid4().hex)
    if not isinstance(identifier, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', identifier):
        raise ValueError('文字の識別子が正しくありません。')
    text_format = data.get('format', 'auto')
    if text_format not in ('auto', 'text', 'latex'):
        raise ValueError('文字の形式はauto・text・latexで指定してください。')
    item = NoteText(text=text, norm_x=x, norm_y=y, size=size, color=color, id=identifier, format=text_format)
    layout = annotation_layout(text, size, color, x, aspect, text_format)
    if layout:
        if y + text_bounds(item, aspect)['height'] > .98:
            raise ValueError('数式がノートの下端を越えます。位置・大きさを変えてください。')
        return transform_note_text(item, validate_text_transform(data.get('transform')) or [1, 0, 0, 1, 0, 0], aspect)
    # Store explicit line breaks so tablet and desktop use the same layout.
    columns = (.98 - x) / (size * .0015 * min(1, 1 / aspect))
    lines = []
    for paragraph in text.split('\n'):
        line, width = '', 0
        for char in paragraph:
            advance = character_width(char)
            if advance > columns:
                raise ValueError('右端に近すぎます。書き込む位置を左へ移してください。')
            if line and width + advance > columns:
                lines.append(line)
                line, width = '', 0
            line += char
            width += advance
        lines.append(line)
    item.text = '\n'.join(lines)
    if y + text_bounds(item, aspect)['height'] > .98:
        raise ValueError('文字がノートの下端を越えます。短くするか、位置・大きさを変えてください。')
    return transform_note_text(item, validate_text_transform(data.get('transform')) or [1, 0, 0, 1, 0, 0], aspect)


def paint_note_texts(painter, texts, rect):
    painter.save()
    painter.setClipRect(rect)
    for item in texts:
        painter.save()
        painter.translate(rect.left(), rect.top())
        if item.transform:
            a, b, c, d, e, f = item.transform
            w, h = rect.width(), rect.height()
            painter.setTransform(QTransform(a, b*h/w, c*w/h, d, e*w, f*h), True)
        pixels = max(1, round(min(rect.width(), rect.height()) * item.size * .0015))
        font = QFont('sans-serif')
        font.setPixelSize(pixels)
        painter.setFont(font)
        painter.setPen(QColor(item.color))
        x = item.norm_x * rect.width()
        top = item.norm_y * rect.height()
        layout = annotation_layout(item.text, item.size, item.color, item.norm_x, rect.width() / rect.height(), item.format)
        if layout:
            renderer = QSvgRenderer(QByteArray(layout.svg.encode()))
            renderer.render(painter, QRectF(x, top, layout.width * pixels, layout.height * pixels))
            painter.restore()
            continue
        for index, line in enumerate(item.text.split('\n')):
            painter.drawText(QPointF(x, top + pixels + index * pixels * 1.45), line)
        painter.restore()
    painter.restore()


# Backwards-compatible import for the notebook HTML builder.
from notesync.TabletText import NOTE_TEXT_SCRIPT
