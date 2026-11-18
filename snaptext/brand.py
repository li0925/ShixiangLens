"""Public identity. Legacy storage identifiers stay stable across upgrades."""
from pathlib import Path

NAME = '拾像 Lens'
VERSION = '4.1.0'
TEAM = '空天遥感数学交叉技术创新中心'
TAGLINE = '截图 · 标注 · 识字'
ASSETS = Path(__file__).resolve().parent / 'assets'


def icon():
    from PyQt5.QtGui import QIcon
    return QIcon(str(ASSETS / 'lens.ico'))


def guide(capture='F1', paste='F3'):
    return (f'① 截图：按 {capture}，拖动框选，可拉动边框调整范围。\n'
            f'② 贴图：按 Enter 复制，再按 {paste} 贴到桌面。选区内直接按 F3 也可贴图。\n'
            '③ 标注：在贴图上按空格，选择箭头、画笔、文字等工具。\n'
            '④ 识字：按住 Ctrl 在图上拖选；右键也可识别整图。结果可编辑、复制。\n'
            '⑤ 找回：双击隐藏贴图；托盘图标右键 → 显示全部贴图。\n\n'
            '滚轮缩放 · Ctrl+滚轮调透明度 · Ctrl+S 保存 · Ctrl+Z 撤销\n'
            '右键菜单有更多功能。关闭说明窗口后仍驻留托盘；托盘右键可退出。')
