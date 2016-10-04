import unittest

import context
from makechr import app, bg_color_spec, image_processor, free_sprite_processor

import filecmp
import os
import tempfile


class MockArgs(object):
  def __init__(self):
    self.dir = tempfile.mkdtemp()
    self.palette_view = self.tmppng('pal')
    self.colorization_view = self.tmppng('color')
    self.reuse_view = self.tmppng('reuse')
    self.nametable_view = self.tmppng('nt')
    self.chr_view = self.tmppng('chr')
    self.grid_view = self.tmppng('grid')
    self.bg_color = bg_color_spec.default()
    self.traversal = 'horizontal'
    self.is_sprite = False
    self.is_locked_tiles = False
    self.order = None
    self.compile = None
    self.output = self.tmpfile('actual-%s.dat')

  def tmppng(self, name):
    return os.path.join(self.dir, 'actual-%s.png' % name)

  def tmpfile(self, template):
    return os.path.join(self.dir, template)


class GeneralAppTests(unittest.TestCase):
  def setUp(self):
    self.args = MockArgs()
    self.golden_file_prefix = 'full-image'

  def process_image(self, img, palette_text=None, auto_sprite_bg=False):
    if self.args.traversal != 'free':
      self.processor = image_processor.ImageProcessor()
      if auto_sprite_bg:
        self.processor._test_only_auto_sprite_bg = auto_sprite_bg
      self.processor.process_image(img, palette_text,
                                   self.args.bg_color.look,
                                   self.args.traversal, self.args.is_sprite,
                                   self.args.is_locked_tiles)
    else:
      self.processor = free_sprite_processor.FreeSpriteProcessor()
      self.processor.process_image(img, palette_text,
                                   self.args.bg_color.look,
                                   self.args.bg_color.fill)
    self.ppu_memory = self.processor.ppu_memory()
    self.err = self.processor.err()

  def create_output(self):
    a = app.Application()
    if self.args.bg_color.fill:
      self.ppu_memory.override_bg_color(self.args.bg_color.fill)
    a.create_output(self.ppu_memory, self.args, self.args.traversal)

  def assert_output_result(self, name, golden_suffix=''):
    actual_file = self.args.output % name
    expect_file = self.golden(name + golden_suffix, 'dat')
    self.assert_file_eq(actual_file, expect_file)

  def assert_not_exist(self, name):
    missing_file = self.args.output % name
    self.assertFalse(os.path.exists(missing_file))

  def golden(self, name, ext):
    if name:
      return 'testdata/%s-%s.%s' % (self.golden_file_prefix, name, ext)
    else:
      return 'testdata/%s.%s' % (self.golden_file_prefix, ext)

  def assert_file_eq(self, actual_file, expect_file):
    self.assertTrue(filecmp.cmp(actual_file, expect_file, shallow=False),
                    "Files did not match actual:%s expect:%s" % (
                      actual_file, os.path.abspath(expect_file)))
