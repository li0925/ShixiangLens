"""Turn images, image files, text, HTML and color values into desktop pins."""
from PyQt5.QtGui import QImage,QPainter,QColor,QTextDocument,QFont
from PyQt5.QtCore import Qt,QSizeF


def clipboard_image(mime):
    if mime.hasImage():
        from PyQt5.QtGui import QPixmap
        value=mime.imageData()
        return value.toImage() if isinstance(value,QPixmap) else QImage(value)
    if mime.hasUrls():
        for url in mime.urls():
            if url.isLocalFile():
                image=QImage(url.toLocalFile())
                if not image.isNull(): return image
    text=mime.text().strip() if mime.hasText() else ''
    color=QColor(text)
    if text and color.isValid() and (text.startswith('#') or text.lower().startswith(('rgb','red','blue','green'))):
        image=QImage(340,150,QImage.Format_RGB32)
        image.fill(color)
        painter=QPainter(image)
        painter.setPen(Qt.white if color.lightness()<140 else Qt.black)
        painter.setFont(QFont('Consolas',14))
        painter.drawText(image.rect().adjusted(16,10,-10,-10),Qt.AlignVCenter,
            f'{color.name().upper()}\nRGB: {color.red()}, {color.green()}, {color.blue()}')
        painter.end()
        return image
    if not text and not mime.hasHtml(): return QImage()
    # Disable all external document resources, including remote image loading.
    class LocalDocument(QTextDocument):
        def loadResource(self,kind,url): return None
    doc=LocalDocument()
    doc.setDefaultFont(QFont('Microsoft YaHei',12))
    if mime.hasHtml(): doc.setHtml(mime.html())
    else: doc.setPlainText(text)
    doc.setTextWidth(min(800,max(200,doc.idealWidth()+20)))
    size=doc.size().toSize()
    image=QImage(min(1000,size.width()+24),min(4096,size.height()+24),QImage.Format_ARGB32)
    image.fill(Qt.white)
    painter=QPainter(image)
    painter.translate(12,12)
    doc.drawContents(painter)
    painter.end()
    return image
