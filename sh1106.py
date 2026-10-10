"""Minimal MicroPython driver for the SH1106 I2C OLED (128x64, 4-pin).
No external library needed - this is the whole driver.
"""
import framebuf

_SET_CONTRAST = 0x81
_DISPLAY_ALLON_RESUME = 0xA4
_NORMAL_DISPLAY = 0xA6
_DISPLAY_OFF = 0xAE
_DISPLAY_ON = 0xAF
_SET_DISPLAY_OFFSET = 0xD3
_SET_COM_PINS = 0xDA
_SET_VCOM_DETECT = 0xDB
_SET_DISPLAY_CLOCKDIV = 0xD5
_SET_PRECHARGE = 0xD9
_SET_MULTIPLEX = 0xA8
_SET_STARTLINE = 0x40
_MEMORY_MODE = 0x20
_COM_SCAN_DEC = 0xC8
_SEG_REMAP = 0xA0
_CHARGE_PUMP = 0x8D


class SH1106_I2C(framebuf.FrameBuffer):
    """res, rotate, delay accepted for API compatibility but unused -
    the common 4-pin modules have no hardware reset line and need no delay."""

    def __init__(self, width, height, i2c, res=None, addr=0x3c, rotate=0, delay=0):
        self.i2c = i2c
        self.addr = addr
        self.width = width
        self.height = height
        self.pages = height // 8
        self.buffer = bytearray(self.pages * width)
        super().__init__(self.buffer, width, height, framebuf.MONO_VLSB)
        self.init_display()

    def write_cmd(self, cmd):
        self.i2c.writeto(self.addr, bytearray([0x00, cmd]))

    def write_data(self, buf):
        self.i2c.writeto(self.addr, b'\x40' + buf)

    def init_display(self):
        for cmd in (
            _DISPLAY_OFF,
            _SET_DISPLAY_CLOCKDIV, 0x80,
            _SET_MULTIPLEX, self.height - 1,
            _SET_DISPLAY_OFFSET, 0x00,
            _SET_STARTLINE | 0x00,
            _CHARGE_PUMP, 0x14,
            _MEMORY_MODE, 0x00,
            _SEG_REMAP | 0x01,
            _COM_SCAN_DEC,
            _SET_COM_PINS, 0x12,
            _SET_CONTRAST, 0xCF,
            _SET_PRECHARGE, 0xF1,
            _SET_VCOM_DETECT, 0x40,
            _DISPLAY_ALLON_RESUME,
            _NORMAL_DISPLAY,
            _DISPLAY_ON,
        ):
            self.write_cmd(cmd)
        self.fill(0)
        self.show()

    def show(self):
        for page in range(self.pages):
            self.write_cmd(0xB0 + page)   # set page address
            self.write_cmd(0x02)          # set lower column = 2
            self.write_cmd(0x10)          # set upper column = 0
            start = page * self.width
            self.write_data(bytes(self.buffer[start:start + self.width]))