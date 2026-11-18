from PyQt5.QtCore import Qt,QRectF,QPointF
from PyQt5.QtGui import QPixmap,QIcon,QPainter,QPen,QColor,QFont


def tool_icon(name):
    pixmap=QPixmap(24,24)
    pixmap.fill(Qt.transparent)
    painter=QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor('#33465d'),1.6,Qt.SolidLine,Qt.RoundCap))
    if name=='rect': painter.drawRect(4,5,16,14)
    elif name=='ellipse': painter.drawEllipse(4,5,16,14)
    elif name=='line': painter.drawLine(4,19,20,5)
    elif name=='arrow':
        painter.drawLine(4,20,20,4)
        painter.drawLine(20,4,12,5)
        painter.drawLine(20,4,19,12)
    elif name=='mosaic':
        for x,y in [(4,4),(12,4),(8,8),(16,8),(4,12),(12,12),(8,16),(16,16)]:
            painter.fillRect(x,y,4,4,QColor('#33465d'))
    elif name in ('pen','highlight'):
        painter.setPen(QPen(QColor('#33465d'),4 if name=='highlight' else 2))
        painter.drawLine(5,19,18,5)
        painter.drawLine(5,19,9,18)
    elif name=='eraser':
        painter.translate(12,12)
        painter.rotate(-40)
        painter.drawRect(-5,-8,10,16)
        painter.fillRect(-4,1,8,6,QColor('#a3b8d5'))
    else:
        painter.setFont(QFont('Segoe UI',12))
        painter.drawText(pixmap.rect(),Qt.AlignCenter,{'move':'✥','text':'T','ocr':'文','crop':'⌗','blur':'◉'}.get(name,name[:1]))
    painter.end()
    return QIcon(pixmap)
