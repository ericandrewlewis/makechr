import collections
import errors
import id_manifest
import image_processor
import ppu_memory
import rgb


NULL = 0xff
ARTIFACT_VCID = 2


class EightBySixteenProcessor(image_processor.ImageProcessor):
  """Converts image of 8x16 sprites into data structures of the PPU's memory."""

  def __init__(self):
    image_processor.ImageProcessor.__init__(self)
    self._vert_color_manifest = id_manifest.CountingIdManifest()

  def process_block(self, block_y, block_x, is_sprite):
    """Process the block by treating it as two vertical pairs."""
    y = block_y * 2
    x = block_x * 2
    process_tile_func = self.process_tile
    combine_color_needs_func = self.combine_color_needs
    for j in xrange(2):
      # Collect color_needs for vertical pair.
      vert_color_needs = bytearray([NULL, NULL, NULL, NULL])
      for i in xrange(2):
        try:
          (color_needs, dot_profile) = process_tile_func(y + i, x + j, 0, 0)
        except (errors.PaletteOverflowError, errors.ColorNotAllowedError) as e:
          self.collect_error(e, block_y, block_x, i, j)
          continue
        cid = self._color_manifest.id(color_needs)
        did = self._dot_manifest.id(dot_profile)
        self._artifacts[y + i][x + j] = [cid, did, None]
        try:
          combine_color_needs_func(vert_color_needs, color_needs)
        except errors.PaletteOverflowError as e:
          e.block_y = block_y
          e.block_x = block_x
          self.collect_error(e, block_y, block_x, i, j)
          return
      vcid = self._vert_color_manifest.id(vert_color_needs)
      self._artifacts[y    ][x + j][ARTIFACT_VCID] = vcid
      self._artifacts[y + 1][x + j][ARTIFACT_VCID] = vcid

  def process_to_artifacts(self, config):
    """Wrap process_to_artifacts, just to set needs_provider."""
    image_processor.ImageProcessor.process_to_artifacts(self, config)
    self._needs_provider = self._vert_color_manifest

  def make_colorization(self, pal, config):
    """Colorization for each vertical pair."""
    for (y,x) in self.get_generator('8x16'):
      # Upper and lower have the same color. Ignore the lower position.
      (cid, did, vcid) = self._artifacts[y][x]
      color_needs = self._vert_color_manifest.at(vcid)
      try:
        (pid, palette_option) = pal.select(color_needs)
      except IndexError:
        self._err.add(errors.PaletteNoChoiceError(y, x, color_needs))
        pid = 0
      self._ppu_memory.gfx_0.colorization[y    ][x] = pid
      self._ppu_memory.gfx_0.colorization[y + 1][x] = pid

  def traverse_artifacts(self, traversal, pal, config):
    """Traverse in 8x16 order, and create CHR."""
    empty_did = self._dot_manifest.get(chr(0) * 64)
    empty_cid = self._color_manifest.get(chr(pal.bg_color) + chr(NULL) * 3)
    for (y,x) in self.get_generator(traversal):
      (cid_u, did_u, unused) = self._artifacts[y  ][x]
      (cid_l, did_l, unused) = self._artifacts[y+1][x]
      if not config.is_locked_tiles:
        if (empty_cid == cid_u and empty_did == did_u and
            empty_cid == cid_l and empty_did == did_l):
          self._ppu_memory.gfx_0.nametable[y  ][x] = 0x100
          self._ppu_memory.gfx_0.nametable[y+1][x] = 0x100
          self._ppu_memory.empty_tile = 0x100
          continue
      # For 8x16, colorization must be the same for each tile in a vert_pair.
      pid_u = self._ppu_memory.gfx_0.colorization[y][x]
      palette_option = pal.get(pid_u)
      force_store = ppu_memory.PpuMemoryConfig(is_sprite=config.is_sprite,
                                               is_locked_tiles=True)
      # Create upper tile.
      color_needs = self._color_manifest.at(cid_u)
      xlat_u = self.get_dot_xlat(color_needs, palette_option)
      tile_u = self.build_tile(xlat_u, did_u)
      # Create lower tile.
      color_needs = self._color_manifest.at(cid_l)
      xlat_l = self.get_dot_xlat(color_needs, palette_option)
      tile_l = self.build_tile(xlat_l, did_l)
      # Check if the cache contains this key.
      key = str(tile_u) + str(tile_l)
      if key in self._chrdata_cache and not config.is_locked_tiles:
        (chr_num_u, chr_num_l) = self._chrdata_cache[key]
      else:
        # Otherwise, force both tiles to be created.
        (chr_num_u, flip_bits) = self.store_chrdata(xlat_u, did_u, force_store)
        (chr_num_l, flip_bits) = self.store_chrdata(xlat_l, did_l, force_store)
      self._ppu_memory.gfx_0.nametable[y  ][x] = chr_num_u
      self._ppu_memory.gfx_0.nametable[y+1][x] = chr_num_l
      self._chrdata_cache[key] = (chr_num_u, chr_num_l)

  def make_spritelist(self, traversal, pal, config):
    """Convert data from the nametable to create spritelist.

    traversal: Method of traversal
    """
    empty_did = self._dot_manifest.get(chr(0) * 64)
    empty_cid = self._color_manifest.get(chr(pal.bg_color) + chr(NULL) * 3)
    # TODO: Only set this to 1 if the sprite chr order is 1.
    tile_low_bit = 1
    for (y,x) in self.get_generator(traversal):
      (cid_u, did_u, bcid_u) = self._artifacts[y  ][x]
      (cid_l, did_l, bcid_l) = self._artifacts[y+1][x]
      if (empty_cid == cid_u and empty_did == did_u and
          empty_cid == cid_l and empty_did == did_l):
        continue
      tile = self._ppu_memory.gfx_0.nametable[y][x]
      if len(self._ppu_memory.spritelist) == 0x40:
        if not config.is_locked_tiles:
          self._err.add(errors.SpritelistOverflow(y, x))
        continue
      y_pos = y * 8 - 1 if y > 0 else 0
      x_pos = x * 8
      attr = self._ppu_memory.gfx_0.colorization[y][x] | self._flip_bits[y][x]
      self._ppu_memory.spritelist.append([y_pos, tile + tile_low_bit,
                                          attr, x_pos])

  def get_generator(self, traversal):
    return ((y*2,x) for y in xrange(self.blocks_y) for
            x in xrange(self.blocks_x * 2))
