"""Bounded, offline TeX math rendering shared by Qt and the tablet browser.

Only a mathematical expression is accepted: no documents, macro definitions,
file commands, external resources, or user-supplied SVG. Ziamath's bundled font
becomes SVG paths, so all clients display exactly the same equation.
"""

from dataclasses import dataclass
from functools import lru_cache
import math
import re
import threading
import unicodedata
from xml.etree import ElementTree as ET


MAX_LATEX_LENGTH = 2000
MAX_BRACE_DEPTH = 32
MAX_MATHML_NODES = 2048
MAX_SVG_BYTES = 512 * 1024
_LOCK = threading.RLock()
_COMMAND = re.compile(r'\\(?:[a-zA-Z]+|.)', re.DOTALL)
_ENVIRONMENT = re.compile(r'\\(begin|end)\s*\{([a-zA-Z]+\*?)\}')
_COLOR = re.compile(r'#[0-9a-fA-F]{6}')
_DIMENSION = re.compile(r'\d+(?:\.\d+)?\s*(?:pt|em|ex|mm|cm|in|pc|bp|dd|cc|sp|mu)\b')
_ENVIRONMENTS = frozenset(('matrix', 'pmatrix', 'bmatrix', 'Bmatrix', 'vmatrix',
    'Vmatrix', 'smallmatrix', 'array', 'cases', 'aligned', 'alignedat', 'align',
    'align*', 'gathered', 'gather', 'gather*', 'split', 'equation', 'equation*'))
_FORBIDDEN = frozenset(('input', 'include', 'includegraphics', 'write', 'write18',
    'openout', 'openin', 'read', 'catcode', 'csname', 'newcommand', 'renewcommand',
    'providecommand', 'def', 'gdef', 'edef', 'xdef', 'let', 'newenvironment',
    'renewenvironment', 'DeclareMathOperator', 'href', 'url', 'htmlId', 'htmlClass',
    'htmlStyle', 'htmlData', 'class', 'style', 'require', 'unicode', 'char',
    'color', 'textcolor', 'colorbox', 'fcolorbox', 'bbox', 'tag', 'label', 'ref',
    'eqref', 'notag', 'nonumber', 'hspace', 'vspace', 'kern', 'mkern', 'hskip',
    'vskip', 'rule', 'raisebox', 'raise', 'lower', 'above', 'abovewithdelims',
    'genfrac', 'skew', 'mspace'))
_SVG_TAGS = frozenset(('svg', 'g', 'path', 'rect', 'line', 'polyline', 'polygon', 'circle', 'ellipse'))
_SVG_ATTRIBUTES = frozenset(('xmlns', 'width', 'height', 'viewBox', 'd', 'fill',
    'stroke', 'stroke-width', 'stroke-linecap', 'stroke-linejoin', 'opacity',
    'fill-opacity', 'stroke-opacity', 'transform', 'x', 'y', 'rx', 'ry', 'cx',
    'cy', 'r', 'x1', 'x2', 'y1', 'y2', 'points'))


@dataclass(frozen=True)
class MathSvg:
    svg: str
    width: float
    height: float
    baseline: float


def _validate_source(latex):
    if not isinstance(latex, str) or not latex.strip() or len(latex) > MAX_LATEX_LENGTH:
        raise ValueError('数式を1〜2000文字のTeXで指定してください。')
    if any(unicodedata.category(char) in ('Cc', 'Cs') and char not in '\n\t' for char in latex):
        raise ValueError('数式に使用できない文字が含まれています。')
    source = latex.strip()
    depth = commands = rows = cells = 0
    position = 0
    while position < len(source):
        char = source[position]
        if char == '\\':
            match = _COMMAND.match(source, position)
            if match is None:
                raise ValueError('数式のTeXコマンドが途中で終わっています。')
            command = match.group()[1:]
            commands += 1
            if command in _FORBIDDEN or commands > 512:
                raise ValueError('このTeXコマンド・数式の複雑さには対応していません。')
            if command == '\\':
                rows += 1
            position = match.end()
            continue
        if char == '{':
            depth += 1
            if depth > MAX_BRACE_DEPTH:
                raise ValueError('数式の入れ子は32段までにしてください。')
        elif char == '}':
            depth -= 1
            if depth < 0:
                raise ValueError('数式の波括弧の対応を確認してください。')
        elif char == '&':
            cells += 1
        elif char in ('%', '#', '$'):
            raise ValueError('数式の区切りや特殊文字を確認してください。')
        position += 1
    if depth:
        raise ValueError('数式の波括弧の対応を確認してください。')
    if rows > 63 or cells > 255 or _DIMENSION.search(source):
        raise ValueError('数式の行数・列数・寸法指定が大きすぎます。')
    environments = []
    for match in _ENVIRONMENT.finditer(source):
        action, name = match.groups()
        if name not in _ENVIRONMENTS:
            raise ValueError('このTeXの数式環境には対応していません。')
        if action == 'begin':
            environments.append(name)
            if len(environments) > 8:
                raise ValueError('数式環境の入れ子が深すぎます。')
        elif not environments or environments.pop() != name:
            raise ValueError('数式のbegin/endの対応を確認してください。')
    if environments:
        raise ValueError('数式のbegin/endの対応を確認してください。')
    return source


@lru_cache(maxsize=1)
def _backend():
    try:
        import ziamath
        from latex2mathml import commands
        from latex2mathml.symbols_parser import SYMBOLS
        from ziamath.tex import tex2mml
    except ImportError as exc:
        raise ValueError('数式表示にはziamathとlatex2mathmlのインストールが必要です。') from exc
    known = set(SYMBOLS)
    for value in vars(commands).values():
        if isinstance(value, str):
            known.add(value)
        elif isinstance(value, (tuple, list, set, dict)):
            known.update(item for item in value if isinstance(item, str))
    return ziamath, tex2mml, frozenset(known)


def _check_mathml(root):
    count = 0
    pending = [(root, 0)]
    while pending:
        element, depth = pending.pop()
        count += 1
        if count > MAX_MATHML_NODES or depth > 64:
            raise ValueError('数式が複雑すぎます。短い式に分けてください。')
        pending.extend((child, depth + 1) for child in element)


def _safe_svg(root):
    root.attrib.pop('xmlns:xlink', None)
    elements = list(root.iter())
    if len(elements) > 8192 or not any(node.tag == 'path' for node in elements):
        raise ValueError('数式を描画できませんでした。TeXを確認してください。')
    for node in elements:
        if node.tag not in _SVG_TAGS or set(node.attrib) - _SVG_ATTRIBUTES:
            raise ValueError('この数式の描画形式には対応していません。')
        if node.text and node.text.strip():
            raise ValueError('この数式の描画形式には対応していません。')
        for attribute in ('fill', 'stroke'):
            value = node.get(attribute)
            if value is not None and value != 'none' and _COLOR.fullmatch(value) is None:
                raise ValueError('この数式の色指定には対応していません。')
    try:
        width, height = float(root.attrib['width']), float(root.attrib['height'])
        viewbox = [float(part) for part in root.attrib['viewBox'].split()]
    except (KeyError, ValueError) as exc:
        raise ValueError('数式の大きさを取得できませんでした。') from exc
    if (len(viewbox) != 4 or not all(math.isfinite(value) for value in (width, height, *viewbox))
            or not 0 < width <= 8192 or not 0 < height <= 4096
            or not 0 <= -viewbox[1] <= height):
        raise ValueError('数式が大きすぎます。短い式に分けてください。')
    svg = ET.tostring(root, encoding='unicode')
    if len(svg.encode('utf-8')) > MAX_SVG_BYTES:
        raise ValueError('数式が複雑すぎます。短い式に分けてください。')
    # Ziamath draws the expression at SVG y=0, its actual math baseline. The
    # viewBox top includes ascenders and margin, so no font-height guess is used.
    return MathSvg(svg, width, height, -viewbox[1])


@lru_cache(maxsize=64)
def _render(source, size, color, inline):
    ziamath, convert, known = _backend()
    for match in _COMMAND.finditer(source):
        command = match.group()
        if len(command) > 2 and command not in known:
            raise ValueError(f'このTeXコマンドには対応していません: {command[:40]}')
    try:
        _check_mathml(ET.fromstring(convert(source, inline=inline)))
        with _LOCK:
            svg2, precision = ziamath.config.svg2, ziamath.config.precision
            numbering = ziamath.config.numbering.autonumber
            try:
                ziamath.config.svg2 = False
                ziamath.config.precision = 3
                ziamath.config.numbering.autonumber = False
                root = ziamath.Latex(source, size=size, color=color, inline=inline, margin=1).svgxml()
            finally:
                ziamath.config.svg2 = svg2
                ziamath.config.precision = precision
                ziamath.config.numbering.autonumber = numbering
        return _safe_svg(root)
    except Exception as exc:
        if isinstance(exc, ValueError) and str(exc).startswith(('数式', 'この')):
            raise
        raise ValueError('数式を描画できませんでした。対応するTeX・括弧を確認してください。') from exc


def render_math_svg(latex, *, size=24, color='#3478dc', inline=False):
    r"""Return immutable path-only SVG plus actual size/baseline in CSS pixels.

    ``latex`` is the inside of a math delimiter, e.g. ``r'\frac{a}{b}'``.
    ``size`` is the font size in pixels before any notebook/view scaling.
    No TeX executable, shell command, external font path, or network is used.
    """
    source = _validate_source(latex)
    if type(size) not in (int, float):
        raise ValueError('数式の文字サイズは6〜96で指定してください。')
    try:
        size = float(size)
    except OverflowError as exc:
        raise ValueError('数式の文字サイズは6〜96で指定してください。') from exc
    if not math.isfinite(size) or not 6 <= size <= 96:
        raise ValueError('数式の文字サイズは6〜96で指定してください。')
    if not isinstance(color, str) or _COLOR.fullmatch(color) is None:
        raise ValueError('数式の色を#3478dcのような形式で指定してください。')
    if type(inline) is not bool:
        raise ValueError('数式の表示方法を確認してください。')
    return _render(source, size, color.lower(), inline)
