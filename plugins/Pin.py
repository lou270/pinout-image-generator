########################################
# Pinout image builder - Pin class
# Louis Barbier
# MIT License
########################################

class Pin:

    def __init__(self, cx, cy, r=0.85, number=1, side='left', displayed=True, pad_name=None, footprint=None):
        self.cx = float(cx)
        self.cy = float(cy)
        self.r = float(r) if r else 0.85
        self.number = int(number)
        self.side = str(side).lower() if side else 'left'
        self.displayed = displayed
        self.pad_name = str(pad_name) if pad_name is not None else str(self.number)
        self.footprint = str(footprint) if footprint is not None else ''
        self.functions = []

    def add_function(self, name, color='#888888'):
        self.functions.append({
            'name': str(name),
            'color': str(color)
        })

    def __repr__(self):
        return f"Pin(#{self.number}, pos=({self.cx:.2f}, {self.cy:.2f}), side={self.side}, funcs={len(self.functions)})"
