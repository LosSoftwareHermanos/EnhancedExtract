"""Minimal read-only UDF reader: lists files in an ISO and where their bytes live.

Supports plain UDF 1.02-2.01 images with type 1 partition maps (what game ISOs
use). Each file is described by extents of (byte offset in the ISO, length).
"""
import struct

SECTOR = 2048

TAG_AVDP = 2
TAG_PD = 5
TAG_LVD = 6
TAG_TD = 8
TAG_FSD = 256
TAG_FID = 257
TAG_AED = 258
TAG_FE = 261
TAG_EFE = 266


class UDFError(Exception):
    pass


class Entry:
    def __init__(self, path, size, extents, is_dir, data=None):
        self.path = path            # "/dir/name.ext"
        self.size = size
        self.extents = extents      # [(iso_offset or None for sparse, length)]
        self.is_dir = is_dir
        self.data = data            # bytes of a small file stored inside its file entry

    def __repr__(self):
        return f"Entry({self.path!r}, {self.size}, {len(self.extents)} extents)"


class UDFImage:
    def __init__(self, path):
        self.path = path
        self.f = open(path, "rb")
        try:
            self._load()
        except Exception:
            self.f.close()
            raise

    def close(self):
        self.f.close()

    # ---------- low level ----------
    def _sector(self, n, count=1):
        self.f.seek(n * SECTOR)
        return self.f.read(SECTOR * count)

    @staticmethod
    def _tag(buf):
        return struct.unpack_from("<H", buf, 0)[0]

    def _lb(self, lbn):
        """Byte offset of a logical block in the partition."""
        return (self.part_start + lbn) * self.block

    def _read_at(self, off, n):
        self.f.seek(off)
        return self.f.read(n)

    # ---------- volume structure ----------
    def _load(self):
        avdp = self._sector(256)
        if self._tag(avdp) != TAG_AVDP:
            raise UDFError("Not a UDF image (no anchor at sector 256).")
        vds_len, vds_loc = struct.unpack_from("<II", avdp, 16)
        self.part_start = None
        lvd = None
        for i in range(max(1, vds_len // SECTOR)):
            d = self._sector(vds_loc + i)
            tag = self._tag(d)
            if tag == TAG_PD and self.part_start is None:
                self.part_start = struct.unpack_from("<I", d, 188)[0]
            elif tag == TAG_LVD and lvd is None:
                lvd = d
            elif tag == TAG_TD:
                break
        if self.part_start is None or lvd is None:
            raise UDFError("UDF volume descriptors not found.")
        self.block = struct.unpack_from("<I", lvd, 212)[0]
        if self.block != SECTOR:
            raise UDFError(f"Unsupported block size {self.block}.")
        nmaps = struct.unpack_from("<I", lvd, 268)[0]
        if nmaps >= 1 and lvd[440] != 1:
            raise UDFError("Unsupported UDF partition map (metadata/virtual partitions).")
        fsd_len, fsd_lbn = struct.unpack_from("<II", lvd, 248)
        fsd = self._read_at(self._lb(fsd_lbn), SECTOR)
        if self._tag(fsd) != TAG_FSD:
            raise UDFError("File set descriptor not found.")
        root_lbn = struct.unpack_from("<I", fsd, 404)[0]
        self.entries = []
        self._walk(root_lbn, "", depth=0)

    def _file_entry(self, lbn):
        """Return (size, extents, is_dir, embedded_data_or_None)."""
        fe = self._read_at(self._lb(lbn), SECTOR)
        tag = self._tag(fe)
        if tag == TAG_FE:
            size = struct.unpack_from("<Q", fe, 56)[0]
            l_ea, l_ad = struct.unpack_from("<II", fe, 168)
            base = 176
        elif tag == TAG_EFE:
            size = struct.unpack_from("<Q", fe, 56)[0]
            l_ea, l_ad = struct.unpack_from("<II", fe, 208)
            base = 216
        else:
            raise UDFError(f"Bad file entry at block {lbn} (tag {tag}).")
        file_type = fe[16 + 11]
        is_dir = file_type == 4
        alloc = struct.unpack_from("<H", fe, 16 + 18)[0] & 7
        ads = fe[base + l_ea: base + l_ea + l_ad]
        if alloc == 3:
            return size, [], is_dir, ads[:size]
        return size, self._extents(ads, alloc), is_dir, None

    def _extents(self, ads, alloc):
        out = []
        step = 8 if alloc == 0 else 16
        pos = 0
        while pos + step <= len(ads):
            raw_len, lbn = struct.unpack_from("<II", ads, pos)
            pos += step
            etype, length = raw_len >> 30, raw_len & 0x3FFFFFFF
            if length == 0:
                break
            if etype == 3:  # continuation: more descriptors in an allocation extent
                aed = self._read_at(self._lb(lbn), length)
                if self._tag(aed) != TAG_AED:
                    raise UDFError("Bad allocation extent descriptor.")
                n = struct.unpack_from("<I", aed, 20)[0]
                out.extend(self._extents(aed[24:24 + n], alloc))
                break
            out.append((self._lb(lbn) if etype == 0 else None, length))
        return out

    def _read_extents(self, size, extents, embedded):
        if embedded is not None:
            return embedded
        chunks, left = [], size
        for off, length in extents:
            n = min(length, left)
            chunks.append(bytes(n) if off is None else self._read_at(off, n))
            left -= n
            if left <= 0:
                break
        return b"".join(chunks)

    def _walk(self, dir_lbn, prefix, depth):
        if depth > 32:
            raise UDFError("Directory tree too deep.")
        size, extents, _, embedded = self._file_entry(dir_lbn)
        data = self._read_extents(size, extents, embedded)
        pos = 0
        while pos + 38 <= len(data):
            if self._tag(data[pos:]) != TAG_FID:
                break
            chars = data[pos + 18]
            l_fi = data[pos + 19]
            icb_lbn = struct.unpack_from("<I", data, pos + 20 + 4)[0]
            l_iu = struct.unpack_from("<H", data, pos + 36)[0]
            name_raw = data[pos + 38 + l_iu: pos + 38 + l_iu + l_fi]
            pos += (38 + l_iu + l_fi + 3) & ~3
            if chars & 0x08 or chars & 0x04:  # parent entry / deleted
                continue
            name = self._dstring(name_raw)
            path = f"{prefix}/{name}"
            fsize, fext, is_dir, emb = self._file_entry(icb_lbn)
            if is_dir:
                self.entries.append(Entry(path, 0, [], True))
                self._walk(icb_lbn, path, depth + 1)
            else:
                self.entries.append(Entry(path, fsize, _trim(fext, fsize), False, data=emb))

    @staticmethod
    def _dstring(raw):
        if not raw:
            return ""
        if raw[0] == 8:
            return raw[1:].decode("latin1")
        if raw[0] == 16:
            return raw[1:].decode("utf-16-be")
        raise UDFError(f"Unknown name encoding {raw[0]}.")

    def files(self):
        return [e for e in self.entries if not e.is_dir]


def _trim(extents, size):
    """Cut the extent list to exactly `size` bytes."""
    out, left = [], size
    for off, length in extents:
        if left <= 0:
            break
        n = min(length, left)
        out.append((off, n))
        left -= n
    return out


def read_file_range(f, entry, offset, size):
    """Read bytes [offset, offset+size) of `entry` from an open ISO file object."""
    if entry.data is not None:
        return entry.data[offset:offset + size]
    out = []
    pos = 0
    end = min(offset + size, entry.size)
    for ext_off, length in entry.extents:
        ext_end = pos + length
        if ext_end > offset and pos < end:
            a = max(offset, pos)
            b = min(end, ext_end)
            if ext_off is None:
                out.append(bytes(b - a))
            else:
                f.seek(ext_off + (a - pos))
                out.append(f.read(b - a))
        pos = ext_end
        if pos >= end:
            break
    return b"".join(out)


def iso_ranges(entry, offset, size):
    """ISO byte ranges [(start, end)] backing bytes [offset, offset+size) of entry."""
    out = []
    pos = 0
    end = min(offset + size, entry.size)
    for ext_off, length in entry.extents:
        ext_end = pos + length
        if ext_end > offset and pos < end and ext_off is not None:
            a = max(offset, pos)
            b = min(end, ext_end)
            out.append((ext_off + (a - pos), ext_off + (b - pos)))
        pos = ext_end
        if pos >= end:
            break
    return out


if __name__ == "__main__":
    import sys
    img = UDFImage(sys.argv[1])
    for e in img.files():
        print(f"{e.size:>16,}  {len(e.extents):>3} ext  {e.path}")
