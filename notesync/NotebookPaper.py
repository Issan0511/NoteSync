"""Paper rendering shared by the editor and the headless exporter."""
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QPen

def paint_paper(painter, rect, paper):
    painter.fillRect(rect, Qt.GlobalColor.white)
    if paper == 'plain':
        return
    gap = rect.height() / 24
    painter.setPen(QPen(QColor('#e5e9f0'), .7))
    y = rect.top() + gap
    while y < rect.bottom():
        painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        y += gap
    if paper == 'grid':
        x = rect.left() + gap
        while x < rect.right():
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += gap
